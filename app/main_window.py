# -*- coding: utf-8 -*-
"""
Główne okno aplikacji YTDLPGUI.

Klasa jest złożona z mixinów — każdy odpowiada za jeden obszar logiki:
  - ThemeMixin        → motyw wizualny
  - DependenciesMixin → yt-dlp / FFmpeg
  - ProgressMixin     → pasek postępu i konsola
  - QueueMixin        → kolejka, ścieżki, schowek, CDA
  - PreviewMixin      → podgląd metadanych URL
  - DownloadMixin     → pobieranie, retry, budowanie komendy
  - SettingsMixin     → zapis / odczyt / reset ustawień
"""

import logging
import os
import platform
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import (
    DEFAULT_SOCKET_TIMEOUT,
    FFMPEG_PATH_LINUX,
    FFMPEG_PATH_WINDOWS,
    STRICT_URL_REGEX,
    YTDLP_PATH_LINUX,
    YTDLP_PATH_WINDOWS,
    app_data_base_dir,
    log_dir,
)
from .mixins.dependencies import DependenciesMixin
from .mixins.download import DownloadMixin
from .mixins.preview import PreviewMixin
from .mixins.progress import ProgressMixin
from .mixins.queue import QueueMixin
from .mixins.settings import SettingsMixin
from .mixins.theme import ThemeMixin
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
from .ui.tabs import (
    APP_VERSION,
    init_about_tab,
    init_advanced_tab,
    init_audio_tab,
    init_options_tabs,
    init_playlist_tab,
    init_queue_panel,
    init_queue_tab,
    init_settings_tab,
    init_video_tab,
)
from .utils import human_duration, human_size, resource_path

logger = logging.getLogger(__name__)


class YTDLPGUI(
    ThemeMixin,
    DependenciesMixin,
    ProgressMixin,
    QueueMixin,
    PreviewMixin,
    DownloadMixin,
    SettingsMixin,
    QMainWindow,
):
    """Główne okno aplikacji — złożone z mixinów."""

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

        self.failed_log_file = log_dir / "failed_downloads.log"
        self.failed_logger = logging.getLogger("failed_downloads")
        fh = logging.FileHandler(self.failed_log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        self.failed_logger.addHandler(fh)
        self.failed_logger.setLevel(logging.INFO)

        self.default_ytdlp_path_fallback = (
            str(YTDLP_PATH_WINDOWS) if os.name == "nt" else str(YTDLP_PATH_LINUX)
        )
        self.default_ffmpeg_path_local_fallback = (
            str(FFMPEG_PATH_WINDOWS) if os.name == "nt" else str(FFMPEG_PATH_LINUX)
        )

        self.thread: Optional[YTDLPThread] = None
        self.update_ytdlp_thread: Optional[UpdateYTDLPThread] = None
        self.download_ffmpeg_thread: Optional[DownloadFFmpegThread] = None
        self.cda_check_thread: Optional[CDAStatusCheckThread] = None
        self.preview_thread: Optional[PreviewFetchThread] = None
        self.batch_preview_thread: Optional[BatchPreviewThread] = None
        self.title_thread: Optional[TitleFetchThread] = None

        self.download_queue: List[str] = []
        self.failed_queue: List[str] = []
        self.item_retry_counts: Dict[str, int] = {}
        self.pending_queue_check = False
        self.failed_dialog_shown = False
        self._user_stopped = False

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
        if p:
            return p
        local = Path(self.default_ffmpeg_path_local_fallback)
        return str(local) if local.exists() else "ffmpeg"

    def get_user_downloads_path(self) -> str:
        if os.name == "nt":
            import winreg
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
                )
                path, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                winreg.CloseKey(key)
                return path
            except Exception:
                pass
        downloads = Path.home() / "Downloads"
        if downloads.exists():
            return str(downloads)
        pobrane = Path.home() / "Pobrane"
        return str(pobrane) if pobrane.exists() else str(Path.home())

    # =========================================================
    # Budowanie UI
    # =========================================================

    def init_ui(self):
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setWindowTitle("Video Downloader")
        self.setGeometry(100, 100, 1280, 860)
        self.setStatusBar(QStatusBar(self))

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(6)

        # --- URL bar ---
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
        self.preview_widget = QWidget()
        preview_panel = QHBoxLayout(self.preview_widget)
        preview_panel.setContentsMargins(0, 4, 0, 0)
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
        self.preview_widget.setVisible(False)
        url_layout.addWidget(self.preview_widget)
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)

        # --- Split poziomy: lewa=opcje, prawa=kolejka ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget  = QWidget()
        right_widget = QWidget()

        init_options_tabs(self, left_widget)
        init_queue_panel(self, right_widget)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([760, 480])
        main_layout.addWidget(splitter, stretch=3)

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
        main_layout.addWidget(out_group, stretch=1)

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
        del_act = QAction(self)
        del_act.setShortcut("Delete")
        del_act.triggered.connect(self.remove_from_queue)
        self.addAction(del_act)

        enter_act = QAction(self)
        enter_act.setShortcut("Return")
        enter_act.triggered.connect(lambda: self.start_download(add_current_url=True))
        self.addAction(enter_act)

        f2_act = QAction(self)
        f2_act.setShortcut("F2")
        f2_act.triggered.connect(self.edit_queue_item)
        self.addAction(f2_act)

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
