# Desktop builds

THE LAST SIGNAL is a Python/Pygame game. These scripts create a Linux `.deb` and a Windows `.exe`.

## Ubuntu: build the `.deb`

From the extracted project directory:

```bash
sudo apt update
sudo apt install -y dpkg-dev python3-pygame
chmod +x packaging/build-deb.sh
./packaging/build-deb.sh
```

The package is written to `dist/`. Install it with `sudo apt install ./dist/the-last-signal_*.deb`. After installation, launch **THE LAST SIGNAL** from the applications menu, or run `the-last-signal`. The package uses Ubuntu's system Python and Pygame, rather than bundling a Python runtime.

## Windows: build the `.exe`

A Windows executable must be built on Windows (PyInstaller does not reliably cross-compile Windows executables from Linux). Install Python 3.10+ from python.org and select **Add Python to PATH**. Open PowerShell in the extracted project folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\build-windows.ps1
```

The single-file GUI executable is `dist\TheLastSignal.exe`. Double-click it to launch. It bundles Pygame and the game's `assets` directory. Windows may show a SmartScreen warning for an unsigned, self-built executable; only run builds you trust.

## Notes

- Build each platform's native package on that platform. The Linux `.deb` is for Ubuntu/Debian systems; the `.exe` is for Windows.
- A `.deb` file is installed once, then the app appears in the applications menu. An `.exe` is directly double-clickable.
- For LAN multiplayer, allow the game through the OS firewall when prompted. Network discovery uses UDP 47200 and game traffic uses TCP 47201.
