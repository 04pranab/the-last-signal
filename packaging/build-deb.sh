#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/game/config.py" | head -n1)"
ARCH="$(dpkg --print-architecture)"
PKG="$ROOT/build/deb/the-last-signal"
OUT="$ROOT/dist"
rm -rf "$ROOT/build/deb" "$OUT"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/the-last-signal" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" "$OUT"
cp -a "$ROOT/game" "$ROOT/assets" "$ROOT/main.py" "$PKG/opt/the-last-signal/"
chmod 755 "$PKG/DEBIAN"
chmod g-s "$PKG/DEBIAN"
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: the-last-signal
Version: ${VERSION:-1.0.0}
Section: games
Priority: optional
Architecture: ${ARCH}
Maintainer: THE LAST SIGNAL contributors
Depends: python3 (>= 3.9), python3-pygame
Description: THE LAST SIGNAL top-down survival game
 Explore an abandoned research station, collect signal fragments and survive the Echo.
CONTROL
cat > "$PKG/usr/bin/the-last-signal" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 /opt/the-last-signal/main.py "$@"
LAUNCHER
chmod 755 "$PKG/usr/bin/the-last-signal"
install -m 644 "$ROOT/packaging/the-last-signal.desktop" "$PKG/usr/share/applications/the-last-signal.desktop"
install -m 644 "$ROOT/packaging/the-last-signal.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/the-last-signal.svg"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/the-last-signal_${VERSION:-1.0.0}_${ARCH}.deb"
echo "Built: $OUT/the-last-signal_${VERSION:-1.0.0}_${ARCH}.deb"
