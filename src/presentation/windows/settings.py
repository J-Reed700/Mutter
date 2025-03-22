from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QComboBox, QTabWidget,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QKeySequenceEdit, QDialog, QSlider, QFrame,
    QApplication, QStyle, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QKeySequence, QFont, QIcon, QPixmap
import sounddevice as sd
import logging
from pathlib import Path

from ...domain.settings import Settings
from ...infrastructure.persistence.settings_repository import SettingsRepository
from ..theme import AppTheme

logger = logging.getLogger(__name__)

class SettingsWindow(QMainWindow):
    def __init__(self, settings: Settings, settings_repository: SettingsRepository):
        super().__init__()
        self.settings = settings
        self.settings_repository = settings_repository
        
        self.setWindowTitle("Voice Recorder Settings")
        self.setMinimumSize(600, 500)
        
        # Set window icon if available
        icon_path = Path(__file__).parent.parent.parent.parent / "resources" / "images" / "microphone.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with title and version
        header_layout = QHBoxLayout()
        title_label = QLabel("Voice Recorder Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        version_label = QLabel("v1.0.0")  # Update with your actual version
        version_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(version_label)
        
        layout.addLayout(header_layout)
        
        # Add a separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Add tabs
        tabs.addTab(self._create_hotkeys_tab(), "Hotkeys")
        tabs.addTab(self._create_audio_tab(), "Audio")
        tabs.addTab(self._create_transcription_tab(), "Transcription")
        tabs.addTab(self._create_llm_tab(), "LLM Processing")
        tabs.addTab(self._create_appearance_tab(), "Appearance")
        
        # Add bottom buttons
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)
        
        # Add quit button on the left
        quit_button = QPushButton("Quit Application")
        quit_button.setStyleSheet(f"background-color: {AppTheme.ACCENT}; color: white;")
        quit_button.clicked.connect(self._quit_application)
        button_layout.addWidget(quit_button)
        
        # Add spacer to push buttons to the right
        button_layout.addStretch()
        
        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("background-color: #e0e0e0; color: #333333;")
        cancel_button.clicked.connect(self.close)
        button_layout.addWidget(cancel_button)
        
        # Save button
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(save_button)
    
    def _create_hotkeys_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Help text at the top
        help_label = QLabel(
            "Configure keyboard shortcuts for recording. "
            "Press the key combination you want to use."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Record hotkey
        record_group = QGroupBox("Recording Hotkey")
        record_layout = QFormLayout(record_group)
        record_layout.setContentsMargins(15, 20, 15, 15)
        record_layout.setSpacing(10)
        
        self.record_hotkey_edit = QKeySequenceEdit(
            self.settings.hotkeys.record_key
        )
        self.record_hotkey_edit.setMinimumWidth(200)
        record_layout.addRow("Record Key:", self.record_hotkey_edit)
        
        # Add a description
        record_desc = QLabel("Press this key combination to start recording")
        record_desc.setStyleSheet("color: #666666; font-size: 12px;")
        record_layout.addRow("", record_desc)
        
        layout.addWidget(record_group)
        
        # Pause hotkey
        pause_group = QGroupBox("Pause Hotkey (Optional)")
        pause_layout = QFormLayout(pause_group)
        pause_layout.setContentsMargins(15, 20, 15, 15)
        pause_layout.setSpacing(10)
        
        self.pause_hotkey_edit = QKeySequenceEdit(
            self.settings.hotkeys.pause_key or QKeySequence()
        )
        self.pause_hotkey_edit.setMinimumWidth(200)
        pause_layout.addRow("Pause Key:", self.pause_hotkey_edit)
        
        # Add a description
        pause_desc = QLabel("Press this key combination to pause/resume recording")
        pause_desc.setStyleSheet("color: #666666; font-size: 12px;")
        pause_layout.addRow("", pause_desc)
        
        layout.addWidget(pause_group)
        
        # Process text hotkey
        process_group = QGroupBox("Process Text Hotkey")
        process_layout = QFormLayout(process_group)
        process_layout.setContentsMargins(15, 20, 15, 15)
        process_layout.setSpacing(10)
        
        self.process_hotkey_edit = QKeySequenceEdit(
            self.settings.hotkeys.process_text_key or QKeySequence("Ctrl+Shift+P")
        )
        self.process_hotkey_edit.setMinimumWidth(200)
        process_layout.addRow("Process Text Key:", self.process_hotkey_edit)
        
        # Add a description
        process_desc = QLabel("Press this key combination to process transcribed text with LLM")
        process_desc.setStyleSheet("color: #666666; font-size: 12px;")
        process_layout.addRow("", process_desc)
        
        layout.addWidget(process_group)
        
        layout.addStretch()
        
        return widget
    
    def _create_audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Help text at the top
        help_label = QLabel(
            "Configure audio recording settings. Higher quality settings use more disk space "
            "and may require more processing power."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Audio device selection
        device_group = QGroupBox("Audio Device")
        device_layout = QFormLayout(device_group)
        device_layout.setContentsMargins(15, 20, 15, 15)
        device_layout.setSpacing(10)
        
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(300)
        self._populate_audio_devices()
        device_layout.addRow("Input Device:", self.device_combo)
        
        # Refresh button
        refresh_button = QPushButton("Refresh Devices")
        refresh_button.setStyleSheet("padding: 5px 10px;")
        refresh_button.clicked.connect(self._populate_audio_devices)
        device_layout.addRow("", refresh_button)
        
        layout.addWidget(device_group)
        
        # Audio settings
        settings_group = QGroupBox("Recording Settings")
        settings_layout = QFormLayout(settings_group)
        settings_layout.setContentsMargins(15, 20, 15, 15)
        settings_layout.setSpacing(10)
        
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.setMinimumWidth(200)
        for rate in [8000, 16000, 44100, 48000]:
            self.sample_rate_combo.addItem(f"{rate} Hz", rate)
        self.sample_rate_combo.setCurrentText(f"{self.settings.audio.sample_rate} Hz")
        settings_layout.addRow("Sample Rate:", self.sample_rate_combo)
        
        # Add a sample rate description
        sample_rate_desc = QLabel("Higher sample rates provide better audio quality")
        sample_rate_desc.setStyleSheet("color: #666666; font-size: 12px;")
        settings_layout.addRow("", sample_rate_desc)
        
        self.channels_spin = QSpinBox()
        self.channels_spin.setRange(1, 2)
        self.channels_spin.setValue(self.settings.audio.channels)
        settings_layout.addRow("Channels:", self.channels_spin)
        
        # Add a channels description
        channels_desc = QLabel("1 = Mono, 2 = Stereo")
        channels_desc.setStyleSheet("color: #666666; font-size: 12px;")
        settings_layout.addRow("", channels_desc)
        
        layout.addWidget(settings_group)
        layout.addStretch()
        
        return widget
    
    def _create_transcription_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Help text at the top
        help_label = QLabel(
            "Configure transcription settings. Larger models provide better accuracy "
            "but use more memory and CPU/GPU resources."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Model settings
        model_group = QGroupBox("Whisper Model")
        model_layout = QFormLayout(model_group)
        model_layout.setContentsMargins(15, 20, 15, 15)
        model_layout.setSpacing(10)
        
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        for model in ['tiny', 'base', 'small', 'medium', 'large']:
            self.model_combo.addItem(model)
        self.model_combo.setCurrentText(self.settings.transcription.model)
        model_layout.addRow("Model Size:", self.model_combo)
        
        # Add a model description
        model_desc = QLabel("Larger models are more accurate but use more resources")
        model_desc.setStyleSheet("color: #666666; font-size: 12px;")
        model_layout.addRow("", model_desc)
        
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(['cpu', 'cuda'])
        self.device_type_combo.setCurrentText(self.settings.transcription.device)
        model_layout.addRow("Device:", self.device_type_combo)
        
        # Add a device description
        device_desc = QLabel("CPU is compatible with all systems, CUDA requires NVIDIA GPU")
        device_desc.setStyleSheet("color: #666666; font-size: 12px;")
        model_layout.addRow("", device_desc)
        
        layout.addWidget(model_group)
        
        # Language settings
        lang_group = QGroupBox("Language")
        lang_layout = QFormLayout(lang_group)
        lang_layout.setContentsMargins(15, 20, 15, 15)
        lang_layout.setSpacing(10)
        
        self.language_combo = QComboBox()
        self.language_combo.setMinimumWidth(200)
        languages = [
            ('auto', 'Auto-detect'),
            ('en', 'English'),
            ('es', 'Spanish'),
            ('fr', 'French'),
            ('de', 'German'),
            ('it', 'Italian'),
            ('pt', 'Portuguese'),
            ('nl', 'Dutch'),
            ('pl', 'Polish'),
            ('ru', 'Russian'),
            ('zh', 'Chinese'),
            ('ja', 'Japanese'),
            ('ko', 'Korean')
        ]
        for code, name in languages:
            self.language_combo.addItem(name, code)
            if code == self.settings.transcription.language:
                self.language_combo.setCurrentText(name)
        
        lang_layout.addRow("Language:", self.language_combo)
        
        # Add a language description
        lang_desc = QLabel("Select the language for transcription or let Whisper auto-detect")
        lang_desc.setStyleSheet("color: #666666; font-size: 12px;")
        lang_layout.addRow("", lang_desc)
        
        layout.addWidget(lang_group)
        layout.addStretch()
        
        return widget
    
    def _create_llm_tab(self) -> QWidget:
        """Create the LLM settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Help text at the top
        help_label = QLabel(
            "Configure the local LLM processing for transcriptions. "
            "This requires a local LLM server running."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # LLM Enable/Disable
        enable_group = QGroupBox("Enable LLM Processing")
        enable_layout = QFormLayout(enable_group)
        enable_layout.setContentsMargins(15, 20, 15, 15)
        enable_layout.setSpacing(10)
        
        self.llm_enabled_check = QCheckBox("Enable LLM processing")
        self.llm_enabled_check.setChecked(self.settings.llm.enabled)
        self.llm_enabled_check.toggled.connect(self._on_llm_enabled_toggled)
        enable_layout.addRow("", self.llm_enabled_check)
        
        enable_desc = QLabel("Process transcriptions with a local LLM server")
        enable_desc.setStyleSheet("color: #666666; font-size: 12px;")
        enable_layout.addRow("", enable_desc)
        
        layout.addWidget(enable_group)
        
        # LLM Server Settings
        server_group = QGroupBox("LLM Server Settings")
        server_layout = QFormLayout(server_group)
        server_layout.setContentsMargins(15, 20, 15, 15)
        server_layout.setSpacing(10)
        
        self.llm_api_url_edit = QComboBox()
        self.llm_api_url_edit.setEditable(True)
        self.llm_api_url_edit.setMinimumWidth(300)
        self.llm_api_url_edit.addItems([
            "http://localhost:8080/v1",
            "http://localhost:11434/v1",
            "http://localhost:5000/v1",
        ])
        self.llm_api_url_edit.setCurrentText(self.settings.llm.api_url)
        server_layout.addRow("API URL:", self.llm_api_url_edit)
        
        self.llm_model_edit = QComboBox()
        self.llm_model_edit.setEditable(True)
        self.llm_model_edit.setMinimumWidth(200)
        self.llm_model_edit.addItems([
            "llama3",
            "mistral",
            "codellama",
            "phi3",
            "mixtral"
        ])
        self.llm_model_edit.setCurrentText(self.settings.llm.model)
        server_layout.addRow("Model:", self.llm_model_edit)
        
        # Test LLM Connection button
        test_button = QPushButton("Test Connection")
        test_button.setStyleSheet("padding: 5px 10px;")
        test_button.clicked.connect(self._test_llm_connection)
        server_layout.addRow("", test_button)
        
        layout.addWidget(server_group)
        
        # LLM Processing Settings
        processing_group = QGroupBox("Processing Settings")
        processing_layout = QFormLayout(processing_group)
        processing_layout.setContentsMargins(15, 20, 15, 15)
        processing_layout.setSpacing(10)
        
        self.processing_type_combo = QComboBox()
        self.processing_type_combo.addItem("Summarize", "summarize")
        self.processing_type_combo.addItem("Extract Action Items", "action_items")
        self.processing_type_combo.addItem("Key Points", "key_points")
        self.processing_type_combo.addItem("Custom Prompt", "custom")
        
        # Set current item based on settings
        for i in range(self.processing_type_combo.count()):
            if self.processing_type_combo.itemData(i) == self.settings.llm.default_processing_type:
                self.processing_type_combo.setCurrentIndex(i)
                break
                
        processing_layout.addRow("Default Processing:", self.processing_type_combo)
        
        # Custom prompt text edit
        custom_prompt_desc = QLabel("You can use {text} as a placeholder for the transcribed text")
        custom_prompt_desc.setStyleSheet("color: #666666; font-size: 12px;")
        processing_layout.addRow("", custom_prompt_desc)
        
        layout.addWidget(processing_group)
        
        # Disable the settings if LLM is not enabled
        server_group.setEnabled(self.settings.llm.enabled)
        processing_group.setEnabled(self.settings.llm.enabled)
        
        layout.addStretch()
        
        return widget
    
    def _create_appearance_tab(self) -> QWidget:
        """Create the appearance settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Help text at the top
        help_label = QLabel("Customize the appearance and behavior of the application.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Notification settings
        notif_group = QGroupBox("Notifications")
        notif_layout = QFormLayout(notif_group)
        notif_layout.setContentsMargins(15, 20, 15, 15)
        notif_layout.setSpacing(10)
        
        self.show_notif_check = QCheckBox("Show notifications")
        self.show_notif_check.setChecked(True)  # Default to true
        notif_layout.addRow("", self.show_notif_check)
        
        self.clipboard_check = QCheckBox("Auto-copy transcription to clipboard")
        self.clipboard_check.setChecked(False)  # Default to false
        notif_layout.addRow("", self.clipboard_check)
        
        layout.addWidget(notif_group)
        
        # Theme settings (for future implementation)
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)
        theme_layout.setContentsMargins(15, 20, 15, 15)
        theme_layout.setSpacing(10)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(['Light', 'Dark', 'System'])
        self.theme_combo.setCurrentText('Light')  # Default
        theme_layout.addRow("Theme:", self.theme_combo)
        
        # Add a theme description
        theme_desc = QLabel("Theme changes will apply after restart")
        theme_desc.setStyleSheet("color: #666666; font-size: 12px;")
        theme_layout.addRow("", theme_desc)
        
        layout.addWidget(theme_group)
        layout.addStretch()
        
        return widget
    
    def _populate_audio_devices(self):
        """Populate the audio devices combo box"""
        devices = sd.query_devices()
        self.device_combo.clear()
        
        # Add default device
        self.device_combo.addItem("Default", "default")
        
        # Add input devices
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                name = f"{dev['name']} ({dev['max_input_channels']} channels)"
                self.device_combo.addItem(name, dev['name'])
                
                if dev['name'] == self.settings.audio.input_device:
                    self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
    
    @Slot()
    def _save_settings(self):
        """Save the current settings"""
        # Update hotkey settings
        self.settings.hotkeys.record_key = self.record_hotkey_edit.keySequence()
        pause_seq = self.pause_hotkey_edit.keySequence()
        self.settings.hotkeys.pause_key = pause_seq if not pause_seq.isEmpty() else None
        process_seq = self.process_hotkey_edit.keySequence()
        self.settings.hotkeys.process_text_key = process_seq if not process_seq.isEmpty() else None
        
        # Update audio settings
        self.settings.audio.input_device = self.device_combo.currentData()
        self.settings.audio.sample_rate = self.sample_rate_combo.currentData()
        self.settings.audio.channels = self.channels_spin.value()
        
        # Update transcription settings
        self.settings.transcription.model = self.model_combo.currentText()
        self.settings.transcription.device = self.device_type_combo.currentText()
        self.settings.transcription.language = self.language_combo.currentData()
        
        # Update LLM settings
        self.settings.llm.enabled = self.llm_enabled_check.isChecked()
        self.settings.llm.api_url = self.llm_api_url_edit.currentText()
        self.settings.llm.model = self.llm_model_edit.currentText()
        self.settings.llm.default_processing_type = self.processing_type_combo.currentData()
        
        # Save appearance settings
        # TODO: Store appearance settings to the settings object
        
        # Save to file
        self.settings_repository.save(self.settings)
        
        # Close the window
        self.close()

    def _quit_application(self):
        """Quit the application with confirmation"""
        confirm = QMessageBox.question(
            self,
            "Quit Application",
            "Are you sure you want to quit the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            QApplication.quit()

    def _on_llm_enabled_toggled(self, enabled):
        """Handle LLM enabled checkbox toggle"""
        # Find the LLM tab widgets
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if isinstance(widget, QTabWidget):
                tab_widget = widget
                # Find the LLM tab
                for j in range(tab_widget.count()):
                    if tab_widget.tabText(j) == "LLM Processing":
                        llm_tab = tab_widget.widget(j)
                        # Enable/disable all group boxes except the first one
                        for k in range(llm_tab.layout().count()):
                            item = llm_tab.layout().itemAt(k)
                            if item and item.widget() and isinstance(item.widget(), QGroupBox):
                                if k > 0:  # Skip the first group box (enable/disable)
                                    item.widget().setEnabled(enabled)
    
    def _test_llm_connection(self):
        """Test the LLM server connection"""
        from ...infrastructure.llm.processor import TextProcessor
        
        cursor = self.cursor()
        cursor.setShape(Qt.WaitCursor)
        self.setCursor(cursor)
        
        try:
            processor = TextProcessor(api_url=self.llm_api_url_edit.currentText())
            if processor.available:
                models = processor.get_available_models()
                if models:
                    QMessageBox.information(
                        self,
                        "Connection Successful",
                        f"Successfully connected to LLM server.\nAvailable models: {', '.join(models[:5])}",
                        QMessageBox.Ok
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Connection Successful",
                        "Successfully connected to LLM server, but no models found.",
                        QMessageBox.Ok
                    )
            else:
                QMessageBox.warning(
                    self,
                    "Connection Failed",
                    "Could not connect to LLM server. Please check the API URL and ensure the server is running.",
                    QMessageBox.Ok
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Error connecting to LLM server: {str(e)}",
                QMessageBox.Ok
            )
        finally:
            cursor.setShape(Qt.ArrowCursor)
            self.setCursor(cursor)

class SettingsDialog(QDialog):
    hotkey_changed = Signal(object)  # Emits QKeySequence

    def __init__(self, parent=None, settings=None, settings_repository=None):
        super().__init__(parent)
        self.settings = settings
        self.settings_repository = settings_repository
        self.setWindowTitle("Voice Recorder Settings")
        self.setMinimumWidth(400)
        
        # Set window icon if available
        icon_path = Path(__file__).parent.parent.parent.parent / "resources" / "images" / "microphone.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Add title label
        title_label = QLabel("Recording Hotkey Settings")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Add description
        desc_label = QLabel(
            "Configure the hotkey used for recording. Press the key combination you want to use."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Add a separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Hotkey section
        hotkey_layout = QFormLayout()
        hotkey_layout.setContentsMargins(0, 10, 0, 10)
        hotkey_layout.setSpacing(10)
        
        hotkey_label = QLabel("Recording Hotkey:")
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMinimumWidth(200)
        self.hotkey_edit.editingFinished.connect(self._on_hotkey_changed)
        hotkey_layout.addRow(hotkey_label, self.hotkey_edit)
        
        # Add a note
        note_label = QLabel("Note: The hotkey works globally across all applications")
        note_label.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; font-size: {AppTheme.FONT_SIZE_SMALL}pt;")
        hotkey_layout.addRow("", note_label)
        
        layout.addLayout(hotkey_layout)
        
        # Add spacer
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Add quit button on the left
        quit_button = QPushButton("Quit Application")
        quit_button.setStyleSheet(f"background-color: {AppTheme.ACCENT}; color: white;")
        quit_button.clicked.connect(self._quit_application)
        button_layout.addWidget(quit_button)
        
        # Add spacer to push OK/Cancel buttons to the right
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("background-color: #e0e0e0; color: #333333;")
        
        ok_button = QPushButton("OK")
        
        cancel_button.clicked.connect(self.reject)
        ok_button.clicked.connect(self.accept)
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)

    def _quit_application(self):
        """Quit the application with confirmation"""
        confirm = QMessageBox.question(
            self,
            "Quit Application",
            "Are you sure you want to quit the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            QApplication.quit()
        
    def _on_hotkey_changed(self):
        """Handle hotkey changes"""
        new_sequence = self.hotkey_edit.keySequence()
        self.hotkey_changed.emit(new_sequence)
        logger.debug(f"Hotkey changed to: {new_sequence.toString()}")

    def set_current_hotkey(self, key_sequence):
        """Set the current hotkey in the editor"""
        self.hotkey_edit.setKeySequence(key_sequence) 