# -*- coding: utf-8 -*-
"""
Główne okno aplikacji YTDLPGUI.

Odpowiada za:
  - budowanie UI (deleguje do app.ui.tabs)
  - zarządzanie kolejką (download_queue, failed_queue)
  - logikę pobierania i ponawiania
  - ustawienia (zapis/odczyt)
  - motyw wizualny (deleguje do app.ui.styles)
"""

import json
import logging
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import (
    DEFAULT_SOCKET_TIMEOUT,
    FFMPEG_BIN_DIR,
    FFMPEG_PATH_LINUX,
    FFMPEG_PATH_WINDOWS,
    LIBS_DIR,
    STRICT_URL_REGEX,
    YTDLP_PATH_LINUX,
    YTDLP_PATH_WINDOWS,
    app_data_base_dir,
    log_dir,
)
from .queue_widget import QueueListWidget
from .threads import (
    BatchPreviewThread,
    CDAStatusCheckThread,
    DownloadFFmpegThread,
    PreviewFetchThread,
    TitleFetchThread,
    UpdateYTDLPThread,
    YTDLPThread,
)
from .ui.styles import (
    build_dark_palette,
    build_dark_stylesheet,
    build_white_palette,
    build_white_stylesheet,
)
from .ui.tabs import (
    APP_VERSION,
    init_about_tab,
    init_advanced_tab,
    init_audio_tab,
    init_playlist_tab,
    init_queue_tab,
    init_settings_tab,
    init_video_tab,
)
from .utils import human_duration, human_size, resource_path

logger = logging.getLogger(__name__)


