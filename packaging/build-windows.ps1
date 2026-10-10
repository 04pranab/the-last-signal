$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
py -m pip install --upgrade pip pyinstaller pygame
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "TheLastSignal" --add-data "assets;assets" --collect-all pygame main.py
Write-Host "Build complete: dist\TheLastSignal.exe"
