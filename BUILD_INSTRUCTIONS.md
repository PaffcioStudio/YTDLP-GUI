# Instrukcje budowania YTDLP-GUI

## Budowanie AppImage (domyślnie)

```bash
./build.sh
# lub
./build.sh appimage
```

## Budowanie pakietu .deb

```bash
./build.sh deb
# lub bezpośrednio
./build_deb.sh
```

## Wymagania systemowe

### Dla AppImage:
- Python 3.8+
- python3-venv
- libxcb-cursor0
- qt6-base-dev
- wget

### Dla pakietu .deb:
- Python 3.8+
- python3-venv
- libxcb-cursor0
- qt6-base-dev
- dpkg-dev
- ImageMagick (opcjonalne, do konwersji ikon)

## Instalacja wymagań na Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3-venv python3-full python3-pip libxcb-cursor0 libxcb-cursor-dev qt6-base-dev dpkg-dev imagemagick
```

## Instalacja pakietu .deb:

Po zbudowaniu pakietu .deb możesz go zainstalować:

```bash
sudo dpkg -i ytdlp-gui_1.0.0_amd64.deb
sudo apt-get install -f  # jeśli są problemy z zależnościami
```

## Odinstalowanie pakietu .deb:

```bash
sudo apt remove ytdlp-gui
```

## Uruchamianie aplikacji:

- Z menu aplikacji: znajdź "YTDLP-GUI" w kategorii Multimedia
- Z terminala: `ytdlp-gui`
- AppImage: `./YTDLP-GUI-*.AppImage`

## Struktura pakietu .deb:

Pakiet .deb zawiera:
- `/usr/bin/ytdlp-gui` - plik wykonywalny
- `/usr/share/applications/ytdlp-gui.desktop` - wpis menu
- `/usr/share/icons/hicolor/256x256/apps/ytdlp-gui.png` - ikona
- `/usr/share/pixmaps/ytdlp-gui.png` - ikona dla starszych środowisk
- `/usr/share/doc/ytdlp-gui/` - dokumentacja
