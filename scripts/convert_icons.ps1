# Check if Magick.NET package is installed
if (-not (Get-Command -ErrorAction SilentlyContinue magick)) {
    Write-Host "ImageMagick is not installed. Please install it via:"
    Write-Host "choco install imagemagick"
    exit 1
}

# Define icon sizes
$sizes = @(16, 24, 32, 48, 64, 128, 256)

# Define source files
$microphone_svg = "resources/images/microphone.svg"
$recording_svg = "resources/images/recording.svg"

# Output directory
$output_dir = "resources/images/windows"

# Make sure output directory exists
if (-not (Test-Path $output_dir)) {
    New-Item -ItemType Directory -Force -Path $output_dir
}

# Convert microphone icon to various sizes
foreach ($size in $sizes) {
    Write-Host "Converting microphone icon to $size x $size"
    magick convert -background none -size "$size`x$size" $microphone_svg "$output_dir/microphone_$size.png"
}

# Convert recording icon to various sizes
foreach ($size in $sizes) {
    Write-Host "Converting recording icon to $size x $size"
    magick convert -background none -size "$size`x$size" $recording_svg "$output_dir/recording_$size.png"
}

# Generate traditional OS-specific icons
Write-Host "Creating microphone_16.png and recording_16.png for system tray"
Copy-Item "$output_dir/microphone_16.png" "resources/images/microphone_16.png"
Copy-Item "$output_dir/recording_16.png" "resources/images/recording_16.png"

Write-Host "Creating microphone.png and recording.png"
Copy-Item "$output_dir/microphone_256.png" "resources/images/microphone.png"
Copy-Item "$output_dir/recording_256.png" "resources/images/recording.png"

Write-Host "Icon conversion complete!" 