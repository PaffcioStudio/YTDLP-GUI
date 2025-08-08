#!/bin/bash

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Funkcja czyszczenia śmieciowych folderów
cleanup_build_dirs() {
    echo -e "${BLUE}🧹 Czyszczenie śmieciowych folderów...${NC}"
    rm -rf venv_build venv_windows_build build deb_build AppDir *.spec
    rm -f linuxdeploy-x86_64.AppImage appimagetool-x86_64.AppImage
    rm -f YTDLP-GUI.desktop Dockerfile.windows
    echo -e "${GREEN}✅ Wyczyszczono${NC}"
}

# Funkcja budowania DEB
build_deb() {
    echo -e "${YELLOW}📦 Budowanie pakietu DEB...${NC}"
    
    # Sprawdzenie wymagań
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python3 nie znaleziony${NC}"
        return 1
    fi
    
    # Instalacja wymaganych pakietów
    echo -e "${BLUE}📋 Instalowanie wymaganych pakietów...${NC}"
    sudo apt update
    sudo apt install -y python3-venv python3-full python3-pip dpkg-dev
    
    # Tworzenie środowiska wirtualnego
    echo -e "${BLUE}🔧 Tworzenie środowiska wirtualnego...${NC}"
    python3 -m venv venv_build
    source venv_build/bin/activate
    
    pip install --upgrade pip
    pip install PyQt6 requests pyinstaller
    
    # Budowanie binarki
    echo -e "${BLUE}⚙️ Kompilowanie aplikacji...${NC}"
    pyinstaller --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons:icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py
    
    # Tworzenie struktury DEB
    echo -e "${BLUE}📁 Tworzenie struktury pakietu DEB...${NC}"
    mkdir -p deb_build/ytdlp-gui_1.0.1_amd64/DEBIAN
    mkdir -p deb_build/ytdlp-gui_1.0.1_amd64/usr/bin
    mkdir -p deb_build/ytdlp-gui_1.0.1_amd64/usr/share/applications
    mkdir -p deb_build/ytdlp-gui_1.0.1_amd64/usr/share/pixmaps
    
    # Kopiowanie plików
    cp dist/YTDLP-GUI deb_build/ytdlp-gui_1.0.1_amd64/usr/bin/ytdlp-gui
    chmod +x deb_build/ytdlp-gui_1.0.1_amd64/usr/bin/ytdlp-gui
    cp icon.ico deb_build/ytdlp-gui_1.0.1_amd64/usr/share/pixmaps/ytdlp-gui.ico
    
    # Tworzenie pliku control
    cat > deb_build/ytdlp-gui_1.0.1_amd64/DEBIAN/control << EOF
Package: ytdlp-gui
Version: 1.0.1
Section: multimedia
Priority: optional
Architecture: amd64
Maintainer: PaffcioStudio <paffciostudio@gmail.com>
Description: GUI dla yt-dlp - pobieranie filmów z YouTube i innych platform
 YTDLP-GUI to nowoczesny graficzny interfejs użytkownika dla yt-dlp
 umożliwiający łatwe pobieranie filmów z YouTube, CDA.pl i setek innych platform.
EOF
    
    # Tworzenie pliku .desktop
    cat > deb_build/ytdlp-gui_1.0.1_amd64/usr/share/applications/ytdlp-gui.desktop << EOF
[Desktop Entry]
Type=Application
Name=YTDLP-GUI
Comment=GUI dla yt-dlp - pobieranie filmów z YouTube i innych platform
Exec=ytdlp-gui
Icon=ytdlp-gui
Categories=AudioVideo;Video;Network;
Terminal=false
StartupNotify=true
EOF
    
    # Budowanie pakietu DEB
    echo -e "${BLUE}🔨 Budowanie pakietu DEB...${NC}"
    dpkg-deb --build deb_build/ytdlp-gui_1.0.1_amd64
    
    # Przeniesienie do dist
    mkdir -p dist
    mv deb_build/ytdlp-gui_1.0.1_amd64.deb dist/
    
    # Usuwanie zbędnej binarki PyInstaller z dist
    rm -f dist/YTDLP-GUI
    
    deactivate
    echo -e "${GREEN}✅ DEB zbudowany: dist/ytdlp-gui_1.0.1_amd64.deb${NC}"
}

