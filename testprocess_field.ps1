param(
    [int]$Year, [int]$Month, [int]$Day,
    [int]$Hour, [int]$Minute, [int]$Second,
    [string]$ImageType, [string]$TargetName
)

# ----------------------------
# 1. Configuration & Initialisation
# ----------------------------
$PythonExe  = "C:\Users\aster\AppData\Local\Programs\Python\Python312\python.exe"
$DesignPy   = "C:\NightImages\Scripts\neocp_designation.py"
$logFile    = "C:\Users\aster\Documents\astro\NINA\NINA_copy_log.txt"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp : $Message" | Add-Content -Path $logFile
}

Write-Log "--- Début Session : $TargetName ($ImageType) ---"

# Gestion de l'année (ex: 26 -> 2026)
$fullYear = if ($Year -lt 100) { 2000 + $Year } else { $Year }
$dateObj = Get-Date -Year $fullYear -Month $Month -Day $Day -Hour $Hour -Minute $Minute -Second $Second
$nightDate = $dateObj.ToUniversalTime().AddHours(-12).ToString("yyyy-MM-dd")

# ----------------------------
# 2. Logique CONFIRM vs SURVEY
# ----------------------------
$fieldCode = ""
$sourceType = $ImageType

if ($ImageType -eq "CONFIRM") {
    # On utilise le TargetName (ex: Conf_1) comme code et on force la source sur LIGHT
    $fieldCode = $TargetName
    $sourceType = "LIGHT"
    Write-Log "MODE CONFIRM : Source forcée sur LIGHT. Code utilisé : $fieldCode"
}
else {
    # Mode SURVEY : Appel Python pour nouveau code (ex: FCZAAD)
    $fieldCodeRaw = & $PythonExe $DesignPy --next-field $fullYear $Month $Day 2>&1 | Out-String
    $fieldCode = $fieldCodeRaw.Trim()
    if ($fieldCode -notmatch "^[A-Z0-9]{6}$") {
        Write-Log "ERREUR : code champ invalide retourné par Python : '$fieldCode'"
        exit
    }
    Write-Log "MODE SURVEY : Nouveau code champ généré : $fieldCode"
}

# Dossier source réel sur C:
$srcFieldDir = "C:\NightImages\$nightDate\$sourceType\$TargetName"

# ----------------------------
# 3. Extraction RA/DEC du Header FITS
# ----------------------------
$fieldTag = "UnknownCoords"
$fitsFiles = Get-ChildItem -Path $srcFieldDir -Filter "*.fits" -Recurse

if ($fitsFiles.Count -gt 0) {
    try {
        $firstFits = $fitsFiles[0].FullName
        # Lecture binaire du début du fichier pour le header
        $bytes = [System.IO.File]::ReadAllBytes($firstFits)
        $headerString = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 28800)

        $TargetRA = 0; $TargetDec = 0
        if ($headerString -match "RA\s*=\s*([0-9\.\-]+)") { $TargetRA = [double]$matches[1] }
        if ($headerString -match "DEC\s*=\s*([0-9\.\-]+)") { $TargetDec = [double]$matches[1] }

        # Conversion RA -> HMS
        $raHoursTotal = $TargetRA / 15.0
        $raH = [math]::Floor($raHoursTotal)
        $raM = [math]::Floor(($raHoursTotal - $raH) * 60)
        $raS = [math]::Round((($raHoursTotal - $raH) * 60 - $raM) * 60)
        $raString = "$($raH.ToString('00'))h$($raM.ToString('00'))m$($raS.ToString('00'))s"

        # Conversion DEC -> DMS
        $decSign = if ($TargetDec -lt 0) { "-" } else { "+" }
        $decAbs = [math]::Abs($TargetDec)
        $decD = [math]::Floor($decAbs)
        $decM = [math]::Floor(($decAbs - $decD) * 60)
        $decS = [math]::Round(($decAbs - $decD) * 60 - $decM) * 60
        $decString = "$decSign$($decD.ToString('00'))d$($decM.ToString('00'))m$($decS.ToString('00'))s"

        $fieldTag = "${raString}_${decString}"
        Write-Log "Coordonnées identifiées : $fieldTag"
    }
    catch {
        Write-Log "Avertissement : Impossible de lire le header FITS."
    }
} else {
    Write-Log "ERREUR : Aucun fichier FITS trouvé dans $srcFieldDir"
    exit
}

# ----------------------------
# 4. Double Transfert : D: (Archive) et H: (Réseau)
# ----------------------------
$baseD = "D:\NightImages\$nightDate\$ImageType\$fieldCode"
$baseH = "H:\NightImages\$nightDate\$ImageType\$fieldCode"

Write-Log "Début du transfert et renommage vers D: et H:..."

foreach ($file in $fitsFiles) {
    # Extraction du numéro final (ex: 0000) juste avant l'extension
    if ($file.BaseName -match "(\d+)$") { 
        $num = $matches[1] 
    } else { 
        $num = "0000" 
    }
    
    # Nouveau nom : CODE_COORD_NUM.fits
    $newName = "${fieldCode}_${fieldTag}_${num}.fits"
    
    # Gestion bin1 / bin2
    $subDir = if ($file.DirectoryName -match "bin2") { "bin2" } else { "bin1" }
    
    $destPathD = Join-Path $baseD $subDir
    $destPathH = Join-Path $baseH $subDir

    if (-not (Test-Path $destPathD)) { New-Item -ItemType Directory -Path $destPathD -Force | Out-Null }
    if (-not (Test-Path $destPathH)) { New-Item -ItemType Directory -Path $destPathH -Force | Out-Null }

    # Copie physique
    Copy-Item -Path $file.FullName -Destination (Join-Path $destPathD $newName) -Force
    Copy-Item -Path $file.FullName -Destination (Join-Path $destPathH $newName) -Force
}

# ----------------------------
# 5. Nettoyage et Synchronisation
# ----------------------------
if ((Get-ChildItem $baseD -Recurse -File).Count -ge $fitsFiles.Count) {
    Remove-Item -Path $srcFieldDir -Recurse -Force
    Write-Log "Transfert réussi. Source C: supprimée."
}

$syncDir = "C:\NightImages\Sync"
if (-not (Test-Path $syncDir)) { New-Item -ItemType Directory -Path $syncDir -Force | Out-Null }

Join-Path $baseH "bin1" | Out-File -Encoding ascii -FilePath (Join-Path $syncDir "bin1_$fieldCode.txt") -Force
Join-Path $baseH "bin2" | Out-File -Encoding ascii -FilePath (Join-Path $syncDir "bin2_$fieldCode.txt") -Force

Write-Log "--- Session terminée avec succès ---"
[System.Media.SystemSounds]::Beep.Play()