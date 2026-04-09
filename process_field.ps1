<#
.SYNOPSIS
    process_field.ps1 - Automatisation du post-traitement des images FITS.
#>

param(
    [int]$Year, [int]$Month, [int]$Day,
    [int]$Hour, [int]$Minute, [int]$Second,
    [string]$ImageType, [string]$TargetName
)

# --------------------------------------------------------------------------
# 0. CONFIGURATION
# --------------------------------------------------------------------------
$DriveLocal   = "C:"
$DriveArchive = "E:"
$JIM_PC       = "\\JIM-PC\NightImages"  # <--- CHANGEMENT ICI : Chemin UNC direct
$NAS          = "Z:"

$PythonExe    = "$DriveLocal\Users\aster\AppData\Local\Programs\Python\Python312\python.exe"
$DesignPy     = "$DriveLocal\NightImages\Scripts\neocp_designation.py"

function Write-Log {
    param([string]$Message)
    $logFile = "$DriveLocal\NightImages\Scripts\process_field.log"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp : $Message" | Add-Content -Path $logFile
}

Write-Log "--- Début Session : $TargetName ($ImageType) ---"

# Calcul de la date de la nuit (à midi pour l'astronomie)
$dateObj = Get-Date -Year $Year -Month $Month -Day $Day -Hour $Hour -Minute $Minute -Second $Second
$nightDate = $dateObj.ToUniversalTime().AddHours(-12).ToString("yyyy-MM-dd")

# 1. Génération du code champ
$fieldCode = & $PythonExe $DesignPy --next-field $Year $Month $Day 2>&1
$fieldCode = $fieldCode.Trim()
if ($fieldCode -notmatch "^[A-Z1-5]{6}$") {
    Write-Log "ERREUR : code champ invalide : '$fieldCode'"
    exit
}
Write-Log "Code champ : $fieldCode"

# --- CONSTRUCTION DES CHEMINS ---
# Note : On retire "NightImages" ici car il est déjà dans $JIM_PC
$baseRemote   = Join-Path $JIM_PC "$nightDate\$ImageType\$fieldCode"
$baseNAS      = Join-Path $NAS "$nightDate\$ImageType\$fieldCode"
$baseArchive  = Join-Path $DriveArchive "NightImages\$nightDate\$ImageType\$fieldCode"

$isConfirm = ($ImageType -eq "CONFIRM")

# 2. Localisation et Préparation
$parentDir = "$DriveLocal\NightImages\$nightDate\$ImageType"
if (-not (Test-Path $parentDir)) { $parentDir = "$DriveLocal\NightImages\$nightDate\LIGHT" }
$srcFieldDir = Join-Path $parentDir $TargetName

$orphans = Get-ChildItem -Path $parentDir -Filter "$TargetName*.fits" -File
if ($orphans.Count -gt 0) {
    if (-not (Test-Path $srcFieldDir)) { New-Item -ItemType Directory -Path $srcFieldDir -Force | Out-Null }
    $orphans | Move-Item -Destination $srcFieldDir -Force
}

if (-not (Test-Path $srcFieldDir) -or (Get-ChildItem -Path $srcFieldDir -Filter "*.fits").Count -eq 0) {
    Write-Log "ERREUR : Aucune image trouvée pour $TargetName"
    exit
}

# 3. Header FITS (Extraction Tag)
$fitsFiles = Get-ChildItem -Path $srcFieldDir -Filter "*.fits" -File
$fieldTag = "UnknownCoords"
if ($fitsFiles.Count -gt 0) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($fitsFiles[0].FullName)
        $header = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 28800)
        $tra = 0.0; $tdec = 0.0
        if ($header -match "RA\s*=\s*([0-9\.\-]+)") { $tra = [double]$matches[1] }
        if ($header -match "DEC\s*=\s*([0-9\.\-]+)") { $tdec = [double]$matches[1] }
        $totalSecRA = [math]::Round(($tra / 15) * 3600); $rh = [math]::Floor($totalSecRA / 3600); $rm = [math]::Floor(($totalSecRA % 3600) / 60); $rs = $totalSecRA % 60
        $ds = if($tdec -lt 0){"-"}else{"+"}; $da = [math]::Abs($tdec); $totalSecDec = [math]::Round($da * 3600); $dd = [math]::Floor($totalSecDec / 3600); $dm = [math]::Floor(($totalSecDec % 3600) / 60); $dsoc = $totalSecDec % 60
        $fieldTag = "$($rh.ToString('00'))h$($rm.ToString('00'))m$($rs.ToString('00'))s_$ds$($dd.ToString('00'))d$($dm.ToString('00'))m$($dsoc.ToString('00'))s"
    } catch { Write-Log "ERREUR : Lecture header FITS." }
}

