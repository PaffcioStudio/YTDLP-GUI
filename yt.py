import os
import sys
import json
import subprocess
import requests
import logging
import re
import zipfile
import shutil
import platform
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QCheckBox,
    QSpinBox, QFormLayout, QGroupBox, QFileDialog, QProgressBar,
    QMessageBox, QScrollArea, QListWidget, QInputDialog, QStyle
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSettings, QSize
from PyQt6.QtGui import QClipboard, QIcon, QPalette, QColor, QFont

# --- Konfiguracja ścieżek i logowania ---
app_data_base_dir = Path(os.getenv("APPDATA") or Path.home()) / "VideoDownloader"
log_dir = app_data_base_dir / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=log_dir / "app.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

LIBS_DIR = app_data_base_dir / "libs"
YTDLP_PATH_WINDOWS = LIBS_DIR / "yt-dlp.exe"
FFMPEG_DIR = LIBS_DIR / "ffmpeg"
FFMPEG_BIN_DIR = FFMPEG_DIR / "bin"
FFMPEG_PATH_WINDOWS = FFMPEG_BIN_DIR / "ffmpeg.exe"
FFMPEG_DOWNLOAD_URL_WINDOWS = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

DETAILED_PROGRESS_REGEX = re.compile(r"\[download\]\s+([\d.]+)\%(?:.*?(?:of|\s+)\s*([\d.]+\S+))?(?:.*?at\s+([\d.]+\S+)\/s)?.*")

# Funkcja do obsługi ścieżek zasobów w PyInstallerze
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    # Używamy getattr, aby bezpiecznie sprawdzić _MEIPASS, nie wywołując alarmu Pylance'a
    base_path = getattr(sys, '_MEIPASS', os.path.abspath(".")) #
    return os.path.join(base_path, relative_path)


# --- Wątki robocze ---

class CDAStatusCheckThread(QThread):
    """Wątek do sprawdzania statusu logowania CDA w tle."""
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, email, password, ytdlp_path, main_window: 'YTDLPGUI', parent=None):
        super().__init__(parent)
        self.email = email
        self.password = password
        self.ytdlp_path = ytdlp_path
        self.main_window = main_window
        self.process = None

    def run(self):
        if not self.email or not self.password:
            self.finished_signal.emit(False, "Wprowadź email i hasło.")
            return

        try:
            command = [
                str(self.ytdlp_path),
                "--username", self.email,
                "--password", self.password,
                "--verbose",
                "https://www.cda.pl/" # Używamy generycznego URL do sprowokowania logowania
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=creationflags
            )

            if not self.process or not self.process.stderr:
                self.finished_signal.emit(False, "Nie udało się uruchomić procesu weryfikacji.")
                logger.error("Nie udało się utworzyć procesu Popen lub jego strumienia stderr dla CDAStatusCheckThread.")
                return

            output = ""
            while True:
                line = self.process.stderr.readline()
                if not line and self.process.poll() is not None:
                    break
                if line:
                    output += line
                    logger.debug(f"[CDA Check]: {line.strip()}")
                    # Sukces logowania
                    if "[cda] Logged in as" in line:
                        self.process.terminate()
                        self.finished_signal.emit(True, "Zalogowano pomyślnie.")
                        return
                    # Typowe błędy logowania
                    if "Unable to log in" in line:
                        self.process.terminate()
                        self.finished_signal.emit(False, "Błąd logowania: Nieprawidłowe dane.")
                        return
                    # Błąd połączenia z CDA
                    if "ERROR: Unable to download webpage" in line or "ERROR: Unable to extract" in line:
                        self.process.terminate()
                        self.finished_signal.emit(False, "Błąd połączenia z CDA. Sprawdź internet lub dostępność strony.")
                        return
                    # Błąd autoryzacji (np. CAPTCHA, blokada konta)
                    if "ERROR: This video is only available for registered users" in line:
                        self.process.terminate()
                        self.finished_signal.emit(False, "Wymagane konto CDA Premium lub dodatkowa autoryzacja.")
                        return
                    # Błąd limitu prób logowania
                    if "too many login attempts" in line or "temporarily blocked" in line:
                        self.process.terminate()
                        self.finished_signal.emit(False, "Zbyt wiele prób logowania. Konto tymczasowo zablokowane.")
                        return
            self.process.wait()
            # Ostateczne sprawdzenie, jeśli nie znaleziono wcześniej
            if "[cda] Logged in as" in output:
                self.finished_signal.emit(True, "Zalogowano pomyślnie.")
            elif "Unable to log in" in output:
                self.finished_signal.emit(False, "Błąd logowania: Nieprawidłowe dane.")
            elif "ERROR: Unable to download webpage" in output or "ERROR: Unable to extract" in output:
                self.finished_signal.emit(False, "Błąd połączenia z CDA. Sprawdź internet lub dostępność strony.")
            elif "ERROR: This video is only available for registered users" in output:
                self.finished_signal.emit(False, "Wymagane konto CDA Premium lub dodatkowa autoryzacja.")
            elif "too many login attempts" in output or "temporarily blocked" in output:
                self.finished_signal.emit(False, "Zbyt wiele prób logowania. Konto tymczasowo zablokowane.")
            elif "Successfully authenticated" in output or "Authentication succeeded" in output:
                self.finished_signal.emit(True, "Logowanie prawdopodobnie powiodło się (brak typowego komunikatu CDA, ale nie wykryto błędów).")
            else:
                # Heurystyka: jeśli nie ma typowych błędów, a yt-dlp nie zwraca komunikatu sukcesu, ale nie ma też komunikatów o błędzie
                if "ERROR" not in output and "Unable to log in" not in output and "temporarily blocked" not in output:
                    self.finished_signal.emit(True, "Test nie zwrócił błedów. Wygląda na poprawne dane logowania.")
                else:
                    self.finished_signal.emit(False, "Nie udało się zweryfikować statusu. Sprawdź dane lub spróbuj ponownie.")

        except FileNotFoundError:
            self.finished_signal.emit(False, f"Błąd: Nie znaleziono yt-dlp w '{self.ytdlp_path}'")
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania statusu CDA: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Błąd: {e}")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()


class YTDLPThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)
    progress_percent_signal = pyqtSignal(int)
    progress_detailed_signal = pyqtSignal(int, str, str, str)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.is_running = True
        self.process = None

    def run(self):
        try:
            if not Path(self.command[0]).exists() and self.command[0] != 'yt-dlp':
                error_msg = f"Błąd: Nie znaleziono pliku wykonawczego: {self.command[0]}"
                self.progress_signal.emit(error_msg)
                logger.error(error_msg)
                self.finished_signal.emit(False)
                return
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            quoted_command = [str(arg) for arg in self.command]

            logger.info(f"Uruchamiam proces: {' '.join(quoted_command)}")
            self.process = subprocess.Popen(
                quoted_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=creationflags,
            )

            if not self.process or not self.process.stdout:
                self.finished_signal.emit(False)
                logger.error("Nie udało się utworzyć procesu Popen lub jego strumienia stdout dla YTDLPThread.")
                return

            while self.is_running:
                output = self.process.stdout.readline()
                if output == '' and self.process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    self.progress_signal.emit(line)
                    match = DETAILED_PROGRESS_REGEX.search(line)
                    if match:
                        try:
                            percent = int(float(match.group(1)))
                            total_size_str = match.group(2) if match.group(2) else "N/A"
                            speed_match = match.group(3)
                            speed_str = speed_match + "/s" if speed_match else "N/A"
                            self.progress_detailed_signal.emit(percent, total_size_str, speed_str, line)

                        except (ValueError, IndexError) as e:
                            logger.debug(f"Failed to parse detailed progress from line '{line}': {e}")
                            pass


            returncode = self.process.wait()
            logger.info(f"Proces zakończony z kodem: {returncode}")
            if returncode == 0:
                self.progress_detailed_signal.emit(100, "N/A", "N/A", "[download] 100%")

            self.finished_signal.emit(returncode == 0)

        except FileNotFoundError:
            error_msg = f"Plik wykonawczy nie znaleziono: {self.command[0]}"
            logger.error(error_msg)
            self.progress_signal.emit(f"Błąd: {error_msg}\nUpewnij się, że ścieżka w ustawieniach jest poprawna.")
            self.finished_signal.emit(False)
        except Exception as e:
            logger.error(f"Błąd w wątku pobierania: {e}", exc_info=True)
            self.progress_signal.emit(f"Błąd: {str(e)}")
            self.finished_signal.emit(False)

    def stop(self):
        self.is_running = False
        if self.process and self.process.poll() is None:
            try:
                logger.info("Próbuję zakończyć proces yt-dlp...")
                if os.name == 'nt':
                    # Użyj taskkill dla lepszego zakończenia drzewa procesów (ffmpeg)
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.kill(self.process.pid, 2) # SIGINT

                self.process.wait(timeout=5)
                logger.info("Proces yt-dlp zakończony (terminate/SIGINT).")
            except subprocess.TimeoutExpired:
                logger.warning("Proces nie zakończył się po próbie zakończenia, wymuszam zatrzymanie (kill).")
                try:
                    self.process.kill()
                    logger.info("Proces yt-dlp zabity.")
                except Exception as kill_e:
                    logger.error(f"Błąd podczas zabijania procesu: {kill_e}")
            except ProcessLookupError:
                logger.warning("Próba zatrzymania nieistniejącego procesu.")
            except Exception as e:
                logger.error(f"Błąd podczas zatrzymywania procesu: {e}", exc_info=True)
        else:
            logger.info("Próba zatrzymania, ale proces nie działa lub już się zakończył.")


class UpdateYTDLPThread(QThread):
    finished_signal = pyqtSignal(bool, str)
    progress_signal = pyqtSignal(str)

    def __init__(self, yt_dlp_path, main_window: 'YTDLPGUI', parent=None):
        super().__init__(parent)
        self.yt_dlp_path = Path(yt_dlp_path)
        self.main_window = main_window
        if self.yt_dlp_path.is_absolute() and not str(self.yt_dlp_path).startswith('yt-dlp'):
            self.yt_dlp_path.parent.mkdir(parents=True, exist_ok=True)

    def run(self):
        if not self.main_window.settings.value("check_ytdlp_updates", True, type=bool):
            logger.info("Sprawdzanie aktualizacji yt-dlp pominięte (ustawienie wyłączone)")
            self.check_local_ytdlp(str(self.yt_dlp_path))
            return

        try:
            self.progress_signal.emit("Sprawdzam aktualizacje yt-dlp...")
            api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            latest_version = data.get("tag_name", "")
            assets = data.get("assets", [])
            exe_url = None
            target_yt_dlp_path = YTDLP_PATH_WINDOWS if os.name == 'nt' else self.yt_dlp_path

            if os.name == 'nt':
                target_yt_dlp_path.parent.mkdir(parents=True, exist_ok=True)

                for asset in assets:
                    name = asset.get("name", "").lower()
                    if name.endswith(".exe") and ("yt-dlp" in name or "youtube-dlp" in name):
                        if platform.architecture()[0] == '64bit' and ("i686" not in name and "386" not in name):
                            exe_url = asset.get("browser_download_url")
                            break
                if not exe_url:
                    for asset in assets:
                        name = asset.get("name", "").lower()
                        if name.endswith(".exe") and ("yt-dlp" in name or "youtube-dlp" in name):
                            exe_url = asset.get("browser_download_url")
                            break

                if not exe_url:
                    self.finished_signal.emit(False, "Nie znaleziono pliku yt-dlp.exe w najnowszym wydaniu na GitHub.")
                    logger.error("Nie znaleziono pliku yt-dlp.exe w zasobach GitHub.")
                    self.check_local_ytdlp(str(self.yt_dlp_path))
                    return
            if os.name == 'nt' and exe_url:
                current_version = ""
                if target_yt_dlp_path.exists():
                    try:
                        result = subprocess.run(
                            [str(target_yt_dlp_path), "--version"],
                            capture_output=True, text=True, check=True, timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                            encoding='utf-8'
                        )
                        current_version = result.stdout.strip()
                        self.progress_signal.emit(f"Obecna wersja yt-dlp: {current_version} (lokalnie: {target_yt_dlp_path.name})")
                        logger.info(f"Obecna wersja yt-dlp: {current_version} (lokalnie)")
                    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                        self.progress_signal.emit("Nie można pobrać obecnej wersji yt-dlp (możliwe, że plik nie istnieje, jest uszkodzony lub brak uprawnień).")
                        logger.warning("Nie można uzyskać obecnej wersji yt-dlp.")
                        current_version = "brak"
                    except Exception as e:
                        logger.warning(f"Błąd podczas sprawdzania wersji yt-dlp: {e}", exc_info=True)
                        self.progress_signal.emit(f"Błąd podczas sprawdzania wersji yt-dlp: {e}")
                        current_version = "error"
                latest_version_clean = latest_version.lstrip('v')
                current_version_clean = current_version.lstrip('v')
                needs_update = False
                if current_version in ["brak", "error"]:
                    needs_update = True
                    self.progress_signal.emit("Lokalna wersja yt-dlp nieznana lub brak pliku. Próbuję pobrać najnowszą.")
                elif latest_version_clean != current_version_clean:
                    try:
                        current_parts = list(map(int, current_version_clean.split('.')))
                        latest_parts = list(map(int, latest_version_clean.split('.')))
                        max_len = max(len(current_parts), len(latest_parts))
                        current_parts.extend([0] * (max_len - len(current_parts)))
                        latest_parts.extend([0] * (max_len - len(latest_parts)))

                        if latest_parts > current_parts:
                            needs_update = True
                            self.progress_signal.emit(f"Dostępna nowsza wersja yt-dlp: {latest_version} (obecna: {current_version}). Pobieram...")
                        else:
                            self.progress_signal.emit("Najnowsza wersja yt-dlp jest już zainstalowana.")
                            logger.info("YT-DLP jest aktualne.")
                            self.finished_signal.emit(True, "Najnowsza wersja yt-dlp jest już zainstalowana.")
                            self.main_window.settings.setValue("ytdlp_path", str(target_yt_dlp_path))
                            return

                    except ValueError:
                        logger.warning(f"Nie udało się porównać wersji yt-dlp ({current_version} vs {latest_version}) numerycznie. Zakładam potrzebę aktualizacji jeśli różne.")
                        if latest_version_clean != current_version_clean:
                            needs_update = True
                            self.progress_signal.emit(f"Dostępna inna wersja yt-dlp: {latest_version} (obecna: {current_version}). Pobieram (porównanie numeryczne nie powiodło się)...")
                        else:
                            self.progress_signal.emit("Wersja yt-dlp zgodna z najnowszą (porównanie tekstowe).")
                            logger.info("YT-DLP jest aktualne (porównanie tekstowe).")
                            self.finished_signal.emit(True, "Wersja yt-dlp zgodna z najnowszą.")
                            self.main_window.settings.setValue("ytdlp_path", str(target_yt_dlp_path))
                            return

                if not needs_update:
                    self.progress_signal.emit("Najnowsza wersja yt-dlp jest już zainstalowana.")
                    logger.info("YT-DLP jest aktualne.")
                    self.finished_signal.emit(True, "Najnowsza wersja yt-dlp jest już zainstalowana.")
                    self.main_window.settings.setValue("ytdlp_path", str(target_yt_dlp_path))
                    return
                self.progress_signal.emit(f"Pobieram yt-dlp {latest_version} z {exe_url} do {target_yt_dlp_path}...")
                logger.info(f"Pobieram yt-dlp {latest_version} z {exe_url} do {target_yt_dlp_path}")
                exe_response = requests.get(exe_url, timeout=60, stream=True)
                exe_response.raise_for_status()
                temp_yt_dlp_path = target_yt_dlp_path.with_suffix(".tmp")

                with open(temp_yt_dlp_path, "wb") as f:
                    shutil.copyfileobj(exe_response.raw, f)
                os.replace(temp_yt_dlp_path, target_yt_dlp_path)
                self.progress_signal.emit(f"Pobrano brakujący/zaktualizowany moduł yt-dlp {latest_version}.")
                logger.info(f"Pobrano brakujący/zaktualizowany moduł yt-dlp {latest_version}.")
                self.main_window.settings.setValue("ytdlp_path", str(target_yt_dlp_path))
                self.finished_signal.emit(True, f"Pobrano brakujący/zaktualizowany moduł yt-dlp {latest_version}.")

            elif os.name != 'nt':
                logger.info("System nie jest Windows, pomijam automatyczne pobieranie yt-dlp. Sprawdzam lokalną instalację.")
                self.check_local_ytdlp(str(self.yt_dlp_path))

        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd sieciowy podczas aktualizacji yt-dlp: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Błąd sieciowy podczas aktualizacji yt-dlp: {e}")
            logger.warning("Błąd sieciowy podczas sprawdzania aktualizacji yt-dlp. Sprawdzam lokalną instalację.")
            self.check_local_ytdlp(str(self.yt_dlp_path))
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd aktualizacji yt-dlp: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Nieoczekiwany błąd aktualizacji yt-dlp: {e}")
            logger.warning("Nieoczekiwany błąd podczas aktualizacji yt-dlp. Sprawdzam lokalną instalację.")
            self.check_local_ytdlp(str(self.yt_dlp_path))
        finally:
            temp_yt_dlp_path = YTDLP_PATH_WINDOWS.with_suffix(".tmp") if os.name == 'nt' else None
            if temp_yt_dlp_path and temp_yt_dlp_path.exists():
                try:
                    temp_yt_dlp_path.unlink()
                    logger.info(f"Usunięto plik tymczasowy yt-dlp: {temp_yt_dlp_path}")
                except Exception as e:
                    logger.warning(f"Nie udało się usunąć pliku tymczasowego yt-dlp: {temp_yt_dlp_path}, {e}")


    def check_local_ytdlp(self, ytdlp_path_setting_str):
        """Checks if yt-dlp exists in the specified path or system PATH."""
        ytdlp_path_setting = Path(ytdlp_path_setting_str) if ytdlp_path_setting_str else ""
        try:
            if not ytdlp_path_setting_str: raise FileNotFoundError("Path is empty")
            logger.info(f"Sprawdzam lokalną instalację yt-dlp pod ścieżką z ustawień: {ytdlp_path_setting}")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(
                [str(ytdlp_path_setting), "--version"],
                capture_output=True, text=True, check=True, timeout=10,
                creationflags=creationflags,
                encoding='utf-8'
            )
            current_version = result.stdout.strip()
            message = f"Znaleziono yt-dlp pod ścieżką z ustawień: {ytdlp_path_setting} (Wersja: {current_version})"
            logger.info(message)
            self.finished_signal.emit(True, message)
            self.main_window.settings.setValue("ytdlp_path", str(ytdlp_path_setting))

        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            try:
                logger.info("Nie znaleziono yt-dlp pod ustawioną ścieżką. Sprawdzam w systemowej ścieżce (PATH)...")
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                result = subprocess.run(
                    ["yt-dlp", "--version"],
                    capture_output=True, text=True, check=True, timeout=10,
                    creationflags=creationflags,
                    encoding='utf-8'
                )
                current_version = result.stdout.strip()
                message = f"Znaleziono yt-dlp w systemowej ścieżce (PATH). (Wersja: {current_version})"
                logger.info(message)
                self.finished_signal.emit(True, message)
                self.main_window.settings.setValue("ytdlp_path", "yt-dlp")

            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                message = f"Nie znaleziono yt-dlp ani pod ustawioną ścieżką ({ytdlp_path_setting}), ani w systemowej ścieżce (PATH).\nProszę zainstalować yt-dlp ręcznie lub włączyć automatyczne pobieranie (tylko Windows)."
                logger.error(message)
                self.finished_signal.emit(False, message)
                self.main_window.settings.setValue("ytdlp_path", "")
            except Exception as e:
                message = f"Nieoczekiwany błąd podczas sprawdzania yt-dlp w PATH: {e}"
                logger.error(message, exc_info=True)
                self.finished_signal.emit(False, message)
                self.main_window.settings.setValue("ytdlp_path", "")

        except Exception as e:
            message = f"Nieoczekiwany błąd podczas sprawdzania lokalnej instalacji yt-dlp: {e}"
            logger.error(message, exc_info=True)
            self.finished_signal.emit(False, message)
            self.main_window.settings.setValue("ytdlp_path", "")


