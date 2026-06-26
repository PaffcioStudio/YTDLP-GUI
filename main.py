#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Downloader – punkt wejścia aplikacji.

Uruchomienie:
    python main.py

lub po zbudowaniu przez PyInstaller:
    ./YTDLP-GUI
"""

import sys
import os

# Wymuszenie UTF-8 na Windows - bez tego polskie znaki w QMessageBox moga byc krzakami
if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    os.environ.setdefault("PYTHONUTF8", "1")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

from app.main_window import YTDLPGUI


def main():
    # UTF-8 dla Qt na Windows
    QCoreApplication.setApplicationName("YTDLP-GUI")
    QCoreApplication.setOrganizationName("PaffcioStudio")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Spójny wygląd na wszystkich platformach

    window = YTDLPGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
