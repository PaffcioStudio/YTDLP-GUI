#!/bin/bash

echo "Budowanie pakietu .deb dla YTDLP-GUI"
echo "===================================="

# Kolory dla output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Sprawdzenie czy jesteśmy w odpowiednim katalogu
if [ ! -f "yt.py" ]; then
    echo -e "${RED}Błąd: Nie znaleziono pliku yt.py. Uruchom skrypt z katalogu projektu.${NC}"
    exit 1
fi

# Sprawdzenie wymaganych narzędzi
echo "Sprawdzanie wymaganych narzędzi..."

# Sprawdzenie dpkg-deb
if ! command -v dpkg-deb &> /dev/null; then
    echo -e "${RED}Błąd: dpkg-deb nie jest zainstalowany${NC}"
    echo "Zainstaluj: sudo apt install dpkg-dev"
    exit 1
fi

# Sprawdzenie Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Błąd: Python3 nie jest zainstalowany${NC}"
    exit 1
fi

# Informacje o pakiecie
PACKAGE_NAME="ytdlp-gui"
VERSION="1.0.0"
ARCHITECTURE="amd64"
MAINTAINER="PaffcioStudio <paffcio@example.com>"
DESCRIPTION="Graficzny interfejs użytkownika dla yt-dlp"

# Sprawdzenie python3-venv i zależności Qt
if ! python3 -c "import venv" 2>/dev/null; then
    echo -e "${YELLOW}python3-venv nie znaleziony.${NC}"
    echo -e "${RED}Zainstaluj wymagane pakiety:${NC}"
    echo -e "${YELLOW}sudo apt install python3-venv python3-full python3-pip libxcb-cursor0 libxcb-cursor-dev qt6-base-dev dpkg-dev${NC}"
    exit 1
else
    echo -e "${GREEN}Środowisko Python gotowe do użycia${NC}"
    # Sprawdzenie czy dpkg-dev jest zainstalowany
    if ! command -v dpkg-deb &> /dev/null; then
        echo -e "${RED}Błąd: dpkg-deb nie jest zainstalowany${NC}"
        echo "Zainstaluj: sudo apt install dpkg-dev"
        exit 1
    fi
fi

# Tworzenie środowiska wirtualnego
VENV_DIR="venv_build"
if [ ! -d "$VENV_DIR" ]; then
    echo "Tworzenie środowiska wirtualnego..."
    python3 -m venv "$VENV_DIR"
fi

# Aktywacja środowiska wirtualnego
echo "Aktywacja środowiska wirtualnego..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo -e "${RED}Błąd: Nie udało się utworzyć środowiska wirtualnego${NC}"
    exit 1
fi

source "$VENV_DIR/bin/activate"

# Aktualizacja pip w środowisku wirtualnym
echo "Aktualizacja pip..."
pip install --upgrade pip

# Instalacja wymaganych bibliotek w środowisku wirtualnym
echo "Instalowanie wymaganych bibliotek..."
pip install PyQt6 requests pyinstaller

# Czyszczenie starych buildów
echo "Czyszczenie starych plików..."
rm -rf build dist YTDLP-GUI.spec deb_build *.deb

# Pakowanie aplikacji za pomocą PyInstaller
echo "Pakowanie aplikacji..."
pyinstaller --onefile \
    --windowed \
    --name=YTDLP-GUI \
    --icon="icon.ico" \
    --add-data "icons:icons" \
    --hidden-import=PyQt6.QtCore \
    --hidden-import=PyQt6.QtGui \
    --hidden-import=PyQt6.QtWidgets \
    --collect-submodules=PyQt6 \
    yt.py

if [ $? -ne 0 ]; then
    echo -e "${RED}Błąd podczas pakowania z PyInstaller!${NC}"
    if command -v deactivate &> /dev/null; then
        deactivate
    fi
    exit 1
fi

# Tworzenie struktury pakietu .deb
echo "Tworzenie struktury pakietu .deb..."
DEB_DIR="deb_build/${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}"

mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/bin"
mkdir -p "$DEB_DIR/usr/share/applications"
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}"
mkdir -p "$DEB_DIR/usr/share/pixmaps"

# Tworzenie pliku control
echo "Tworzenie pliku control..."
cat > "$DEB_DIR/DEBIAN/control" << EOF
Package: $PACKAGE_NAME
Version: $VERSION
Section: multimedia
Priority: optional
Architecture: $ARCHITECTURE
Depends: python3, python3-pyqt6, libxcb-cursor0, qt6-base-dev
Maintainer: $MAINTAINER
Description: $DESCRIPTION
 YTDLP-GUI to nowoczesny graficzny interfejs użytkownika dla yt-dlp,
 umożliwiający pobieranie filmów i muzyki z YouTube, CDA.pl i setek innych platform.
 Obsługuje pobieranie w różnych formatach i jakościach, ekstraktowanie audio,
 pobieranie playlist oraz wiele innych zaawansowanych opcji.
 .
 Funkcje:
 - Pobieranie wideo z YouTube, CDA.pl i 1000+ platform
 - Ekstraktowanie audio do MP3, AAC, FLAC, OGG
 - Obsługa playlist i pobieranie wsadowe
 - Wsparcie dla CDA Premium
 - System kolejki pobierania
 - Ciemny i jasny motyw interfejsu
Homepage: https://github.com/PaffcioStudio/YTDLP-GUI
EOF

# Tworzenie skryptu postinst
echo "Tworzenie skryptu postinst..."
cat > "$DEB_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

# Aktualizacja cache ikon
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -qt /usr/share/icons/hicolor/ || true
fi

# Aktualizacja cache aplikacji desktop
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

echo "YTDLP-GUI zainstalowany pomyślnie!"
echo "Możesz uruchomić aplikację z menu aplikacji lub wpisując: ytdlp-gui"

