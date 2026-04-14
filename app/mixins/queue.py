# -*- coding: utf-8 -*-
"""Mixin: zarządzanie kolejką pobierania (dodawanie, usuwanie, zapis, odczyt, przeglądanie ścieżek)."""

import json
import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import List

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
)

from ..config import FFMPEG_BIN_DIR, LIBS_DIR, STRICT_URL_REGEX
from ..threads import CDAStatusCheckThread

logger = logging.getLogger(__name__)


class QueueMixin:
    # =========================================================
    # Pomocnicze UI
    # =========================================================

    def update_remove_btn_state(self):
        has = bool(self.queue_list.selectedItems())
        self.remove_btn.setEnabled(has)
        self.edit_btn.setEnabled(has)

    def toggle_password_visibility(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password.setEchoMode(mode)
        icon = "icons/eye-off.png" if checked else "icons/eye.png"
        self.password_show_btn.setIcon(QIcon(icon))
        self.password.setFocus()

    def toggle_cda_password_visibility(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.cda_password.setEchoMode(mode)
        icon = "icons/eye-off.png" if checked else "icons/eye.png"
        self.cda_password_show_btn.setIcon(QIcon(icon))
        self.cda_password.setFocus()

    def run_cda_status_check(self):
        if self.cda_check_thread and self.cda_check_thread.isRunning():
            return
        ytdlp = self.get_ytdlp_path()
        if ytdlp != "yt-dlp" and not Path(ytdlp).exists():
            self.cda_status_label.setText("<font color='red'>Status: Błąd - Nie znaleziono yt-dlp</font>")
            QMessageBox.critical(self, "Błąd YT-DLP", f"Plik YT-DLP nie znaleziony: '{ytdlp}'.")
            return
        email = self.cda_email.text().strip()
        password = self.cda_password.text()
        if not email or not password:
            QMessageBox.warning(self, "Brak danych", "Wprowadź email i hasło CDA Premium.")
            return
        self.check_cda_status_btn.setEnabled(False)
        self.cda_status_label.setText("Status: Sprawdzanie...")
        self.cda_check_thread = CDAStatusCheckThread(email, password, ytdlp, self, self)
        self.cda_check_thread.finished_signal.connect(self.handle_cda_status_result)
        self.cda_check_thread.start()

    def handle_cda_status_result(self, success: bool, message: str):
        color = "green" if success else "red"
        self.cda_status_label.setText(f"<font color='{color}'><b>Status: {message}</b></font>")
        self.check_cda_status_btn.setEnabled(True)

    # =========================================================
    # Schowek
    # =========================================================

    def paste_from_clipboard(self):
        try:
            cb = QApplication.clipboard()
            text = cb.text().strip() if cb else ""
            if not text:
                QMessageBox.warning(self, "Schowek pusty", "Schowek jest pusty.")
                return
            if STRICT_URL_REGEX.match(text):
                if not text.lower().startswith(("http://", "https://")):
                    text = "https://" + text
                self.url_input.setText(text)
                if self.auto_add_to_queue.isChecked():
                    self.add_to_queue()
            else:
                QMessageBox.warning(self, "Błędny URL", "URL nie wygląda na poprawny.")
        except Exception as e:
            logger.error(f"Błąd wklejania: {e}", exc_info=True)
            QMessageBox.critical(self, "Błąd", f"Nie udało się wkleić: {e}")

    def paste_and_add_to_queue(self):
        try:
            cb = QApplication.clipboard()
            text = cb.text().strip() if cb else ""
            if not text:
                QMessageBox.warning(self, "Schowek pusty", "Schowek jest pusty.")
                return
            self.url_input.setText(text)
            existing = {self.queue_list.item(i).text().strip()
                        for i in range(self.queue_list.count())}
            existing |= set(self.download_queue + self.failed_queue)
            if text in existing:
                QMessageBox.information(self, "Duplikat URL", f"URL już w kolejce:\n{text}")
                return
            self.add_to_queue()
        except Exception as e:
            logger.error(f"Błąd wklej+dodaj: {e}", exc_info=True)
            QMessageBox.critical(self, "Błąd", f"Nie udało się wkleić i dodać: {e}")

    def open_output_folder(self):
        path = (
            self.output_path.text().strip()
            or self.audio_output_path.text().strip()
            or self.default_output_path.text().strip()
            or self.get_user_downloads_path()
        )
        if not path:
            return
        if os.name == "nt":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])

    def add_multiple_urls_dialog(self):
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Dodaj wiele URL")
        dlg.setLabelText("Wklej wiele URL (jeden w linii):")
        dlg.resize(600, dlg.height())
        if dlg.exec() and dlg.textValue().strip():
            urls = [ln.strip() for ln in dlg.textValue().splitlines() if ln.strip()]
            self._add_urls_list(urls)

    # =========================================================
    # Przeglądanie ścieżek
    # =========================================================

    def browse_output_path(self):
        start = self.output_path.text().strip() or self.default_output_path.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Wybierz katalog wyjściowy (Wideo)", start)
        if d:
            self.output_path.setText(d)

    def browse_audio_output_path(self):
        start = self.audio_output_path.text().strip() or self.default_output_path.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Wybierz katalog wyjściowy (Audio)", start)
        if d:
            self.audio_output_path.setText(d)

    def browse_archive_file(self):
        fd = QFileDialog(self)
        fd.setFileMode(QFileDialog.FileMode.AnyFile)
        fd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        fd.setWindowTitle("Wybierz plik archiwum")
        cur = self.archive_file.text().strip()
        fd.selectFile(cur if cur else str(self.appdata_dir / "archive.txt"))
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self.archive_file.setText(files[0])

    def browse_ytdlp_path(self):
        fd = QFileDialog(self)
        fd.setFileMode(QFileDialog.FileMode.ExistingFile)
        fd.setWindowTitle("Wybierz plik yt-dlp")
        cur = self.ytdlp_path_input.text().strip()
        start = str(Path(cur).parent) if cur and Path(cur).is_absolute() else str(Path.home())
        if not Path(start).exists() and LIBS_DIR.exists():
            start = str(LIBS_DIR)
        fd.setDirectory(start)
        if os.name == "nt":
            fd.setNameFilter("Wykonywalne (*.exe);;Wszystkie pliki (*)")
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self.ytdlp_path_input.setText(files[0])

    def browse_ffmpeg_path(self):
        fd = QFileDialog(self)
        fd.setFileMode(QFileDialog.FileMode.ExistingFile)
        fd.setWindowTitle("Wybierz plik ffmpeg")
        cur = self.ffmpeg_path.text().strip()
        if cur and Path(cur).is_absolute():
            start = str(Path(cur).parent)
        elif FFMPEG_BIN_DIR.exists():
            start = str(FFMPEG_BIN_DIR)
        elif LIBS_DIR.exists():
            start = str(LIBS_DIR)
        else:
            start = str(Path.home())
        fd.setDirectory(start)
        if os.name == "nt":
            fd.setNameFilter("Wykonywalne (*.exe);;Wszystkie pliki (*)")
        if fd.exec():
            files = fd.selectedFiles()
            if files:
                self.ffmpeg_path.setText(files[0])

    def browse_default_output_path(self):
        start = self.default_output_path.text().strip() or self.get_user_downloads_path()
        d = QFileDialog.getExistingDirectory(self, "Wybierz domyślny katalog wyjściowy", start)
        if d:
            self.default_output_path.setText(d)

    # =========================================================
    # Zarządzanie kolejką
    # =========================================================

    def _add_urls_list(self, urls: List[str]):
        existing = set(self.download_queue + self.failed_queue)
        existing |= {self.queue_list.item(i).text().strip()
                     for i in range(self.queue_list.count())}
        added = []
        for url in urls:
            if not url.lower().startswith(("http://", "https://")):
                url = "https://" + url
            if not STRICT_URL_REGEX.match(url) or url in existing:
                continue
            self.download_queue.append(url)
            item = QListWidgetItem(url)
            item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
            self.queue_list.addItem(item)
            existing.add(url)
            added.append(url)
        if added:
            self.save_queue()
            self.output_text.append(f"Dodano {len(added)} URL do kolejki.")
            self._start_batch_preview(added)

    def add_to_queue(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Błąd", "Wpisz URL aby dodać do kolejki.")
            return
        existing = set(self.download_queue + self.failed_queue)
        existing |= {self.queue_list.item(i).text().strip()
                     for i in range(self.queue_list.count())}

        if url in existing:
            if url in self.failed_queue:
                reply = QMessageBox.question(
                    self, "URL w nieudanych",
                    f"URL już jest w nieudanych.\nPrzenieść do kolejki?\n\n{url}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.failed_queue.remove(url)
                    for i in range(self.queue_list.count()):
                        it = self.queue_list.item(i)
                        if it and it.text().strip() == url:
                            self.queue_list.mark_status(
                                it, self.queue_list.STATUS_NORMAL, self.is_dark_theme()
                            )
                            break
                    if url not in self.download_queue:
                        self.download_queue.append(url)
                    self.save_queue()
                    self.url_input.clear()
            else:
                QMessageBox.information(self, "Duplikat URL", f"URL już w kolejce:\n{url}")
            return

        if not STRICT_URL_REGEX.match(url):
            QMessageBox.warning(self, "Błąd", "Podany URL nie wygląda na poprawny.")
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url

        if "vider.info" in url.lower():
            QMessageBox.warning(
                self, "Uwaga – vider.info",
                "Serwis vider.info nie jest obsługiwany przez yt-dlp.\n\n"
                "Pobieranie z tego serwisu prawdopodobnie się nie powiedzie.\n"
                "URL zostanie dodany do kolejki, ale oczekuj błędu 404."
            )

        self.download_queue.append(url)
        item = QListWidgetItem(url)
        item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
        self.queue_list.addItem(item)
        self.url_input.clear()
        self.save_queue()
        self._start_batch_preview([url])

    def remove_from_queue(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            QMessageBox.warning(self, "Błąd", "Wybierz element do usunięcia.")
            return
        for idx in sorted([self.queue_list.row(it) for it in sel], reverse=True):
            if 0 <= idx < self.queue_list.count():
                text = self.queue_list.item(idx).text().strip()
                if text in self.download_queue:
                    self.download_queue.remove(text)
                self.queue_list.takeItem(idx)
        self.save_queue()

    def move_queue_item_up(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            return
        item = sel[0]; idx = self.queue_list.row(item)
        if idx > 0:
            if idx < len(self.download_queue):
                url = self.download_queue.pop(idx)
                self.download_queue.insert(idx - 1, url)
            self.queue_list.takeItem(idx)
            self.queue_list.insertItem(idx - 1, item)
            self.queue_list.setCurrentItem(item)
            self.save_queue()

    def move_queue_item_down(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            return
        item = sel[0]; idx = self.queue_list.row(item)
        if idx < self.queue_list.count() - 1:
            if idx < len(self.download_queue):
                url = self.download_queue.pop(idx)
                self.download_queue.insert(idx + 1, url)
            self.queue_list.takeItem(idx)
            self.queue_list.insertItem(idx + 1, item)
            self.queue_list.setCurrentItem(item)
            self.save_queue()

    def edit_queue_item(self):
        sel = self.queue_list.selectedItems()
        if not sel:
            QMessageBox.warning(self, "Błąd", "Wybierz element do edycji.")
            return
        item = sel[0]; idx = self.queue_list.row(item)
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Edytuj URL")
        dlg.setLabelText("Wprowadź nowy URL:")
        dlg.setTextValue(item.text())
        dlg.resize(500, dlg.height())
        if dlg.exec():
            new_url = dlg.textValue().strip()
            if new_url and STRICT_URL_REGEX.match(new_url):
                if not new_url.lower().startswith(("http://", "https://")):
                    new_url = "https://" + new_url
                item.setText(new_url)
                if 0 <= idx < len(self.download_queue):
                    self.download_queue[idx] = new_url
                self.save_queue()
                self._start_batch_preview([new_url])
            else:
                QMessageBox.warning(self, "Błąd edycji", "URL nie wygląda na poprawny.")

    def clear_queue(self):
        box = QMessageBox(
            QMessageBox.Icon.Question, "Wyczyść kolejkę",
            "Czy na pewno chcesz wyczyścić kolejkę?", parent=self,
        )
        yes = box.addButton("Tak", QMessageBox.ButtonRole.YesRole)
        no  = box.addButton("Nie", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.exec()
        if box.clickedButton() == yes:
            self.queue_list.clear()
            self.download_queue.clear()
            self.failed_queue.clear()
            self.item_retry_counts.clear()
            self.failed_dialog_shown = False
            self.save_queue()

    def _sync_download_queue_from_widget(self):
        new_order = [self.queue_list.item(i).text().strip()
                     for i in range(self.queue_list.count())
                     if self.queue_list.item(i)]
        self.download_queue = [u for u in new_order if u in self.download_queue or u not in self.failed_queue]
        self.save_queue()

    # =========================================================
    # Zapis / odczyt kolejki
    # =========================================================

    def save_queue(self):
        queue_file = self.appdata_dir / "queue.json"
        try:
            queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(queue_file, "w", encoding="utf-8") as f:
                json.dump({
                    "download_queue": self.download_queue,
                    "failed_queue": self.failed_queue,
                    "retry_counts": self.item_retry_counts,
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Błąd zapisu kolejki: {e}", exc_info=True)

    def load_queue(self) -> bool:
        queue_file = self.appdata_dir / "queue.json"
        if not queue_file.exists():
            return False
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                data = json.loads(content) if content else {}

            if isinstance(data, dict):
                self.download_queue    = [u.strip() for u in data.get("download_queue", []) if u and u.strip()]
                self.failed_queue      = [u.strip() for u in data.get("failed_queue", []) if u and u.strip()]
                self.item_retry_counts = data.get("retry_counts", {})
            elif isinstance(data, list):
                self.download_queue    = [u.strip() for u in data if u and u.strip()]
                self.failed_queue      = []
                self.item_retry_counts = {}
            else:
                self.download_queue, self.failed_queue, self.item_retry_counts = [], [], {}
                return False

            self.queue_list.clear()
            all_urls = list(self.download_queue)
            for u in self.failed_queue:
                if u not in all_urls:
                    all_urls.append(u)

            for url in all_urls:
                item = QListWidgetItem(url)
                if url in self.failed_queue:
                    self.queue_list.mark_status(item, self.queue_list.STATUS_FAILED, self.is_dark_theme())
                else:
                    item.setData(self.queue_list.ROLE_STATUS, self.queue_list.STATUS_NORMAL)
                self.queue_list.addItem(item)

            if all_urls:
                self._start_batch_preview(all_urls)
            return True
        except Exception as e:
            logger.error(f"Błąd wczytywania kolejki: {e}", exc_info=True)
            QMessageBox.warning(self, "Błąd wczytywania", f"Nie udało się wczytać kolejki:\n{e}")
            return False

    def ask_resume_queue(self):
        self.load_queue()
        total = len(self.download_queue) + len(self.failed_queue)
        if total > 0:
            failed_info = f" ({len(self.failed_queue)} nieudanych)" if self.failed_queue else ""
            box = QMessageBox(
                QMessageBox.Icon.Question, "Kontynuuj kolejkę",
                f"Wykryto zapisaną kolejkę ({len(self.download_queue)} normalnych{failed_info}).\n"
                "Czy chcesz kontynuować pobieranie?",
                parent=self,
            )
            yes = box.addButton("Tak", QMessageBox.ButtonRole.YesRole)
            no  = box.addButton("Nie", QMessageBox.ButtonRole.NoRole)
            box.setDefaultButton(yes)
            box.exec()
            if box.clickedButton() == yes:
                if self.download_queue or self.failed_queue:
                    self.start_download(add_current_url=False)
            else:
                self.clear_queue()
