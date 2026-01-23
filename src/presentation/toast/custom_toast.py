import logging
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QTimer
import platform

logger = logging.getLogger(__name__)

# Try to import win32gui for window flashing (attention-getting on Windows)
try:
    import win32gui
    import win32con
    HAS_WIN32GUI = True
except ImportError:
    HAS_WIN32GUI = False
    logger.debug("win32gui not available, window flashing disabled")

class CustomToast(QWidget):
    """Custom toast notification that's less intrusive than system notifications"""
    
    def __init__(self, parent=None):
        # Initialize with appropriate flags for the platform
        if platform.system() == 'Darwin':
            super().__init__(parent)
            # Set window flags for macOS
            self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            # Set attributes for macOS
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_NoSystemBackground)
        else:
            super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            
        self.setStyleSheet("""
            QWidget#toastWidget {
                background: rgba(45, 45, 60, 0.97);
                border-radius: 12px;
                border: 1px solid rgba(160, 160, 200, 0.5);
                color: white;
            }
            QLabel#titleLabel {
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 6px 2px 2px 2px;
                background-color: transparent;
            }
            QLabel#messageLabel {
                color: #e0e0e0;
                font-size: 12px;
                padding: 2px 4px 6px 2px;
                background-color: transparent;
            }
            QLabel#iconLabel {
                background-color: transparent;
            }
            QPushButton#closeButton {
                border: none;
                background-color: transparent;
                color: #aaa;
                padding: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#closeButton:hover {
                color: white;
            }
        """)
        
        # Ensure window is fully opaque
        self.setObjectName("toastWidget")
        self.setWindowOpacity(0.95)  # Slight transparency for modern look
        
        # Disable any composition/transparency effects
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 10, 14, 10)
        self.layout.setSpacing(0)
        
        # Status row
        self.status_layout = QHBoxLayout()
        self.status_layout.setSpacing(8)  # Slightly more space between icon and title
        
        # Add icon label
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        self.status_layout.addWidget(self.icon_label)
        
        # Title with custom style
        self.title_label = QLabel("Recording")
        self.title_label.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(20, 20)
        self.close_button.clicked.connect(self.hide)
        
        self.status_layout.addWidget(self.title_label)
        self.status_layout.addStretch()
        self.status_layout.addWidget(self.close_button)
        
        # Message with custom style
        self.message_label = QLabel("Recording started")
        self.message_label.setObjectName("messageLabel")
        self.message_label.setWordWrap(True)
        
        self.layout.addLayout(self.status_layout)
        self.layout.addWidget(self.message_label)
        
        # Set up auto-hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._safe_hide)
        
        # Animation properties
        self.opacity = 0.0
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate_appearance)
        self.animation_step = 0
        
        # Fade-out animation timer (separate from appearance animation)
        self.fadeout_timer = QTimer(self)
        self.fadeout_timer.setSingleShot(True)
        self.fadeout_timer.timeout.connect(self._fadeout_step)
        self.fadeout_step_count = 0
        
        # Initialize size
        self.setFixedSize(280, 80)
        
        # Set initial position outside screen
        self.move(2000, 2000)
        
        # Track toast state
        self.is_active = False
        self.current_flash_timer = None
        self._is_closing = False  # Prevent re-entry during close

    def _animate_appearance(self):
        """Animate the appearance of the toast with a subtle fade-in effect"""
        self.animation_step += 1
        
        # Calculate opacity for fade-in effect
        opacity = min(1.0, self.animation_step / 5)
        self.setWindowOpacity(opacity)
        
        # Stop the animation after 5 frames
        if self.animation_step >= 5:
            self.animation_timer.stop()
            self.setWindowOpacity(0.95)  # Final opacity
            # Ensure visibility by bringing to front and raising
            if platform.system() != 'Darwin':
                self.activateWindow()  # Skip activation on macOS
            self.raise_()
            return

    def set_icon(self, icon_type):
        """Set the icon based on notification type"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if icon_type == "recording":
            # Red circle for recording
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 80, 80))  # Brighter red
            painter.drawEllipse(2, 2, 12, 12)
        elif icon_type == "success":
            # Green circle for success
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(60, 185, 80))  # Brighter green
            painter.drawEllipse(2, 2, 12, 12)
            
            # Checkmark
            painter.setPen(QColor(255, 255, 255))
            painter.drawLine(4, 8, 7, 11)
            painter.drawLine(7, 11, 12, 5)
        elif icon_type == "info":
            # Blue circle for info
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(50, 140, 255))  # Brighter blue
            painter.drawEllipse(2, 2, 12, 12)
            
            # "i" for info
            painter.setPen(QColor(255, 255, 255))
            painter.drawLine(8, 5, 8, 6)
            painter.drawLine(8, 8, 8, 11)
        
        painter.end()
        self.icon_label.setPixmap(pixmap)

    def force_close(self):
        """Force close any active toast immediately"""
        if self.is_active or self._is_closing:
            logger.debug("Force closing active toast")
            self._stop_all_timers()
            
            # Actually hide the toast
            self._is_closing = True
            try:
                super().hide()
            finally:
                self.is_active = False
                self._is_closing = False
            logger.debug("Toast closed")
    
    def _stop_all_timers(self):
        """Stop all timers to prevent memory leaks and orphaned callbacks."""
        try:
            if self.hide_timer and self.hide_timer.isActive():
                self.hide_timer.stop()
        except RuntimeError:
            pass  # Timer may already be deleted
        
        try:
            if self.animation_timer and self.animation_timer.isActive():
                self.animation_timer.stop()
        except RuntimeError:
            pass
        
        try:
            if self.fadeout_timer and self.fadeout_timer.isActive():
                self.fadeout_timer.stop()
        except RuntimeError:
            pass
        
        try:
            if self.current_flash_timer and self.current_flash_timer.isActive():
                self.current_flash_timer.stop()
        except (RuntimeError, AttributeError):
            pass

    def show_toast(self, title, message, duration=3500, icon_type="info"):
        """Show the toast notification with animation
        
        Args:
            title: Title text
            message: Message content
            duration: Display duration in milliseconds
            icon_type: Type of icon to show ("recording", "success", "info")
        """
        # First close any existing toast
        self.force_close()
        
        # Log that we're about to show a toast - sanitize message for logging
        safe_message = message.encode('ascii', 'replace').decode('ascii')
        logger.info(f"Showing toast notification: {title} - {safe_message}")
        self.is_active = True
        
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.set_icon(icon_type)
        
        # Use smaller fixed size for quicker reading
        self.setFixedSize(300, 80)
        
        # Position in the bottom-right corner of the screen
        screen_rect = QApplication.primaryScreen().availableGeometry()
        
        # On macOS, position slightly higher to avoid the Dock
        if platform.system() == 'Darwin':
            toast_x = screen_rect.right() - self.width() - 20  # 20px from right edge
            toast_y = screen_rect.bottom() - self.height() - 40  # 40px from bottom edge to avoid Dock
        else:
            toast_x = screen_rect.right() - self.width() - 20  # 20px from right edge
            toast_y = screen_rect.bottom() - self.height() - 20  # 20px from bottom edge
        
        self.move(toast_x, toast_y)
        
        # Set initial opacity for animation
        self.setWindowOpacity(0.0)
        
        # Show toast and force it to be visible
        self.show()
        self.raise_()
        
        # Start appearance animation
        self.animation_step = 0
        self.animation_timer.start(30)
        
        # Start auto-hide timer
        self.hide_timer.start(duration)
        
        # Log for debugging
        logger.info(f"Toast notification displayed (duration: {duration}ms)")

    def _safe_hide(self):
        """Safe wrapper for hide that handles re-entry."""
        if not self._is_closing:
            self.hide()
    
    def hide(self):
        """Override hide to track state and add fade-out animation"""
        if self._is_closing:
            return
        
        self._is_closing = True
        self._stop_all_timers()
        
        # Start async fade-out animation
        self.fadeout_step_count = 0
        self._fadeout_step()
    
    def _fadeout_step(self):
        """Perform one step of the fadeout animation."""
        opacity_levels = [0.8, 0.6, 0.4, 0.2, 0.0]
        
        if self.fadeout_step_count < len(opacity_levels):
            try:
                self.setWindowOpacity(opacity_levels[self.fadeout_step_count])
                self.fadeout_step_count += 1
                # Schedule next step
                self.fadeout_timer.start(20)  # 20ms between steps
            except RuntimeError:
                # Widget may have been deleted
                self._finish_hide()
        else:
            self._finish_hide()
    
    def _finish_hide(self):
        """Complete the hide operation."""
        try:
            super().hide()
        except RuntimeError:
            pass  # Widget may have been deleted
        finally:
            self.is_active = False
            self._is_closing = False
            logger.debug("Toast hidden")
    
    def cleanup(self):
        """Clean up all resources. Call this before application shutdown."""
        logger.debug("Cleaning up CustomToast resources")
        self._stop_all_timers()
        self.is_active = False
        self._is_closing = False
        
        # Explicitly delete timers
        try:
            self.hide_timer.deleteLater()
        except (RuntimeError, AttributeError):
            pass
        
        try:
            self.animation_timer.deleteLater()
        except (RuntimeError, AttributeError):
            pass
        
        try:
            self.fadeout_timer.deleteLater()
        except (RuntimeError, AttributeError):
            pass
    
    def closeEvent(self, event):
        """Handle close event to ensure proper cleanup."""
        self._stop_all_timers()
        super().closeEvent(event)