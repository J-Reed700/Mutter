from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QComboBox, QTabWidget,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QKeySequenceEdit, QDialog, QSlider, QFrame,
    QApplication, QStyle, QSizePolicy, QMessageBox,
    QButtonGroup, QRadioButton, QScrollArea, QProgressBar
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QFont, QIcon, QPixmap
import sounddevice as sd
import logging
from pathlib import Path

from ...domain.settings import Settings
from ...infrastructure.persistence.settings_repository import SettingsRepository
from ..theme import AppTheme

logger = logging.getLogger(__name__)

# Define constants if not in AppTheme
if not hasattr(AppTheme, 'TEXT_SECONDARY'):
    setattr(AppTheme, 'TEXT_SECONDARY', '#777777')
if not hasattr(AppTheme, 'FONT_SIZE_SMALL'):
    setattr(AppTheme, 'FONT_SIZE_SMALL', 8)
if not hasattr(AppTheme, 'ACCENT'):
    setattr(AppTheme, 'ACCENT', '#0078D7')

class SettingsWindow(QMainWindow):
    # Add a signal to indicate settings were saved
    settings_saved = Signal()
    
    def __init__(self, settings: Settings, settings_repository: SettingsRepository):
        super().__init__()
        self.settings = settings
        self.settings_repository = settings_repository
        self.save_requested = False  # Track if Save button was clicked
        self.settings_changed = False  # Track if any settings were actually changed
        
        # Log settings values at initialization
        logger.info(f"SettingsWindow initialized with: "
                   f"quit_key={self.settings.hotkeys.quit_key.toString() if self.settings.hotkeys.quit_key else 'None'}, "
                   f"record_key={self.settings.hotkeys.record_key.toString()}")
        
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
        
        # Apply a simpler combo box styling that will be more reliable
        self.setStyleSheet("""
            QComboBox {
                padding: 5px;
                min-height: 25px;
            }
            QComboBox QAbstractItemView {
                padding: 8px;
            }
        """)
        
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
        # tabs.addTab(self._create_llm_tab(), "LLM Processing")
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
        
        # Quit hotkey
        quit_group = QGroupBox("Quit Hotkey")
        quit_layout = QFormLayout(quit_group)
        quit_layout.setContentsMargins(15, 20, 15, 15)
        quit_layout.setSpacing(10)
        
        self.quit_hotkey_edit = QKeySequenceEdit(
            self.settings.hotkeys.quit_key or QKeySequence()
        )
        self.quit_hotkey_edit.setMinimumWidth(200)
        self.quit_hotkey_edit.editingFinished.connect(self._mark_settings_changed)
        quit_layout.addRow("Quit Key:", self.quit_hotkey_edit)
        
        # Add a description
        quit_desc = QLabel("Press this key combination to quit the application")
        quit_desc.setStyleSheet("color: #666666; font-size: 12px;")
        quit_layout.addRow("", quit_desc)
        
        layout.addWidget(quit_group)
        
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
        # Ensure LLM settings are initialized
        self._ensure_llm_settings_initialized()
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)  # Increase spacing between groups
        
        # Help text at the top
        help_label = QLabel(
            "Configure LLM processing for transcriptions. "
            "You can use either the built-in LLM or connect to an external LLM server."
            "Please note that these are experimental features and may not work as expected."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Add a progress bar for model downloading (hidden by default)
        self.download_group = QGroupBox("Model Download Status")
        download_layout = QVBoxLayout(self.download_group)
        download_layout.setContentsMargins(15, 20, 15, 15)
        download_layout.setSpacing(10)
        
        self.download_status_label = QLabel("No download in progress")
        self.download_status_label.setWordWrap(True)
        download_layout.addWidget(self.download_status_label)
        
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        download_layout.addWidget(self.download_progress)
        
        # Add the download group to the layout but hide it initially
        layout.addWidget(self.download_group)
        self.download_group.setVisible(False)
        
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
        
        # --------- LLM Mode selection (embedded vs external) ----------
        # Changed to use separate groups for clearer organization
        
        # Mode selection (radio buttons only)
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
        mode_layout.addWidget(self.external_radio)
        
        layout.addWidget(mode_group)
        
        # ---------- Embedded Model Settings (separate group) ----------
        embedded_group = QGroupBox("Built-in Model Settings")
        embedded_layout = QFormLayout(embedded_group)
        embedded_layout.setContentsMargins(15, 20, 15, 15)
        embedded_layout.setSpacing(10)
        
        self.embedded_model_combo = QComboBox()
        self.embedded_model_combo.addItems([
            "facebook/distilbart-cnn-12-6",
            "sshleifer/distilbart-xsum-12-3",
            "google/flan-t5-small",
            "facebook/bart-large-cnn",
            "philschmid/distilbart-cnn-12-6-samsum"
        ])
        self.embedded_model_combo.setMinimumWidth(300)
        self.embedded_model_combo.setMinimumHeight(30)
        # Fix dropdown width when shown
        self.embedded_model_combo.view().setTextElideMode(Qt.ElideNone)
        self.embedded_model_combo.installEventFilter(self)
        self.embedded_model_combo.activated.connect(lambda: self._resize_combo_popup(self.embedded_model_combo))
        
        # Set current embedded model
        if hasattr(self.settings.llm, 'embedded_model_name') and self.settings.llm.embedded_model_name:
            index = self.embedded_model_combo.findText(self.settings.llm.embedded_model_name)
            if index >= 0:
                self.embedded_model_combo.setCurrentIndex(index)
            else:
                # If not found, set the first item
                self.embedded_model_combo.setCurrentIndex(0)
        else:
            # Default to first item if no setting
            self.embedded_model_combo.setCurrentIndex(0)
        
        self.embedded_model_combo.currentIndexChanged.connect(self._mark_settings_changed)
        
        embedded_layout.addRow("Model:", self.embedded_model_combo)
        
        embedded_desc = QLabel("Built-in models work immediately without additional setup but use more memory.\nT5 models (t5-small, flan-t5-small) are better at handling custom prompts.")
        embedded_desc.setStyleSheet("color: #666666; font-size: 12px;")
        embedded_desc.setWordWrap(True)
        embedded_layout.addRow("", embedded_desc)
        
        # Add download button for embedded models
        self.download_model_button = QPushButton("Download Selected Model")
        self.download_model_button.setToolTip("Download the selected model now instead of waiting for first use")
        self.download_model_button.clicked.connect(self._download_selected_model)
        embedded_layout.addRow("", self.download_model_button)
        
        layout.addWidget(embedded_group)
        
        # ---------- External Server Settings (separate group) ----------
        external_group = QGroupBox("External LLM Server Settings")
        external_layout = QFormLayout(external_group)
        external_layout.setContentsMargins(15, 20, 15, 15)
        external_layout.setSpacing(10)
        
        self.llm_api_url_edit = QComboBox()
        self.llm_api_url_edit.setEditable(True)
        self.llm_api_url_edit.setMinimumWidth(300)
        self.llm_api_url_edit.setMinimumHeight(30)
        # Fix dropdown width when shown
        self.llm_api_url_edit.view().setTextElideMode(Qt.ElideNone)
        self.llm_api_url_edit.installEventFilter(self)
        self.llm_api_url_edit.addItems([
            "http://localhost:8080/v1",
            "http://localhost:11434/v1",
            "http://localhost:5000/v1",
        ])
        
        # Set the current API URL
        if hasattr(self.settings.llm, 'api_url') and self.settings.llm.api_url:
            # First check if it's in the list
            index = self.llm_api_url_edit.findText(self.settings.llm.api_url)
            if index >= 0:
                self.llm_api_url_edit.setCurrentIndex(index)
            else:
                # If not found in the list, just set the text directly
                self.llm_api_url_edit.setCurrentText(self.settings.llm.api_url)
        else:
            # Default to first item
            self.llm_api_url_edit.setCurrentIndex(0)
        
        # Connect both signals for editable combo box
        self.llm_api_url_edit.currentTextChanged.connect(self._mark_settings_changed)
        self.llm_api_url_edit.activated.connect(lambda: self._resize_combo_popup(self.llm_api_url_edit))
        self.llm_api_url_edit.editTextChanged.connect(self._mark_settings_changed)
        external_layout.addRow("API URL:", self.llm_api_url_edit)
        
        self.llm_model_edit = QComboBox()
        self.llm_model_edit.setEditable(True)
        self.llm_model_edit.setMinimumWidth(300)
        self.llm_model_edit.setMinimumHeight(30)
        # Fix dropdown width when shown
        self.llm_model_edit.view().setTextElideMode(Qt.ElideNone)
        self.llm_model_edit.installEventFilter(self)
        self.llm_model_edit.addItems([
            "llama3",
            "mistral",
            "codellama",
            "phi3",
            "mixtral"
        ])
        
        # Set the current model
        if hasattr(self.settings.llm, 'model') and self.settings.llm.model:
            # First check if it's in the list
            index = self.llm_model_edit.findText(self.settings.llm.model)
            if index >= 0:
                self.llm_model_edit.setCurrentIndex(index)
            else:
                # If not found in the list, just set the text directly
                self.llm_model_edit.setCurrentText(self.settings.llm.model)
        else:
            # Default to first item
            self.llm_model_edit.setCurrentIndex(0)
        
        # Connect both signals for editable combo box
        self.llm_model_edit.currentTextChanged.connect(self._mark_settings_changed)
        self.llm_model_edit.activated.connect(lambda: self._resize_combo_popup(self.llm_model_edit))
        self.llm_model_edit.editTextChanged.connect(self._mark_settings_changed)
        external_layout.addRow("Model:", self.llm_model_edit)
        
        # Test LLM Connection button
        test_button = QPushButton("Test Connection")
        test_button.setStyleSheet("padding: 5px 10px;")
        test_button.clicked.connect(self._test_llm_connection)
        external_layout.addRow("", test_button)
        
        layout.addWidget(external_group)
        
        # Connect signals to enable/disable the appropriate sections
        self.embedded_radio.toggled.connect(lambda checked: embedded_group.setEnabled(checked))
        self.embedded_radio.toggled.connect(self._mark_settings_changed)
        self.external_radio.toggled.connect(lambda checked: external_group.setEnabled(checked))
        self.external_radio.toggled.connect(self._mark_settings_changed)
        
        # Set initial state based on radio button
        embedded_group.setEnabled(self.embedded_radio.isChecked())
        external_group.setEnabled(self.external_radio.isChecked())
        
        # ---------- LLM Processing Settings ----------
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
        # Fix dropdown width when shown
        self.processing_type_combo.view().setTextElideMode(Qt.ElideNone)
        self.processing_type_combo.installEventFilter(self)
        self.processing_type_combo.activated.connect(lambda: self._resize_combo_popup(self.processing_type_combo))
        
        # Set current item based on settings
        if hasattr(self.settings.llm, 'default_processing_type') and self.settings.llm.default_processing_type:
            for i in range(self.processing_type_combo.count()):
                if self.processing_type_combo.itemData(i) == self.settings.llm.default_processing_type:
                    self.processing_type_combo.setCurrentIndex(i)
                    break
            else:
                # Not found, default to first item
                self.processing_type_combo.setCurrentIndex(0)
        else:
            # Default to first item if no setting
            self.processing_type_combo.setCurrentIndex(0)
                
        self.processing_type_combo.currentIndexChanged.connect(self._mark_settings_changed)
        
        processing_layout.addRow("Default Processing:", self.processing_type_combo)
        
        # Custom prompt text edit
        custom_prompt_desc = QLabel("You can use {text} as a placeholder for the transcribed text")
        custom_prompt_desc.setStyleSheet("color: #666666; font-size: 12px;")
        processing_layout.addRow("", custom_prompt_desc)
        
        # Note about embedded model limitations
        embedded_note = QLabel("Note: BART/DistilBART models only support summarization, while T5 models better support custom prompts")
        embedded_note.setStyleSheet("color: #666666; font-size: 12px; font-style: italic;")
        embedded_note.setWordWrap(True)
        processing_layout.addRow("", embedded_note)
        
        layout.addWidget(processing_group)
        
        # Disable the settings if LLM is not enabled
        mode_group.setEnabled(self.settings.llm.enabled)
        embedded_group.setEnabled(self.settings.llm.enabled and self.embedded_radio.isChecked())
        external_group.setEnabled(self.settings.llm.enabled and self.external_radio.isChecked())
        processing_group.setEnabled(self.settings.llm.enabled)
        
        # Add scroll area for smaller screens
        scroll_area = QScrollArea()
        scroll_area.setWidget(widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.addWidget(scroll_area)
        
        return scroll_widget
    
    def _ensure_llm_settings_initialized(self):
        """Ensure LLM settings are initialized with default values if missing"""
        if not hasattr(self.settings, 'llm'):
            from ...domain.settings import LLMSettings
            self.settings.llm = LLMSettings()
            
        # Set default values if not present
        if not hasattr(self.settings.llm, 'enabled'):
            self.settings.llm.enabled = False
            
        if not hasattr(self.settings.llm, 'use_embedded_model'):
            self.settings.llm.use_embedded_model = True
            
        if not hasattr(self.settings.llm, 'embedded_model_name'):
            self.settings.llm.embedded_model_name = "google/flan-t5-small"
            
        if not hasattr(self.settings.llm, 'api_url'):
            self.settings.llm.api_url = "http://localhost:8080/v1"
            
        if not hasattr(self.settings.llm, 'model'):
            self.settings.llm.model = "llama3"
            
        if not hasattr(self.settings.llm, 'default_processing_type'):
            self.settings.llm.default_processing_type = "summarize"
    
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
        
        
        self.clipboard_check = QCheckBox("Auto-copy transcription to clipboard")
        self.clipboard_check.setChecked(self.settings.appearance.auto_copy_to_clipboard if hasattr(self.settings, 'appearance') else True)
        self.clipboard_check.toggled.connect(self._mark_settings_changed)
        notif_layout.addRow("", self.clipboard_check)
        
        self.auto_paste_check = QCheckBox("Auto-paste transcription into active text field")
        self.auto_paste_check.setChecked(self.settings.appearance.auto_paste if hasattr(self.settings, 'appearance') else True)
        self.auto_paste_check.toggled.connect(self._mark_settings_changed)
        notif_layout.addRow("", self.auto_paste_check)
        
        layout.addWidget(notif_group)
        
        # Theme settings (for future implementation)
        # theme_group = QGroupBox("Theme")
        # theme_layout = QFormLayout(theme_group)
        # theme_layout.setContentsMargins(15, 20, 15, 15)
        # theme_layout.setSpacing(10)
        # 
        # self.theme_combo = QComboBox()
        # self.theme_combo.setMinimumWidth(200)
        # self.theme_combo.setMinimumHeight(30)
        # self.theme_combo.addItems(['Light', 'Dark', 'System'])
        # self.theme_combo.setCurrentText(self.settings.appearance.theme if hasattr(self.settings, 'appearance') else 'Light')
        # self.theme_combo.currentIndexChanged.connect(self._mark_settings_changed)
        # theme_layout.addRow("Theme:", self.theme_combo)
        # 
        # # Add a theme description
        # theme_desc = QLabel("Theme changes will apply after restart")
        # theme_desc.setStyleSheet("color: #666666; font-size: 12px;")
        # theme_layout.addRow("", theme_desc)
        
        # layout.addWidget(theme_group)
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
        except (TypeError, RuntimeError):
            # This is fine - signal might not be connected yet
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
        """Save settings to the repository when the Save button is clicked"""
        logger.debug("Saving settings")
        
        # 1. Hotkeys tab
        if hasattr(self, 'record_hotkey_edit'):
            self.settings.hotkeys.record_key = self.record_hotkey_edit.keySequence()
        if hasattr(self, 'quit_hotkey_edit'):
            self.settings.hotkeys.quit_key = self.quit_hotkey_edit.keySequence()
        
        # 2. Audio tab
        if hasattr(self, 'device_combo'):
            self.settings.audio.input_device = self.device_combo.currentData()
        if hasattr(self, 'sample_rate_combo'):
            self.settings.audio.sample_rate = self.sample_rate_combo.currentData()
        if hasattr(self, 'channels_spin'):
            self.settings.audio.channels = self.channels_spin.value()
        
        # 3. Transcription tab
        if hasattr(self, 'model_combo'):
            self.settings.transcription.model = self.model_combo.currentText()
        
        # Extract device value from the selection (remove description)
        if hasattr(self, 'device_type_combo'):
            device_text = self.device_type_combo.currentText()
            self.settings.transcription.device = "cpu" if device_text.startswith("cpu") else "cuda"
        
        if hasattr(self, 'language_combo'):
            self.settings.transcription.language = self.language_combo.currentText()
            if self.settings.transcription.language == "Auto-detect":
                self.settings.transcription.language = None
                
        # Log key settings that are being saved
        logger.info(f"Saving settings with values: "
                   f"quit_key={self.settings.hotkeys.quit_key.toString() if self.settings.hotkeys.quit_key else 'None'}, "
                   f"record_key={self.settings.hotkeys.record_key.toString()}, "
                   f"input_device={self.settings.audio.input_device}, " 
                   f"sample_rate={self.settings.audio.sample_rate}")
        
        # 4. LLM tab
        if hasattr(self, 'llm_enabled_check'):
            self.settings.llm.enabled = self.llm_enabled_check.isChecked()
            
            # Check whether we're using embedded model or external API
            if hasattr(self, 'embedded_radio'):
                self.settings.llm.use_embedded_model = self.embedded_radio.isChecked()
                
                if self.settings.llm.use_embedded_model and hasattr(self, 'embedded_model_combo'):
                    # Get the embedded model name
                    model_name = self.embedded_model_combo.currentText()
                    
                    # Ensure model names have proper repository prefix
                    if model_name == "distilbart-cnn-12-6":
                        model_name = "facebook/distilbart-cnn-12-6"
                    
                    self.settings.llm.embedded_model_name = model_name
                    
                    # If the model has been changed, we should show the download progress
                    old_model = getattr(self.settings.llm, 'embedded_model_name', "")
                    if old_model != model_name and hasattr(self, 'download_group'):
                        self.download_group.setVisible(True)
                        self.download_status_label.setText(f"Model will be downloaded when processing starts: {model_name}")
                        QApplication.processEvents()  # Ensure UI updates
                elif hasattr(self, 'server_url_input'):
                    # External API settings
                    # Get text directly from editable combo boxes
                    if hasattr(self, 'llm_api_url_edit'):
                        self.settings.llm.api_url = self.llm_api_url_edit.currentText().strip()
                    if hasattr(self, 'llm_model_edit'):
                        self.settings.llm.model = self.llm_model_edit.currentText().strip()
                    
                    # Ensure we have default values if empty
                    if not self.settings.llm.api_url:
                        self.settings.llm.api_url = "http://localhost:8080/v1"
                    if not self.settings.llm.model:
                        self.settings.llm.model = "llama3"
            
            # Processing type (common for both modes)
            if hasattr(self, 'processing_type_combo'):
                self.settings.llm.default_processing_type = self.processing_type_combo.currentData()
        
        # 5. Appearance tab
        if not hasattr(self.settings, 'appearance'):
            from ...domain.settings import AppearanceSettings
            self.settings.appearance = AppearanceSettings()
        
        if hasattr(self, 'show_notif_check'):
            self.settings.appearance.show_notifications = self.show_notif_check.isChecked()
        if hasattr(self, 'clipboard_check'):
            self.settings.appearance.auto_copy_to_clipboard = self.clipboard_check.isChecked()
        if hasattr(self, 'auto_paste_check'):
            self.settings.appearance.auto_paste = self.auto_paste_check.isChecked()
        if hasattr(self, 'theme_combo'):
            self.settings.appearance.theme = self.theme_combo.currentText()
        
        # Save settings
        try:
            self.settings_repository.save(self.settings)
            self.settings_saved.emit()  # Emit signal that settings were saved
            
            # Show a saved toast
            QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
            
            # Set save_requested to True to avoid the unsaved changes dialog
            self.save_requested = True
            self.settings_changed = False  # Reset the changed flag
            
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

    def eventFilter(self, obj, event):
        """Handle events for widgets that have this object as their event filter."""
        if isinstance(obj, QComboBox):
            if event.type() == QEvent.Type.MouseButtonPress:
                # Resize popup when combo box is clicked
                QTimer.singleShot(10, lambda: self._resize_combo_popup(obj))
            elif event.type() == QEvent.Type.FocusIn and obj.isEditable():
                # Also resize when entering an editable combo box
                QTimer.singleShot(10, lambda: self._resize_combo_popup(obj))
            elif event.type() == QEvent.Type.Show:
                # For show events, just resize the combo box popup if it's visible
                QTimer.singleShot(10, lambda: self._resize_combo_popup(obj))
                
        return super().eventFilter(obj, event)

    def _resize_combo_popup(self, combo_box):
        """Resize the popup for a combobox to show all items properly."""
        if not combo_box or not hasattr(combo_box, 'view'):
            return
            
        view = combo_box.view()
        if not view or not view.isVisible():
            # The popup is not visible, nothing to do
            return
            
        # Calculate content width
        width = 0
        fontMetrics = combo_box.fontMetrics()
        
        # Check all items to find the widest one
        for i in range(combo_box.count()):
            itemText = combo_box.itemText(i)
            itemWidth = fontMetrics.horizontalAdvance(itemText) + 30  # Add padding
            width = max(width, itemWidth)
            
        # Ensure at least as wide as the combo box itself plus some extra space
        width = max(width, combo_box.width() + 50)
        
        # Set the popup width
        try:
            view.setMinimumWidth(width)
            view.resize(width, view.height())
            
            # For editable combo boxes, make sure we can see text being typed
            if combo_box.isEditable() and hasattr(combo_box, 'lineEdit'):
                combo_box.lineEdit().setMinimumWidth(width - 30)  # Account for dropdown button
        except Exception as e:
            # Log but don't crash if there's an issue resizing
            logger.debug(f"Failed to resize combo popup: {e}")

    def update_model_download_progress(self, message: str, progress: float):
        """Update the model download progress display
        
        Args:
            message: Status message to display
            progress: Progress percentage (0-100) or negative for error
        """
        # Ensure the download group is visible
        self.download_group.setVisible(True)
        
        # Update the status message
        self.download_status_label.setText(message)
        
        # Update the progress bar
        if progress < 0:
            # Negative value indicates error
            self.download_progress.setStyleSheet("QProgressBar { color: white; background-color: #ffaaaa; } QProgressBar::chunk { background-color: #ff6666; }")
            self.download_progress.setFormat("Error")
            self.download_progress.setValue(0)
        elif progress >= 100:
            # Complete
            self.download_progress.setStyleSheet("QProgressBar { color: white; background-color: #aaffaa; } QProgressBar::chunk { background-color: #66ff66; }")
            self.download_progress.setFormat("Complete")
            self.download_progress.setValue(100)
            
            # Hide the group after a delay
            QTimer.singleShot(3000, lambda: self.download_group.setVisible(False))
        else:
            # In progress
            self.download_progress.setStyleSheet("")
            self.download_progress.setFormat("%p%")
            self.download_progress.setValue(int(progress))
        
        # Process events to ensure UI updates
        QApplication.processEvents()

    def _download_selected_model(self):
        """Pre-download the selected embedded model"""
        from ...infrastructure.llm.embedded_processor import EmbeddedTextProcessor
        
        model_name = self.embedded_model_combo.currentText()
        
        # Show the download status UI
        self.download_group.setVisible(True)
        self.download_status_label.setText(f"Initializing download for model: {model_name}")
        self.download_progress.setValue(0)
        QApplication.processEvents()
        
        try:
            # Create an embedded processor instance just for downloading
            # We can't reuse existing ones from ServiceManager because we want immediate update
            processor = EmbeddedTextProcessor(
                model_name=model_name,
                progress_callback=self.update_model_download_progress
            )
            
            # Show a message that download has started
            QMessageBox.information(
                self,
                "Download Started",
                f"Download of model {model_name} has been started. Progress will be shown in the settings window.",
                QMessageBox.Ok
            )
        except Exception as e:
            # Show error message
            QMessageBox.critical(
                self,
                "Download Error",
                f"Failed to start model download: {str(e)}",
                QMessageBox.Ok
            )
            # Update progress display to show error
            self.update_model_download_progress(f"Error starting download: {str(e)}", -1)

class SettingsDialog(QDialog):
    hotkey_changed = Signal(object)  # Emits QKeySequence

    def __init__(self, parent=None, settings=None, recording_service=None):
        super().__init__(parent)
        self.settings = settings
        self.recording_service = recording_service
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
        
        # Set the current hotkey from settings
        if self.settings and hasattr(self.settings, 'hotkeys') and self.settings.hotkeys.record_key:
            self.hotkey_edit.setKeySequence(self.settings.hotkeys.record_key)
            
        hotkey_layout.addRow(hotkey_label, self.hotkey_edit)
        
        # Add a section for quit hotkey
        quit_hotkey_label = QLabel("Quit Hotkey:")
        self.quit_hotkey_edit = QKeySequenceEdit()
        self.quit_hotkey_edit.setMinimumWidth(200)
        
        # Set the current quit hotkey from settings
        if self.settings and hasattr(self.settings, 'hotkeys') and self.settings.hotkeys.quit_key:
            self.quit_hotkey_edit.setKeySequence(self.settings.hotkeys.quit_key)
            
        hotkey_layout.addRow(quit_hotkey_label, self.quit_hotkey_edit)
        
        # Add a note
        note_label = QLabel("Note: These hotkeys work globally across all applications")
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
        """Override accept to save the hotkey settings when OK is clicked"""
        if self.settings and hasattr(self.settings, 'hotkeys'):
            # Save record hotkey
            new_record_sequence = self.hotkey_edit.keySequence()
            if new_record_sequence != self.settings.hotkeys.record_key:
                self.settings.hotkeys.record_key = new_record_sequence
                if self.recording_service:
                    self.recording_service.set_hotkey(new_record_sequence)
                    
            # Save quit hotkey
            new_quit_sequence = self.quit_hotkey_edit.keySequence()
            if new_quit_sequence != self.settings.hotkeys.quit_key:
                self.settings.hotkeys.quit_key = new_quit_sequence
                if self.recording_service:
                    self.recording_service.set_quit_hotkey(new_quit_sequence)
                    
            # Emit the signal for compatibility
            self.hotkey_changed.emit(new_record_sequence)
            logger.debug(f"Hotkeys saved: Record={new_record_sequence.toString()}, Quit={new_quit_sequence.toString()}")
            
        super().accept()
        
    def _on_hotkey_changed(self):
        """Handle hotkey changes - this is kept for backwards compatibility"""
        pass

    def set_current_hotkey(self, key_sequence):
        """Set the current hotkey in the editor"""
        self.hotkey_edit.setKeySequence(key_sequence)
        
    def get_settings(self):
        """Get the current settings
        
        Returns:
            Settings: The updated settings object
        """
        return self.settings 