# Funkcja budowania AppImage
build_appimage() {
    echo -e "${YELLOW}🚀 Budowanie AppImage...${NC}"
    
    # Sprawdzenie wymagań
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python3 nie znaleziony${NC}"
        return 1
    fi
    
    # Instalacja wymaganych pakietów
    echo -e "${BLUE}📋 Instalowanie wymaganych pakietów...${NC}"
    sudo apt update
    sudo apt install -y python3-venv python3-full libxcb-cursor0 libxcb-cursor-dev qt6-base-dev wget
    
    # Tworzenie środowiska wirtualnego
    echo -e "${BLUE}🔧 Tworzenie środowiska wirtualnego...${NC}"
    python3 -m venv venv_build
    source venv_build/bin/activate
    
    pip install --upgrade pip
    pip install PyQt6 requests pyinstaller
    
    # Pobieranie narzędzi AppImage
    echo -e "${BLUE}📥 Pobieranie narzędzi AppImage...${NC}"
    if [ ! -f "linuxdeploy-x86_64.AppImage" ]; then
        wget -O linuxdeploy-x86_64.AppImage https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
        chmod +x linuxdeploy-x86_64.AppImage
    fi
    
    if [ ! -f "appimagetool-x86_64.AppImage" ]; then
        wget -O appimagetool-x86_64.AppImage https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
        chmod +x appimagetool-x86_64.AppImage
    fi
    
    # Budowanie binarki
    echo -e "${BLUE}⚙️ Kompilowanie aplikacji...${NC}"
    pyinstaller --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons:icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py
    
    # Tworzenie struktury AppDir
    echo -e "${BLUE}📁 Tworzenie struktury AppImage...${NC}"
    mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps
    
    cp dist/YTDLP-GUI AppDir/usr/bin/
    chmod +x AppDir/usr/bin/YTDLP-GUI
    
    # Tworzenie pliku .desktop
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
    
    cp YTDLP-GUI.desktop AppDir/usr/share/applications/
    cp YTDLP-GUI.desktop AppDir/
    
    # Ikona
    if command -v convert &> /dev/null; then
        convert icon.ico AppDir/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png
        cp AppDir/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png AppDir/
    else
        cp icon.ico AppDir/ytdlp-gui.png
    fi
    
    # AppRun
    cat > AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export APPDIR="$HERE"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"
export QT_PLUGIN_PATH="$HERE/usr/plugins:$QT_PLUGIN_PATH"
export QT_QPA_PLATFORM_PLUGIN_PATH="$HERE/usr/plugins/platforms"
export QT_QPA_PLATFORM="xcb"
exec "$HERE/usr/bin/YTDLP-GUI" "$@"
EOF
    
    chmod +x AppDir/AppRun
    
    # Budowanie AppImage
    echo -e "${BLUE}🔨 Budowanie AppImage...${NC}"
    ./linuxdeploy-x86_64.AppImage --appdir AppDir --executable AppDir/usr/bin/YTDLP-GUI
    ./appimagetool-x86_64.AppImage AppDir YTDLP-GUI-x86_64.AppImage
    
    # Przeniesienie do dist
    mkdir -p dist
    mv YTDLP-GUI-x86_64.AppImage dist/
    
    # Usuwanie zbędnej binarki PyInstaller z dist
    rm -f dist/YTDLP-GUI
    
    deactivate
    echo -e "${GREEN}✅ AppImage zbudowany: dist/YTDLP-GUI-x86_64.AppImage${NC}"
}