exit 0
EOF

chmod +x "$DEB_DIR/DEBIAN/postinst"

# Tworzenie skryptu prerm
echo "Tworzenie skryptu prerm..."
cat > "$DEB_DIR/DEBIAN/prerm" << 'EOF'
#!/bin/bash
set -e

echo "Usuwanie YTDLP-GUI..."

exit 0
EOF

chmod +x "$DEB_DIR/DEBIAN/prerm"

# Kopiowanie plików aplikacji
echo "Kopiowanie plików aplikacji..."
cp dist/YTDLP-GUI "$DEB_DIR/usr/bin/ytdlp-gui"
chmod +x "$DEB_DIR/usr/bin/ytdlp-gui"

# Tworzenie pliku .desktop
echo "Tworzenie pliku .desktop..."
cat > "$DEB_DIR/usr/share/applications/ytdlp-gui.desktop" << EOF
[Desktop Entry]
Type=Application
Name=YTDLP-GUI
Name[pl]=YTDLP-GUI
Comment=GUI dla yt-dlp - pobieranie filmów z YouTube i innych platform
Comment[pl]=Graficzny interfejs użytkownika dla yt-dlp
Comment[en]=GUI for yt-dlp - download videos from YouTube and other platforms
Exec=ytdlp-gui
Icon=ytdlp-gui
Categories=AudioVideo;Video;Network;Qt;
Terminal=false
StartupNotify=true
Keywords=youtube;video;download;ytdlp;cda;
MimeType=text/uri-list;x-scheme-handler/http;x-scheme-handler/https;
EOF

# Konwertowanie ikony ico na png (jeśli możliwe)
if command -v convert &> /dev/null; then
    echo "Konwertowanie ikony..."
    convert icon.ico -resize 256x256 "$DEB_DIR/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png"
    convert icon.ico -resize 48x48 "$DEB_DIR/usr/share/pixmaps/ytdlp-gui.png"
else
    echo -e "${YELLOW}ImageMagick nie znaleziony. Kopiuję ikonę ico...${NC}"
    cp icon.ico "$DEB_DIR/usr/share/pixmaps/ytdlp-gui.png"
    cp icon.ico "$DEB_DIR/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png"
fi

# Tworzenie dokumentacji
echo "Tworzenie dokumentacji..."
cp README.md "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}/"
cp LICENSE.md "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}/" 2>/dev/null || echo "Brak pliku LICENSE.md"

# Tworzenie pliku copyright
cat > "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}/copyright" << EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: YTDLP-GUI
Upstream-Contact: PaffcioStudio <paffcio@example.com>
Source: https://github.com/PaffcioStudio/YTDLP-GUI

Files: *
Copyright: 2025 PaffcioStudio
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
EOF

# Kompresja dokumentacji
gzip -9 "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}/README.md" 2>/dev/null || true

# Tworzenie changelog
cat > "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}/changelog.Debian" << EOF
$PACKAGE_NAME ($VERSION) unstable; urgency=low

  * Initial release
  * GUI dla yt-dlp z obsługą YouTube, CDA.pl i innych platform
  * Obsługa pobierania wideo i audio w różnych formatach
  * System kolejki i pobieranie wsadowe
  * Wsparcie dla CDA Premium
  * Ciemny i jasny motyw interfejsu

 -- $MAINTAINER  $(date -R)
EOF

gzip -9 "$DEB_DIR/usr/share/doc/${PACKAGE_NAME}/changelog.Debian"

# Ustawianie uprawnień
echo "Ustawianie uprawnień..."
find "$DEB_DIR" -type f -exec chmod 644 {} \;
find "$DEB_DIR" -type d -exec chmod 755 {} \;
chmod 755 "$DEB_DIR/usr/bin/ytdlp-gui"
chmod 755 "$DEB_DIR/DEBIAN/postinst"
chmod 755 "$DEB_DIR/DEBIAN/prerm"

# Budowanie pakietu .deb
echo "Budowanie pakietu .deb..."
DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}.deb"

dpkg-deb --build "$DEB_DIR" "$DEB_FILE"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}Sukces! Pakiet .deb został utworzony pomyślnie!${NC}"
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}Plik pakietu: $DEB_FILE${NC}"
    echo -e "${GREEN}Aby zainstalować pakiet, użyj:${NC}"
    echo -e "${BLUE}sudo dpkg -i $DEB_FILE${NC}"
    echo -e "${BLUE}sudo apt-get install -f  # jeśli są problemy z zależnościami${NC}"
    echo ""
    echo -e "${GREEN}Informacje o pakiecie:${NC}"
    dpkg --info "$DEB_FILE"
    
    # Opcjonalnie - przeniesienie do katalogu domowego użytkownika
    read -p "Czy chcesz przenieść pakiet .deb do katalogu domowego? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mv "$DEB_FILE" "$HOME/"
        echo -e "${GREEN}Pakiet .deb przeniesiony do: $HOME/$DEB_FILE${NC}"
    fi
else
    echo -e "${RED}Błąd podczas tworzenia pakietu .deb!${NC}"
    if command -v deactivate &> /dev/null; then
        deactivate
    fi
    exit 1
fi

# Deaktywacja środowiska wirtualnego
if command -v deactivate &> /dev/null; then
    deactivate
fi

echo -e "${GREEN}Build pakietu .deb zakończony pomyślnie!${NC}"
echo ""
echo -e "${YELLOW}Dodatkowe informacje:${NC}"
echo "- Pakiet można odinstalować: sudo apt remove $PACKAGE_NAME"
echo "- Aplikacja będzie dostępna w menu jako 'YTDLP-GUI'"
echo "- Można uruchomić z terminala: ytdlp-gui"
