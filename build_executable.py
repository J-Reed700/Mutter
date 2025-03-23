"""
Build script for the Memo application.
This script handles the packaging of the application using PyInstaller.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Constants
APP_NAME = "Memo"
DIST_DIR = "dist"
BUILD_DIR = "build"
SPEC_FILE = "Memo.spec"
HOOKS_DIR = "hooks"


def clean_build_dirs():
    """Clean up previous build artifacts"""
    print("Cleaning build directories...")
    for dir_name in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Removed {dir_name} directory")


def setup_hooks():
    """Set up hooks for PyInstaller"""
    if not os.path.exists(HOOKS_DIR):
        os.makedirs(HOOKS_DIR)
        print(f"Created {HOOKS_DIR} directory")
    
    # Copy hook file for faster_whisper if it exists
    hook_file = "hook-faster_whisper.py"
    if os.path.exists(hook_file):
        shutil.copy(hook_file, os.path.join(HOOKS_DIR, hook_file))
        print(f"Copied {hook_file} to {HOOKS_DIR}")


def run_pyinstaller():
    """Run PyInstaller to build the executable"""
    print(f"Building {APP_NAME} executable...")
    
    # Update spec file to use hooks directory
    with open(SPEC_FILE, 'r') as f:
        spec_content = f.read()
    
    # Add hooks directory to spec if needed
    if 'hookspath=[]' in spec_content:
        spec_content = spec_content.replace('hookspath=[]', f'hookspath=["{HOOKS_DIR}"]')
        with open(SPEC_FILE, 'w') as f:
            f.write(spec_content)
        print(f"Updated {SPEC_FILE} to include hooks directory")
    
    # Run PyInstaller with the spec file
    cmd = ["python", "-m", "poetry", "run", "pyinstaller", SPEC_FILE, "--clean"]
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error building executable:\n{result.stderr}")
        return False
    
    print(f"Successfully built {APP_NAME} executable")
    print(f"Output logs:\n{result.stdout}")
    return True


def copy_additional_files():
    """Copy any additional required files to the distribution directory"""
    # Create a models directory in the distribution directory
    dist_models_dir = os.path.join(DIST_DIR, APP_NAME, "models")
    if not os.path.exists(dist_models_dir):
        os.makedirs(dist_models_dir)
        print(f"Created models directory in {DIST_DIR}/{APP_NAME}")
    
    # Add a README file to the distribution
    readme_content = f"""
{APP_NAME} - Voice Recording and Transcription Application

This application allows you to record audio and transcribe it to text.
Models for transcription will be downloaded automatically on first use.

To run the application, double-click on {APP_NAME}.exe
"""
    with open(os.path.join(DIST_DIR, APP_NAME, "README.txt"), 'w') as f:
        f.write(readme_content)
    print("Added README.txt to distribution")


def create_installer():
    """Create an installer for the application using NSIS (if available)"""
    # This could be implemented later if needed
    print("Installer creation feature not implemented yet")
    print(f"You can distribute the entire {DIST_DIR}/{APP_NAME} directory")


def main():
    """Main build process"""
    print(f"=== Building {APP_NAME} Application ===")
    
    clean_build_dirs()
    setup_hooks()
    
    if run_pyinstaller():
        copy_additional_files()
        
        print("\n=== Build Complete ===")
        print(f"The executable is available at: {DIST_DIR}/{APP_NAME}/{APP_NAME}.exe")
        
        create_installer_yn = input("Would you like to create an installer? (y/n): ")
        if create_installer_yn.lower() == 'y':
            create_installer()
    else:
        print("\n=== Build Failed ===")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 