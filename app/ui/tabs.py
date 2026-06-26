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

from ..config import FFMPEG_PATH_WINDOWS, LIBS_DIR, YTDLP_PATH_WINDOWS, get_icon_path
from ..queue_widget import QueueListWidget

def _read_version() -> str:
    import pathlib, sys, os
    candidates = []
    # 1. PyInstaller onefile - sys._MEIPASS (EXE Windows i Linux)
    if hasattr(sys, "_MEIPASS"):
        candidates.append(pathlib.Path(sys._MEIPASS) / "VERSION")
    # 2. AppImage - zmienna srodowiskowa APPDIR
    if os.environ.get("APPDIR"):
        candidates.append(pathlib.Path(os.environ["APPDIR"]) / "usr" / "share" / "ytdlp-gui" / "VERSION")
    # 3. DEB - zainstalowany systemowo
    candidates.append(pathlib.Path("/usr/share/ytdlp-gui/VERSION"))
    # 4. Uruchomienie z source (dev)
    candidates.append(pathlib.Path(__file__).parent.parent.parent / "VERSION")
    for path in candidates:
        try:
            v = path.read_text().strip()
            if v:
                return v
        except Exception:
            continue
    return "?.?.?"

APP_VERSION = _read_version()


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


# ---------------------------------------------------------------------------
# Tryb zaawansowany - helper
# ---------------------------------------------------------------------------

def _apply_advanced_mode(win, enabled: bool):
    """Pokazuje lub chowa zakladki Playlista i Zaawansowane."""
    tabs = win.options_tabs
    if enabled:
        titles = [tabs.tabText(i) for i in range(tabs.count())]
        if "Playlista" not in titles:
            tabs.insertTab(1, win._playlist_tab_widget, "Playlista")
        titles = [tabs.tabText(i) for i in range(tabs.count())]
        if "Zaawansowane" not in titles:
            pl_idx = titles.index("Playlista") if "Playlista" in titles else 1
            tabs.insertTab(pl_idx + 1, win._advanced_tab_widget, "Zaawansowane")
    else:
        for name in ["Zaawansowane", "Playlista"]:
            titles = [tabs.tabText(i) for i in range(tabs.count())]
            if name in titles:
                tabs.removeTab(titles.index(name))


# ---------------------------------------------------------------------------
# init_options_tabs
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

    win._playlist_tab_widget = playlist_tab
    win._advanced_tab_widget = advanced_tab

    win.options_tabs.addTab(format_tab,   "Pobieranie")
    win.options_tabs.addTab(playlist_tab, "Playlista")
    win.options_tabs.addTab(advanced_tab, "Zaawansowane")
    win.options_tabs.addTab(settings_tab, "Ustawienia")
    win.options_tabs.addTab(about_tab,    "O programie")

    layout.addWidget(win.options_tabs)


# ---------------------------------------------------------------------------
# "Pobieranie" - glowna zakladka (dawniej "Format i tryb")
# ---------------------------------------------------------------------------

