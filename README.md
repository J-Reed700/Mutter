# Mutter

A powerful voice recording application with local speech-to-text transcription. Press a hotkey to start recording, release to transcribe automatically.

## Features

- Global hotkey to start/stop recording
- Local speech-to-text transcription using Whisper
- System tray integration for easy access
- Automatic clipboard copy of transcriptions
- Optional LLM processing for summarization (requires additional dependencies)
- Cross-platform support (Windows, macOS coming soon)

## Installation

### Prerequisites

- Python 3.10 or lower
- Poetry for dependency management
- PySide6 for the GUI
- faster-whisper for transcription

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/voice-recorder.git
   cd voice-recorder

   ```
2. Install Poetry:
    ```
    pip install poetry
    ```

3. Install the dependencies using Poetry:

   # Optional: Lock the dependencies
   ```
   python -m poetry lock
   ```
   ```
   # For basic functionality (without local LLM processing)
   python -m poetry install
   
   # To include local LLM processing capabilities (requires more resources)
   python -m poetry install --extras llm
   ```

4. Activate the virtual environment created by Poetry:
   ```
   python -m poetry shell
   ```

### Optional LLM Processing

The application supports two modes for LLM processing:

1. **External API Mode** (Default, no extra dependencies): 
   - Uses a local LLM API server (like Ollama) at http://localhost:8080/v1
   - Requires you to run an LLM server separately

2. **Embedded Mode** (Requires additional dependencies):
   - Uses PyTorch and Transformers libraries to run models directly in the app
   - Requires more system resources (especially for larger models)
   - Install with `python -m poetry install --extras llm` or manually install torch/transformers

If you're using the application on multiple machines:
- For your main/powerful machine: Install with LLM extras for full functionality
- For secondary/less powerful machines: Install only the basic dependencies and use External API mode

## Usage

1. Run the application:
   ```
   python -m poetry run python -m src.main
   ```

2. The application will start in the system tray.

3. Press `Ctrl+Shift+R` (default hotkey) to start recording.

4. Release the hotkey to stop recording and start transcription.

5. The transcription will appear in a notification and can be copied to clipboard.

6. Press `Ctrl+Shift+R` again to start recording again.

7. You can now paste the transcription into your favorite text editor or chat application.

8. You can press `Ctrl+Shift+Q` to quit the application.

### LLM Processing, Added in future updates

1. To use LLM processing, you need to have an LLM server running.

2. The default server is Ollama, but you can use any other LLM server that supports the API.

3. You can configure the server in the settings.

4. You can also use the `python -m poetry install --extras llm` command to install the LLM dependencies and run the application with embedded LLM processing.


## Configuration

- Click on the system tray icon and select "Settings" to configure:
  - Hotkeys
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
