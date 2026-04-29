<#
.SYNOPSIS
    Automatisation complète du post-traitement des images FITS pour les sessions SURVEY et CONFIRM.

.DESCRIPTION
    Ce script effectue les opérations suivantes :
    1. Calcule la date astronomique de la session (Date-12h).
    2. Génère un code de champ unique via un script Python externe.
    3. Organise les fichiers FITS locaux, extrait les coordonnées RA/DEC du header et renomme les fichiers.
    4. Gère deux modes de traitement :
       - Mode SURVEY : Renommage, binning 2x2 via Siril, et triple sauvegarde (Archive E:, JIM-PC H:, NAS Z:).
       - Mode CONFIRM : Renommage et transfert spécifique vers le dossier de synchronisation réseau.
    5. Envoie un signal (fichier .txt) pour déclencher automatiquement l'analyse dans Tycho Tracker.
    6. Nettoie les fichiers temporaires sur le disque C: après confirmation de la sauvegarde sur E:.

.PARAMETER Year
    Année de la capture (format AAAA). Utilisée pour la date astro et le code champ.

.PARAMETER Month
    Mois de la capture (1-12).

.PARAMETER Day
    Jour de la capture (1-31).

.PARAMETER Hour
    Heure de la capture (0-23). Utilisée pour calculer la date de la nuit (si < 12h, appartient à la nuit précédente).

.PARAMETER Minute
    Minute de la capture (0-59).

.PARAMETER Second
    Seconde de la capture (0-59).

.PARAMETER ImageType
    Type de session : 
    - "LIGHT" ou "SURVEY" : Déclenche le processus standard de binning et d'archivage triple.
    - "CONFIRM" : Déclenche le processus simplifié pour les confirmations d'astéroïdes.

.PARAMETER TargetName
    Nom de la cible tel que défini dans NINA (ex: "Field_1"). Utilisé pour localiser les fichiers sources sur C:.

.EXAMPLE
    .\process_field.ps1 -Year 2026 -Month 04 -Day 08 -Hour 23 -Minute 30 -Second 00 -ImageType "LIGHT" -TargetName "Field_1"
    Traite le premier champ de la nuit du 8 avril 2026.

.NOTES
    Auteur : Aster
    Dépendances : Siril (siril-cli.exe), Python 3.x, neocp_designation.py.
    Le script utilise désormais des chemins UNC (\\JIM-PC\...) pour améliorer la fiabilité réseau.
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
$baseRemoteConf = Join-Path $JIM_PC "confsync\$nightDate\$TargetName"
$baseArchiveConf = Join-Path $DriveArchive "NightImages\$nightDate\CONFIRM\$TargetName"
$todoPath = Join-Path $JIM_PC "confsync\todo.txt"


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

# --------------------------------------------------------------------------
# 4. PRÉPARATION, RENOMMAGE ET BINNING (COMMUN À TOUS LES TYPES)
# --------------------------------------------------------------------------

# Création des sous-dossiers locaux bin1 et bin2 sur C:
$bin1 = Join-Path $srcFieldDir "bin1"
$bin2 = Join-Path $srcFieldDir "bin2"
@($bin1, $bin2) | ForEach-Object { if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null } }

Write-Log "Organisation des fichiers et renommage..."
foreach ($f in $fitsFiles) {
    $num = if ($f.BaseName -match "(\d+)$") { $matches[1] } else { "0000" }
    
    # Choix du préfixe : TargetName pour Confirmation, FieldCode pour Survey
    $prefix = if ($isConfirm) { $TargetName } else { $fieldCode }
    $newName = "${prefix}_${fieldTag}_${num}.fits"
    
    # Déplacement vers le dossier bin1 local
    Move-Item $f.FullName -Destination (Join-Path $bin1 $newName) -Force
}