def _init_format_tab(win, tab_widget: QWidget):
    outer = QVBoxLayout(tab_widget)
    outer.setSpacing(8)
    outer.setContentsMargins(8, 8, 8, 8)
    scroll = QScrollArea(); scroll.setWidgetResizable(True)
    content = QWidget(); scroll.setWidget(content)
    cl = QVBoxLayout(content)
    cl.setSpacing(10)

    # --- 1. Playlisty vs pojedyncze wideo ---
    pl_group = QGroupBox("Co pobrac?")
    pl_layout = QHBoxLayout()
    pl_layout.setSpacing(12)

    win._pl_single = QRadioButton("Tylko to wideo")
    win._pl_single.setToolTip("Ignoruje playlisty - pobiera tylko ten jeden film z linku.")
    win._pl_all    = QRadioButton("Cala playliste")
    win._pl_all.setToolTip("Pobiera wszystkie filmy z playlisty/kanalu.")
    win._pl_all.setChecked(True)

    pl_layout.addWidget(win._pl_single)
    pl_layout.addWidget(win._pl_all)
    pl_layout.addStretch()

    # Przycisk trybu zaawansowanego - widoczny zawsze
    win._adv_mode_btn = QPushButton("+ Tryb zaawansowany")
    win._adv_mode_btn.setCheckable(True)
    win._adv_mode_btn.setToolTip(
        "Wlacza dodatkowe zakladki: Playlista (zakres, kolejnosc) i Zaawansowane (proxy, FFmpeg, argumenty)."
    )

    def _on_adv_toggled(checked):
        win._adv_mode_btn.setText("- Tryb zaawansowany" if checked else "+ Tryb zaawansowany")
        _apply_advanced_mode(win, checked)
        win.advanced_mode.blockSignals(True)
        win.advanced_mode.setChecked(checked)
        win.advanced_mode.blockSignals(False)

    win._adv_mode_btn.toggled.connect(_on_adv_toggled)
    pl_layout.addWidget(win._adv_mode_btn)

    pl_group.setLayout(pl_layout)
    cl.addWidget(pl_group)

    # --- 2. Co pobrac: wideo/audio/wideo bez audio ---
    mode_group = QGroupBox("Typ pobierania")
    mode_layout = QHBoxLayout()
    mode_layout.setSpacing(12)
    win._mode_both  = QRadioButton("Wideo + audio")
    win._mode_audio = QRadioButton("Tylko audio")
    win._mode_video = QRadioButton("Tylko wideo (bez dzwieku)")
    win._mode_both.setChecked(True)
    win._mode_both.setToolTip("Pobiera najlepsze wideo i scala z audio przez FFmpeg.")
    win._mode_audio.setToolTip("Pobiera audio i konwertuje do wybranego formatu (mp3, flac, itp.).")
    win._mode_video.setToolTip("Sam strumien wideo bez dzwieku - do dalszej obrobki.")
    mode_layout.addWidget(win._mode_both)
    mode_layout.addWidget(win._mode_audio)
    mode_layout.addWidget(win._mode_video)
    mode_layout.addStretch()
    mode_group.setLayout(mode_layout)
    cl.addWidget(mode_group)

    # --- 3. Jakosc - zawsze na widoku ---
    quality_group = QGroupBox("Jakosc")
    quality_lay = QGridLayout()
    quality_lay.setSpacing(8)
    quality_lay.setColumnStretch(1, 1)

    win.video_quality = QComboBox()
    win.video_quality.addItems([
        "Najlepsza (auto)", "2160p (4K)", "1440p (2K)",
        "1080p", "720p", "480p", "360p", "240p", "144p",
    ])
    quality_lay.addWidget(QLabel("Jakosc wideo:"), 0, 0)
    quality_lay.addWidget(win.video_quality, 0, 1)

    win.video_format = QComboBox()
    win.video_format.addItems(["mp4", "webm", "mkv", "flv", "avi"])
    quality_lay.addWidget(QLabel("Format wideo:"), 1, 0)
    quality_lay.addWidget(win.video_format, 1, 1)

    win.video_codec = QComboBox()
    win.video_codec.addItems(["auto", "h264", "h265", "vp9", "av1"])
    quality_lay.addWidget(QLabel("Kodek wideo:"), 2, 0)
    quality_lay.addWidget(win.video_codec, 2, 1)

    win.audio_format = QComboBox()
    win.audio_format.addItems(["najlepszy", "mp3", "aac", "flac", "m4a", "opus", "vorbis", "wav"])
    quality_lay.addWidget(QLabel("Format audio:"), 3, 0)
    quality_lay.addWidget(win.audio_format, 3, 1)

    win.audio_quality = QComboBox()
    win.audio_quality.addItems([
        f"{i} ({'najlepsza' if i == 0 else 'najgorsza' if i == 9 else ''})" for i in range(10)
    ])
    quality_lay.addWidget(QLabel("Jakosc audio (VBR):"), 4, 0)
    quality_lay.addWidget(win.audio_quality, 4, 1)

    quality_group.setLayout(quality_lay)
    cl.addWidget(quality_group)

    # Widocznosc pol jakosci w zaleznosci od trybu
    def _update_quality_visibility():
        is_audio = win._mode_audio.isChecked()
        is_video_only = win._mode_video.isChecked()
        win.video_quality.setEnabled(not is_audio)
        win.video_format.setEnabled(not is_audio)
        win.video_codec.setEnabled(not is_audio)
        win.audio_format.setEnabled(is_audio)
        win.audio_quality.setEnabled(is_audio)

    win._mode_both.toggled.connect(lambda _: _update_quality_visibility())
    win._mode_audio.toggled.connect(lambda _: _update_quality_visibility())
    win._mode_video.toggled.connect(lambda _: _update_quality_visibility())
    _update_quality_visibility()

    # --- 4. Plik wyjsciowy ---
    file_group = QGroupBox("Plik wyjsciowy")
    file_lay = QFormLayout()
    file_lay.setSpacing(6)

    win.output_path = QLineEdit()
    browse_out = QPushButton(" Przegladaj...")
    browse_out.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_out.clicked.connect(win.browse_output_path)
    out_row = QHBoxLayout()
    out_row.addWidget(win.output_path); out_row.addWidget(browse_out)
    file_lay.addRow("Katalog:", out_row)

    win.output_template = QLineEdit("%(playlist_title|)s/%(title)s.%(ext)s")
    win.output_template.setToolTip(
        "Szablon nazwy plikow.\n"
        "%(title)s - tytul, %(ext)s - rozszerzenie,\n"
        "%(playlist_title|)s - nazwa playlisty (puste dla pojedynczego wideo)"
    )
    file_lay.addRow("Szablon nazwy:", win.output_template)

    win.limit_rate = QLineEdit()
    win.limit_rate.setPlaceholderText("np. 50K lub 4.2M  (puste = bez limitu)")
    file_lay.addRow("Limit predkosci:", win.limit_rate)

    file_group.setLayout(file_lay)
    cl.addWidget(file_group)

    # --- 5. Opcje osadzania ---
    embed_group = QGroupBox("Opcje")
    embed_lay = QVBoxLayout()
    embed_lay.setSpacing(4)
    win.embed_thumbnails = QCheckBox("Osadz miniaturke")
    win.embed_thumbnails.setChecked(True)
    win.embed_subs      = QCheckBox("Osadz napisy")
    win.write_subs      = QCheckBox("Zapisz napisy do pliku")
    win.write_auto_subs = QCheckBox("Zapisz automatyczne napisy")
    win.add_metadata    = QCheckBox("Dodaj metadane (artysta, tytul, itp.)")
    win.add_metadata.setChecked(True)
    win.write_info_json = QCheckBox("Zapisz metadane do .info.json")
    for w_ in (win.embed_thumbnails, win.embed_subs, win.write_subs,
               win.write_auto_subs, win.add_metadata, win.write_info_json):
        embed_lay.addWidget(w_)
    embed_group.setLayout(embed_lay)
    cl.addWidget(embed_group)

    cl.addStretch()
    outer.addWidget(scroll)

    # Aliasy dla kompatybilnosci z reszta kodu
    win.audio_output_template = win.output_template
    win.audio_output_path     = win.output_path
    win.embed_thumbnail       = win.embed_thumbnails
    win.extract_audio         = QCheckBox()  # ukryty, uzywany przez DownloadMixin
    win.keep_video            = QCheckBox()
    win.retries               = QSpinBox(); win.retries.setValue(10)
    win.prefer_ffmpeg         = QCheckBox()


