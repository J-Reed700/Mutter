from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QWidget
from PySide6.QtGui import QIcon, QAction, QFont, QClipboard, QPixmap, QPainter, QColor
from PySide6.QtCore import Slot, QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from pathlib import Path
from .toast.custom_toast import CustomToast
import logging
import platform

logger = logging.getLogger(__name__)

class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        
        # Settings for notifications (defaults)
        self.show_notifications = False
        self.mute_notifications = True
        
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
        
        # Create pulse animation timer
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate_recording_icon)
        self.animation_frame = 0
        self.is_recording = False
        
        # Create multiple animation frames
        self.recording_frames = []
        self._create_recording_animation_frames()
        
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
        
        # Add recent LLM processed text action
        self.recent_llm_action = QAction("No LLM processed text")
        self.recent_llm_action.setEnabled(False)
        llm_font = QFont()
        llm_font.setPointSize(9)
        llm_font.setItalic(True)
        self.recent_llm_action.setFont(llm_font)
        self.menu.addAction(self.recent_llm_action)
        
        # Add copy to clipboard action with icon
        self.copy_action = QAction("Copy to Clipboard")
        self.copy_action.setEnabled(False)
        self.copy_action.triggered.connect(self.copy_to_clipboard)
        # Add clipboard icon if available
        clipboard_icon = QIcon.fromTheme("edit-copy")
        if not clipboard_icon.isNull():
            self.copy_action.setIcon(clipboard_icon)
        self.menu.addAction(self.copy_action)
        
        # Add copy LLM result to clipboard action
        self.copy_llm_action = QAction("Copy LLM Result to Clipboard")
        self.copy_llm_action.setEnabled(False)
        self.copy_llm_action.triggered.connect(self.copy_llm_to_clipboard)
        if not clipboard_icon.isNull():
            self.copy_llm_action.setIcon(clipboard_icon)
        self.menu.addAction(self.copy_llm_action)
        
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
        
        # Store the last transcription and processed text
        self.last_transcription = ""
        self.last_llm_result = ""
        
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
        """Update tray settings from application settings"""
        if hasattr(settings, 'appearance') and settings.appearance:
            # Override settings to always disable notifications
            self.show_notifications = False
            self.mute_notifications = True
            logger.debug("Notifications have been disabled")

    def show_notification(self, title, message, icon=QSystemTrayIcon.MessageIcon.Information, duration=3000):
        """Show a notification if enabled in settings
        
        Args:
            title: Notification title
            message: Notification message
            icon: Icon type (Information, Warning, Critical)
            duration: Display duration in milliseconds
        """
        if self.show_notifications:
            # PySide6 doesn't support ShowMessageHint.NoSound directly
            # We can't control sound in PySide6 directly, so we just show the notification
            # The system's notification sound settings will control whether sound is played
            self.showMessage(title, message, icon, duration)
            
            # Note: In PySide6, sound control for notifications needs to be handled at the system level
            # If mute_notifications is True, the application can't directly control this
            # Users should mute notification sounds in their system settings

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.last_transcription:
                self.copy_to_clipboard()
                # No notification needed, just log the action
                logger.debug("Double-click triggered: transcription copied to clipboard")

    @Slot()
    def on_recording_started(self):
        """Handle recording started signal"""
        self.status_action.setText("● Recording...")
        self.setToolTip("Voice Recorder\nRecording in progress")
        
        # Set the recording state
        self.is_recording = True
        
        # Start animation timer - update every 500ms for smooth pulsing
        self.animation_frame = 0
        self.animation_timer.start(500)
        
        # Show custom toast notification with recording icon - shorter duration (2.5 seconds)
        self.toast.show_toast("Recording", "Started recording audio", 2500, "recording")

    @Slot()
    def on_stop_hotkey_pressed(self):
        """
        Slot called when the stop hotkey is pressed.
        Shows a toast notification indicating that recording is stopping.
        """
        # Use an emoji icon to grab attention
        logger.debug("on_stop_hotkey_pressed called - showing toast notification for stopping recording")
        self.toast.show_toast(
            "Recording Stopped", 
            "⏹️ Processing...",
            duration=3000,  # 3 seconds - shorter duration
            icon_type="info"
        )
        
        logger.debug("Toast notification shown for stopping recording")

    @Slot(Path)
    def on_recording_stopped(self, file_path: Path):
        """Handle recording stopped signal"""
        self.status_action.setText("Processing...")
        self.setToolTip("Voice Recorder\nProcessing recording")
        
        # Set recording state
        self.is_recording = False
        
        # Stop animation timer
        self.animation_timer.stop()
        
        # Restore original icon
        if hasattr(self, '_default_icon'):
            self.setIcon(self._default_icon)
        else:
            icon_path = self._find_icon(f"microphone_{16 if platform.system() == 'Windows' else 32}.png", "microphone.png")
            if icon_path.exists():
                self.setIcon(QIcon(str(icon_path)))
            else:
                self.setIcon(self._create_default_icon())
        
        # Show custom toast notification with info icon to indicate processing immediately
        self.toast.show_toast("Processing Recording", "Your recording is being analyzed...", 4000, "info")

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
        
        # Store the transcription and update menu items
        self.last_transcription = text
        self.update_last_transcription_menu_item()
        
        # Copy to clipboard automatically without showing notification
        self.copy_to_clipboard()
        
        # Schedule the toast notification with a slight delay to avoid overlap
        logger.debug("Scheduling transcription complete toast with 1.5s delay")
        QTimer.singleShot(1500, self._show_transcription_complete_toast)

    def _show_transcription_complete_toast(self):
        """Show a toast notification indicating transcription is complete"""
        logger.debug("Showing transcription complete toast")
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
        
        # Update menu items
        preview = result.processed_text[:50] + "..." if len(result.processed_text) > 50 else result.processed_text
        self.recent_llm_action.setText(preview)
        self.recent_llm_action.setEnabled(True)
        self.copy_llm_action.setEnabled(True)
        
        # Copy to clipboard
        self.copy_llm_to_clipboard()
        
        # Show toast with preview of processed text and success icon - extended duration
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
        logger.debug("Copied transcription to clipboard")
    
    def copy_llm_to_clipboard(self):
        """Copy the last LLM processed text to clipboard"""
        if not self.last_llm_result:
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_llm_result)
        logger.debug("Copied LLM result to clipboard")

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

    def _create_recording_animation_frames(self):
        """Create animation frames for recording indicator"""
        self.recording_frames = []
        
        # Create 4 frames with different opacity levels for pulsing effect
        opacity_levels = [1.0, 0.8, 0.6, 0.8]  # Pulse effect
        sizes = [16, 24, 32, 48, 64, 128]
        
        for opacity in opacity_levels:
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
                
                # Draw a red recording indicator with varying opacity
                indicator_size = max(size // 4, 4)  # Ensure it's at least 4px
                indicator_x = size - indicator_size - 2
                indicator_y = 2
                
                recording_color = QColor(255, 59, 48, int(255 * opacity))  # #ff3b30 with variable opacity
                painter.setBrush(recording_color)
                painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)
                
                painter.end()
                icon.addPixmap(pixmap)
                
            self.recording_frames.append(icon)

    def _animate_recording_icon(self):
        """Animate the recording icon by cycling through frames"""
        if not self.is_recording:
            return
            
        frame_index = self.animation_frame % len(self.recording_frames)
        self.setIcon(self.recording_frames[frame_index])
        self.animation_frame += 1 

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