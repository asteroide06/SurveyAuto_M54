# On définit les paramètres dans l'ordre exact de ta ligne NINA
param(
    [string]$Annee,
    [string]$Mois,
    [string]$Jour,
    [string]$Heure,
    [string]$Minute,
    [string]$Seconde,
    [string]$TypeImage,
    [string]$NomCible
)

# Préparation du message pour la notification
$horodatage = "$Jour/$Mois/$Annee à $Heure:$Minute:$Seconde"
$details = "Type: $TypeImage | Cible: $NomCible"

# Chargement de l'interface Windows pour la bulle de notification
[void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
$notification = New-Object System.Windows.Forms.NotifyIcon
$notification.Icon = [System.Drawing.SystemIcons]::Shield # Icône bouclier pour changer
$notification.Visible = $true
$notification.BalloonTipTitle = "Validation Séquenceur NINA"
$notification.BalloonTipText = "Reçu : $horodatage`n$details"
$notification.ShowBalloonTip(10000) # Affiche pendant 10 secondes

# Petit bip de confirmation
[System.Media.SystemSounds]::Question.Play()

# Pause de 2 secondes pour laisser le temps au processus de respirer
Start-Sleep -Seconds 2