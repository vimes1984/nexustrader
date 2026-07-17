import os
from PIL import Image, ImageDraw

def create_icon(size, filename):
    # Create dark theme image
    img = Image.new("RGBA", (size, size), "#0f172a")
    draw = ImageDraw.Draw(img)
    
    # Outer glowing circle
    padding = size * 0.1
    glow_color = (168, 85, 247, 50)  # Neon Purple glow
    border_color = (0, 240, 255, 255) # Cyan border
    
    # Draw glow
    draw.ellipse(
        [padding - 4, padding - 4, size - padding + 4, size - padding + 4],
        outline=glow_color,
        width=max(2, int(size * 0.04))
    )
    
    # Draw border
    draw.ellipse(
        [padding, padding, size - padding, size - padding],
        outline=border_color,
        width=max(2, int(size * 0.02))
    )
    
    # Draw futuristic 'N' inside the circle
    center_start_x = size * 0.38
    center_end_x = size * 0.62
    y_top = size * 0.33
    y_bottom = size * 0.67
    
    # Draw N legs
    draw.line([(center_start_x, y_bottom), (center_start_x, y_top)], fill="#a855f7", width=max(2, int(size * 0.05)))
    draw.line([(center_start_x, y_top), (center_end_x, y_bottom)], fill="#00f0ff", width=max(2, int(size * 0.05)))
    draw.line([(center_end_x, y_bottom), (center_end_x, y_top)], fill="#a855f7", width=max(2, int(size * 0.05)))
    
    # Save image
    img.save(filename, "PNG")
    print(f"Saved {filename}")

if __name__ == "__main__":
    os.makedirs("dashboard", exist_ok=True)
    create_icon(192, "dashboard/icon-192.png")
    create_icon(512, "dashboard/icon-512.png")
