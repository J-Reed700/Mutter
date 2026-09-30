from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QComboBox, QTabWidget,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QKeySequenceEdit, QFrame,
    QApplication, QStyle, QSizePolicy, QMessageBox,
    QScrollArea,
    QTextEdit, QLineEdit
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QFont, QIcon
import sounddevice as sd
import logging
from pathlib import Path

from ...domain.settings import Settings, DEFAULT_LLM_PROMPT
from ...infrastructure.persistence.settings_repository import SettingsRepository
from ..theme import AppTheme

# Display name -> Whisper language code (None = auto-detect)
LANGUAGE_OPTIONS = [
    ("Auto-detect", None),
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("German", "de"),
    ("Italian", "it"),
    ("Portuguese", "pt"),
    ("Dutch", "nl"),
    ("Russian", "ru"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
    ("Chinese", "zh"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
]

# Legacy settings stored full names ("English") instead of codes
_LANGUAGE_NAME_TO_CODE = {name.lower(): code for name, code in LANGUAGE_OPTIONS}

logger = logging.getLogger(__name__)

class SettingsWindow(QMainWindow):
    # Add a signal to indicate settings were saved
    settings_saved = Signal()

    def __init__(self, settings: Settings, settings_repository: SettingsRepository):
        super().__init__()
        self.settings = settings
        self.settings_repository = settings_repository
        self.save_requested = False  # Track if Save button was clicked
        
        # Log settings values at initialization
        logger.info(f"SettingsWindow initialized with: "
                   f"quit_key={self.settings.hotkeys.quit_key.toString() if self.settings.hotkeys.quit_key else 'None'}, "
                   f"record_key={self.settings.hotkeys.record_key.toString()}")
        
        self.setWindowTitle("Mutter Settings")
        self.setMinimumSize(640, 640)
        
        # Set window icon if available
        icon_path = Path(__file__).parent.parent.parent.parent / "resources" / "images" / "microphone.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Colors and control styling come from the app-wide theme; only local
        # sizing tweaks live here
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
        title_label = QLabel("Mutter Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        version = self._get_app_version()
        if version:
            version_label = QLabel(f"v{version}")
            version_label.setProperty("labelStyle", "hint")
            version_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            header_layout.addWidget(version_label)

        layout.addLayout(header_layout)

        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Add tabs
        tabs.addTab(self._create_hotkeys_tab(), "Hotkeys")
        tabs.addTab(self._create_audio_tab(), "Audio")
        tabs.addTab(self._create_transcription_tab(), "Transcription")
        tabs.addTab(self._create_llm_tab(), "LLM Processing")
        tabs.addTab(self._create_appearance_tab(), "Appearance")

        # Separator between content and actions
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Bottom action buttons, right-aligned
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setProperty("buttonStyle", "secondary")
        cancel_button.clicked.connect(self.close)
        button_layout.addWidget(cancel_button)

        save_button = QPushButton("Save")
        save_button.setDefault(True)
        save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(save_button)

        # Snapshot the UI state so closing can reliably detect real edits —
        # signal-based dirty tracking misfires on programmatic changes
        self._initial_ui_state = self._ui_state()

    def _ui_state(self) -> tuple:
        """Collect every editable value in the window for change detection."""
        return (
            self.record_hotkey_edit.keySequence().toString(),
            self.quit_hotkey_edit.keySequence().toString(),
            self.process_hotkey_edit.keySequence().toString(),
            self.device_combo.currentData(),
            self.sample_rate_combo.currentData(),
            self.channels_spin.value(),
            self.model_combo.currentText(),
            self.device_type_combo.currentText(),
            self.language_combo.currentData(),
            self.llm_enabled_check.isChecked(),
            self.llm_api_url_edit.text(),
            self.llm_model_combo.currentText(),
            self.llm_username_edit.text(),
            self.llm_password_edit.text(),
            self.custom_prompt_edit.toPlainText(),
            self.show_notif_check.isChecked(),
            self.clipboard_check.isChecked(),
            self.auto_paste_check.isChecked(),
        )

    def _has_unsaved_changes(self) -> bool:
        """True if any control differs from the state the window opened with."""
        try:
            return self._ui_state() != self._initial_ui_state
        except Exception as e:
            logger.warning(f"Could not compute UI state for change detection: {e}")
            return False

    @staticmethod
    def _get_app_version() -> str:
        """Best-effort application version for the header (empty if unknown)."""
        try:
            from importlib.metadata import version
            return version("voice-recorder")
        except Exception:
            return ""

    @staticmethod
    def _hint_label(text: str) -> QLabel:
        """A small secondary-color label for inline help text."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("labelStyle", "hint")
        return label

    @staticmethod
    def _secondary_button(text: str) -> QPushButton:
        """A compact, quiet button for minor utility actions."""
        button = QPushButton(text)
        button.setProperty("buttonStyle", "secondary")
        return button
    
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
        self.record_hotkey_edit.setMaximumSequenceLength(1)
        self.record_hotkey_edit.setFixedWidth(240)
        self.record_hotkey_edit.keySequenceChanged.connect(self._update_hotkey_displays)
        record_layout.addRow("Record Key:", self.record_hotkey_edit)
        
        # Add a display label for showing friendly key representation
        self.record_hotkey_display = QLabel("")
        self.record_hotkey_display.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; font-style: italic;")
        record_layout.addRow("", self.record_hotkey_display)
        
        layout.addWidget(record_group)
        
        # Quit hotkey
        quit_group = QGroupBox("Quit Hotkey")
        quit_layout = QFormLayout(quit_group)
        quit_layout.setContentsMargins(15, 20, 15, 15)
        quit_layout.setSpacing(10)
        
        self.quit_hotkey_edit = QKeySequenceEdit(
            self.settings.hotkeys.quit_key or QKeySequence()
        )
        self.quit_hotkey_edit.setMaximumSequenceLength(1)
        self.quit_hotkey_edit.setFixedWidth(240)
        self.quit_hotkey_edit.keySequenceChanged.connect(self._update_hotkey_displays)
        quit_layout.addRow("Quit Key:", self.quit_hotkey_edit)

        # Add a display label for showing friendly key representation
        self.quit_hotkey_display = QLabel("")
        self.quit_hotkey_display.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; font-style: italic;")
        quit_layout.addRow("", self.quit_hotkey_display)

        layout.addWidget(quit_group)

        # Process text hotkey (re-runs LLM processing on the last transcription)
        process_group = QGroupBox("Process Text Hotkey")
        process_layout = QFormLayout(process_group)
        process_layout.setContentsMargins(15, 20, 15, 15)
        process_layout.setSpacing(10)

        process_help = self._hint_label(
            "Optional: re-process the most recent transcription with the LLM. "
            "Leave empty to disable."
        )
        process_layout.addRow(process_help)

        self.process_hotkey_edit = QKeySequenceEdit(
            self.settings.hotkeys.process_text_key or QKeySequence()
        )
        self.process_hotkey_edit.setMaximumSequenceLength(1)
        self.process_hotkey_edit.setFixedWidth(240)
        self.process_hotkey_edit.keySequenceChanged.connect(self._update_hotkey_displays)

        clear_process_button = self._secondary_button("Clear")
        clear_process_button.clicked.connect(self.process_hotkey_edit.clear)

        process_key_row = QHBoxLayout()
        process_key_row.setSpacing(8)
        process_key_row.addWidget(self.process_hotkey_edit)
        process_key_row.addWidget(clear_process_button)
        process_key_row.addStretch()
        process_layout.addRow("Process Key:", process_key_row)

        self.process_hotkey_display = QLabel("")
        self.process_hotkey_display.setStyleSheet(f"color: {AppTheme.TEXT_SECONDARY}; font-style: italic;")
        process_layout.addRow("", self.process_hotkey_display)

        layout.addWidget(process_group)

        layout.addStretch()
        
        # Initial update of displays
        self._update_hotkey_displays()
        
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
        self.device_combo.setMinimumWidth(280)
        self.device_combo.setMaximumWidth(420)
        self.device_combo.setMinimumHeight(30)
        self._populate_audio_devices()

        # Mark settings changed but don't call _on_device_changed here to avoid adding duplicate rates

        refresh_button = self._secondary_button("Refresh")
        refresh_button.setToolTip("Rescan available input devices")
        refresh_button.clicked.connect(self._populate_audio_devices)

        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_row.addWidget(self.device_combo)
        device_row.addWidget(refresh_button)
        device_row.addStretch()
        device_layout.addRow("Input Device:", device_row)

        layout.addWidget(device_group)
        
        # Audio settings
        settings_group = QGroupBox("Recording Settings")
        settings_layout = QFormLayout(settings_group)
        settings_layout.setContentsMargins(15, 20, 15, 15)
        settings_layout.setSpacing(10)
        
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.setFixedWidth(240)
        self.sample_rate_combo.setMinimumHeight(30)
        for rate in [8000, 16000, 22050, 32000, 44100, 48000, 96000]:
            self.sample_rate_combo.addItem(f"{rate} Hz", rate)

        # Find and select the current sample rate, adding it if not present
        current_rate_index = self.sample_rate_combo.findData(self.settings.audio.sample_rate)
        if current_rate_index < 0:
            self.sample_rate_combo.addItem(f"{self.settings.audio.sample_rate} Hz", self.settings.audio.sample_rate)
            current_rate_index = self.sample_rate_combo.count() - 1
        self.sample_rate_combo.setCurrentIndex(current_rate_index)

        settings_layout.addRow("Sample Rate:", self.sample_rate_combo)
        
        settings_layout.addRow("", self._hint_label("Higher sample rates provide better audio quality"))

        self.channels_spin = QSpinBox()
        self.channels_spin.setRange(1, 2)
        self.channels_spin.setFixedWidth(80)
        self.channels_spin.setValue(self.settings.audio.channels)
        settings_layout.addRow("Channels:", self.channels_spin)

        settings_layout.addRow("", self._hint_label("1 = Mono, 2 = Stereo"))
        
        layout.addWidget(settings_group)
        layout.addStretch()
        
        return widget
    
    def _create_transcription_tab(self) -> QWidget:
        """Create the transcription tab with all settings for speech recognition."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)

        # Help text at the top
        help_label = QLabel(
            "Choose the speech recognition model and language. "
            "Larger models are more accurate but slower."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Model selection group
        model_group = QGroupBox("Model")
        model_layout = QFormLayout(model_group)
        model_layout.setContentsMargins(15, 20, 15, 15)
        model_layout.setSpacing(10)

        # Model dropdown
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_combo.setCurrentText(self.settings.transcription.model)
        self.model_combo.setFixedWidth(240)
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
        
        self.device_type_combo.setFixedWidth(340)
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
        language_group = QGroupBox("Language")
        language_layout = QFormLayout(language_group)
        language_layout.setContentsMargins(15, 20, 15, 15)
        language_layout.setSpacing(10)

        # Language dropdown — stores ISO codes as item data (None = auto-detect)
        self.language_combo = QComboBox()
        for name, code in LANGUAGE_OPTIONS:
            self.language_combo.addItem(name, code)

        current_language = self.settings.transcription.language
        if current_language and current_language.lower() in _LANGUAGE_NAME_TO_CODE:
            # Legacy settings stored full names — map them to codes
            current_language = _LANGUAGE_NAME_TO_CODE[current_language.lower()]
        language_index = self.language_combo.findData(current_language)
        if language_index < 0:
            # Unknown code (e.g. hand-edited settings file): keep it selectable
            self.language_combo.addItem(current_language, current_language)
            language_index = self.language_combo.count() - 1
        self.language_combo.setCurrentIndex(language_index)

        self.language_combo.setFixedWidth(240)
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
        layout.setSpacing(15)
        
        # Help text at the top
        help_label = QLabel(
            "Process transcriptions with an LLM to fix grammar, summarize, or transform text. "
            "Use {text} in your prompt as a placeholder for the transcribed text."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # LLM Enable/Disable
        enable_group = QGroupBox("Enable LLM Processing")
        enable_layout = QFormLayout(enable_group)
        enable_layout.setContentsMargins(15, 20, 15, 15)
        enable_layout.setSpacing(10)
        
        self.llm_enabled_check = QCheckBox("Enable LLM processing after transcription")
        self.llm_enabled_check.setChecked(self.settings.llm.enabled)
        self.llm_enabled_check.toggled.connect(self._on_llm_enabled_toggled)
        enable_layout.addRow("", self.llm_enabled_check)
        
        layout.addWidget(enable_group)
        
        # ---------- External Server Settings ----------
        self.external_group = QGroupBox("External LLM Server")
        external_layout = QFormLayout(self.external_group)
        external_layout.setContentsMargins(15, 20, 15, 15)
        external_layout.setSpacing(10)
        
        self.llm_api_url_edit = QLineEdit()
        self.llm_api_url_edit.setMinimumWidth(300)
        self.llm_api_url_edit.setMaximumWidth(420)
        self.llm_api_url_edit.setMinimumHeight(30)
        self.llm_api_url_edit.setPlaceholderText("http://localhost:11434/v1")
        
        # Set the current API URL
        if hasattr(self.settings.llm, 'api_url') and self.settings.llm.api_url:
            self.llm_api_url_edit.setText(self.settings.llm.api_url)
        else:
            self.llm_api_url_edit.setText("http://localhost:11434/v1")
        
        external_layout.addRow("API URL:", self.llm_api_url_edit)
        
        # Model dropdown (populated by Test Connection)
        self.llm_model_combo = QComboBox()
        self.llm_model_combo.setEditable(True)  # Allow custom model names
        self.llm_model_combo.setMinimumWidth(300)
        self.llm_model_combo.setMaximumWidth(420)
        self.llm_model_combo.setMinimumHeight(30)
        self.llm_model_combo.lineEdit().setPlaceholderText("Click 'Test Connection' to load models")
        
        if hasattr(self.settings.llm, 'model') and self.settings.llm.model:
            self.llm_model_combo.addItem(self.settings.llm.model)
            self.llm_model_combo.setCurrentText(self.settings.llm.model)
        
        external_layout.addRow("Model:", self.llm_model_combo)
        
        # Authentication fields (for reverse proxy like Pangolin)
        external_layout.addRow("", self._hint_label("Authentication (optional, for reverse proxy)"))

        self.llm_username_edit = QLineEdit()
        self.llm_username_edit.setMinimumWidth(300)
        self.llm_username_edit.setMaximumWidth(420)
        self.llm_username_edit.setMinimumHeight(30)
        self.llm_username_edit.setPlaceholderText("Username (leave empty if not required)")

        if self.settings.llm.api_username:
            self.llm_username_edit.setText(self.settings.llm.api_username)

        external_layout.addRow("Username:", self.llm_username_edit)

        self.llm_password_edit = QLineEdit()
        self.llm_password_edit.setMinimumWidth(300)
        self.llm_password_edit.setMaximumWidth(420)
        self.llm_password_edit.setMinimumHeight(30)
        self.llm_password_edit.setPlaceholderText("Password (leave empty if not required)")
        self.llm_password_edit.setEchoMode(QLineEdit.Password)  # Hide password

        if self.settings.llm.api_password:
            self.llm_password_edit.setText(self.settings.llm.api_password)

        external_layout.addRow("Password:", self.llm_password_edit)

        external_desc = self._hint_label("Test the connection to verify the server and load available models.")
        external_layout.addRow("", external_desc)

        layout.addWidget(self.external_group)

        # Button row for test and warm up — deliberately OUTSIDE the group
        # gated by the enable checkbox, so the server can be tested before
        # LLM processing is switched on
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        test_button = self._secondary_button("Test Connection && Load Models")
        test_button.clicked.connect(self._test_llm_connection)
        button_layout.addWidget(test_button)

        warmup_button = self._secondary_button("Warm Up Model")
        warmup_button.setToolTip("Send a test request to load the model into memory (may take 1-2 minutes)")
        warmup_button.clicked.connect(self._warm_up_model)
        button_layout.addWidget(warmup_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # ---------- System Prompt ----------
        prompt_group = QGroupBox("System Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        prompt_layout.setContentsMargins(15, 20, 15, 15)
        prompt_layout.setSpacing(10)
        
        prompt_desc = self._hint_label("Enter your prompt below. Use {text} as a placeholder for the transcribed text.")
        prompt_layout.addWidget(prompt_desc)
        
        self.custom_prompt_edit = QTextEdit()
        self.custom_prompt_edit.setMinimumHeight(100)
        self.custom_prompt_edit.setPlaceholderText(DEFAULT_LLM_PROMPT)

        # Set the current custom prompt
        self.custom_prompt_edit.setText(self.settings.llm.custom_prompt or DEFAULT_LLM_PROMPT)

        prompt_layout.addWidget(self.custom_prompt_edit)
        
        layout.addWidget(prompt_group)
        
        # Disable all settings if LLM is not enabled
        self._update_llm_settings_enabled(self.settings.llm.enabled)
        
        layout.addStretch()
        
        # Wrap in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.addWidget(scroll_area)
        
        return scroll_widget
    
    def _update_llm_settings_enabled(self, enabled: bool):
        """Enable or disable LLM settings based on the main checkbox"""
        self.external_group.setEnabled(enabled)
        # Find prompt group and enable/disable it
        for child in self.findChildren(QGroupBox):
            if child.title() == "System Prompt":
                child.setEnabled(enabled)
                break
    
    def _ensure_llm_settings_initialized(self):
        """Ensure LLM settings are initialized with default values if missing"""
        if not hasattr(self.settings, 'llm') or self.settings.llm is None:
            from ...domain.settings import LLMSettings
            self.settings.llm = LLMSettings()
    
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
        self.show_notif_check.setChecked(self.settings.appearance.show_notifications)
        notif_layout.addRow("", self.show_notif_check)

        layout.addWidget(notif_group)

        # Output behavior settings
        output_group = QGroupBox("Transcription Output")
        output_layout = QFormLayout(output_group)
        output_layout.setContentsMargins(15, 20, 15, 15)
        output_layout.setSpacing(10)

        self.clipboard_check = QCheckBox("Auto-copy transcription to clipboard")
        self.clipboard_check.setChecked(self.settings.appearance.auto_copy_to_clipboard)
        output_layout.addRow("", self.clipboard_check)

        self.auto_paste_check = QCheckBox("Auto-paste transcription into active text field")
        self.auto_paste_check.setChecked(self.settings.appearance.auto_paste)
        output_layout.addRow("", self.auto_paste_check)

        layout.addWidget(output_group)
        
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

        # Repopulating fires currentIndexChanged for every clear/add — block
        # signals so a device refresh doesn't count as a settings change.
        previous_selection = self.device_combo.currentData()
        self.device_combo.blockSignals(True)
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
        
        # On refresh, keep whatever the user had selected if it still exists
        if previous_selection is not None:
            previous_index = self.device_combo.findData(previous_selection)
            if previous_index >= 0:
                self.device_combo.setCurrentIndex(previous_index)

        self.device_combo.blockSignals(False)

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
                        # Reuse an existing entry for this rate if one was already added
                        existing_index = self.sample_rate_combo.findData(default_sample_rate)
                        if existing_index < 0:
                            self.sample_rate_combo.addItem(f"{default_sample_rate} Hz (device default)", default_sample_rate)
                            existing_index = self.sample_rate_combo.count() - 1
                        self.sample_rate_combo.setCurrentIndex(existing_index)
                    else:
                        self.sample_rate_combo.setCurrentIndex(closest_index)
                        
                    logger.debug(f"Selected sample rate {self.sample_rate_combo.currentText()} for device {device_name}")
        except Exception as e:
            logger.error(f"Error updating sample rate for device: {e}")
    
    @Slot()
    def _save_settings(self):
        """Save settings to the repository when the Save button is clicked"""
        logger.debug("Saving settings")
        
        # 1. Hotkeys tab
        if hasattr(self, 'record_hotkey_edit'):
            # Get the key sequence from the editor
            record_key = self.record_hotkey_edit.keySequence()
            record_key_str = record_key.toString()

            # The record hotkey is required — without it the app can't record
            if record_key.isEmpty():
                QMessageBox.warning(
                    self,
                    "Record Hotkey Required",
                    "The record hotkey cannot be empty. Please set a key combination for recording."
                )
                return
            
            # On macOS, ensure that if "Ctrl" is used, we mention this might not work as expected
            import platform
            if platform.system() == "Darwin":
                if "Ctrl" in record_key_str and "Meta" not in record_key_str:
                    confirm = QMessageBox.question(
                        self,
                        "Confirm Control Key Usage",
                        "You've selected a shortcut using the Control key. On macOS, the Command key (⌘) "
                        "is typically used for shortcuts.\n\n"
                        "Do you want to continue with the Control key? Choose 'No' to use Command instead.",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if confirm == QMessageBox.No:
                        # Replace Ctrl with Meta (Command) in the key sequence
                        new_key_str = record_key_str.replace("Ctrl", "Meta")
                        logger.info(f"Converting key sequence from {record_key_str} to {new_key_str}")
                        record_key = QKeySequence(new_key_str)
                        
                        # Use our helper method to get a friendly display
                        friendly_display = self.get_macos_friendly_key_display(record_key)
                        logger.debug(f"Friendly display for macOS: {friendly_display}")
                        
                        # Show confirmation to the user
                        QMessageBox.information(
                            self,
                            "Hotkey Updated",
                            f"Your hotkey has been converted to use Command instead of Control: {friendly_display}"
                        )
                
                # Log raw key data for debugging
                logger.debug(f"Final key sequence for record hotkey: {record_key.toString()}")
            
            self.settings.hotkeys.record_key = record_key
            
        if hasattr(self, 'quit_hotkey_edit'):
            quit_key = self.quit_hotkey_edit.keySequence()
            
            # Apply the same macOS normalization to quit key if needed
            import platform
            if platform.system() == "Darwin" and "Ctrl" in quit_key.toString() and "Meta" not in quit_key.toString():
                confirm = QMessageBox.question(
                    self,
                    "Confirm Control Key Usage for Quit",
                    "You've selected a quit shortcut using the Control key. On macOS, the Command key (⌘) "
                    "is typically used for shortcuts.\n\n"
                    "Do you want to continue with the Control key? Choose 'No' to use Command instead.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if confirm == QMessageBox.No:
                    # Replace Ctrl with Meta (Command) in the key sequence
                    new_key_str = quit_key.toString().replace("Ctrl", "Meta")
                    logger.info(f"Converting quit key sequence from {quit_key.toString()} to {new_key_str}")
                    quit_key = QKeySequence(new_key_str)
                    
                    # Use our helper method to get a friendly display
                    friendly_display = self.get_macos_friendly_key_display(quit_key)
                    logger.debug(f"Friendly display for macOS quit key: {friendly_display}")
                    
                    # Show confirmation to the user
                    QMessageBox.information(
                        self,
                        "Quit Hotkey Updated",
                        f"Your quit hotkey has been converted to use Command instead of Control: {friendly_display}"
                    )
            
            # Log raw key data for debugging
            logger.debug(f"Final key sequence for quit hotkey: {quit_key.toString()}")
            self.settings.hotkeys.quit_key = quit_key if not quit_key.isEmpty() else None

        if hasattr(self, 'process_hotkey_edit'):
            process_key = self.process_hotkey_edit.keySequence()
            self.settings.hotkeys.process_text_key = process_key if not process_key.isEmpty() else None
        
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
            # Item data holds the ISO code; None means auto-detect
            self.settings.transcription.language = self.language_combo.currentData()
                
        # Log key settings that are being saved
        logger.info(f"Saving settings with values: "
                   f"quit_key={self.settings.hotkeys.quit_key.toString() if self.settings.hotkeys.quit_key else 'None'}, "
                   f"record_key={self.settings.hotkeys.record_key.toString()}, "
                   f"input_device={self.settings.audio.input_device}, " 
                   f"sample_rate={self.settings.audio.sample_rate}")
        
        # 4. LLM tab
        if hasattr(self, 'llm_enabled_check'):
            # Ensure LLM settings exist
            if not self.settings.llm:
                from ...domain.settings import LLMSettings
                self.settings.llm = LLMSettings()
            
            self.settings.llm.enabled = self.llm_enabled_check.isChecked()

            # Save external API settings
            if hasattr(self, 'llm_api_url_edit'):
                self.settings.llm.api_url = self.llm_api_url_edit.text().strip()
                if not self.settings.llm.api_url:
                    self.settings.llm.api_url = "http://localhost:11434/v1"

            if hasattr(self, 'llm_model_combo'):
                self.settings.llm.model = self.llm_model_combo.currentText().strip()
                if not self.settings.llm.model:
                    self.settings.llm.model = "llama3.2"

            # Save authentication credentials
            if hasattr(self, 'llm_username_edit'):
                self.settings.llm.api_username = self.llm_username_edit.text().strip()
            if hasattr(self, 'llm_password_edit'):
                self.settings.llm.api_password = self.llm_password_edit.text()
            
            # Save custom prompt (fall back to the default if left empty)
            if hasattr(self, 'custom_prompt_edit'):
                prompt = self.custom_prompt_edit.toPlainText().strip()
                self.settings.llm.custom_prompt = prompt if prompt else DEFAULT_LLM_PROMPT
        
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
            self._initial_ui_state = self._ui_state()  # Saved state is the new baseline

            # Close the window
            self.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")
            return

    def _on_llm_enabled_toggled(self, enabled):
        """Handle LLM enabled checkbox toggle"""
        self._update_llm_settings_enabled(enabled)
    
    def _llm_request_params(self):
        """Normalized API URL and auth from the current form values."""
        from requests.auth import HTTPBasicAuth

        api_url = self.llm_api_url_edit.text().strip().rstrip('/')
        if not api_url:
            api_url = "http://localhost:11434/v1"
        if not api_url.endswith('/v1'):
            api_url = f"{api_url}/v1"

        username = self.llm_username_edit.text().strip()
        password = self.llm_password_edit.text()
        auth = HTTPBasicAuth(username, password) if username and password else None
        return api_url, auth

    def _run_async(self, work, on_done, title: str, text: str):
        """Run `work` in a background thread with a modal progress dialog.

        Network calls must never run on the Qt main thread — a slow or
        unreachable server would freeze the whole window. `on_done(ok, value)`
        is called on the main thread with (True, result) or (False, exception).
        """
        import threading
        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog(text, "Cancel", 0, 0, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        state = {"result": None, "cancelled": False}

        def runner():
            try:
                state["result"] = (True, work())
            except Exception as e:
                state["result"] = (False, e)

        def poll():
            if state["cancelled"]:
                return
            if state["result"] is None:
                QTimer.singleShot(200, poll)
                return
            progress.close()
            ok, value = state["result"]
            on_done(ok, value)

        def on_cancelled():
            state["cancelled"] = True
            progress.close()

        progress.canceled.connect(on_cancelled)
        threading.Thread(target=runner, daemon=True, name="SettingsNetworkTask").start()
        QTimer.singleShot(200, poll)

    def _test_llm_connection(self):
        """Test the LLM server connection and load available models."""
        import requests

        api_url, auth = self._llm_request_params()
        base_url = api_url[:-3] if api_url.endswith('/v1') else api_url

        def work():
            response = requests.get(base_url, timeout=5, auth=auth, allow_redirects=True)
            status_code = response.status_code

            models = []
            if status_code not in (401, 403):
                try:
                    models_response = requests.get(f"{api_url}/models", timeout=5, auth=auth)
                    if models_response.status_code == 200:
                        data = models_response.json()
                        models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                except requests.exceptions.RequestException:
                    pass  # Models endpoint might not exist, that's okay
            return status_code, models

        def on_done(ok, value):
            if not ok:
                if isinstance(value, requests.exceptions.Timeout):
                    QMessageBox.warning(
                        self,
                        "Connection Timeout",
                        f"Connection to {base_url} timed out after 5 seconds.\n\nThe server may be slow or unreachable.",
                        QMessageBox.Ok
                    )
                elif isinstance(value, requests.exceptions.ConnectionError):
                    QMessageBox.critical(
                        self,
                        "Connection Failed",
                        f"Could not connect to {base_url}\n\nPlease check:\n- The URL is correct\n- The server is running\n- Any firewalls or proxies",
                        QMessageBox.Ok
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Connection Error",
                        f"Error connecting to LLM server: {value}",
                        QMessageBox.Ok
                    )
                return

            status_code, models = value
            if status_code in (401, 403):
                QMessageBox.warning(
                    self,
                    "Authentication Required",
                    f"Server responded with status {status_code}.\n\nThe server is reachable but requires authentication.\nPlease check your username and password.",
                    QMessageBox.Ok
                )
                return

            models_list = ""
            if models:
                models_list = "\n\nAvailable models:\n• " + "\n• ".join(models[:10])
                if len(models) > 10:
                    models_list += f"\n... and {len(models) - 10} more"

                current_model = self.llm_model_combo.currentText()
                self.llm_model_combo.clear()
                self.llm_model_combo.addItems(models)
                if current_model in models:
                    self.llm_model_combo.setCurrentText(current_model)
                else:
                    self.llm_model_combo.setCurrentIndex(0)
                models_list += "\n\n✓ Model dropdown has been populated!"

            QMessageBox.information(
                self,
                "Connection Successful",
                f"Successfully connected to LLM server!\n\nURL: {api_url}\nStatus: {status_code}{models_list}",
                QMessageBox.Ok
            )

        self._run_async(work, on_done, "Testing Connection", f"Connecting to {base_url}...")

    def _warm_up_model(self):
        """Send a test request to warm up the model (load it into VRAM)"""
        import requests

        model = self.llm_model_combo.currentText().strip()
        if not model:
            QMessageBox.warning(
                self,
                "No Model Selected",
                "Please select a model first.\n\nUse 'Test Connection & Load Models' to populate the model list.",
                QMessageBox.Ok
            )
            return

        api_url, auth = self._llm_request_params()

        def work():
            response = requests.post(
                f"{api_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5
                },
                timeout=120,
                auth=auth
            )
            return response

        def on_done(ok, value):
            if ok and value.status_code == 200:
                QMessageBox.information(
                    self,
                    "Model Ready",
                    f"Model '{model}' is now warmed up and ready to use!",
                    QMessageBox.Ok
                )
                return

            if not ok:
                if isinstance(value, requests.exceptions.Timeout):
                    message = ("Request timed out after 2 minutes.\n"
                               "The model may be very large or the server is slow.")
                elif isinstance(value, requests.exceptions.ConnectionError):
                    message = "Could not connect to the server."
                else:
                    message = str(value)
            else:
                message = f"Error: {value.text[:200] if value.text else f'Status {value.status_code}'}"

            QMessageBox.warning(
                self,
                "Warm Up Failed",
                f"Failed to warm up model '{model}':\n\n{message}",
                QMessageBox.Ok
            )

        self._run_async(
            work, on_done,
            "Warming Up Model",
            f"Warming up model '{model}'...\n\nThis may take 1-2 minutes on first load."
        )

    def closeEvent(self, event):
        """Handle the window close event"""
        # If Save button was clicked, accept the close event
        if self.save_requested:
            self.save_requested = False  # Reset for next time
            event.accept()
            return

        # If nothing actually differs from the state the window opened with,
        # close without nagging
        if not self._has_unsaved_changes():
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

    @staticmethod
    def get_macos_friendly_key_display(key_sequence: QKeySequence) -> str:
        """
        Convert a QKeySequence to a macOS-friendly display string with proper symbols.
        
        Args:
            key_sequence: The QKeySequence to convert
            
        Returns:
            str: A string representation with macOS symbols
        """
        if not key_sequence:
            return ""
            
        # Get the key sequence as a string
        key_str = key_sequence.toString()
        
        # Map keys to macOS symbols
        key_map = {
            "Meta": "⌘",  # Command
            "Ctrl": "⌃",  # Control
            "Alt": "⌥",   # Option
            "Shift": "⇧",  # Shift
            "Return": "↩",  # Return/Enter
            "Escape": "⎋",  # Escape
            "Backspace": "⌫",  # Delete left
            "Delete": "⌦",  # Delete right
            "Tab": "⇥",  # Tab
        }
        
        # Replace keys with symbols
        for key, symbol in key_map.items():
            key_str = key_str.replace(key, symbol)
            
        return key_str
        
    def _update_hotkey_displays(self):
        """Update the hotkey displays with user-friendly representations"""
        import platform
        if platform.system() != "Darwin":
            return

        pairs = [
            ('record_hotkey_edit', 'record_hotkey_display'),
            ('quit_hotkey_edit', 'quit_hotkey_display'),
            ('process_hotkey_edit', 'process_hotkey_display'),
        ]
        for edit_attr, display_attr in pairs:
            edit = getattr(self, edit_attr, None)
            display = getattr(self, display_attr, None)
            if edit is None or display is None:
                continue
            friendly_display = self.get_macos_friendly_key_display(edit.keySequence())
            display.setText(f"Current: {friendly_display}" if friendly_display else "")
