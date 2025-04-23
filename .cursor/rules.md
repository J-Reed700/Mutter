# Project Organization Rules

## Entry Points
- `src/main.py` - Application bootstrap and initialization

## Infrastructure

### Hotkeys
- `src/infrastructure/hotkeys/*.py` - Global hotkey handling across platforms
- `src/infrastructure/hotkeys/windows.py` - Windows-specific hotkey implementation using Win32 API
- `src/infrastructure/hotkeys/base.py` - Abstract base class for hotkey handlers

### Audio
- `src/infrastructure/audio/*.py` - Audio recording and processing functionality
- `src/infrastructure/audio/recorder.py` - Thread-safe audio recording implementation

### Transcription
- `src/infrastructure/transcription/*.py` - Speech-to-text conversion services
- `src/infrastructure/transcription/transcriber.py` - Faster-Whisper based transcription implementation

### Persistence
- `src/infrastructure/persistence/*.py` - Data storage and settings management

### Services
- `src/infrastructure/services/*.py` - Infrastructure service implementations
- `src/infrastructure/services/recording_service.py` - Recording service coordinating audio and transcription

## Presentation

### System Tray
- `src/presentation/system_tray.py` - System tray icon and menu implementation

### Windows
- `src/presentation/windows/*.py` - Application windows and dialogs
- `src/presentation/windows/settings.py` - Settings window and configuration UI

### Resources
- `src/presentation/resources/**/*` - UI resources like icons and images

## Domain
- `src/domain/*.py` - Core business logic and data models
- `src/domain/settings.py` - Settings data models and validation

## Application
- `src/application/*.py` - Application services and use cases
- `src/application/recording_service.py` - Recording service orchestration

## Tests
- `tests/unit/**/*.py` - Unit tests for individual components
- `tests/integration/**/*.py` - Integration tests between components

## Package
- `**/__init__.py` - Package initialization files

## Configuration
- `pyproject.toml` - Project configuration and dependencies
- `poetry.lock` - Locked dependencies for reproducible builds

## Documentation
- `README.md` - Project documentation
- `docs/**/*` - Detailed documentation files

## Scripts
- `scripts/**/*.py` - Utility scripts and tools
- `scripts/dev.py` - Development helper scripts

## External Dependencies
- `.venv/Lib/site-packages/faster_whisper/**/*.py` - Faster-Whisper library implementation
- `.venv/Lib/site-packages/PySide6/**/*.py*` - PySide6 Qt bindings

## Coding Conventions

### Naming
- Classes: PascalCase
- Methods: snake_case
- Constants: UPPER_SNAKE_CASE
- Private members: _leading_underscore

### Structure
- Maximum file length: 500 lines
- Maximum class length: 300 lines
- Maximum method length: 50 lines
- Maximum parameters: 5

### Documentation
Required sections:
- Args
- Returns
- Raises

### Architecture
Dependencies:
- Domain: No dependencies
- Application: Depends on Domain
- Infrastructure: Depends on Domain and Application
- Presentation: Depends on Domain and Application

### Threading Guidelines
- Use locks for shared resources
- Avoid blocking the main thread
- Clean up threads on shutdown

### Error Handling
- Log all exceptions
- Use specific exception types
- Provide meaningful error messages 