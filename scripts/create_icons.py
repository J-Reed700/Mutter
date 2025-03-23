from PIL import Image
import os
from pathlib import Path

def create_app_icons(input_image_path, output_dir, base_name="microphone"):
    """
    Creates app icons in multiple sizes from an input image.
    
    Args:
        input_image_path: Path to the source image
        output_dir: Directory to save the icons
        base_name: Base filename for the icons
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Open the input image
    img = Image.open(input_image_path)
    
    # Convert to RGBA to ensure transparency support
    img = img.convert("RGBA")
    
    # Get dimensions
    width, height = img.size
    
    # Create a square canvas
    max_dim = max(width, height)
    square_img = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))  # Transparent background
    
    # Calculate position to center the image
    offset = ((max_dim - width) // 2, (max_dim - height) // 2)
    square_img.paste(img, offset, img)
    
    # Define sizes needed
    sizes = {
        f"{base_name}_16.png": 16,
        f"{base_name}_32.png": 32,
        f"{base_name}.png": 128,  # Main icon
    }
    
    # Create resized versions
    for filename, size in sizes.items():
        resized = square_img.resize((size, size), Image.LANCZOS)  # LANCZOS provides good quality downsampling
        output_path = os.path.join(output_dir, filename)
        resized.save(output_path)
        print(f"Saved {output_path}")
    
    print("Icon creation complete!")

# Usage example
if __name__ == "__main__":
    # Replace with your image path
    input_image = "C:/Users/tronk/Downloads/rumham7102_cool_whispers_minimal_pixel_logo_design_abstract_str_557e5403-71b9-4fd5-8cbd-70beab0678b1.png"
    
    # Set output directory to resources/images
    output_dir = Path("resources") / "images"
    
    create_app_icons(input_image, output_dir)