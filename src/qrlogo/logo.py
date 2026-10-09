"""Load a logo and turn it into a square tile for the middle of the QR code."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageColor, ImageDraw


def hex_color(value: str) -> str:
    """'#abc', 'red', 'rgb(1,2,3)' -> '#rrggbb'."""
    r, g, b = ImageColor.getrgb(value)[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


def load(path: str, svg_px: int = 768) -> Image.Image:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"logo not found: {path}")
    if p.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError as e:  # pragma: no cover
            raise SystemExit("SVG logos need cairosvg: pip install 'qrlogo[svg]'") from e
        png = cairosvg.svg2png(url=str(p), output_width=svg_px)
        return Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.open(p).convert("RGBA")


def shape_mask(px: int, shape: str) -> Optional[Image.Image]:
    """'L' mask for rounded/circle tiles; None for a plain square."""
    if shape == "square":
        return None
    ss = 4
    m = Image.new("L", (px * ss, px * ss), 0)
    d = ImageDraw.Draw(m)
    box = [0, 0, px * ss - 1, px * ss - 1]
    if shape == "circle":
        d.ellipse(box, fill=255)
    elif shape == "rounded":
        d.rounded_rectangle(box, radius=int(px * ss * 0.2), fill=255)
    else:
        raise ValueError(f"unknown logo shape: {shape!r} (square | rounded | circle)")
    return m.resize((px, px), Image.LANCZOS)


def tile(
    path: str,
    px: int,
    crop: Optional[Tuple[float, float, float, float]] = None,
    bg: Optional[str] = None,
    fallback_bg: str = "#ffffff",
) -> Tuple[Image.Image, str]:
    """Return (RGB px×px tile, tile background hex).

    `crop` is (x0, y0, x1, y1) as fractions of the image. The tile background is `bg`,
    else the logo's own corner colour when the image is opaque there, else `fallback_bg`.
    """
    im = load(path)
    w, h = im.size
    if crop:
        x0, y0, x1, y1 = crop
        im = im.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
        w, h = im.size
    if bg:
        bg_hex = hex_color(bg)
    else:
        r, g, b, a = im.getpixel((0, 0))
        bg_hex = f"#{r:02x}{g:02x}{b:02x}" if a > 200 else hex_color(fallback_bg)
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), ImageColor.getrgb(bg_hex) + (255,))
    canvas.alpha_composite(im, ((side - w) // 2, (side - h) // 2))
    return canvas.convert("RGB").resize((px, px), Image.LANCZOS), bg_hex


def snap_palette(img: Image.Image, colors: int = 3) -> Image.Image:
    """Reduce a tile to a few flat colours: the background, the colour farthest from it,
    a blend of the two (soft edges), then more farthest colours. Long runs keep the
    e-mail table small."""
    a = np.asarray(img.convert("RGB")).astype(np.float64)
    flat = a.reshape(-1, 3)
    uniq, counts = np.unique(flat.astype(np.uint8), axis=0, return_counts=True)
    pal = [uniq[counts.argmax()].astype(np.float64)]

    def farthest():
        d = np.min([((flat - p) ** 2).sum(1) for p in pal], axis=0)
        i = int(d.argmax())
        return flat[i].copy(), float(d[i])

    if colors >= 2:
        c, dist = farthest()
        if dist > 400:
            pal.append(c)
            if colors >= 3:
                pal.append((pal[0] + pal[1]) / 2)
    while len(pal) < colors:
        c, dist = farthest()
        if dist <= 400:
            break
        pal.append(c)
    pal_a = np.array(pal)
    idx = ((flat[:, None, :] - pal_a[None, :, :]) ** 2).sum(-1).argmin(1)
    return Image.fromarray(pal_a[idx].astype(np.uint8).reshape(a.shape), "RGB")
