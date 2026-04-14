# -*- coding: utf-8 -*-
"""
Wątki robocze Qt:
  - YTDLPThread           – uruchamia yt-dlp i parsuje postęp
  - UpdateYTDLPThread     – sprawdza / pobiera aktualizację yt-dlp
  - DownloadFFmpegThread  – sprawdza / pobiera FFmpeg
  - CDAStatusCheckThread  – weryfikuje login CDA Premium
  - PreviewFetchThread    – pobiera metadane jednego URL
  - BatchPreviewThread    – pobiera metadane wielu URL w tle
  - TitleFetchThread      – pobiera tytuł jednego URL
"""

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, List

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from .config import (
    DEFAULT_SOCKET_TIMEOUT,
    DETAILED_PROGRESS_REGEX,
    FFMPEG_BIN_DIR,
    FFMPEG_DOWNLOAD_URL_LINUX,
    FFMPEG_DOWNLOAD_URL_WINDOWS,
    FFMPEG_PATH_LINUX,
    FFMPEG_PATH_WINDOWS,
    LIBS_DIR,
    THUMBS_CACHE_DIR,
    TOOLS_DIR,
    YTDLP_PATH_LINUX,
    YTDLP_PATH_WINDOWS,
)

if TYPE_CHECKING:
    from .main_window import YTDLPGUI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pomocnik – uruchamianie podprocesu bez okna konsoli
# ---------------------------------------------------------------------------

