from pathlib import Path

def setup_project():
    # Create all necessary directories
    dirs = [
        "src/domain",
        "src/application",
        "src/infrastructure/audio",
        "src/infrastructure/hotkeys",
        "src/infrastructure/transcription",
        "src/infrastructure/persistence",
        "src/presentation/windows",
        "resources/icons",
        "tests"
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    # Create empty __init__.py files
    for dir_path in dirs:
        init_file = Path(dir_path) / "__init__.py"
        init_file.touch(exist_ok=True)

if __name__ == "__main__":
    setup_project() 