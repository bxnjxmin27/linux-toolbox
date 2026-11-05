#!/usr/bin/env bash
# Installiert Toolbox für den aktuellen Benutzer (keine Root-Rechte nötig).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
APP_DIR="$(pwd)"

echo "▸ Python-Umgebung anlegen …"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q --no-deps rapidocr-onnxruntime

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
cat > "$HOME/.local/bin/toolbox" <<LAUNCH
#!/usr/bin/env bash
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/main.py" "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/toolbox"
cp assets/toolbox.svg "$HOME/.local/share/icons/hicolor/scalable/apps/linux-toolbox.svg"
sed "s|@EXEC@|$HOME/.local/bin/toolbox|" packaging/linux-toolbox.desktop > "$HOME/.local/share/applications/linux-toolbox.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "✓ Fertig. Starte Toolbox über das Anwendungsmenü oder mit:  toolbox"
echo
echo "Empfohlene System-Pakete (für alle Werkzeuge):"
echo "  sudo dnf install qpdf tesseract ddcutil zbar wl-clipboard poppler-utils libheif-tools libreoffice"
echo "  (FFmpeg mit allen Codecs: RPM Fusion → sudo dnf swap ffmpeg-free ffmpeg --allowerasing)"
