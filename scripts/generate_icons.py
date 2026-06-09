"""Generate GameTracker application icons (PNG + ICO)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw


def create_gamepad_image(size: int) -> Image.Image:
    """Create a game controller icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Colors
    primary = (0, 120, 215)  # Windows blue
    dark = (30, 30, 30)
    white = (255, 255, 255)
    accent = (0, 180, 120)  # green accent

    # Scale factor for responsive drawing
    s = size / 256

    # Draw outer rounded gamepad body
    body_color = primary
    # Main controller body
    body_w = 200 * s
    body_h = 120 * s
    body_x = (size - body_w) / 2
    body_y = (size - body_h) / 2

    # Left grip
    draw.rounded_rectangle(
        [body_x - 20 * s, body_y + 10 * s, body_x + 30 * s, body_y + body_h - 10 * s],
        radius=15 * s,
        fill=body_color,
    )
    # Right grip
    draw.rounded_rectangle(
        [body_x + body_w - 30 * s, body_y + 10 * s, body_x + body_w + 20 * s, body_y + body_h - 10 * s],
        radius=15 * s,
        fill=body_color,
    )
    # Main body
    draw.rounded_rectangle(
        [body_x, body_y, body_x + body_w, body_y + body_h],
        radius=25 * s,
        fill=body_color,
    )

    # D-pad (left side)
    dpad_color = dark
    dpad_w = 20 * s
    dpad_h = 50 * s
    dpad_x = body_x + 35 * s
    dpad_y = body_y + (body_h - dpad_h) / 2
    draw.rounded_rectangle(
        [dpad_x, dpad_y, dpad_x + dpad_w, dpad_y + dpad_h],
        radius=4 * s,
        fill=dpad_color,
    )
    dpad_x2 = dpad_x - 15 * s
    dpad_y2 = dpad_y + 15 * s
    draw.rounded_rectangle(
        [dpad_x2, dpad_y2, dpad_x2 + dpad_w + 30 * s, dpad_y2 + dpad_h - 30 * s],
        radius=4 * s,
        fill=dpad_color,
    )

    # Action buttons (right side) - A, B, X, Y style
    btn_radius = 9 * s
    btn_center_x = body_x + body_w - 45 * s
    btn_center_y = body_y + body_h / 2
    # Y (top)
    draw.ellipse(
        [btn_center_x - btn_radius, btn_center_y - 25 * s - btn_radius,
         btn_center_x + btn_radius, btn_center_y - 25 * s + btn_radius],
        fill=accent,
    )
    # A (bottom)
    draw.ellipse(
        [btn_center_x - btn_radius, btn_center_y + 25 * s - btn_radius,
         btn_center_x + btn_radius, btn_center_y + 25 * s + btn_radius],
        fill=accent,
    )
    # X (left)
    draw.ellipse(
        [btn_center_x - 25 * s - btn_radius, btn_center_y - btn_radius,
         btn_center_x - 25 * s + btn_radius, btn_center_y + btn_radius],
        fill=accent,
    )
    # B (right)
    draw.ellipse(
        [btn_center_x + 25 * s - btn_radius, btn_center_y - btn_radius,
         btn_center_x + 25 * s + btn_radius, btn_center_y + btn_radius],
        fill=accent,
    )

    # Center logo area - a simple "G" letter
    g_font_size = int(55 * s)
    # Draw white circle in center
    circle_r = 22 * s
    circle_cx = body_x + body_w / 2
    circle_cy = body_y + body_h / 2
    draw.ellipse(
        [circle_cx - circle_r, circle_cy - circle_r,
         circle_cx + circle_r, circle_cy + circle_r],
        fill=white,
    )

    # Draw "GT" text in the center using basic shapes
    text_color = primary
    # Simple "G" shape using basic primitives
    g_size = 20 * s
    g_x = circle_cx - g_size / 2
    g_y = circle_cy - g_size / 2
    draw.arc(
        [g_x, g_y, g_x + g_size, g_y + g_size],
        start=0, end=300, fill=text_color, width=int(4 * s),
    )
    draw.line(
        [g_x + g_size / 2, g_y + g_size / 2, g_x + g_size, g_y + g_size / 2],
        fill=text_color, width=int(4 * s),
    )

    # Home/menu buttons (small dots between D-pad and buttons)
    home_r = 4 * s
    home_y = body_y + body_h + 5 * s
    draw.ellipse(
        [circle_cx - home_r, home_y - home_r, circle_cx + home_r, home_y + home_r],
        fill=white,
    )

    # Subtle highlight on top of body
    highlight = Image.new("RGBA", img.size, (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(highlight)
    h_draw.rounded_rectangle(
        [body_x + 40 * s, body_y + 2 * s, body_x + body_w - 40 * s, body_y + 30 * s],
        radius=15 * s,
        fill=(255, 255, 255, 30),
    )
    img = Image.alpha_composite(img, highlight)

    return img


def main() -> None:
    icons_dir = Path(__file__).resolve().parent.parent / "ui" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Generate 256x256 PNG
    png_path = icons_dir / "app_icon.png"
    img_256 = create_gamepad_image(256)
    img_256.save(png_path, "PNG")
    print(f"Created: {png_path} ({img_256.size[0]}x{img_256.size[1]})")

    # Generate ICO with multiple sizes
    ico_path = icons_dir / "app_icon.ico"
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]

    images = []
    for sz in ico_sizes:
        if sz <= 256:
            resized = img_256.resize((sz, sz), Image.LANCZOS)
            images.append(resized)

    # Save ICO (first image is used as default, but all sizes are stored)
    img_256.save(ico_path, "ICO", sizes=[(s, s) for s in ico_sizes if s <= 256])
    print(f"Created: {ico_path} (sizes: {ico_sizes})")

    # Verify the ICO
    ico_check = Image.open(ico_path)
    print(f"ICO verified: {ico_check.size}, frames: {getattr(ico_check, 'n_frames', 1)}")

    # Also generate smaller PNG for system tray (22x22)
    tray_path = icons_dir / "tray_icon.png"
    tray_img = img_256.resize((22, 22), Image.LANCZOS)
    tray_img.save(tray_path, "PNG")
    print(f"Created: {tray_path} ({tray_img.size[0]}x{tray_img.size[1]})")


if __name__ == "__main__":
    main()
