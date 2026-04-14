# -*- coding: utf-8 -*-
"""Mixin: motyw wizualny (Dark / White)."""

from ..ui.styles import (
    build_dark_palette,
    build_dark_stylesheet,
    build_white_palette,
    build_white_stylesheet,
)


class ThemeMixin:
    def is_dark_theme(self) -> bool:
        return self.settings.value("theme", "Dark", type=str) == "Dark"

    def apply_style(self):
        if self.is_dark_theme():
            self.apply_dark_style()
        else:
            self.apply_white_style()

    def apply_dark_style(self):
        palette = build_dark_palette()
        self.setPalette(palette)
        self.setStyleSheet(build_dark_stylesheet(palette))

    def apply_white_style(self):
        palette = build_white_palette()
        self.setPalette(palette)
        self.setStyleSheet(build_white_stylesheet(palette))

    def change_theme(self, _index):
        theme = self.theme_combo.currentText()
        self.settings.setValue("theme", theme)
        self.apply_style()
        for i in range(self.queue_list.count()):
            it = self.queue_list.item(i)
            st = it.data(self.queue_list.ROLE_STATUS) or self.queue_list.STATUS_NORMAL
            self.queue_list.mark_status(it, st, self.is_dark_theme())
