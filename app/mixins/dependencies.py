# -*- coding: utf-8 -*-
"""Mixin: sprawdzanie i pobieranie zależności (yt-dlp, FFmpeg)."""

import re
import subprocess

from ..threads import DownloadFFmpegThread, UpdateYTDLPThread


class DependenciesMixin:
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

    def _refresh_about_versions(self):
        """Aktualizuje etykiety wersji w zakładce 'O programie'."""
        try:
            ytdlp = self.get_ytdlp_path()
            r = subprocess.run([ytdlp, "--version"], capture_output=True, text=True,
                               timeout=5, encoding="utf-8")
            self._about_ytdlp_lbl.setText(r.stdout.strip() or "brak")
        except Exception:
            self._about_ytdlp_lbl.setText("brak")
        try:
            ffmpeg = self.get_ffmpeg_path() or "ffmpeg"
            r = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True,
                               timeout=5, encoding="utf-8")
            m = re.search(r"ffmpeg version (\S+)", r.stdout or r.stderr)
            self._about_ffmpeg_lbl.setText(m.group(1) if m else "brak")
        except Exception:
            self._about_ffmpeg_lbl.setText("brak")
