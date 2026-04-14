# -*- coding: utf-8 -*-
"""Mixin: podgląd metadanych URL (miniaturka, tytuł, rozmiar)."""

import logging
from pathlib import Path
from typing import List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QMessageBox

from ..config import STRICT_URL_REGEX
from ..threads import BatchPreviewThread, PreviewFetchThread
from ..utils import human_duration, human_size

logger = logging.getLogger(__name__)


class PreviewMixin:
    def _build_format_string_for_preview(self) -> Tuple[str, str]:
        if self.extract_audio_adv.isChecked():
            return "bestaudio/best", "audio_adv"
        if self.extract_audio.isChecked():
            return "bestaudio/best", "audio"
        vfmt   = self.video_format.currentText()
        vqual  = self.video_quality.currentText()
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
        self.preview_widget.setVisible(True)
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
        self.preview_widget.setVisible(True)
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
        self.preview_widget.setVisible(False)
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
