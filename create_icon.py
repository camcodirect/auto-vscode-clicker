"""Generate icon.ico for the system tray and shortcuts."""
from PIL import Image, ImageDraw

sizes = [16, 32, 48, 64, 128, 256]
images = []

for size in sizes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(1, size // 16)
    # Green circle background
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(76, 175, 80, 255))
    # White cursor/arrow triangle
    cx, cy = size // 2, size // 2
    s = size // 4
    draw.polygon([
        (cx - s, cy - s),
        (cx - s, cy + s),
        (cx + s // 2, cy + s // 4),
    ], fill=(255, 255, 255, 230))

    images.append(img)

images[0].save("icon.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
print("Created icon.ico")
