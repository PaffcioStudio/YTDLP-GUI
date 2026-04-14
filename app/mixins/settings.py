# -*- coding: utf-8 -*-
"""Mixin: zapis, odczyt i reset ustawień aplikacji."""

import logging

from PyQt6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


class SettingsMixin:
    def save_settings(self):
        s = self.settings
        s.setValue("ytdlp_path",  self.ytdlp_path_input.text().strip().replace("\\", "/"))
        s.setValue("ffmpeg_path", self.ffmpeg_path.text().strip().replace("\\", "/"))
        s.setValue("check_ytdlp_updates",  self.check_ytdlp_updates.isChecked())
        s.setValue("auto_download_ffmpeg", self.auto_download_ffmpeg.isChecked())
        s.setValue("cda_email",    self.cda_email.text().strip())
        s.setValue("cda_password", self.cda_password.text())
        s.setValue("default_output_path", self.default_output_path.text().strip())
        s.setValue("default_template",    self.default_template.text().strip())
        s.setValue("auto_add_to_queue",   self.auto_add_to_queue.isChecked())
        s.setValue("theme", self.theme_combo.currentText())

        # wideo
        s.setValue("video_format",    self.video_format.currentText())
        s.setValue("video_quality",   self.video_quality.currentIndex())
        s.setValue("video_codec",     self.video_codec.currentText())
        s.setValue("embed_thumbnails", self.embed_thumbnails.isChecked())
        s.setValue("embed_subs",       self.embed_subs.isChecked())
        s.setValue("output_template",  self.output_template.text().strip())
        s.setValue("output_path",      self.output_path.text().strip())
        s.setValue("limit_rate",       self.limit_rate.text().strip())
        s.setValue("retries",          self.retries.value())
        s.setValue("extract_audio",    self.extract_audio.isChecked())
        s.setValue("keep_video",       self.keep_video.isChecked())
        s.setValue("write_subs",       self.write_subs.isChecked())
        s.setValue("write_auto_subs",  self.write_auto_subs.isChecked())
        s.setValue("write_info_json",  self.write_info_json.isChecked())

        # audio
        s.setValue("audio_format",         self.audio_format.currentText())
        s.setValue("audio_quality",        self.audio_quality.currentIndex())
        s.setValue("add_metadata",         self.add_metadata.isChecked())
        s.setValue("embed_thumbnail",      self.embed_thumbnail.isChecked())
        s.setValue("audio_output_template", self.audio_output_template.text().strip())
        s.setValue("audio_output_path",    self.audio_output_path.text().strip())
        s.setValue("prefer_ffmpeg",        self.prefer_ffmpeg.isChecked())

        # playlista
        s.setValue("playlist_start",   self.playlist_start.value())
        s.setValue("playlist_end",     self.playlist_end.value())
        s.setValue("playlist_items",   self.playlist_items.text().strip())
        s.setValue("playlist_reverse", self.playlist_reverse.isChecked())
        s.setValue("playlist_random",  self.playlist_random.isChecked())
        s.setValue("use_archive",      self.use_archive.isChecked())
        s.setValue("archive_file",     self.archive_file.text().strip())

        # sieć / auth
        s.setValue("proxy",          self.proxy.text().strip())
        s.setValue("source_address", self.source_address.text().strip())
        s.setValue("force_ipv4",     self.force_ipv4.isChecked())
        s.setValue("force_ipv6",     self.force_ipv6.isChecked())
        s.setValue("username",       self.username.text().strip())
        s.setValue("password",       self.password.text())
        s.setValue("twofactor",      self.twofactor.text().strip())
        s.setValue("video_password", self.video_password.text())

        # zaawansowane
        s.setValue("extract_audio_adv",  self.extract_audio_adv.isChecked())
        s.setValue("audio_format_adv",   self.audio_format_adv.currentText())
        s.setValue("audio_quality_adv",  self.audio_quality_adv.currentIndex())
        s.setValue("keep_video_adv",     self.keep_video_adv.isChecked())
        s.setValue("recode_video",       self.recode_video.currentText())
        s.setValue("postprocessor_args", self.postprocessor_args.text().strip())
        s.setValue("custom_ytdlp_args", self.custom_ytdlp_args.text().strip())
        s.setValue("ignore_errors",      self.ignore_errors.isChecked())
        s.setValue("no_warnings",        self.no_warnings.isChecked())
        s.setValue("quiet",              self.quiet.isChecked())
        s.setValue("no_color",           self.no_color.isChecked())
        s.setValue("simulate",           self.simulate.isChecked())
        s.setValue("skip_download",      self.skip_download.isChecked())
        s.setValue("max_retry_per_item", self.max_retry_per_item.value())
        s.setValue("enable_clipboard_monitor", self.enable_clipboard_monitor.isChecked())

        s.sync()
        if self.enable_clipboard_monitor.isChecked():
            if not self.clipboard_timer.isActive():
                self.clipboard_timer.start()
        else:
            self.clipboard_timer.stop()
        logger.info("Ustawienia zapisane.")

    def load_settings(self, initial: bool = False):
        s = self.settings
        logger.info("Wczytuję ustawienia...")

        self.check_ytdlp_updates.setChecked(s.value("check_ytdlp_updates", True, type=bool))
        self.auto_download_ffmpeg.setChecked(s.value("auto_download_ffmpeg", True, type=bool))

        saved_out = s.value("default_output_path", "", type=str).strip()
        self.default_output_path.setText(saved_out or self.get_user_downloads_path())
        self.default_template.setText(s.value("default_template", "%(title)s.%(ext)s", type=str).strip())
        self.auto_add_to_queue.setChecked(s.value("auto_add_to_queue", False, type=bool))

        theme = s.value("theme", "Dark", type=str)
        idx = self.theme_combo.findText(theme)
        self.theme_combo.setCurrentIndex(idx if idx != -1 else 0)

        self.ytdlp_path_input.setText(self.get_ytdlp_path())
        self.ffmpeg_path.setText(self.get_ffmpeg_path())
        self.cda_email.setText(s.value("cda_email", "", type=str).strip())
        self.cda_password.setText(s.value("cda_password", "", type=str))

        self.video_format.setCurrentText(s.value("video_format", "mp4", type=str))
        self.video_quality.setCurrentIndex(s.value("video_quality", 0, type=int))
        self.video_codec.setCurrentText(s.value("video_codec", "auto", type=str))
        self.embed_thumbnails.setChecked(s.value("embed_thumbnails", True, type=bool))
        self.embed_subs.setChecked(s.value("embed_subs", False, type=bool))

        tmpl = s.value("output_template", "", type=str).strip()
        self.output_template.setText(tmpl or self.default_template.text())
        out_p = s.value("output_path", "", type=str).strip()
        self.output_path.setText(out_p or self.default_output_path.text())
        self.limit_rate.setText(s.value("limit_rate", "", type=str).strip())
        self.retries.setValue(s.value("retries", 10, type=int))
        self.extract_audio.setChecked(s.value("extract_audio", False, type=bool))
        self.keep_video.setChecked(s.value("keep_video", False, type=bool))
        self.write_subs.setChecked(s.value("write_subs", False, type=bool))
        self.write_auto_subs.setChecked(s.value("write_auto_subs", False, type=bool))
        self.write_info_json.setChecked(s.value("write_info_json", False, type=bool))

        self.audio_format.setCurrentText(s.value("audio_format", "najlepszy", type=str))
        try:
            self.audio_quality.setCurrentIndex(int(s.value("audio_quality", 0)))
        except Exception:
            self.audio_quality.setCurrentIndex(0)
        self.add_metadata.setChecked(s.value("add_metadata", True, type=bool))
        self.embed_thumbnail.setChecked(s.value("embed_thumbnail", True, type=bool))
        at = s.value("audio_output_template", "", type=str).strip()
        self.audio_output_template.setText(at or self.default_template.text())
        ap = s.value("audio_output_path", "", type=str).strip()
        self.audio_output_path.setText(ap or self.default_output_path.text())
        self.prefer_ffmpeg.setChecked(s.value("prefer_ffmpeg", False, type=bool))

        self.playlist_start.setValue(s.value("playlist_start", 1, type=int))
        self.playlist_end.setValue(s.value("playlist_end", 0, type=int))
        self.playlist_items.setText(s.value("playlist_items", "", type=str).strip())
        self.playlist_reverse.setChecked(s.value("playlist_reverse", False, type=bool))
        self.playlist_random.setChecked(s.value("playlist_random", False, type=bool))
        self.use_archive.setChecked(s.value("use_archive", False, type=bool))
        arch = s.value("archive_file", "", type=str).strip()
        self.archive_file.setText(arch or str(self.appdata_dir / "archive.txt"))
        (self.appdata_dir / "archive.txt").parent.mkdir(parents=True, exist_ok=True)

        self.proxy.setText(s.value("proxy", "", type=str).strip())
        self.source_address.setText(s.value("source_address", "", type=str).strip())
        self.force_ipv4.setChecked(s.value("force_ipv4", False, type=bool))
        self.force_ipv6.setChecked(s.value("force_ipv6", False, type=bool))
        self.username.setText(s.value("username", "", type=str).strip())
        self.password.setText(s.value("password", "", type=str))
        self.twofactor.setText(s.value("twofactor", "", type=str).strip())
        self.video_password.setText(s.value("video_password", "", type=str))

        self.extract_audio_adv.setChecked(s.value("extract_audio_adv", False, type=bool))
        self.audio_format_adv.setCurrentText(s.value("audio_format_adv", "najlepszy", type=str))
        try:
            self.audio_quality_adv.setCurrentIndex(int(s.value("audio_quality_adv", 0)))
        except Exception:
            self.audio_quality_adv.setCurrentIndex(0)
        self.keep_video_adv.setChecked(s.value("keep_video_adv", False, type=bool))
        self.recode_video.setCurrentText(s.value("recode_video", "Nie przetwarzaj", type=str))
        self.postprocessor_args.setText(s.value("postprocessor_args", "", type=str).strip())
        self.custom_ytdlp_args.setText(s.value("custom_ytdlp_args", "", type=str).strip())
        self.ignore_errors.setChecked(s.value("ignore_errors", False, type=bool))
        self.no_warnings.setChecked(s.value("no_warnings", False, type=bool))
        self.quiet.setChecked(s.value("quiet", False, type=bool))
        self.no_color.setChecked(s.value("no_color", False, type=bool))
        self.simulate.setChecked(s.value("simulate", False, type=bool))
        self.skip_download.setChecked(s.value("skip_download", False, type=bool))
        self.max_retry_per_item.setValue(s.value("max_retry_per_item", 2, type=int))
        self.enable_clipboard_monitor.setChecked(s.value("enable_clipboard_monitor", False, type=bool))

        if self.enable_clipboard_monitor.isChecked():
            self.clipboard_timer.start()
        else:
            self.clipboard_timer.stop()

        if not initial:
            QMessageBox.information(self, "Ustawienia wczytane", "Ustawienia zostały wczytane.")

    def reset_settings(self):
        r = QMessageBox.question(
            self, "Resetuj ustawienia",
            "Czy na pewno chcesz zresetować ustawienia do domyślnych?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            self.settings.clear()
            self.default_output_path.setText(self.get_user_downloads_path())
            self.default_template.setText("%(title)s.%(ext)s")
            self.archive_file.setText(str(self.appdata_dir / "archive.txt"))
            self.load_settings(initial=False)
            self.apply_style()
            QMessageBox.information(self, "Zresetowano", "Ustawienia zresetowane do domyślnych.")
