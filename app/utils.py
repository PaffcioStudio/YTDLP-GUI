# -*- coding: utf-8 -*-
"""
Funkcje pomocnicze (formatowanie rozmiaru, czasu, ścieżka zasobów).
"""

import os
import sys
from typing import Optional


def resource_path(relative_path: str) -> str:
    """Zwraca absolutną ścieżkę do zasobu (obsługuje PyInstaller _MEIPASS)."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def human_size(num_bytes: Optional[int]) -> str:
    """Zwraca rozmiar w czytelnej postaci (B / KB / MB / GB / TB)."""
    if not num_bytes or num_bytes <= 0:
        return "N/D"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    n = float(num_bytes)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.1f} {units[i]}"


def human_duration(seconds: int) -> str:
    """Zwraca czas trwania w postaci H:MM:SS lub M:SS."""
    try:
        s = int(seconds or 0)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h:
            return f"{h:d}:{m:02d}:{sec:02d}"
        return f"{m:d}:{sec:02d}"
    except Exception:
        return "N/D"
