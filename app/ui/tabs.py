# -*- coding: utf-8 -*-
"""
Inicjalizacja interfejsu użytkownika — nowy layout.

Split pionowy: lewa = opcje (Format/Playlista/Zaawansowane/Ustawienia/O programie),
prawa = zawsze widoczna kolejka pobierania.
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QFont, QCursor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QRadioButton, QScrollArea, QSpinBox, QStackedWidget, QStyle, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..config import FFMPEG_PATH_WINDOWS, LIBS_DIR, YTDLP_PATH_WINDOWS
from ..queue_widget import QueueListWidget

APP_VERSION = "1.2.1"


def _hsep():
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


# ---------------------------------------------------------------------------
# Panel kolejki (prawa kolumna)
# ---------------------------------------------------------------------------

def init_queue_panel(win, parent: QWidget):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)

    q_group = QGroupBox("Kolejka pobierania")
    q_lay = QVBoxLayout()

    win.queue_list = QueueListWidget(win)
    win.queue_list.setToolTip("Lista URL-i w kolejce. Obsługuje drag&drop i menu kontekstowe.")
    win.queue_list.itemSelectionChanged.connect(win.update_remove_btn_state)
    win.queue_list.dropped_reordered.connect(win._sync_download_queue_from_widget)
    win.queue_list.dropped_external_urls.connect(win._add_urls_list)
    q_lay.addWidget(win.queue_list)

    btns = QHBoxLayout()
    style = win.style()

    add_btn = QPushButton(" Dodaj URL")
    add_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
    add_btn.clicked.connect(win.add_to_queue)
    btns.addWidget(add_btn)

    win.remove_btn = QPushButton(" Usuń")
    win.remove_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
    win.remove_btn.clicked.connect(win.remove_from_queue)
    win.remove_btn.setEnabled(False)
    btns.addWidget(win.remove_btn)

    up_btn = QPushButton()
    up_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
    up_btn.setToolTip("W górę")
    up_btn.clicked.connect(win.move_queue_item_up)
    btns.addWidget(up_btn)

    down_btn = QPushButton()
    down_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
    down_btn.setToolTip("W dół")
    down_btn.clicked.connect(win.move_queue_item_down)
    btns.addWidget(down_btn)

    win.edit_btn = QPushButton(" Edytuj")
    win.edit_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
    win.edit_btn.clicked.connect(win.edit_queue_item)
    win.edit_btn.setEnabled(False)
    btns.addWidget(win.edit_btn)

    clear_q_btn = QPushButton()
    clear_q_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
    clear_q_btn.setToolTip("Wyczyść kolejkę")
    clear_q_btn.clicked.connect(win.clear_queue)
    btns.addWidget(clear_q_btn)

    q_lay.addLayout(btns)
    q_group.setLayout(q_lay)
    layout.addWidget(q_group)


# ---------------------------------------------------------------------------
# Zakładki opcji (lewa kolumna)
# ---------------------------------------------------------------------------

def init_options_tabs(win, parent: QWidget):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)

    win.options_tabs = QTabWidget()

    format_tab   = QWidget()
    playlist_tab = QWidget()
    advanced_tab = QWidget()
    settings_tab = QWidget()
    about_tab    = QWidget()

    _init_format_tab(win, format_tab)
    _init_playlist_tab(win, playlist_tab)
    _init_advanced_tab(win, advanced_tab)
    _init_settings_tab(win, settings_tab)
    _init_about_tab(win, about_tab)

    win.options_tabs.addTab(format_tab,   "Format i tryb")
    win.options_tabs.addTab(playlist_tab, "Playlista")
    win.options_tabs.addTab(advanced_tab, "Zaawansowane")
    win.options_tabs.addTab(settings_tab, "Ustawienia")
    win.options_tabs.addTab(about_tab,    "O programie")

    layout.addWidget(win.options_tabs)


# ---------------------------------------------------------------------------
# "Format i tryb"
# ---------------------------------------------------------------------------

def _init_format_tab(win, tab_widget: QWidget):
    outer = QVBoxLayout(tab_widget)
    scroll = QScrollArea(); scroll.setWidgetResizable(True)
    content = QWidget(); scroll.setWidget(content)
    cl = QVBoxLayout(content)
    cl.setSpacing(10)

    # wybor trybu
    mode_group = QGroupBox("Co chcesz pobrać?")
    mode_layout = QVBoxLayout()
    win._mode_both  = QRadioButton("Wideo z dźwiękiem  (domyślne)")
    win._mode_audio = QRadioButton("Tylko audio  (np. muzyka z YouTube → mp3, flac…)")
    win._mode_video = QRadioButton("Tylko wideo  (bez dźwięku)")
    win._mode_both.setChecked(True)
    mode_hint = QLabel(
        "<i>Tryb <b>Audio</b>: pobiera strumień audio i konwertuje do wybranego formatu.<br>"
        "Tryb <b>Wideo z dźwiękiem</b>: pobiera najlepsze wideo i scala z audio przez FFmpeg.</i>"
    )
    mode_hint.setWordWrap(True)
    mode_layout.addWidget(win._mode_both)
    mode_layout.addWidget(win._mode_audio)
    mode_layout.addWidget(win._mode_video)
    mode_layout.addWidget(mode_hint)
    mode_group.setLayout(mode_layout)
    cl.addWidget(mode_group)

    # stos paneli
    win._format_stack = QStackedWidget()
    win._format_stack.addWidget(_make_video_audio_panel(win))  # 0
    win._format_stack.addWidget(_make_audio_only_panel(win))   # 1
    win._format_stack.addWidget(_make_video_only_panel(win))   # 2
    cl.addWidget(win._format_stack)

    win._mode_both.toggled.connect( lambda c: win._format_stack.setCurrentIndex(0) if c else None)
    win._mode_audio.toggled.connect(lambda c: win._format_stack.setCurrentIndex(1) if c else None)
    win._mode_video.toggled.connect(lambda c: win._format_stack.setCurrentIndex(2) if c else None)

    # wspólne opcje pliku
    file_group = QGroupBox("Plik wyjściowy")
    file_lay = QFormLayout()
    win.output_template = QLineEdit("%(playlist_title|)s/%(title)s.%(ext)s")
    file_lay.addRow("Szablon nazwy:", win.output_template)

    win.output_path = QLineEdit()
    browse_out = QPushButton(" Przeglądaj...")
    browse_out.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_out.clicked.connect(win.browse_output_path)
    out_row = QHBoxLayout()
    out_row.addWidget(win.output_path); out_row.addWidget(browse_out)
    file_lay.addRow("Katalog wyjściowy:", out_row)

    win.limit_rate = QLineEdit()
    win.limit_rate.setPlaceholderText("np. 50K lub 4.2M")
    file_lay.addRow("Ograniczenie prędkości:", win.limit_rate)

    win.retries = QSpinBox()
    win.retries.setRange(0, 99); win.retries.setValue(10)
    file_lay.addRow("Liczba prób (yt-dlp):", win.retries)

    file_group.setLayout(file_lay)
    cl.addWidget(file_group)
    cl.addStretch()
    outer.addWidget(scroll)

    # aliasy dla SettingsMixin
    win.audio_output_template = win.output_template
    win.audio_output_path     = win.output_path


def _lbl_right(text):
    l = QLabel(text)
    l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return l


def _make_video_audio_panel(win) -> QWidget:
    w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
    g = QGroupBox("Parametry wideo"); gl = QGridLayout()
    gl.setSpacing(8); gl.setColumnStretch(1, 1)

    win.video_format = QComboBox()
    win.video_format.addItems(["mp4", "webm", "mkv", "flv", "avi"])
    gl.addWidget(_lbl_right("Kontener:"), 0, 0); gl.addWidget(win.video_format, 0, 1)

    win.video_quality = QComboBox()
    win.video_quality.addItems([
        "Najlepsze (auto)", "2160p (4K)", "1440p (2K)",
        "1080p", "720p", "480p", "360p", "240p", "144p",
    ])
    gl.addWidget(_lbl_right("Jakość:"), 1, 0); gl.addWidget(win.video_quality, 1, 1)

    win.video_codec = QComboBox()
    win.video_codec.addItems(["auto", "h264", "h265", "vp9", "av1"])
    gl.addWidget(_lbl_right("Kodek:"), 2, 0); gl.addWidget(win.video_codec, 2, 1)
    g.setLayout(gl); lay.addWidget(g)

    ch_g = QGroupBox("Dodatkowe opcje"); ch_l = QVBoxLayout()
    win.embed_thumbnails = QCheckBox("Osadź miniaturkę"); win.embed_thumbnails.setChecked(True)
    win.embed_subs      = QCheckBox("Osadź napisy")
    win.write_subs      = QCheckBox("Zapisz napisy do pliku")
    win.write_auto_subs = QCheckBox("Zapisz automatyczne napisy")
    win.write_info_json = QCheckBox("Zapisz metadane do .info.json")
    for w_ in (win.embed_thumbnails, win.embed_subs, win.write_subs,
               win.write_auto_subs, win.write_info_json):
        ch_l.addWidget(w_)
    ch_g.setLayout(ch_l); lay.addWidget(ch_g)

    # wymagane przez DownloadMixin (nieużywane w tym trybie, ale muszą istnieć)
    win.extract_audio = QCheckBox(); win.keep_video = QCheckBox()
    lay.addStretch()
    return w


def _make_audio_only_panel(win) -> QWidget:
    w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
    g = QGroupBox("Parametry audio"); gl = QFormLayout()

    win.audio_format = QComboBox()
    win.audio_format.addItems(["najlepszy", "mp3", "aac", "flac", "m4a", "opus", "vorbis", "wav"])
    gl.addRow("Format:", win.audio_format)

    win.audio_quality = QComboBox()
    win.audio_quality.addItems([
        f"{i} ({'najlepsza' if i == 0 else 'najgorsza' if i in (9, 10) else ''})".strip()
        for i in range(10)
    ])
    gl.addRow("Jakość (VBR, 0=najlepsza):", win.audio_quality)

    win.add_metadata = QCheckBox("Dodaj metadane (artysta, tytuł itp.)")
    win.add_metadata.setChecked(True)
    gl.addRow(win.add_metadata)

    win.embed_thumbnail = QCheckBox("Osadź miniaturkę w pliku audio")
    win.embed_thumbnail.setChecked(True)
    gl.addRow(win.embed_thumbnail)

    win.prefer_ffmpeg = QCheckBox("Preferuj ffmpeg do konwersji")
    gl.addRow(win.prefer_ffmpeg)

    g.setLayout(gl); lay.addWidget(g)
    lay.addStretch()
    return w


def _make_video_only_panel(win) -> QWidget:
    w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
    note = QLabel(
        "<b>Tylko wideo</b> — pobiera strumień wideo bez scalania audio.<br>"
        "Używa tych samych ustawień formatu/jakości/kodeka co tryb 'Wideo z dźwiękiem'.<br>"
        "<i>Przydatne do dalszej obróbki w edytorze wideo.</i>"
    )
    note.setWordWrap(True)
    lay.addWidget(note)
    lay.addStretch()
    return w


# ---------------------------------------------------------------------------
# "Playlista"
# ---------------------------------------------------------------------------

def _init_playlist_tab(win, tab_widget: QWidget):
    layout = QVBoxLayout(tab_widget)
    scroll = QScrollArea(); scroll.setWidgetResizable(True)
    content = QWidget(); scroll.setWidget(content)
    cl = QVBoxLayout(content)

    pl_mode_group = QGroupBox("Tryb pobierania playlisty")
    pm_lay = QVBoxLayout()
    win._pl_single = QRadioButton("Pobierz tylko jedno wideo (ignoruj playlistę)")
    win._pl_all    = QRadioButton("Pobierz całą playlistę")
    win._pl_range  = QRadioButton("Pobierz fragment / konkretne pozycje")
    win._pl_all.setChecked(True)
    pm_lay.addWidget(win._pl_single)
    pm_lay.addWidget(win._pl_all)
    pm_lay.addWidget(win._pl_range)
    pl_mode_group.setLayout(pm_lay)
    cl.addWidget(pl_mode_group)

    win._pl_range_panel = QGroupBox("Zakres / konkretne pozycje")
    rp = QFormLayout()
    win.playlist_start = QSpinBox(); win.playlist_start.setRange(1, 9999)
    rp.addRow("Rozpocznij od pozycji:", win.playlist_start)
    win.playlist_end = QSpinBox(); win.playlist_end.setRange(0, 9999)
    win.playlist_end.setSpecialValueText("Do końca")
    rp.addRow("Zakończ na pozycji:", win.playlist_end)
    win.playlist_items = QLineEdit()
    win.playlist_items.setPlaceholderText("np. 1,3,5-8  albo  2-10  (nadpisuje pola powyżej)")
    rp.addRow("Konkretne pozycje:", win.playlist_items)
    win._pl_range_panel.setLayout(rp)
    win._pl_range_panel.setEnabled(False)
    cl.addWidget(win._pl_range_panel)

    order_group = QGroupBox("Kolejność pobierania")
    ol = QVBoxLayout()
    win.playlist_reverse = QCheckBox("Pobierz w odwrotnej kolejności")
    win.playlist_random  = QCheckBox("Pobierz w losowej kolejności")
    ol.addWidget(win.playlist_reverse); ol.addWidget(win.playlist_random)
    order_group.setLayout(ol)
    cl.addWidget(order_group)

    arch_group = QGroupBox("Plik archiwum (pomiń już pobrane)")
    arch_lay = QVBoxLayout()
    win.use_archive = QCheckBox("Użyj pliku archiwum")
    arch_lay.addWidget(win.use_archive)
    arch_row = QHBoxLayout()
    win.archive_file = QLineEdit()
    win.archive_file.setPlaceholderText("Domyślnie: archive.txt w katalogu aplikacji")
    browse_arch = QPushButton(" Przeglądaj...")
    browse_arch.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_arch.clicked.connect(win.browse_archive_file)
    arch_row.addWidget(win.archive_file); arch_row.addWidget(browse_arch)
    arch_lay.addLayout(arch_row)
    arch_group.setLayout(arch_lay)
    cl.addWidget(arch_group)

    cl.addStretch()
    layout.addWidget(scroll)

    win._pl_range.toggled.connect(win._pl_range_panel.setEnabled)


# ---------------------------------------------------------------------------
# "Zaawansowane"
# ---------------------------------------------------------------------------

def _init_advanced_tab(win, tab_widget: QWidget):
    layout = QVBoxLayout(tab_widget)
    scroll = QScrollArea(); scroll.setWidgetResizable(True)
    content = QWidget(); scroll.setWidget(content)
    adv = QVBoxLayout(content)

    net_group = QGroupBox("Opcje sieciowe")
    net_lay = QFormLayout()
    win.proxy = QLineEdit(); win.proxy.setPlaceholderText("np. socks5://user:pass@127.0.0.1:1080/")
    net_lay.addRow("Proxy:", win.proxy)
    win.source_address = QLineEdit(); win.source_address.setPlaceholderText("np. 192.168.0.1")
    net_lay.addRow("Adres źródłowy:", win.source_address)
    win.force_ipv4 = QCheckBox("Wymuś IPv4"); net_lay.addRow(win.force_ipv4)
    win.force_ipv6 = QCheckBox("Wymuś IPv6"); net_lay.addRow(win.force_ipv6)
    net_group.setLayout(net_lay)
    adv.addWidget(net_group)

    auth_group = QGroupBox("Uwierzytelnianie (inne niż CDA)")
    auth_lay = QFormLayout()
    win.username = QLineEdit()
    auth_lay.addRow("Nazwa użytkownika:", win.username)
    win.password = QLineEdit(); win.password.setEchoMode(QLineEdit.EchoMode.Password)
    win.password_show_btn = QPushButton()
    win.password_show_btn.setIcon(QIcon("icons/eye.png"))
    win.password_show_btn.setFixedSize(QSize(30, 24))
    win.password_show_btn.setCheckable(True)
    win.password_show_btn.toggled.connect(win.toggle_password_visibility)
    win.password_show_btn.setToolTip("Pokaż/ukryj hasło.")
    pass_row = QHBoxLayout()
    pass_row.addWidget(win.password); pass_row.addWidget(win.password_show_btn)
    auth_lay.addRow("Hasło:", pass_row)
    win.twofactor = QLineEdit(); win.twofactor.setPlaceholderText("Kod 2FA")
    auth_lay.addRow("Kod 2FA:", win.twofactor)
    win.video_password = QLineEdit(); win.video_password.setEchoMode(QLineEdit.EchoMode.Password)
    auth_lay.addRow("Hasło do wideo:", win.video_password)
    auth_group.setLayout(auth_lay)
    adv.addWidget(auth_group)

    post_group = QGroupBox("Przetwarzanie końcowe (FFmpeg)")
    post_lay = QFormLayout()
    win.extract_audio_adv = QCheckBox("Wyodrębnij audio (nadpisuje tryb z zakładki Format)")
    post_lay.addRow(win.extract_audio_adv)
    win.audio_format_adv = QComboBox()
    win.audio_format_adv.addItems(["najlepszy", "mp3", "aac", "flac", "m4a", "opus", "vorbis", "wav"])
    post_lay.addRow("Format audio (adv):", win.audio_format_adv)
    win.audio_quality_adv = QComboBox()
    win.audio_quality_adv.addItems([str(i) for i in range(11)])
    post_lay.addRow("Jakość audio (adv):", win.audio_quality_adv)
    win.keep_video_adv = QCheckBox("Zachowaj plik wideo po wyodrębnieniu")
    post_lay.addRow(win.keep_video_adv)
    win.recode_video = QComboBox()
    win.recode_video.addItems([
        "Nie przetwarzaj", "mp4", "flv", "ogg", "webm", "mkv",
        "avi", "mov", "wmv", "gif", "m4a", "mp3", "aac", "opus", "vorbis", "wav", "aiff",
    ])
    post_lay.addRow("Przetwórz do:", win.recode_video)
    win.postprocessor_args = QLineEdit()
    win.postprocessor_args.setPlaceholderText("np. -crf 28 lub -b:a 192k")
    post_lay.addRow("Argumenty FFmpeg:", win.postprocessor_args)
    post_group.setLayout(post_lay)
    adv.addWidget(post_group)

    other_group = QGroupBox("Zachowanie programu")
    other_lay = QFormLayout()
    win.ignore_errors = QCheckBox("Kontynuuj przy błędach");          other_lay.addRow(win.ignore_errors)
    win.no_warnings   = QCheckBox("Wyłącz ostrzeżenia");              other_lay.addRow(win.no_warnings)
    win.quiet         = QCheckBox("Tryb cichy (mniej wyjścia)");      other_lay.addRow(win.quiet)
    win.no_color      = QCheckBox("Wyłącz kolory w wyjściu");         other_lay.addRow(win.no_color)
    win.simulate      = QCheckBox("Symuluj (nie pobieraj plików)");   other_lay.addRow(win.simulate)
    win.skip_download = QCheckBox("Pomiń pobieranie (tylko info)");   other_lay.addRow(win.skip_download)
    win.max_retry_per_item = QSpinBox(); win.max_retry_per_item.setRange(0, 10)
    win.max_retry_per_item.setValue(win.settings.value("max_retry_per_item", 2, type=int))
    other_lay.addRow("Maks. ponowień na URL:", win.max_retry_per_item)
    win.enable_clipboard_monitor = QCheckBox("Monitoruj schowek i auto-dodawaj URL")
    other_lay.addRow(win.enable_clipboard_monitor)
    other_group.setLayout(other_lay)
    adv.addWidget(other_group)

    custom_group = QGroupBox("Własne argumenty yt-dlp")
    custom_lay = QVBoxLayout()
    custom_info = QLabel(
        "Dodatkowe argumenty przekazywane bezpośrednio do yt-dlp (dopisywane przed URL-em).\n"
        "Przykłady:  --cookies-from-browser chrome    --sub-lang pl  --no-playlist"
    )
    custom_info.setWordWrap(True)
    custom_lay.addWidget(custom_info)
    win.custom_ytdlp_args = QLineEdit()
    win.custom_ytdlp_args.setPlaceholderText(
        "np. --cookies-from-browser chrome  lub  --extractor-args \"generic:impersonate=chrome\""
    )
    custom_lay.addWidget(win.custom_ytdlp_args)
    custom_group.setLayout(custom_lay)
    adv.addWidget(custom_group)

    adv.addStretch()
    layout.addWidget(scroll)


# ---------------------------------------------------------------------------
# "Ustawienia" — z podzakładkami
# ---------------------------------------------------------------------------

def _init_settings_tab(win, tab_widget: QWidget):
    outer = QVBoxLayout(tab_widget)
    inner_tabs = QTabWidget()
    style = win.style()

    # Podzakładka: Narzędzia
    tools_w = QWidget()
    tools_scroll = QScrollArea(); tools_scroll.setWidgetResizable(True)
    tools_content = QWidget(); tools_scroll.setWidget(tools_content)
    tl = QVBoxLayout(tools_content)
    ytdlp_group = QGroupBox("Konfiguracja narzędzi")
    ytdlp_lay = QFormLayout()
    win.ytdlp_path_input = QLineEdit(win.get_ytdlp_path())
    win.ytdlp_path_input.setPlaceholderText(f"Domyślnie: {YTDLP_PATH_WINDOWS} (Windows) lub 'yt-dlp' (PATH)")
    browse_ytdlp = QPushButton(" Przeglądaj...")
    browse_ytdlp.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_ytdlp.clicked.connect(win.browse_ytdlp_path)
    ytdlp_row = QHBoxLayout()
    ytdlp_row.addWidget(win.ytdlp_path_input); ytdlp_row.addWidget(browse_ytdlp)
    ytdlp_lay.addRow("Ścieżka do YT-DLP:", ytdlp_row)
    win.ffmpeg_path = QLineEdit(win.get_ffmpeg_path())
    win.ffmpeg_path.setPlaceholderText(f"Domyślnie: {FFMPEG_PATH_WINDOWS} (Windows) lub 'ffmpeg' (PATH)")
    browse_ffmpeg = QPushButton(" Przeglądaj...")
    browse_ffmpeg.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_ffmpeg.clicked.connect(win.browse_ffmpeg_path)
    ffmpeg_row = QHBoxLayout()
    ffmpeg_row.addWidget(win.ffmpeg_path); ffmpeg_row.addWidget(browse_ffmpeg)
    ytdlp_lay.addRow("Ścieżka do FFmpeg:", ffmpeg_row)
    win.check_ytdlp_updates = QCheckBox("Sprawdzaj aktualizacje YT-DLP przy starcie")
    ytdlp_lay.addRow(win.check_ytdlp_updates)
    win.auto_download_ffmpeg = QCheckBox("Automatycznie pobieraj FFmpeg jeśli brak")
    win.auto_download_ffmpeg.setToolTip("Windows: Essentials, Linux: static build.")
    win.auto_download_ffmpeg.setChecked(True)
    ytdlp_lay.addRow(win.auto_download_ffmpeg)
    ytdlp_group.setLayout(ytdlp_lay)
    tl.addWidget(ytdlp_group); tl.addStretch()
    tools_w_lay = QVBoxLayout(tools_w); tools_w_lay.setContentsMargins(0,0,0,0)
    tools_w_lay.addWidget(tools_scroll)

    # Podzakładka: Ogólne
    general_w = QWidget()
    gen_scroll = QScrollArea(); gen_scroll.setWidgetResizable(True)
    gen_content = QWidget(); gen_scroll.setWidget(gen_content)
    gl = QVBoxLayout(gen_content)
    def_group = QGroupBox("Domyślne ustawienia")
    def_lay = QFormLayout()
    win.default_output_path = QLineEdit()
    browse_def = QPushButton(" Przeglądaj...")
    browse_def.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_def.clicked.connect(win.browse_default_output_path)
    def_out_row = QHBoxLayout()
    def_out_row.addWidget(win.default_output_path); def_out_row.addWidget(browse_def)
    def_lay.addRow("Domyślna ścieżka wyjściowa:", def_out_row)
    win.default_template = QLineEdit("%(playlist_title|)s/%(title)s.%(ext)s")
    def_lay.addRow("Domyślny szablon nazwy:", win.default_template)
    win.auto_add_to_queue = QCheckBox("Automatycznie dodawaj wklejone URL-e do kolejki")
    def_lay.addRow(win.auto_add_to_queue)
    win.theme_combo = QComboBox()
    win.theme_combo.addItems(["Dark", "White"])
    win.theme_combo.currentIndexChanged.connect(win.change_theme)
    def_lay.addRow("Motyw GUI:", win.theme_combo)
    def_group.setLayout(def_lay)
    gl.addWidget(def_group); gl.addStretch()
    gen_w_lay = QVBoxLayout(general_w); gen_w_lay.setContentsMargins(0,0,0,0)
    gen_w_lay.addWidget(gen_scroll)

    # Podzakładka: CDA
    cda_w = QWidget()
    cda_scroll = QScrollArea(); cda_scroll.setWidgetResizable(True)
    cda_content = QWidget(); cda_scroll.setWidget(cda_content)
    cdal = QVBoxLayout(cda_content)
    cda_group = QGroupBox("CDA Premium")
    cda_lay = QFormLayout()
    win.cda_email = QLineEdit(); win.cda_email.setPlaceholderText("twoj@email.com")
    cda_lay.addRow("Email:", win.cda_email)
    win.cda_password = QLineEdit(); win.cda_password.setEchoMode(QLineEdit.EchoMode.Password)
    win.cda_password_show_btn = QPushButton()
    win.cda_password_show_btn.setIcon(QIcon("icons/eye.png"))
    win.cda_password_show_btn.setFixedSize(QSize(30, 24))
    win.cda_password_show_btn.setCheckable(True)
    win.cda_password_show_btn.toggled.connect(win.toggle_cda_password_visibility)
    cda_pass_row = QHBoxLayout()
    cda_pass_row.addWidget(win.cda_password); cda_pass_row.addWidget(win.cda_password_show_btn)
    cda_lay.addRow("Hasło:", cda_pass_row)
    cda_status_row = QHBoxLayout()
    win.cda_status_label = QLabel("Status: Nie sprawdzono")
    win.check_cda_status_btn = QPushButton("Sprawdź status")
    win.check_cda_status_btn.clicked.connect(win.run_cda_status_check)
    cda_status_row.addWidget(win.cda_status_label)
    cda_status_row.addStretch()
    cda_status_row.addWidget(win.check_cda_status_btn)
    cda_lay.addRow(cda_status_row)
    cda_group.setLayout(cda_lay)
    cdal.addWidget(cda_group); cdal.addStretch()
    cda_w_lay = QVBoxLayout(cda_w); cda_w_lay.setContentsMargins(0,0,0,0)
    cda_w_lay.addWidget(cda_scroll)

    inner_tabs.addTab(tools_w,   "Narzędzia")
    inner_tabs.addTab(general_w, "Ogólne")
    inner_tabs.addTab(cda_w,     "CDA Premium")

    save_row = QHBoxLayout()
    save_btn = QPushButton(" Zapisz ustawienia")
    save_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
    save_btn.clicked.connect(win.save_settings)
    save_row.addWidget(save_btn)
    load_btn = QPushButton(" Wczytaj ustawienia")
    load_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
    load_btn.clicked.connect(lambda: win.load_settings(initial=False))
    save_row.addWidget(load_btn)
    reset_btn = QPushButton(" Przywróć domyślne")
    reset_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
    reset_btn.clicked.connect(win.reset_settings)
    save_row.addWidget(reset_btn)

    outer.addWidget(inner_tabs)
    outer.addLayout(save_row)


# ---------------------------------------------------------------------------
# "O programie"
# ---------------------------------------------------------------------------

def _make_link_label(text: str, url: str) -> QLabel:
    lbl = QLabel(f'<a href="{url}">{text}</a>')
    lbl.setOpenExternalLinks(True)
    lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return lbl


def _init_about_tab(win, tab_widget: QWidget):
    layout = QVBoxLayout(tab_widget)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    title_lbl = QLabel("YTDLP-GUI")
    font = QFont(); font.setPointSize(22); font.setBold(True)
    title_lbl.setFont(font)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(title_lbl)
    desc_lbl = QLabel(
        "Graficzny interfejs użytkownika dla yt-dlp.\n"
        "Pobieraj filmy i muzykę z setek serwisów jednym kliknięciem."
    )
    desc_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    desc_lbl.setWordWrap(True)
    layout.addWidget(desc_lbl)
    layout.addSpacing(16)
    info_group = QGroupBox("Informacje")
    info_lay = QFormLayout(); info_lay.setHorizontalSpacing(16)
    info_lay.addRow("Wersja programu:", QLabel(APP_VERSION))
    info_lay.addRow("Autor:", QLabel("Paffcio"))
    win._about_ffmpeg_lbl = QLabel("Sprawdzam...")
    info_lay.addRow("Wersja FFmpeg:", win._about_ffmpeg_lbl)
    win._about_ytdlp_lbl = QLabel("Sprawdzam...")
    info_lay.addRow("Wersja yt-dlp:", win._about_ytdlp_lbl)
    info_group.setLayout(info_lay)
    layout.addWidget(info_group)
    layout.addSpacing(16)
    links_group = QGroupBox("Linki")
    links_lay = QFormLayout(); links_lay.setHorizontalSpacing(16)
    links_lay.addRow("Projekt (GitHub):",
        _make_link_label("github.com/PaffcioStudio/YTDLP-GUI",
                         "https://github.com/PaffcioStudio/YTDLP-GUI"))
    links_lay.addRow("yt-dlp:",
        _make_link_label("github.com/yt-dlp/yt-dlp", "https://github.com/yt-dlp/yt-dlp"))
    links_lay.addRow("FFmpeg:",
        _make_link_label("github.com/FFmpeg/FFmpeg", "https://github.com/FFmpeg/FFmpeg"))
    links_group.setLayout(links_lay)
    layout.addWidget(links_group)
    layout.addStretch()


# ---------------------------------------------------------------------------
# Stub'y dla starego API (main_window.py importuje te nazwy)
# — właściwa inicjalizacja odbywa się przez init_options_tabs / init_queue_panel
# ---------------------------------------------------------------------------

def init_video_tab(win, tab_widget):    pass
def init_audio_tab(win, tab_widget):   pass
def init_playlist_tab(win, tab_widget): pass
def init_queue_tab(win, tab_widget):   pass
def init_advanced_tab(win, tab_widget): pass
def init_settings_tab(win, tab_widget): pass
def init_about_tab(win, tab_widget):   pass