# --- BINNING 2x2 VIA SIRIL ---
$sirilExe = "$DriveLocal\Program Files\Siril\bin\siril-cli.exe"
if (Test-Path $sirilExe) {
    Write-Log "Lancement du binning 2x2 Siril (Survey & Confirm)..."
    foreach ($f in (Get-ChildItem $bin1 -Filter *.fits)) {
        $outPath = Join-Path $bin2 ($f.Name)
        # Script Siril pour charger, binner et sauvegarder
        $tmpScript = "requires 1.2.0`nload `"$($f.FullName -replace '\\','\\')`"`nbinxy 2 -sum`nsave `"$($outPath -replace '\\','\\')`"`nclose"
        $tmpPath = Join-Path $env:TEMP "siril_$(Get-Random).ssf"
        $tmpScript | Out-File -Encoding ascii $tmpPath
        & $sirilExe -s $tmpPath | Out-Null
        Remove-Item $tmpPath -ErrorAction SilentlyContinue
    }
}

# --------------------------------------------------------------------------
# 5. TRANSFERTS VERS JIM-PC ET ARCHIVES
# --------------------------------------------------------------------------

if ($isConfirm) {
    # --- MODE CONFIRMATION ---

    Write-Log "Transfert CONFIRM (bin1+bin2) vers JIM-PC..."
    
# Création des répertoires distants (bin1 et bin2)
    $remoteBin1 = Join-Path $baseRemoteConf "bin1"
    $remoteBin2 = Join-Path $baseRemoteConf "bin2"
    if (-not (Test-Path $remoteBin1)) { New-Item -ItemType Directory -Path $remoteBin1 -Force | Out-Null }
    if (-not (Test-Path $remoteBin2)) { New-Item -ItemType Directory -Path $remoteBin2 -Force | Out-Null }
    
    # Transfert vers JIM-PC
    robocopy $bin1 $remoteBin1 *.fits /R:10 /W:10 /NJH /NJS | Out-Null
    robocopy $bin2 $remoteBin2 *.fits /R:10 /W:10 /NJH /NJS | Out-Null
    
    # Archive locale sur E:
    robocopy $bin1 (Join-Path $baseArchiveConf "bin1") *.fits /R:5 /W:5 /NJH /NJS | Out-Null
    robocopy $bin2 (Join-Path $baseArchiveConf "bin2") *.fits /R:5 /W:5 /NJH /NJS | Out-Null

    # Ajout à la liste de traitement du Master Watcher
    Add-Content -Path $todoPath -Value $TargetName
    Write-Log "CONFIRM : Signal envoyé dans todo.txt."

} else {
    # --- MODE SURVEY ---


    Write-Log "Transfert SURVEY (bin1+bin2) vers JIM-PC et NAS..."
    
    # Transfert vers JIM-PC
    robocopy $bin1 (Join-Path $baseRemote "bin1") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null
    robocopy $bin2 (Join-Path $baseRemote "bin2") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null

    # Signal pour Tycho (Survey uniquement)
    $networkSyncDir = Join-Path $JIM_PC "sync"
    if (-not (Test-Path $networkSyncDir)) { New-Item -ItemType Directory -Path $networkSyncDir -Force | Out-Null }
    
    # Conversion dynamique du chemin UNC vers le volume local H:
    $pathBin2Local = $baseRemote -replace [regex]::Escape($JIM_PC), "H:\NightImages"
    $pathBin2Local = Join-Path $pathBin2Local "bin2"
    
    # Écriture du fichier signal
    $pathBin2Local | Out-File (Join-Path $networkSyncDir ("bin2_$fieldCode.txt")) -Encoding ascii -Force
    # Sauvegarde NAS
    robocopy $bin1 (Join-Path $baseNAS "bin1") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null
    robocopy $bin2 (Join-Path $baseNAS "bin2") *.fits /MT:8 /Z /R:20 /W:15 | Out-Null
}

# --------------------------------------------------------------------------
# 7. NETTOYAGE LOCAL (C:)
# --------------------------------------------------------------------------
# On définit le chemin d'archive à vérifier selon le mode
$finalArchiveCheck = if ($isConfirm) { Join-Path $baseArchiveConf "bin2" } else { Join-Path $baseArchive "bin2" }

if (Test-Path $finalArchiveCheck) {
    $countE = (Get-ChildItem $finalArchiveCheck -Filter *.fits).Count
    if ($countE -gt 0) {
        # On remonte d'un niveau pour supprimer bin1, bin2 et le dossier cible
        Remove-Item -Path $srcFieldDir -Recurse -Force
        Write-Log "NETTOYAGE : Fichiers locaux supprimés. Sauvegarde confirmée sur E: ($countE fichiers)."
    }
} else {
    Write-Log "ATTENTION : Nettoyage annulé, dossier introuvable sur E: ($finalArchiveCheck)."
}