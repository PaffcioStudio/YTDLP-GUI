# -*- coding: utf-8 -*-
"""
Motywy wizualne aplikacji: Dark i White.
"""

from PyQt6.QtGui import QColor, QPalette


def build_dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(30, 31, 33))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(230, 230, 230))
    palette.setColor(QPalette.ColorRole.Base,            QColor(44, 45, 48))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(40, 41, 44))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(60, 60, 62))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Text,            QColor(230, 230, 230))
    palette.setColor(QPalette.ColorRole.Button,          QColor(60, 62, 65))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(225, 225, 225))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(255, 165, 0))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(160, 160, 160))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(140, 140, 140))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(140, 140, 140))
    return palette


def build_dark_stylesheet(palette: QPalette) -> str:
    accent = QColor(255, 165, 0)
    base   = palette.color(QPalette.ColorRole.Base).name()
    win    = palette.color(QPalette.ColorRole.Window).name()
    text   = palette.color(QPalette.ColorRole.Text).name()
    btn    = palette.color(QPalette.ColorRole.Button)
    btnT   = palette.color(QPalette.ColorRole.ButtonText).name()
    acc    = accent.name()
    accD   = accent.darker(130).name()
    accL   = accent.lighter(120).name()
    btnD   = btn.darker(140).name()
    btnL   = btn.lighter(120).name()
    btnLL  = btn.lighter(145).name()
    btnD2  = btn.darker(150).name()
    return f"""
        QMainWindow, QWidget {{
            background-color: {win}; color: {text};
        }}
        QMenu {{
            background-color: {base}; color: {text};
            border: 1px solid {btn.darker(120).name()};
        }}
        QMenu::item:selected {{ background-color: {acc}; color: #000; }}
        QTabWidget::pane {{
            border: 1px solid {btnD}; background-color: {win};
        }}
        QTabBar::tab {{
            background: {btn.name()}; color: {btnT};
            border: 1px solid {btnD};
            border-top-left-radius: 6px; border-top-right-radius: 6px;
            padding: 7px 12px; margin-right: 3px;
        }}
        QTabBar::tab:selected {{ background: {base}; border-color: {btnD2}; }}
        QGroupBox {{
            border: 1px solid {btnD}; border-radius: 8px;
            margin-top: 10px; padding-top: 10px;
        }}
        QGroupBox::title {{
            left: 10px; padding: 0 5px; color: {acc}; font-weight: bold;
        }}
        QLineEdit, QTextEdit, QComboBox, QListWidget, QSpinBox {{
            background-color: {base}; color: {text};
            border: 1px solid {btnD2}; border-radius: 6px; padding: 6px;
            selection-background-color: {acc}; selection-color: #000;
        }}
        QComboBox QAbstractItemView {{
            background-color: {base}; color: {text};
            selection-background-color: {acc}; selection-color: #000;
            border: 1px solid {btnD};
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {acc};
        }}
        QPushButton {{
            background-color: {btnL}; color: {btnT};
            border: 1px solid {btnD2}; padding: 7px 14px;
            border-radius: 6px; font-weight: bold;
        }}
        QPushButton#downloadButton, QPushButton#pasteAndAddButton {{
            background-color: {acc}; color: #000000;
            border: 1px solid {accD};
        }}
        QPushButton:hover {{ background-color: {btnLL}; }}
        QPushButton#downloadButton:hover, QPushButton#pasteAndAddButton:hover {{
            background-color: {accL};
        }}
        QProgressBar {{
            border: 1px solid {btnD2}; border-radius: 6px; text-align: center;
            background-color: {base}; color: {text}; height: 20px;
        }}
        QProgressBar::chunk {{ background-color: {acc}; border-radius: 6px; }}
    """


def build_white_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(245, 246, 248))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Base,            QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(238, 239, 241))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(255, 255, 220))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(50, 50, 50))
    palette.setColor(QPalette.ColorRole.Text,            QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Button,          QColor(235, 236, 238))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(0, 120, 215))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(120, 120, 120))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(140, 140, 140))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(140, 140, 140))
    return palette


def build_white_stylesheet(palette: QPalette) -> str:
    accent = QColor(0, 120, 215)
    base   = palette.color(QPalette.ColorRole.Base).name()
    win    = palette.color(QPalette.ColorRole.Window).name()
    text   = palette.color(QPalette.ColorRole.Text).name()
    btn    = palette.color(QPalette.ColorRole.Button).name()
    btnT   = palette.color(QPalette.ColorRole.ButtonText).name()
    hl     = palette.color(QPalette.ColorRole.Highlight).name()
    hlT    = palette.color(QPalette.ColorRole.HighlightedText).name()
    acc    = accent.name()
    accD   = accent.darker(120).name()
    return f"""
        QMainWindow, QWidget {{ background-color: {win}; color: {text}; }}
        QTabWidget::pane {{ border: 1px solid #DCDCDC; background-color: {win}; }}
        QTabBar::tab {{
            background: {btn}; color: {btnT};
            border: 1px solid #DCDCDC;
            border-top-left-radius: 6px; border-top-right-radius: 6px;
            padding: 7px 12px; margin-right: 3px;
        }}
        QTabBar::tab:selected {{ background: {base}; border-bottom-color: {base}; }}
        QGroupBox {{
            background-color: {base}; border: 1px solid #DCDCDC;
            border-radius: 8px; margin-top: 10px; padding-top: 10px;
        }}
        QGroupBox::title {{
            left: 10px; padding: 0 5px; color: {accD}; font-weight: bold;
            background-color: {base};
        }}
        QLineEdit, QTextEdit, QComboBox, QListWidget, QSpinBox {{
            background-color: {base}; color: {text};
            border: 1px solid #CCCCCC; border-radius: 6px; padding: 6px;
            selection-background-color: {hl}; selection-color: {hlT};
        }}
        QComboBox QAbstractItemView {{
            background-color: {base}; color: {text};
            selection-background-color: {hl}; selection-color: {hlT};
            border: 1px solid #CCCCCC;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {acc};
        }}
        QPushButton {{
            background-color: {btn}; color: {btnT};
            border: 1px solid #BBBBBB; padding: 7px 14px;
            border-radius: 6px; font-weight: bold;
        }}
        QPushButton#downloadButton, QPushButton#pasteAndAddButton {{
            background-color: {acc}; color: #FFFFFF;
            border: 1px solid {accD};
        }}
        QPushButton:hover {{ background-color: #D5D6D8; }}
        QProgressBar {{
            border: 1px solid #BBBBBB; border-radius: 6px; text-align: center;
            background-color: {base}; color: {text}; height: 20px;
        }}
        QProgressBar::chunk {{ background-color: {acc}; border-radius: 6px; }}
    """