# ---------------------------------------------------------------------------
# "Playlista" - tylko w trybie zaawansowanym
# ---------------------------------------------------------------------------

def _init_playlist_tab(win, tab_widget: QWidget):
    layout = QVBoxLayout(tab_widget)
    scroll = QScrollArea(); scroll.setWidgetResizable(True)
    content = QWidget(); scroll.setWidget(content)
    cl = QVBoxLayout(content)
    cl.setSpacing(10)

    info = QLabel(
        "<i>Te opcje sa dostepne tylko gdy pobierasz playlisty.<br>"
        "Wybor 'Tylko to wideo' vs 'Cala playliste' jest na zakladce <b>Pobieranie</b>.</i>"
    )
    info.setWordWrap(True)
    cl.addWidget(info)

    win._pl_range  = QRadioButton("Pobierz fragment / konkretne pozycje")

    range_group = QGroupBox("Zakres / konkretne pozycje")
    rp = QFormLayout()
    win.playlist_start = QSpinBox(); win.playlist_start.setRange(1, 9999)
    rp.addRow("Rozpocznij od pozycji:", win.playlist_start)
    win.playlist_end = QSpinBox(); win.playlist_end.setRange(0, 9999)
    win.playlist_end.setSpecialValueText("Do konca")
    rp.addRow("Zakoncz na pozycji:", win.playlist_end)
    win.playlist_items = QLineEdit()
    win.playlist_items.setPlaceholderText("np. 1,3,5-8  albo  2-10  (nadpisuje pola powyzej)")
    rp.addRow("Konkretne pozycje:", win.playlist_items)
    range_group.setLayout(rp)
    cl.addWidget(range_group)

    order_group = QGroupBox("Kolejnosc pobierania")
    ol = QVBoxLayout()
    win.playlist_reverse = QCheckBox("Pobierz w odwrotnej kolejnosci")
    win.playlist_random  = QCheckBox("Pobierz w losowej kolejnosci")
    ol.addWidget(win.playlist_reverse); ol.addWidget(win.playlist_random)
    order_group.setLayout(ol)
    cl.addWidget(order_group)

    arch_group = QGroupBox("Plik archiwum (pomin juz pobrane)")
    arch_lay = QVBoxLayout()
    win.use_archive = QCheckBox("Uzywaj pliku archiwum")
    arch_lay.addWidget(win.use_archive)
    arch_row = QHBoxLayout()
    win.archive_file = QLineEdit()
    win.archive_file.setPlaceholderText("Domyslnie: archive.txt w katalogu aplikacji")
    browse_arch = QPushButton(" Przegladaj...")
    browse_arch.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_arch.clicked.connect(win.browse_archive_file)
    arch_row.addWidget(win.archive_file); arch_row.addWidget(browse_arch)
    arch_lay.addLayout(arch_row)
    arch_group.setLayout(arch_lay)
    cl.addWidget(arch_group)

    cl.addStretch()
    layout.addWidget(scroll)


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
    win.password_show_btn.setIcon(QIcon(get_icon_path("eye.png")))
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


