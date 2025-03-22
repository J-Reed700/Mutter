from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel)

class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Recorder Settings")
        self.setMinimumSize(400, 300)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Add some placeholder content
        layout.addWidget(QLabel("Hotkey Settings (Coming Soon)"))
        layout.addWidget(QLabel("Recording Settings (Coming Soon)"))
        
        # Add a close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button) 