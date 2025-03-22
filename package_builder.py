import os
import sys
import platform
import subprocess
import shutil

def build_executable():
    # Create a 'build' directory if it doesn't exist
    if not os.path.exists('build'):
        os.makedirs('build')
    
    # Create a 'dist' directory if it doesn't exist
    if not os.path.exists('dist'):
        os.makedirs('dist')
    
    # Determine the platform
    system = platform.system()
    
    # Base PyInstaller command
    cmd = [
        'pyinstaller',
        '--name=VoiceRecorder',
        '--windowed',  # No console window
        '--onefile',   # Single executable file
        '--clean',     # Clean PyInstaller cache
        '--noconfirm', # Replace output directory without asking
    ]
    
    # Add icon based on platform
    if system == 'Windows':
        # Add Windows-specific options
        cmd.append('--icon=resources/icons/app.ico')
        # Add Windows version info
        cmd.append('--version-file=version_info.txt')
    elif system == 'Darwin':  # macOS
        # Add macOS-specific options
        cmd.append('--icon=resources/icons/app.icns')
        # Add Info.plist
        cmd.append('--osx-bundle-identifier=com.yourcompany.voicerecorder')
    
    # Add the main script
    cmd.append('src/main.py')
    
    # Run PyInstaller
    subprocess.run(cmd)
    
    # Post-processing for macOS to create DMG
    if system == 'Darwin':
        create_dmg()

def create_dmg():
    """Create a DMG file for macOS"""
    try:
        # Check if create-dmg is installed
        subprocess.run(['which', 'create-dmg'], check=True)
        
        # Create DMG
        subprocess.run([
            'create-dmg',
            '--volname', 'VoiceRecorder',
            '--volicon', 'resources/icons/app.icns',
            '--window-pos', '200', '120',
            '--window-size', '800', '400',
            '--icon-size', '100',
            '--icon', 'VoiceRecorder.app', '200', '200',
            '--hide-extension', 'VoiceRecorder.app',
            '--app-drop-link', '600', '200',
            'dist/VoiceRecorder.dmg',
            'dist/VoiceRecorder.app'
        ])
        print("DMG created successfully!")
    except subprocess.CalledProcessError:
        print("Warning: create-dmg not found. Install it with 'brew install create-dmg' to create DMG files.")
    except Exception as e:
        print(f"Error creating DMG: {e}")

if __name__ == "__main__":
    build_executable() 