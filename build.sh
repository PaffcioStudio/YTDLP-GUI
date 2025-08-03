#!/bin/bash

# Sprawdzenie parametrów
BUILD_TYPE=${1:-appimage}

if [ "$BUILD_TYPE" = "deb" ]; then
    echo "Budowanie pakietu .deb dla YTDLP-GUI"
    echo "===================================="
    exec ./build_deb.sh
elif [ "$BUILD_TYPE" = "appimage" ]; then
    echo "Budowanie YTDLP-GUI AppImage dla Linux"
    echo "======================================"
else
    echo "Użycie: $0 [appimage|deb]"
    echo "  appimage - buduje plik AppImage (domyślnie)"
    echo "  deb      - buduje pakiet .deb"
    exit 1
fi

# Kolory dla output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Sprawdzenie czy jesteśmy w odpowiednim katalogu
if [ ! -f "yt.py" ]; then
    echo -e "${RED}Błąd: Nie znaleziono pliku yt.py. Uruchom skrypt z katalogu projektu.${NC}"
    exit 1
fi

# Sprawdzenie wymaganych narzędzi
echo "Sprawdzanie wymaganych narzędzi..."

# Sprawdzenie Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Błąd: Python3 nie jest zainstalowany${NC}"
    exit 1
fi

# Sprawdzenie python3-venv i zależności Qt
if ! python3 -c "import venv" 2>/dev/null; then
    echo -e "${YELLOW}python3-venv nie znaleziony. Instaluję wymagane pakiety...${NC}"
    sudo apt update
    sudo apt install -y python3-venv python3-full python3-pip libxcb-cursor0 libxcb-cursor-dev
    
    # Sprawdzenie czy instalacja się powiodła
    if ! python3 -c "import venv" 2>/dev/null; then
        echo -e "${RED}Nie udało się zainstalować python3-venv. Spróbuj ręcznie:${NC}"
        echo -e "${YELLOW}sudo apt install python3-venv python3-full${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Instalowanie zależności Qt dla AppImage...${NC}"
    sudo apt update
    sudo apt install -y libxcb-cursor0 libxcb-cursor-dev qt6-base-dev
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

# Pobieranie linuxdeploy i appimagetool jeśli nie istnieją
LINUXDEPLOY_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"

if [ ! -f "linuxdeploy-x86_64.AppImage" ]; then
    echo "Pobieranie linuxdeploy..."
    wget -O linuxdeploy-x86_64.AppImage "$LINUXDEPLOY_URL"
    chmod +x linuxdeploy-x86_64.AppImage
fi

if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Pobieranie appimagetool..."
    wget -O appimagetool-x86_64.AppImage "$APPIMAGETOOL_URL"
    chmod +x appimagetool-x86_64.AppImage
fi

# Czyszczenie starych buildów
echo "Czyszczenie starych plików..."
rm -rf build dist YTDLP-GUI.spec AppDir YTDLP-GUI-*.AppImage

# Tworzenie pliku .desktop
echo "Tworzenie pliku .desktop..."
cat > YTDLP-GUI.desktop << EOF
[Desktop Entry]
Type=Application
Name=YTDLP-GUI
Comment=GUI dla yt-dlp - pobieranie filmów z YouTube i innych platform
Exec=YTDLP-GUI
Icon=ytdlp-gui
Categories=AudioVideo;Video;Network;
Terminal=false
StartupNotify=true
EOF

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

# Tworzenie struktury AppDir
echo "Tworzenie struktury AppDir..."
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps

# Kopiowanie plików
cp dist/YTDLP-GUI AppDir/usr/bin/
cp YTDLP-GUI.desktop AppDir/usr/share/applications/
cp YTDLP-GUI.desktop AppDir/

# Konwertowanie ikony ico na png (jeśli możliwe)
if command -v convert &> /dev/null; then
    echo "Konwertowanie ikony..."
    convert icon.ico AppDir/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png
    cp AppDir/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png AppDir/
else
    echo -e "${YELLOW}ImageMagick nie znaleziony. Kopiuję ikonę ico...${NC}"
    cp icon.ico AppDir/ytdlp-gui.png
fi

# Nadawanie uprawnień wykonywania
chmod +x AppDir/usr/bin/YTDLP-GUI

# Tworzenie AppRun
cat > AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export APPDIR="$HERE"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"

# Qt environment variables for AppImage
export QT_PLUGIN_PATH="$HERE/usr/plugins:$QT_PLUGIN_PATH"
export QT_QPA_PLATFORM_PLUGIN_PATH="$HERE/usr/plugins/platforms"
export QT_QPA_PLATFORM="xcb"

# Try to use system Qt libraries if AppImage Qt fails
if [ -z "$QT_QPA_PLATFORM_PLUGIN_PATH_FALLBACK" ]; then
    export QT_QPA_PLATFORM_PLUGIN_PATH_FALLBACK="/usr/lib/x86_64-linux-gnu/qt6/plugins/platforms:/usr/lib/qt6/plugins/platforms"
fi

exec "$HERE/usr/bin/YTDLP-GUI" "$@"
EOF

chmod +x AppDir/AppRun

# Użycie linuxdeploy do przygotowania AppDir z poprawkami dla Qt
echo "Przygotowywanie AppDir z linuxdeploy..."
./linuxdeploy-x86_64.AppImage --appdir AppDir --executable AppDir/usr/bin/YTDLP-GUI --library /usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0

# Tworzenie AppImage
echo "Tworzenie AppImage..."
./appimagetool-x86_64.AppImage AppDir

if [ $? -eq 0 ]; then
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}Sukces! AppImage został utworzony pomyślnie!${NC}"
    echo -e "${GREEN}===============================================${NC}"
    
    # Znajdowanie utworzonego pliku AppImage
    APPIMAGE_FILE=$(ls YTDLP-GUI-*.AppImage 2>/dev/null | head -n1)
    if [ -n "$APPIMAGE_FILE" ]; then
        echo -e "${GREEN}Plik AppImage: $APPIMAGE_FILE${NC}"
        echo -e "${GREEN}Aby uruchomić aplikację, użyj: ./$APPIMAGE_FILE${NC}"
        
        # Nadanie uprawnień wykonywania
        chmod +x "$APPIMAGE_FILE"
        
        # Opcjonalnie - przeniesienie do katalogu domowego użytkownika
        read -p "Czy chcesz przenieść AppImage do katalogu domowego? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            mv "$APPIMAGE_FILE" "$HOME/"
            echo -e "${GREEN}AppImage przeniesiony do: $HOME/$APPIMAGE_FILE${NC}"
        fi
    fi
else
    echo -e "${RED}Błąd podczas tworzenia AppImage!${NC}"
    if command -v deactivate &> /dev/null; then
        deactivate
    fi
    exit 1
fi

# Deaktywacja środowiska wirtualnego
if command -v deactivate &> /dev/null; then
    deactivate
fi

echo -e "${GREEN}Build zakończony pomyślnie!${NC}"
