"""
Theme management for the Memo application.
Provides consistent styling across the application.
"""

from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import platform
import logging

logger = logging.getLogger(__name__)

class AppTheme:
    """Provides theme constants and utilities for the application."""
    
    # Primary colors
    PRIMARY = "#0066cc"  # Blue
    PRIMARY_LIGHT = "#4d94ff"
    PRIMARY_DARK = "#004c99"
    
    # Accent colors
    ACCENT = "#ff3b30"  # Red (for recording)
    ACCENT_LIGHT = "#ff7066"
    ACCENT_DARK = "#cc2f26"
    
    # Neutral colors
    BACKGROUND = "#f5f5f7"
    SURFACE = "#ffffff"
    TEXT_PRIMARY = "#111111"
    TEXT_SECONDARY = "#666666"
    TEXT_DISABLED = "#999999"
    
    # Font sizes
    FONT_SIZE_SMALL = 9
    FONT_SIZE_NORMAL = 10
    FONT_SIZE_LARGE = 12
    FONT_SIZE_TITLE = 14
    
    @staticmethod
    def apply(app: QApplication):
        """Apply the theme to the application.
        
        Args:
            app: The QApplication instance
        """
        is_windows = platform.system() == "Windows"
        is_mac = platform.system() == "Darwin"
        
        # Set application style
        if is_windows:
            app.setStyle("Fusion")  # Fusion style works well across platforms
        
        # Set up the palette
        palette = QPalette()
        
        # Basic colors
        palette.setColor(QPalette.Window, QColor(AppTheme.BACKGROUND))
        palette.setColor(QPalette.WindowText, QColor(AppTheme.TEXT_PRIMARY))
        palette.setColor(QPalette.Base, QColor(AppTheme.SURFACE))
        palette.setColor(QPalette.AlternateBase, QColor(AppTheme.BACKGROUND))
        palette.setColor(QPalette.ToolTipBase, QColor(AppTheme.SURFACE))
        palette.setColor(QPalette.ToolTipText, QColor(AppTheme.TEXT_PRIMARY))
        
        # Buttons
        palette.setColor(QPalette.Button, QColor(AppTheme.PRIMARY))
        palette.setColor(QPalette.ButtonText, Qt.white)
        
        # Links
        palette.setColor(QPalette.Link, QColor(AppTheme.PRIMARY))
        palette.setColor(QPalette.LinkVisited, QColor(AppTheme.PRIMARY_DARK))
        
        # Text colors
        palette.setColor(QPalette.Text, QColor(AppTheme.TEXT_PRIMARY))
        palette.setColor(QPalette.BrightText, Qt.white)
        
        # Highlights
        palette.setColor(QPalette.Highlight, QColor(AppTheme.PRIMARY))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        
        # Disabled elements
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(AppTheme.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(AppTheme.TEXT_DISABLED))
        
        # Apply the palette if not on Mac (macOS handles this better natively)
        if not is_mac:
            app.setPalette(palette)
        
        # Set default font
        default_font = QFont()
        if is_windows:
            default_font.setFamily("Segoe UI")
            default_font.setPointSize(AppTheme.FONT_SIZE_NORMAL)
        elif is_mac:
            default_font.setFamily("SF Pro Text")
            default_font.setPointSize(AppTheme.FONT_SIZE_NORMAL)
        else:  # Linux and others
            default_font.setFamily("Roboto")
            default_font.setPointSize(AppTheme.FONT_SIZE_NORMAL)
        
        app.setFont(default_font)
        
        # Apply stylesheet
        app.setStyleSheet(AppTheme.get_stylesheet())
        
        logger.debug(f"Applied theme for {platform.system()}")

    @staticmethod
    def get_stylesheet() -> str:
        """Get the application's stylesheet.
        
        Returns:
            str: The CSS stylesheet
        """
        return f"""
            /* General */
            QWidget {{
                color: {AppTheme.TEXT_PRIMARY};
                font-size: {AppTheme.FONT_SIZE_NORMAL}pt;
            }}
            
            /* Buttons */
            QPushButton {{
                background-color: {AppTheme.PRIMARY};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            
            QPushButton:hover {{
                background-color: {AppTheme.PRIMARY_LIGHT};
            }}
            
            QPushButton:pressed {{
                background-color: {AppTheme.PRIMARY_DARK};
            }}
            
            QPushButton:disabled {{
                background-color: #cccccc;
                color: {AppTheme.TEXT_DISABLED};
            }}
            
            /* Menus and toolbars */
            QMenu {{
                background-color: {AppTheme.SURFACE};
                border: 1px solid #d1d1d6;
            }}
            
            QMenu::item {{
                padding: 6px 20px;
            }}
            
            QMenu::item:selected {{
                background-color: {AppTheme.PRIMARY};
                color: white;
            }}
            
            /* Input controls */
            QLineEdit, QTextEdit, QComboBox, QSpinBox {{
                border: 1px solid #d1d1d6;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: {AppTheme.SURFACE};
                selection-background-color: {AppTheme.PRIMARY_LIGHT};
            }}
            
            /* Tabs */
            QTabWidget::pane {{
                border: 1px solid #d1d1d6;
                border-radius: 4px;
                background-color: {AppTheme.SURFACE};
            }}
            
            QTabBar::tab {{
                background-color: #e4e4e9;
                border: 1px solid #d1d1d6;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 16px;
                margin-right: 2px;
            }}
            
            QTabBar::tab:selected {{
                background-color: {AppTheme.SURFACE};
                border-bottom: none;
            }}
            
            /* Group boxes */
            QGroupBox {{
                font-weight: bold;
                border: 1px solid #d1d1d6;
                border-radius: 4px;
                margin-top: 1em;
                padding-top: 0.5em;
                background-color: {AppTheme.SURFACE};
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """ 