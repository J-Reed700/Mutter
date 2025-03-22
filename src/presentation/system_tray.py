from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QWidget
from PySide6.QtGui import QIcon, QAction, QFont, QClipboard, QPixmap, QPainter, QColor
from PySide6.QtCore import Slot, QSize, Qt
from PySide6.QtWidgets import QApplication
from pathlib import Path
import logging
import platform

logger = logging.getLogger(__name__)

class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        
        # Set the tray icon with appropriate resolution based on platform
        if platform.system() == 'Windows':
            icon_size = 16  # Windows usually uses 16x16 icons in system tray
        else:
            icon_size = 32  # macOS and others use larger icons
            
        # Set the tray icon - either load from file or create in memory
        self._default_icon = self._create_default_icon()
        self.setIcon(self._default_icon)
        
        # Set recording icon - we'll create it in memory for consistency
        self.recording_icon = self._create_recording_icon()
        
        # Create the tray menu with styled font
        self.menu = QMenu()
        font = QFont()
        font.setPointSize(10)
        self.menu.setFont(font)
        
        # Add status indicator action (disabled, just for display)
        self.status_action = QAction("Ready")
        self.status_action.setEnabled(False)
        bold_font = QFont()
        bold_font.setPointSize(10)
        bold_font.setBold(True)
        self.status_action.setFont(bold_font)
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()
        
        # Add recent transcription action with better styling
        self.recent_transcription_action = QAction("No recent transcriptions")
        self.recent_transcription_action.setEnabled(False)
        italic_font = QFont()
        italic_font.setPointSize(9)
        italic_font.setItalic(True)
        self.recent_transcription_action.setFont(italic_font)
        self.menu.addAction(self.recent_transcription_action)
        
        # Add copy to clipboard action with icon
        self.copy_action = QAction("Copy to Clipboard")
        self.copy_action.setEnabled(False)
        self.copy_action.triggered.connect(self.copy_to_clipboard)
        # Add clipboard icon if available
        clipboard_icon = QIcon.fromTheme("edit-copy")
        if not clipboard_icon.isNull():
            self.copy_action.setIcon(clipboard_icon)
        self.menu.addAction(self.copy_action)
        
        self.menu.addSeparator()
        
        # Add settings action with icon
        self.settings_action = QAction("Settings")
        self.settings_action.triggered.connect(self.show_settings)
        # Add settings icon if available
        settings_icon = QIcon.fromTheme("preferences-system")
        if not settings_icon.isNull():
            self.settings_action.setIcon(settings_icon)
        self.menu.addAction(self.settings_action)
        
        # Add quit action with icon
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.quit_application)
        # Add quit icon if available
        quit_icon = QIcon.fromTheme("application-exit")
        if not quit_icon.isNull():
            quit_action.setIcon(quit_icon)
        self.menu.addAction(quit_action)
        
        # Set the menu
        self.setContextMenu(self.menu)
        
        # Set tooltip
        self.setToolTip("Voice Recorder\nReady")
        
        # Store the last transcription
        self.last_transcription = ""
        
        # Connect activation signal for double-click
        self.activated.connect(self.on_activated)

    def _find_icon(self, preferred_name, fallback_name):
        """Find an icon file in the resources directory
        
        Args:
            preferred_name: Preferred filename to look for
            fallback_name: Fallback filename if preferred isn't found
            
        Returns:
            Path to the icon file
        """
        # Look in resources/images
        paths = [
            Path(__file__).parent.parent.parent / "resources" / "images" / preferred_name,
            Path(__file__).parent.parent.parent / "resources" / "images" / fallback_name,
            # Fallbacks
            Path(__file__).parent.parent.parent / "resources" / fallback_name,
            Path(__file__).parent / "resources" / fallback_name
        ]
        
        for path in paths:
            if path.exists():
                return path
                
        # Return the last path anyway, even if it doesn't exist
        logger.debug(f"Could not find icon: {preferred_name} or {fallback_name}")
        return paths[0]

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.last_transcription:
                self.copy_to_clipboard()
                self.showMessage(
                    "Copied to Clipboard",
                    "The transcription has been copied to your clipboard.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )

    @Slot()
    def on_recording_started(self):
        """Handle recording started signal"""
        self.status_action.setText("● Recording...")
        self.setToolTip("Voice Recorder\nRecording in progress")
        
        # Change icon to recording icon if it exists
        self.setIcon(self.recording_icon)
        
        # Show notification - but fewer and shorter
        self.showMessage(
            "Recording",
            "Started",
            QSystemTrayIcon.MessageIcon.Information,
            1000  # Show for 1 second only
        )

    @Slot(Path)
    def on_recording_stopped(self, file_path: Path):
        """Handle recording stopped signal"""
        self.status_action.setText("Ready")
        self.setToolTip("Voice Recorder\nReady")
        
        # Restore original icon
        if hasattr(self, '_default_icon'):
            self.setIcon(self._default_icon)
        else:
            icon_path = self._find_icon(f"microphone_{16 if platform.system() == 'Windows' else 32}.png", "microphone.png")
            if icon_path.exists():
                self.setIcon(QIcon(str(icon_path)))
            else:
                self.setIcon(self._create_default_icon())
        
        # Don't show notification for stopping - will show transcription notification later
        # Remove this notification entirely

    @Slot(str)
    def on_recording_failed(self, error_message: str):
        """Handle recording failed signal"""
        self.status_action.setText("Ready")
        self.setToolTip("Voice Recorder\nReady")
        
        # Restore original icon
        icon_path = self._find_icon(f"microphone_{16 if platform.system() == 'Windows' else 32}.png", "microphone.png")
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            self.setIcon(self._create_default_icon())
        
        # Show error notification
        self.showMessage(
            "Voice Recorder - Error",
            f"Recording failed:\n{error_message}",
            QSystemTrayIcon.MessageIcon.Critical,
            5000  # Show for 5 seconds
        )

    @Slot(str)
    def on_transcription_complete(self, text: str):
        """Handle transcription completion"""
        self.status_action.setText("Ready")
        self.setToolTip("Voice Recorder\nReady")
        
        # Store the transcription
        self.last_transcription = text
        
        # Update menu items
        preview = text[:50] + "..." if len(text) > 50 else text
        self.recent_transcription_action.setText(preview)
        self.recent_transcription_action.setEnabled(True)
        self.copy_action.setEnabled(True)
        
        # Automatically copy to clipboard
        self.copy_to_clipboard()
        
        # Show notification with transcribed text, but shorter
        preview_for_notification = text[:75] + "..." if len(text) > 75 else text
        self.showMessage(
            "Transcription Complete",
            f"{preview_for_notification}\n\nCopied to clipboard",
            QSystemTrayIcon.MessageIcon.Information,
            3000  # Show for 3 seconds
        )

    def copy_to_clipboard(self):
        """Copy the last transcription to clipboard"""
        if not self.last_transcription:
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_transcription)
        logger.debug("Copied transcription to clipboard")

    def show_settings(self):
        """Show the settings window"""
        # This is connected externally
        pass

    def quit_application(self):
        """Quit the application"""
        QApplication.quit()

    def _create_default_icon(self) -> QIcon:
        """Create a modern microphone icon if the file is not found"""
        sizes = [16, 24, 32, 48, 64, 128]
        icon = QIcon()
        
        for size in sizes:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw a blue circle
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 102, 204))  # #0066cc - Primary blue
            painter.drawEllipse(2, 2, size-4, size-4)
            
            # Calculate microphone dimensions
            mic_width = size // 3
            mic_height = size // 2
            mic_x = (size - mic_width) // 2
            mic_y = size // 5
            
            # Draw a microphone body (white rounded rectangle)
            painter.setBrush(QColor(255, 255, 255))  # White
            painter.drawRoundedRect(mic_x, mic_y, mic_width, mic_height, mic_width//3, mic_width//3)
            
            # Draw a microphone stand
            stand_width = size // 10
            stand_height = size // 4
            stand_x = size // 2 - stand_width // 2
            stand_y = mic_y + mic_height
            
            painter.drawRect(stand_x, stand_y, stand_width, stand_height)
            
            # Draw a stand base
            base_width = size // 2
            base_height = size // 16
            base_x = size // 2 - base_width // 2
            base_y = stand_y + stand_height
            
            painter.drawRoundedRect(base_x, base_y, base_width, base_height, base_height//2, base_height//2)
            
            painter.end()
            icon.addPixmap(pixmap)
            
        return icon
    
    def _create_recording_icon(self) -> QIcon:
        """Create a modern recording icon with red indicator"""
        sizes = [16, 24, 32, 48, 64, 128]
        icon = QIcon()
        
        for size in sizes:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw a blue circle
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 102, 204))  # #0066cc - Primary blue
            painter.drawEllipse(2, 2, size-4, size-4)
            
            # Calculate microphone dimensions
            mic_width = size // 3
            mic_height = size // 2
            mic_x = (size - mic_width) // 2
            mic_y = size // 5
            
            # Draw a microphone body (white rounded rectangle)
            painter.setBrush(QColor(255, 255, 255))  # White
            painter.drawRoundedRect(mic_x, mic_y, mic_width, mic_height, mic_width//3, mic_width//3)
            
            # Draw a microphone stand
            stand_width = size // 10
            stand_height = size // 4
            stand_x = size // 2 - stand_width // 2
            stand_y = mic_y + mic_height
            
            painter.drawRect(stand_x, stand_y, stand_width, stand_height)
            
            # Draw a stand base
            base_width = size // 2
            base_height = size // 16
            base_x = size // 2 - base_width // 2
            base_y = stand_y + stand_height
            
            painter.drawRoundedRect(base_x, base_y, base_width, base_height, base_height//2, base_height//2)
            
            # Draw a red recording indicator
            indicator_size = max(size // 4, 4)  # Ensure it's at least 4px
            indicator_x = size - indicator_size - 2
            indicator_y = 2
            
            painter.setBrush(QColor(255, 59, 48))  # #ff3b30 - iOS-style red
            painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
            
            painter.end()
            icon.addPixmap(pixmap)
            
        return icon 