from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from .settings_window import SettingsWindow

class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self):
        super().__init__()
        
        # TODO: Replace with actual icon
        self.setIcon(QIcon.fromTheme("media-record"))
        
        # Create the settings window (but don't show it yet)
        self.settings_window = SettingsWindow()
        
        # Create tray menu
        self.menu = QMenu()
        
        # Add menu items
        self.settings_action = self.menu.addAction("Settings")
        self.settings_action.triggered.connect(self.show_settings)
        
        self.menu.addSeparator()
        
        self.quit_action = self.menu.addAction("Quit")
        self.quit_action.triggered.connect(self.quit_app)
        
        # Set the menu
        self.setContextMenu(self.menu)
        
    def show_settings(self):
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
    
    def quit_app(self):
        from PySide6.QtWidgets import QApplication
        QApplication.quit() 