@echo off
echo Budowanie YTDLP-GUI.exe bez konsoli
echo.

:: Czyszczenie starych buildów
echo Czyszcze stare foldery i plik spec...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist YTDLP-GUI.spec del /q YTDLP-GUI.spec
echo.

:: Pakowanie aplikacji
echo Pakowanie YTDLP-GUI.exe...

C:\Python312\Scripts\pyinstaller.exe --onefile --noconsole --name=YTDLP-GUI --icon="%CD%\icon.ico" --add-data "icons;icons" yt.py

if %ERRORLEVEL% neq 0 (
    echo Cos poszlo nie tak podczas pakowania! Sprawdz logi w build\YTDLP-GUI\warn-YTDLP-GUI.txt
    pause
    exit /b 1
)

echo.
echo Gotowe! YTDLP-GUI.exe znajduje sie w folderze dist!
echo Odpal dist\YTDLP-GUI.exe i sprawdz czy wszystko smiga.
pause
exit /b 0
