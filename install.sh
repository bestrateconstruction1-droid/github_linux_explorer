#!/usr/bin/env bash
# Installs Linux Explorer for the current user: app menu entry, desktop shortcut, and a terminal command.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/bin" "$HOME/.local/share/icons"
cp "$APP_DIR/icon.svg" "$HOME/.local/share/icons/linux-explorer.svg"

cat > "$HOME/.local/bin/linux-explorer" <<LAUNCH
#!/usr/bin/env bash
exec python3 "$APP_DIR/explorer.py" "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/linux-explorer"

DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Version=1.0
Name=Linux Explorer
GenericName=File and Directory Explorer
Comment=Browse and search files and folders, and see the Linux command behind every click
Exec=$HOME/.local/bin/linux-explorer
Icon=$HOME/.local/share/icons/linux-explorer.svg
Terminal=false
Categories=Utility;FileTools;
Keywords=files;folders;directories;find;search;linux;terminal;learn;
StartupNotify=false"
printf '%s\n' "$DESKTOP_ENTRY" > "$HOME/.local/share/applications/linux-explorer.desktop"
chmod +x "$HOME/.local/share/applications/linux-explorer.desktop"

if [ -d "$HOME/Desktop" ]; then
  printf '%s\n' "$DESKTOP_ENTRY" > "$HOME/Desktop/Linux Explorer.desktop"
  chmod +x "$HOME/Desktop/Linux Explorer.desktop"
  command -v gio >/dev/null && gio set "$HOME/Desktop/Linux Explorer.desktop" metadata::trusted true 2>/dev/null || true
fi
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Installed. Open it from the app menu (search 'Linux Explorer'), the desktop icon, or by typing: linux-explorer"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Note: add \$HOME/.local/bin to your PATH to use the 'linux-explorer' command in new terminals." ;; esac