class YTDLPGUI(QMainWindow):
    """Główne okno aplikacji."""

    # =========================================================
    # Inicjalizacja
    # =========================================================

    def __init__(self):
        super().__init__()

        self.appdata_dir = app_data_base_dir
        self.appdata_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Katalog aplikacji: {self.appdata_dir}")

        self.settings = QSettings(
            str(self.appdata_dir / "settings.ini"), QSettings.Format.IniFormat
        )

        self.current_video_title = "Unknown"
        self.current_processing_url: Optional[str] = None

        # logger nieudanych
        self.failed_log_file = log_dir / "failed_downloads.log"
        self.failed_logger = logging.getLogger("failed_downloads")
        fh = logging.FileHandler(self.failed_log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        self.failed_logger.addHandler(fh)
        self.failed_logger.setLevel(logging.INFO)

        # domyślne ścieżki narzędzi
        self.default_ytdlp_path_fallback = (
            str(YTDLP_PATH_WINDOWS) if os.name == "nt" else str(YTDLP_PATH_LINUX)
        )
        self.default_ffmpeg_path_local_fallback = (
            str(FFMPEG_PATH_WINDOWS) if os.name == "nt" else str(FFMPEG_PATH_LINUX)
        )

        # wątki
        self.thread: Optional[YTDLPThread] = None
        self.update_ytdlp_thread: Optional[UpdateYTDLPThread] = None
        self.download_ffmpeg_thread: Optional[DownloadFFmpegThread] = None
        self.cda_check_thread: Optional[CDAStatusCheckThread] = None
        self.preview_thread: Optional[PreviewFetchThread] = None
        self.batch_preview_thread: Optional[BatchPreviewThread] = None
        self.title_thread: Optional[TitleFetchThread] = None

        # kolejki
        self.download_queue: List[str] = []
        self.failed_queue: List[str] = []
        self.item_retry_counts: Dict[str, int] = {}
        self.pending_queue_check = False
        self.failed_dialog_shown = False
        self._user_stopped = False          # True gdy użytkownik kliknął Stop

        # monitor schowka
        self._clipboard_prev = ""
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setInterval(1200)
        self.clipboard_timer.timeout.connect(self._poll_clipboard)

        self.init_ui()
        self.load_settings(initial=True)
        self.apply_style()

        self.setEnabled(False)
        self.output_text.append("Sprawdzam zależności...")
        self.check_ytdlp_version()

    # =========================================================
    # Dostęp do ścieżek narzędzi
    # =========================================================

    def get_ytdlp_path(self) -> str:
        p = self.settings.value("ytdlp_path", "", type=str).strip()
        return p if p else self.default_ytdlp_path_fallback

    def get_ffmpeg_path(self) -> str:
        p = self.settings.value("ffmpeg_path", "", type=str).strip()
        return p if p else self.default_ffmpeg_path_local_fallback

    def get_user_downloads_path(self) -> str:
        try:
            p = Path.home() / "Downloads"
            return str(p) if p.exists() else str(Path.home())
        except Exception as e:
            logger.error(f"Nie udało się uzyskać ścieżki Pobrane: {e}")
            return str(Path.home())

    # =========================================================
    # Motywy
    # =========================================================

    def is_dark_theme(self) -> bool:
        return self.settings.value("theme", "Dark", type=str) == "Dark"

    def apply_style(self):
        if self.is_dark_theme():
            self.apply_dark_style()
        else:
            self.apply_white_style()

    def apply_dark_style(self):
        palette = build_dark_palette()
        self.setPalette(palette)
        self.setStyleSheet(build_dark_stylesheet(palette))

    def apply_white_style(self):
        palette = build_white_palette()
        self.setPalette(palette)
        self.setStyleSheet(build_white_stylesheet(palette))

    def change_theme(self, _index):
        theme = self.theme_combo.currentText()
        self.settings.setValue("theme", theme)
        self.apply_style()
        for i in range(self.queue_list.count()):
            it = self.queue_list.item(i)
            st = it.data(self.queue_list.ROLE_STATUS) or self.queue_list.STATUS_NORMAL
            self.queue_list.mark_status(it, st, self.is_dark_theme())

    # =========================================================
    # Inicjalizacja UI
    # =========================================================

    def init_ui(self):
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setWindowTitle("Video Downloader")
        self.setGeometry(100, 100, 1020, 820)

        self.setStatusBar(QStatusBar(self))

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- URL group ---
        url_group = QGroupBox("URL wideo/playlisty")
        url_layout = QVBoxLayout()
        url_row = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Wprowadź URL YouTube, CDA lub playlisty...")
        url_row.addWidget(self.url_input, 4)

        style = self.style()
        paste_btn = QPushButton(" Wklej")
        paste_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        paste_btn.clicked.connect(self.paste_from_clipboard)
        url_row.addWidget(paste_btn, 1)

        paste_add_btn = QPushButton(" Wklej i Dodaj")
        paste_add_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        paste_add_btn.setObjectName("pasteAndAddButton")
        paste_add_btn.clicked.connect(self.paste_and_add_to_queue)
        url_row.addWidget(paste_add_btn, 1)

        preview_btn = QPushButton(" Podgląd")
        preview_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
        preview_btn.setToolTip("Pobierz tytuł, miniaturę i szacowany rozmiar dla aktualnych opcji.")
        preview_btn.clicked.connect(self.preview_current_url)
        url_row.addWidget(preview_btn, 1)

        add_multi_btn = QPushButton(" Dodaj wiele...")
        add_multi_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        add_multi_btn.setToolTip("Dodaj wiele URL-i naraz.")
        add_multi_btn.clicked.connect(self.add_multiple_urls_dialog)
        url_row.addWidget(add_multi_btn, 1)

        url_layout.addLayout(url_row)

        # panel podglądu
        preview_panel = QHBoxLayout()
        self.preview_thumb = QLabel()
        self.preview_thumb.setFixedSize(200, 112)
        self.preview_thumb.setScaledContents(True)
        self.preview_title    = QLabel("Tytuł: -")
        self.preview_title.setWordWrap(True)
        self.preview_uploader = QLabel("Kanał: -")
        self.preview_duration = QLabel("Czas trwania: -")
        self.preview_size     = QLabel("Szacowany rozmiar: -")
        info_col = QVBoxLayout()
        for lbl in (self.preview_title, self.preview_uploader,
                    self.preview_duration, self.preview_size):
            info_col.addWidget(lbl)
        preview_panel.addWidget(self.preview_thumb)
        preview_panel.addLayout(info_col)
        url_layout.addLayout(preview_panel)
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)

        # --- Zakładki ---
        self.tabs = QTabWidget()
        self.video_tab_widget    = QWidget()
        self.audio_tab_widget    = QWidget()
        self.playlist_tab_widget = QWidget()
        self.queue_tab_widget    = QWidget()
        self.advanced_tab_widget = QWidget()
        self.settings_tab_widget = QWidget()
        self.about_tab_widget    = QWidget()

        init_video_tab(self, self.video_tab_widget)
        init_audio_tab(self, self.audio_tab_widget)
        init_playlist_tab(self, self.playlist_tab_widget)
        init_queue_tab(self, self.queue_tab_widget)
        init_advanced_tab(self, self.advanced_tab_widget)
        init_settings_tab(self, self.settings_tab_widget)
        init_about_tab(self, self.about_tab_widget)

        self.tabs.addTab(self.video_tab_widget,    "Wideo")
        self.tabs.addTab(self.audio_tab_widget,    "Audio")
        self.tabs.addTab(self.playlist_tab_widget, "Playlista")
        self.tabs.addTab(self.queue_tab_widget,    "Kolejka")
        self.tabs.addTab(self.advanced_tab_widget, "Zaawansowane")
        self.tabs.addTab(self.settings_tab_widget, "Ustawienia")
        self.tabs.addTab(self.about_tab_widget,    "O programie")
        main_layout.addWidget(self.tabs)

        # --- Wyjście i postęp ---
        out_group = QGroupBox("Wyjście i postęp")
        out_layout = QVBoxLayout()
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        font = QFont("Consolas" if platform.system() == "Windows" else "Monospace", 9)
        self.output_text.setFont(font)
        out_layout.addWidget(self.output_text)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFormat("%p%")
        out_layout.addWidget(self.progress_bar)

        actions_row = QHBoxLayout()
        open_out_btn = QPushButton(" Otwórz folder wyjściowy")
        open_out_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        open_out_btn.clicked.connect(self.open_output_folder)
        actions_row.addWidget(open_out_btn)
        scan_btn = QPushButton(" Skanuj tytuły i rozmiary (lista)")
        scan_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        scan_btn.clicked.connect(self.scan_queue_metadata)
        actions_row.addWidget(scan_btn)
        actions_row.addStretch()
        out_layout.addLayout(actions_row)
        out_group.setLayout(out_layout)
        main_layout.addWidget(out_group)

        # --- Przyciski główne ---
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Pobierz i rozpocznij kolejkę")
        self.download_btn.setObjectName("downloadButton")
        self.download_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.download_btn.clicked.connect(self.start_download)
        btn_row.addWidget(self.download_btn)

        self.stop_btn = QPushButton("Zatrzymaj pobieranie")
        self.stop_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("Wyczyść konsolę")
        self.clear_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        self.clear_btn.clicked.connect(self.clear_output)
        btn_row.addWidget(self.clear_btn)

        main_layout.addLayout(btn_row)
        self._install_shortcuts()

    def _install_shortcuts(self):
        del_act = QAction(self); del_act.setShortcut("Delete")
        del_act.triggered.connect(self.remove_from_queue); self.addAction(del_act)
        enter_act = QAction(self); enter_act.setShortcut("Return")
        enter_act.triggered.connect(lambda: self.start_download(add_current_url=True))
        self.addAction(enter_act)
        f2_act = QAction(self); f2_act.setShortcut("F2")
        f2_act.triggered.connect(self.edit_queue_item); self.addAction(f2_act)

    # =========================================================
    # Zależności (yt-dlp + ffmpeg)
    # =========================================================

    def check_ytdlp_version(self):
        path = self.ytdlp_path_input.text().strip()
        self.update_ytdlp_thread = UpdateYTDLPThread(path, self, self)
        self.update_ytdlp_thread.finished_signal.connect(self.handle_ytdlp_update)
        self.update_ytdlp_thread.progress_signal.connect(self.update_progress)
        self.update_ytdlp_thread.progress_percent_signal.connect(self.update_progress_percent)
        self.update_ytdlp_thread.progress_detailed_signal.connect(self.update_detailed_progress)
        self.update_ytdlp_thread.start()
        self.pending_queue_check = True

    def handle_ytdlp_update(self, success, message):
        self.output_text.append(message)
        self.ytdlp_path_input.setText(self.get_ytdlp_path())
        self._clear_detailed_active()
        self.check_ffmpeg_present_or_download()

    def check_ffmpeg_present_or_download(self):
        path = self.ffmpeg_path.text().strip()
        self.download_ffmpeg_thread = DownloadFFmpegThread(path, self, self)
        self.download_ffmpeg_thread.finished_signal.connect(self.handle_ffmpeg_download)
        self.download_ffmpeg_thread.progress_signal.connect(self.update_progress)
        self.download_ffmpeg_thread.progress_percent_signal.connect(self.update_progress_percent)
        self.download_ffmpeg_thread.progress_detailed_signal.connect(self.update_detailed_progress)
        self.download_ffmpeg_thread.start()

    def handle_ffmpeg_download(self, success, message):
        self.output_text.append(message)
        self.ffmpeg_path.setText(self.get_ffmpeg_path())
        self._clear_detailed_active()
        self.dependency_checks_finished()

    def dependency_checks_finished(self):
        self.setEnabled(True)
        self.output_text.append("Sprawdzanie zależności zakończone.")
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Wszystkie zależności pobrane, gotowy!")
        if self.pending_queue_check:
            self.ask_resume_queue()
            self.pending_queue_check = False
        self._refresh_about_versions()

    def _clear_detailed_active(self):
        if hasattr(self.progress_bar, "_detailed_active"):
            delattr(self.progress_bar, "_detailed_active")

    def _refresh_about_versions(self):
        """Aktualizuje etykiety wersji w zakładce 'O programie'."""
        import subprocess as _sp
        # yt-dlp
        try:
            ytdlp = self.get_ytdlp_path()
            r = _sp.run([ytdlp, "--version"], capture_output=True, text=True,
                        timeout=5, encoding="utf-8")
            self._about_ytdlp_lbl.setText(r.stdout.strip() or "brak")
        except Exception:
            self._about_ytdlp_lbl.setText("brak")
        # ffmpeg
        try:
            ffmpeg = self.get_ffmpeg_path() or "ffmpeg"
            r = _sp.run([ffmpeg, "-version"], capture_output=True, text=True,
                        timeout=5, encoding="utf-8")
            import re as _re
            m = _re.search(r"ffmpeg version (\S+)", r.stdout or r.stderr)
            self._about_ffmpeg_lbl.setText(m.group(1) if m else "brak")
        except Exception:
            self._about_ffmpeg_lbl.setText("brak")

    # =========================================================
    # Aktualizacje progress bar
    # =========================================================

    def update_progress(self, text: str):
        self.output_text.append(text)
        if sb := self.output_text.verticalScrollBar():
            sb.setValue(sb.maximum())
        m = re.search(r"\[info\]\s+Title:\s+(.+)", text)
        if m:
            self.current_video_title = m.group(1).strip()

    def update_progress_percent(self, percent: int):
        percent = max(0, min(100, percent))
        self.progress_bar.setValue(percent)
        if not hasattr(self.progress_bar, "_detailed_active"):
            self.progress_bar.setFormat("%p%")

    def update_detailed_progress(self, name: str, percent, dl: str, total: str):
        try:
            if isinstance(percent, str):
                clean = "".join(c for c in percent if c.isdigit() or c == ".")
                percent = float(clean) if clean else 0.0
            elif percent is None:
                percent = 0.0
            percent = max(0.0, min(100.0, float(percent)))
            self.progress_bar.setValue(int(percent))
            self.progress_bar._detailed_active = True
            if dl != "N/A" and total != "N/A":
                self.progress_bar.setFormat(f"{name} | {dl} / {total} | {int(percent)}%")
            else:
                self.progress_bar.setFormat(f"{name} | {int(percent)}%")
        except Exception as e:
            logger.warning(f"Błąd konwersji postępu: {e}")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"Pobieranie {name}...")

    def clear_output(self):
        self.output_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

    # =========================================================
    # UI – akcje przycisków górnych
    # =========================================================

    def update_remove_btn_state(self):
        has = bool(self.queue_list.selectedItems())
        self.remove_btn.setEnabled(has)
        self.edit_btn.setEnabled(has)

    def toggle_password_visibility(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password.setEchoMode(mode)
        icon = "icons/eye-off.png" if checked else "icons/eye.png"
        self.password_show_btn.setIcon(QIcon(icon))
        self.password.setFocus()

    def toggle_cda_password_visibility(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.cda_password.setEchoMode(mode)
        icon = "icons/eye-off.png" if checked else "icons/eye.png"
        self.cda_password_show_btn.setIcon(QIcon(icon))
        self.cda_password.setFocus()

    def run_cda_status_check(self):
        if self.cda_check_thread and self.cda_check_thread.isRunning():
            return
        ytdlp = self.get_ytdlp_path()
        if ytdlp != "yt-dlp" and not Path(ytdlp).exists():
            self.cda_status_label.setText("<font color='red'>Status: Błąd - Nie znaleziono yt-dlp</font>")
            QMessageBox.critical(self, "Błąd YT-DLP", f"Plik YT-DLP nie znaleziony: '{ytdlp}'.")
            return
        email = self.cda_email.text().strip()
        password = self.cda_password.text()
        if not email or not password:
            QMessageBox.warning(self, "Brak danych", "Wprowadź email i hasło CDA Premium.")
            return
        self.check_cda_status_btn.setEnabled(False)
        self.cda_status_label.setText("Status: Sprawdzanie...")
        self.cda_check_thread = CDAStatusCheckThread(email, password, ytdlp, self, self)
        self.cda_check_thread.finished_signal.connect(self.handle_cda_status_result)
        self.cda_check_thread.start()

    def handle_cda_status_result(self, success: bool, message: str):
        color = "green" if success else "red"
        self.cda_status_label.setText(f"<font color='{color}'><b>Status: {message}</b></font>")
        self.check_cda_status_btn.setEnabled(True)

    def paste_from_clipboard(self):
        try:
            cb = QApplication.clipboard()
            text = cb.text().strip() if cb else ""
            if not text:
                QMessageBox.warning(self, "Schowek pusty", "Schowek jest pusty.")
                return
            if STRICT_URL_REGEX.match(text):
                if not text.lower().startswith(("http://", "https://")):
                    text = "https://" + text
                self.url_input.setText(text)
                if self.auto_add_to_queue.isChecked():
                    self.add_to_queue()
            else:
                QMessageBox.warning(self, "Błędny URL", "URL nie wygląda na poprawny.")
        except Exception as e:
            logger.error(f"Błąd wklejania: {e}", exc_info=True)
            QMessageBox.critical(self, "Błąd", f"Nie udało się wkleić: {e}")

    def paste_and_add_to_queue(self):
        try:
            cb = QApplication.clipboard()
            text = cb.text().strip() if cb else ""
            if not text:
                QMessageBox.warning(self, "Schowek pusty", "Schowek jest pusty.")
                return
            self.url_input.setText(text)
            existing = {self.queue_list.item(i).text().strip()
                        for i in range(self.queue_list.count())}
            existing |= set(self.download_queue + self.failed_queue)
            if text in existing:
                QMessageBox.information(self, "Duplikat URL", f"URL już w kolejce:\n{text}")
                return
            self.add_to_queue()
        except Exception as e:
            logger.error(f"Błąd wklej+dodaj: {e}", exc_info=True)
            QMessageBox.critical(self, "Błąd", f"Nie udało się wkleić i dodać: {e}")

    def open_output_folder(self):
        path = (
            self.output_path.text().strip()
            or self.audio_output_path.text().strip()
            or self.default_output_path.text().strip()
            or self.get_user_downloads_path()
        )
        if not path:
            return
        if os.name == "nt":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])

    def add_multiple_urls_dialog(self):
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Dodaj wiele URL")
        dlg.setLabelText("Wklej wiele URL (jeden w linii):")
        dlg.resize(600, dlg.height())
        if dlg.exec() and dlg.textValue().strip():
            urls = [ln.strip() for ln in dlg.textValue().splitlines() if ln.strip()]
            self._add_urls_list(urls)

    # =========================================================
    # Przeglądanie ścieżek
    # =========================================================

    def browse_output_path(self):
        start = self.output_path.text().strip() or self.default_output_path.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Wybierz katalog wyjściowy (Wideo)", start)
        if d:
            self.output_path.setText(d)

    def browse_audio_output_path(self):
        start = self.audio_output_path.text().strip() or self.default_output_path.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Wybierz katalog wyjściowy (Audio)", start)
        if d:
            self.audio_output_path.setText(d)

    def browse_archive_file(self):
        fd = QFileDialog(self)
        fd.setFileMode(QFileDialog.FileMode.AnyFile)
        fd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        fd.setWindowTitle("Wybierz plik archiwum")
        cur = self.archive_file.text().strip()
        fd.selectFile(cur if cur else str(self.appdata_dir / "archive.txt"))
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self.archive_file.setText(files[0])

    def browse_ytdlp_path(self):
        fd = QFileDialog(self)
        fd.setFileMode(QFileDialog.FileMode.ExistingFile)
        fd.setWindowTitle("Wybierz plik yt-dlp")
        cur = self.ytdlp_path_input.text().strip()
        start = str(Path(cur).parent) if cur and Path(cur).is_absolute() else str(Path.home())
        if not Path(start).exists() and LIBS_DIR.exists():
            start = str(LIBS_DIR)
        fd.setDirectory(start)
        if os.name == "nt":
            fd.setNameFilter("Wykonywalne (*.exe);;Wszystkie pliki (*)")
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self.ytdlp_path_input.setText(files[0])

    def browse_ffmpeg_path(self):
        fd = QFileDialog(self)
        fd.setFileMode(QFileDialog.FileMode.ExistingFile)
        fd.setWindowTitle("Wybierz plik ffmpeg")
        cur = self.ffmpeg_path.text().strip()
        if cur and Path(cur).is_absolute():
            start = str(Path(cur).parent)
        elif FFMPEG_BIN_DIR.exists():
            start = str(FFMPEG_BIN_DIR)
        elif LIBS_DIR.exists():
            start = str(LIBS_DIR)
        else:
            start = str(Path.home())
        fd.setDirectory(start)
        if os.name == "nt":
            fd.setNameFilter("Wykonywalne (*.exe);;Wszystkie pliki (*)")
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self.ffmpeg_path.setText(files[0])

    def browse_default_output_path(self):
        start = self.default_output_path.text().strip() or self.get_user_downloads_path()
        d = QFileDialog.getExistingDirectory(self, "Wybierz domyślny katalog wyjściowy", start)
        if d:
            self.default_output_path.setText(d)

    # =========================================================
    # Zarządzanie kolejką
    # =========================================================

    def _add_urls_list(self, urls: List[str]):
        existing = set(self.download_queue + self.failed_queue)
        existing |= {self.queue_list.item(i).text().strip()
                     for i in range(self.queue_list.count())}
        added = []
        for url in urls:
            if not url.lower().startswith(("http://", "https://")):
                url = "https://" + url
            if not STRICT_URL_REGEX.match(url) or url in existing:
                continue
            self.download_queue.append(url)
            item = QListWidgetItem(url)
            item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
            self.queue_list.addItem(item)
            existing.add(url)
            added.append(url)
        if added:
            self.save_queue()
            self.output_text.append(f"Dodano {len(added)} URL do kolejki.")
            self.tabs.setCurrentWidget(self.queue_tab_widget)
            self._start_batch_preview(added)

    def add_to_queue(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Błąd", "Wpisz URL aby dodać do kolejki.")
            return
        existing = set(self.download_queue + self.failed_queue)
        existing |= {self.queue_list.item(i).text().strip()
                     for i in range(self.queue_list.count())}

        if url in existing:
            if url in self.failed_queue:
                reply = QMessageBox.question(
                    self, "URL w nieudanych",
                    f"URL już jest w nieudanych.\nPrzenieść do kolejki?\n\n{url}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.failed_queue.remove(url)
                    for i in range(self.queue_list.count()):
                        it = self.queue_list.item(i)
                        if it and it.text().strip() == url:
                            self.queue_list.mark_status(
                                it, self.queue_list.STATUS_NORMAL, self.is_dark_theme()
                            )
                            break
                    if url not in self.download_queue:
                        self.download_queue.append(url)
                    self.save_queue()
                    self.url_input.clear()
            else:
                QMessageBox.information(self, "Duplikat URL", f"URL już w kolejce:\n{url}")
            return

        if not STRICT_URL_REGEX.match(url):
            QMessageBox.warning(self, "Błąd", "Podany URL nie wygląda na poprawny.")
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url

        self.download_queue.append(url)
        item = QListWidgetItem(url)
        item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
        self.queue_list.addItem(item)
        self.url_input.clear()
        self.save_queue()
        self.tabs.setCurrentWidget(self.queue_tab_widget)
        self._start_batch_preview([url])

    def remove_from_queue(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            QMessageBox.warning(self, "Błąd", "Wybierz element do usunięcia.")
            return
        for idx in sorted([self.queue_list.row(it) for it in sel], reverse=True):
            if 0 <= idx < self.queue_list.count():
                text = self.queue_list.item(idx).text().strip()
                if text in self.download_queue:
                    self.download_queue.remove(text)
                self.queue_list.takeItem(idx)
        self.save_queue()

    def move_queue_item_up(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            return
        item = sel[0]; idx = self.queue_list.row(item)
        if idx > 0:
            if idx < len(self.download_queue):
                url = self.download_queue.pop(idx)
                self.download_queue.insert(idx - 1, url)
            self.queue_list.takeItem(idx)
            self.queue_list.insertItem(idx - 1, item)
            self.queue_list.setCurrentItem(item)
            self.save_queue()

    def move_queue_item_down(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            return
        item = sel[0]; idx = self.queue_list.row(item)
        if idx < self.queue_list.count() - 1:
            if idx < len(self.download_queue):
                url = self.download_queue.pop(idx)
                self.download_queue.insert(idx + 1, url)
            self.queue_list.takeItem(idx)
            self.queue_list.insertItem(idx + 1, item)
            self.queue_list.setCurrentItem(item)
            self.save_queue()

    def edit_queue_item(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            QMessageBox.warning(self, "Błąd", "Wybierz element do edycji.")
            return
        item = sel[0]; idx = self.queue_list.row(item)
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Edytuj URL")
        dlg.setLabelText("Wprowadź nowy URL:")
        dlg.setTextValue(item.text())
        dlg.resize(500, dlg.height())
        if dlg.exec():
            new_url = dlg.textValue().strip()
            if new_url and STRICT_URL_REGEX.match(new_url):
                if not new_url.lower().startswith(("http://", "https://")):
                    new_url = "https://" + new_url
                item.setText(new_url)
                if 0 <= idx < len(self.download_queue):
                    self.download_queue[idx] = new_url
                self.save_queue()
                self._start_batch_preview([new_url])
            else:
                QMessageBox.warning(self, "Błąd edycji", "URL nie wygląda na poprawny.")

    def clear_queue(self):
        box = QMessageBox(
            QMessageBox.Icon.Question, "Wyczyść kolejkę",
            "Czy na pewno chcesz wyczyścić kolejkę?", parent=self,
        )
        yes = box.addButton("Tak", QMessageBox.ButtonRole.YesRole)
        no  = box.addButton("Nie", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() == yes:
            self.queue_list.clear()
            self.download_queue.clear()
            self.failed_queue.clear()
            self.item_retry_counts.clear()
            self.failed_dialog_shown = False
            self.save_queue()

    def _sync_download_queue_from_widget(self):
        new_order = [self.queue_list.item(i).text().strip()
                     for i in range(self.queue_list.count())
                     if self.queue_list.item(i)]
        self.download_queue = [u for u in new_order if u in self.download_queue or u not in self.failed_queue]
        self.save_queue()

    def save_queue(self):
        queue_file = self.appdata_dir / "queue.json"
        try:
            queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(queue_file, "w", encoding="utf-8") as f:
                json.dump({
                    "download_queue": self.download_queue,
                    "failed_queue": self.failed_queue,
                    "retry_counts": self.item_retry_counts,
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Błąd zapisu kolejki: {e}", exc_info=True)

    def load_queue(self) -> bool:
        queue_file = self.appdata_dir / "queue.json"
        if not queue_file.exists():
            return False
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                data = json.loads(content) if content else {}

            if isinstance(data, dict):
                self.download_queue    = [u.strip() for u in data.get("download_queue", []) if u and u.strip()]
                self.failed_queue      = [u.strip() for u in data.get("failed_queue", []) if u and u.strip()]
                self.item_retry_counts = data.get("retry_counts", {})
            elif isinstance(data, list):
                self.download_queue    = [u.strip() for u in data if u and u.strip()]
                self.failed_queue      = []
                self.item_retry_counts = {}
            else:
                self.download_queue, self.failed_queue, self.item_retry_counts = [], [], {}
                return False

            self.queue_list.clear()
            all_urls = list(self.download_queue)
            for u in self.failed_queue:
                if u not in all_urls:
                    all_urls.append(u)

            for url in all_urls:
                item = QListWidgetItem(url)
                if url in self.failed_queue:
                    self.queue_list.mark_status(item, self.queue_list.STATUS_FAILED, self.is_dark_theme())
                else:
                    item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
                self.queue_list.addItem(item)

            if all_urls:
                self._start_batch_preview(all_urls)
            return True
        except Exception as e:
            logger.error(f"Błąd wczytywania kolejki: {e}", exc_info=True)
            QMessageBox.warning(self, "Błąd wczytywania", f"Nie udało się wczytać kolejki:\n{e}")
            return False

    def ask_resume_queue(self):
        self.load_queue()
        total = len(self.download_queue) + len(self.failed_queue)
        if total > 0:
            failed_info = f" ({len(self.failed_queue)} nieudanych)" if self.failed_queue else ""
            box = QMessageBox(
                QMessageBox.Icon.Question, "Kontynuuj kolejkę",
                f"Wykryto zapisaną kolejkę ({len(self.download_queue)} normalnych{failed_info}).\n"
                "Czy chcesz kontynuować pobieranie?",
                parent=self,
            )
            yes = box.addButton("Tak", QMessageBox.ButtonRole.YesRole)
            no  = box.addButton("Nie", QMessageBox.ButtonRole.NoRole)
            box.setDefaultButton(yes)
            box.exec()
            if box.clickedButton() == yes:
                self.tabs.setCurrentWidget(self.queue_tab_widget)
                if self.download_queue or self.failed_queue:
                    self.start_download(add_current_url=False)
            else:
                self.clear_queue()

    # =========================================================
    # Ustawienia
    # =========================================================

    def save_settings(self):
        s = self.settings
        s.setValue("ytdlp_path",  self.ytdlp_path_input.text().strip().replace("\\", "/"))
        s.setValue("ffmpeg_path", self.ffmpeg_path.text().strip().replace("\\", "/"))
        s.setValue("check_ytdlp_updates",  self.check_ytdlp_updates.isChecked())
        s.setValue("auto_download_ffmpeg", self.auto_download_ffmpeg.isChecked())
        s.setValue("cda_email",    self.cda_email.text().strip())
        s.setValue("cda_password", self.cda_password.text())
        s.setValue("default_output_path", self.default_output_path.text().strip())
        s.setValue("default_template",    self.default_template.text().strip())
        s.setValue("auto_add_to_queue",   self.auto_add_to_queue.isChecked())
        s.setValue("theme", self.theme_combo.currentText())

        # wideo
        s.setValue("video_format",    self.video_format.currentText())
        s.setValue("video_quality",   self.video_quality.currentIndex())
        s.setValue("video_codec",     self.video_codec.currentText())
        s.setValue("embed_thumbnails", self.embed_thumbnails.isChecked())
        s.setValue("embed_subs",       self.embed_subs.isChecked())
        s.setValue("output_template",  self.output_template.text().strip())
        s.setValue("output_path",      self.output_path.text().strip())
        s.setValue("limit_rate",       self.limit_rate.text().strip())
        s.setValue("retries",          self.retries.value())
        s.setValue("extract_audio",    self.extract_audio.isChecked())
        s.setValue("keep_video",       self.keep_video.isChecked())
        s.setValue("write_subs",       self.write_subs.isChecked())
        s.setValue("write_auto_subs",  self.write_auto_subs.isChecked())
        s.setValue("write_info_json",  self.write_info_json.isChecked())

        # audio
        s.setValue("audio_format",         self.audio_format.currentText())
        s.setValue("audio_quality",        self.audio_quality.currentIndex())
        s.setValue("add_metadata",         self.add_metadata.isChecked())
        s.setValue("embed_thumbnail",      self.embed_thumbnail.isChecked())
        s.setValue("audio_output_template", self.audio_output_template.text().strip())
        s.setValue("audio_output_path",    self.audio_output_path.text().strip())
        s.setValue("prefer_ffmpeg",        self.prefer_ffmpeg.isChecked())

        # playlista
        s.setValue("playlist_start",   self.playlist_start.value())
        s.setValue("playlist_end",     self.playlist_end.value())
        s.setValue("playlist_items",   self.playlist_items.text().strip())
        s.setValue("playlist_reverse", self.playlist_reverse.isChecked())
        s.setValue("playlist_random",  self.playlist_random.isChecked())
        s.setValue("use_archive",      self.use_archive.isChecked())
        s.setValue("archive_file",     self.archive_file.text().strip())

        # sieć / auth
        s.setValue("proxy",          self.proxy.text().strip())
        s.setValue("source_address", self.source_address.text().strip())
        s.setValue("force_ipv4",     self.force_ipv4.isChecked())
        s.setValue("force_ipv6",     self.force_ipv6.isChecked())
        s.setValue("username",       self.username.text().strip())
        s.setValue("password",       self.password.text())
        s.setValue("twofactor",      self.twofactor.text().strip())
        s.setValue("video_password", self.video_password.text())

        # zaawansowane
        s.setValue("extract_audio_adv",  self.extract_audio_adv.isChecked())
        s.setValue("audio_format_adv",   self.audio_format_adv.currentText())
        s.setValue("audio_quality_adv",  self.audio_quality_adv.currentIndex())
        s.setValue("keep_video_adv",     self.keep_video_adv.isChecked())
        s.setValue("recode_video",       self.recode_video.currentText())
        s.setValue("postprocessor_args", self.postprocessor_args.text().strip())
        s.setValue("custom_ytdlp_args", self.custom_ytdlp_args.text().strip())
        s.setValue("ignore_errors",      self.ignore_errors.isChecked())
        s.setValue("no_warnings",        self.no_warnings.isChecked())
        s.setValue("quiet",              self.quiet.isChecked())
        s.setValue("no_color",           self.no_color.isChecked())
        s.setValue("simulate",           self.simulate.isChecked())
        s.setValue("skip_download",      self.skip_download.isChecked())
        s.setValue("max_retry_per_item", self.max_retry_per_item.value())
        s.setValue("enable_clipboard_monitor", self.enable_clipboard_monitor.isChecked())

        s.sync()
        if self.enable_clipboard_monitor.isChecked():
            if not self.clipboard_timer.isActive():
                self.clipboard_timer.start()
        else:
            self.clipboard_timer.stop()
        logger.info("Ustawienia zapisane.")

    def load_settings(self, initial: bool = False):
        s = self.settings
        logger.info("Wczytuję ustawienia...")

        self.check_ytdlp_updates.setChecked(s.value("check_ytdlp_updates", True, type=bool))
        self.auto_download_ffmpeg.setChecked(s.value("auto_download_ffmpeg", True, type=bool))

        saved_out = s.value("default_output_path", "", type=str).strip()
        self.default_output_path.setText(saved_out or self.get_user_downloads_path())
        self.default_template.setText(s.value("default_template", "%(title)s.%(ext)s", type=str).strip())
        self.auto_add_to_queue.setChecked(s.value("auto_add_to_queue", False, type=bool))

        theme = s.value("theme", "Dark", type=str)
        idx = self.theme_combo.findText(theme)
        self.theme_combo.setCurrentIndex(idx if idx != -1 else 0)

        self.ytdlp_path_input.setText(self.get_ytdlp_path())
        self.ffmpeg_path.setText(self.get_ffmpeg_path())
        self.cda_email.setText(s.value("cda_email", "", type=str).strip())
        self.cda_password.setText(s.value("cda_password", "", type=str))

        self.video_format.setCurrentText(s.value("video_format", "mp4", type=str))
        self.video_quality.setCurrentIndex(s.value("video_quality", 0, type=int))
        self.video_codec.setCurrentText(s.value("video_codec", "auto", type=str))
        self.embed_thumbnails.setChecked(s.value("embed_thumbnails", True, type=bool))
        self.embed_subs.setChecked(s.value("embed_subs", False, type=bool))

        tmpl = s.value("output_template", "", type=str).strip()
        self.output_template.setText(tmpl or self.default_template.text())
        out_p = s.value("output_path", "", type=str).strip()
        self.output_path.setText(out_p or self.default_output_path.text())
        self.limit_rate.setText(s.value("limit_rate", "", type=str).strip())
        self.retries.setValue(s.value("retries", 10, type=int))
        self.extract_audio.setChecked(s.value("extract_audio", False, type=bool))
        self.keep_video.setChecked(s.value("keep_video", False, type=bool))
        self.write_subs.setChecked(s.value("write_subs", False, type=bool))
        self.write_auto_subs.setChecked(s.value("write_auto_subs", False, type=bool))
        self.write_info_json.setChecked(s.value("write_info_json", False, type=bool))

        self.audio_format.setCurrentText(s.value("audio_format", "najlepszy", type=str))
        try:
            self.audio_quality.setCurrentIndex(int(s.value("audio_quality", 0)))
        except Exception:
            self.audio_quality.setCurrentIndex(0)
        self.add_metadata.setChecked(s.value("add_metadata", True, type=bool))
        self.embed_thumbnail.setChecked(s.value("embed_thumbnail", True, type=bool))
        at = s.value("audio_output_template", "", type=str).strip()
        self.audio_output_template.setText(at or self.default_template.text())
        ap = s.value("audio_output_path", "", type=str).strip()
        self.audio_output_path.setText(ap or self.default_output_path.text())
        self.prefer_ffmpeg.setChecked(s.value("prefer_ffmpeg", False, type=bool))

        self.playlist_start.setValue(s.value("playlist_start", 1, type=int))
        self.playlist_end.setValue(s.value("playlist_end", 0, type=int))
        self.playlist_items.setText(s.value("playlist_items", "", type=str).strip())
        self.playlist_reverse.setChecked(s.value("playlist_reverse", False, type=bool))
        self.playlist_random.setChecked(s.value("playlist_random", False, type=bool))
        self.use_archive.setChecked(s.value("use_archive", False, type=bool))
        arch = s.value("archive_file", "", type=str).strip()
        self.archive_file.setText(arch or str(self.appdata_dir / "archive.txt"))
        (self.appdata_dir / "archive.txt").parent.mkdir(parents=True, exist_ok=True)

        self.proxy.setText(s.value("proxy", "", type=str).strip())
        self.source_address.setText(s.value("source_address", "", type=str).strip())
        self.force_ipv4.setChecked(s.value("force_ipv4", False, type=bool))
        self.force_ipv6.setChecked(s.value("force_ipv6", False, type=bool))
        self.username.setText(s.value("username", "", type=str).strip())
        self.password.setText(s.value("password", "", type=str))
        self.twofactor.setText(s.value("twofactor", "", type=str).strip())
        self.video_password.setText(s.value("video_password", "", type=str))

        self.extract_audio_adv.setChecked(s.value("extract_audio_adv", False, type=bool))
        self.audio_format_adv.setCurrentText(s.value("audio_format_adv", "najlepszy", type=str))
        try:
            self.audio_quality_adv.setCurrentIndex(int(s.value("audio_quality_adv", 0)))
        except Exception:
            self.audio_quality_adv.setCurrentIndex(0)
        self.keep_video_adv.setChecked(s.value("keep_video_adv", False, type=bool))
        self.recode_video.setCurrentText(s.value("recode_video", "Nie przetwarzaj", type=str))
        self.postprocessor_args.setText(s.value("postprocessor_args", "", type=str).strip())
        self.custom_ytdlp_args.setText(s.value("custom_ytdlp_args", "", type=str).strip())
        self.ignore_errors.setChecked(s.value("ignore_errors", False, type=bool))
        self.no_warnings.setChecked(s.value("no_warnings", False, type=bool))
        self.quiet.setChecked(s.value("quiet", False, type=bool))
        self.no_color.setChecked(s.value("no_color", False, type=bool))
        self.simulate.setChecked(s.value("simulate", False, type=bool))
        self.skip_download.setChecked(s.value("skip_download", False, type=bool))
        self.max_retry_per_item.setValue(s.value("max_retry_per_item", 2, type=int))
        self.enable_clipboard_monitor.setChecked(s.value("enable_clipboard_monitor", False, type=bool))

        if self.enable_clipboard_monitor.isChecked():
            self.clipboard_timer.start()
        else:
            self.clipboard_timer.stop()

        if not initial:
            QMessageBox.information(self, "Ustawienia wczytane", "Ustawienia zostały wczytane.")

    def reset_settings(self):
        r = QMessageBox.question(
            self, "Resetuj ustawienia",
            "Czy na pewno chcesz zresetować ustawienia do domyślnych?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            self.settings.clear()
            self.default_output_path.setText(self.get_user_downloads_path())
            self.default_template.setText("%(title)s.%(ext)s")
            self.archive_file.setText(str(self.appdata_dir / "archive.txt"))
            self.load_settings(initial=False)
            self.apply_style()
            QMessageBox.information(self, "Zresetowano", "Ustawienia zresetowane do domyślnych.")

    # =========================================================
    # Podgląd
    # =========================================================

    def _build_format_string_for_preview(self) -> Tuple[str, str]:
        if self.extract_audio_adv.isChecked():
            return "bestaudio/best", "audio_adv"
        if self.extract_audio.isChecked():
            return "bestaudio/best", "audio"
        vfmt  = self.video_format.currentText()
        vqual = self.video_quality.currentText()
        vcodec = self.video_codec.currentText()
        if vqual == "Najlepsze (auto)":
            fs = f"bv*[ext={vfmt}]+ba[ext=m4a]/b[ext={vfmt}]/bv*+ba/b"
        else:
            try:
                h = int(vqual.split("p")[0])
            except Exception:
                h = 0
            fs = (
                f"bv*[height<={h}][ext={vfmt}]+ba[ext=m4a]"
                f"/b[ext={vfmt}][height<={h}]"
                f"/bv*[height<={h}]+ba/b[height<={h}]"
            )
        if vcodec != "auto":
            fs = fs.replace("bv*", f"bv*[vcodec~=^({vcodec})]")
        return fs, "video"

    def preview_current_url(self):
        url = self.url_input.text().strip()
        if not url or not STRICT_URL_REGEX.match(url):
            QMessageBox.warning(self, "Błędny URL", "Podaj poprawny URL.")
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
            self.url_input.setText(url)
        self._run_preview(url)

    def preview_selected_from_queue(self):
        sel = self.queue_list.selectedItems()
        if sel:
            self._run_preview(sel[0].text().strip())

    def _run_preview(self, url: str):
        if self.preview_thread and self.preview_thread.isRunning():
            return
        for lbl, txt in [
            (self.preview_title,    "Tytuł: (pobieranie...)"),
            (self.preview_uploader, "Kanał: -"),
            (self.preview_duration, "Czas trwania: -"),
            (self.preview_size,     "Szacowany rozmiar: -"),
        ]:
            lbl.setText(txt)
        self.preview_thumb.setPixmap(QPixmap())
        self.preview_thread = PreviewFetchThread(self, url, self)
        self.preview_thread.result_signal.connect(self._handle_preview_result)
        self.preview_thread.error_signal.connect(self._handle_preview_error)
        self.preview_thread.start()

    def _set_preview_ui(self, info: dict):
        self.preview_title.setText(f"Tytuł: {info.get('title') or '-'}")
        self.preview_uploader.setText(f"Kanał: {info.get('uploader') or '-'}")
        self.preview_duration.setText(f"Czas trwania: {human_duration(info.get('duration', 0))}")
        self.preview_size.setText(f"Szacowany rozmiar: {human_size(info.get('estimated_bytes') or 0)}")
        tp = info.get("thumb_path") or ""
        if tp and Path(tp).exists():
            pix = QPixmap(tp)
            if not pix.isNull():
                self.preview_thumb.setPixmap(pix)
                return
        self.preview_thumb.setPixmap(QPixmap())

    def _handle_preview_result(self, info: dict):
        self._set_preview_ui(info)
        url = info.get("webpage_url", "")
        items = self.queue_list.findItems(url, Qt.MatchFlag.MatchExactly) or []
        tip = f"{info.get('title', '')}\n{human_duration(info.get('duration', 0))} | ≈ {human_size(info.get('estimated_bytes') or 0)}"
        if info.get("thumb_path") and Path(info["thumb_path"]).exists():
            pix = QPixmap(info["thumb_path"])
            if not pix.isNull():
                ic = QIcon(pix)
                for it in items:
                    it.setIcon(ic); it.setToolTip(tip)
                return
        for it in items:
            it.setToolTip(tip)

    def _handle_preview_error(self, err: str):
        QMessageBox.warning(self, "Błąd podglądu", f"Nie udało się pobrać podglądu:\n{err}")

    def _start_batch_preview(self, urls: List[str]):
        if not urls:
            return
        self.batch_preview_thread = BatchPreviewThread(self, urls, self)
        self.batch_preview_thread.item_result_signal.connect(self._on_batch_item_result)
        self.batch_preview_thread.finished_signal.connect(self._on_batch_finished)
        self.batch_preview_thread.start()

    def _on_batch_item_result(self, url: str, info: dict):
        items = self.queue_list.findItems(url, Qt.MatchFlag.MatchExactly)
        tip = f"{info.get('title', '')}\n≈ {human_size(info.get('estimated_bytes') or 0)}"
        for it in items:
            it.setToolTip(tip)
            tp = info.get("thumb_path")
            if tp and Path(tp).exists():
                pix = QPixmap(tp)
                if not pix.isNull():
                    it.setIcon(QIcon(pix))

    def _on_batch_finished(self, updated: int, total: int):
        self.statusBar().showMessage(
            f"Skanowanie zakończone: zaktualizowano {updated}/{total} pozycji.", 3000
        )

    def scan_queue_metadata(self):
        urls = [self.queue_list.item(i).text().strip() for i in range(self.queue_list.count())]
        if not urls:
            QMessageBox.information(self, "Kolejka pusta", "Brak elementów do skanowania.")
            return
        self._start_batch_preview(urls)

    # =========================================================
    # Pobieranie i retry
    # =========================================================

    def start_download(self, add_current_url: bool = True):
        self.failed_dialog_shown = False
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, "Pobieranie w toku", "Poczekaj na zakończenie obecnego pobierania.")
            return

        current_url = self.url_input.text().strip()
        if add_current_url and current_url:
            self.download_queue.append(current_url)
            item = QListWidgetItem(current_url)
            item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
            self.queue_list.addItem(item)
            self.url_input.clear()
            self.save_queue()
            self._start_batch_preview([current_url])
        elif not self.download_queue and not self.failed_queue:
            QMessageBox.warning(self, "Brak URL", "Wprowadź URL lub dodaj coś do kolejki.")
            return

        if self.failed_queue and not self.download_queue:
            reply = QMessageBox.question(
                self, "Ponów pobierania",
                f"W kolejce są tylko nieudane pobrania ({len(self.failed_queue)}).\n"
                "Czy chcesz spróbować ponownie?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                for url in self.failed_queue:
                    if url not in self.download_queue:
                        self.download_queue.append(url)
                for i in range(self.queue_list.count()):
                    it = self.queue_list.item(i)
                    if it and it.text() in self.failed_queue:
                        self.queue_list.mark_status(it, self.queue_list.STATUS_NORMAL, self.is_dark_theme())
                self.failed_queue.clear()
                self.item_retry_counts = {}
                self.save_queue()
            else:
                self.download_btn.setEnabled(True)
                return

        self.start_next_in_queue()

    def start_next_in_queue(self):
        if not self.download_queue:
            self.download_btn.setEnabled(True)
            return
        next_url = next((u for u in self.download_queue if u not in self.failed_queue), None)
        if not next_url:
            self.download_btn.setEnabled(True)
            return

        # Zabezpieczenie przed duplikacją — jeśli poprzedni wątek jeszcze żyje, poczekaj
        if self.thread and self.thread.isRunning():
            logger.warning("start_next_in_queue: poprzedni wątek wciąż aktywny, oczekuję...")
            self.thread.wait(3000)
            if self.thread.isRunning():
                logger.error("Wątek nie zakończył się w czasie — przerywam.")
                return

        self.current_processing_url = next_url
        self.output_text.append(f"\n--- ROZPOCZYNAM POBIERANIE DLA: {next_url} ---")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0%")

        # tytuł w tle
        if self.title_thread and self.title_thread.isRunning():
            self.title_thread.wait(100)
        self.title_thread = TitleFetchThread(self.get_ytdlp_path(), next_url, self)
        self.title_thread.title_signal.connect(self._on_title_fetched)
        self.title_thread.error_signal.connect(self._on_title_error)
        self.title_thread.start()

        command = self.build_command(next_url)
        if not command:
            self.download_finished(False)
            return

        self.thread = YTDLPThread(command, self)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.download_finished)
        self.thread.progress_percent_signal.connect(self.update_progress_percent)
        self.thread.progress_detailed_signal.connect(self.update_detailed_progress)
        self.thread.start()
        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_title_fetched(self, url: str, title: str):
        if self.current_processing_url == url and title:
            self.current_video_title = title

    def _on_title_error(self, url: str, err: str):
        logger.warning(f"Nie udało się pobrać tytułu dla {url}: {err}")

    def stop_download(self):
        if self.thread and self.thread.isRunning():
            self._user_stopped = True          # flaga: użytkownik ręcznie zatrzymał
            self.thread.stop()
            self.output_text.append("\nZatrzymuję pobieranie...")
            self.download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def download_finished(self, success: bool):
        self.stop_btn.setEnabled(False)
        self.progress_bar.setFormat("%p%")
        cur = getattr(self, "current_processing_url", None)

        # Jeśli użytkownik kliknął Stop — porzuć retry i nie ruszaj kolejki
        if self._user_stopped:
            self._user_stopped = False
            self.current_video_title = "Unknown"
            self.current_processing_url = None
            self.download_btn.setEnabled(True)
            self.output_text.append("Pobieranie zatrzymane przez użytkownika.")
            return

        if self.download_queue and cur and cur == self.download_queue[0]:
            finished_url = self.download_queue.pop(0)
            items = self.queue_list.findItems(finished_url, Qt.MatchFlag.MatchExactly)
            if items:
                item = items[0]
                row = self.queue_list.row(item)
                self.queue_list.takeItem(row)
                if not success:
                    self._handle_retry_or_fail(finished_url, row)
                else:
                    self.output_text.append("Pobieranie zakończone pomyślnie.")
            self.save_queue()
            self.url_input.clear()

        self.current_video_title = "Unknown"
        self.current_processing_url = None

        remaining = [u for u in self.download_queue if u not in self.failed_queue]
        if remaining:
            self.output_text.append(f"Pozostało {len(remaining)} elementów. Rozpoczynam następny...")
            self.start_next_in_queue()
        else:
            self._handle_queue_completion()

    def _handle_retry_or_fail(self, url: str, row: int):
        retry_count = self.item_retry_counts.get(url, 0)
        max_retry   = self.max_retry_per_item.value()
        if retry_count < max_retry:
            self.item_retry_counts[url] = retry_count + 1
            retry_item = QListWidgetItem(url)
            self.queue_list.mark_status(retry_item, self.queue_list.STATUS_RETRYING, self.is_dark_theme())
            self.queue_list.addItem(retry_item)
            self.download_queue.append(url)
            self.output_text.append(
                f"Ponawiam później ({self.item_retry_counts[url]}/{max_retry}): {url}"
            )
        else:
            # Nieudane pobieranie – zostaje w kolejce jako "failed", NIE jest usuwane automatycznie
            if url not in self.failed_queue:
                self.failed_queue.append(url)
            failed_item = QListWidgetItem(url)
            self.queue_list.mark_status(failed_item, self.queue_list.STATUS_FAILED, self.is_dark_theme())
            self.queue_list.insertItem(row, failed_item)
            self.output_text.append(
                f"--- BŁĄD ---\nNieudane pobieranie: {url}\nTytuł: {self.current_video_title}\nZapisano do listy nieudanych."
            )
            self.failed_logger.info(f"FAILED_URL: {url} | TITLE: {self.current_video_title}")

    def _handle_queue_completion(self):
        if self.failed_queue and not self.failed_dialog_shown:
            self.output_text.append(f"Kolejka zakończona. {len(self.failed_queue)} nieudanych.")
            self.failed_dialog_shown = True
            self._show_failed_downloads_dialog()
        elif not self.failed_queue and not self.download_queue:
            self.output_text.append("Kolejka jest pusta. Pobieranie zakończone.")
            self.download_btn.setEnabled(True)

    def _show_failed_downloads_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Nieudane pobierania")
        dialog.setModal(True)
        dialog.resize(560, 360)
        lay = QVBoxLayout(dialog)
        lay.addWidget(QLabel(f"Znaleziono {len(self.failed_queue)} nieudanych pobierań:"))
        failed_list = QListWidget()
        for url in self.failed_queue:
            failed_list.addItem(url)
        lay.addWidget(failed_list)
        btn_row = QHBoxLayout()
        retry_btn = QPushButton("Ponów próbę nieudanych")
        retry_btn.clicked.connect(lambda: self._retry_failed_downloads(dialog))
        btn_row.addWidget(retry_btn)
        clear_btn = QPushButton("Usuń nieudane z kolejki")
        clear_btn.clicked.connect(lambda: self._clear_failed_downloads(dialog))
        btn_row.addWidget(clear_btn)
        cancel_btn = QPushButton("Zamknij")
        cancel_btn.clicked.connect(lambda: self._close_failed_dialog(dialog))
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)
        dialog.exec()

    def _close_failed_dialog(self, dialog: QDialog):
        self.failed_dialog_shown = False
        dialog.close()
        self.download_btn.setEnabled(True)

    def _retry_failed_downloads(self, dialog: QDialog):
        to_move = list(self.failed_queue)
        for i in range(self.queue_list.count()):
            it = self.queue_list.item(i)
            if it and it.text() in to_move:
                self.queue_list.mark_status(it, self.queue_list.STATUS_NORMAL, self.is_dark_theme())
        for url in to_move:
            if url not in self.download_queue:
                self.download_queue.append(url)
        self.failed_queue.clear()
        self.item_retry_counts = {}
        self.save_queue()
        self.output_text.append(f"Przeniesiono {len(to_move)} nieudanych z powrotem do kolejki.")
        self.failed_dialog_shown = False
        dialog.close()
        self.start_next_in_queue()

    def _clear_failed_downloads(self, dialog: QDialog):
        to_remove = []
        for i in range(self.queue_list.count()):
            it = self.queue_list.item(i)
            if it and self.queue_list.is_failed_item(it):
                to_remove.append((i, it.text()))
        for i, url in reversed(to_remove):
            self.queue_list.takeItem(i)
            if url in self.download_queue:
                self.download_queue.remove(url)
        self.failed_queue.clear()
        self.save_queue()
        self.output_text.append(f"Usunięto {len(to_remove)} nieudanych z kolejki.")
        self.failed_dialog_shown = False
        dialog.close()
        self.download_btn.setEnabled(True)

    # =========================================================
    # Budowanie komendy yt-dlp
    # =========================================================

    def build_command(self, url: str) -> Optional[list]:
        ytdlp = self.get_ytdlp_path()
        if ytdlp != "yt-dlp" and not Path(ytdlp).exists():
            QMessageBox.critical(self, "Błąd YT-DLP", f"Nie znaleziono YT-DLP: '{ytdlp}'.")
            return None
        cmd = [ytdlp]

        ffmpeg = self.get_ffmpeg_path()
        if ffmpeg:
            if ffmpeg == "ffmpeg" or Path(ffmpeg).is_file():
                cmd += ["--ffmpeg-location", str(Path(ffmpeg).parent)]
            else:
                self.output_text.append(f"OSTRZEŻENIE: Ścieżka FFmpeg '{ffmpeg}' nie jest plikiem.")

        cmd += ["--socket-timeout", str(DEFAULT_SOCKET_TIMEOUT)]

        vfmt   = self.video_format.currentText()
        vqual  = self.video_quality.currentText()
        vcodec = self.video_codec.currentText()
        afmt   = self.audio_format.currentText()
        aqi    = self.audio_quality.currentIndex()
        recode = self.recode_video.currentText()
        extract_adv = self.extract_audio_adv.isChecked()

        mode = "audio_adv" if extract_adv else ("audio" if self.extract_audio.isChecked() else "video")

        if recode != "Nie przetwarzaj":
            cmd += ["--recode-video", recode]

        if mode in ("audio", "audio_adv"):
            cmd.append("-x")
            if mode == "audio":
                cmd += ["--audio-format", afmt, "--audio-quality", str(aqi)]
                if self.keep_video.isChecked():    cmd.append("-k")
                if self.add_metadata.isChecked():  cmd.append("--add-metadata")
                if self.embed_thumbnail.isChecked(): cmd.append("--embed-thumbnail")
                out_path = self.audio_output_path.text().strip() or self.default_output_path.text().strip()
                out_tmpl = self.audio_output_template.text().strip() or self.default_template.text().strip()
            else:
                cmd += ["--audio-format", self.audio_format_adv.currentText(),
                        "--audio-quality", str(self.audio_quality_adv.currentIndex())]
                if self.keep_video_adv.isChecked(): cmd.append("-k")
                out_path = self.default_output_path.text().strip()
                out_tmpl = self.default_template.text().strip()
        else:
            if vqual == "Najlepsze (auto)":
                fs = f"bv*[ext={vfmt}]+ba[ext=m4a]/b[ext={vfmt}]/bv*+ba/b"
            else:
                h = vqual.split("p")[0]
                fs = (
                    f"bv*[height<={h}][ext={vfmt}]+ba[ext=m4a]"
                    f"/b[ext={vfmt}][height<={h}]"
                    f"/bv*[height<={h}]+ba/b[height<={h}]"
                )
            if vcodec != "auto":
                fs = fs.replace("bv*", f"bv*[vcodec~=^({vcodec})]")
            cmd += ["-f", fs]
            if self.embed_thumbnails.isChecked(): cmd.append("--embed-thumbnail")
            if self.embed_subs.isChecked():       cmd.append("--embed-subs")
            out_path = self.output_path.text().strip() or self.default_output_path.text().strip()
            out_tmpl = self.output_template.text().strip() or self.default_template.text().strip()

        if out_path: cmd += ["-P", out_path]
        if out_tmpl: cmd += ["-o", out_tmpl]

        if r := self.limit_rate.text().strip():    cmd += ["-r", r]
        if v := self.retries.value():              cmd += ["--retries", str(v)]
        if self.write_subs.isChecked():            cmd.append("--write-subs")
        if self.write_auto_subs.isChecked():       cmd.append("--write-auto-subs")
        if self.write_info_json.isChecked():       cmd.append("--write-info-json")
        if self.prefer_ffmpeg.isChecked():         cmd.append("--prefer-ffmpeg")

        if self.playlist_start.value() > 1:
            cmd += ["--playlist-start", str(self.playlist_start.value())]
        if self.playlist_end.value() > 0:
            cmd += ["--playlist-end", str(self.playlist_end.value())]
        if it := self.playlist_items.text().strip():
            cmd += ["--playlist-items", it]
        if self.playlist_reverse.isChecked(): cmd.append("--playlist-reverse")
        if self.playlist_random.isChecked():  cmd.append("--playlist-random")

        if self.use_archive.isChecked():
            arch = self.archive_file.text().strip()
            if arch:
                cmd += ["--download-archive", arch]
            else:
                self.output_text.append("OSTRZEŻENIE: Włączono archiwum, ale ścieżka jest pusta.")

        if p := self.proxy.text().strip():          cmd += ["--proxy", p]
        if s := self.source_address.text().strip(): cmd += ["--source-address", s]
        if self.force_ipv4.isChecked(): cmd.append("--force-ipv4")
        if self.force_ipv6.isChecked(): cmd.append("--force-ipv6")

        # uwierzytelnianie
        cda_email = self.cda_email.text().strip()
        cda_pass  = self.cda_password.text()
        username  = self.username.text().strip()
        password  = self.password.text()
        if url and "cda.pl" in url:
            if "/vfilm" in url:
                if cda_email and cda_pass:
                    cmd += ["--username", cda_email, "--password", cda_pass]
                else:
                    QMessageBox.warning(self, "Brak danych CDA", "Film premium CDA wymaga danych logowania.")
                    return None
            elif cda_email and cda_pass:
                # Zwykły film CDA – przekaż dane jeśli są (CDA może wymagać auth nawet dla darmowych)
                cmd += ["--username", cda_email, "--password", cda_pass]
        else:
            if cda_email and cda_pass:
                cmd += ["--username", cda_email, "--password", cda_pass]
            elif username and password:
                cmd += ["--username", username, "--password", password]

        if tf := self.twofactor.text().strip():     cmd += ["--twofactor", tf]
        if vp := self.video_password.text():        cmd += ["--video-password", vp]
        if ppa := self.postprocessor_args.text().strip(): cmd += ["--postprocessor-args", ppa]

        # Własne argumenty użytkownika – parsujemy prostym shlex aby obsłużyć cudzysłowy
        if raw := self.custom_ytdlp_args.text().strip():
            import shlex as _shlex
            try:
                cmd += _shlex.split(raw)
            except ValueError:
                cmd += raw.split()

        if self.ignore_errors.isChecked():  cmd.append("--ignore-errors")
        if self.no_warnings.isChecked():   cmd.append("--no-warnings")
        if self.quiet.isChecked():         cmd.append("--quiet")
        if self.no_color.isChecked():      cmd.append("--no-color")
        if self.simulate.isChecked():      cmd.append("--simulate")
        if self.skip_download.isChecked(): cmd.append("--skip-download")

        cmd.append(url)
        logger.info(f"Komenda: {' '.join(cmd)}")
        return cmd

    # =========================================================
    # Monitor schowka
    # =========================================================

    def _poll_clipboard(self):
        try:
            if not self.enable_clipboard_monitor.isChecked():
                return
            cb = QApplication.clipboard()
            text = cb.text().strip() if cb else ""
            if text and text != self._clipboard_prev and STRICT_URL_REGEX.match(text):
                self._clipboard_prev = text
                if self.auto_add_to_queue.isChecked():
                    self.url_input.setText(text)
                    self.add_to_queue()
                    self.statusBar().showMessage("URL dodany z schowka", 2000)
        except Exception as e:
            logger.debug(f"Clipboard poll err: {e}")

    # =========================================================
    # Zamknięcie okna
    # =========================================================

    def closeEvent(self, event):
        logger.info("Zamykanie, zapis ustawień i kolejki.")
        self.save_settings()
        self.save_queue()
        timeout = 3000
        for t in [self.thread, self.update_ytdlp_thread, self.download_ffmpeg_thread]:
            if t and t.isRunning():
                if t is self.thread:
                    t.stop()
                else:
                    t.quit()
                if not t.wait(timeout):
                    t.terminate()
                    t.wait(1000)
        for t in [self.preview_thread, self.batch_preview_thread, self.title_thread]:
            if t and t.isRunning():
                t.terminate()
                t.wait(500)
        event.accept()
