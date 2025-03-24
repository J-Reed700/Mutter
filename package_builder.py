import os
import sys
import platform
import subprocess
import shutil
import argparse

def build_executable(include_llm=False):
    """
    Build the executable for the current platform
    
    Args:
        include_llm (bool): Whether to include LLM dependencies (torch, transformers)
    """
    # Create a 'build' directory if it doesn't exist
    if not os.path.exists('build'):
        os.makedirs('build')
    
    # Create a 'dist' directory if it doesn't exist
    if not os.path.exists('dist'):
        os.makedirs('dist')
    
    # Determine the platform
    system = platform.system()
    
    # Update requirements.txt to include or exclude LLM deps
    update_requirements(include_llm)
    
    # Suffix for the executable name
    suffix = "_with_llm" if include_llm else ""
    
    # Base PyInstaller command
    cmd = [
        'pyinstaller',
        f'--name=Mutter{suffix}',
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
        cmd.append('--osx-bundle-identifier=com.yourcompany.Mutter')
    
    # Add the main script
    cmd.append('src/main.py')
    
    # Run PyInstaller
    print(f"Building executable {'with' if include_llm else 'without'} LLM dependencies...")
    subprocess.run(cmd)
    
    # Post-processing for macOS to create DMG
    if system == 'Darwin':
        create_dmg(suffix)
    
    # Restore requirements.txt
    update_requirements(False)
    print("Build complete!")

def update_requirements(include_llm):
    """Toggle LLM dependencies in requirements.txt"""
    # Read requirements.txt
    with open('requirements.txt', 'r') as f:
        lines = f.readlines()
    
    # Write updated requirements.txt
    with open('requirements.txt', 'w') as f:
        for line in lines:
            if line.strip().startswith('# torch>=') or line.strip().startswith('# transformers>='):
                # Include or exclude LLM dependencies
                if include_llm:
                    f.write(line.replace('# ', ''))
                else:
                    f.write(line)
            else:
                f.write(line)

def create_dmg(suffix=""):
    """Create a DMG file for macOS"""
    try:
        # Check if create-dmg is installed
        subprocess.run(['which', 'create-dmg'], check=True)
        
        # Create DMG
        subprocess.run([
            'create-dmg',
            '--volname', f'Mutter{suffix}',
            '--volicon', 'resources/icons/app.icns',
            '--window-pos', '200', '120',
            '--window-size', '800', '400',
            '--icon-size', '100',
            '--icon', f'Mutter{suffix}.app', '200', '200',
            '--hide-extension', f'Mutter{suffix}.app',
            '--app-drop-link', '600', '200',
            f'dist/Mutter{suffix}.dmg',
            f'dist/Mutter{suffix}.app'
        ])
        print("DMG created successfully!")
    except subprocess.CalledProcessError:
        print("Warning: create-dmg not found. Install it with 'brew install create-dmg' to create DMG files.")
    except Exception as e:
        print(f"Error creating DMG: {e}")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Build Mutter executable')
    parser.add_argument('--with-llm', action='store_true', 
                      help='Include LLM dependencies (torch, transformers)')
    args = parser.parse_args()
    
    # Build executable
    build_executable(include_llm=args.with_llm) 