# 4. Branche CONFIRM
if ($isConfirm) {
    # Note : RemotePath doit être défini ou utiliser baseRemote. Ici on garde votre logique.
    $baseRemoteConf = Join-Path $JIM_PC "NightImages\confsync\$nightDate\$TargetName\bin2"
    $baseArchiveConf = Join-Path $DriveArchive "NightImages\$nightDate\CONFIRM\$TargetName\bin2"
    if (-not (Test-Path $baseArchiveConf)) { New-Item -ItemType Directory -Path $baseArchiveConf -Force | Out-Null }

    foreach ($f in $fitsFiles) {
        $num = if ($f.BaseName -match "(\d+)$") { $matches[1] } else { "0000" }
        $newName = "${TargetName}_${fieldTag}_${num}.fits"
        Copy-Item $f.FullName -Destination (Join-Path $baseArchiveConf $newName) -Force
        robocopy $srcFieldDir $baseRemoteConf $f.Name /R:10 /W:10 /NJH /NJS | Out-Null
    }
    exit
}

# ---------------------------------------------------------
# 5. Branche SURVEY
# ---------------------------------------------------------
$bin1 = Join-Path $srcFieldDir "bin1"
$bin2 = Join-Path $srcFieldDir "bin2"
@($bin1, $bin2) | ForEach-Object { if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null } }

foreach ($f in $fitsFiles) {
    $num = if ($f.BaseName -match "(\d+)$") { $matches[1] } else { "0000" }
    $newName = "${fieldCode}_${fieldTag}_${num}.fits"
    Move-Item $f.FullName -Destination (Join-Path $bin1 $newName) -Force
}

# Binning Siril
$sirilExe = "$DriveLocal\Program Files\Siril\bin\siril-cli.exe"
if (Test-Path $sirilExe) {
    foreach ($f in (Get-ChildItem $bin1 -Filter *.fits)) {
        $outPath = Join-Path $bin2 ($f.Name)
        $tmpScript = "requires 1.2.0`nload `"$($f.FullName -replace '\\','\\')`"`nbinxy 2 -sum`nsave `"$($outPath -replace '\\','\\')`"`nclose"
        $tmpPath = Join-Path $env:TEMP "siril_$(Get-Random).ssf"
        $tmpScript | Out-File -Encoding ascii $tmpPath
        & $sirilExe -s $tmpPath | Out-Null
        Remove-Item $tmpPath -ErrorAction SilentlyContinue
    }
}

# --------------------------------------------------------------------------
# 6. TRANSFERTS ET SAUVEGARDES (TRIPLE REDONDANCE)
# --------------------------------------------------------------------------

# 1. ARCHIVE LOCALE (E:)
Write-Log "Sauvegarde Archive locale (E:)..."
robocopy $bin1 (Join-Path $baseArchive "bin1") *.fits /MT:8 /Z /R:5 /W:5 | Out-Null
robocopy $bin2 (Join-Path $baseArchive "bin2") *.fits /MT:8 /Z /R:5 /W:5 | Out-Null

# 2. JIM-PC (Réseau direct)
Write-Log "Transfert vers JIM-PC (\\JIM-PC)..."
robocopy $bin1 (Join-Path $baseRemote "bin1") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null
robocopy $bin2 (Join-Path $baseRemote "bin2") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null

# 2.1 SIGNAL POUR TYCHO TRACKER
# On pointe directement vers le dossier sync à la racine du partage
$networkSyncDir = Join-Path $JIM_PC "sync" 
try {
    if (-not (Test-Path $networkSyncDir)) { New-Item -ItemType Directory -Path $networkSyncDir -Force | Out-Null }
    $pathBin2 = Join-Path $baseRemote "bin2"
    $pathBin2 | Out-File (Join-Path $networkSyncDir ("bin2_$fieldCode.txt")) -Encoding ascii -Force
    Write-Log "Signal bin2 envoyé via chemin UNC."
} catch {
    Write-Log "ALERTE : Impossible d'écrire le signal."
}

# 3. NAS (Z:) - Sauvegarde supplémentaire
Write-Log "Sauvegarde sur le NAS (Z:)..."
robocopy $bin1 (Join-Path $baseNAS "bin1") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null
robocopy $bin2 (Join-Path $baseNAS "bin2") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null

# --------------------------------------------------------------------------
# 7. NETTOYAGE LOCAL (C:)
# --------------------------------------------------------------------------
$checkPath = Join-Path $baseArchive "bin2"
if (Test-Path $checkPath) {
    $countE = (Get-ChildItem $checkPath -Filter *.fits).Count
    if ($countE -gt 0) {
        Get-ChildItem $srcFieldDir -Recurse | Remove-Item -Recurse -Force
        Write-Log "NETTOYAGE : Fichiers locaux supprimés. Sauvegarde confirmée sur E: ($countE fichiers)."
    }
} else {
    Write-Log "ATTENTION : Nettoyage annulé, dossier introuvable sur E:."
}