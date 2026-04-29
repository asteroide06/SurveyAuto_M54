<#
.SYNOPSIS
    Post-traitement FITS : Priorité BIN2 pour Tycho Tracker.

.DESCRIPTION
    1. Calcul Date Astro & Code Champ (Python).
    2. Header FITS (RA/DEC) & Renommage.
    3. Binning 2x2 (Siril-cli) avec chemins robustes.
    4. Transfert PRIORITAIRE BIN2 vers JIM-PC + Signal Tycho immédiat.
    5. Sauvegardes secondaires (BIN1, Archive E:, NAS).
    6. Nettoie C: si la copie sur E: est confirmée.

.NOTES
    Version : 3.0 (Priorité Tycho & Correction Siril
    Auteur : Jean-Marc Mari / Gemini
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
$JIM_PC       = "\\JIM-PC\NightImages" 
$NAS          = "Z:"

$PythonExe    = "$DriveLocal\Users\aster\AppData\Local\Programs\Python\Python312\python.exe"
$DesignPy     = "$DriveLocal\NightImages\Scripts\neocp_designation.py"

function Write-Log {
    param([string]$Message)
    $logFile = "$DriveLocal\NightImages\Scripts\process_field.log"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp : $Message" | Add-Content -Path $logFile
}

function Get-UniqueTargetName {
    param([string]$BasePath, [string]$TargetName)
    $finalPath = Join-Path $BasePath $TargetName
    if (-not (Test-Path $finalPath)) { return $TargetName }
    $i = 2
    while (Test-Path "${finalPath}_$i") { $i++ }
    return "${TargetName}_$i"
}

Write-Log "--- Début Session : $TargetName ($ImageType) ---"

# Calcul de la date de la nuit
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

$isConfirm = ($ImageType -eq "CONFIRM")

# 2. Localisation Source sur C:
$parentDir = "$DriveLocal\NightImages\$nightDate\$ImageType"
if (-not (Test-Path $parentDir)) { $parentDir = "$DriveLocal\NightImages\$nightDate\LIGHT" }
$srcFieldDir = Join-Path $parentDir $TargetName

# Récupération fichiers orphelins
$orphans = Get-ChildItem -Path $parentDir -Filter "$TargetName*.fits" -File
if ($orphans.Count -gt 0) {
    if (-not (Test-Path $srcFieldDir)) { New-Item -ItemType Directory -Path $srcFieldDir -Force | Out-Null }
    $orphans | Move-Item -Destination $srcFieldDir -Force
}

if (-not (Test-Path $srcFieldDir) -or (Get-ChildItem -Path $srcFieldDir -Filter "*.fits").Count -eq 0) {
    Write-Log "ERREUR : Aucune image trouvée pour $TargetName"
    exit
}

# 3. Extraction Coordonnées Header FITS
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
        $fieldTag = "$($rh.ToString('00'))h$($rm.ToString('00'))s_$ds$($dd.ToString('00'))d$($dm.ToString('00'))m$($dsoc.ToString('00'))s"
    } catch { Write-Log "ERREUR : Lecture header FITS." }
}

# 4. Préparation, Renommage et Binning
$bin1 = Join-Path $srcFieldDir "bin1"
$bin2 = Join-Path $srcFieldDir "bin2"
@($bin1, $bin2) | ForEach-Object { if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null } }

Write-Log "Organisation des fichiers et renommage..."
foreach ($f in $fitsFiles) {
    $num = if ($f.BaseName -match "(\d+)$") { $matches[1] } else { "0000" }
    $prefix = if ($isConfirm) { $TargetName } else { $fieldCode }
    $newName = "${prefix}_${fieldTag}_${num}.fits"
    Move-Item $f.FullName -Destination (Join-Path $bin1 $newName) -Force
}

# --- BINNING 2x2 VIA SIRIL ---
$sirilExe = "$DriveLocal\Program Files\Siril\bin\siril-cli.exe"
if (Test-Path $sirilExe) {
    $filesToBin = Get-ChildItem $bin1 -Filter *.fits
    Write-Log "Lancement Siril pour $($filesToBin.Count) images..."
    foreach ($f in $filesToBin) {
        $outPath = Join-Path $bin2 ($f.Name)
        # Chemins robustes avec / pour Siril
        $tmpScript = "requires 1.2.0`ncd `"$($bin1 -replace '\\','/')`"`nload `"$($f.Name)`"`nbinxy 2 -sum`nsave `"$($outPath -replace '\\','/')`"`nclose"
        $tmpPath = Join-Path $env:TEMP "siril_$(Get-Random).ssf"
        $tmpScript | Out-File (New-Item $tmpPath -Force) -Encoding ascii
        & $sirilExe -s $tmpPath | Out-Null
        Remove-Item $tmpPath -ErrorAction SilentlyContinue
    }
}