class DownloadFFmpegThread(QThread):
    finished_signal = pyqtSignal(bool, str)
    progress_signal = pyqtSignal(str)

    def __init__(self, ffmpeg_path, main_window: 'YTDLPGUI', parent=None):
        super().__init__(parent)
        self.ffmpeg_path_setting = Path(ffmpeg_path)
        self.main_window = main_window


    def run(self):
        auto_download_enabled = self.main_window.settings.value("auto_download_ffmpeg", os.name == 'nt', type=bool) and os.name == 'nt'
        download_target_exe = FFMPEG_PATH_WINDOWS

        if os.name != 'nt':
            message = "Automatyczne pobieranie FFmpeg nie jest obsługiwane na tym systemie operacyjnym. Proszę zainstalować FFmpeg ręcznie i upewnić się, że jest w ścieżce systemowej (PATH) lub ustawić ścieżkę w Ustawieniach."
            logger.info("Pobieranie FFmpeg pominięte - system nie jest Windows.")
            self.progress_signal.emit(message)
            self.check_local_ffmpeg(str(self.ffmpeg_path_setting))
            return
        try:
            self.progress_signal.emit("Sprawdzam obecność FFmpeg...")

            logger.info(f"Sprawdzam obecność FFmpeg w domyślnej lokalizacji auto-pobierania: {download_target_exe}")
            if download_target_exe.exists():
                self.progress_signal.emit("FFmpeg znaleziono lokalnie w domyślnej lokalizacji.")
                logger.info("FFmpeg znaleziono lokalnie.")
                self.finished_signal.emit(True, "FFmpeg jest już zainstalowany.")
                self.main_window.settings.setValue("ffmpeg_path", str(download_target_exe))
                return

            if not auto_download_enabled:
                logger.info("Automatyczne pobieranie FFmpeg wyłączone. Sprawdzam inne ścieżki.")
                self.progress_signal.emit("Automatyczne pobieranie FFmpeg jest wyłączone. Sprawdzam inne lokalizacje.")
                self.check_local_ffmpeg(str(self.ffmpeg_path_setting))
                return

            self.progress_signal.emit(f"FFmpeg nie znaleziono w domyślnej lokalizacji auto-pobierania. Próbuję pobrać z {FFMPEG_DOWNLOAD_URL_WINDOWS}")
            logger.info(f"FFmpeg nie znaleziono. Próbuję pobrać z {FFMPEG_DOWNLOAD_URL_WINDOWS}")
            response = requests.get(FFMPEG_DOWNLOAD_URL_WINDOWS, stream=True, timeout=180)
            response.raise_for_status()
            temp_zip_path = LIBS_DIR / "ffmpeg.zip"
            temp_zip_path.parent.mkdir(parents=True, exist_ok=True)

            self.progress_signal.emit("Pobieram archiwum FFmpeg...")

            with open(temp_zip_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)

            self.progress_signal.emit("Pobieranie archiwum FFmpeg zakończone.")
            logger.info("Pobieranie FFmpeg zakończone.")

            self.progress_signal.emit(f"Rozpakowuję FFmpeg do {FFMPEG_BIN_DIR}...")
            logger.info(f"Rozpakowuję FFmpeg z: {temp_zip_path} do {FFMPEG_BIN_DIR}")

            FFMPEG_BIN_DIR.mkdir(parents=True, exist_ok=True)
            files_to_extract = ["ffmpeg.exe", "ffplay.exe", "ffprobe.exe"]
            extracted_tools = []

            try:
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    for member_info in zip_ref.infolist():
                        if member_info.is_dir():
                            continue

                        file_path_parts = member_info.filename.replace('\\', '/').split('/')
                        file_name = file_path_parts[-1].lower()

                        if 'bin' in file_path_parts and file_name in files_to_extract:
                            logger.info(f"Znaleziono w archiwum: {member_info.filename}")
                            target_path = FFMPEG_BIN_DIR / os.path.basename(member_info.filename)
                            with zip_ref.open(member_info) as source_file, open(target_path, "wb") as target_file:
                                shutil.copyfileobj(source_file, target_file)
                            logger.info(f"Rozpakowano: {target_path}")
                            extracted_tools.append(file_name)

                if "ffmpeg.exe" not in extracted_tools:
                    self.progress_signal.emit("Błąd: Nie znaleziono pliku ffmpeg.exe w pobranym archiwum.")
                    logger.error(f"Nie znaleziono pliku ffmpeg.exe w archiwum: {temp_zip_path}")
                    self.finished_signal.emit(False, "Nie znaleziono pliku ffmpeg.exe w archiwum zip FFmpeg.")
                    return

                self.progress_signal.emit("Rozpakowywanie zakończone.")
                logger.info("FFmpeg i powiązane narzędzia rozpakowane pomyślnie.")
                self.finished_signal.emit(True, "Pobrano i zainstalowano FFmpeg.")
                self.main_window.settings.setValue("ffmpeg_path", str(download_target_exe))

            except zipfile.BadZipFile:
                logger.error(f"Pobrany plik FFmpeg jest uszkodzony ZIP: {temp_zip_path}", exc_info=True)
                self.finished_signal.emit(False, "Pobrany plik FFmpeg jest uszkodzony.")
                if str(self.ffmpeg_path_setting) != str(download_target_exe) and str(self.ffmpeg_path_setting) != 'ffmpeg':
                    self.check_local_ffmpeg(str(self.ffmpeg_path_setting))
                return

            except Exception as e:
                logger.error(f"Błąd podczas rozpakowywania FFmpeg: {e}", exc_info=True)
                self.finished_signal.emit(False, f"Nieoczekiwany błąd rozpakowywania FFmpeg: {e}")
                if str(self.ffmpeg_path_setting) != str(download_target_exe) and str(self.ffmpeg_path_setting) != 'ffmpeg':
                    self.check_local_ffmpeg(str(self.ffmpeg_path_setting))
                return

        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd sieciowy podczas pobierania FFmpeg: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Błąd sieciowy podczas pobierania FFmpeg: {e}")
            logger.warning("Błąd sieciowy podczas pobierania FFmpeg. Sprawdzam lokalną instalację.")
            self.check_local_ffmpeg(str(self.ffmpeg_path_setting))
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas pobierania/rozpakowywania FFmpeg: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Nieoczekiwany błąd podczas pobierania/rozpakowywania FFmpeg: {e}")
            logger.warning("Nieoczekiwany błąd podczas pobierania/rozpakowywania FFmpeg. Sprawdzam lokalną instalację.")
            self.check_local_ffmpeg(str(self.ffmpeg_path_setting))
        finally:
            temp_zip_path = LIBS_DIR / "ffmpeg.zip"
            if temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                    logger.info(f"Usunięto plik tymczasowy FFmpeg: {temp_zip_path}")
                except Exception as e:
                    logger.warning(f"Nie udało się usunąć pliku tymczasowego FFmpeg: {temp_zip_path}, {e}")


    def check_local_ffmpeg(self, ffmpeg_path_setting_str):
        """Checks if ffmpeg exists in the specified path or system PATH."""
        ffmpeg_path_setting = Path(ffmpeg_path_setting_str) if ffmpeg_path_setting_str else ""
        try:
            if not ffmpeg_path_setting_str: raise FileNotFoundError("Path is empty")
            logger.info(f"Sprawdzam lokalną instalację FFmpeg pod ścieżką z ustawień: {ffmpeg_path_setting}")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(
                [str(ffmpeg_path_setting), "-version"],
                capture_output=True, text=True, check=True, timeout=10,
                creationflags=creationflags,
                encoding='utf-8'
            )
            version_match = re.search(r"ffmpeg version (.+)", result.stdout) # Note: version info is often in stdout not stderr for ffmpeg
            if not version_match:
                version_match = re.search(r"ffmpeg version (.+)", result.stderr)

            current_version = version_match.group(1).split(' ')[0] if version_match else "unknown version"

            message = f"Znaleziono FFmpeg pod ścieżką z ustawień: {ffmpeg_path_setting} (Wersja: {current_version})"
            logger.info(message)
            self.finished_signal.emit(True, message)
            self.main_window.settings.setValue("ffmpeg_path", str(ffmpeg_path_setting))

        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            try:
                logger.info("Nie znaleziono FFmpeg pod ustawioną ścieżką. Sprawdzam w systemowej ścieżce (PATH)...")
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                result = subprocess.run(
                    ["ffmpeg", "-version"],
                    capture_output=True, text=True, check=True, timeout=10,
                    creationflags=creationflags,
                    encoding='utf-8'
                )
                version_match = re.search(r"ffmpeg version (.+)", result.stdout)
                if not version_match:
                    version_match = re.search(r"ffmpeg version (.+)", result.stderr)

                current_version = version_match.group(1).split(' ')[0] if version_match else "unknown version"
                message = f"Znaleziono FFmpeg w systemowej ścieżce (PATH). (Wersja: {current_version})"
                logger.info(message)
                self.finished_signal.emit(True, message)
                self.main_window.settings.setValue("ffmpeg_path", "ffmpeg")

            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                message = f"Nie znaleziono FFmpeg ani pod ustawioną ścieżką ({ffmpeg_path_setting}), ani w systemowej ścieżce (PATH).\nKonwersja/scalanie może zawieść. Proszę zainstalować FFmpeg ręcznie lub włączyć automatyczne pobieranie (tylko Windows)."
                logger.warning(message)
                self.finished_signal.emit(False, message)
                self.main_window.settings.setValue("ffmpeg_path", "")

            except Exception as e:
                message = f"Nieoczekiwany błąd podczas sprawdzania FFmpeg w PATH: {e}"
                logger.error(message, exc_info=True)
                self.finished_signal.emit(False, message)
                self.main_window.settings.setValue("ffmpeg_path", "")

        except Exception as e:
            message = f"Nieoczekiwany błąd podczas sprawdzania lokalnej instalacji FFmpeg: {e}"
            logger.error(message, exc_info=True)
            self.finished_signal.emit(False, message)
            self.main_window.settings.setValue("ffmpeg_path", "")

# --- Główne okno GUI ---

