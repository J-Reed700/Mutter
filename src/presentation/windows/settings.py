from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QComboBox, QTabWidget,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QKeySequenceEdit, QDialog, QSlider, QFrame,
    QApplication, QStyle, QSizePolicy, QMessageBox,
    QButtonGroup, QRadioButton
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
    # Add a signal to indicate settings were saved
    settings_saved = Signal()
    
    def __init__(self, settings: Settings, settings_repository: SettingsRepository):
        super().__init__()
        self.settings = settings
        self.settings_repository = settings_repository
        self.save_requested = False  # Track if Save button was clicked
        self.settings_changed = False  # Track if any settings were actually changed
        
        self.setWindowTitle("Memo Settings")
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
        title_label = QLabel("Memo Settings")
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
        self.record_hotkey_edit.editingFinished.connect(self._mark_settings_changed)
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
        self.pause_hotkey_edit.editingFinished.connect(self._mark_settings_changed)
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
        self.process_hotkey_edit.editingFinished.connect(self._mark_settings_changed)
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
        self.device_combo.setMinimumHeight(30)
        self._populate_audio_devices()
        
        # Mark settings changed but don't call _on_device_changed here to avoid adding duplicate rates
        self.device_combo.currentIndexChanged.connect(self._mark_settings_changed)
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
        self.sample_rate_combo.setMinimumHeight(30)
        for rate in [8000, 16000, 22050, 32000, 44100, 48000, 96000]:
            self.sample_rate_combo.addItem(f"{rate} Hz", rate)
        
        # Find and select the current sample rate
        for i in range(self.sample_rate_combo.count()):
            if self.sample_rate_combo.itemData(i) == self.settings.audio.sample_rate:
                self.sample_rate_combo.setCurrentIndex(i)
                break
        else:
            # If not found, add it
            self.sample_rate_combo.addItem(f"{self.settings.audio.sample_rate} Hz", self.settings.audio.sample_rate)
            self.sample_rate_combo.setCurrentIndex(self.sample_rate_combo.count() - 1)
        
        self.sample_rate_combo.currentIndexChanged.connect(self._mark_settings_changed)
        settings_layout.addRow("Sample Rate:", self.sample_rate_combo)
        
        # Add a sample rate description
        sample_rate_desc = QLabel("Higher sample rates provide better audio quality")
        sample_rate_desc.setStyleSheet("color: #666666; font-size: 12px;")
        settings_layout.addRow("", sample_rate_desc)
        
        self.channels_spin = QSpinBox()
        self.channels_spin.setRange(1, 2)
        self.channels_spin.setValue(self.settings.audio.channels)
        self.channels_spin.valueChanged.connect(self._mark_settings_changed)
        settings_layout.addRow("Channels:", self.channels_spin)
        
        # Add a channels description
        channels_desc = QLabel("1 = Mono, 2 = Stereo")
        channels_desc.setStyleSheet("color: #666666; font-size: 12px;")
        settings_layout.addRow("", channels_desc)
        
        layout.addWidget(settings_group)
        layout.addStretch()
        
        return widget
    
    def _create_transcription_tab(self) -> QWidget:
        """Create the transcription tab with all settings for speech recognition."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Model selection group
        model_group = QGroupBox("Transcription Model Settings")
        model_layout = QFormLayout(model_group)

        # Model dropdown
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_combo.setCurrentText(self.settings.transcription.model)
        self.model_combo.currentTextChanged.connect(self._mark_settings_changed)
        self.model_combo.setMinimumWidth(200)
        self.model_combo.setMinimumHeight(30)
        
        # Add tooltip to explain model sizes
        self.model_combo.setToolTip(
            "Model size affects accuracy and performance:\n"
            "- tiny: Fastest, lowest accuracy\n"
            "- base: Fast, moderate accuracy\n"
            "- small: Good balance of speed and accuracy\n"
            "- medium: Higher accuracy, slower\n"
            "- large: Best accuracy, slowest and uses most memory"
        )
        
        model_layout.addRow("Model Size:", self.model_combo)

        # Device selection
        self.device_type_combo = QComboBox()
        # Updated device options with descriptions
        device_options = [
            "cpu - Works on all computers", 
            "cuda - Requires NVIDIA GPU with CUDA libraries"
        ]
        self.device_type_combo.addItems(device_options)
        
        # Set the current device with the description
        current_device = "cpu - Works on all computers" if self.settings.transcription.device == "cpu" else "cuda - Requires NVIDIA GPU with CUDA libraries"
        self.device_type_combo.setCurrentText(current_device)
        
        self.device_type_combo.currentTextChanged.connect(self._mark_settings_changed)
        self.device_type_combo.setMinimumWidth(200)
        self.device_type_combo.setMinimumHeight(30)
        
        # Add tooltip to explain device options
        self.device_type_combo.setToolTip(
            "Select processing device:\n"
            "- CPU: Compatible with all computers, slower\n"
            "- CUDA: Requires NVIDIA GPU with CUDA libraries installed, much faster\n\n"
            "If CUDA libraries are missing, the application will fall back to CPU automatically."
        )
        
        model_layout.addRow("Processing Device:", self.device_type_combo)

        # Add model group to layout
        layout.addWidget(model_group)

        # Language selection group
        language_group = QGroupBox("Language Settings")
        language_layout = QFormLayout(language_group)

        # Language dropdown
        self.language_combo = QComboBox()
        languages = ["English", "Spanish", "French", "German", "Italian", "Portuguese", "Dutch", 
                     "Russian", "Arabic", "Chinese", "Japanese", "Korean", "Auto-detect"]
        self.language_combo.addItems(languages)
        self.language_combo.setCurrentText(self.settings.transcription.language or "English")
        self.language_combo.currentTextChanged.connect(self._mark_settings_changed)
        self.language_combo.setMinimumWidth(200)
        self.language_combo.setMinimumHeight(30)
        language_layout.addRow("Language:", self.language_combo)

        # Add language group to layout
        layout.addWidget(language_group)

        # Add spacer at the bottom
        layout.addStretch()

        return tab
    
    def _create_llm_tab(self) -> QWidget:
        """Create the LLM settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Help text at the top
        help_label = QLabel(
            "Configure LLM processing for transcriptions. "
            "You can use either the built-in LLM or connect to an external LLM server."
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
        self.llm_enabled_check.toggled.connect(self._mark_settings_changed)
        enable_layout.addRow("", self.llm_enabled_check)
        
        enable_desc = QLabel("Process transcriptions with an LLM to summarize or extract key points")
        enable_desc.setStyleSheet("color: #666666; font-size: 12px;")
        enable_layout.addRow("", enable_desc)
        
        layout.addWidget(enable_group)
        
        # LLM Mode selection (embedded vs external)
        mode_group = QGroupBox("LLM Mode")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setContentsMargins(15, 20, 15, 15)
        mode_layout.setSpacing(10)
        
        self.llm_mode_group = QButtonGroup(self)
        self.embedded_radio = QRadioButton("Use built-in LLM (no setup required)")
        self.external_radio = QRadioButton("Use external LLM server")
        
        # Set the initial state based on settings
        if hasattr(self.settings.llm, 'use_embedded_model'):
            self.embedded_radio.setChecked(self.settings.llm.use_embedded_model)
            self.external_radio.setChecked(not self.settings.llm.use_embedded_model)
        else:
            self.embedded_radio.setChecked(True)
            self.external_radio.setChecked(False)
        
        self.llm_mode_group.addButton(self.embedded_radio)
        self.llm_mode_group.addButton(self.external_radio)
        
        mode_layout.addWidget(self.embedded_radio)
        
        # Add embedded model selection
        embedded_settings = QWidget()
        embedded_layout = QFormLayout(embedded_settings)
        embedded_layout.setContentsMargins(20, 5, 5, 5)
        
        self.embedded_model_combo = QComboBox()
        self.embedded_model_combo.addItems([
            "distilbart-cnn-12-6",
            "sshleifer/distilbart-xsum-12-3",
            "facebook/bart-large-cnn",
            "philschmid/distilbart-cnn-12-6-samsum"
        ])
        self.embedded_model_combo.setMinimumWidth(300)
        self.embedded_model_combo.setMinimumHeight(30)
        # Set current embedded model
        if hasattr(self.settings.llm, 'embedded_model_name') and self.settings.llm.embedded_model_name:
            index = self.embedded_model_combo.findText(self.settings.llm.embedded_model_name)
            if index >= 0:
                self.embedded_model_combo.setCurrentIndex(index)
        
        self.embedded_model_combo.currentIndexChanged.connect(self._mark_settings_changed)
        
        embedded_layout.addRow("Model:", self.embedded_model_combo)
        
        embedded_desc = QLabel("Built-in models work immediately without additional setup but use more memory")
        embedded_desc.setStyleSheet("color: #666666; font-size: 12px;")
        embedded_desc.setWordWrap(True)
        embedded_layout.addRow("", embedded_desc)
        
        mode_layout.addWidget(embedded_settings)
        mode_layout.addWidget(self.external_radio)
        
        # Add external server settings
        server_settings = QWidget()
        server_layout = QFormLayout(server_settings)
        server_layout.setContentsMargins(20, 5, 5, 5)
        
        self.llm_api_url_edit = QComboBox()
        self.llm_api_url_edit.setEditable(True)
        self.llm_api_url_edit.setMinimumWidth(300)
        self.llm_api_url_edit.setMinimumHeight(30)
        self.llm_api_url_edit.addItems([
            "http://localhost:8080/v1",
            "http://localhost:11434/v1",
            "http://localhost:5000/v1",
        ])
        self.llm_api_url_edit.setCurrentText(self.settings.llm.api_url)
        self.llm_api_url_edit.currentTextChanged.connect(self._mark_settings_changed)
        server_layout.addRow("API URL:", self.llm_api_url_edit)
        
        self.llm_model_edit = QComboBox()
        self.llm_model_edit.setEditable(True)
        self.llm_model_edit.setMinimumWidth(300)
        self.llm_model_edit.setMinimumHeight(30)
        self.llm_model_edit.addItems([
            "llama3",
            "mistral",
            "codellama",
            "phi3",
            "mixtral"
        ])
        self.llm_model_edit.setCurrentText(self.settings.llm.model)
        self.llm_model_edit.currentTextChanged.connect(self._mark_settings_changed)
        server_layout.addRow("Model:", self.llm_model_edit)
        
        # Test LLM Connection button
        test_button = QPushButton("Test Connection")
        test_button.setStyleSheet("padding: 5px 10px;")
        test_button.clicked.connect(self._test_llm_connection)
        server_layout.addRow("", test_button)
        
        mode_layout.addWidget(server_settings)
        
        # Connect signals to enable/disable the appropriate sections
        self.embedded_radio.toggled.connect(lambda checked: embedded_settings.setEnabled(checked))
        self.embedded_radio.toggled.connect(self._mark_settings_changed)
        self.external_radio.toggled.connect(lambda checked: server_settings.setEnabled(checked))
        self.external_radio.toggled.connect(self._mark_settings_changed)
        
        layout.addWidget(mode_group)
        
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
        self.processing_type_combo.setMinimumWidth(250)
        self.processing_type_combo.setMinimumHeight(30)
        
        # Set current item based on settings
        for i in range(self.processing_type_combo.count()):
            if self.processing_type_combo.itemData(i) == self.settings.llm.default_processing_type:
                self.processing_type_combo.setCurrentIndex(i)
                break
                
        self.processing_type_combo.currentIndexChanged.connect(self._mark_settings_changed)
        
        processing_layout.addRow("Default Processing:", self.processing_type_combo)
        
        # Custom prompt text edit
        custom_prompt_desc = QLabel("You can use {text} as a placeholder for the transcribed text")
        custom_prompt_desc.setStyleSheet("color: #666666; font-size: 12px;")
        processing_layout.addRow("", custom_prompt_desc)
        
        # Note about embedded model limitations
        embedded_note = QLabel("Note: Built-in models only support summarization and may ignore custom prompts")
        embedded_note.setStyleSheet("color: #666666; font-size: 12px; font-style: italic;")
        embedded_note.setWordWrap(True)
        processing_layout.addRow("", embedded_note)
        
        layout.addWidget(processing_group)
        
        # Disable the settings if LLM is not enabled
        mode_group.setEnabled(self.settings.llm.enabled)
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
        self.show_notif_check.setChecked(self.settings.appearance.show_notifications if hasattr(self.settings, 'appearance') else True)
        self.show_notif_check.toggled.connect(self._mark_settings_changed)
        notif_layout.addRow("", self.show_notif_check)
        
        self.mute_notif_check = QCheckBox("Mute notification sounds")
        self.mute_notif_check.setChecked(self.settings.appearance.mute_notifications if hasattr(self.settings, 'appearance') else True)
        self.mute_notif_check.toggled.connect(self._mark_settings_changed)
        notif_layout.addRow("", self.mute_notif_check)
        
        self.clipboard_check = QCheckBox("Auto-copy transcription to clipboard")
        self.clipboard_check.setChecked(self.settings.appearance.auto_copy_to_clipboard if hasattr(self.settings, 'appearance') else True)
        self.clipboard_check.toggled.connect(self._mark_settings_changed)
        notif_layout.addRow("", self.clipboard_check)
        
        layout.addWidget(notif_group)
        
        # Theme settings (for future implementation)
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)
        theme_layout.setContentsMargins(15, 20, 15, 15)
        theme_layout.setSpacing(10)
        
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(200)
        self.theme_combo.setMinimumHeight(30)
        self.theme_combo.addItems(['Light', 'Dark', 'System'])
        self.theme_combo.setCurrentText(self.settings.appearance.theme if hasattr(self.settings, 'appearance') else 'Light')
        self.theme_combo.currentIndexChanged.connect(self._mark_settings_changed)
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
        
        # First, check for duplicate device names
        device_names = {}
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                name = dev['name']
                if name in device_names:
                    device_names[name].append(i)
                else:
                    device_names[name] = [i]
                    
        # Add input devices
        for name, indices in device_names.items():
            # If only one device with this name, just add it normally
            if len(indices) == 1:
                idx = indices[0]
                dev = devices[idx]
                # Include sample rate in display
                sample_rate = int(dev.get('default_samplerate', 44100))
                display_name = f"{dev['name']} ({dev['max_input_channels']} ch, {sample_rate} Hz)"
                self.device_combo.addItem(display_name, dev['name'])
                
                if dev['name'] == self.settings.audio.input_device:
                    self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
            else:
                # Multiple devices with same name, add API type to differentiate
                for idx in indices:
                    dev = devices[idx]
                    try:
                        host_api = dev.get('hostapi', 0)
                        host_info = sd.query_hostapis(host_api)
                        host_name = host_info.get('name', 'Unknown')
                        
                        # Include sample rate in display
                        sample_rate = int(dev.get('default_samplerate', 44100))
                        display_name = f"{dev['name']} ({host_name}, {dev['max_input_channels']} ch, {sample_rate} Hz)"
                        # Still use just the device name as the data, as that's what the recorder expects
                        self.device_combo.addItem(display_name, dev['name'])
                        
                        if dev['name'] == self.settings.audio.input_device:
                            self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
                    except Exception as e:
                        logger.error(f"Error getting host API info: {e}")
                        # Fallback to simpler display if we can't get host API info
                        sample_rate = int(dev.get('default_samplerate', 44100))
                        display_name = f"{dev['name']} (ID: {idx}, {dev['max_input_channels']} ch, {sample_rate} Hz)"
                        self.device_combo.addItem(display_name, dev['name'])
        
        # Connect device change signal to update sample rate
        # Disconnect first to avoid multiple connections
        try:
            self.device_combo.currentIndexChanged.disconnect(self._on_device_changed)
        except:
            pass
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
    
    def _on_device_changed(self, index):
        """Handle device selection changes"""
        self._mark_settings_changed()
        
        # Get selected device and update sample rate dropdown to match device's default
        device_name = self.device_combo.currentData()
        
        if device_name == "default":
            # For default device, just use system default values
            return
            
        try:
            # Find the device(s) with this name
            devices = sd.query_devices()
            matching_devices = []
            for i, dev in enumerate(devices):
                if dev['name'] == device_name and dev['max_input_channels'] > 0:
                    matching_devices.append((i, dev))
            
            if matching_devices:
                # Prefer WASAPI device if available
                wasapi_device = None
                for idx, dev in matching_devices:
                    host_api = dev.get('hostapi', 0)
                    try:
                        host_name = sd.query_hostapis(host_api).get('name', 'Unknown').lower()
                        if "wasapi" in host_name:
                            wasapi_device = (idx, dev)
                            break
                    except Exception as e:
                        logger.error(f"Error querying host API: {e}")
                
                # Use WASAPI device if found, else use first matching device
                device_info = wasapi_device[1] if wasapi_device else matching_devices[0][1]
                
                # Get device's default sample rate
                default_sample_rate = int(device_info.get('default_samplerate', 44100))
                
                # Find and select the closest sample rate in the dropdown
                closest_index = -1
                closest_diff = float('inf')
                
                for i in range(self.sample_rate_combo.count()):
                    rate = self.sample_rate_combo.itemData(i)
                    diff = abs(rate - default_sample_rate)
                    if diff < closest_diff:
                        closest_diff = diff
                        closest_index = i
                
                if closest_index >= 0:
                    # If we don't have an exact match, add the device's default rate
                    if closest_diff > 0:
                        # Add the device's default sample rate to the dropdown
                        self.sample_rate_combo.addItem(f"{default_sample_rate} Hz (device default)", default_sample_rate)
                        self.sample_rate_combo.setCurrentIndex(self.sample_rate_combo.count() - 1)
                    else:
                        self.sample_rate_combo.setCurrentIndex(closest_index)
                        
                    logger.debug(f"Selected sample rate {self.sample_rate_combo.currentText()} for device {device_name}")
        except Exception as e:
            logger.error(f"Error updating sample rate for device: {e}")
    
    def _mark_settings_changed(self):
        """Mark that settings have been changed"""
        self.settings_changed = True
    
    @Slot()
    def _save_settings(self):
        """Save settings and apply them"""
        # Save the state of our save request
        self.save_requested = True
        
        # If no settings were changed, just close the window
        if not self.settings_changed:
            self.close()
            return
        
        # Update settings with values from UI
        # 1. Hotkeys tab
        record_key = self.record_hotkey_edit.keySequence()
        self.settings.hotkeys.record_key = record_key
        
        if self.process_hotkey_edit.keySequence().isEmpty():
            self.settings.hotkeys.process_text_key = None
        else:
            self.settings.hotkeys.process_text_key = self.process_hotkey_edit.keySequence()
        
        # 2. Audio tab
        self.settings.audio.input_device = self.device_combo.currentData()
        self.settings.audio.sample_rate = self.sample_rate_combo.currentData()
        self.settings.audio.channels = self.channels_spin.value()
        
        # 3. Transcription tab
        self.settings.transcription.model = self.model_combo.currentText()
        
        # Extract device value from the selection (remove description)
        device_text = self.device_type_combo.currentText()
        self.settings.transcription.device = "cpu" if device_text.startswith("cpu") else "cuda"
        
        self.settings.transcription.language = self.language_combo.currentText()
        if self.settings.transcription.language == "Auto-detect":
            self.settings.transcription.language = None
        
        # 4. LLM tab
        self.settings.llm.enabled = self.llm_enabled_check.isChecked()
        
        # Check whether we're using embedded model or external API
        self.settings.llm.use_embedded_model = self.embedded_radio.isChecked()
        
        if self.settings.llm.use_embedded_model:
            # Get the embedded model name
            self.settings.llm.embedded_model_name = self.embedded_model_combo.currentText()
        else:
            # External API settings
            self.settings.llm.api_url = self.llm_api_url_edit.currentText()
            self.settings.llm.model = self.llm_model_edit.currentText()
        
        # Processing type (common for both modes)
        self.settings.llm.default_processing_type = self.processing_type_combo.currentData()
        
        # 5. Appearance tab
        if not hasattr(self.settings, 'appearance'):
            from ...domain.settings import AppearanceSettings
            self.settings.appearance = AppearanceSettings()
            
        self.settings.appearance.show_notifications = self.show_notif_check.isChecked()
        self.settings.appearance.mute_notifications = self.mute_notif_check.isChecked()
        self.settings.appearance.auto_copy_to_clipboard = self.clipboard_check.isChecked()
        self.settings.appearance.theme = self.theme_combo.currentText()
        
        # Save settings
        try:
            self.settings_repository.save(self.settings)
            self.settings_saved.emit()  # Emit signal that settings were saved
            
            # Show a saved toast
            QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
            
            # Close the window
            self.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")
            return

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

    def closeEvent(self, event):
        """Handle the window close event"""
        # If Save button was clicked, accept the close event
        if self.save_requested:
            self.save_requested = False  # Reset for next time
            event.accept()
            return
            
        # If no changes were made, just close without confirmation
        if not self.settings_changed:
            event.accept()
            return
            
        # If close button (X) was clicked with changes, ask for confirmation
        confirm = QMessageBox.question(
            self,
            "Close Settings",
            "Close without saving changes?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

class SettingsDialog(QDialog):
    hotkey_changed = Signal(object)  # Emits QKeySequence

    def __init__(self, parent=None, settings=None, settings_repository=None):
        super().__init__(parent)
        self.settings = settings
        self.settings_repository = settings_repository
        self.setWindowTitle("Memo Settings")
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
    
    def accept(self):
        """Override accept to emit hotkey_changed signal when OK is clicked"""
        new_sequence = self.hotkey_edit.keySequence()
        self.hotkey_changed.emit(new_sequence)
        logger.debug(f"Hotkey changed to: {new_sequence.toString()}")
        super().accept()
        
    def _on_hotkey_changed(self):
        """Handle hotkey changes - this is kept for backwards compatibility"""
        pass

    def set_current_hotkey(self, key_sequence):
        """Set the current hotkey in the editor"""
        self.hotkey_edit.setKeySequence(key_sequence) 