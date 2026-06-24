@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Wersja aplikacji - zmień tutaj przy każdym releazie
set "APP_VERSION=1.2.2"

:: Kolory (nie wszystkie terminale Windows obsługują ANSI)
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "CYAN=[96m"
set "NC=[0m"

:: Funkcja czyszczenia śmieciowych folderów
:cleanup_build_dirs
echo %BLUE% Czyszczenie śmieciowych folderów...%NC%
rmdir /s /q venv_build 2>nul
rmdir /s /q build 2>nul
del /f /q *.spec 2>nul
echo %GREEN% Wyczyszczono%NC%
goto :eof

:: Funkcja budowania EXE
:build_exe
echo %YELLOW% Budowanie Windows EXE...%NC%

:: Sprawdzenie Python
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED% Python nie znaleziony w PATH!%NC%
    echo Zainstaluj Python z https://python.org
    goto :eof
)

:: Tworzenie środowiska wirtualnego
echo %BLUE% Tworzenie środowiska wirtualnego...%NC%
python -m venv venv_build
if errorlevel 1 (
    echo %RED% Nie udało się utworzyć środowiska wirtualnego!%NC%
    goto :eof
)

:: Aktywacja środowiska wirtualnego
call venv_build\Scripts\activate.bat

:: Instalacja pakietów
echo %BLUE% Instalowanie wymaganych pakietów...%NC%
python -m pip install --upgrade pip
pip install PyQt6 requests pyinstaller

:: Budowanie aplikacji
echo %BLUE% Kompilowanie aplikacji...%NC%
pyinstaller --onefile --windowed --name=YTDLP-GUI --icon="icon.ico" --add-data "icons;icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets --collect-all PyQt6 main.py

if errorlevel 1 (
    echo %RED% Błąd podczas kompilacji!%NC%
    call deactivate
    goto :eof
)

:: Przeniesienie do dist
if not exist dist mkdir dist
move dist\YTDLP-GUI.exe dist\YTDLP-GUI-%APP_VERSION%-windows.exe >nul 2>&1

call deactivate
echo %GREEN% Windows EXE zbudowany: dist\YTDLP-GUI-%APP_VERSION%-windows.exe%NC%
goto :eof

:: Funkcja dla Windows Portable
:build_portable
echo %YELLOW% Budowanie Windows Portable...%NC%

:: Sprawdzenie Python
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED% Python nie znaleziony!%NC%
    goto :eof
)

:: Tworzenie środowiska wirtualnego
echo %BLUE% Tworzenie środowiska wirtualnego...%NC%
python -m venv venv_build
call venv_build\Scripts\activate.bat

:: Instalacja pakietów
echo %BLUE% Instalowanie pakietów...%NC%
python -m pip install --upgrade pip
pip install PyQt6 requests pyinstaller

:: Budowanie portable
echo %BLUE% Kompilowanie wersji portable...%NC%
pyinstaller --onedir --windowed --name=YTDLP-GUI-Portable --icon="icon.ico" --add-data "icons;icons" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets --collect-all PyQt6 main.py

if errorlevel 1 (
    echo %RED% Błąd podczas kompilacji portable!%NC%
    call deactivate
    goto :eof
)

:: Przeniesienie do dist
if not exist dist mkdir dist
if exist "dist\YTDLP-GUI-Portable" rmdir /s /q "dist\YTDLP-GUI-Portable"
move "dist\YTDLP-GUI-Portable" "dist\YTDLP-GUI-%APP_VERSION%-Portable" >nul 2>&1

call deactivate
echo %GREEN% Windows Portable zbudowany: dist\YTDLP-GUI-%APP_VERSION%-Portable\%NC%
goto :eof

:: Funkcja ostrzeżenia dla Linux
:build_linux_warning
echo %YELLOW% Budowanie Linux...%NC%
echo %RED% UWAGA: Budowanie Linux na Windows nie jest możliwe!%NC%
echo %BLUE% Alternatywne rozwiązania:%NC%
echo 1. Użyj Linux VM lub maszyny
echo 2. Użyj GitHub Actions (automatyczne)  
echo 3. Użyj WSL2 (Windows Subsystem for Linux)
echo.
pause
goto :eof

:: Menu główne
cls
echo %CYAN%%NC%
echo %CYAN%         YTDLP-GUI Builder            %NC%
echo %CYAN%%NC%
echo.
echo %YELLOW%Wybierz co chcesz zbudować:%NC%
echo.
echo %GREEN%1.%NC%  Windows EXE (pojedynczy plik)
echo %GREEN%2.%NC%  Windows Portable (folder z bibliotekami)
echo %GREEN%3.%NC%  Linux (niemożliwe na Windows)
echo %GREEN%4.%NC%  Wszystko Windows (EXE + Portable)
echo %GREEN%5.%NC%  Anuluj i wyjdź
echo.
set /p choice=%BLUE%Twój wybór (1-5): %NC%

if "%choice%"=="1" (
    call :build_exe
    call :cleanup_build_dirs
) else if "%choice%"=="2" (
    call :build_portable
    call :cleanup_build_dirs
) else if "%choice%"=="3" (
    call :build_linux_warning
    goto :end
) else if "%choice%"=="4" (
    echo %YELLOW% Budowanie wszystkiego dla Windows...%NC%
    call :build_exe
    call :build_portable
    call :cleanup_build_dirs
    echo %GREEN% Wszystko gotowe w folderze dist\%NC%
) else if "%choice%"=="5" (
    echo %RED% Anulowano%NC%
    goto :end
) else (
    echo %RED% Nieprawidłowy wybór!%NC%
    echo Użyj cyfr 1-5
    pause
    goto :menu
)

:end
echo.
echo %GREEN% Budowanie zakończone!%NC%
echo %BLUE% Sprawdź folder dist\ dla gotowych plików%NC%
pause
