# -*- coding: utf-8 -*-
"""Mixin: aktualizacje paska postępu i konsoli wyjścia."""

import logging
import re

logger = logging.getLogger(__name__)


class ProgressMixin:
    def _clear_detailed_active(self):
        if hasattr(self.progress_bar, "_detailed_active"):
            delattr(self.progress_bar, "_detailed_active")

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
