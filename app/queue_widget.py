# -*- coding: utf-8 -*-
"""
Niestandardowy widget listy kolejki pobierania.

Obsługuje:
  - drag & drop (wewnętrzne porządkowanie i zewnętrzne URL-e)
  - menu kontekstowe
  - kolorowanie statusu elementów (normalny / ponowienie / błąd)
"""

import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QMenu,
)

from .config import STRICT_URL_REGEX, URL_SIMPLE_REGEX


class QueueListWidget(QListWidget):
    dropped_reordered     = pyqtSignal()
    dropped_external_urls = pyqtSignal(list)

    ROLE_STATUS    = Qt.ItemDataRole.UserRole + 1
    STATUS_NORMAL  = "normal"
    STATUS_RETRYING = "retrying"
    STATUS_FAILED  = "failed"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)
        self.setIconSize(QSize(64, 36))

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def dropEvent(self, event):
        if event.source() is self and event.dropAction() == Qt.DropAction.MoveAction:
            super().dropEvent(event)
            self.dropped_reordered.emit()
            return
        if event.mimeData().hasText():
            urls = self._extract_urls(event.mimeData().text())
            if urls:
                self.dropped_external_urls.emit(urls)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def _extract_urls(self, text: str) -> list:
        if not text:
            return []
        urls = []
        for m in URL_SIMPLE_REGEX.finditer(text):
            u = m.group(0).strip()
            if not u:
                continue
            if not u.lower().startswith(("http://", "https://")):
                u = "https://" + u
            if STRICT_URL_REGEX.match(u):
                urls.append(u)
        return urls

    # ------------------------------------------------------------------
    # Menu kontekstowe
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event):
        pass  # obsługa przez signal

    def _open_context_menu(self, pos):
        menu = QMenu(self)
        act_preview      = QAction("Pokaż podgląd", self)
        act_edit         = QAction("Edytuj", self)
        act_copy         = QAction("Kopiuj URL", self)
        act_open         = QAction("Otwórz w przeglądarce", self)
        act_remove       = QAction("Usuń", self)
        act_clear_failed = QAction("Usuń oznaczone jako nieudane", self)

        act_preview.triggered.connect(self._action_preview)
        act_edit.triggered.connect(self._action_edit)
        act_copy.triggered.connect(self._action_copy)
        act_open.triggered.connect(self._action_open)
        act_remove.triggered.connect(self._action_remove)
        act_clear_failed.triggered.connect(self._action_clear_failed)

        if not self.selectedItems():
            for a in (act_preview, act_edit, act_copy, act_open, act_remove):
                a.setEnabled(False)

        menu.addAction(act_preview)
        menu.addSeparator()
        menu.addAction(act_edit)
        menu.addAction(act_copy)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_remove)
        menu.addAction(act_clear_failed)
        menu.exec(self.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Akcje menu
    # ------------------------------------------------------------------

    def _owner(self):
        return self.window()

    def _action_preview(self):
        if not self.selectedItems():
            return
        owner = self._owner()
        if hasattr(owner, "preview_selected_from_queue"):
            owner.preview_selected_from_queue()

    def _action_edit(self):
        if not self.selectedItems():
            return
        owner = self._owner()
        if hasattr(owner, "edit_queue_item"):
            owner.edit_queue_item()

    def _action_copy(self):
        items = self.selectedItems()
        if items:
            QApplication.clipboard().setText("\n".join(i.text() for i in items))

    def _action_open(self):
        for it in self.selectedItems():
            webbrowser.open(it.text())

    def _action_remove(self):
        if not self.selectedItems():
            return
        owner = self._owner()
        if hasattr(owner, "remove_from_queue"):
            owner.remove_from_queue()

    def _action_clear_failed(self):
        owner = self._owner()
        to_remove = []
        for i in range(self.count()):
            item = self.item(i)
            if item and item.data(self.ROLE_STATUS) == self.STATUS_FAILED:
                to_remove.append((i, item.text()))
        for idx, url in reversed(to_remove):
            self.takeItem(idx)
            if hasattr(owner, "download_queue") and url in owner.download_queue:
                owner.download_queue.remove(url)
        if hasattr(owner, "failed_queue"):
            owner.failed_queue = []
        if hasattr(owner, "save_queue"):
            owner.save_queue()

    # ------------------------------------------------------------------
    # Kolorowanie statusu
    # ------------------------------------------------------------------

    def mark_status(self, item: QListWidgetItem, status: str, is_dark: bool):
        item.setData(self.ROLE_STATUS, status)
        if status == self.STATUS_FAILED:
            if is_dark:
                item.setBackground(QColor(120, 50, 50))
                item.setForeground(QColor(255, 200, 200))
            else:
                item.setBackground(QColor(255, 200, 200))
                item.setForeground(QColor(150, 0, 0))
        elif status == self.STATUS_RETRYING:
            if is_dark:
                item.setBackground(QColor(120, 80, 30))
                item.setForeground(QColor(255, 230, 200))
            else:
                item.setBackground(QColor(255, 230, 200))
                item.setForeground(QColor(120, 60, 0))
        else:
            item.setBackground(QColor())
            item.setForeground(QColor())

    def is_failed_item(self, item: QListWidgetItem) -> bool:
        return item.data(self.ROLE_STATUS) == self.STATUS_FAILED

    def is_retry_item(self, item: QListWidgetItem) -> bool:
        return item.data(self.ROLE_STATUS) == self.STATUS_RETRYING
