# -*- coding: utf-8 -*-
"""Mixin: logika pobierania, kolejkowanie, retry, budowanie komendy yt-dlp."""

import logging
import shlex
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..config import DEFAULT_SOCKET_TIMEOUT
from ..threads import TitleFetchThread, YTDLPThread

logger = logging.getLogger(__name__)


class DownloadMixin:
    # =========================================================
    # Sterowanie pobieraniem
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
            self._user_stopped = True
            self.thread.stop()
            self.output_text.append("\nZatrzymuję pobieranie...")
            self.download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def download_finished(self, success: bool):
        self.stop_btn.setEnabled(False)
        self.progress_bar.setFormat("%p%")
        cur = getattr(self, "current_processing_url", None)

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

        mode = "audio_adv" if extract_adv else (
            "audio" if getattr(self, '_mode_audio', None) and self._mode_audio.isChecked()
            else ("video_only" if getattr(self, '_mode_video', None) and self._mode_video.isChecked()
                  else "video")
        )
        # fallback dla starego kodu (extract_audio checkbox)
        if mode == "video" and hasattr(self, 'extract_audio') and self.extract_audio.isChecked():
            mode = "audio"

        if recode != "Nie przetwarzaj":
            cmd += ["--recode-video", recode]

        # --no-playlist gdy użytkownik wybrał "tylko jedno wideo"
        if getattr(self, '_pl_single', None) and self._pl_single.isChecked():
            cmd.append("--no-playlist")

        if mode in ("audio", "audio_adv"):
            cmd.append("-x")
            if mode == "audio":
                if afmt != "najlepszy":
                    cmd += ["--audio-format", afmt]
                cmd += ["--audio-quality", str(aqi)]
                if hasattr(self, "keep_video") and self.keep_video.isChecked(): cmd.append("-k")
                if self.add_metadata.isChecked():    cmd.append("--add-metadata")
                if self.embed_thumbnail.isChecked(): cmd.append("--embed-thumbnail")
                out_path = self.audio_output_path.text().strip() or self.default_output_path.text().strip()
                out_tmpl = self.audio_output_template.text().strip() or self.default_template.text().strip()
            else:
                _afmt_adv = self.audio_format_adv.currentText()
                if _afmt_adv != "najlepszy":
                    cmd += ["--audio-format", _afmt_adv]
                cmd += ["--audio-quality", str(self.audio_quality_adv.currentIndex())]
                if self.keep_video_adv.isChecked(): cmd.append("-k")
                out_path = self.default_output_path.text().strip()
                out_tmpl = self.default_template.text().strip()
        else:
            if mode == "video_only":
                # tylko strumień wideo, bez audio
                if vqual == "Najlepsza (auto)":
                    fs = f"bv*[ext={vfmt}]/bv*"
                else:
                    h = vqual.split("p")[0]
                    fs = f"bv*[height<={h}][ext={vfmt}]/bv*[height<={h}]"
                if vcodec != "auto":
                    fs = fs.replace("bv*", f"bv*[vcodec~=^({vcodec})]")
                cmd += ["-f", fs]
            else:
                if vqual == "Najlepsza (auto)":
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

        # playlista - uwzględniamy nowe radio buttony
        _pl_single_active = getattr(self, '_pl_single', None) and self._pl_single.isChecked()
        _pl_range_active  = getattr(self, '_pl_range',  None) and self._pl_range.isChecked()

        if not _pl_single_active:
            if _pl_range_active or not hasattr(self, '_pl_range'):
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
            cmd += ["--no-check-certificate"]
            if "/vfilm" in url:
                if cda_email and cda_pass:
                    cmd += ["--username", cda_email, "--password", cda_pass]
                else:
                    QMessageBox.warning(self, "Brak danych CDA", "Film premium CDA wymaga danych logowania.")
                    return None
            # Zwykłe filmy CDA (bez /vfilm) – NIE przekazuj credentials.
            # Anonimowy dostęp działa, a logowanie powoduje HTTP 403.
        else:
            if cda_email and cda_pass:
                cmd += ["--username", cda_email, "--password", cda_pass]
            elif username and password:
                cmd += ["--username", username, "--password", password]

        if tf := self.twofactor.text().strip():      cmd += ["--twofactor", tf]
        if vp := self.video_password.text():         cmd += ["--video-password", vp]
        if ppa := self.postprocessor_args.text().strip(): cmd += ["--postprocessor-args", ppa]

        if raw := self.custom_ytdlp_args.text().strip():
            try:
                cmd += shlex.split(raw)
            except ValueError:
                cmd += raw.split()

        if self.ignore_errors.isChecked():  cmd.append("--ignore-errors")
        if self.no_warnings.isChecked():    cmd.append("--no-warnings")
        if self.quiet.isChecked():          cmd.append("--quiet")
        if self.no_color.isChecked():       cmd.append("--no-color")
        if self.simulate.isChecked():       cmd.append("--simulate")
        if self.skip_download.isChecked():  cmd.append("--skip-download")

        cmd.append(url)
        logger.info(f"Komenda: {' '.join(cmd)}")
        return cmd
