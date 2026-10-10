$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m pip install --upgrade pip pyinstaller pygame==2.6.1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "TheLastSignal" --add-data "assets;assets" --collect-all pygame main.py
Write-Host "Build complete: dist\TheLastSignal.exe"