def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _run_cmd(command, timeout: int = 30):
    """Uruchamia komendę i zwraca (returncode, combined_output, stdout, stderr)."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=_creationflags(),
    )
    stdout, stderr = process.communicate(timeout=timeout)
    return process.returncode, stdout + stderr, stdout, stderr


# ===========================================================================
# YTDLPThread
# ===========================================================================

class YTDLPThread(QThread):
    progress_signal         = pyqtSignal(str)
    finished_signal         = pyqtSignal(bool)
    progress_percent_signal = pyqtSignal(int)
    progress_detailed_signal = pyqtSignal(str, int, str, str)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.is_running = True
        self.process = None

    # Wzorzec wykrywający błąd Cloudflare 403 w wyjściu yt-dlp
    _CF_ERROR_RE = re.compile(
        r"Got HTTP Error 403.*[Cc]loudflare|[Cc]loudflare.*403|"
        r"anti-bot.*challenge|try again with.*--extractor-args.*impersonate",
        re.IGNORECASE,
    )

    def run(self):
        try:
            if not Path(self.command[0]).exists() and self.command[0] != "yt-dlp":
                msg = f"Błąd: Nie znaleziono pliku wykonawczego: {self.command[0]}"
                self.progress_signal.emit(msg)
                logger.error(msg)
                self.finished_signal.emit(False)
                return

            success, cloudflare_hit = self._run_process(self.command)

            # Fallback: jeśli Cloudflare zablokował, ponawiamy z --extractor-args "generic:impersonate=chrome"
            if not success and cloudflare_hit and self.is_running:
                self.progress_signal.emit(
                    "\nUWAGA: Wykryto blokadę Cloudflare (HTTP 403). "
                    "Ponawiam z --extractor-args \"generic:impersonate=chrome\"..."
                )
                logger.info("Cloudflare fallback: dodaję --extractor-args generic:impersonate=chrome")
                fallback_cmd = list(self.command)
                # Wstawiamy argument tuż przed URL-em (ostatni element)
                url = fallback_cmd.pop()
                fallback_cmd += ["--extractor-args", "generic:impersonate=chrome", url]
                success, _ = self._run_process(fallback_cmd)

            self.finished_signal.emit(success)

        except FileNotFoundError:
            msg = f"Plik wykonawczy nie znaleziono: {self.command[0]}"
            logger.error(msg)
            self.progress_signal.emit(f"Błąd: {msg}\nUpewnij się, że ścieżka w ustawieniach jest poprawna.")
            self.finished_signal.emit(False)
        except Exception as e:
            logger.error(f"Błąd w wątku pobierania: {e}", exc_info=True)
            self.progress_signal.emit(f"Błąd: {e}")
            self.finished_signal.emit(False)

    def _run_process(self, command: list) -> tuple:
        """Uruchamia proces yt-dlp, parsuje wyjście i zwraca (success, cloudflare_hit)."""
        cloudflare_hit = False
        quoted = [str(a) for a in command]
        logger.info(f"Uruchamiam: {' '.join(quoted)}")
        self.process = subprocess.Popen(
            quoted,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_creationflags(),
            bufsize=1,
        )
        if not self.process or not self.process.stdout:
            return False, False

        while True:
            output = self.process.stdout.readline()
            if output == "" and self.process.poll() is not None:
                break
            if output:
                line = output.strip()
                self.progress_signal.emit(line)
                self._parse_progress(line)
                if self._CF_ERROR_RE.search(line):
                    cloudflare_hit = True
            if not self.is_running and self.process.poll() is not None:
                break

        returncode = self.process.wait()
        logger.info(f"Proces zakończony z kodem: {returncode}")
        if returncode == 0:
            self.progress_detailed_signal.emit("wideo", 100, "Ukończono", "Ukończono")
        return returncode == 0, cloudflare_hit

    def _parse_progress(self, line: str):
        match = DETAILED_PROGRESS_REGEX.search(line)
        if not match:
            return
        try:
            percent = int(float(match.group(1)))
            total_size_str = match.group(2) if match.group(2) else "N/A"
            speed_match = match.group(3)
            downloaded_str = "N/A"
            if total_size_str != "N/A" and percent > 0:
                val = float(re.sub(r"[^\d.]", "", total_size_str))
                if "GiB" in total_size_str or "GB" in total_size_str:
                    total_mb = val * (1024 if "GiB" in total_size_str else 1000)
                elif "KiB" in total_size_str or "KB" in total_size_str:
                    total_mb = val / (1024 if "KiB" in total_size_str else 1000)
                else:
                    total_mb = val
                downloaded_mb = (percent / 100.0) * total_mb
                downloaded_str = f"{downloaded_mb:.1f} MB"
                total_size_str = f"{total_mb:.1f} MB"
            self.progress_detailed_signal.emit("wideo", percent, downloaded_str, total_size_str)
        except Exception as e:
            logger.debug(f"Parse progress failed: {e}")

    def stop(self):
        self.is_running = False
        if self.process and self.process.poll() is None:
            try:
                logger.info("Próbuję zakończyć yt-dlp...")
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        creationflags=_creationflags(),
                    )
                else:
                    os.kill(self.process.pid, 2)
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Timeout przy zamykaniu, kill()")
                try:
                    self.process.kill()
                except Exception as e:
                    logger.error(f"Błąd kill: {e}")
            except Exception as e:
                logger.error(f"Błąd zatrzymywania: {e}", exc_info=True)
        # NIE emitujemy finished_signal tutaj — run() zakończy pętlę
        # (is_running=False + martwy proces) i sam wyemituje finished_signal.


# ===========================================================================
# UpdateYTDLPThread
# ===========================================================================

class UpdateYTDLPThread(QThread):
    finished_signal         = pyqtSignal(bool, str)
    progress_signal         = pyqtSignal(str)
    progress_percent_signal = pyqtSignal(int)
    progress_detailed_signal = pyqtSignal(str, int, str, str)

    def __init__(self, yt_dlp_path, main_window: "YTDLPGUI", parent=None):
        super().__init__(parent)
        self.yt_dlp_path = Path(yt_dlp_path) if yt_dlp_path else Path("")
        self.main_window = main_window
        if self.yt_dlp_path.is_absolute() and not str(self.yt_dlp_path).startswith("yt-dlp"):
            self.yt_dlp_path.parent.mkdir(parents=True, exist_ok=True)

    def run(self):
        if not self.main_window.settings.value("check_ytdlp_updates", True, type=bool):
            logger.info("Pominięto sprawdzanie aktualizacji yt-dlp")
            self._check_local(str(self.yt_dlp_path))
            return
        try:
            self.progress_signal.emit("Sprawdzam aktualizacje yt-dlp...")
            api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            latest_version = data.get("tag_name", "")
            assets = data.get("assets", [])

            target = YTDLP_PATH_WINDOWS if os.name == "nt" else YTDLP_PATH_LINUX
            target.parent.mkdir(parents=True, exist_ok=True)
            download_url = self._find_asset_url(assets)

            if not download_url:
                self.finished_signal.emit(False, "Nie znaleziono pliku yt-dlp w wydaniu GitHub.")
                self._check_local(str(self.yt_dlp_path))
                return

            current_version = self._get_current_version(target)
            latest_clean = (latest_version or "").lstrip("v")
            current_clean = (current_version or "").lstrip("v")

            if current_version and current_version != "brak" and latest_clean == current_clean:
                self.progress_signal.emit("Najnowsza wersja yt-dlp zainstalowana.")
                self.finished_signal.emit(True, "Najnowsza wersja yt-dlp jest już zainstalowana.")
                self.main_window.settings.setValue("ytdlp_path", str(target))
                return

            self.progress_signal.emit(f"Pobieram yt-dlp {latest_version}...")
            self._download_ytdlp(download_url, target, latest_version)

        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd sieciowy yt-dlp: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Błąd sieciowy: {e}")
            self._check_local(str(self.yt_dlp_path))
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd yt-dlp: {e}", exc_info=True)
            self.finished_signal.emit(False, f"Błąd: {e}")
            self._check_local(str(self.yt_dlp_path))

    def _find_asset_url(self, assets):
        if os.name == "nt":
            for a in assets:
                name = a.get("name", "").lower()
                if name.endswith(".exe") and ("yt-dlp" in name or "youtube-dlp" in name):
                    return a.get("browser_download_url")
        else:
            for a in assets:
                name = a.get("name", "").lower()
                if ("yt-dlp" in name or "youtube-dlp" in name) and not name.endswith(
                    (".exe", ".zip", ".tar.gz", ".tar.xz", ".deb", ".rpm")
                ):
                    if "linux" in name or not any(x in name for x in ["win", "macos", "darwin", "windows"]):
                        return a.get("browser_download_url")
        return None

    def _get_current_version(self, path: Path) -> str:
        if not path.exists():
            return "brak"
        try:
            r = subprocess.run(
                [str(path), "--version"],
                capture_output=True, text=True, check=True, timeout=5,
                creationflags=_creationflags(), encoding="utf-8",
            )
            v = r.stdout.strip()
            self.progress_signal.emit(f"Obecna wersja yt-dlp: {v}")
            return v
        except Exception:
            return "brak"

    def _download_ytdlp(self, url: str, target: Path, version: str):
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        tmp = target.with_suffix(".tmp")
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int((downloaded / total) * 100)
                        self.progress_percent_signal.emit(pct)
                        self.progress_detailed_signal.emit(
                            "yt-dlp", pct,
                            f"{downloaded / 1048576:.1f} MB",
                            f"{total / 1048576:.1f} MB",
                        )
        if os.name != "nt":
            os.chmod(tmp, 0o755)
        os.replace(tmp, target)
        self.progress_signal.emit(f"Pobrano yt-dlp {version}.")
        self.main_window.settings.setValue("ytdlp_path", str(target))
        self.finished_signal.emit(True, f"Pobrano yt-dlp {version}.")

    def _check_local(self, path_str: str):
        """Fallback – sprawdza lokalny plik lub yt-dlp z PATH."""
        path = Path(path_str) if path_str else Path("")
        for cmd in ([str(path), "--version"] if path_str else None, ["yt-dlp", "--version"]):
            if cmd is None:
                continue
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, check=True, timeout=10,
                    creationflags=_creationflags(), encoding="utf-8",
                )
                v = r.stdout.strip()
                src = str(path) if cmd[0] != "yt-dlp" else "yt-dlp (PATH)"
                self.finished_signal.emit(True, f"Znaleziono yt-dlp: {src} (Wersja: {v})")
                key = str(path) if cmd[0] != "yt-dlp" else "yt-dlp"
                self.main_window.settings.setValue("ytdlp_path", key)
                return
            except Exception:
                continue
        self.finished_signal.emit(False, f"Nie znaleziono yt-dlp ani pod ścieżką ({path_str}), ani w PATH.")
        self.main_window.settings.setValue("ytdlp_path", "")


# ===========================================================================
# DownloadFFmpegThread
# ===========================================================================

class DownloadFFmpegThread(QThread):
    finished_signal         = pyqtSignal(bool, str)
    progress_signal         = pyqtSignal(str)
    progress_percent_signal = pyqtSignal(int)
    progress_detailed_signal = pyqtSignal(str, int, str, str)

    def __init__(self, ffmpeg_path, main_window: "YTDLPGUI", parent=None):
        super().__init__(parent)
        self.ffmpeg_path_setting = Path(ffmpeg_path) if ffmpeg_path else Path("")
        self.main_window = main_window

    def run(self):
        auto_dl = self.main_window.settings.value("auto_download_ffmpeg", True, type=bool)
        target = FFMPEG_PATH_WINDOWS if os.name == "nt" else FFMPEG_PATH_LINUX
        try:
            self.progress_signal.emit("Sprawdzam obecność FFmpeg...")
            if target.exists():
                self.progress_signal.emit("FFmpeg znaleziono lokalnie.")
                self.finished_signal.emit(True, "FFmpeg jest już zainstalowany.")
                self.main_window.settings.setValue("ffmpeg_path", str(target))
                return
            if not auto_dl:
                self.progress_signal.emit("Automatyczne pobieranie FFmpeg wyłączone. Sprawdzam inne lokalizacje.")
                self._check_local(str(self.ffmpeg_path_setting))
                return
            if os.name == "nt":
                self._download_windows(target)
            else:
                self._download_linux(target)
        except requests.exceptions.RequestException as e:
            self.finished_signal.emit(False, f"Błąd sieciowy: {e}")
            self._check_local(str(self.ffmpeg_path_setting))
        except Exception as e:
            self.finished_signal.emit(False, f"Błąd FFmpeg: {e}")
            self._check_local(str(self.ffmpeg_path_setting))
        finally:
            for tmp in [LIBS_DIR / "ffmpeg.zip", TOOLS_DIR / "ffmpeg.tar.xz"]:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    def _stream_download(self, url: str, dest: Path, label: str):
        resp = requests.get(url, stream=True, timeout=180)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int((downloaded / total) * 100)
                        self.progress_percent_signal.emit(pct)
                        self.progress_detailed_signal.emit(
                            label, pct,
                            f"{downloaded / 1048576:.1f} MB",
                            f"{total / 1048576:.1f} MB",
                        )

    def _download_windows(self, target: Path):
        import zipfile
        self.progress_signal.emit(f"Pobieram FFmpeg z {FFMPEG_DOWNLOAD_URL_WINDOWS}")
        tmp_zip = LIBS_DIR / "ffmpeg.zip"
        tmp_zip.parent.mkdir(parents=True, exist_ok=True)
        self._stream_download(FFMPEG_DOWNLOAD_URL_WINDOWS, tmp_zip, "FFmpeg")
        self.progress_signal.emit("Rozpakowuję FFmpeg...")
        FFMPEG_BIN_DIR.mkdir(parents=True, exist_ok=True)
        to_extract = {"ffmpeg.exe", "ffplay.exe", "ffprobe.exe"}
        extracted = []
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                parts = info.filename.replace("\\", "/").split("/")
                fname = parts[-1].lower()
                if "bin" in parts and fname in to_extract:
                    dest = FFMPEG_BIN_DIR / os.path.basename(info.filename)
                    with zf.open(info) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(fname)
        if "ffmpeg.exe" not in extracted:
            self.finished_signal.emit(False, "Nie znaleziono ffmpeg.exe w archiwum.")
            return
        self.finished_signal.emit(True, "Pobrano i zainstalowano FFmpeg.")
        self.main_window.settings.setValue("ffmpeg_path", str(target))

    def _download_linux(self, target: Path):
        import tarfile
        self.progress_signal.emit(f"Pobieram FFmpeg z {FFMPEG_DOWNLOAD_URL_LINUX}")
        tmp_tar = TOOLS_DIR / "ffmpeg.tar.xz"
        tmp_tar.parent.mkdir(parents=True, exist_ok=True)
        self._stream_download(FFMPEG_DOWNLOAD_URL_LINUX, tmp_tar, "FFmpeg")
        self.progress_signal.emit("Rozpakowuję FFmpeg...")
        to_extract = {"ffmpeg", "ffplay", "ffprobe"}
        extracted = []
        with tarfile.open(tmp_tar, "r:xz") as tf:
            for member in tf.getmembers():
                if member.isdir():
                    continue
                parts = member.name.split("/")
                fname = parts[-1]
                if "bin" not in parts or fname not in to_extract:
                    continue
                dest = TOOLS_DIR / fname
                src = tf.extractfile(member)
                if src is None:
                    continue
                with src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, 0o755)
                extracted.append(fname)
        if "ffmpeg" not in extracted:
            self.finished_signal.emit(False, "Nie znaleziono ffmpeg w archiwum.")
            return
        self.finished_signal.emit(True, "Pobrano i zainstalowano FFmpeg.")
        self.main_window.settings.setValue("ffmpeg_path", str(target))

    def _check_local(self, path_str: str):
        path = Path(path_str) if path_str else Path("")
        for cmd in ([str(path), "-version"] if path_str else None, ["ffmpeg", "-version"]):
            if cmd is None:
                continue
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, check=True, timeout=10,
                    creationflags=_creationflags(), encoding="utf-8",
                )
                m = re.search(r"ffmpeg version (.+)", r.stdout or r.stderr or "")
                v = m.group(1).split()[0] if m else "unknown"
                src = str(path) if cmd[0] != "ffmpeg" else "ffmpeg (PATH)"
                self.finished_signal.emit(True, f"Znaleziono FFmpeg: {src} (Wersja: {v})")
                key = str(path) if cmd[0] != "ffmpeg" else "ffmpeg"
                self.main_window.settings.setValue("ffmpeg_path", key)
                return
            except Exception:
                continue
        self.finished_signal.emit(False, "Nie znaleziono FFmpeg ani pod ścieżką ustawioną, ani w PATH.")
        self.main_window.settings.setValue("ffmpeg_path", "")


# ===========================================================================
# CDAStatusCheckThread
# ===========================================================================

class CDAStatusCheckThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, email: str, password: str, ytdlp_path: str,
                 main_window: "YTDLPGUI", parent=None):
        super().__init__(parent)
        self.email = email
        self.password = password
        self.ytdlp_path = ytdlp_path
        self.main_window = main_window

    def run(self):
        if not self.email or not self.password:
            self.finished_signal.emit(False, "Wprowadź email i hasło.")
            return
        try:
            basic = self._test_basic()
            if not basic["success"]:
                self.finished_signal.emit(False, basic["message"])
                return
            premium = self._test_premium()
            if premium.get("is_premium"):
                msg = "Zalogowano pomyślnie! Posiadasz dostęp do CDA Premium"
            else:
                msg = "Zalogowano pomyślnie! Posiadasz konto podstawowe bez Premium"
            self.finished_signal.emit(True, msg)
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania CDA: {e}")
            self.finished_signal.emit(False, f"Błąd: {e}")

    def _base_cmd(self, url: str) -> list:
        return [
            str(self.ytdlp_path), "--username", self.email, "--password", self.password,
            "--verbose", "--simulate", "--no-download", "--get-title",
            "--no-check-certificate",
            "--socket-timeout", str(DEFAULT_SOCKET_TIMEOUT), url,
        ]

    def _test_basic(self) -> dict:
        try:
            rc, out, stdout, _ = _run_cmd(self._base_cmd("https://www.cda.pl/video/2292883791"))
            logger.debug(f"[CDA Basic] {out}")
            if "cda-bearer" in out or "Loading cda-bearer" in out:
                return {"success": True, "message": "Logowanie pomyślne (wykryto token)"}
            if "Unable to log in" in out or "Invalid username or password" in out:
                return {"success": False, "message": "Nieprawidłowe dane logowania"}
            if "HTTP Error 403" in out:
                return {"success": False, "message": "Błąd autoryzacji – sprawdź dane logowania"}
            if rc == 0 and stdout.strip():
                return {"success": True, "message": "Logowanie pomyślne"}
            return {"success": False, "message": "Nie udało się nawiązać połączenia z CDA."}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout podczas sprawdzania logowania"}
        except Exception as e:
            return {"success": False, "message": f"Błąd testu: {e}"}

    def _test_premium(self) -> dict:
        try:
            rc, out, stdout, _ = _run_cmd(
                self._base_cmd("https://www.cda.pl/video/2557979760/vfilm")
            )
            logger.debug(f"[CDA Premium] {out}")
            if "Video requires CDA Premium" in out or "premium account required" in out.lower():
                return {"is_premium": False}
            if rc == 0 and stdout.strip():
                return {"is_premium": True}
            return {"is_premium": False}
        except Exception:
            return {"is_premium": False}


# ===========================================================================
# PreviewFetchThread
# ===========================================================================

class PreviewFetchThread(QThread):
    result_signal = pyqtSignal(dict)
    error_signal  = pyqtSignal(str)

    def __init__(self, main_window: "YTDLPGUI", url: str, parent=None):
        super().__init__(parent)
        self.mw = main_window
        self.url = url

    def run(self):
        try:
            ytdlp = self.mw.get_ytdlp_path()
            fmt, mode = self.mw._build_format_string_for_preview()
            cmd = [ytdlp, "-s", "--dump-json", "--socket-timeout", str(DEFAULT_SOCKET_TIMEOUT)]
            if fmt:
                cmd += ["-f", fmt]
            cmd += self._auth_args()
            cmd.append(self.url)

            logger.info(f"[Preview] cmd: {' '.join(cmd)}")
            p = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="ignore", timeout=30, creationflags=_creationflags(),
            )
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Nie udało się pobrać metadanych")

            lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
            if not lines:
                raise RuntimeError("Brak metadanych JSON.")
            data = json.loads(lines[-1])
            result = self._extract_info(data)
            self.result_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))

    def _auth_args(self) -> list:
        args = []
        cda_email = self.mw.cda_email.text().strip()
        cda_pass  = self.mw.cda_password.text()
        username  = self.mw.username.text().strip()
        password  = self.mw.password.text()
        if self.url and "cda.pl" in self.url:
            args += ["--no-check-certificate"]
            if "/vfilm" in self.url and cda_email and cda_pass:
                # Tylko premium (/vfilm) wymaga credentials.
                # Zwykłe filmy CDA działają anonimowo; podanie credentials powoduje HTTP 403.
                args += ["--username", cda_email, "--password", cda_pass]
        else:
            if cda_email and cda_pass:
                args += ["--username", cda_email, "--password", cda_pass]
            elif username and password:
                args += ["--username", username, "--password", password]
        return args

    def _extract_info(self, data: dict) -> dict:
        thumb_url = None
        if isinstance(data.get("thumbnails"), list) and data["thumbnails"]:
            thumb_url = data["thumbnails"][-1].get("url")
        if not thumb_url:
            thumb_url = data.get("thumbnail")

        est_bytes = _estimate_bytes(data)
        thumb_path = _download_thumbnail(data.get("id"), thumb_url)

        return {
            "title": data.get("title") or "Unknown",
            "uploader": data.get("uploader") or data.get("channel") or "",
            "duration": int(data.get("duration") or 0),
            "estimated_bytes": int(est_bytes) if est_bytes else None,
            "thumb_path": str(thumb_path) if thumb_path else "",
            "mode": "",
            "webpage_url": data.get("webpage_url") or self.url,
        }


# ===========================================================================
# BatchPreviewThread
# ===========================================================================

class BatchPreviewThread(QThread):
    progress_signal   = pyqtSignal(str)
    item_result_signal = pyqtSignal(str, dict)   # url, info
    finished_signal   = pyqtSignal(int, int)     # updated, total

    def __init__(self, main_window: "YTDLPGUI", urls: List[str], parent=None):
        super().__init__(parent)
        self.mw = main_window
        self.urls = urls

    def run(self):
        updated = 0
        for u in self.urls:
            try:
                ytdlp = self.mw.get_ytdlp_path()
                fmt, _ = self.mw._build_format_string_for_preview()
                cmd = [ytdlp, "-s", "--dump-json", "--socket-timeout", str(DEFAULT_SOCKET_TIMEOUT)]
                if fmt:
                    cmd += ["-f", fmt]
                if "cda.pl" in u:
                    cmd += ["--no-check-certificate"]
                    if "/vfilm" in u:
                        cda_email = self.mw.cda_email.text().strip()
                        cda_pass  = self.mw.cda_password.text()
                        if cda_email and cda_pass:
                            cmd += ["--username", cda_email, "--password", cda_pass]
                cmd.append(u)
                p = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8",
                    errors="ignore", timeout=25, creationflags=_creationflags(),
                )
                if p.returncode != 0:
                    continue
                lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
                if not lines:
                    continue
                data = json.loads(lines[-1])
                est_bytes = _estimate_bytes(data)
                thumb_url = data.get("thumbnail")
                if not thumb_url and isinstance(data.get("thumbnails"), list) and data["thumbnails"]:
                    thumb_url = data["thumbnails"][-1].get("url")
                thumb_path = _download_thumbnail(data.get("id"), thumb_url)
                info = {
                    "title": data.get("title") or "",
                    "estimated_bytes": int(est_bytes) if est_bytes else None,
                    "thumb_path": str(thumb_path) if thumb_path else "",
                }
                self.item_result_signal.emit(u, info)
                updated += 1
            except Exception as e:
                logger.debug(f"Batch preview failed for {u}: {e}")
        self.finished_signal.emit(updated, len(self.urls))


# ===========================================================================
# TitleFetchThread
# ===========================================================================

class TitleFetchThread(QThread):
    title_signal = pyqtSignal(str, str)   # url, title
    error_signal = pyqtSignal(str, str)   # url, error

    def __init__(self, ytdlp_path: str, url: str, parent=None):
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self.url = url

    def run(self):
        try:
            cmd = [
                self.ytdlp_path, "--get-title", "--simulate",
                "--socket-timeout", str(DEFAULT_SOCKET_TIMEOUT),
            ]
            if "cda.pl" in self.url:
                cmd += ["--no-check-certificate"]
            cmd.append(self.url)
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="ignore", timeout=20, creationflags=_creationflags(),
            )
            if r.returncode == 0 and r.stdout.strip():
                self.title_signal.emit(self.url, r.stdout.strip())
            else:
                self.error_signal.emit(self.url, "Brak tytułu")
        except subprocess.TimeoutExpired:
            self.error_signal.emit(self.url, "Timeout")
        except Exception as e:
            self.error_signal.emit(self.url, str(e))


# ===========================================================================
# Pomocnicze funkcje prywatne
# ===========================================================================

def _estimate_bytes(data: dict):
    # 1. requested_downloads – najbardziej precyzyjne (po wyborze formatu)
    req = data.get("requested_downloads")
    if req and isinstance(req, list):
        s = sum(
            int(p.get("filesize") or p.get("filesize_approx") or 0)
            for p in req
        )
        if s > 0:
            return s

    # 2. requested_formats – DASH: wideo + audio jako osobne strumienie
    req_fmts = data.get("requested_formats")
    if req_fmts and isinstance(req_fmts, list):
        s = sum(
            int(f.get("filesize") or f.get("filesize_approx") or 0)
            for f in req_fmts
        )
        if s > 0:
            return s

    # 3. Globalny filesize na poziomie wideo
    top = data.get("filesize") or data.get("filesize_approx")
    if top:
        return top

    # 4. Przeszukaj listę formats i zsumuj wybrany format wideo + audio
    fmt_id = data.get("format_id", "")
    formats = data.get("formats")
    if formats and isinstance(formats, list):
        # Jeśli format_id to "X+Y" (DASH), zsumuj oba
        ids = set(fmt_id.replace("+", " ").split()) if fmt_id else set()
        if ids:
            s = sum(
                int(f.get("filesize") or f.get("filesize_approx") or 0)
                for f in formats
                if f.get("format_id") in ids
            )
            if s > 0:
                return s
        # Fallback: największy pojedynczy format z listy
        best = max(
            (int(f.get("filesize") or f.get("filesize_approx") or 0) for f in formats),
            default=0,
        )
        if best > 0:
            return best

    return None


def _download_thumbnail(video_id: str, thumb_url: str):
    if not thumb_url:
        return None
    try:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", video_id or "thumb") + ".jpg"
        path = THUMBS_CACHE_DIR / safe
        if not path.exists():
            r = requests.get(thumb_url, timeout=15)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
        return path
    except Exception as e:
        logger.debug(f"Nie udało się pobrać miniatury: {e}")
        return None
