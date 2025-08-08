# 🛠️ YTDLP-GUI Builder

Prosty system budowania dla YTDLP-GUI z menu wyboru.

## 🚀 Użycie

### Linux
```bash
./build.sh
```

### Windows
```cmd
build.bat
```

## 📋 Menu opcji

Po uruchomieniu skryptu wybierz opcję wpisując numer (1-5):

### Linux (build.sh)
1. **📦 Pakiet DEB** (Ubuntu/Debian) 
2. **🚀 AppImage** (Universal Linux)  
3. **💻 Linux Executable** (zamiennik Windows EXE)
4. **🎯 Wszystko Linux** (DEB + AppImage + Executable)
5. **🪟 Windows EXE/Portable** (eksperymentalne - wymaga Wine/Docker)
6. **❌ Anuluj** - wyjście z programu

### Windows (build.bat)
1. **💻 Windows EXE** (pojedynczy plik)
2. **📦 Windows Portable** (folder z bibliotekami)
3. **🐧 Linux** (niemożliwe na Windows - ostrzeżenie)
4. **🎯 Wszystko Windows** (EXE + Portable)
5. **❌ Anuluj** - wyjście z programu

## 📁 Wyniki budowania

Wszystkie zbudowane pliki trafiają do folderu `dist/`:

- `ytdlp-gui_1.0.1_amd64.deb` - pakiet DEB
- `YTDLP-GUI-x86_64.AppImage` - AppImage
- `YTDLP-GUI-linux` - Linux executable
- `YTDLP-GUI-windows.exe` - Windows EXE (jeśli zbudowano przez Wine/Docker)
- `YTDLP-GUI-Portable-Windows/` - Windows Portable (jeśli zbudowano przez Wine/Docker)

## 🍷 Cross-compilation (Linux → Windows)

Opcja 5 na Linux umożliwia eksperymentalne budowanie Windows EXE/Portable:

### Metoda 1: Wine (lokalne) - **REKOMENDOWANA**
```bash
# 1. Instalacja Wine
sudo apt update
sudo apt install wine

# 2. Uruchomienie buildera (Python zostanie zainstalowany automatycznie)
./build.sh
# Wybierz opcję 5 → 1 (Wine)

# Skrypt automatycznie:
# - Sprawdzi czy Wine jest zainstalowany
# - Pobierze i zainstaluje Python 3.12 w Wine (jeśli potrzeba)
# - Zainstaluje PyQt6, requests, pyinstaller
# - Zbuduje Windows EXE
# - Zapyta czy usunąć pliki tymczasowe
```

### Metoda 2: Docker + Wine (izolowane)
```bash
# Instalacja Docker
sudo apt install docker.io
sudo usermod -aG docker $USER
# Wyloguj się i zaloguj ponownie

# Uruchomienie buildera
./build.sh
# Wybierz opcję 5 → 2 (Docker)
```

### ⚡ Automatyczne funkcje Wine:
- 🔍 **Sprawdzanie Wine** - automatycznie pyta czy zainstalować (jeśli brak)
- 📥 **Auto-instalacja Python** - pobiera Python 3.12 z python.org jeśli brak w Wine
- 📦 **Auto-instalacja pakietów** - PyQt6, requests, pyinstaller
- 🧹 **Inteligentne czyszczenie** - pyta czy usunąć pliki tymczasowe (venv_wine_build)
- ❌ **Tylko EXE** - nie tworzy niepotrzebnego folderu Portable (syfiastego)
- ⚡ **Szybkie kolejne buildy** - jeśli nie usuniesz venv, następny build ~30 sekund

## 🧹 Automatyczne czyszczenie

Skrypty automatycznie czyszczą śmieciowe foldery po budowaniu:
- `venv_build/`
- `build/`
- `*.spec`
- narzędzia AppImage (tylko Linux)

## ⚠️ Wymagania

### Linux
- Python 3.8+
- `python3-venv`
- `python3-pip`
- `dpkg-dev` (dla DEB)
- `wget` (dla AppImage)
- `wine` (opcjonalnie - dla Windows cross-compilation)
- `docker` (opcjonalnie - dla Windows cross-compilation)

### Windows
- Python 3.8+
- pip

## 🔧 Instalacja wymagań

### Ubuntu/Debian
```bash
sudo apt install python3-venv python3-pip dpkg-dev wget
```

### Windows
Pobierz Python z https://python.org i zaznacz "Add to PATH".

## 🎯 Przykład użycia

```bash
# Uruchomienie buildera
./build.sh

# Wybór opcji (np. 4 dla wszystkiego)
Twój wybór (1-5): 4

# Sprawdzenie wyników
ls dist/
```

## 📝 Uwagi

- **Cross-compilation** nie jest obsługiwana - buduj na docelowej platformie
- **Folder `/lib/`** zawiera FFmpeg dla Windows - nie usuwaj go!
- Wszystkie zależności instalują się automatycznie w środowisku wirtualnym
- Pierwszy build może potrwać dłużej ze względu na pobieranie zależności
- System automatycznie usuwa zbędne pliki PyInstaller z folderu `dist/`
