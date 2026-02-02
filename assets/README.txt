# Tray Icon Assets

This directory is for tray application icons.

## Expected Files

- `icon.png` - Main tray icon (recommended: 64x64 or 256x256 PNG with transparency)
- `icon_active.png` - Optional: icon when agent is actively connected
- `icon_inactive.png` - Optional: icon when agent is disconnected

## Icon Guidelines

1. Use PNG format with transparency
2. Recommended sizes: 16x16, 32x32, 64x64, or 256x256
3. Windows will scale automatically, but 256x256 gives best quality
4. Use high contrast colors for visibility in both light and dark system themes

## Creating Icons

You can create icons using:
- Pillow/PIL in Python
- Any image editor (Photoshop, GIMP, Paint.NET)
- Online icon generators

Example Python code to create a basic icon:

```python
from PIL import Image, ImageDraw

# Create a 64x64 image with transparency
img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw a simple marker icon
draw.ellipse([8, 8, 56, 56], fill=(138, 43, 226))  # Purple circle
draw.polygon([(32, 48), (20, 28), (44, 28)], fill=(255, 255, 255))  # Arrow

img.save('icon.png')
```

Note: Do NOT commit actual icon files to this scaffold.
Icons should be created or designed separately.
