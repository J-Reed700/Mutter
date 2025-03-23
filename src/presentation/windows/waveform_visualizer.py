from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsView, QGraphicsScene, QHBoxLayout, QGraphicsPathItem
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF
from PySide6.QtGui import QPen, QColor, QPainterPath, QLinearGradient, QBrush, QFont, QPainter
import numpy as np
import logging

logger = logging.getLogger(__name__)

class WaveformVisualizerWindow(QWidget):
    """A modern, sleek window that visualizes audio waveforms in real-time during recording."""
    
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.Tool)
        
        # Set window properties
        self.setWindowTitle("Recording Waveform")
        self.setMinimumSize(480, 220)
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d3b;
                color: #ffffff;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-size: 13px;
            }
        """)
        
        # Visual properties
        self.waveform_color = QColor(48, 209, 88)  # Vibrant green
        self.waveform_base_color = QColor(32, 139, 58)  # Darker green
        self.background_color = QColor(45, 45, 59)
        self.grid_color = QColor(80, 80, 95, 80)
        
        # Audio data properties
        self.audio_data = None
        self.max_amplitude = 0.01  # Prevent division by zero
        self.sample_rate = 16000
        self.duration = 0
        
        # Set up the UI
        self._setup_ui()
        
        # Setup update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_waveform)
        
        # Don't start timer yet - will start when we get data
        
    def _setup_ui(self):
        """Set up the UI elements"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Title and time display
        header_layout = QHBoxLayout()
        
        # Title
        self.title_label = QLabel("Recording")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        
        # Time display
        self.time_label = QLabel("00:00")
        time_font = QFont()
        time_font.setPointSize(14)
        self.time_label.setFont(time_font)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.time_label)
        layout.addLayout(header_layout)
        
        # Waveform display
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(self.background_color)
        
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setFrameShape(QGraphicsView.NoFrame)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Create the waveform path
        self.waveform_path = QGraphicsPathItem()
        
        # Create a gradient for the waveform
        gradient = QLinearGradient(0, -50, 0, 50)
        gradient.setColorAt(0, self.waveform_color)
        gradient.setColorAt(1, self.waveform_base_color)
        
        # Set pen and brush
        pen = QPen(self.waveform_color, 1.5)
        self.waveform_path.setPen(pen)
        self.waveform_path.setBrush(QBrush(gradient))
        
        self.scene.addItem(self.waveform_path)
        layout.addWidget(self.view)
        
        # Status label
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
    
    def _draw_grid(self):
        """Draw a subtle grid in the background"""
        # Clear existing grid lines
        for item in self.scene.items():
            if item != self.waveform_path:
                self.scene.removeItem(item)
        
        rect = self.view.viewport().rect()
        scene_rect = QRectF(0, -50, rect.width(), 100)
        self.scene.setSceneRect(scene_rect)
        
        # Draw horizontal grid lines
        pen = QPen(self.grid_color, 1, Qt.DashLine)
        for y in [-40, -20, 0, 20, 40]:
            line = self.scene.addLine(0, y, rect.width(), y, pen)
        
        # Draw vertical grid lines
        for x in range(0, rect.width(), 40):
            line = self.scene.addLine(x, -50, x, 50, pen)
    
    def _update_waveform(self):
        """Update the waveform visualization with latest data"""
        if not hasattr(self, 'audio_data') or self.audio_data is None or len(self.audio_data) == 0:
            return
        
        # Update time display
        total_seconds = len(self.audio_data) / self.sample_rate
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")
        
        # Update status
        audio_mean = np.mean(np.abs(self.audio_data))
        if audio_mean < 0.01:
            self.status_label.setText("Audio level: Very quiet")
        elif audio_mean < 0.05:
            self.status_label.setText("Audio level: Low")
        elif audio_mean < 0.2:
            self.status_label.setText("Audio level: Good")
        else:
            self.status_label.setText("Audio level: High")
        
        # Update viewport dimensions
        rect = self.view.viewport().rect()
        width = rect.width()
        height = rect.height()
        
        # Ensure we have reasonable dimensions
        if width <= 10 or height <= 10:
            return
        
        # Prepare path
        path = QPainterPath()
        
        # Determine number of samples to display and how to downsample
        num_display_points = width
        
        if len(self.audio_data) == 0:
            return
            
        # Downsample data to fit the display width
        if len(self.audio_data) > num_display_points:
            # Calculate points per pixel
            samples_per_point = max(1, len(self.audio_data) // num_display_points)
            
            # Reshape audio data to calculate min/max per segment
            remainder = len(self.audio_data) % samples_per_point
            if remainder > 0:
                # Pad the array to make it divisible by samples_per_point
                pad_size = samples_per_point - remainder
                padded_data = np.pad(self.audio_data, (0, pad_size), 'constant')
            else:
                padded_data = self.audio_data
                
            # Reshape and get min/max values
            segments = padded_data.reshape(-1, samples_per_point)
            mins = np.min(segments, axis=1)
            maxs = np.max(segments, axis=1)
            
            # Update max amplitude for normalization
            self.max_amplitude = max(self.max_amplitude, np.max(np.abs(self.audio_data)))
            
            # Start path at the left with first min value
            path.moveTo(0, 50 * mins[0] / self.max_amplitude)
            
            # Add points for each segment
            for i, (min_val, max_val) in enumerate(zip(mins, maxs)):
                x = i
                # Normalize values to fit in the view
                y_min = 50 * min_val / self.max_amplitude
                y_max = 50 * max_val / self.max_amplitude
                
                # Draw vertical line for this segment
                path.lineTo(x, y_max)
                path.lineTo(x, y_min)
            
            # Close the path
            path.lineTo(num_display_points - 1, 0)
            path.closeSubpath()
        else:
            # If we have fewer samples than display width, just plot each sample
            x_scale = width / len(self.audio_data)
            
            # Update max amplitude for normalization
            self.max_amplitude = max(self.max_amplitude, np.max(np.abs(self.audio_data)))
            
            # Start path at the left
            path.moveTo(0, 0)
            
            # Add points for each sample
            for i, sample in enumerate(self.audio_data):
                x = i * x_scale
                # Normalize value to fit in the view (-50 to 50)
                y = 50 * sample / self.max_amplitude
                path.lineTo(x, y)
            
            # Close the path
            path.lineTo((len(self.audio_data) - 1) * x_scale, 0)
            path.closeSubpath()
        
        # Update the path
        self.waveform_path.setPath(path)
        
        # Update the scene rectangle
        self.scene.setSceneRect(0, -50, width, 100)
        
        # Redraw the grid
        self._draw_grid()
    
    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        # Redraw the grid when the window is resized
        self._draw_grid()
        # Update the waveform
        self._update_waveform()
    
    def showEvent(self, event):
        """Handle show events"""
        super().showEvent(event)
        # Start the timer when the window is shown
        self.update_timer.start(100)  # Update 10 times per second
        # Draw the initial grid
        self._draw_grid()
    
    def hideEvent(self, event):
        """Handle hide events"""
        super().hideEvent(event)
        # Stop the timer when the window is hidden
        self.update_timer.stop()
    
    @Slot(object)
    def update_audio_data(self, audio_data, sample_rate=None):
        """Update the audio data to be visualized
        
        Args:
            audio_data: numpy array of audio data
            sample_rate: sample rate of the audio (optional)
        """
        self.audio_data = audio_data
        if sample_rate:
            self.sample_rate = sample_rate
            
        # Make sure timer is running
        if not self.update_timer.isActive():
            self.update_timer.start(100)
        
        # Update the waveform
        self._update_waveform() 