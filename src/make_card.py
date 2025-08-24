"""Generate branded image cards for tweets."""
from __future__ import annotations

from pathlib import Path
from typing import List
import logging

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _load_font(name: str, size: int) -> ImageFont.ImageFont:
    """Load a TrueType font, falling back to PIL's default if unavailable."""
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        logger.warning("Font %s not found, using default", name)
        return ImageFont.load_default()


def _text_width(text: str, font: ImageFont.ImageFont, draw: ImageDraw.ImageDraw) -> int:
    """Return pixel width of text across Pillow versions."""
    if hasattr(draw, "textlength"):  # Pillow ≥ 8.0
        return int(draw.textlength(text, font=font))
    # Pillow < 8.0
    return draw.textsize(text, font=font)[0]


def _line_height(font: ImageFont.ImageFont, draw: ImageDraw.ImageDraw) -> int:
    """Return a reliable line height across Pillow versions."""
    sample = "Ag"  # covers ascender + descender reasonably
    if hasattr(draw, "textbbox"):  # Pillow ≥ 8.0
        left, top, right, bottom = draw.textbbox((0, 0), sample, font=font)
        return bottom - top
    # Pillow < 8.0
    return draw.textsize(sample, font=font)[1]


def _wrap(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Simple greedy text wrapper using pixel width measurements."""
    words = text.split()
    lines: List[str] = []
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        if _text_width(test, font, draw) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_card(headline: str, bullets: List[str], source: str, out_path: str) -> None:
    """Create a 1200x675 news card with headline and up to three bullets.

    Args:
        headline: Main headline text.
        bullets: Up to three bullet strings.
        source: Source attribution string.
        out_path: Path to save JPEG file.
    """
    # Canvas & palette
    width, height = 1200, 675
    background = (15, 15, 15)
    stripe_height = 12
    accent = (200, 0, 0)
    text_color = "white"

    img = Image.new("RGB", (width, height), color=background)
    draw = ImageDraw.Draw(img)

    # Top accent stripe
    draw.rectangle([(0, 0), (width, stripe_height)], fill=accent)

    # Fonts (fallback to default if DejaVu not present on the Pi)
    headline_font = _load_font("DejaVuSans-Bold.ttf", 62)
    bullet_font = _load_font("DejaVuSans.ttf", 44)
    source_font = _load_font("DejaVuSans.ttf", 34)

    x_margin = 60
    y = stripe_height + 40
    max_text_width = width - 2 * x_margin

    # Headline
    for line in _wrap(headline, headline_font, max_text_width, draw):
        draw.text((x_margin, y), line, font=headline_font, fill=text_color)
        y += _line_height(headline_font, draw) + 10

    # Bullets
    y += 10
    for bullet in bullets[:3]:
        wrapped = _wrap(bullet, bullet_font, max_text_width - 40, draw)
        if not wrapped:
            continue
        # First line with bullet dot
        first = wrapped[0]
        draw.text((x_margin, y), f"• {first}", font=bullet_font, fill=text_color)
        y += _line_height(bullet_font, draw) + 5
        # Continuation lines indented
        for cont in wrapped[1:]:
            draw.text((x_margin + 35, y), cont, font=bullet_font, fill=text_color)
            y += _line_height(bullet_font, draw) + 5
        y += 5

    # Source line at bottom
    source_text = f"Source: {source}"
    source_y = height - _line_height(source_font, draw) - 30
    draw.text((x_margin, source_y), source_text, font=source_font, fill=text_color)

    # Save
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="JPEG", quality=92)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    demo_path = Path("media_cards/example.jpg")
    make_card(
        headline="Demo Headline",
        bullets=["First bullet", "Second bullet", "Third bullet"],
        source="example.com",
        out_path=str(demo_path),
    )
    logger.info("Saved demo card to %s", demo_path)
