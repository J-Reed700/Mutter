"""
Theme management for the Mutter application.
Provides consistent, color-scheme-aware styling across the application.
"""

from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import platform
import logging
from typing import Optional

logger = logging.getLogger(__name__)


_LIGHT_COLORS = {
    "PRIMARY": "#0066cc",
    "PRIMARY_LIGHT": "#338be0",
    "PRIMARY_DARK": "#004c99",
    "ACCENT": "#ff3b30",
    "ACCENT_LIGHT": "#ff7066",
    "ACCENT_DARK": "#cc2f26",
    "BACKGROUND": "#f5f5f7",
    "SURFACE": "#ffffff",
    "TEXT_PRIMARY": "#1d1d1f",
    "TEXT_SECONDARY": "#6e6e73",
    "TEXT_DISABLED": "#a0a0a5",
    "BORDER": "#d1d1d6",
    "CONTROL_BG": "#e8e8ed",
    "CONTROL_HOVER": "#dcdce1",
    "CONTROL_PRESSED": "#cfcfd4",
    "DISABLED_BG": "#ececf0",
}

_DARK_COLORS = {
    "PRIMARY": "#2f81f7",
    "PRIMARY_LIGHT": "#4d94ff",
    "PRIMARY_DARK": "#1f6feb",
    "ACCENT": "#ff453a",
    "ACCENT_LIGHT": "#ff7066",
    "ACCENT_DARK": "#cc2f26",
    "BACKGROUND": "#1e1e20",
    "SURFACE": "#2a2a2e",
    "TEXT_PRIMARY": "#e8e8ea",
    "TEXT_SECONDARY": "#a0a0a8",
    "TEXT_DISABLED": "#6a6a72",
    "BORDER": "#3f3f46",
    "CONTROL_BG": "#3a3a40",
    "CONTROL_HOVER": "#46464e",
    "CONTROL_PRESSED": "#52525a",
    "DISABLED_BG": "#2f2f34",
}


class AppTheme:
    """Provides theme constants and utilities for the application.

    Color attributes (PRIMARY, SURFACE, ...) are set for the active color
    scheme when apply() runs; they default to the light scheme so they are
    always usable.
    """

    DARK_MODE = False

    # Font sizes
    FONT_SIZE_SMALL = 9
    FONT_SIZE_NORMAL = 10
    FONT_SIZE_LARGE = 12
    FONT_SIZE_TITLE = 14

    _scheme_watch_connected = False

    @classmethod
    def _activate_colors(cls, dark: bool):
        """Load the light or dark color set onto the class attributes."""
        cls.DARK_MODE = dark
        for name, value in (_DARK_COLORS if dark else _LIGHT_COLORS).items():
            setattr(cls, name, value)

    @staticmethod
    def _system_prefers_dark(app: QApplication) -> bool:
        """Detect the OS color scheme (best effort)."""
        try:
            return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            return False

    @classmethod
    def apply(cls, app: QApplication, dark: Optional[bool] = None):
        """Apply the theme to the application.

        Args:
            app: The QApplication instance
            dark: Force dark (True) or light (False) mode; None follows the OS
        """
        if dark is None:
            dark = cls._system_prefers_dark(app)
        cls._activate_colors(dark)

        # Fusion renders identically on every platform and respects our
        # palette fully — half-native styling is what causes unreadable
        # light-on-light / dark-on-dark mixes.
        app.setStyle("Fusion")
        app.setPalette(cls._build_palette())

        # Set default font (leave macOS on the system default)
        default_font = QFont()
        if platform.system() == "Windows":
            default_font.setFamily("Segoe UI")
        elif platform.system() == "Linux":
            default_font.setFamily("Roboto")
        default_font.setPointSize(cls.FONT_SIZE_NORMAL)
        app.setFont(default_font)

        app.setStyleSheet(cls.get_stylesheet())

        # Re-apply automatically when the OS switches between light and dark
        if not cls._scheme_watch_connected:
            try:
                app.styleHints().colorSchemeChanged.connect(lambda *_: cls.apply(app))
                cls._scheme_watch_connected = True
            except Exception:
                pass

        logger.debug(f"Applied {'dark' if dark else 'light'} theme for {platform.system()}")

    @classmethod
    def _build_palette(cls) -> QPalette:
        palette = QPalette()

        palette.setColor(QPalette.Window, QColor(cls.BACKGROUND))
        palette.setColor(QPalette.WindowText, QColor(cls.TEXT_PRIMARY))
        palette.setColor(QPalette.Base, QColor(cls.SURFACE))
        palette.setColor(QPalette.AlternateBase, QColor(cls.BACKGROUND))
        palette.setColor(QPalette.ToolTipBase, QColor(cls.SURFACE))
        palette.setColor(QPalette.ToolTipText, QColor(cls.TEXT_PRIMARY))

        palette.setColor(QPalette.Button, QColor(cls.CONTROL_BG))
        palette.setColor(QPalette.ButtonText, QColor(cls.TEXT_PRIMARY))

        palette.setColor(QPalette.Link, QColor(cls.PRIMARY))
        palette.setColor(QPalette.LinkVisited, QColor(cls.PRIMARY_DARK))

        palette.setColor(QPalette.Text, QColor(cls.TEXT_PRIMARY))
        palette.setColor(QPalette.PlaceholderText, QColor(cls.TEXT_DISABLED))
        palette.setColor(QPalette.BrightText, Qt.white)

        palette.setColor(QPalette.Highlight, QColor(cls.PRIMARY))
        palette.setColor(QPalette.HighlightedText, Qt.white)

        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, QColor(cls.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.Base, QColor(cls.DISABLED_BG))
        palette.setColor(QPalette.Disabled, QPalette.Button, QColor(cls.DISABLED_BG))

        return palette

    @classmethod
    def get_stylesheet(cls) -> str:
        """Get the application's stylesheet for the active color scheme."""
        return f"""
            /* General */
            QWidget {{
                color: {cls.TEXT_PRIMARY};
                font-size: {cls.FONT_SIZE_NORMAL}pt;
            }}

            /* Buttons — primary by default */
            QPushButton {{
                background-color: {cls.PRIMARY};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }}

            QPushButton:hover {{
                background-color: {cls.PRIMARY_LIGHT};
            }}

            QPushButton:pressed {{
                background-color: {cls.PRIMARY_DARK};
            }}

            QPushButton:disabled {{
                background-color: {cls.DISABLED_BG};
                color: {cls.TEXT_DISABLED};
            }}

            /* Quiet secondary buttons for minor utility actions */
            QPushButton[buttonStyle="secondary"] {{
                background-color: {cls.CONTROL_BG};
                color: {cls.TEXT_PRIMARY};
                font-weight: normal;
                padding: 5px 14px;
            }}

            QPushButton[buttonStyle="secondary"]:hover {{
                background-color: {cls.CONTROL_HOVER};
            }}

            QPushButton[buttonStyle="secondary"]:pressed {{
                background-color: {cls.CONTROL_PRESSED};
            }}

            QPushButton[buttonStyle="secondary"]:disabled {{
                background-color: {cls.DISABLED_BG};
                color: {cls.TEXT_DISABLED};
            }}

            /* Small secondary-color help text */
            QLabel[labelStyle="hint"] {{
                color: {cls.TEXT_SECONDARY};
                font-size: 12px;
            }}

            /* Menus */
            QMenu {{
                background-color: {cls.SURFACE};
                border: 1px solid {cls.BORDER};
            }}

            QMenu::item {{
                padding: 6px 20px;
            }}

            QMenu::item:selected {{
                background-color: {cls.PRIMARY};
                color: white;
            }}

            /* Input controls */
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QKeySequenceEdit {{
                border: 1px solid {cls.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                background-color: {cls.SURFACE};
                selection-background-color: {cls.PRIMARY};
                selection-color: white;
            }}

            QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
                background-color: {cls.DISABLED_BG};
                color: {cls.TEXT_DISABLED};
            }}

            QComboBox QAbstractItemView {{
                background-color: {cls.SURFACE};
                border: 1px solid {cls.BORDER};
                selection-background-color: {cls.PRIMARY};
                selection-color: white;
            }}

            /* Tabs */
            QTabWidget::pane {{
                border: 1px solid {cls.BORDER};
                border-radius: 4px;
                background-color: {cls.SURFACE};
            }}

            QTabBar::tab {{
                background-color: {cls.CONTROL_BG};
                border: 1px solid {cls.BORDER};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 16px;
                margin-right: 2px;
            }}

            QTabBar::tab:selected {{
                background-color: {cls.SURFACE};
                border-bottom: none;
            }}

            /* Group boxes */
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {cls.BORDER};
                border-radius: 4px;
                margin-top: 1.4em;
                padding-top: 0.9em;
                background-color: {cls.SURFACE};
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}

            QGroupBox:disabled {{
                color: {cls.TEXT_DISABLED};
            }}

            /* Dialogs */
            QMessageBox, QProgressDialog {{
                background-color: {cls.BACKGROUND};
            }}
        """


# Ensure color attributes exist even if apply() was never called
AppTheme._activate_colors(False)