# Funkcja budowania Windows na Linux (eksperymentalne)
build_windows_on_linux() {
    echo -e "${YELLOW}🪟 Budowanie Windows EXE/Portable na Linux...${NC}"
    echo -e "${RED}⚠️ UWAGA: To jest funkcja eksperymentalna!${NC}"
    echo -e "${BLUE}💡 Opcje budowania Windows na Linux:${NC}"
    echo "1. Wine + PyInstaller (lokalne)"
    echo "2. Docker + Wine (izolowane)"
    echo "3. Anuluj"
    echo ""
    echo -n -e "${BLUE}Wybierz metodę (1-3): ${NC}"
    read method_choice
    
    case $method_choice in
        1)
            build_with_wine
            ;;
        2)
            build_with_docker_wine
            ;;
        3)
            echo -e "${YELLOW}❌ Anulowano budowanie Windows${NC}"
            return
            ;;
        *)
            echo -e "${RED}❌ Nieprawidłowy wybór!${NC}"
            return
            ;;
    esac
}

# Funkcja budowania z Wine (lokalne)
build_with_wine() {
    echo -e "${YELLOW}🍷 Budowanie z Wine...${NC}"
    
    # Sprawdzenie Wine
    if ! command -v wine &> /dev/null; then
        echo -e "${RED}❌ Wine nie jest zainstalowany!${NC}"
        echo -e "${YELLOW}⚠️ Wine jest wymagany do budowania Windows EXE na Linux${NC}"
        echo -e "${BLUE}Czy chcesz automatycznie zainstalować Wine?${NC}"
        echo -n -e "${BLUE}t = tak, n = nie (przerwij): ${NC}"
        read -r wine_install
        
        if [[ $wine_install == "t" || $wine_install == "T" ]]; then
            echo -e "${BLUE}📥 Instalowanie Wine...${NC}"
            sudo apt update && sudo apt install -y wine
            if [ $? -ne 0 ]; then
                echo -e "${RED}❌ Nie udało się zainstalować Wine!${NC}"
                return 1
            fi
            echo -e "${GREEN}✅ Wine zainstalowany${NC}"
        else
            echo -e "${YELLOW}⏹️ Anulowano budowanie Windows EXE${NC}"
            return 1
        fi
    fi
    
    echo -e "${GREEN}✅ Wine znaleziony: $(wine --version)${NC}"
    
    # Sprawdzenie Python w Wine
    echo -e "${BLUE}🔍 Sprawdzanie Python w Wine...${NC}"
    if ! wine python --version &> /dev/null; then
        echo -e "${YELLOW}⚠️ Python nie jest zainstalowany w Wine${NC}"
        echo -e "${BLUE}� Automatyczna instalacja Python 3.12...${NC}"
        
        # Pobieranie Python
        if [ ! -f "python-installer.exe" ]; then
            echo -e "${BLUE}⬇️ Pobieranie instalatora Python...${NC}"
            wget -O python-installer.exe https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe
            if [ $? -ne 0 ]; then
                echo -e "${RED}❌ Błąd podczas pobierania Python!${NC}"
                return 1
            fi
        fi
        
        # Instalacja Python w Wine
        echo -e "${BLUE}⚙️ Instalowanie Python w Wine...${NC}"
        wine python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
        
        # Sprawdzenie czy instalacja się powiodła
        sleep 2
        if ! wine python --version &> /dev/null; then
            echo -e "${RED}❌ Nie udało się zainstalować Python w Wine!${NC}"
            return 1
        fi
        
        # Czyszczenie instalatora
        rm -f python-installer.exe
        echo -e "${GREEN}✅ Python zainstalowany w Wine${NC}"
    else
        echo -e "${GREEN}✅ Python znaleziony w Wine: $(wine python --version 2>/dev/null)${NC}"
    fi
    
    echo -e "${BLUE}🔧 Tworzenie środowiska wirtualnego Wine...${NC}"
    
    # Tworzenie środowiska wirtualnego w Wine
    wine python -m venv venv_wine_build
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Nie udało się utworzyć środowiska wirtualnego w Wine!${NC}"
        return 1
    fi
    
    # Instalacja pakietów
    echo -e "${BLUE}📦 Instalowanie pakietów w Wine...${NC}"
    wine venv_wine_build/Scripts/python.exe -m pip install --upgrade pip
    wine venv_wine_build/Scripts/pip.exe install PyQt6 requests pyinstaller
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Błąd podczas instalacji pakietów w Wine!${NC}"
        rm -rf venv_wine_build
        return 1
    fi
    
    # Budowanie tylko EXE (bez Portable - niepotrzebny syf)
    echo -e "${BLUE}⚙️ Kompilowanie Windows EXE...${NC}"
    wine venv_wine_build/Scripts/pyinstaller.exe --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons;icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py
    
    if [ $? -eq 0 ]; then
        mkdir -p dist
        if [ -f dist/YTDLP-GUI.exe ]; then
            mv dist/YTDLP-GUI.exe dist/YTDLP-GUI-windows.exe 2>/dev/null
            echo -e "${GREEN}✅ Windows EXE zbudowany: dist/YTDLP-GUI-windows.exe${NC}"
            
            # Wyświetlenie informacji o pliku
            EXE_SIZE=$(du -h dist/YTDLP-GUI-windows.exe | cut -f1)
            echo -e "${CYAN}� Rozmiar pliku: ${EXE_SIZE}${NC}"
        else
            echo -e "${RED}❌ Nie znaleziono zbudowanego pliku EXE!${NC}"
        fi
    else
        echo -e "${RED}❌ Błąd podczas budowania z Wine!${NC}"
    fi
    
    # Pytanie o czyszczenie plików tymczasowych
    echo ""
    echo -e "${YELLOW}🧹 Czy usunąć pliki tymczasowe Wine? (venv_wine_build, build/, *.spec)${NC}"
    echo -e "${BLUE}t = tak (zalecane), n = nie (zachowaj dla następnego buildu)${NC}"
    echo -n -e "${BLUE}Twój wybór (t/n): ${NC}"
    read -r cleanup_choice
    
    if [[ $cleanup_choice == "t" || $cleanup_choice == "T" || $cleanup_choice == "" ]]; then
        echo -e "${BLUE}🗑️ Usuwanie plików tymczasowych...${NC}"
        rm -rf venv_wine_build build *.spec
        echo -e "${GREEN}✅ Wyczyszczono${NC}"
    else
        echo -e "${YELLOW}💾 Pliki tymczasowe zachowane (następny build będzie szybszy)${NC}"
    fi
}

