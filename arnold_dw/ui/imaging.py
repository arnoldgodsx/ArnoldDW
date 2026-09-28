"""PIL helpers for previews and the spinner animations (no Tk here; safe in worker threads)."""

from functools import lru_cache

from PIL import Image, ImageDraw, ImageOps

from arnold_dw.ui.theme import ACCENT, SPINNER_DIAMETER, SPINNER_STEP, SPINNER_WIDTH, TEXT


def make_rounded(img: Image.Image, size, radius=14):
    img = ImageOps.fit(img, size, Image.LANCZOS)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    out = Image.new("RGBA", size)
    out.paste(img, (0, 0), mask)
    return out


def hex_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=64)
def spinner_sprite(angle, diameter=SPINNER_DIAMETER, width=SPINNER_WIDTH):
    """A small transparent PNG with a faint ring + a bright rotating arc on it.

    Cached: the animation only ever cycles through 360 / SPINNER_STEP angles.
    Callers must not mutate the returned image.
    """
    ring_color = hex_rgb(ACCENT) + (255,)
    track_color = hex_rgb(TEXT) + (46,)
    size = diameter + width * 2 + 4
    sprite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    pad = width // 2 + 2
    bbox = [pad, pad, size - pad, size - pad]
    draw.arc(bbox, 0, 360, fill=track_color, width=width)
    draw.arc(bbox, angle, angle + 100, fill=ring_color, width=width)
    return sprite


def spinner_angles():
    return range(0, 360, SPINNER_STEP)


def dim_image(img, alpha=150, radius=12):
    """Darken a rounded-rect image while keeping its transparent corners transparent."""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle([(0, 0), (base.width - 1, base.height - 1)], radius=radius, fill=(0, 0, 0, alpha))
    return Image.alpha_composite(base, overlay)


def compose_spinner_frame(base_img, angle, diameter=SPINNER_DIAMETER, width=SPINNER_WIDTH):
    frame = base_img.convert("RGBA").copy()
    sprite = spinner_sprite(angle, diameter, width)
    x = (frame.width - sprite.width) // 2
    y = (frame.height - sprite.height) // 2
    frame.paste(sprite, (x, y), sprite)
    return frame
