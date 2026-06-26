@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Wersja aplikacji czytana z pliku VERSION (jedno wspolne miejsce)
set /p APP_VERSION=<"%~dp0VERSION"
set "APP_VERSION=%APP_VERSION: =%"
set "APP_VERSION=%APP_VERSION:	=%"
if "%APP_VERSION%"=="" (
    echo BLAD: Nie znaleziono pliku VERSION w katalogu projektu!
    exit /b 1
)

:: Kolory
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "CYAN=[96m"
set "NC=[0m"

goto :menu

:: -------------------------------------------------------
:cleanup_build_dirs
echo %BLUE%Czyszczenie folderow tymczasowych...%NC%
rmdir /s /q venv_build 2>nul
rmdir /s /q build 2>nul
del /f /q *.spec 2>nul
echo %GREEN%Wyczyszczono%NC%
goto :eof

:: -------------------------------------------------------
:build_exe
echo %YELLOW%Budowanie Windows EXE...%NC%

python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%Python nie znaleziony w PATH!%NC%
    echo Zainstaluj Python z https://python.org
    goto :eof
)

:: Usun stare srodowisko jesli istnieje
if exist venv_build rmdir /s /q venv_build

echo %BLUE%Tworzenie srodowiska wirtualnego...%NC%
python -m venv venv_build
if errorlevel 1 (
    echo %RED%Nie udalo sie utworzyc srodowiska wirtualnego!%NC%
    goto :eof
)

call venv_build\Scripts\activate.bat

echo %BLUE%Instalowanie pakietow...%NC%
python -m pip install --upgrade pip --quiet
python -m pip install PyQt6 requests pyinstaller --quiet
if errorlevel 1 (
    echo %RED%Blad instalacji pakietow!%NC%
    call deactivate
    goto :eof
)

echo %BLUE%Kompilowanie EXE...%NC%
pyinstaller --onefile --windowed ^
    --name=YTDLP-GUI ^
    --icon="icon.ico" ^
    --manifest="app.manifest" ^
    --add-data "icons;icons" ^
    --add-data "VERSION;." ^
    --hidden-import=PyQt6.QtCore ^
    --hidden-import=PyQt6.QtGui ^
    --hidden-import=PyQt6.QtWidgets ^
    --collect-all PyQt6 ^
    main.py

if errorlevel 1 (
    echo %RED%Blad kompilacji EXE!%NC%
    call deactivate
    goto :eof
)

call deactivate

if not exist dist mkdir dist
if exist "dist\YTDLP-GUI-%APP_VERSION%-windows.exe" del /f /q "dist\YTDLP-GUI-%APP_VERSION%-windows.exe"
move "dist\YTDLP-GUI.exe" "dist\YTDLP-GUI-%APP_VERSION%-windows.exe" >nul 2>&1
echo %GREEN%Windows EXE: dist\YTDLP-GUI-%APP_VERSION%-windows.exe%NC%
goto :eof

:: -------------------------------------------------------
:build_portable
echo %YELLOW%Budowanie Windows Portable...%NC%

python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%Python nie znaleziony w PATH!%NC%
    goto :eof
)

:: Usun stare srodowisko jesli istnieje
if exist venv_build rmdir /s /q venv_build

echo %BLUE%Tworzenie srodowiska wirtualnego...%NC%
python -m venv venv_build
if errorlevel 1 (
    echo %RED%Nie udalo sie utworzyc srodowiska wirtualnego!%NC%
    goto :eof
)

call venv_build\Scripts\activate.bat

echo %BLUE%Instalowanie pakietow...%NC%
python -m pip install --upgrade pip --quiet
python -m pip install PyQt6 requests pyinstaller --quiet
if errorlevel 1 (
    echo %RED%Blad instalacji pakietow!%NC%
    call deactivate
    goto :eof
)

echo %BLUE%Kompilowanie Portable...%NC%
pyinstaller --onedir --windowed ^
    --name=YTDLP-GUI-Portable ^
    --icon="icon.ico" ^
    --manifest="app.manifest" ^
    --add-data "icons;icons" ^
    --add-data "VERSION;." ^
    --hidden-import=PyQt6.QtCore ^
    --hidden-import=PyQt6.QtGui ^
    --hidden-import=PyQt6.QtWidgets ^
    --collect-all PyQt6 ^
    main.py

if errorlevel 1 (
    echo %RED%Blad kompilacji Portable!%NC%
    call deactivate
    goto :eof
)

call deactivate

if not exist dist mkdir dist
if exist "dist\YTDLP-GUI-%APP_VERSION%-Portable" rmdir /s /q "dist\YTDLP-GUI-%APP_VERSION%-Portable"
if exist "dist\YTDLP-GUI-Portable" (
    move "dist\YTDLP-GUI-Portable" "dist\YTDLP-GUI-%APP_VERSION%-Portable" >nul 2>&1
)
echo %GREEN%Windows Portable: dist\YTDLP-GUI-%APP_VERSION%-Portable\%NC%
goto :eof

:: -------------------------------------------------------
:build_linux_warning
echo %YELLOW%Budowanie Linux...%NC%
echo %RED%UWAGA: Budowanie Linux na Windows nie jest mozliwe!%NC%
echo %BLUE%Alternatywy:%NC%
echo   1. Uzyj maszyny/VM z Linuksem
echo   2. Uzyj GitHub Actions
echo   3. Uzyj WSL2
echo.
pause
goto :eof

:: -------------------------------------------------------
:menu
cls
echo %CYAN%======================================%NC%
echo %CYAN%         YTDLP-GUI Builder v%APP_VERSION%   %NC%
echo %CYAN%======================================%NC%
echo.
echo %YELLOW%Wybierz co chcesz zbudowac:%NC%
echo.
echo %GREEN%1.%NC%  Windows EXE (pojedynczy plik .exe)
echo %GREEN%2.%NC%  Windows Portable (folder z bibliotekami)
echo %GREEN%3.%NC%  Wszystko Windows (EXE + Portable)
echo %GREEN%4.%NC%  Linux (niemozliwe na Windows - instrukcja)
echo %GREEN%5.%NC%  Anuluj i wyjdz
echo.
set /p choice=%BLUE%Twoj wybor (1-5): %NC%

if "%choice%"=="1" (
    call :build_exe
    call :cleanup_build_dirs
) else if "%choice%"=="2" (
    call :build_portable
    call :cleanup_build_dirs
) else if "%choice%"=="3" (
    echo %YELLOW%Budowanie wszystkiego dla Windows...%NC%
    call :build_exe
    call :build_portable
    call :cleanup_build_dirs
    echo %GREEN%Wszystko gotowe w folderze dist\%NC%
) else if "%choice%"=="4" (
    call :build_linux_warning
    goto :end
) else if "%choice%"=="5" (
    echo Anulowano.
    goto :end
) else (
    echo %RED%Nieprawidlowy wybor! Uzyj cyfr 1-5%NC%
    pause
    goto :menu
)

:end
echo.
echo %GREEN%Budowanie zakonczone!%NC%
echo %BLUE%Sprawdz folder dist\ dla gotowych plikow%NC%
pause
