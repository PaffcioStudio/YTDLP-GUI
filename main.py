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

from PyQt6.QtWidgets import QApplication

from app.main_window import YTDLPGUI


def main():
    app = QApplication(sys.argv)
    window = YTDLPGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