# Funkcja budowania z Docker + Wine
build_with_docker_wine() {
    echo -e "${YELLOW}🐳 Budowanie z Docker + Wine...${NC}"
    
    # Sprawdzenie Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker nie jest zainstalowany!${NC}"
        echo -e "${BLUE}💡 Aby zainstalować Docker:${NC}"
        echo "sudo apt update"
        echo "sudo apt install docker.io"
        echo "sudo usermod -aG docker \$USER"
        echo "# Wyloguj się i zaloguj ponownie"
        return 1
    fi
    
    # Tworzenie Dockerfile dla Windows build
    echo -e "${BLUE}📝 Tworzenie Dockerfile...${NC}"
    cat > Dockerfile.windows << 'EOF'
FROM ubuntu:22.04

# Instalacja Wine i zależności
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    wine64 \
    wget \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Konfiguracja Wine
ENV WINEPREFIX=/root/.wine
ENV DISPLAY=:99

# Pobieranie i instalacja Python w Wine
RUN Xvfb :99 -screen 0 1024x768x24 & \
    sleep 5 && \
    wget -O python.exe https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe && \
    wine python.exe /quiet InstallAllUsers=1 PrependPath=1 && \
    rm python.exe

WORKDIR /app
COPY . .

# Skrypt budowania
RUN echo '#!/bin/bash\n\
set -e\n\
Xvfb :99 -screen 0 1024x768x24 &\n\
sleep 5\n\
wine python -m venv venv_build\n\
wine venv_build/Scripts/python.exe -m pip install --upgrade pip\n\
wine venv_build/Scripts/pip.exe install PyQt6 requests pyinstaller\n\
wine venv_build/Scripts/pyinstaller.exe --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons;icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py\n\
wine venv_build/Scripts/pyinstaller.exe --onedir --windowed --name=YTDLP-GUI-Portable --icon="icon.ico" --add-data "icons;icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py\n\
' > build_windows.sh && chmod +x build_windows.sh

CMD ["./build_windows.sh"]
EOF

    # Budowanie Docker image
    echo -e "${BLUE}🔨 Budowanie Docker image...${NC}"
    docker build -f Dockerfile.windows -t ytdlp-gui-wine .
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Błąd podczas budowania Docker image!${NC}"
        return 1
    fi
    
    # Uruchomienie kontenera
    echo -e "${BLUE}🚀 Uruchamianie budowania w kontenerze...${NC}"
    docker run --rm -v "$(pwd)/dist:/app/dist" ytdlp-gui-wine
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Windows buildy gotowe w dist/${NC}"
        # Przeniesienie plików
        [ -f dist/YTDLP-GUI.exe ] && mv dist/YTDLP-GUI.exe dist/YTDLP-GUI-windows.exe
        [ -d dist/YTDLP-GUI-Portable ] && mv dist/YTDLP-GUI-Portable dist/YTDLP-GUI-Portable-Windows
    else
        echo -e "${RED}❌ Błąd podczas budowania w kontenerze!${NC}"
    fi
    
    # Czyszczenie
    rm -f Dockerfile.windows
}