# ---------------------------------------------------------------------------
# "Ustawienia"
# ---------------------------------------------------------------------------

def _init_settings_tab(win, tab_widget: QWidget):
    outer = QVBoxLayout(tab_widget)
    inner_tabs = QTabWidget()
    style = win.style()

    # --- Podzakladka: Ogolne ---
    general_w = QWidget()
    gen_scroll = QScrollArea(); gen_scroll.setWidgetResizable(True)
    gen_content = QWidget(); gen_scroll.setWidget(gen_content)
    gl = QVBoxLayout(gen_content)

    def_group = QGroupBox("Domyslne ustawienia pobierania")
    def_lay = QFormLayout(); def_lay.setSpacing(6)

    win.default_output_path = QLineEdit()
    browse_def = QPushButton(" Przegladaj...")
    browse_def.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_def.clicked.connect(win.browse_default_output_path)
    def_out_row = QHBoxLayout()
    def_out_row.addWidget(win.default_output_path); def_out_row.addWidget(browse_def)
    def_lay.addRow("Domyslna sciezka wyjsciowa:", def_out_row)

    win.default_template = QLineEdit("%(playlist_title|)s/%(title)s.%(ext)s")
    win.default_template.setToolTip(
        "Szablon nazwy plikow.\n%(title)s, %(ext)s, %(playlist_title|)s itp."
    )
    def_lay.addRow("Domyslny szablon nazwy:", win.default_template)

    win.auto_add_to_queue = QCheckBox("Automatycznie dodawaj wklejone URL-e do kolejki")
    def_lay.addRow(win.auto_add_to_queue)
    def_group.setLayout(def_lay)
    gl.addWidget(def_group)

    ui_group = QGroupBox("Interfejs")
    ui_lay = QFormLayout(); ui_lay.setSpacing(6)

    win.theme_combo = QComboBox()
    win.theme_combo.addItems(["Dark", "White"])
    win.theme_combo.currentIndexChanged.connect(win.change_theme)
    ui_lay.addRow("Motyw:", win.theme_combo)

    win.advanced_mode = QCheckBox("Tryb zaawansowany (zakladki Playlista i Zaawansowane)")
    win.advanced_mode.setToolTip(
        "Wlacza dodatkowe zakladki z opcjami zakresu playlist,\n"
        "proxy, argumentow FFmpeg i innych zaawansowanych ustawien."
    )
    win.advanced_mode.toggled.connect(lambda checked: _apply_advanced_mode(win, checked))
    win.advanced_mode.toggled.connect(lambda checked: win._adv_mode_btn.setChecked(checked))
    ui_lay.addRow(win.advanced_mode)
    ui_group.setLayout(ui_lay)
    gl.addWidget(ui_group)
    gl.addStretch()

    gen_w_lay = QVBoxLayout(general_w); gen_w_lay.setContentsMargins(0, 0, 0, 0)
    gen_w_lay.addWidget(gen_scroll)

    # --- Podzakladka: Narzedzia ---
    tools_w = QWidget()
    tools_scroll = QScrollArea(); tools_scroll.setWidgetResizable(True)
    tools_content = QWidget(); tools_scroll.setWidget(tools_content)
    tl = QVBoxLayout(tools_content)

    ytdlp_group = QGroupBox("Sciezki do narzedzi")
    ytdlp_lay = QFormLayout(); ytdlp_lay.setSpacing(6)

    win.ytdlp_path_input = QLineEdit(win.get_ytdlp_path())
    win.ytdlp_path_input.setPlaceholderText(f"Domyslnie: {YTDLP_PATH_WINDOWS} (Win) lub 'yt-dlp' (PATH)")
    browse_ytdlp = QPushButton(" Przegladaj...")
    browse_ytdlp.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_ytdlp.clicked.connect(win.browse_ytdlp_path)
    ytdlp_row = QHBoxLayout()
    ytdlp_row.addWidget(win.ytdlp_path_input); ytdlp_row.addWidget(browse_ytdlp)
    ytdlp_lay.addRow("Sciezka do YT-DLP:", ytdlp_row)

    win.ffmpeg_path = QLineEdit(win.get_ffmpeg_path())
    win.ffmpeg_path.setPlaceholderText(f"Domyslnie: {FFMPEG_PATH_WINDOWS} (Win) lub 'ffmpeg' (PATH)")
    browse_ffmpeg = QPushButton(" Przegladaj...")
    browse_ffmpeg.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_ffmpeg.clicked.connect(win.browse_ffmpeg_path)
    ffmpeg_row = QHBoxLayout()
    ffmpeg_row.addWidget(win.ffmpeg_path); ffmpeg_row.addWidget(browse_ffmpeg)
    ytdlp_lay.addRow("Sciezka do FFmpeg:", ffmpeg_row)

    win.check_ytdlp_updates = QCheckBox("Sprawdzaj aktualizacje YT-DLP przy starcie")
    ytdlp_lay.addRow(win.check_ytdlp_updates)

    win.auto_download_ffmpeg = QCheckBox("Automatycznie pobieraj FFmpeg jesli brak")
    win.auto_download_ffmpeg.setToolTip("Windows: Essentials, Linux: static build.")
    win.auto_download_ffmpeg.setChecked(True)
    ytdlp_lay.addRow(win.auto_download_ffmpeg)

    ytdlp_group.setLayout(ytdlp_lay)
    tl.addWidget(ytdlp_group); tl.addStretch()

    tools_w_lay = QVBoxLayout(tools_w); tools_w_lay.setContentsMargins(0, 0, 0, 0)
    tools_w_lay.addWidget(tools_scroll)

    # --- Podzakladka: Konta ---
    accounts_w = QWidget()
    acc_scroll = QScrollArea(); acc_scroll.setWidgetResizable(True)
    acc_content = QWidget(); acc_scroll.setWidget(acc_content)
    acl = QVBoxLayout(acc_content)
    acl.setSpacing(12)

    acc_info = QLabel(
        "<i>Tutaj skonfiguruj konta dla serwisow wymagajacych logowania.<br>"
        "Dane sa przechowywane lokalnie w ustawieniach aplikacji.</i>"
    )
    acc_info.setWordWrap(True)
    acl.addWidget(acc_info)

    # CDA Premium
    cda_group = QGroupBox("CDA Premium")
    cda_lay = QFormLayout(); cda_lay.setSpacing(6)

    win.cda_email = QLineEdit(); win.cda_email.setPlaceholderText("twoj@email.com")
    cda_lay.addRow("Email:", win.cda_email)

    win.cda_password = QLineEdit(); win.cda_password.setEchoMode(QLineEdit.EchoMode.Password)
    win.cda_password_show_btn = QPushButton()
    win.cda_password_show_btn.setIcon(QIcon(get_icon_path("eye.png")))
    win.cda_password_show_btn.setFixedSize(QSize(30, 24))
    win.cda_password_show_btn.setCheckable(True)
    win.cda_password_show_btn.toggled.connect(win.toggle_cda_password_visibility)
    cda_pass_row = QHBoxLayout()
    cda_pass_row.addWidget(win.cda_password); cda_pass_row.addWidget(win.cda_password_show_btn)
    cda_lay.addRow("Haslo:", cda_pass_row)

    cda_status_row = QHBoxLayout()
    win.cda_status_label = QLabel("Status: Nie sprawdzono")
    win.check_cda_status_btn = QPushButton("Sprawdz status")
    win.check_cda_status_btn.clicked.connect(win.run_cda_status_check)
    cda_status_row.addWidget(win.cda_status_label)
    cda_status_row.addStretch()
    cda_status_row.addWidget(win.check_cda_status_btn)
    cda_lay.addRow(cda_status_row)
    cda_group.setLayout(cda_lay)
    acl.addWidget(cda_group)

    acl.addStretch()
    accounts_w_lay = QVBoxLayout(accounts_w); accounts_w_lay.setContentsMargins(0, 0, 0, 0)
    accounts_w_lay.addWidget(acc_scroll)

    # Skladamy podzakladki
    inner_tabs.addTab(general_w, "Ogolne")
    inner_tabs.addTab(tools_w,   "Narzedzia")
    inner_tabs.addTab(accounts_w, "Konta")

    # Przyciski zapisu
    save_row = QHBoxLayout()
    save_btn = QPushButton(" Zapisz ustawienia")
    save_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
    save_btn.clicked.connect(win.save_settings)
    save_row.addWidget(save_btn)
    load_btn = QPushButton(" Wczytaj ustawienia")
    load_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
    load_btn.clicked.connect(lambda: win.load_settings(initial=False))
    save_row.addWidget(load_btn)
    reset_btn = QPushButton(" Przywroc domyslne")
    reset_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
    reset_btn.clicked.connect(win.reset_settings)
    save_row.addWidget(reset_btn)

    outer.addWidget(inner_tabs)
    outer.addLayout(save_row)


