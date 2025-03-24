import logging
from pathlib import Path
from typing import Dict, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QProgressBar, QScrollArea, 
    QFrame, QApplication, QListWidget, QListWidgetItem,
    QDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QMutex, QDateTime
from PySide6.QtGui import QIcon, QFont

from ..theme import AppTheme

logger = logging.getLogger(__name__)

class DownloadManagerWindow(QMainWindow):
    """Window that displays all current model downloads and their status"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Model Downloads")
        self.setMinimumSize(500, 400)
        
        # Set window icon if available
        icon_path = Path(__file__).parent.parent.parent.parent / "resources" / "images" / "microphone.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Dictionary to store download progress for each model
        self._downloads: Dict[str, Dict] = {}
        self._downloads_mutex = QMutex()
        
        # Setup UI
        self._setup_ui()
        
        # Setup a timer to periodically refresh the UI
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._update_download_list)
        self._refresh_timer.start(1000)  # Update every second
    
    def _setup_ui(self):
        """Set up the main UI components"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with title
        header_layout = QHBoxLayout()
        title_label = QLabel("Model Downloads")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        layout.addLayout(header_layout)
        
        # Add a separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Help text explaining what this window is for
        help_label = QLabel(
            "This window shows the current status of model downloads. "
            "Downloads can happen in the background while you use other "
            "features of the application."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Create a scroll area for downloads
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.scroll_area)
        
        # Create container widget for downloads
        self.downloads_container = QWidget()
        self.downloads_layout = QVBoxLayout(self.downloads_container)
        self.scroll_area.setWidget(self.downloads_container)
        
        # Add a "No downloads" message (will be hidden when downloads exist)
        self.no_downloads_label = QLabel("No active downloads")
        self.no_downloads_label.setAlignment(Qt.AlignCenter)
        self.no_downloads_label.setStyleSheet("color: #888888; font-size: 14px; padding: 20px;")
        self.downloads_layout.addWidget(self.no_downloads_label)
        
        # Add bottom buttons
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)
        
        # Add spacer to push buttons to the right
        button_layout.addStretch()
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
    
    def update_download_progress(self, model_name: str, message: str, progress: float):
        """Update the progress for a model download
        
        Args:
            model_name: Name of the model being downloaded
            message: Status message to display
            progress: Progress percentage (0-100) or negative for error
        """
        # Log the update
        logger.debug(f"Received download update: {model_name} - {progress:.1f}% - {message}")
        
        # Update download info in our dictionary
        self._downloads_mutex.lock()
        try:
            current_time = QDateTime.currentMSecsSinceEpoch()
            
            # Add new download or update existing one
            if model_name not in self._downloads:
                logger.info(f"Adding new download to UI: {model_name}")
                self._downloads[model_name] = {
                    "message": message,
                    "progress": progress,
                    "updated_at": current_time
                }
            else:
                logger.debug(f"Updating existing download: {model_name}")
                self._downloads[model_name]["message"] = message
                self._downloads[model_name]["progress"] = progress
                self._downloads[model_name]["updated_at"] = current_time
                
            # If download completed or errored, schedule it for removal after a delay
            if progress >= 100 or progress < 0:
                # Remove after 10 seconds (10000 msecs)
                self._downloads[model_name]["remove_after"] = current_time + 10000
        finally:
            self._downloads_mutex.unlock()
        
        # Force an immediate UI update instead of waiting for the timer
        self._update_download_list()
        
        # Ensure window is visible if we have active downloads
        if not self.isVisible() and len(self._downloads) > 0:
            # Only automatically show for new downloads, not updates
            if model_name not in self._downloads:
                logger.info(f"Automatically showing download window for new download: {model_name}")
                self.show()
                self.raise_()
    
    def _update_download_list(self):
        """Update the download list UI from the current downloads dictionary"""
        self._downloads_mutex.lock()
        try:
            # Check if we need to remove any completed downloads
            current_time = QDateTime.currentMSecsSinceEpoch()
            models_to_remove = []
            for model_name, download_info in self._downloads.items():
                if "remove_after" in download_info and current_time > download_info["remove_after"]:
                    models_to_remove.append(model_name)
            
            # Remove expired downloads
            for model_name in models_to_remove:
                del self._downloads[model_name]
            
            # Clear existing widgets in the layout
            while self.downloads_layout.count() > 0:
                item = self.downloads_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # Add widgets for each download
            if not self._downloads:
                # Show "No downloads" message if there are no downloads
                self.no_downloads_label = QLabel("No active downloads")
                self.no_downloads_label.setAlignment(Qt.AlignCenter)
                self.no_downloads_label.setStyleSheet("color: #888888; font-size: 14px; padding: 20px;")
                self.downloads_layout.addWidget(self.no_downloads_label)
            else:
                # Add each download
                for model_name, download_info in self._downloads.items():
                    self._add_download_widget(model_name, download_info)
            
            # Add stretch at the end to push everything to the top
            self.downloads_layout.addStretch()
        finally:
            self._downloads_mutex.unlock()
    
    def _add_download_widget(self, model_name: str, download_info: Dict):
        """Add or update a widget for a download
        
        Args:
            model_name: Name of the model
            download_info: Dictionary with download info
        """
        # Create a frame for this download
        download_frame = QFrame()
        download_frame.setFrameShape(QFrame.StyledPanel)
        download_frame.setStyleSheet("QFrame { border: 1px solid #cccccc; border-radius: 5px; padding: 10px; margin: 5px; }")
        
        # Layout for this download
        download_layout = QVBoxLayout(download_frame)
        download_layout.setContentsMargins(10, 10, 10, 10)
        download_layout.setSpacing(5)
        
        # Model name
        name_label = QLabel(model_name)
        name_font = QFont()
        name_font.setBold(True)
        name_label.setFont(name_font)
        download_layout.addWidget(name_label)
        
        # Status message
        message_label = QLabel(download_info["message"])
        message_label.setWordWrap(True)
        download_layout.addWidget(message_label)
        
        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        
        # Set progress and style based on status
        progress = download_info["progress"]
        if progress < 0:
            # Error
            progress_bar.setStyleSheet("QProgressBar { color: white; background-color: #ffaaaa; } QProgressBar::chunk { background-color: #ff6666; }")
            progress_bar.setFormat("Error")
            progress_bar.setValue(0)
        elif progress >= 100:
            # Complete
            progress_bar.setStyleSheet("QProgressBar { color: white; background-color: #aaffaa; } QProgressBar::chunk { background-color: #66ff66; }")
            progress_bar.setFormat("Complete")
            progress_bar.setValue(100)
        else:
            # In progress
            progress_bar.setStyleSheet("")
            progress_bar.setFormat("%p%")
            progress_bar.setValue(int(progress))
        
        download_layout.addWidget(progress_bar)
        
        # Add this download frame to the main layout
        self.downloads_layout.addWidget(download_frame)
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Don't actually remove downloads when closing, just hide the window
        event.accept() 