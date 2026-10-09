"""Decode what we made. A QR code that does not scan is worse than no QR code."""
from __future__ import annotations

import io
from collections import Counter
from html.parser import HTMLParser
from typing import Optional

import numpy as np
from PIL import Image, ImageColor


def _cv2():
    try:
        import cv2
    except ImportError:
        return None
    return cv2


def available() -> bool:
    return _cv2() is not None


def decode_image(img: Image.Image) -> Optional[str]:
    """Decode a PIL image. Tries a few scales/borders because OpenCV is picky."""
    cv2 = _cv2()
    if cv2 is None:
        raise RuntimeError("opencv-python-headless is not installed (pip install 'qrlogo[verify]')")
    rgb = img.convert("RGB")
    det = cv2.QRCodeDetector()
    w = rgb.width
    for border in (0, w // 8):
        base = rgb
        if border:
            padded = Image.new("RGB", (w + 2 * border, rgb.height + 2 * border), "white")
            padded.paste(rgb, (border, border))
            base = padded
        for target in (None, 600, 900, 300):
            im = base
            if target and base.width != target:
                im = base.resize((target, target), Image.NEAREST if target > base.width else Image.LANCZOS)
            arr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
            text, _, _ = det.detectAndDecode(arr)
            if text:
                return text
    return None


def decode_svg(svg: str) -> Optional[str]:
    try:
        import cairosvg
    except ImportError:
        raise RuntimeError("cairosvg is not installed (pip install 'qrlogo[svg]')")
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=700, background_color="white")
    return decode_image(Image.open(io.BytesIO(png)))


class _Table(HTMLParser):
    """Reads the outer table of the e-mail snippet into rows of cells."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.rows: list = []
        self.cur = None
        self.td = None
        self.table_bg = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table_bg = a.get("bgcolor")
        elif tag == "tr" and self.depth == 1:
            self.cur = []
            self.rows.append(self.cur)
        elif tag == "td":
            if self.depth == 1:
                self.td = {
                    "colspan": int(a.get("colspan", 1) or 1),
                    "rowspan": int(a.get("rowspan", 1) or 1),
                    "bg": a.get("bgcolor") or None,
                    "inner": Counter(),
                }
                self.cur.append(self.td)
            elif self.depth == 2 and self.td is not None and a.get("bgcolor"):
                self.td["inner"][a["bgcolor"]] += int(a.get("colspan", 1) or 1)

    def handle_endtag(self, tag):
        if tag == "table":
            self.depth -= 1


def email_grid(html: str, bg: str = "#ffffff", n_expected: Optional[int] = None) -> np.ndarray:
    """Lay the table out like a browser would (colspan/rowspan) -> (rows, cols, 3) uint8.

    The first <tr> is the column-width spacer row and is skipped."""
    p = _Table()
    p.feed(html)
    rows = p.rows[1:]
    occ: dict = {}
    placed = []
    ncols = 0
    for r, cells in enumerate(rows):
        c = 0
        for cell in cells:
            while (r, c) in occ:
                c += 1
            for dr in range(cell["rowspan"]):
                for dc in range(cell["colspan"]):
                    occ[(r + dr, c + dc)] = True
            placed.append((r, c, cell))
            c += cell["colspan"]
            ncols = max(ncols, c)
    nrows = len(rows)
    base = ImageColor.getrgb(p.table_bg or bg)
    grid = np.zeros((nrows, ncols, 3), dtype=np.uint8)
    grid[:, :] = base
    for r, c, cell in placed:
        col = cell["bg"] or (cell["inner"].most_common(1)[0][0] if cell["inner"] else None)
        if col:
            grid[r : r + cell["rowspan"], c : c + cell["colspan"]] = ImageColor.getrgb(col)
    if n_expected is not None and grid.shape[:2] != (n_expected, n_expected):
        raise ValueError(f"e-mail table lays out as {grid.shape[1]}x{grid.shape[0]}, expected {n_expected}x{n_expected}")
    return grid


def decode_email(html: str, bg: str = "#ffffff", n_expected: Optional[int] = None) -> Optional[str]:
    grid = email_grid(html, bg, n_expected)
    img = Image.fromarray(grid, "RGB").resize((grid.shape[1] * 8, grid.shape[0] * 8), Image.NEAREST)
    return decode_image(img)
