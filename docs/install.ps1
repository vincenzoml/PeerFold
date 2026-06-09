# PeerFold installer for Windows. Fetches the latest GitHub release.
$ErrorActionPreference = "Stop"

$BaseUrl = "https://github.com/vincenzoml/PeerFold/releases/latest/download"
$InstallDir = if ($env:PEERFOLD_INSTALL_DIR) {
    $env:PEERFOLD_INSTALL_DIR
} else {
    Join-Path $env:LOCALAPPDATA "Programs\PeerFold"
}
$ExePath = Join-Path $InstallDir "peerfold.exe"

Write-Host "Downloading PeerFold for Windows..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Invoke-WebRequest -Uri "$BaseUrl/peerfold-win.exe" -OutFile $ExePath -UseBasicParsing

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    $updated = if ($userPath) { "$userPath;$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $updated, "User")
    $env:Path = "$env:Path;$InstallDir"
}

Write-Host "Installed peerfold to $ExePath"
Write-Host "Open a new terminal, then run: peerfold manuscript.pdf --reviewer RB"
