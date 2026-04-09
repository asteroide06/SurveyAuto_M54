param([string]$Target)

# On simule un travail de 5 secondes (binning, copie, etc.)
Start-Sleep -Seconds 5

# On joue un son système pour l'alerte sonore
[System.Media.SystemSounds]::Asterisk.Play()

# On affiche une bulle de notification Windows
[void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
$notification = New-Object System.Windows.Forms.NotifyIcon
$notification.Icon = [System.Drawing.SystemIcons]::Information
$notification.BalloonTipTitle = "Test NINA Réussi"
$notification.BalloonTipText = "Le script pour la cible $Target s'est exécuté en arrière-plan."
$notification.Visible = $true
$notification.ShowBalloonTip(5000)

# On laisse 2 secondes pour que la bulle s'affiche avant de fermer le processus
Start-Sleep -Seconds 2