class YTDLPGUI(QMainWindow):
    def update_remove_btn_state(self):
        # Przycisk 'Usuń' i 'Edytuj' aktywne tylko gdy coś jest zaznaczone
        has_selection = bool(self.queue_list.selectedItems())
        self.remove_btn.setEnabled(has_selection)
        self.edit_btn.setEnabled(has_selection)
    def __init__(self):
        super().__init__()
        self.appdata_dir = app_data_base_dir
        self.appdata_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Katalog aplikacji: {self.appdata_dir}")
        self.settings = QSettings(str(self.appdata_dir / "settings.ini"), QSettings.Format.IniFormat)
        self.current_video_title = "Unknown"
        self.failed_log_file = log_dir / "failed_downloads.log"
        self.failed_logger = logging.getLogger("failed_downloads")
        failed_handler = logging.FileHandler(self.failed_log_file, encoding="utf-8")
        failed_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        self.failed_logger.addHandler(failed_handler)
        self.failed_logger.setLevel(logging.INFO)
        self.default_ytdlp_path_fallback = str(YTDLP_PATH_WINDOWS) if os.name == 'nt' else 'yt-dlp'
        self.default_ffmpeg_path_local_fallback = str(FFMPEG_PATH_WINDOWS) if os.name == 'nt' else 'ffmpeg'

        self.thread: Optional[YTDLPThread] = None
        self.update_ytdlp_thread: Optional[UpdateYTDLPThread] = None
        self.download_ffmpeg_thread: Optional[DownloadFFmpegThread] = None
        self.cda_check_thread: Optional[CDAStatusCheckThread] = None

        self.download_queue = []
        self.pending_queue_check = False

        self.init_ui()
        self.load_settings(initial=True)

        self.apply_style()
        self.setEnabled(False)
        self.output_text.append("Sprawdzam zależności...")
        self.check_ytdlp_version()

    def apply_style(self):
        """Applies the chosen theme style."""
        theme = self.settings.value("theme", "Dark", type=str)

        if theme == "Dark":
            self.apply_dark_style()
        else:
            self.apply_white_style()

        logger.info(f"Zastosowano motyw: {theme}")

    def apply_dark_style(self):
        """Applies a custom dark theme style."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.Base, QColor(55, 55, 55))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 50))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(50, 50, 50))
        palette.setColor(QPalette.ColorRole.Text, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.Button, QColor(60, 60, 60))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(200, 200, 200))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(80, 80, 80))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(120, 120, 120))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(120, 120, 120))
        accent_color = QColor(255, 165, 0) # Orange
        self.setPalette(palette)
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {palette.color(QPalette.ColorRole.Window).name()};
                color: {palette.color(QPalette.ColorRole.WindowText).name()};
            }}
            QWidget {{ /* Apply text color to all widgets by default */
                color: {palette.color(QPalette.ColorRole.Text).name()};
                outline: none; /* Remove focus outline */
            }}
            QTabWidget::pane {{
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                background-color: {palette.color(QPalette.ColorRole.Window).name()}; /* Dark background for content pane */
            }}
            QTabWidget::tab-bar {{
                left: 5px; /* move to the right */
            }}
            QTabBar::tab {{
                background: {palette.color(QPalette.ColorRole.Button).name()};
                color: {palette.color(QPalette.ColorRole.ButtonText).name()};
                border: 1px solid {palette.color(QPalette.ColorRole.Button).name()};
                border-bottom-color: {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 5px 10px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {palette.color(QPalette.ColorRole.Base).name()};
                border-color: {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                border-bottom-color: {palette.color(QPalette.ColorRole.Base).name()}; /* same as pane color */
            }}
            QTabBar::tab:hover {{
                background: {palette.color(QPalette.ColorRole.Button).lighter(120).name()};
            }}

            QScrollArea > QWidget > QWidget {{ /* Ensure widget inside ScrollArea has correct background */
                background-color: {palette.color(QPalette.ColorRole.Window).name()};
            }}

            QGroupBox {{
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px; /* Add padding to make space for title */
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: {accent_color.name()}; /* Accent color for titles */
                font-weight: bold;
            }}

            QLineEdit, QTextEdit, QComboBox, QListWidget, QSpinBox {{
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                color: {palette.color(QPalette.ColorRole.Text).name()};
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                border-radius: 3px;
                padding: 3px;
                selection-background-color: {accent_color.name()};
                selection-color: #000000;
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border: 1px solid {accent_color.name()};
            }}
            QTextEdit {{
                padding: 5px;
            }}
            QComboBox {{
                padding-right: 20px; /* make room for the arrow */
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 15px;
                border-left-width: 1px;
                border-left-color: {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                border-left-style: solid; /* just a vertical line */
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }}
            QComboBox QAbstractItemView {{ /* Dropdown list items */
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                color: {palette.color(QPalette.ColorRole.Text).name()};
                selection-background-color: {accent_color.name()};
                selection-color: #000000;
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
            }}
            QComboBox QAbstractItemView::item {{
                padding: 5px;
            }}

            QPushButton {{
                background-color: {palette.color(QPalette.ColorRole.Button).lighter(120).name()};
                color: {palette.color(QPalette.ColorRole.ButtonText).name()};
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                padding: 5px 15px;
                border-radius: 3px;
                font-weight: bold;
            }}
            QPushButton#downloadButton, QPushButton#pasteAndAddButton {{
                background-color: {accent_color.name()};
                color: #000000;
            }}
            QPushButton:hover {{ background-color: {palette.color(QPalette.ColorRole.Button).lighter(150).name()}; }}
            QPushButton#downloadButton:hover, QPushButton#pasteAndAddButton:hover {{ background-color: {accent_color.lighter(120).name()}; }}
            QPushButton:pressed {{ background-color: {palette.color(QPalette.ColorRole.Button).darker(120).name()}; }}
            QPushButton#downloadButton:pressed, QPushButton#pasteAndAddButton:pressed {{ background-color: {accent_color.darker(120).name()}; }}
            QPushButton:disabled {{
                background-color: {palette.color(QPalette.ColorRole.Button).name()};
                color: {palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name()};
            }}

            QCheckBox {{
                color: {palette.color(QPalette.ColorRole.Text).name()};
                spacing: 5px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                border-radius: 2px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 1px solid {accent_color.name()};
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid {accent_color.darker(120).name()};
                background-color: {accent_color.name()};
                border-radius: 2px;
            }}
            QProgressBar {{
                border: 1px solid {palette.color(QPalette.ColorRole.Button).darker(120).name()};
                border-radius: 3px;
                text-align: center;
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                color: {palette.color(QPalette.ColorRole.Text).name()};
            }}
            QProgressBar::chunk {{
                background-color: {accent_color.name()};
            }}

            QScrollBar:vertical {{
                border: none;
                background: {palette.color(QPalette.ColorRole.Window).name()};
                width: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {palette.color(QPalette.ColorRole.Button).lighter(130).name()};
                min-height: 20px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: {palette.color(QPalette.ColorRole.Window).name()};
                height: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {palette.color(QPalette.ColorRole.Button).lighter(130).name()};
                min-width: 20px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            QToolTip {{
                border: 1px solid {accent_color.name()};
                background-color: {palette.color(QPalette.ColorRole.ToolTipBase).name()};
                color: {palette.color(QPalette.ColorRole.ToolTipText).name()};
                padding: 2px;
            }}
        """)


    def apply_white_style(self):
        """Applies a bright/white theme style."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(230, 230, 230))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(50, 50, 50))
        palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Button, QColor(225, 225, 225))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(0, 0, 238))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(100, 100, 100))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(120, 120, 120))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(120, 120, 120))
        accent_color = QColor(0, 120, 215) # Blue

        self.setPalette(palette)

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {palette.color(QPalette.ColorRole.Window).name()};
                color: {palette.color(QPalette.ColorRole.WindowText).name()};
            }}
            QWidget {{
                color: {palette.color(QPalette.ColorRole.Text).name()};
                outline: none;
            }}
            QTabWidget::pane {{
                border: 1px solid #DCDCDC;
                background-color: {palette.color(QPalette.ColorRole.Window).name()};
            }}
            QTabWidget::tab-bar {{
                left: 5px;
            }}
            QTabBar::tab {{
                background: {palette.color(QPalette.ColorRole.Button).name()};
                color: {palette.color(QPalette.ColorRole.ButtonText).name()};
                border: 1px solid #DCDCDC;
                border-bottom-color: #DCDCDC;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 5px 10px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {palette.color(QPalette.ColorRole.Base).name()};
                border-color: #DCDCDC;
                border-bottom-color: {palette.color(QPalette.ColorRole.Base).name()};
            }}
            QTabBar::tab:hover {{
                background: {palette.color(QPalette.ColorRole.Button).darker(105).name()};
            }}

            QScrollArea > QWidget > QWidget {{
                background-color: {palette.color(QPalette.ColorRole.Window).name()};
            }}

            QGroupBox {{
                border: 1px solid #DCDCDC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: {accent_color.darker(120).name()};
                font-weight: bold;
            }}

            QLineEdit, QTextEdit, QComboBox, QListWidget, QSpinBox {{
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                color: {palette.color(QPalette.ColorRole.Text).name()};
                border: 1px solid #CCCCCC;
                border-radius: 3px;
                padding: 3px;
                selection-background-color: {palette.color(QPalette.ColorRole.Highlight).name()};
                selection-color: {palette.color(QPalette.ColorRole.HighlightedText).name()};
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border: 1px solid {accent_color.name()};
            }}
            QTextEdit {{
                padding: 5px;
            }}
            QComboBox {{
                padding-right: 20px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 15px;
                border-left-width: 1px;
                border-left-color: #CCCCCC;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                color: {palette.color(QPalette.ColorRole.Text).name()};
                selection-background-color: {palette.color(QPalette.ColorRole.Highlight).name()};
                selection-color: {palette.color(QPalette.ColorRole.HighlightedText).name()};
                border: 1px solid #CCCCCC;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 5px;
            }}

            QPushButton {{
                background-color: {palette.color(QPalette.ColorRole.Button).name()};
                color: {palette.color(QPalette.ColorRole.ButtonText).name()};
                border: 1px solid #BBBBBB;
                padding: 5px 15px;
                border-radius: 3px;
                font-weight: bold;
            }}
            QPushButton#downloadButton, QPushButton#pasteAndAddButton {{
                background-color: {accent_color.name()};
                color: #FFFFFF;
                border: 1px solid {accent_color.darker(120).name()};
            }}
            QPushButton:hover {{ background-color: {palette.color(QPalette.ColorRole.Button).darker(110).name()}; }}
            QPushButton#downloadButton:hover, QPushButton#pasteAndAddButton:hover {{ background-color: {accent_color.lighter(120).name()}; }}
            QPushButton:pressed {{ background-color: {palette.color(QPalette.ColorRole.Button).darker(120).name()}; }}
            QPushButton#downloadButton:pressed, QPushButton#pasteAndAddButton:pressed {{ background-color: {accent_color.darker(120).name()}; }}
            QPushButton:disabled {{
                background-color: {palette.color(QPalette.ColorRole.Button).name()};
                color: {palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name()};
            }}

            QCheckBox {{
                color: {palette.color(QPalette.ColorRole.Text).name()};
                spacing: 5px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 1px solid #BBBBBB;
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                border-radius: 2px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 1px solid {accent_color.name()};
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid {accent_color.darker(120).name()};
                background-color: {accent_color.name()};
                border-radius: 2px;
            }}

            QProgressBar {{
                border: 1px solid #BBBBBB;
                border-radius: 3px;
                text-align: center;
                background-color: {palette.color(QPalette.ColorRole.Base).name()};
                color: {palette.color(QPalette.ColorRole.Text).name()};
            }}
            QProgressBar::chunk {{
                background-color: {accent_color.name()};
            }}

            QScrollBar:vertical {{
                border: none;
                background: {palette.color(QPalette.ColorRole.Window).name()};
                width: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #CCCCCC;
                min-height: 20px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: {palette.color(QPalette.ColorRole.Window).name()};
                height: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: #CCCCCC;
                min-width: 20px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
            QToolTip {{
                border: 1px solid {accent_color.darker(120).name()};
                background-color: {palette.color(QPalette.ColorRole.ToolTipBase).name()};
                color: {palette.color(QPalette.ColorRole.ToolTipText).name()};
                padding: 2px;
            }}
        """)


    def get_user_downloads_path(self):
        """Gets the path to the user's Downloads folder."""
        try:
            downloads_path = Path.home() / "Downloads"
            if downloads_path.exists():
                return str(downloads_path)
            else:
                logger.warning(f"Katalog Pobrane nie istnieje pod standardową ścieżką: {downloads_path}. Używam katalogu domowego.")
                return str(Path.home())
        except Exception as e:
            logger.error(f"Nie udało się uzyskać ścieżki katalogu Pobrane: {e}")
            return str(Path.home())

    def get_ytdlp_path(self):
        """Returns the path to youtube-dlp.exe from settings or default fallback."""
        settings_path = self.settings.value("ytdlp_path", "", type=str).strip()
        if settings_path:
            logger.debug(f"Używam ścieżki yt-dlp z ustawień: {settings_path}")
            return settings_path
        logger.debug(f"Używam domyślnej lokalnej ścieżki/systemowej yt-dlp: {self.default_ytdlp_path_fallback}")
        return self.default_ytdlp_path_fallback

    def get_ffmpeg_path(self):
        """Returns the path to ffmpeg.exe from settings or default fallback."""
        settings_path = self.settings.value("ffmpeg_path", "", type=str).strip()
        if settings_path:
            logger.debug(f"Używam ścieżki FFmpeg z ustawień: {settings_path}")
            return settings_path
        logger.debug(f"Używam domyślnej lokalnej ścieżki/systemowej FFmpeg: {self.default_ffmpeg_path_local_fallback}")
        return self.default_ffmpeg_path_local_fallback


    def check_ytdlp_version(self):
        """Sprawdza i pobiera yt-dlp przy starcie."""
        logger.info("Rozpoczynam sprawdzanie wersji yt-dlp")
        current_ytdlp_path_to_check = self.ytdlp_path_input.text().strip()
        self.update_ytdlp_thread = UpdateYTDLPThread(current_ytdlp_path_to_check, self, parent=self)
        self.update_ytdlp_thread.finished_signal.connect(self.handle_ytdlp_update)
        self.update_ytdlp_thread.progress_signal.connect(self.update_progress)
        self.update_ytdlp_thread.start()
        self.pending_queue_check = True
        logger.info("Ustawiono pending_queue_check na True podczas sprawdzania yt-dlp")


    def handle_ytdlp_update(self, success, message):
        self.output_text.append(message)
        logger.info(f"Aktualizacja/Sprawdzenie yt-dlp zakończone: {success}, {message}")
        self.ytdlp_path_input.setText(self.get_ytdlp_path())
        self.check_ffmpeg_present_or_download()


    def check_ffmpeg_present_or_download(self):
        """Checks for FFmpeg and downloads if necessary."""
        logger.info("Rozpoczynam sprawdzanie obecności FFmpeg")
        current_ffmpeg_path_to_check = self.ffmpeg_path.text().strip()
        self.download_ffmpeg_thread = DownloadFFmpegThread(current_ffmpeg_path_to_check, self, parent=self)
        self.download_ffmpeg_thread.finished_signal.connect(self.handle_ffmpeg_download)
        self.download_ffmpeg_thread.progress_signal.connect(self.update_progress)
        self.download_ffmpeg_thread.start()


    def handle_ffmpeg_download(self, success, message):
        self.output_text.append(message)
        logger.info(f"Pobieranie/Sprawdzenie FFmpeg zakończone: {success}, {message}")
        self.ffmpeg_path.setText(self.get_ffmpeg_path())

        self.dependency_checks_finished()


    def dependency_checks_finished(self):
        """Called when all dependency checks/downloads are complete."""
        self.setEnabled(True)
        self.output_text.append("Sprawdzanie zależności zakończone.")
        logger.info("Dependency checks finished. GUI enabled.")
        if self.pending_queue_check:
            logger.info("Performing pending queue check.")
            self.ask_resume_queue()
            self.pending_queue_check = False
        else:
            logger.debug("No pending queue check needed.")


    def init_ui(self):
        # Ustaw ikonę głównego okna
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setWindowTitle('Video Downloader')
        self.setGeometry(100, 100, 900, 700)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        url_group = QGroupBox("URL wideo/playlisty")
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Wprowadź URL YouTube, CDA lub playlisty...")
        self.url_input.setToolTip("Wprowadź adres URL pojedynczego wideo lub playlisty z obsługiwanej strony (np. YouTube, CDA).")
        url_layout.addWidget(self.url_input, 4)

        style = self.style()
        if not style:
            logger.warning("Could not retrieve widget style. Icons will not be set.")
            return

        paste_btn = QPushButton(" Wklej")
        paste_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        paste_btn.clicked.connect(self.paste_from_clipboard)
        paste_btn.setToolTip("Wkleja adres URL ze schowka systemowego do pola powyżej.")
        url_layout.addWidget(paste_btn, 1)

        paste_and_add_btn = QPushButton(" Wklej i Dodaj")
        paste_and_add_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        paste_and_add_btn.setObjectName("pasteAndAddButton")
        paste_and_add_btn.clicked.connect(self.paste_and_add_to_queue)
        paste_and_add_btn.setToolTip("Wkleja adres URL ze schowka do pola powyżej, a następnie dodaje go do kolejki pobierania.")
        url_layout.addWidget(paste_and_add_btn, 1)

        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)
        self.tabs = QTabWidget()
        self.video_tab_widget = QWidget()
        self.audio_tab_widget = QWidget()
        self.playlist_tab_widget = QWidget()
        self.queue_tab_widget = QWidget()
        self.advanced_tab_widget = QWidget()
        self.settings_tab_widget = QWidget()

        self.init_video_tab(self.video_tab_widget)
        self.init_audio_tab(self.audio_tab_widget)
        self.init_playlist_tab(self.playlist_tab_widget)
        self.init_queue_tab(self.queue_tab_widget)
        self.init_advanced_tab(self.advanced_tab_widget)
        self.init_settings_tab(self.settings_tab_widget)

        self.tabs.addTab(self.video_tab_widget, "Wideo")
        self.tabs.addTab(self.audio_tab_widget, "Audio")
        self.tabs.addTab(self.playlist_tab_widget, "Playlista")
        self.tabs.addTab(self.queue_tab_widget, "Kolejka")
        self.tabs.addTab(self.advanced_tab_widget, "Zaawansowane")
        self.tabs.addTab(self.settings_tab_widget, "Ustawienia")

        main_layout.addWidget(self.tabs)
        output_group = QGroupBox("Wyjście i postęp")
        output_layout = QVBoxLayout()

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.output_text.setToolTip("Wyświetla logi i postęp pobierania z programu yt-dlp.")
        font = QFont("Courier New", 9)
        self.output_text.setFont(font)
        output_layout.addWidget(self.output_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setToolTip("Wyświetla postęp bieżącego pobierania.")
        output_layout.addWidget(self.progress_bar)

        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        button_layout = QHBoxLayout()

        self.download_btn = QPushButton("Pobierz i rozpocznij kolejkę")
        self.download_btn.setObjectName("downloadButton")
        self.download_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setToolTip("Dodaje URL z pola wejściowego (jeśli nie jest puste) do kolejki, a następnie rozpoczyna pobieranie wszystkich elementów z kolejki po kolei.")
        button_layout.addWidget(self.download_btn)

        self.stop_btn = QPushButton("Zatrzymaj pobieranie")
        self.stop_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("Zatrzymuje aktualnie trwające pobieranie.")
        button_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("Wyczyść konsolę")
        self.clear_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        self.clear_btn.clicked.connect(self.clear_output)
        self.clear_btn.setToolTip("Czyści okno wyjścia i resetuje pasek postępu.")
        button_layout.addWidget(self.clear_btn)

        main_layout.addLayout(button_layout)

    def init_video_tab(self, tab_widget):
        layout = QVBoxLayout(tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)

        format_group = QGroupBox("Format wideo")
        format_group.setToolTip("Ustawienia dotyczące formatu i jakości pobieranego pliku wideo.")
        format_layout = QFormLayout()

        self.video_format = QComboBox()
        self.video_format.addItems(["mp4", "webm", "mkv", "flv", "avi"])
        self.video_format.setToolTip("Wybierz format kontenera dla pliku wideo. Wymaga FFmpeg.")
        format_layout.addRow("Format kontenera:", self.video_format)

        self.video_quality = QComboBox()
        self.video_quality.addItems([
            "Najlepsze (auto)", "2160p (4K)", "1440p (2K)", "1080p", "720p", "480p", "360p", "240p", "144p"
        ])
        self.video_quality.setToolTip("Wybierz preferowaną jakość wideo.")
        format_layout.addRow("Jakość:", self.video_quality)

        self.video_codec = QComboBox()
        self.video_codec.addItems(["auto", "h264", "h265", "vp9", "av1"])
        self.video_codec.setToolTip("Wybierz preferowany kodek wideo. 'auto' wybierze najlepszy dostępny. Może wymagać rekodowania i FFmpeg.")
        format_layout.addRow("Kodek wideo:", self.video_codec)

        self.embed_thumbnails = QCheckBox("Osadź miniaturkę")
        self.embed_thumbnails.setToolTip("Osadza miniaturkę wideo w pliku wyjściowym (jeśli format kontenera na to pozwala). Wymaga FFmpeg.")
        self.embed_thumbnails.setChecked(True)
        format_layout.addRow(self.embed_thumbnails)

        self.embed_subs = QCheckBox("Osadź napisy")
        self.embed_subs.setToolTip("Osadza napisy (jeśli dostępne) w pliku wyjściowym. Wymaga FFmpeg.")
        format_layout.addRow(self.embed_subs)

        format_group.setLayout(format_layout)
        content_layout.addWidget(format_group)

        options_group = QGroupBox("Opcje pobierania")
        options_group.setToolTip("Ogólne opcje dotyczące procesu pobierania plików.")
        options_layout = QFormLayout()

        self.output_template = QLineEdit("%(title)s.%(ext)s")
        self.output_template.setToolTip("Szablon nazwy pliku wyjściowego. %(title)s to tytuł, %(ext)s to rozszerzenie itp. Pełna lista opcji dostępna w dokumentacji yt-dlp.")
        options_layout.addRow("Szablon nazwy pliku:", self.output_template)

        self.output_path = QLineEdit()
        self.output_path.setToolTip("Katalog, do którego zostaną zapisane pobrane pliki wideo. Pozostaw puste, aby użyć domyślnej ścieżki z Ustawień.")
        browse_output_btn = QPushButton(" Przeglądaj...")
        style = self.style()
        if style:
            browse_output_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_output_btn.clicked.connect(self.browse_output_path)
        browse_output_btn.setToolTip("Wybierz katalog wyjściowy.")

        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(self.output_path)
        output_path_layout.addWidget(browse_output_btn)
        options_layout.addRow("Katalog wyjściowy:", output_path_layout)

        self.limit_rate = QLineEdit()
        self.limit_rate.setPlaceholderText("np. 50K lub 4.2M")
        self.limit_rate.setToolTip("Ogranicza maksymalną prędkość pobierania. Podaj wartość w bajtach, np. 50K, 1M, 4.2M. Pozostaw puste dla braku ograniczenia.")
        options_layout.addRow("Ograniczenie prędkości:", self.limit_rate)

        self.retries = QSpinBox()
        self.retries.setRange(0, 99)
        self.retries.setValue(10)
        self.retries.setToolTip("Liczba prób ponowienia pobierania w przypadku błędu sieciowego.")
        options_layout.addRow("Liczba prób:", self.retries)

        options_group.setLayout(options_layout)
        content_layout.addWidget(options_group)

        extra_group = QGroupBox("Dodatkowe opcje wideo")
        extra_group.setToolTip("Dodatkowe opcje przetwarzania dla plików wideo.")
        extra_layout = QVBoxLayout()

        self.extract_audio = QCheckBox("Wyodrębnij tylko audio")
        self.extract_audio.setToolTip("Pobiera tylko ścieżkę audio i konwertuje ją do wybranego formatu audio. Zignoruje ustawienia formatu wideo.")
        extra_layout.addWidget(self.extract_audio)

        self.keep_video = QCheckBox("Zachowaj plik wideo przy wyodrębnianiu audio")
        self.keep_video.setToolTip("Jeśli wybrano wyodrębnianie audio, ta opcja zachowa oryginalny plik wideo po ekstrakcji audio.")
        extra_layout.addWidget(self.keep_video)

        self.write_subs = QCheckBox("Zapisz napisy do pliku")
        self.write_subs.setToolTip("Pobiera dostępne napisy i zapisuje je do osobnego pliku (.srt, .vtt itp.).")
        extra_layout.addWidget(self.write_subs)

        self.write_auto_subs = QCheckBox("Zapisz automatyczne napisy")
        self.write_auto_subs.setToolTip("Pobiera automatycznie generowane napisy (np. z YouTube) i zapisuje je do osobnego pliku.")
        extra_layout.addWidget(self.write_auto_subs)

        self.write_info_json = QCheckBox("Zapisz metadane do pliku .info.json")
        self.write_info_json.setToolTip("Zapisuje wszystkie dostępne metadane o wideo/playliście do pliku w formacie JSON.")
        extra_layout.addWidget(self.write_info_json)

        extra_group.setLayout(extra_layout)
        content_layout.addWidget(extra_group)

        content_layout.addStretch()
        layout.addWidget(scroll)

    def init_audio_tab(self, tab_widget):
        layout = QVBoxLayout(tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)

        format_group = QGroupBox("Format audio")
        format_group.setToolTip("Ustawienia dotyczące formatu i jakości pobieranego pliku audio.")
        format_layout = QFormLayout()

        self.audio_format = QComboBox()
        self.audio_format.addItems(["najlepszy", "mp3", "aac", "flac", "m4a", "opus", "vorbis", "wav"])
        self.audio_format.setToolTip("Wybierz format konwersji audio. 'najlepszy' pobierze najlepsze dostępne audio bez konwersji. Wymaga FFmpeg do konwersji na inne formaty.")
        format_layout.addRow("Format:", self.audio_format)

        self.audio_quality = QComboBox()
        self.audio_quality.addItems([
            "0 (najlepsza)", "1", "2", "3", "4", "5", "6", "7", "8", "9 (najgorsza)"
        ])
        self.audio_quality.setToolTip("Wybierz jakość audio VBR (Variable Bitrate). Niższa liczba oznacza lepszą jakość. Zakres 0-9.")
        format_layout.addRow("Jakość (VBR):", self.audio_quality)

        self.add_metadata = QCheckBox("Dodaj metadane (artysta, tytuł itp.)")
        self.add_metadata.setToolTip("Dodaje metadane (tytuł, artysta, album itp.) do pobranego pliku audio. Wymaga FFmpeg.")
        self.add_metadata.setChecked(True)
        format_layout.addRow(self.add_metadata)

        self.embed_thumbnail = QCheckBox("Osadź miniaturkę w pliku audio")
        self.embed_thumbnail.setToolTip("Osadza miniaturkę w pliku audio (jeśli format na to pozwala). Wymaga FFmpeg.")
        self.embed_thumbnail.setChecked(True)
        format_layout.addRow(self.embed_thumbnail)

        format_group.setLayout(format_layout)
        content_layout.addWidget(format_group)

        options_group = QGroupBox("Opcje pobierania audio")
        options_group.setToolTip("Ogólne opcje dotyczące procesu pobierania plików audio.")
        options_layout = QFormLayout()

        self.audio_output_template = QLineEdit("%(title)s.%(ext)s")
        self.audio_output_template.setToolTip("Szablon nazwy pliku wyjściowego audio.")
        options_layout.addRow("Szablon nazwy pliku:", self.audio_output_template)

        self.audio_output_path = QLineEdit()
        self.audio_output_path.setToolTip("Katalog, do którego zostaną zapisane pobrane pliki audio. Pozostaw puste, aby użyć domyślnej ścieżki z Ustawień.")
        browse_audio_output_btn = QPushButton(" Przeglądaj...")
        style = self.style()
        if style:
            browse_audio_output_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_audio_output_btn.clicked.connect(self.browse_audio_output_path)
        browse_audio_output_btn.setToolTip("Wybierz katalog wyjściowy.")

        audio_output_path_layout = QHBoxLayout()
        audio_output_path_layout.addWidget(self.audio_output_path)
        audio_output_path_layout.addWidget(browse_audio_output_btn)
        options_layout.addRow("Katalog wyjściowy:", audio_output_path_layout)

        options_group.setLayout(options_layout)
        content_layout.addWidget(options_group)

        extract_group = QGroupBox("Opcje ekstrakcji audio")
        extract_group.setToolTip("Dodatkowe opcje dotyczące wyodrębniania audio.")
        extract_layout = QVBoxLayout()

        self.prefer_ffmpeg = QCheckBox("Preferuj ffmpeg do scalania/konwersji")
        self.prefer_ffmpeg.setToolTip("Wymusza użycie FFmpeg do wszystkich operacji scalania i konwersji (domyślnie yt-dlp może używać innych narzędzi lub metod). Wymaga FFmpeg.")
        extract_layout.addWidget(self.prefer_ffmpeg)

        extract_group.setLayout(extract_layout)
        content_layout.addWidget(extract_group)

        content_layout.addStretch()
        layout.addWidget(scroll)

    def init_playlist_tab(self, tab_widget):
        layout = QVBoxLayout(tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)


        playlist_group = QGroupBox("Opcje playlisty")
        playlist_group.setToolTip("Ustawienia dotyczące pobierania playlist.")
        playlist_layout = QFormLayout()

        self.playlist_start = QSpinBox()
        self.playlist_start.setRange(1, 9999)
        self.playlist_start.setToolTip("Określa, od którego elementu (numeracja od 1) rozpocząć pobieranie z playlisty.")
        playlist_layout.addRow("Rozpocznij od filmu:", self.playlist_start)

        self.playlist_end = QSpinBox()
        self.playlist_end.setRange(0, 9999)
        self.playlist_end.setSpecialValueText("Koniec")
        self.playlist_end.setToolTip("Określa, na którym elemencie (numeracja od 1) zakończyć pobieranie z playlisty. 0 oznacza do końca.")
        playlist_layout.addRow("Zakończ na filmie:", self.playlist_end)

        self.playlist_items = QLineEdit()
        self.playlist_items.setPlaceholderText("np. 1,3,5-8 lub 1-3,7 (przecinki i myślniki)")
        self.playlist_items.setToolTip("Pobiera tylko określone elementy z playlisty. Można podawać pojedyncze numery oddzielone przecinkami lub zakresy z myślnikami.")
        playlist_layout.addRow("Konkretne pozycje:", self.playlist_items)

        self.playlist_reverse = QCheckBox("Pobierz w odwrotnej kolejności")
        self.playlist_reverse.setToolTip("Pobiera elementy playlisty zaczynając od ostatniego do pierwszego.")
        playlist_layout.addRow(self.playlist_reverse)

        self.playlist_random = QCheckBox("Pobierz w losowej kolejności")
        self.playlist_random.setToolTip("Pobiera elementy playlisty w losowej kolejności.")
        playlist_layout.addRow(self.playlist_random)

        playlist_group.setLayout(playlist_layout)
        content_layout.addWidget(playlist_group)

        archive_group = QGroupBox("Opcje archiwum")
        archive_group.setToolTip("Opcje użycia pliku archiwum w celu pominięcia już pobranych elementów (przydatne przy wznawianiu pobierania dużych playlist).")
        archive_layout = QVBoxLayout()

        self.use_archive = QCheckBox("Użyj pliku archiwum (pomiń pobrane wcześniej)")
        self.use_archive.setToolTip("Włącza użycie pliku archiwum. yt-dlp zapisuje identyfikator każdego pobranego filmu do tego pliku i pomija je w przyszłości.")
        archive_layout.addWidget(self.use_archive)

        self.archive_file = QLineEdit()
        self.archive_file.setPlaceholderText("Ścieżka do pliku archiwum (domyślnie: archive.txt w katalogu aplikacji)")
        self.archive_file.setToolTip("Ścieżka do pliku tekstowego archiwum. Każda linia to identyfikator już pobranego wideo. Pozostaw puste, aby użyć domyślnego pliku w katalogu aplikacji.")
        browse_archive_btn = QPushButton(" Przeglądaj...")
        style = self.style()
        if style:
            browse_archive_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_archive_btn.clicked.connect(self.browse_archive_file)
        browse_archive_btn.setToolTip("Wybierz lokalizację pliku archiwum.")

        archive_file_layout = QHBoxLayout()
        archive_file_layout.addWidget(self.archive_file)
        archive_file_layout.addWidget(browse_archive_btn)
        archive_layout.addLayout(archive_file_layout)

        archive_group.setLayout(archive_layout)
        content_layout.addWidget(archive_group)

        content_layout.addStretch()
        layout.addWidget(scroll)

    def init_queue_tab(self, tab_widget):
        layout = QVBoxLayout(tab_widget)

        queue_group = QGroupBox("Kolejka pobierania")
        queue_group.setToolTip("Zarządzanie listą adresów URL oczekujących na pobranie.")
        queue_layout = QVBoxLayout()

        self.queue_list = QListWidget()
        self.queue_list.setToolTip("Lista adresów URL w kolejce pobierania. Program pobierze je po kolei.")
        self.queue_list.itemSelectionChanged.connect(self.update_remove_btn_state)
        queue_layout.addWidget(self.queue_list)

        buttons_layout = QHBoxLayout()
        style = self.style()
        if not style: return

        add_btn = QPushButton(" Dodaj URL")
        add_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        add_btn.clicked.connect(self.add_to_queue)
        add_btn.setToolTip("Dodaje adres URL z pola wejściowego u góry okna do kolejki.")
        buttons_layout.addWidget(add_btn)

        self.remove_btn = QPushButton(" Usuń")
        self.remove_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.remove_btn.clicked.connect(self.remove_from_queue)
        self.remove_btn.setToolTip("Usuwa wybrany adres URL z kolejki.")
        self.remove_btn.setEnabled(False)
        buttons_layout.addWidget(self.remove_btn)

        up_btn = QPushButton(" W górę")
        up_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        up_btn.clicked.connect(self.move_queue_item_up)
        up_btn.setToolTip("Przesuwa wybrany adres URL w górę kolejki (wyższy priorytet).")
        buttons_layout.addWidget(up_btn)

        down_btn = QPushButton(" W dół")
        down_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        down_btn.clicked.connect(self.move_queue_item_down)
        down_btn.setToolTip("Przesuwa wybrany adres URL w dół kolejki (niższy priorytet).")
        buttons_layout.addWidget(down_btn)

        self.edit_btn = QPushButton(" Edytuj")
        self.edit_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.edit_btn.clicked.connect(self.edit_queue_item)
        self.edit_btn.setToolTip("Edytuje wybrany adres URL w kolejce.")
        self.edit_btn.setEnabled(False)
        buttons_layout.addWidget(self.edit_btn)

        clear_queue_btn = QPushButton(" Wyczyść")
        clear_queue_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        clear_queue_btn.clicked.connect(self.clear_queue)
        clear_queue_btn.setToolTip("Usuwa wszystkie adresy URL z kolejki.")
        buttons_layout.addWidget(clear_queue_btn)

        queue_layout.addLayout(buttons_layout)
        queue_group.setLayout(queue_layout)
        layout.addWidget(queue_group)

        layout.addStretch()

    def init_advanced_tab(self, tab_widget):
        layout = QVBoxLayout(tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        advanced_layout = QVBoxLayout(content)

        network_group = QGroupBox("Opcje sieciowe")
        network_group.setToolTip("Zaawansowane opcje dotyczące połączenia sieciowego.")
        network_layout = QFormLayout()

        self.proxy = QLineEdit()
        self.proxy.setPlaceholderText("np. socks5://user:pass@127.0.0.1:1080/")
        self.proxy.setToolTip("Użyj określonego proxy. Format np. http://IP:PORT, socks5://user:pass@IP:PORT.")
        network_layout.addRow("Proxy:", self.proxy)

        self.source_address = QLineEdit()
        self.source_address.setPlaceholderText("np. 192.168.0.1")
        self.source_address.setToolTip("Powiąż wychodzące połączenia z konkretnym adresem IP interfejsu sieciowego.")
        network_layout.addRow("Adres źródłowy:", self.source_address)

        self.force_ipv4 = QCheckBox("Wymuś IPv4")
        self.force_ipv4.setToolTip("Wymusza połączenie przez IPv4.")
        network_layout.addRow(self.force_ipv4)

        self.force_ipv6 = QCheckBox("Wymuś IPv6")
        self.force_ipv6.setToolTip("Wymusza połączenie przez IPv6.")
        network_layout.addRow(self.force_ipv6)

        network_group.setLayout(network_layout)
        advanced_layout.addWidget(network_group)

        auth_group = QGroupBox("Uwierzytelnianie (inne niż CDA)")
        auth_group.setToolTip("Ustawienia uwierzytelniania dla stron wymagających logowania (nie dla CDA Premium, które ma własne pola w Ustawieniach).")
        auth_layout = QFormLayout()

        self.username = QLineEdit()
        self.username.setToolTip("Nazwa użytkownika do logowania na stronie hostującej wideo.")
        auth_layout.addRow("Nazwa użytkownika:", self.username)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setToolTip("Hasło do logowania na stronie hostującej wideo.")
        self.password_show_btn = QPushButton()
        self.password_show_btn.setIcon(QIcon("icons/eye.png"))
        self.password_show_btn.setFixedSize(QSize(30, 24))
        self.password_show_btn.setCheckable(True)
        self.password_show_btn.toggled.connect(self.toggle_password_visibility)
        self.password_show_btn.setToolTip("Pokaż/ukryj hasło.")
        password_layout = QHBoxLayout()
        password_layout.addWidget(self.password)
        password_layout.addWidget(self.password_show_btn)
        auth_layout.addRow("Hasło:", password_layout)

        self.twofactor = QLineEdit()
        self.twofactor.setPlaceholderText("Kod 2FA")
        self.twofactor.setToolTip("Kod uwierzytelniania dwuskładnikowego (2FA), jeśli wymagany.")
        auth_layout.addRow("Kod 2FA:", self.twofactor)

        self.video_password = QLineEdit()
        self.video_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.video_password.setToolTip("Hasło do konkretnego wideo, jeśli jest chronione hasłem.")
        auth_layout.addRow("Hasło do wideo:", self.video_password)

        auth_group.setLayout(auth_layout)
        advanced_layout.addWidget(auth_group)

        post_group = QGroupBox("Przetwarzanie końcowe (Postprocesing)")
        post_group.setToolTip("Zaawansowane opcje dotyczące przetwarzania plików po ich pobraniu.")
        post_layout = QFormLayout()

        self.extract_audio_adv = QCheckBox("Wyodrębnij audio (zaawansowane)")
        self.extract_audio_adv.setToolTip("Wymusza wyodrębnienie audio i konwersję do wybranego formatu audio, niezależnie od ustawień na zakładce Wideo.")
        post_layout.addRow(self.extract_audio_adv)

        self.audio_format_adv = QComboBox()
        self.audio_format_adv.addItems(["najlepszy", "mp3", "aac", "flac", "m4a", "opus", "vorbis", "wav"])
        self.audio_format_adv.setToolTip("Format konwersji audio używany, gdy włączone jest 'Wyodrębnij audio (zaawansowane)'.")
        post_layout.addRow("Format audio:", self.audio_format_adv)

        self.audio_quality_adv = QComboBox()
        self.audio_quality_adv.addItems(["0 (najlepsza)", "1", "2", "3", "4", "5", "6", "7", "8", "9 (najgorsza)", "10 (najgorsza)"])
        self.audio_quality_adv.setToolTip("Jakość audio VBR używana, gdy włączone jest 'Wyodrębnij audio (zaawansowane)'. Niższa liczba = lepsza jakość.")
        post_layout.addRow("Jakość audio (VBR):", self.audio_quality_adv)

        self.keep_video_adv = QCheckBox("Zachowaj plik wideo po wyodrębnieniu (zaawansowane)")
        self.keep_video_adv.setToolTip("Zachowuje oryginalny plik wideo po wyodrębnieniu audio, niezależnie od ustawień na zakładce Wideo.")
        post_layout.addRow(self.keep_video_adv)

        self.recode_video = QComboBox()
        self.recode_video.addItems(["Nie przetwarzaj", "mp4", "flv", "ogg", "webm", "mkv", "avi", "mov", "wmv", "gif", "m4a", "mp3", "aac", "opus", "vorbis", "wav", "aiff"])
        self.recode_video.setToolTip("Rekonwertuje plik wideo (lub audio, jeśli wyodrębniono) do wybranego formatu kontenera po pobraniu. Wymaga FFmpeg.")
        post_layout.addRow("Przetwórz wideo/audio do:", self.recode_video)

        self.postprocessor_args = QLineEdit()
        self.postprocessor_args.setPlaceholderText("Dodatkowe argumenty dla postprocesora (np. --ppa \"-crf 28\")")
        self.postprocessor_args.setToolTip("Dodatkowe argumenty wiersza poleceń przekazywane do postprocesora (np. FFmpeg) przez yt-dlp. Używaj ostrożnie.")
        post_layout.addRow("Argumenty postprocesora:", self.postprocessor_args)

        post_group.setLayout(post_layout)
        advanced_layout.addWidget(post_group)

        other_group = QGroupBox("Inne opcje")
        other_group.setToolTip("Dodatkowe, ogólne opcje dla yt-dlp.")
        other_layout = QFormLayout()

        self.ignore_errors = QCheckBox("Kontynuuj przy błędach")
        self.ignore_errors.setToolTip("Kontynuuje pobieranie następnych filmów z playlisty lub listy, nawet jeśli jeden z nich zakończył się błędem.")
        other_layout.addRow(self.ignore_errors)

        self.no_warnings = QCheckBox("Wyłącz ostrzeżenia")
        self.no_warnings.setToolTip("Nie wyświetla komunikatów ostrzegawczych z yt-dlp.")
        other_layout.addRow(self.no_warnings)

        self.quiet = QCheckBox("Tryb cichy (mniej wyjścia)")
        self.quiet.setToolTip("Minimalizuje ilość informacji wyświetlanych w konsoli yt-dlp.")
        other_layout.addRow(self.quiet)

        self.no_color = QCheckBox("Wyłącz kolory w wyjściu")
        self.no_color.setToolTip("Wyłącza kolorowanie tekstu w wyjściu yt-dlp.")
        other_layout.addRow(self.no_color)

        self.simulate = QCheckBox("Symuluj (nie pobieraj plików)")
        self.simulate.setToolTip("Uruchamia yt-dlp w trybie symulacji - program pokaże, co by pobrał, ale faktycznie nie ściągnie plików.")
        other_layout.addRow(self.simulate)

        self.skip_download = QCheckBox("Pomiń pobieranie (tylko informacje)")
        self.skip_download.setToolTip("Pobiera i wyświetla tylko informacje o wideo/playliście, bez faktycznego pobierania plików. Przydatne np. z opcją --write-info-json.")
        other_layout.addRow(self.skip_download)

        other_group.setLayout(other_layout)
        advanced_layout.addWidget(other_group)

        advanced_layout.addStretch()
        layout.addWidget(scroll)


    def init_settings_tab(self, tab_widget):
        layout = QVBoxLayout(tab_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        settings_layout = QVBoxLayout(content)

        style = self.style()
        if not style: return

        ytdlp_group = QGroupBox("Konfiguracja narzędzi")
        ytdlp_group.setToolTip("Ścieżki do zewnętrznych programów: yt-dlp i FFmpeg.")
        ytdlp_layout = QFormLayout()
        self.ytdlp_path_input = QLineEdit(self.get_ytdlp_path())
        self.ytdlp_path_input.setPlaceholderText(f"Domyślnie: {YTDLP_PATH_WINDOWS} (Windows) lub 'yt-dlp' (PATH)")
        self.ytdlp_path_input.setToolTip("Pełna ścieżka do pliku wykonywalnego yt-dlp (np. youtube-dlp.exe). Pozostaw puste, aby program próbował znaleźć 'yt-dlp' w ścieżce systemowej (PATH).")
        browse_ytdlp_btn = QPushButton(" Przeglądaj...")
        browse_ytdlp_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_ytdlp_btn.clicked.connect(self.browse_ytdlp_path)
        browse_ytdlp_btn.setToolTip("Wybierz lokalizację pliku yt-dlp.")

        ytdlp_path_layout = QHBoxLayout()
        ytdlp_path_layout.addWidget(self.ytdlp_path_input)
        ytdlp_path_layout.addWidget(browse_ytdlp_btn)
        ytdlp_layout.addRow("Ścieżka do YT-DLP:", ytdlp_path_layout)
        self.ffmpeg_path = QLineEdit(self.get_ffmpeg_path())
        self.ffmpeg_path.setPlaceholderText(f"Domyślnie: {FFMPEG_PATH_WINDOWS} (Windows) lub 'ffmpeg' (PATH)")
        self.ffmpeg_path.setToolTip("Pełna ścieżka do pliku wykonywalnego FFmpeg (ffmpeg.exe). FFmpeg jest wymagany do scalania wideo/audio, rekodowania, osadzania miniatur i metadanych. Pozostaw puste, aby program próbował znaleźć 'ffmpeg' w ścieżce systemowej (PATH).")
        browse_ffmpeg_btn = QPushButton(" Przeglądaj...")
        browse_ffmpeg_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_ffmpeg_btn.clicked.connect(self.browse_ffmpeg_path)
        browse_ffmpeg_btn.setToolTip("Wybierz lokalizację pliku FFmpeg.")

        ffmpeg_path_layout = QHBoxLayout()
        ffmpeg_path_layout.addWidget(self.ffmpeg_path)
        ffmpeg_path_layout.addWidget(browse_ffmpeg_btn)
        ytdlp_layout.addRow("Ścieżka do FFmpeg:", ffmpeg_path_layout)

        self.check_ytdlp_updates = QCheckBox("Sprawdzaj aktualizacje YT-DLP przy starcie")
        self.check_ytdlp_updates.setToolTip("Włącza automatyczne sprawdzanie i pobieranie najnowszej wersji yt-dlp z GitHub przy każdym uruchomieniu aplikacji.")
        ytdlp_layout.addRow(self.check_ytdlp_updates)

        self.auto_download_ffmpeg = QCheckBox("Automatycznie pobieraj FFmpeg jeśli brak (tylko Windows)")
        self.auto_download_ffmpeg.setToolTip(f"Włącza automatyczne pobieranie FFmpeg (wersja Essentials 64-bit) do domyślnej lokalizacji ({FFMPEG_BIN_DIR}) jeśli nie zostanie znaleziony. Działa tylko w systemie Windows.")
        self.auto_download_ffmpeg.setChecked(os.name == 'nt')
        self.auto_download_ffmpeg.setEnabled(os.name == 'nt')
        if os.name != 'nt':
            self.auto_download_ffmpeg.setToolTip("Automatyczne pobieranie FFmpeg jest obecnie obsługiwane tylko na Windows.")
        ytdlp_layout.addRow(self.auto_download_ffmpeg)

        ytdlp_group.setLayout(ytdlp_layout)
        settings_layout.addWidget(ytdlp_group)


        cda_group = QGroupBox("CDA Premium")
        cda_group.setToolTip("Ustawienia konta CDA Premium. Wymagane do pobierania filmów i playlist premium.")
        cda_layout = QFormLayout()

        self.cda_email = QLineEdit()
        self.cda_email.setPlaceholderText("twoj@email.com")
        self.cda_email.setToolTip("Adres email Twojego konta CDA Premium.")
        cda_layout.addRow("Email:", self.cda_email)

        self.cda_password = QLineEdit()
        self.cda_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.cda_password.setToolTip("Hasło do Twojego konta CDA Premium. Zapisywane w pliku ustawień.")
        self.cda_password_show_btn = QPushButton()
        self.cda_password_show_btn.setIcon(QIcon("icons/eye.png"))
        self.cda_password_show_btn.setFixedSize(QSize(30, 24))
        self.cda_password_show_btn.setCheckable(True)
        self.cda_password_show_btn.toggled.connect(self.toggle_cda_password_visibility)
        self.cda_password_show_btn.setToolTip("Pokaż/ukryj hasło.")
        cda_password_layout = QHBoxLayout()
        cda_password_layout.addWidget(self.cda_password)
        cda_password_layout.addWidget(self.cda_password_show_btn)
        cda_layout.addRow("Hasło:", cda_password_layout)

        cda_status_layout = QHBoxLayout()
        self.cda_status_label = QLabel("Status: Nie sprawdzono")
        self.cda_status_label.setToolTip("Status logowania do serwisu CDA Premium.")
        self.check_cda_status_btn = QPushButton("Sprawdź status")
        self.check_cda_status_btn.setToolTip("Weryfikuje podane dane logowania CDA Premium.")
        self.check_cda_status_btn.clicked.connect(self.run_cda_status_check)

        cda_status_layout.addWidget(self.cda_status_label)
        cda_status_layout.addStretch()
        cda_status_layout.addWidget(self.check_cda_status_btn)
        cda_layout.addRow(cda_status_layout)

        cda_group.setLayout(cda_layout)
        settings_layout.addWidget(cda_group)


        defaults_group = QGroupBox("Domyślne ustawienia ogólne")
        defaults_group.setToolTip("Ustawienia domyślne dla wszystkich typów pobierania.")
        defaults_layout = QFormLayout()

        self.default_output_path = QLineEdit()
        self.default_output_path.setToolTip(f"Domyślny katalog, do którego będą zapisywane pliki, jeśli na zakładkach Wideo/Audio nie podano inaczej. Domyślnie folder 'Pobrane' użytkownika.")
        browse_default_output_btn = QPushButton(" Przeglądaj...")
        browse_default_output_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_default_output_btn.clicked.connect(self.browse_default_output_path)
        browse_default_output_btn.setToolTip("Wybierz domyślny katalog wyjściowy.")

        default_output_layout = QHBoxLayout()
        default_output_layout.addWidget(self.default_output_path)
        default_output_layout.addWidget(browse_default_output_btn)
        defaults_layout.addRow("Domyślna ścieżka wyjściowa:", default_output_layout)

        self.default_template = QLineEdit("%(title)s.%(ext)s")
        self.default_template.setToolTip("Domyślny szablon nazwy pliku dla wszystkich typów pobierania, jeśli na zakładkach Wideo/Audio nie podano inaczej.")
        defaults_layout.addRow("Domyślny szablon nazwy:", self.default_template)

        self.auto_add_to_queue = QCheckBox("Automatycznie dodawaj wklejone URL-e do kolejki")
        self.auto_add_to_queue.setToolTip("Jeśli zaznaczone, wklejenie tekstu ze schowka do pola URL (np. Ctrl+V) spowoduje automatyczne dodanie go do kolejki, zamiast tylko wypełnić pole URL. Przycisk 'Wklej ze schowka' nadal tylko wkleja.")
        defaults_layout.addRow(self.auto_add_to_queue)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "White"])
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.theme_combo.setToolTip("Wybierz motyw wizualny interfejsu użytkownika.")
        defaults_layout.addRow("Motyw GUI:", self.theme_combo)


        defaults_group.setLayout(defaults_layout)
        settings_layout.addWidget(defaults_group)


        settings_buttons = QHBoxLayout()

        save_btn = QPushButton(" Zapisz ustawienia")
        save_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_btn.clicked.connect(self.save_settings)
        save_btn.setToolTip("Zapisuje wszystkie ustawienia do pliku.")
        settings_buttons.addWidget(save_btn)

        load_btn = QPushButton(" Wczytaj ustawienia")
        load_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        load_btn.clicked.connect(lambda: self.load_settings(initial=False))
        load_btn.setToolTip("Wczytuje ustawienia z pliku, zastępując obecne wartości.")
        settings_buttons.addWidget(load_btn)

        reset_btn = QPushButton(" Przywróć domyślne")
        reset_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        reset_btn.clicked.connect(self.reset_settings)
        reset_btn.setToolTip("Usuwa wszystkie zapisane ustawienia i przywraca wartości domyślne.")
        settings_buttons.addWidget(reset_btn)

        settings_layout.addLayout(settings_buttons)
        settings_layout.addStretch()
        layout.addWidget(scroll)


    def change_theme(self, index):
        """Slot to change the GUI theme."""
        theme_name = self.theme_combo.currentText()
        self.settings.setValue("theme", theme_name)
        self.apply_style()
        logger.info(f"Zmieniono motyw na: {theme_name}")


    def toggle_password_visibility(self, checked):
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        if checked:
            self.password_show_btn.setIcon(QIcon("icons/eye-off.png"))
        else:
            self.password_show_btn.setIcon(QIcon("icons/eye.png"))
        self.password.setFocus()

    def toggle_cda_password_visibility(self, checked):
        self.cda_password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        if checked:
            self.cda_password_show_btn.setIcon(QIcon("icons/eye-off.png"))
        else:
            self.cda_password_show_btn.setIcon(QIcon("icons/eye.png"))
        self.cda_password.setFocus()

    def run_cda_status_check(self):
        if self.cda_check_thread and self.cda_check_thread.isRunning():
            return

        ytdlp_path = self.get_ytdlp_path()
        if ytdlp_path != 'yt-dlp' and not Path(ytdlp_path).exists():
            self.cda_status_label.setText(f"<font color='red'>Status: Błąd - Nie znaleziono yt-dlp</font>")
            QMessageBox.critical(self, "Błąd YT-DLP", f"Plik YT-DLP nie został znaleziony w '{ytdlp_path}'.")
            return

        email = self.cda_email.text().strip()
        password = self.cda_password.text()

        if not email or not password:
            QMessageBox.warning(self, "Brak danych", "Wprowadź email i hasło CDA Premium.")
            return

        self.check_cda_status_btn.setEnabled(False)
        self.cda_status_label.setText("Status: Sprawdzanie...")

        self.cda_check_thread = CDAStatusCheckThread(email, password, ytdlp_path, self, self)
        self.cda_check_thread.finished_signal.connect(self.handle_cda_status_result)
        self.cda_check_thread.start()

    def handle_cda_status_result(self, success, message):
        if success:
            self.cda_status_label.setText(f"<font color='green'><b>Status: {message}</b></font>")
        else:
            self.cda_status_label.setText(f"<font color='red'>Status: {message}</font>")

        self.check_cda_status_btn.setEnabled(True)
        logger.info(f"Wynik sprawdzenia statusu CDA: {success} - {message}")


    def paste_from_clipboard(self):
        try:
            if clipboard := QApplication.clipboard():
                text = clipboard.text().strip()
                if text:
                    # Walidacja i automatyczne poprawianie URL
                    url_pattern = re.compile(r"^(https?://)?([\w.-]+)\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)
                    match = url_pattern.match(text)
                    if match:
                        # Jeśli nie ma protokołu, dodaj https://
                        if not text.lower().startswith("http://") and not text.lower().startswith("https://"):
                            text = "https://" + text
                        self.url_input.setText(text)
                        logger.info(f"Wklejono ze schowka: {text}")
                        if self.auto_add_to_queue.isChecked():
                            self.add_to_queue()
                    else:
                        box = QMessageBox(QMessageBox.Icon.Warning, "Błąd", "URL wpisany w polu URL nie wygląda na poprawny.", parent=self)
                        box.setWindowIcon(QIcon(resource_path("icon.ico")))
                        box.exec()
                        return
                else:
                    box = QMessageBox(QMessageBox.Icon.Warning, "Schowek pusty", "Schowek jest pusty.", parent=self)
                    box.setWindowIcon(QIcon(resource_path("icon.ico")))
                    box.exec()
            else:
                box = QMessageBox(QMessageBox.Icon.Critical, "Błąd", "Nie udało się uzyskać dostępu do schowka.", parent=self)
                box.setWindowIcon(QIcon(resource_path("icon.ico")))
                box.exec()
        except Exception as e:
            logger.error(f"Błąd wklejania ze schowka: {e}", exc_info=True)
            box = QMessageBox(QMessageBox.Icon.Critical, "Błąd", f"Nie udało się wkleić ze schowka: {str(e)}", parent=self)
            box.setWindowIcon(QIcon(resource_path("icon.ico")))
            box.exec()

    def paste_and_add_to_queue(self):
        """Wkleja ze schowka do pola URL, a następnie dodaje URL do kolejki."""
        try:
            if clipboard := QApplication.clipboard():
                text = clipboard.text().strip()
                if text:
                    self.url_input.setText(text)
                    # Zabezpieczenie przed duplikatami
                    urls_in_queue = []
                    for i in range(self.queue_list.count()):
                        item = self.queue_list.item(i)
                        if item is not None:
                            urls_in_queue.append(item.text().strip())
                    if text in urls_in_queue:
                        box = QMessageBox(QMessageBox.Icon.Information, "Duplikat URL", f"URL już znajduje się w kolejce: {text}", parent=self)
                        box.setWindowIcon(QIcon(resource_path("icon.ico")))
                        box.exec()
                        logger.info(f"Próba dodania duplikatu URL do kolejki: {text}")
                        return
                    self.add_to_queue()
                    logger.info(f"Wklejono i dodano do kolejki: {text}")
                else:
                    box = QMessageBox(QMessageBox.Icon.Warning, "Schowek pusty", "Schowek jest pusty.", parent=self)
                    box.setWindowIcon(QIcon(resource_path("icon.ico")))
                    box.exec()
            else:
                box = QMessageBox(QMessageBox.Icon.Critical, "Błąd", "Nie udało się uzyskać dostępu do schowka.", parent=self)
                box.setWindowIcon(QIcon(resource_path("icon.ico")))
                box.exec()
        except Exception as e:
            logger.error(f"Błąd wklejania i dodawania do kolejki: {e}", exc_info=True)
            box = QMessageBox(QMessageBox.Icon.Critical, "Błąd", f"Nie udało się wkleić i dodać do kolejki: {str(e)}", parent=self)
            box.setWindowIcon(QIcon(resource_path("icon.ico")))
            box.exec()


    def browse_output_path(self):
        start_dir = self.output_path.text().strip() or self.default_output_path.text().strip() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Wybierz katalog wyjściowy (Wideo)", start_dir)
        if directory:
            self.output_path.setText(directory)
            logger.debug(f"Wybrano katalog wyjściowy wideo: {directory}")


    def browse_audio_output_path(self):
        start_dir = self.audio_output_path.text().strip() or self.default_output_path.text().strip() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Wybierz katalog wyjściowy (Audio)", start_dir)
        if directory:
            self.audio_output_path.setText(directory)
            logger.debug(f"Wybrano katalog wyjściowy audio: {directory}")

    def browse_archive_file(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setWindowTitle("Wybierz plik archiwum")
        current_archive_path = self.archive_file.text().strip()
        if current_archive_path:
            file_dialog.selectFile(current_archive_path)
        else:
            default_path = self.appdata_dir / "archive.txt"
            file_dialog.selectFile(str(default_path))
            default_path.parent.mkdir(parents=True, exist_ok=True)


        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.archive_file.setText(selected_files[0])
                logger.debug(f"Wybrano plik archiwum: {selected_files[0]}")


    def browse_ytdlp_path(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setWindowTitle("Wybierz plik youtube-dlp")
        current_ytdlp_path = self.ytdlp_path_input.text().strip()
        start_dir = str(Path.home())
        if current_ytdlp_path and Path(current_ytdlp_path).is_absolute():
            start_dir = str(Path(current_ytdlp_path).parent) if Path(current_ytdlp_path).parent.exists() else start_dir
        elif LIBS_DIR.exists():
            start_dir = str(LIBS_DIR)

        file_dialog.setDirectory(start_dir)
        if os.name == 'nt':
            file_dialog.setNameFilter("Wykonywalne (*.exe);;Wszystkie pliki (*)")
        else:
            file_dialog.setNameFilter("Wszystkie pliki (*)")


        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.ytdlp_path_input.setText(selected_files[0])
                logger.debug(f"Wybrano ścieżkę YT-DLP: {selected_files[0]}")


    def browse_ffmpeg_path(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setWindowTitle("Wybierz plik ffmpeg")
        current_ffmpeg_path = self.ffmpeg_path.text().strip()
        start_dir = str(Path.home())
        if current_ffmpeg_path and Path(current_ffmpeg_path).is_absolute():
            start_dir = str(Path(current_ffmpeg_path).parent) if Path(current_ffmpeg_path).parent.exists() else start_dir
        elif FFMPEG_BIN_DIR.exists():
            start_dir = str(FFMPEG_BIN_DIR)
        elif LIBS_DIR.exists():
            start_dir = str(LIBS_DIR)

        file_dialog.setDirectory(start_dir)
        if os.name == 'nt':
            file_dialog.setNameFilter("Wykonywalne (*.exe);;Wszystkie pliki (*)")
        else:
            file_dialog.setNameFilter("Wszystkie pliki (*)")


        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.ffmpeg_path.setText(selected_files[0])
                logger.debug(f"Wybrano ścieżkę FFmpeg: {selected_files[0]}")


    def browse_default_output_path(self):
        start_dir = self.default_output_path.text().strip() or self.get_user_downloads_path()
        directory = QFileDialog.getExistingDirectory(self, "Wybierz domyślny katalog wyjściowy", start_dir)
        if directory:
            self.default_output_path.setText(directory)
            logger.debug(f"Wybrano domyślny katalog wyjściowy: {directory}")

    def add_to_queue(self):
        url = self.url_input.text().strip()
        if not url:
            box = QMessageBox(QMessageBox.Icon.Warning, "Błąd", "Musisz wpisać adres URL w polu URL na samej górze programu aby dodać wideo do kolejki.", parent=self)
            ok_btn = box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
            box.setDefaultButton(ok_btn)
            box.exec()
            return

        # Zabezpieczenie przed duplikatami
        urls_in_queue = [item.text().strip() for i in range(self.queue_list.count()) if (item := self.queue_list.item(i)) is not None]
        if url in urls_in_queue:
            QMessageBox.information(self, "Duplikat URL", f"URL już znajduje się w kolejce: {url}")
            logger.info(f"Próba dodania duplikatu URL do kolejki: {url}")
            return

        # Walidacja i automatyczne poprawianie URL
        import re
        url_pattern = re.compile(r"^(https?://)?([\w.-]+)\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)
        match = url_pattern.match(url)
        if match:
            # Jeśli nie ma protokołu, dodaj https://
            if not url.lower().startswith("http://") and not url.lower().startswith("https://"):
                url = "https://" + url
        else:
            box = QMessageBox(QMessageBox.Icon.Warning, "Błąd", "Podany adres URL w polu URL nie wygląda na poprawny.", parent=self)
            ok_btn = box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
            box.setDefaultButton(ok_btn)
            box.exec()
            return

        self.download_queue.append(url)
        self.queue_list.addItem(url)
        self.url_input.clear()
        logger.info(f"Dodano do kolejki: {url}")
        self.save_queue()
        self.tabs.setCurrentWidget(self.queue_tab_widget)

    def remove_from_queue(self):
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            box = QMessageBox(QMessageBox.Icon.Warning, "Błąd", "Wybierz element do usunięcia.", parent=self)
            ok_btn = box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
            box.setDefaultButton(ok_btn)
            box.exec()
            return
        indices_to_remove = sorted([self.queue_list.row(item) for item in selected_items], reverse=True)

        for index in indices_to_remove:
            if 0 <= index < len(self.download_queue):
                item_text = self.download_queue.pop(index)
                self.queue_list.takeItem(index)
                logger.info(f"Usunięto z kolejki (indeks {index}): {item_text}")
            else:
                logger.warning(f"Próba usunięcia elementu o nieprawidłowym indeksie {index} z kolejki GUI/danych.")

        self.save_queue()

    def move_queue_item_up(self):
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        index = self.queue_list.row(item)
        if index > 0:
            item_text = self.download_queue.pop(index)
            self.download_queue.insert(index - 1, item_text)
            self.queue_list.takeItem(index)
            self.queue_list.insertItem(index - 1, item_text)
            self.queue_list.setCurrentItem(self.queue_list.item(index - 1))
            logger.info(f"Przesunięto w górę element o indeksie {index} do {index-1}")
            self.save_queue()

    def move_queue_item_down(self):
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        index = self.queue_list.row(item)
        if index < self.queue_list.count() - 1:
            item_text = self.download_queue.pop(index)
            self.download_queue.insert(index + 1, item_text)
            self.queue_list.takeItem(index)
            self.queue_list.insertItem(index + 1, item_text)
            self.queue_list.setCurrentItem(self.queue_list.item(index + 1))
            logger.info(f"Przesunięto w dół element o indeksie {index} do {index+1}")
            self.save_queue()

    def edit_queue_item(self):
        selected_items = self.queue_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Błąd", "Wybierz element do edycji.")
            return
        item = selected_items[0]
        index = self.queue_list.row(item)
        current_url = item.text()
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Edytuj URL")
        dlg.setLabelText("Wprowadź nowy URL:")
        dlg.setTextValue(current_url)
        dlg.resize(500, dlg.height())  # Ustaw szersze okno
        # Zmień teksty przycisków na 'Zapisz' i 'Anuluj' (PyQt6) po wyświetleniu okna
        from PyQt6.QtWidgets import QDialogButtonBox
        from PyQt6.QtCore import QTimer
        def set_button_texts():
            button_box = dlg.findChild(QDialogButtonBox)
            if button_box:
                for btn in button_box.buttons():
                    role = button_box.buttonRole(btn)
                    if role == QDialogButtonBox.ButtonRole.AcceptRole:
                        btn.setText("Zapisz")
                    elif role == QDialogButtonBox.ButtonRole.RejectRole:
                        btn.setText("Anuluj")
        QTimer.singleShot(0, set_button_texts)
        ok = dlg.exec()
        new_url = dlg.textValue()
        if ok and new_url.strip():
            item.setText(new_url.strip())
            self.download_queue[index] = new_url.strip()
            logger.info(f"Edytowano URL o indeksie {index}: '{current_url}' -> '{new_url.strip()}'")
            self.save_queue()
        elif ok:
            box = QMessageBox(QMessageBox.Icon.Warning, "Błąd edycji", "URL nie może być pusty.", parent=self)
            ok_btn = box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
            box.setDefaultButton(ok_btn)
            box.exec()


    def clear_queue(self):
        box = QMessageBox(QMessageBox.Icon.Question, "Wyczyść kolejkę", "Czy na pewno chcesz wyczyścić kolejkę?", parent=self)
        yes_btn = box.addButton("Tak", QMessageBox.ButtonRole.YesRole)
        no_btn = box.addButton("Nie", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no_btn)
        box.exec()
        if box.clickedButton() == yes_btn:
            self.queue_list.clear()
            self.download_queue.clear()
            logger.info("Wyczyszczono kolejkę")
            self.save_queue()

    def save_queue(self):
        """Zapisuje kolejkę do pliku JSON."""
        queue_file = self.appdata_dir / "queue.json"
        try:
            queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(queue_file, "w", encoding="utf-8") as f:
                json.dump(self.download_queue, f, indent=2)
            logger.debug(f"Zapisano kolejkę ({len(self.download_queue)} elementów) do {queue_file}")
        except Exception as e:
            logger.error(f"Błąd zapisu kolejki do {queue_file}: {e}", exc_info=True)

    def load_queue(self):
        """Wczytuje kolejkę z pliku JSON."""
        queue_file = self.appdata_dir / "queue.json"
        logger.info(f"Sprawdzam plik kolejki: {queue_file}")
        if not queue_file.exists():
            logger.info("Brak pliku kolejki, pomijam wczytywanie")
            return False

        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    loaded_queue = []
                else:
                    loaded_queue = json.loads(content)

            if isinstance(loaded_queue, list):
                self.download_queue = [url.strip() for url in loaded_queue if url and url.strip()]
                self.queue_list.clear()
                for url in self.download_queue:
                    self.queue_list.addItem(url)
                logger.info(f"Wczytałem kolejkę ({len(self.download_queue)} elementów).")
                return True
            else:
                logger.info(f"Plik kolejki '{queue_file.name}' ma nieprawidłowy format (nie jest listą).")
                QMessageBox.warning(self, "Błąd wczytywania", f"Plik kolejki '{queue_file.name}' ma nieprawidłowy format.")
                self.download_queue = []
                self.queue_list.clear()
                return False

        except json.JSONDecodeError:
            logger.error(f"Błąd dekodowania JSON pliku kolejki: {queue_file}", exc_info=True)
            QMessageBox.warning(self, "Błąd wczytywania", f"Plik kolejki '{queue_file.name}' jest uszkodzony (błąd JSON).")
            self.download_queue = []
            self.queue_list.clear()
            return False
        except Exception as e:
            logger.error(f"Błąd wczytywania kolejki z {queue_file}: {e}", exc_info=True)
            QMessageBox.warning(self, "Błąd wczytywania", f"Nie udało się wczytać kolejki: {str(e)}")
            return False

    def ask_resume_queue(self):
        """Pyta użytkownika, czy kontynuować zapisaną kolejkę."""
        logger.info("Uruchamiam ask_resume_queue")
        self.load_queue()

        if self.download_queue:
            box = QMessageBox(QMessageBox.Icon.Question, "Kontynuuj kolejkę", f"Wykryto zapisaną kolejkę ({len(self.download_queue)} elementów).\nCzy chcesz kontynuować pobieranie?", parent=self)
            yes_btn = box.addButton("Tak", QMessageBox.ButtonRole.YesRole)
            no_btn = box.addButton("Nie", QMessageBox.ButtonRole.NoRole)
            box.setDefaultButton(yes_btn)
            box.exec()
            if box.clickedButton() == yes_btn:
                logger.info("Użytkownik wybrał kontynuację kolejki")
                self.tabs.setCurrentWidget(self.queue_tab_widget)
                self.start_download(add_current_url=False)
            else:
                self.clear_queue()
                logger.info("Użytkownik odrzucił kontynuację kolejki")
        else:
            logger.info("Brak kolejki do wczytania lub kolejka pusta po wczytaniu. Nic do kontynuowania.")


    def save_settings(self):
        self.settings.setValue("ytdlp_path", self.ytdlp_path_input.text().strip().replace("\\", "/"))
        self.settings.setValue("ffmpeg_path", self.ffmpeg_path.text().strip().replace("\\", "/"))
        self.settings.setValue("check_ytdlp_updates", self.check_ytdlp_updates.isChecked())
        self.settings.setValue("auto_download_ffmpeg", self.auto_download_ffmpeg.isChecked())
        self.settings.setValue("cda_email", self.cda_email.text().strip())
        self.settings.setValue("cda_password", self.cda_password.text())
        self.settings.setValue("default_output_path", self.default_output_path.text().strip())
        self.settings.setValue("default_template", self.default_template.text().strip())
        self.settings.setValue("auto_add_to_queue", self.auto_add_to_queue.isChecked())
        self.settings.setValue("theme", self.theme_combo.currentText())
        self.settings.setValue("video_format", self.video_format.currentText())
        self.settings.setValue("video_quality", self.video_quality.currentIndex())
        self.settings.setValue("video_codec", self.video_codec.currentText())
        self.settings.setValue("embed_thumbnails", self.embed_thumbnails.isChecked())
        self.settings.setValue("embed_subs", self.embed_subs.isChecked())
        self.settings.setValue("output_template", self.output_template.text().strip())
        self.settings.setValue("output_path", self.output_path.text().strip())
        self.settings.setValue("limit_rate", self.limit_rate.text().strip())
        self.settings.setValue("retries", self.retries.value())
        self.settings.setValue("extract_audio", self.extract_audio.isChecked())
        self.settings.setValue("keep_video", self.keep_video.isChecked())
        self.settings.setValue("write_subs", self.write_subs.isChecked())
        self.settings.setValue("write_auto_subs", self.write_auto_subs.isChecked())
        self.settings.setValue("write_info_json", self.write_info_json.isChecked())
        self.settings.setValue("audio_format", self.audio_format.currentText())
        self.settings.setValue("audio_quality", self.audio_quality.currentIndex())
        self.settings.setValue("add_metadata", self.add_metadata.isChecked())
        self.settings.setValue("embed_thumbnail", self.embed_thumbnail.isChecked())
        self.settings.setValue("audio_output_template", self.audio_output_template.text().strip())
        self.settings.setValue("audio_output_path", self.audio_output_path.text().strip())
        self.settings.setValue("prefer_ffmpeg", self.prefer_ffmpeg.isChecked())
        self.settings.setValue("playlist_start", self.playlist_start.value())
        self.settings.setValue("playlist_end", self.playlist_end.value())
        self.settings.setValue("playlist_items", self.playlist_items.text().strip())
        self.settings.setValue("playlist_reverse", self.playlist_reverse.isChecked())
        self.settings.setValue("playlist_random", self.playlist_random.isChecked())
        self.settings.setValue("use_archive", self.use_archive.isChecked())
        self.settings.setValue("archive_file", self.archive_file.text().strip())
        self.settings.setValue("proxy", self.proxy.text().strip())
        self.settings.setValue("source_address", self.source_address.text().strip())
        self.settings.setValue("force_ipv4", self.force_ipv4.isChecked())
        self.settings.setValue("force_ipv6", self.force_ipv6.isChecked())
        self.settings.setValue("username", self.username.text().strip())
        self.settings.setValue("password", self.password.text())
        self.settings.setValue("twofactor", self.twofactor.text().strip())
        self.settings.setValue("video_password", self.video_password.text())
        self.settings.setValue("extract_audio_adv", self.extract_audio_adv.isChecked())
        self.settings.setValue("audio_format_adv", self.audio_format_adv.currentText())
        self.settings.setValue("audio_quality_adv", self.audio_quality_adv.currentIndex())
        self.settings.setValue("keep_video_adv", self.keep_video_adv.isChecked())
        self.settings.setValue("recode_video", self.recode_video.currentText())
        self.settings.setValue("postprocessor_args", self.postprocessor_args.text().strip())
        self.settings.setValue("ignore_errors", self.ignore_errors.isChecked())
        self.settings.setValue("no_warnings", self.no_warnings.isChecked())
        self.settings.setValue("quiet", self.quiet.isChecked())
        self.settings.setValue("no_color", self.no_color.isChecked())
        self.settings.setValue("simulate", self.simulate.isChecked())
        self.settings.setValue("skip_download", self.skip_download.isChecked())

        self.settings.sync()
        logger.info("Ustawienia zostały zapisane.")


    def load_settings(self, initial=False):
        """
        Wczytuje ustawienia z pliku.
        Args:
            initial (bool): True if loading during app startup.
        """
        logger.info("Wczytuję ustawienia...")
        self.check_ytdlp_updates.setChecked(self.settings.value("check_ytdlp_updates", True, type=bool))
        self.auto_download_ffmpeg.setChecked(self.settings.value("auto_download_ffmpeg", os.name == 'nt', type=bool))
        if os.name != 'nt': self.auto_download_ffmpeg.setEnabled(False)
        saved_default_output_path = self.settings.value("default_output_path", "", type=str).strip()
        if not saved_default_output_path:
            user_downloads = self.get_user_downloads_path()
            self.default_output_path.setText(user_downloads)
            if not initial: logger.info(f"Ustawiono domyślną ścieżkę wyjściową na: {user_downloads} (poprzednia była pusta).")
            else: logger.debug(f"Domyślna ścieżka wyjściowa ustawiona na: {user_downloads} (przy starcie).")
        else:
            self.default_output_path.setText(saved_default_output_path)
            logger.debug(f"Domyślna ścieżka wyjściowa wczytana: {saved_default_output_path}")


        self.default_template.setText(self.settings.value("default_template", "%(title)s.%(ext)s", type=str).strip())
        self.auto_add_to_queue.setChecked(self.settings.value("auto_add_to_queue", False, type=bool))
        theme_name = self.settings.value("theme", "Dark", type=str)
        index = self.theme_combo.findText(theme_name)
        if index != -1:
            self.theme_combo.setCurrentIndex(index)
        else:
            self.theme_combo.setCurrentText("Dark")
            logger.warning(f"Nieznany motyw '{theme_name}' w ustawieniach, ustawiono domyślny 'Dark'.")
        self.ytdlp_path_input.setText(self.get_ytdlp_path())
        self.ffmpeg_path.setText(self.get_ffmpeg_path())
        cda_email = self.settings.value("cda_email", "", type=str).strip()
        cda_password = self.settings.value("cda_password", "", type=str)
        self.cda_email.setText(cda_email)
        self.cda_password.setText(cda_password)
        self.video_format.setCurrentText(self.settings.value("video_format", "mp4", type=str))
        self.video_quality.setCurrentIndex(self.settings.value("video_quality", 0, type=int))
        self.video_codec.setCurrentText(self.settings.value("video_codec", "auto", type=str))
        self.embed_thumbnails.setChecked(self.settings.value("embed_thumbnails", True, type=bool))
        self.embed_subs.setChecked(self.settings.value("embed_subs", False, type=bool))
        loaded_output_template = self.settings.value("output_template", "", type=str).strip()
        self.output_template.setText(loaded_output_template or self.default_template.text().strip())
        loaded_output_path = self.settings.value("output_path", "", type=str).strip()
        self.output_path.setText(loaded_output_path or self.default_output_path.text().strip())

        self.limit_rate.setText(self.settings.value("limit_rate", "", type=str).strip())
        self.retries.setValue(self.settings.value("retries", 10, type=int))
        self.extract_audio.setChecked(self.settings.value("extract_audio", False, type=bool))
        self.keep_video.setChecked(self.settings.value("keep_video", False, type=bool))
        self.write_subs.setChecked(self.settings.value("write_subs", False, type=bool))
        self.write_auto_subs.setChecked(self.settings.value("write_auto_subs", False, type=bool))
        self.write_info_json.setChecked(self.settings.value("write_info_json", False, type=bool))

        self.audio_format.setCurrentText(self.settings.value("audio_format", "najlepszy", type=str))
        try:
            idx = int(self.settings.value("audio_quality", 0))
        except (TypeError, ValueError):
            idx = 0
        self.audio_quality.setCurrentIndex(idx)
        self.add_metadata.setChecked(self.settings.value("add_metadata", True, type=bool))
        self.embed_thumbnail.setChecked(self.settings.value("embed_thumbnail", True, type=bool))
        loaded_audio_output_template = self.settings.value("audio_output_template", "", type=str).strip()
        self.audio_output_template.setText(loaded_audio_output_template or self.default_template.text().strip())
        loaded_audio_output_path = self.settings.value("audio_output_path", "", type=str).strip()
        self.audio_output_path.setText(loaded_audio_output_path or self.default_output_path.text().strip())

        self.prefer_ffmpeg.setChecked(self.settings.value("prefer_ffmpeg", False, type=bool))

        self.playlist_start.setValue(self.settings.value("playlist_start", 1, type=int))
        self.playlist_end.setValue(self.settings.value("playlist_end", 0, type=int))
        self.playlist_items.setText(self.settings.value("playlist_items", "", type=str).strip())
        self.playlist_reverse.setChecked(self.settings.value("playlist_reverse", False, type=bool))
        self.playlist_random.setChecked(self.settings.value("playlist_random", False, type=bool))
        self.use_archive.setChecked(self.settings.value("use_archive", False, type=bool))
        saved_archive_file = self.settings.value("archive_file", "", type=str).strip()
        if not saved_archive_file:
            default_archive_path = str(self.appdata_dir / "archive.txt")
            self.archive_file.setText(default_archive_path)
            self.archive_file.setPlaceholderText(f"Domyślnie: {self.appdata_dir / 'archive.txt'}")
            (self.appdata_dir / "archive.txt").parent.mkdir(parents=True, exist_ok=True)

            if not initial: logger.info(f"Ustawiono domyślną ścieżkę archiwum na: {default_archive_path} (poprzednia była pusta).")
            else: logger.debug(f"Domyślna ścieżka archiwum ustawiona na: {default_archive_path} (przy starcie).")
        else:
            self.archive_file.setText(saved_archive_file)
            self.archive_file.setPlaceholderText(f"Domyślnie: {self.appdata_dir / 'archive.txt'}")
            logger.debug(f"Ścieżka archiwum wczytana: {saved_archive_file}")


        self.proxy.setText(self.settings.value("proxy", "", type=str).strip())
        self.source_address.setText(self.settings.value("source_address", "", type=str).strip())
        self.force_ipv4.setChecked(self.settings.value("force_ipv4", False, type=bool))
        self.force_ipv6.setChecked(self.settings.value("force_ipv6", False, type=bool))
        self.username.setText(self.settings.value("username", "", type=str).strip())
        self.password.setText(self.settings.value("password", "", type=str))
        self.twofactor.setText(self.settings.value("twofactor", "", type=str).strip())
        self.video_password.setText(self.settings.value("video_password", "", type=str))
        self.extract_audio_adv.setChecked(self.settings.value("extract_audio_adv", False, type=bool))
        self.audio_format_adv.setCurrentText(self.settings.value("audio_format_adv", "najlepszy", type=str))
        try:
            idx_adv = int(self.settings.value("audio_quality_adv", 0))
        except (TypeError, ValueError):
            idx_adv = 0
        self.audio_quality_adv.setCurrentIndex(idx_adv)
        self.keep_video_adv.setChecked(self.settings.value("keep_video_adv", False, type=bool))
        self.recode_video.setCurrentText(self.settings.value("recode_video", "Nie przetwarzaj", type=str))
        self.postprocessor_args.setText(self.settings.value("postprocessor_args", "", type=str).strip())
        self.ignore_errors.setChecked(self.settings.value("ignore_errors", False, type=bool))
        self.no_warnings.setChecked(self.settings.value("no_warnings", False, type=bool))
        self.quiet.setChecked(self.settings.value("quiet", False, type=bool))
        self.no_color.setChecked(self.settings.value("no_color", False, type=bool))
        self.simulate.setChecked(self.settings.value("simulate", False, type=bool))
        self.skip_download.setChecked(self.settings.value("skip_download", False, type=bool))

        if not initial:
            logger.info("Ustawienia wczytane na żądanie użytkownika.")
            QMessageBox.information(self, "Ustawienia wczytane", "Ustawienia zostały wczytane.")
        else:
            logger.info("Ustawienia wczytane przy starcie.")


    def reset_settings(self):
        reply = QMessageBox.question(
            self, "Resetuj ustawienia",
            "Czy na pewno chcesz zresetować ustawienia do domyślnych?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings.clear()
            logger.info("Ustawienia zostały zresetowane.")
            self.default_output_path.setText(self.get_user_downloads_path())
            self.default_template.setText("%(title)s.%(ext)s")
            (self.appdata_dir / "archive.txt").parent.mkdir(parents=True, exist_ok=True)
            self.archive_file.setText(str(self.appdata_dir / "archive.txt"))


            self.load_settings(initial=False)
            self.apply_style()
            QMessageBox.information(self, "Ustawienia zresetowane", "Ustawienia zostały zresetowane do domyślnych.")


    def clear_output(self):
        self.output_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        logger.info("Wyczyszczono okno wyjścia i postępu")

    def update_progress(self, text):
        self.output_text.append(text)
        if scrollbar := self.output_text.verticalScrollBar():
            scrollbar.setValue(scrollbar.maximum())
        logger.debug(f"Wyjście yt-dlp (raw): {text}")
        title_match = re.search(r"\[info\]\s+Title:\s+(.+)", text)
        if title_match:
            self.current_video_title = title_match.group(1).strip()
            logger.debug(f"Przechwycono tytuł wideo: {self.current_video_title}")


    def update_progress_percent(self, percent):
        percent = max(0, min(100, percent))
        pass


    def update_detailed_progress(self, percent, total_size_str, speed_str, raw_status_line):
        """Updates the progress bar with detailed info."""
        percent = max(0, min(100, percent))
        self.progress_bar.setValue(percent)

        status_text = ""
        # Próbuj wyciągnąć ETA lub podobny status
        eta_match = re.search(r"ETA\s+([\d:]+)", raw_status_line)
        if eta_match:
            status_text = f"ETA {eta_match.group(1)}"

        progress_text_parts = [f"{percent}%"]
        if total_size_str != "N/A":
            progress_text_parts.append(f"{total_size_str}")
        if speed_str != "N/A":
            progress_text_parts.append(f"{speed_str}")
        if status_text:
            progress_text_parts.append(status_text)

        formatted_display = " | ".join(progress_text_parts)
        self.progress_bar.setFormat(formatted_display)


    def download_finished(self, success):
        self.stop_btn.setEnabled(False)
        self.progress_bar.setFormat("%p%")
        current_processing_url = getattr(self, "current_processing_url", None)

        # Usuń z kolejki, jeśli tam był
        if self.download_queue and current_processing_url:
            if current_processing_url == self.download_queue[0]:
                finished_url = self.download_queue.pop(0)
                items = self.queue_list.findItems(finished_url, Qt.MatchFlag.MatchExactly)
                if items:
                    row = self.queue_list.row(items[0])
                    self.queue_list.takeItem(row)
                    logger.info(f"Usunięto zakończony element z kolejki (indeks {row}): {finished_url}")
                else:
                    # Spróbuj usunąć pierwszy element, jeśli dokładne dopasowanie zawiedzie (np. z powodu normalizacji)
                    if self.queue_list.count() > 0:
                        self.queue_list.takeItem(0)
                        logger.warning(f"Nie znaleziono zakończonego URL '{finished_url}' w kolejce GUI, usunięto pierwszy element.")
                self.save_queue()
                self.url_input.clear()
            else:
                logger.warning(f"Zakończony URL '{current_processing_url}' nie pasuje do pierwszego elementu w kolejce '{self.download_queue[0]}'")

        if success:
            self.output_text.append("\nPobieranie zakończone pomyślnie.")
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100% | Zakończono")
            logger.info("Pobieranie zakończone pomyślnie")
        else:
            self.output_text.append(f"\n--- BŁĄD ---\nPobieranie nie powiodło się dla: {current_processing_url}\nTytuł: {self.current_video_title}\nSprawdź logi w konsoli lub plik {self.failed_log_file.name} po szczegóły.\n---")
            logger.error(f"Pobieranie nie powiodło się dla: {current_processing_url}")
            self.failed_logger.info(f"FAILED_URL: {current_processing_url} | TITLE: {self.current_video_title}")

        self.current_video_title = "Unknown"
        self.current_processing_url = None

        if self.download_queue:
            self.output_text.append(f"\nPozostało {len(self.download_queue)} elementów w kolejce. Rozpoczynam następny...")
            logger.info(f"Kontynuuję kolejkę, {len(self.download_queue)} elementów pozostało.")
            self.start_next_in_queue()
        else:
            self.output_text.append("\nKolejka jest pusta. Pobieranie zakończone.")
            logger.info("Kolejka pusta, pobieranie zakończone.")
            self.download_btn.setEnabled(True)


    def start_download(self, add_current_url=True):
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "Pobieranie w toku", "Poczekaj na zakończenie obecnego pobierania.")
            return

        current_url = self.url_input.text().strip()
        if add_current_url and current_url:
            self.download_queue.append(current_url)
            self.queue_list.addItem(current_url)
            self.url_input.clear()
            self.save_queue()
            logger.info(f"Dodano do kolejki i rozpoczęto pobieranie: {current_url}")
        elif not self.download_queue:
            QMessageBox.warning(self, "Brak URL", "Wprowadź URL lub dodaj coś do kolejki.")
            return

        self.start_next_in_queue()

    def start_next_in_queue(self):
        if not self.download_queue:
            logger.warning("Próba uruchomienia następnego elementu, ale kolejka jest pusta.")
            self.download_btn.setEnabled(True)
            return

        url = self.download_queue[0]
        self.current_processing_url = url
        self.output_text.append(f"\n--- ROZPOCZYNAM POBIERANIE DLA: {url} ---")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0%")

        command = self.build_command(url)
        if not command:
            self.download_finished(False) # Treat as failure for this item
            return

        self.thread = YTDLPThread(command, self)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.download_finished)
        self.thread.progress_percent_signal.connect(self.update_progress_percent)
        self.thread.progress_detailed_signal.connect(self.update_detailed_progress)

        self.thread.start()
        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_download(self):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.output_text.append("\nZatrzymuję pobieranie...")
            logger.info("Zażądano zatrzymania pobierania.")
        else:
            logger.warning("Próba zatrzymania, ale żaden wątek pobierania nie działa.")

    def build_command(self, url):
        ytdlp_path = self.get_ytdlp_path()
        if ytdlp_path != 'yt-dlp' and not Path(ytdlp_path).exists():
            QMessageBox.critical(self, "Błąd YT-DLP", f"Nie znaleziono pliku YT-DLP w '{ytdlp_path}'. Sprawdź ścieżkę w Ustawieniach.")
            logger.error(f"Nie znaleziono YT-DLP w '{ytdlp_path}' podczas budowania komendy.")
            return None

        command = [ytdlp_path]

        ffmpeg_path_setting = self.get_ffmpeg_path()
        if ffmpeg_path_setting:
            if ffmpeg_path_setting == 'ffmpeg' or Path(ffmpeg_path_setting).is_file():
                ffmpeg_dir = str(Path(ffmpeg_path_setting).parent)
                command.extend(["--ffmpeg-location", ffmpeg_dir])
            else:
                msg = f"Ścieżka do FFmpeg '{ffmpeg_path_setting}' jest nieprawidłowa (nie jest plikiem). Niektóre funkcje mogą nie działać."
                self.output_text.append(f"OSTRZEŻENIE: {msg}")
                logger.warning(msg)

        # Tab Wideo
        video_format = self.video_format.currentText()
        video_quality = self.video_quality.currentText()
        video_codec = self.video_codec.currentText()

        # Tab Audio
        audio_format = self.audio_format.currentText()
        audio_quality_index = self.audio_quality.currentIndex()

        # Tab Zaawansowane
        extract_audio_adv = self.extract_audio_adv.isChecked()
        recode_video_format = self.recode_video.currentText()
        # Wybór trybu (wideo, audio, ekstrakcja zaawansowana)
        mode = "video"
        if extract_audio_adv:
            mode = "audio_adv"
        elif self.extract_audio.isChecked():
            mode = "audio"
        if recode_video_format != "Nie przetwarzaj":
            command.extend(["--recode-video", recode_video_format])
        if mode in ("audio", "audio_adv"):
            command.append("-x") # --extract-audio
            if mode == "audio":
                command.extend(["--audio-format", audio_format])
                if audio_quality_index is not None:
                    command.extend(["--audio-quality", str(audio_quality_index)])
                if self.keep_video.isChecked():
                    command.append("-k") # --keep-video
                if self.add_metadata.isChecked():
                    command.append("--add-metadata")
                if self.embed_thumbnail.isChecked():
                    command.append("--embed-thumbnail")
                output_path = self.audio_output_path.text().strip() or self.default_output_path.text().strip()
                output_template = self.audio_output_template.text().strip() or self.default_template.text().strip()
            else: # audio_adv
                command.extend(["--audio-format", self.audio_format_adv.currentText()])
                if self.audio_quality_adv.currentIndex() is not None:
                    command.extend(["--audio-quality", str(self.audio_quality_adv.currentIndex())])
                if self.keep_video_adv.isChecked():
                    command.append("-k") # --keep-video
                output_path = self.default_output_path.text().strip()
                output_template = self.default_template.text().strip()
        else: # video mode
            if video_quality == "Najlepsze (auto)":
                 format_string = f"bv*[ext={video_format}]+ba[ext=m4a]/b[ext={video_format}]/bv*+ba/b"
            else:
                height = video_quality.split('p')[0]
                format_string = f"bv*[height<={height}][ext={video_format}]+ba[ext=m4a]/b[ext={video_format}][height<={height}]/bv*[height<={height}]+ba/b[height<={height}]"
            if video_codec != "auto":
                format_string = format_string.replace("bv*", f"bv*[vcodec~=^({video_codec})]")
            command.extend(["-f", format_string])
            if self.embed_thumbnails.isChecked():
                command.append("--embed-thumbnail")
            if self.embed_subs.isChecked():
                command.append("--embed-subs")
            output_path = self.output_path.text().strip() or self.default_output_path.text().strip()
            output_template = self.output_template.text().strip() or self.default_template.text().strip()

        if output_path:
            command.extend(["-P", output_path])
        if output_template:
            command.extend(["-o", output_template])

        # Opcje wspólne
        if rate := self.limit_rate.text().strip(): command.extend(["-r", rate])
        if retries := self.retries.value(): command.extend(["--retries", str(retries)])
        if self.write_subs.isChecked(): command.append("--write-subs")
        if self.write_auto_subs.isChecked(): command.append("--write-auto-subs")
        if self.write_info_json.isChecked(): command.append("--write-info-json")
        if self.prefer_ffmpeg.isChecked(): command.append("--prefer-ffmpeg")

        # Playlista
        if start := self.playlist_start.value() > 1: command.extend(["--playlist-start", str(self.playlist_start.value())])
        if end := self.playlist_end.value() > 0: command.extend(["--playlist-end", str(self.playlist_end.value())])
        if items := self.playlist_items.text().strip(): command.extend(["--playlist-items", items])
        if self.playlist_reverse.isChecked(): command.append("--playlist-reverse")
        if self.playlist_random.isChecked(): command.append("--playlist-random")

        # Archiwum
        if self.use_archive.isChecked():
            archive_path = self.archive_file.text().strip()
            if archive_path:
                command.extend(["--download-archive", archive_path])
            else:
                msg = "Opcja archiwum włączona, ale ścieżka do pliku jest pusta. Opcja zostanie zignorowana."
                self.output_text.append(f"OSTRZEŻENIE: {msg}")
                logger.warning(msg)

        # Zaawansowane
        if proxy := self.proxy.text().strip(): command.extend(["--proxy", proxy])
        if s_addr := self.source_address.text().strip(): command.extend(["--source-address", s_addr])
        if self.force_ipv4.isChecked(): command.append("--force-ipv4")
        if self.force_ipv6.isChecked(): command.append("--force-ipv6")

        # Logowanie
        cda_email = self.cda_email.text().strip()
        cda_pass = self.cda_password.text()
        username = self.username.text().strip()
        password = self.password.text()

        if cda_email and cda_pass:
            command.extend(["--username", cda_email, "--password", cda_pass])
        elif username and password:
            command.extend(["--username", username, "--password", password])
        if twofactor := self.twofactor.text().strip(): command.extend(["--twofactor", twofactor])
        if video_pass := self.video_password.text(): command.extend(["--video-password", video_pass])

        if ppa := self.postprocessor_args.text().strip(): command.extend(["--postprocessor-args", ppa])
        if self.ignore_errors.isChecked(): command.append("--ignore-errors")
        if self.no_warnings.isChecked(): command.append("--no-warnings")
        if self.quiet.isChecked(): command.append("--quiet")
        if self.no_color.isChecked(): command.append("--no-color")
        if self.simulate.isChecked(): command.append("--simulate")
        if self.skip_download.isChecked(): command.append("--skip-download")

        command.append(url)
        logger.info(f"Zbudowana komenda: {' '.join(command)}")
        return command

    def closeEvent(self, event):
        """Zapisuje ustawienia przy zamykaniu."""
        logger.info("Aplikacja jest zamykana, zapisuję ustawienia.")
        self.save_settings()
        self.save_queue()
        # Ensure threads are stopped
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        if self.update_ytdlp_thread and self.update_ytdlp_thread.isRunning():
            self.update_ytdlp_thread.quit()
            self.update_ytdlp_thread.wait()
        if self.download_ffmpeg_thread and self.download_ffmpeg_thread.isRunning():
            self.download_ffmpeg_thread.quit()
            self.download_ffmpeg_thread.wait()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YTDLPGUI()
    window.show()
    sys.exit(app.exec())