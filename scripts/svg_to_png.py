#!/usr/bin/env python
"""
Script to convert SVG files to PNG files for the application.
Requires cairosvg to be installed.
"""

import os
import sys
from pathlib import Path

try:
    import cairosvg
except ImportError:
    print("Error: cairosvg is not installed. Please install it with 'pip install cairosvg'")
    sys.exit(1)

def convert_svg_to_png(svg_path, png_path, width=None, height=None):
    """Convert SVG file to PNG file"""
    print(f"Converting {svg_path} to {png_path}")
    
    try:
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=width,
            output_height=height
        )
        print(f"Successfully converted to {png_path}")
        return True
    except Exception as e:
        print(f"Error converting {svg_path}: {e}")
        return False

def main():
    # Get the project root directory
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    
    # Set paths
    svg_dir = project_root / "resources" / "images"
    
    if not svg_dir.exists():
        print(f"SVG directory not found: {svg_dir}")
        return
    
    # Get all SVG files
    svg_files = list(svg_dir.glob("*.svg"))
    
    if not svg_files:
        print(f"No SVG files found in {svg_dir}")
        return
    
    # Convert each SVG file to PNG
    sizes = [16, 32, 48, 128, 256]
    
    for svg_file in svg_files:
        base_name = svg_file.stem
        
        # Standard resolution
        png_path = svg_dir / f"{base_name}.png"
        convert_svg_to_png(svg_file, png_path, width=48, height=48)
        
        # Create various sizes for system tray icons
        for size in sizes:
            png_path = svg_dir / f"{base_name}_{size}.png"
            convert_svg_to_png(svg_file, png_path, width=size, height=size)

if __name__ == "__main__":
    main() 