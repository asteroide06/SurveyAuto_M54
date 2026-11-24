$timeout = 30
while (-not (Test-Connection -ComputerName 192.168.0.10 -Count 1 -Quiet) -and $timeout -gt 0) {
    Start-Sleep -Seconds 2
    $timeout -= 2
}
if (-not (Test-Path "H:/")) {
    net use H: \\192.168.0.10\NightImages /persistent:yes
}
if (-not (Test-Path "Z:/")) {
    net use Z: \\192.168.0.150\Pictures /persistent:yes
}