clear
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         YTDLP-GUI Builder            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Wybierz co chcesz zbudować:${NC}"
echo ""
echo -e "${GREEN}1.${NC} 📦 Pakiet DEB (Ubuntu/Debian)"
echo -e "${GREEN}2.${NC} 🚀 AppImage (Universal Linux)"  
echo -e "${GREEN}3.${NC} 💻 Linux Executable (zamiennik Windows EXE)"
echo -e "${GREEN}4.${NC} 🎯 Wszystko Linux (DEB + AppImage + Executable)"
echo -e "${GREEN}5.${NC} 🪟 Windows EXE/Portable (eksperymentalne - wymaga Wine)"
echo -e "${GREEN}6.${NC} ❌ Anuluj i wyjdź"
echo ""
echo -n -e "${BLUE}Twój wybór (1-6): ${NC}"
read choice

case $choice in
    1)
        build_deb
        cleanup_build_dirs
        ;;
    2)
        build_appimage
        cleanup_build_dirs
        ;;
    3)
        # Budowanie Linux executable bezpośrednio
        echo -e "${BLUE}🔧 Tworzenie Linux executable...${NC}"
        python3 -m venv venv_build
        source venv_build/bin/activate
        pip install --upgrade pip
        pip install PyQt6 requests pyinstaller
        pyinstaller --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons:icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py
        mkdir -p dist
        cp dist/YTDLP-GUI dist/YTDLP-GUI-linux
        rm -f dist/YTDLP-GUI
        deactivate
        echo -e "${GREEN}✅ Linux executable: dist/YTDLP-GUI-linux${NC}"
        cleanup_build_dirs
        ;;
    4)
        echo -e "${YELLOW}🔨 Budowanie wszystkiego Linux...${NC}"
        build_deb
        build_appimage 
        # Budowanie Linux executable
        echo -e "${BLUE}🔧 Dodatkowo tworzenie Linux executable...${NC}"
        python3 -m venv venv_build
        source venv_build/bin/activate
        pip install --upgrade pip
        pip install PyQt6 requests pyinstaller
        pyinstaller --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons:icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets yt.py
        mkdir -p dist
        cp dist/YTDLP-GUI dist/YTDLP-GUI-linux
        rm -f dist/YTDLP-GUI
        deactivate
        cleanup_build_dirs
        echo -e "${GREEN}✅ Wszystko gotowe w folderze dist/${NC}"
        ;;
    5)
        build_windows_on_linux
        cleanup_build_dirs
        ;;
    6)
        echo -e "${RED}❌ Anulowano${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}❌ Nieprawidłowy wybór!${NC}"
        echo "Użyj cyfr 1-6"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 Budowanie zakończone!${NC}"
echo -e "${BLUE}📁 Sprawdź folder dist/ dla gotowych plików${NC}"