# --------------------------------------------------------------------------
# 5. TRANSFERTS PRIORITAIRES ET SIGNAUX TYCHO
# --------------------------------------------------------------------------
if ($isConfirm) {
    $remoteRoot = Join-Path $JIM_PC "confsync\$nightDate"
    $uniqueName = Get-UniqueTargetName -BasePath $remoteRoot -TargetName $TargetName
    $baseRemote = Join-Path $remoteRoot $uniqueName
    $baseArchive = Join-Path $DriveArchive "NightImages\$nightDate\CONFIRM\$uniqueName"
} else {
    $baseRemote = Join-Path $JIM_PC "$nightDate\$ImageType\$fieldCode"
    $baseArchive = Join-Path $DriveArchive "NightImages\$nightDate\$ImageType\$fieldCode"
    $baseNAS = Join-Path $NAS "$nightDate\$ImageType\$fieldCode"
}

# A. PRIORITÉ BIN2 vers JIM-PC
Write-Log "TRANSFERT PRIORITAIRE : BIN2 vers JIM-PC..."
$remoteBin2 = Join-Path $baseRemote "bin2"
if (-not (Test-Path $remoteBin2)) { New-Item -ItemType Directory -Path $remoteBin2 -Force | Out-Null }
robocopy $bin2 $remoteBin2 *.fits /MT:8 /Z /NJH /NJS | Out-Null

# B. SIGNAL TYCHO IMMÉDIAT
Write-Log "Signal Tycho envoyé."
if ($isConfirm) {
    Add-Content -Path (Join-Path $JIM_PC "confsync\todo.txt") -Value $uniqueName
} else {
    $networkSyncDir = Join-Path $JIM_PC "sync"
    if (-not (Test-Path $networkSyncDir)) { New-Item -ItemType Directory -Path $networkSyncDir -Force | Out-Null }
    $pathBin2Local = $baseRemote -replace [regex]::Escape($JIM_PC), "H:\NightImages"
    $pathBin2Local = Join-Path $pathBin2Local "bin2"
    $pathBin2Local | Out-File (Join-Path $networkSyncDir ("bin2_$fieldCode.txt")) -Encoding ascii -Force
}

# C. AUTRES TRANSFERTS (Archive et BIN1)
Write-Log "Sauvegardes secondaires en cours..."
# Bin2 vers Archive/NAS
$archiveBin2 = Join-Path $baseArchive "bin2"
if (-not (Test-Path $archiveBin2)) { New-Item -ItemType Directory -Path $archiveBin2 -Force | Out-Null }
robocopy $bin2 $archiveBin2 *.fits /R:5 /W:5 /NJH /NJS | Out-Null

if (-not $isConfirm -and (Test-Path $NAS)) {
    $nasBin2 = Join-Path $baseNAS "bin2"
    if (-not (Test-Path $nasBin2)) { New-Item -ItemType Directory -Path $nasBin2 -Force | Out-Null }
    robocopy $bin2 $nasBin2 *.fits /MT:8 /Z /NJH /NJS | Out-Null
}

# Bin1 partout (JIM-PC, Archive, NAS)
$destBin1 = @{ "JIM-PC" = Join-Path $baseRemote "bin1"; "Archive" = Join-Path $baseArchive "bin1" }
if (-not $isConfirm -and (Test-Path $NAS)) { $destBin1.Add("NAS", (Join-Path $baseNAS "bin1")) }

foreach ($key in $destBin1.Keys) {
    $p = $destBin1[$key]
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
    robocopy $bin1 $p *.fits /MT:8 /Z /NJH /NJS | Out-Null
}

# --------------------------------------------------------------------------
# 7. NETTOYAGE FINAL (C:)
# --------------------------------------------------------------------------
$checkPath = Join-Path $baseArchive "bin2"
if (Test-Path $checkPath) {
    $countE = (Get-ChildItem $checkPath -Filter *.fits).Count
    if ($countE -gt 0) {
        Remove-Item -Path $srcFieldDir -Recurse -Force
        Write-Log "NETTOYAGE : $TargetName supprimé de C: (Sauvegarde E: OK)."
    }
}