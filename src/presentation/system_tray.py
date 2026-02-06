from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QWidget
from PySide6.QtGui import QIcon, QAction, QFont, QClipboard, QPixmap, QPainter, QColor
from PySide6.QtCore import Slot, QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
import src.presentation.system_extensions.windows as windows
import src.presentation.system_extensions.macos as macos
import src.presentation.system_extensions.linux as linux
from pathlib import Path
from .toast.custom_toast import CustomToast
import logging
import platform
import os

from .windows.settings import SettingsWindow

logger = logging.getLogger(__name__)

class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        
        # Set up Linux-specific configuration
        if platform.system() == 'Linux':
            try:
                # Force use of XCB platform
                os.environ['QT_QPA_PLATFORM'] = 'xcb'
                # Disable D-Bus usage for system tray
                os.environ['QT_NO_DBUS'] = '1'
                # Set up fallback icon theme path
                QIcon.setThemeName('Adwaita')
                QIcon.setThemeSearchPaths(['/usr/share/icons'])
                # Additional Fedora-specific paths
                QIcon.setThemeSearchPaths([
                    '/usr/share/icons',
                    '/usr/share/icons/hicolor',
                    '/usr/share/icons/Adwaita',
                    '/usr/share/icons/gnome'
                ])
                # Set a custom property to mark this as initialized
                self.setProperty("initialized", True)
                logger.debug("Linux-specific configuration applied")
            except Exception as e:
                logger.warning(f"Failed to set up Linux configuration: {e}")
                raise e

        # Settings for notifications (defaults)
        self.show_notifications = False
        self.auto_paste = True  # Enable auto-paste by default
        
        # Create custom toast
        self.toast = CustomToast()
        
        # Set the tray icon with appropriate resolution based on platform
        if platform.system() == 'Windows':
            icon_size = 16  # Windows usually uses 16x16 icons in system tray
            preferred_icon = "microphone_16.png"
        else:
            icon_size = 32  # macOS and others use larger icons
            preferred_icon = "microphone_32.png"
        
        # First try to load icon from file
        icon_path = self._find_icon(preferred_icon, "microphone.png")
        if icon_path.exists():
            logger.debug(f"Loading tray icon from: {icon_path}")
            try:
                self._default_icon = QIcon(str(icon_path))
                # Check if the icon is valid/loaded correctly
                if self._default_icon.isNull():
                    logger.warning("Icon loaded but appears to be null/invalid")
                else:
                    logger.debug("Successfully loaded icon from file")
            except Exception as e:
                logger.error(f"Error loading icon: {e}")
                self._default_icon = self._create_default_icon()
        else:
            logger.info("Using fallback built-in icon")
            self._default_icon = self._create_default_icon()
            
        # Set the icon for the system tray
        self.setIcon(self._default_icon)
        logger.debug("System tray icon set")
        
        # Create success icon for transcription completion
        self.success_icon = self._create_success_icon()
        
        # Store reference to inactive icon for restoration
        self.inactive_icon = self._default_icon
        
        # Set recording icon - we'll create it in memory for consistency
        self.recording_icon = self._create_recording_icon()
        
        # Create processing icon
        self.processing_icon = self._create_processing_icon()
        
        # Create pulse animation timer
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate_icon)
        self.animation_frame = 0
        self.is_recording = False
        self.is_processing = False
        
        # Create multiple animation frames
        self.recording_frames = []
        self._create_recording_animation_frames()
        
        # Create processing animation frames
        self.processing_frames = []
        self._create_processing_animation_frames()
        
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
        self.setToolTip("Mutter\nReady")
        
        # Store the last transcription and processed text
        self.last_transcription = ""
        self.last_llm_result = ""
        
        # Connect activation signal for double-click
        self.activated.connect(self.on_activated)

        # Create reference to windows (don't initialize them yet)
        self.settings_window = None
        
        # Reference to service manager (set later)
        self.service_manager = None

    def _find_icon(self, preferred_name, fallback_name):
        """Find an icon file in the resources directory
        
        Args:
            preferred_name: Preferred filename to look for
            fallback_name: Fallback filename if preferred isn't found
            
        Returns:
            Path to the icon file
        """
        logger.debug(f"Searching for icon: {preferred_name} or {fallback_name}")
        
        # Start with the base project directory
        try:
            base_dir = Path(__file__).parent.parent.parent
            logger.debug(f"Base directory: {base_dir}")
            
            # Check if resources directory exists
            resources_dir = base_dir / "resources"
            if resources_dir.exists():
                logger.debug(f"Resources directory exists: {resources_dir}")
            else:
                logger.warning(f"Resources directory not found at: {resources_dir}")
                
            # Check if images directory exists
            images_dir = resources_dir / "images"
            if images_dir.exists():
                logger.debug(f"Images directory exists: {images_dir}")
            else:
                logger.warning(f"Images directory not found at: {images_dir}")
        except Exception as e:
            logger.error(f"Error checking directories: {e}")
        
        # Look in common locations for the icon files
        paths = [
            # Standard paths
            base_dir / "resources" / "images" / preferred_name,
            base_dir / "resources" / "images" / fallback_name,
            base_dir / "resources" / "images" / preferred_name.lower(),
            base_dir / "resources" / "images" / fallback_name.lower(),
            base_dir / "resources" / fallback_name,
            base_dir / "resources" / fallback_name.lower(),
            # Windows subdirectory
            base_dir / "resources" / "images" / "windows" / preferred_name,
            base_dir / "resources" / "images" / "windows" / fallback_name,
            # Icons directory
            base_dir / "resources" / "icons" / preferred_name,
            base_dir / "resources" / "icons" / fallback_name,
            # Relative paths
            Path(__file__).parent / "resources" / preferred_name,
            Path(__file__).parent / "resources" / fallback_name,
        ]
        
        # Try case-insensitive matching via direct directory scanning
        try:
            # Try to find files with similar names in images directory
            if images_dir.exists():
                for file in images_dir.glob("*.*"):
                    if file.name.lower() == preferred_name.lower() or file.name.lower() == fallback_name.lower():
                        logger.debug(f"Found icon via case-insensitive match: {file}")
                        return file
            
            # Check if icons directory exists and try there too
            icons_dir = resources_dir / "icons"
            if icons_dir.exists():
                for file in icons_dir.glob("*.*"):
                    if file.name.lower() == preferred_name.lower() or file.name.lower() == fallback_name.lower():
                        logger.debug(f"Found icon via case-insensitive match in icons dir: {file}")
                        return file
        except Exception as e:
            logger.error(f"Error during case-insensitive file search: {e}")
        
        # Check all standard paths
        for path in paths:
            if path.exists():
                logger.debug(f"Found icon at: {path}")
                return path
        
        # Do a last-ditch recursive search in the resources directory
        try:
            if resources_dir.exists():
                for pattern in [f"**/{preferred_name}", f"**/{fallback_name}", "**/*.png", "**/*.ico"]:
                    matches = list(resources_dir.glob(pattern))
                    if matches:
                        logger.debug(f"Found icon via recursive search: {matches[0]}")
                        return matches[0]
        except Exception as e:
            logger.error(f"Error during recursive file search: {e}")
                
        # Return the first path anyway, even if it doesn't exist
        logger.warning(f"Could not find icon: {preferred_name} or {fallback_name}")
        return paths[0]

    def update_settings(self, settings):
        """Update settings related to notifications"""
        logger.debug(f"Updating system tray settings")
        if hasattr(settings, 'appearance') and settings.appearance:
            self.show_notifications = settings.appearance.show_notifications
            self.auto_paste = settings.appearance.auto_paste
            logger.debug(f"Updated settings: show_notifications={self.show_notifications}, "
                        f"auto_paste={self.auto_paste}")
        else:
            logger.debug("No appearance settings available")

    def show_notification(self, title, message, icon=QSystemTrayIcon.MessageIcon.Information, duration=3000):
        """Show a notification if enabled in settings
        
        Args:
            title: Notification title
            message: Notification message
            icon: Icon type (Information, Warning, Critical)
            duration: Display duration in milliseconds
        """
        if self.show_notifications:
            self.showMessage(title, message, icon, duration)

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.last_transcription:
                self.copy_to_clipboard()
                # No notification needed, just log the action
                logger.debug("Double-click triggered: transcription copied to clipboard")
        elif reason == QSystemTrayIcon.Trigger:
            # Single click - show/hide settings
            self.show_settings()

    @Slot()
    def on_recording_started(self):
        """Handle recording started signal"""
        self.status_action.setText("● Recording...")
        self.setToolTip("Mutter\nRecording in progress")
        
        # Set the recording state
        self.is_recording = True
        
        # Start animation timer - update every 500ms for smooth pulsing
        self.animation_frame = 0
        self.animation_timer.start(500)
        
        # Show custom toast notification with recording icon - shorter duration (2.5 seconds)
        if self.show_notifications:
            self.toast.show_toast("Recording", "Started recording audio", 2500, "recording")

    @Slot()
    def on_stop_hotkey_pressed(self):
        """
        Slot called when the stop hotkey is pressed.
        Shows a toast notification indicating that recording is stopping.
        """
        # Use an emoji icon to grab attention
        logger.debug("on_stop_hotkey_pressed called - showing toast notification for stopping recording")
        if self.show_notifications:
            self.toast.show_toast(
                "Recording Stopped", 
                "Processing...",
                duration=3000,  # 3 seconds - shorter duration
                icon_type="info"
            )
        
        logger.debug("Toast notification shown for stopping recording")

    @Slot(Path)
    def on_recording_stopped(self, file_path: Path):
        """Handle recording stopped signal"""
        self.status_action.setText("Processing...")
        self.setToolTip("Mutter\nProcessing recording")
        
        # Set recording state
        self.is_recording = False
        self.is_processing = True
        
        # Continue the animation but now using processing frames
        if not self.animation_timer.isActive():
            self.animation_timer.start(500)
        
        # Set the processing icon explicitly to ensure visual indicator changes
        self.setIcon(self.processing_icon)

    @Slot(str)
    def on_recording_failed(self, error_message: str):
        """Handle recording failed signal"""
        self.status_action.setText("Ready")
        self.setToolTip("Mutter\nReady")
        
        # Restore original icon
        icon_path = self._find_icon(f"microphone_{16 if platform.system() == 'Windows' else 32}.png", "microphone.png")
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            self.setIcon(self._create_default_icon())
        
        # Show error notification only for critical errors, but with no sound
        # Use a very small duration (1000ms) to be less intrusive
        logger.error(f"Recording failed: {error_message}")
        
        # Only show UI notification for truly critical errors that need immediate attention
        if "Permission denied" in error_message or "Device not found" in error_message:
            try:
                # Using a hack to show notification without sound - send empty option
                self.showMessage(
                    "Mic Error",
                    f"Could not access microphone:\n{error_message}",
                    QSystemTrayIcon.MessageIcon.Critical,
                    1000  # Short duration
                )
            except:
                # If that fails, just log it
                pass

    @Slot(str)
    def on_transcription_complete(self, text: str):
        """
        Handle transcription complete signal.
        Updates the menu with the transcription and shows a notification.
        """
        logger.debug(f"Transcription complete, text length: {len(text)}")
        logger.debug(f"Received text: {text[:100]}...")

        # Store the transcription and update menu items
        self.last_transcription = text
        logger.debug(f"Set last_transcription to: {self.last_transcription[:100]}...")
        logger.debug(f"Current last_llm_result: {self.last_llm_result[:100] if self.last_llm_result else 'None'}...")
        self.update_last_transcription_menu_item()

        # Set processing state
        self.is_processing = False

        # Stop animation timer
        self.animation_timer.stop()

        # Reset to default icon
        self.setIcon(self._default_icon)

        # Update status
        self.status_action.setText("Ready")
        self.setToolTip("Mutter\nReady")

        # Only copy and auto-paste if LLM did NOT process this text
        # (If LLM processed it, on_llm_processing_complete already handled copy/paste)
        llm_processed_this = (self.last_llm_result and
                             self.last_llm_result == text)

        if not llm_processed_this:
            # LLM was not enabled or did not process - copy and paste the raw transcription
            logger.debug("LLM did not process this text - copying and pasting transcription")
            self.copy_to_clipboard()

            # Auto-paste into current active window if enabled
            if self.auto_paste:
                logger.debug("Auto-pasting raw transcription")
                self._auto_paste_to_active_window()
        else:
            logger.debug("LLM already processed and pasted this text - skipping duplicate paste")

        # Schedule the toast notification with a slight delay to avoid overlap
        logger.debug("Scheduling transcription complete toast with 1.5s delay")
        QTimer.singleShot(1500, self._show_transcription_complete_toast)

    def _show_transcription_complete_toast(self):
        """Show a toast notification indicating transcription is complete"""
        logger.debug("Showing transcription complete toast")
        if self.show_notifications:
            self.toast.show_toast(
                "Transcription Complete", 
                "✓ Copied to clipboard",
                duration=2500,  # 2.5 seconds - shorter duration
                icon_type="success"
            )
        logger.debug("Transcription complete toast shown")

    def _flash_success_icon(self):
        """Flash the icon briefly to indicate transcription is complete"""
        # Create a success icon (green checkmark)
        success_icon = self._create_success_icon()
        
        # Set to success icon
        self.setIcon(success_icon)
        
        # Schedule restoration of the original icon after 1 second
        QTimer.singleShot(1000, lambda: self.setIcon(self._default_icon))

    def _create_success_icon(self) -> QIcon:
        """Create a success icon with a green checkmark"""
        sizes = [16, 24, 32, 48, 64, 128]
        icon = QIcon()
        
        for size in sizes:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw a green circle
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(40, 167, 69))  # Bootstrap success green
            painter.drawEllipse(2, 2, size-4, size-4)
            
            # Draw checkmark
            pen_width = max(2, size // 16)
            painter.setPen(QColor(255, 255, 255))  # White color for the checkmark
            
            # Draw check
            check_points = [
                (size * 0.3, size * 0.5),   # Start point
                (size * 0.45, size * 0.65),  # Middle point
                (size * 0.7, size * 0.35)    # End point
            ]
            
            for i in range(len(check_points) - 1):
                x1, y1 = check_points[i]
                x2, y2 = check_points[i + 1]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            
            painter.end()
            icon.addPixmap(pixmap)
            
        return icon

    @Slot(object)
    def on_llm_processing_complete(self, result):
        """Handle LLM processing complete

        Args:
            result: LLMProcessingResult object
        """
        # Store the LLM result
        self.last_llm_result = result.processed_text
        logger.debug(f"LLM processing complete, stored result: {self.last_llm_result[:50]}...")

        # Update menu items if they exist
        if hasattr(self, 'recent_llm_action') and self.recent_llm_action:
            preview = result.processed_text[:50] + "..." if len(result.processed_text) > 50 else result.processed_text
            self.recent_llm_action.setText(preview)
            self.recent_llm_action.setEnabled(True)
        if hasattr(self, 'copy_llm_action') and self.copy_llm_action:
            self.copy_llm_action.setEnabled(True)

        # When LLM is enabled, auto-paste happens HERE after LLM completes
        # Copy to clipboard and auto-paste the LLM result
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_llm_result)
        logger.debug(f"Copied LLM result to clipboard: {self.last_llm_result[:100]}...")

        # Auto-paste into current active window if enabled
        if self.auto_paste:
            logger.debug("Auto-pasting LLM result")
            self._auto_paste_to_active_window()

        # Show toast with preview of processed text and success icon - extended duration
        if self.show_notifications:
            toast_preview = result.processed_text[:35] + "..." if len(result.processed_text) > 35 else result.processed_text
            process_type = result.processing_type.replace("_", " ").title()  # Format the processing type for display
            self.toast.show_toast(f"{process_type} Complete", toast_preview, 4000, "success")

        # Flash icon to indicate completion
        self._flash_success_icon()

    def copy_to_clipboard(self):
        """Copy the last transcription to clipboard"""
        if not self.last_transcription:
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_transcription)
        logger.debug(f"Copied transcription to clipboard: {self.last_transcription[:100]}...")

        # For Linux, also set the selection clipboard
        if platform.system() == 'Linux':
            clipboard.setText(self.last_transcription, QClipboard.Selection)
            logger.debug("Also copied to selection clipboard on Linux")

    def copy_llm_to_clipboard(self):
        """Copy the last LLM processed text to clipboard"""
        if not self.last_llm_result:
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_llm_result)
        logger.debug("Copied LLM result to clipboard")

    def show_settings(self):
        """Show the settings window"""
        if self.settings_window is None or not self.settings_window.isVisible():
            if self.service_manager:
                # Force reload the settings from the repository to ensure we have the latest
                logger.info("Opening settings window - forcing reload of settings")
                self.service_manager.reload_settings()
                settings = self.service_manager.settings
                
                # Log key settings values for debugging
                logger.info(f"Loading settings window with: "
                           f"quit_key={settings.hotkeys.quit_key.toString() if settings.hotkeys.quit_key else 'None'}, "
                           f"record_key={settings.hotkeys.record_key.toString()}")
                
                if self.settings_window is not None:
                    self._disconnect_settings_signals()
                
                self.settings_window = SettingsWindow(
                    settings=settings,
                    settings_repository=self.service_manager.recording_service.settings_repository
                )
                
                # Connect signals
                if hasattr(self.settings_window, 'settings_saved'):
                    self.settings_window.settings_saved.connect(self._on_settings_saved)
            else:
                logger.error("Cannot show settings: service_manager not set")
                return
        
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
    
    def _disconnect_settings_signals(self):
        """Safely disconnect all signals from the settings window to prevent memory leaks."""
        if self.settings_window is None:
            return
        
        try:
            if hasattr(self.settings_window, 'settings_saved'):
                try:
                    self.settings_window.settings_saved.disconnect(self._on_settings_saved)
                    logger.debug("Disconnected settings_saved signal")
                except (TypeError, RuntimeError):
                    # Signal was not connected or already disconnected
                    pass
        except Exception as e:
            logger.warning(f"Error disconnecting settings signals: {e}")

    def quit_application(self):
        """Quit the application"""
        QApplication.quit()

    def _create_default_icon(self) -> QIcon:
        """Create a default icon based on available image files or generate one if not found"""
        # Try to load from files first
        icon = QIcon()
        base_dir = Path(__file__).parent.parent.parent
        resources_dir = base_dir / "resources" / "images"
        
        # Try to load all sizes of microphone.png
        sizes = [16, 32, 64, 128]
        found_any_file = False
        
        for size in sizes:
            # Try size-specific files first
            size_file = resources_dir / f"microphone_{size}.png"
            if size_file.exists():
                icon.addFile(str(size_file), QSize(size, size))
                found_any_file = True
                logger.debug(f"Loaded icon file: {size_file}")
        
        # If we couldn't find any size-specific files, try the base microphone.png
        if not found_any_file:
            base_file = resources_dir / "microphone.png"
            if base_file.exists():
                icon.addFile(str(base_file))
                found_any_file = True
                logger.debug(f"Loaded base icon file: {base_file}")
        
        # If we found and loaded any icon files, return the icon
        if found_any_file and not icon.isNull():
            return icon
            
        # If we couldn't load any files, generate an icon as fallback
        logger.warning("No microphone icon files found, using generated icon")
        return self._generate_default_icon()
        
    def _generate_default_icon(self) -> QIcon:
        """Generate a default microphone icon if no image files are found"""
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
        """Create a recording icon with red dot in top right corner using the original logo"""
        sizes = [16, 24, 32, 48, 64, 128]
        icon = QIcon()
        
        # Use original microphone icon as the base
        original_icon = self._default_icon
        
        for size in sizes:
            # Start with the original icon pixmap
            pixmap = original_icon.pixmap(size, size)
            
            # If the pixmap is valid (not null or empty), use it as the base
            if not pixmap.isNull() and pixmap.width() > 0:
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                
                # Draw a red recording indicator dot in the top right corner
                indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                indicator_x = size - indicator_size - 1
                indicator_y = 1
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 0, 0))  # Bright red
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                
                painter.end()
            else:
                # If the original icon pixmap is invalid, create a new one with the generated icon
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.transparent)
                
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                
                # Draw the base icon (blue circle with microphone)
                temp_icon = self._generate_default_icon()
                temp_pixmap = temp_icon.pixmap(size, size)
                painter.drawPixmap(0, 0, temp_pixmap)
                
                # Draw a red recording indicator
                indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                indicator_x = size - indicator_size - 1
                indicator_y = 1
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 0, 0))  # Bright red
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                
                painter.end()
            
            icon.addPixmap(pixmap)
        
        return icon

    def _create_recording_animation_frames(self):
        """Create animation frames for recording with flashing red dot"""
        self.recording_frames = []
        
        # Create frames with different opacity levels for flashing red dot
        opacity_levels = [1.0, 0.6, 0.3, 0.6, 1.0]
        
        sizes = [16, 24, 32, 48, 64, 128]
        
        # Use original icon as base
        original_icon = self._default_icon
        
        for opacity in opacity_levels:
            icon = QIcon()
            
            for size in sizes:
                # Start with the original icon pixmap
                pixmap = original_icon.pixmap(size, size)
                
                # If the pixmap is valid, use it as the base
                if not pixmap.isNull() and pixmap.width() > 0:
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # Draw a red recording indicator with variable opacity for flashing
                    indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                    indicator_x = size - indicator_size - 1
                    indicator_y = 1
                    
                    # Use variable opacity for flashing effect
                    recording_color = QColor(255, 0, 0, int(255 * opacity))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(recording_color)
                    painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                    
                    painter.end()
                else:
                    # If the original icon pixmap is invalid, create a new one with the generated icon
                    pixmap = QPixmap(size, size)
                    pixmap.fill(Qt.transparent)
                    
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # Draw the base icon
                    temp_icon = self._generate_default_icon()
                    temp_pixmap = temp_icon.pixmap(size, size)
                    painter.drawPixmap(0, 0, temp_pixmap)
                    
                    # Draw a red recording indicator with variable opacity for flashing
                    indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                    indicator_x = size - indicator_size - 1
                    indicator_y = 1
                    
                    # Use variable opacity for flashing effect
                    recording_color = QColor(255, 0, 0, int(255 * opacity))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(recording_color)
                    painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                    
                    painter.end()
                
                icon.addPixmap(pixmap)
                
            self.recording_frames.append(icon)

    def _animate_icon(self):
        """Animate the icon by cycling through frames based on current state"""
        if self.is_recording:
            frame_index = self.animation_frame % len(self.recording_frames)
            self.setIcon(self.recording_frames[frame_index])
        elif self.is_processing:
            frame_index = self.animation_frame % len(self.processing_frames)
            self.setIcon(self.processing_frames[frame_index])
        
        self.animation_frame += 1

    def _create_processing_icon(self) -> QIcon:
        """Create a processing icon with light red dot in top right corner using the original logo"""
        sizes = [16, 24, 32, 48, 64, 128]
        icon = QIcon()
        
        # Use original microphone icon as the base
        original_icon = self._default_icon
        
        for size in sizes:
            # Start with the original icon pixmap
            pixmap = original_icon.pixmap(size, size)
            
            # If the pixmap is valid (not null or empty), use it as the base
            if not pixmap.isNull() and pixmap.width() > 0:
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                
                # Draw a lighter red processing indicator in the top right corner
                indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                indicator_x = size - indicator_size - 1
                indicator_y = 1
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 128, 128))  # Lighter red
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                
                painter.end()
            else:
                # If the original icon pixmap is invalid, create a new one with the generated icon
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.transparent)
                
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                
                # Draw the base icon (blue circle with microphone)
                temp_icon = self._generate_default_icon()
                temp_pixmap = temp_icon.pixmap(size, size)
                painter.drawPixmap(0, 0, temp_pixmap)
                
                # Draw a lighter red processing indicator
                indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                indicator_x = size - indicator_size - 1
                indicator_y = 1
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 128, 128))  # Lighter red
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                
                painter.end()
            
            icon.addPixmap(pixmap)
        
        return icon

    def _create_processing_animation_frames(self):
        """Create animation frames for processing indicator with light red dot"""
        self.processing_frames = []
        
        # Create frames with different opacity levels for subtle pulsing of lighter red dot
        opacity_levels = [1.0, 0.9, 0.8, 0.7, 0.8, 0.9]
        
        sizes = [16, 24, 32, 48, 64, 128]
        
        # Use original icon as base
        original_icon = self._default_icon
        
        for opacity in opacity_levels:
            icon = QIcon()
            
            for size in sizes:
                # Start with the original icon pixmap
                pixmap = original_icon.pixmap(size, size)
                
                # If the pixmap is valid, use it as the base
                if not pixmap.isNull() and pixmap.width() > 0:
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # Draw a lighter red processing indicator with subtle pulsing
                    indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                    indicator_x = size - indicator_size - 1
                    indicator_y = 1
                    
                    # Use lighter red with variable opacity for subtle pulsing
                    processing_color = QColor(255, 128, 128, int(255 * opacity))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(processing_color)
                    painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                    
                    painter.end()
                else:
                    # If the original icon pixmap is invalid, create a new one with the generated icon
                    pixmap = QPixmap(size, size)
                    pixmap.fill(Qt.transparent)
                    
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # Draw the base icon
                    temp_icon = self._generate_default_icon()
                    temp_pixmap = temp_icon.pixmap(size, size)
                    painter.drawPixmap(0, 0, temp_pixmap)
                    
                    # Draw a lighter red processing indicator with subtle pulsing
                    indicator_size = max(size // 5, 4)  # Ensure it's at least 4px
                    indicator_x = size - indicator_size - 1
                    indicator_y = 1
                    
                    # Use lighter red with variable opacity for subtle pulsing
                    processing_color = QColor(255, 128, 128, int(255 * opacity))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(processing_color)
                    painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                    
                    painter.end()
                
                icon.addPixmap(pixmap)
                
            self.processing_frames.append(icon)

    def update_last_transcription_menu_item(self):
        """Update the text in the recent transcription menu item"""
        if self.last_transcription:
            # Create a preview (truncated text) for the menu item
            preview = self.last_transcription[:50] + "..." if len(self.last_transcription) > 50 else self.last_transcription
            self.recent_transcription_action.setText(preview)
            self.recent_transcription_action.setEnabled(True)
            self.copy_action.setEnabled(True)
        else:
            self.recent_transcription_action.setText("No recent transcriptions")
            self.recent_transcription_action.setEnabled(False)
            self.copy_action.setEnabled(False)

    def _auto_paste_to_active_window(self):
        """Automatically paste the clipboard content into the currently active window"""
        try:
            logger.debug("Attempting to auto-paste to active window")

            # Use LLM result if available, otherwise use raw transcription
            text_to_paste = self.last_llm_result if self.last_llm_result else self.last_transcription
            logger.debug(f"Pasting {'LLM processed' if self.last_llm_result else 'raw'} text: {text_to_paste[:100]}...")

            # Import platform-specific modules
            import platform
            if platform.system() == 'Windows':
                windows.WindowsSystemExtension.paste_text(text_to_paste)
            elif platform.system() == 'Darwin':  # macOS
                macos.MacOSSystemExtension.paste_text(text_to_paste)
            elif platform.system() == 'Linux':
                linux.LinuxSystemExtension.paste_text(text_to_paste)

        except Exception as e:
            logger.error(f"Error in auto-paste: {e}", exc_info=True)

    def set_service_manager(self, service_manager):
        """Set the service manager reference
        
        Args:
            service_manager: ServiceManager instance
        """
        self.service_manager = service_manager

    def _on_settings_saved(self):
        """Handle settings saved event"""
        if self.service_manager:
            # Reload settings in service manager (handles LLM, audio, hotkey updates internally)
            self.service_manager.reload_settings()

            # Update tray's own notification/auto_paste preferences
            self.update_settings(self.service_manager.settings)

    def show(self):
        """Override show method to handle D-Bus errors on Linux"""
        try:
            # Try the normal show method
            super().show()
            logger.debug("System tray icon shown successfully")
        except Exception as e:
            logger.error(f"Error showing system tray icon: {e}")
            if "QDBusError" in str(e) and platform.system() == 'Linux':
                # Try to reinitialize with XCB platform
                try:
                    os.environ['QT_QPA_PLATFORM'] = 'xcb'
                    # Try additional Fedora-specific configurations
                    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = '/usr/lib64/qt5/plugins/platforms'
                    os.environ['QT_QPA_PLATFORM'] = 'xcb'
                    super().show()
                    logger.debug("System tray icon shown successfully with XCB platform")
                except Exception as e2:
                    logger.warning(f"D-Bus error detected and XCB fallback failed: {e2}")
                    # Try one last time with minimal configuration
                    try:
                        os.environ['QT_QPA_PLATFORM'] = 'xcb'
                        os.environ['QT_NO_DBUS'] = '1'
                        super().show()
                        logger.debug("System tray icon shown with minimal configuration")
                    except Exception as e3:
                        logger.warning(f"All attempts to show system tray icon failed: {e3}")
                        logger.info("Application will continue working but tray icon may not be visible")
                        # The application can still work even if the tray icon isn't visible
                        # Users can still use hotkeys to control the application 