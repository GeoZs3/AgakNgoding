import io
from pathlib import Path
from typing import Optional
import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont


def generate_plant_qr_bytes(
    target_url: str,
    logo_path: Optional[Path] = None,
) -> io.BytesIO:
    """
    Menghasilkan gambar PNG QR Code secara dinamis di memori (on-the-fly)
    dengan cutout logo sekolah di tengah, tanpa menyimpan file ke disk.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=12,
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="#1b3b1e", back_color="#ffffff").convert("RGBA")
    qr_w, qr_h = qr_img.size

    # Ukuran cutout tengah ~22% dari lebar QR (aman untuk ERROR_CORRECT_H)
    cutout_size = int(qr_w * 0.22)
    badge_pad = int(cutout_size * 0.14)
    total_badge = cutout_size + (badge_pad * 2)

    badge = Image.new("RGBA", (total_badge, total_badge), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.ellipse(
        (0, 0, total_badge - 1, total_badge - 1),
        fill=(255, 255, 255, 255),
        outline=(27, 94, 32, 255),
        width=4,
    )

    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((cutout_size, cutout_size), Image.Resampling.LANCZOS)

        mask = Image.new("L", logo.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, logo.size[0] - 1, logo.size[1] - 1), fill=255)

        lx = (total_badge - logo.size[0]) // 2
        ly = (total_badge - logo.size[1]) // 2
        badge.paste(logo, (lx, ly), mask)
    else:
        inner_margin = badge_pad + 4
        draw.ellipse(
            (inner_margin, inner_margin, total_badge - inner_margin, total_badge - inner_margin),
            fill=(46, 125, 50, 255),
        )
        font = ImageFont.load_default()
        label = "ADIWIYATA"
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((total_badge - tw) // 2, (total_badge - th) // 2),
            label,
            fill=(255, 255, 255, 255),
            font=font,
        )

    pos_x = (qr_w - total_badge) // 2
    pos_y = (qr_h - total_badge) // 2
    qr_img.paste(badge, (pos_x, pos_y), badge)

    buf = io.BytesIO()
    qr_img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf