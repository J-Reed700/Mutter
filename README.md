# Voice Recorder

A powerful voice recording application with local speech-to-text transcription. Press a hotkey to start recording, release to transcribe automatically.

## Features

- Global hotkey to start/stop recording
- Local speech-to-text transcription using Whisper
- System tray integration for easy access
- Automatic clipboard copy of transcriptions
- Cross-platform support (Windows, macOS coming soon)

## Installation

### Prerequisites

- Python 3.8 or higher
- PySide6 for the GUI
- faster-whisper for transcription

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/voice-recorder.git
   cd voice-recorder
   ```

2. Create a virtual environment:
   ```
   python -m venv .venv
   ```

3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`

4. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```
   python -m src.main
   ```

2. The application will start in the system tray.

3. Press `Ctrl+Shift+R` (default hotkey) to start recording.

4. Release the hotkey to stop recording and start transcription.

5. The transcription will appear in a notification and can be copied to clipboard.

## Configuration

- Click on the system tray icon and select "Settings" to configure:
  - Hotkeys
  - Audio settings
  - Transcription model (larger models are more accurate)
  - Language settings

## Building Executables

To build standalone executables:

```
python package_builder.py
```

The executable will be created in the `dist` directory.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - Optimized Whisper implementation
- [PySide6](https://wiki.qt.io/Qt_for_Python) - Qt bindings for Python 