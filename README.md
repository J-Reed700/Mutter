# Mutter

A powerful voice recording application with local speech-to-text transcription. Press a hotkey to start recording, release to transcribe automatically.

## Features

- Global hotkey to start/stop recording
- Local speech-to-text transcription using Whisper
- System tray integration for easy access
- Automatic clipboard copy of transcriptions

## Installation

### Prerequisites

- Python 3.10 or lower
- Poetry for dependency management
- PySide6 for the GUI
- faster-whisper for transcription

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/J-Reed700/Mutter

2. Install Python 3.11
   https://www.python.org/downloads/release/python-3110/

   ```
   winget install -e --id Python.Python.3.11
   ```

3. Install Poetry:
    ```
    pip install poetry
    ```

4. Install the dependencies using Poetry:
   ```
   Optional: Lock the dependencies
   python -m poetry lock
   ```

   ```
   python -m poetry install
   ```

5. Activate the virtual environment created by Poetry:
   ```
   python -m poetry shell
   ```

## Usage

1. Run the application:
   ```
   poetry run python -m src.main
   ```

2. The application will start in the system tray.

3. Press `Ctrl+Shift+R` (default hotkey) to start recording.

4. Press `Ctrl+Shift+R` again to stop recording and start transcription.

5. The transcription will appear in a notification and can be copied to clipboard. As well as pasted into your favorite text editor or chat application.

6. You can press `Ctrl+Shift+Q` to quit the application.


## Configuration

- Click on the system tray icon and select "Settings" to configure:
  - Hotkeys, (Ctrl+Shift+R to start/stop recording, Ctrl+Shift+Q to quit)
  - Audio settings
  - Transcription model (larger models are more accurate)
  - Language settings

## Building Executables

To build standalone executables:

```
python build_executable.py
```

Note: The default build does NOT include local LLM dependencies (PyTorch/Transformers) to keep the package size manageable. If you need embedded LLM functionality, make sure to uncomment the corresponding lines in requirements.txt before building.

## Audio Device Selection

Mutter supports various audio input devices and handles multiple devices with the same name. The application:

1. **Displays details about each audio device** in the settings menu, including:
   - Device name
   - Audio API type (WASAPI, DirectSound, etc. on Windows)
   - Channel count
   - Sample rate

2. **Automatically detects and suggests optimal sample rates** when you select a device, setting the sample rate to match the device's native sample rate.

3. **Prioritizes high-quality audio APIs** when multiple devices with the same name exist:
   - On Windows, WASAPI is preferred over DirectSound and WDM-KS
   - This ensures better audio quality and compatibility

4. **Dynamically adjusts to device capabilities** by validating that the selected sample rate is supported by the device.

If you experience issues with audio recording:
- Try selecting a different audio API for your device (e.g., WASAPI vs DirectSound)
- Check that the sample rate matches what your device supports
- Use the "Default" device option to use the system's default settings