def _check_app_update(win, btn):
    from ..threads import CheckAppUpdateThread
    btn.setEnabled(False)
    win._app_update_lbl.setText("Sprawdzam...")

    def on_result(is_newer, latest_tag, release_url):
        btn.setEnabled(True)
        if is_newer:
            win._app_update_lbl.setText(
                f'Dostepna nowa wersja: <a href="{release_url}"><b>v{latest_tag}</b></a> '
                f'(masz v{APP_VERSION})'
            )
            from PyQt6.QtWidgets import QMessageBox
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            dlg = QMessageBox(win)
            dlg.setWindowTitle("Dostepna aktualizacja")
            dlg.setIcon(QMessageBox.Icon.Information)
            dlg.setText("<b>Dostepna jest nowa wersja YTDLP-GUI!</b>")
            dlg.setInformativeText(
                f"Twoja wersja: <b>v{APP_VERSION}</b><br>"
                f"Nowa wersja: <b>v{latest_tag}</b><br><br>"
                f"Czy chcesz przejsc na strone pobierania?"
            )
            btn_download = dlg.addButton("Pobierz", QMessageBox.ButtonRole.AcceptRole)
            dlg.addButton("Pozniej", QMessageBox.ButtonRole.RejectRole)
            dlg.exec()
            if dlg.clickedButton() == btn_download:
                QDesktopServices.openUrl(QUrl(release_url))
        elif latest_tag:
            win._app_update_lbl.setText(f"Masz najnowsza wersje (v{APP_VERSION}).")
        else:
            win._app_update_lbl.setText("Nie udalo sie sprawdzic aktualizacji.")

    win._update_check_thread = CheckAppUpdateThread(APP_VERSION)
    win._update_check_thread.result_signal.connect(on_result)
    win._update_check_thread.start()


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
    layout.addSpacing(8)

    # Sprawdzanie aktualizacji aplikacji
    update_group = QGroupBox("Aktualizacje")
    update_vlay = QVBoxLayout()

    win.check_app_updates_on_start = QCheckBox("Sprawdzaj aktualizacje YTDLP-GUI przy starcie")
    win.check_app_updates_on_start.setChecked(True)
    win.check_app_updates_on_start.setToolTip(
        "Jesli wlaczone, przy kazdym uruchomieniu aplikacja cicho sprawdza "
        "czy dostepna jest nowsza wersja i informuje w logu oraz tutaj."
    )
    update_vlay.addWidget(win.check_app_updates_on_start)

    update_row = QHBoxLayout()
    win._app_update_lbl = QLabel("Kliknij przycisk lub poczekaj na sprawdzenie przy starcie.")
    win._app_update_lbl.setWordWrap(True)
    win._app_update_lbl.setOpenExternalLinks(True)
    check_update_btn = QPushButton("Sprawdz teraz")
    check_update_btn.setFixedWidth(130)
    check_update_btn.clicked.connect(lambda: _check_app_update(win, check_update_btn))
    update_row.addWidget(win._app_update_lbl, 1)
    update_row.addWidget(check_update_btn)
    update_vlay.addLayout(update_row)

    update_group.setLayout(update_vlay)
    layout.addWidget(update_group)
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
