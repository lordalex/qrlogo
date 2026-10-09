"""QR matrix + three renderers (PNG, SVG, e-mail table) with a logo in the middle."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import qrcode
import qrcode.util
from PIL import Image, ImageDraw

from . import logo as _logo
from . import verify as _verify

EC_LEVELS = {
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}
GMAIL_CLIP = 102 * 1024  # Gmail cuts a message's HTML at ~102 KB
SHAPES = ("square", "dots", "rounded")


@dataclass
class Style:
    fg: str = "#000000"            # data modules
    finder: Optional[str] = None   # the three corner squares (default: same as fg)
    bg: str = "#ffffff"
    quiet: int = 4                 # blank border, in modules (the spec asks for 4; 2 still scans)
    shape: str = "square"          # square | dots | rounded   (modules; corner squares stay square)
    align: bool = False            # also colour the small alignment squares like the corners

    def __post_init__(self):
        self.fg = _logo.hex_color(self.fg)
        self.bg = _logo.hex_color(self.bg)
        self.finder = _logo.hex_color(self.finder) if self.finder else self.fg
        if self.shape not in SHAPES:
            raise ValueError(f"shape must be one of {SHAPES}, got {self.shape!r}")
        if self.quiet < 0:
            raise ValueError("quiet must be >= 0")


@dataclass
class LogoSpec:
    path: str
    crop: Optional[Tuple[float, float, float, float]] = None  # fractions x0,y0,x1,y1 of the image
    bg: Optional[str] = None            # tile background (default: logo's corner colour)
    scale: float = 0.27                 # tile width as a fraction of the QR width
    shape: str = "square"               # square | rounded | circle
    plate: float = 0.35                 # blank margin around the tile, in modules
    plate_color: Optional[str] = None   # default: style.bg
    max_area: float = 0.14              # never cover more than this share of the code


@dataclass
class Result:
    data: str
    version: int
    n: int
    ec: str
    tile_modules: int
    svg: Optional[str] = None
    png: Optional[Image.Image] = None
    email: Optional[str] = None
    checks: Dict[str, Optional[str]] = field(default_factory=dict)  # format -> decoded text
    warnings: List[str] = field(default_factory=list)
    verified: bool = False

    @property
    def ok(self) -> bool:
        return self.verified and all(v == self.data for v in self.checks.values())


# ---------------------------------------------------------------- layout

@dataclass
class Layout:
    M: np.ndarray
    version: int
    n: int
    quiet: int
    tile: int            # logo tile width in modules (0 = no logo)
    special: frozenset   # (r, c) of corner squares (+ alignment squares when asked)

    @property
    def a(self) -> int:
        return (self.n - self.tile) // 2

    @property
    def b(self) -> int:
        return self.a + self.tile

    @property
    def N(self) -> int:  # modules including the quiet zone
        return self.n + 2 * self.quiet

    def in_logo(self, r: int, c: int) -> bool:
        return bool(self.tile) and self.a <= r < self.b and self.a <= c < self.b


def _tile_modules(n: int, scale: float, max_area: float) -> int:
    t = int(round(n * scale))
    if t % 2 == 0:  # odd, so the tile sits exactly in the centre
        t += 1 if (n * scale) >= t else -1
    t = max(t, 3)
    while t > 3 and (t / n) ** 2 > max_area:
        t -= 2
    return t


def _special(n: int, version: int, align: bool) -> frozenset:
    cells = set()
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(7):
            for c in range(7):
                cells.add((r0 + r, c0 + c))
    if align and version >= 2:
        pos = qrcode.util.pattern_position(version)
        last = pos[-1]
        for cy in pos:
            for cx in pos:
                if (cy, cx) in ((6, 6), (6, last), (last, 6)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        cells.add((cy + dy, cx + dx))
    return frozenset(cells)


def layout(data: str, style: Style, logo: Optional[LogoSpec], ec: Optional[str]) -> Tuple[Layout, str]:
    ec = (ec or ("H" if logo else "M")).upper()
    if ec not in EC_LEVELS:
        raise ValueError(f"ec must be one of L, M, Q, H; got {ec!r}")
    if logo and ec not in ("Q", "H"):
        raise ValueError("a logo needs error correction Q or H (the logo hides part of the code)")
    qr = qrcode.QRCode(error_correction=EC_LEVELS[ec], border=0)
    qr.add_data(data)
    qr.make(fit=True)
    M = np.array(qr.get_matrix(), dtype=bool)
    n = M.shape[0]
    tile = _tile_modules(n, logo.scale, logo.max_area) if logo else 0
    return Layout(M, qr.version, n, style.quiet, tile, _special(n, qr.version, style.align)), ec


@dataclass
class _Prepared:
    modules: int
    img: Image.Image            # RGB, square, high resolution
    mask: Optional[Image.Image]  # L, same size, or None
    plate: float
    plate_color: str
    shape: str


def _prepare(spec: LogoSpec, style: Style, modules: int) -> _Prepared:
    px = 512
    img, _ = _logo.tile(spec.path, px, spec.crop, spec.bg, fallback_bg=style.bg)
    return _Prepared(
        modules,
        img,
        _logo.shape_mask(px, spec.shape),
        spec.plate,
        _logo.hex_color(spec.plate_color) if spec.plate_color else style.bg,
        spec.shape,
    )


def _module_color(L: Layout, style: Style, r: int, c: int) -> str:
    return style.finder if (r, c) in L.special else style.fg


# ---------------------------------------------------------------- PNG

def render_png(L: Layout, style: Style, prep: Optional[_Prepared], px: int = 16) -> Image.Image:
    ss = 1 if style.shape == "square" else 4
    S = px * ss
    N = L.N
    img = Image.new("RGB", (N * S, N * S), style.bg)
    d = ImageDraw.Draw(img)
    q = L.quiet
    for r in range(L.n):
        for c in range(L.n):
            if not L.M[r, c] or L.in_logo(r, c):
                continue
            x0, y0 = (c + q) * S, (r + q) * S
            x1, y1 = x0 + S - 1, y0 + S - 1
            col = _module_color(L, style, r, c)
            shape = "square" if (r, c) in L.special else style.shape
            if shape == "square":
                d.rectangle([x0, y0, x1, y1], fill=col)
            elif shape == "dots":
                pad = S * 0.08
                d.ellipse([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=col)
            else:
                d.rounded_rectangle([x0, y0, x1, y1], radius=S * 0.3, fill=col)
    if prep:
        x0, y0 = (q + L.a) * S, (q + L.a) * S
        side = L.tile * S
        pad = int(round(prep.plate * S))
        box = [x0 - pad, y0 - pad, x0 + side + pad - 1, y0 + side + pad - 1]
        if prep.shape == "circle":
            d.ellipse(box, fill=prep.plate_color)
        else:
            d.rectangle(box, fill=prep.plate_color)
        t = prep.img.resize((side, side), Image.LANCZOS)
        m = prep.mask.resize((side, side), Image.LANCZOS) if prep.mask else None
        img.paste(t, (x0, y0), m)
    if ss > 1:
        img = img.resize((N * px, N * px), Image.LANCZOS)
    return img


# ---------------------------------------------------------------- SVG

def render_svg(L: Layout, style: Style, prep: Optional[_Prepared], px: int = 12) -> str:
    N, q = L.N, L.quiet
    paths: Dict[str, List[str]] = {}
    extra: List[str] = []
    for r in range(L.n):
        c = 0
        while c < L.n:
            if not L.M[r, c] or L.in_logo(r, c):
                c += 1
                continue
            col = _module_color(L, style, r, c)
            square = style.shape == "square" or (r, c) in L.special
            if square:
                c0 = c
                while (
                    c < L.n
                    and L.M[r, c]
                    and not L.in_logo(r, c)
                    and _module_color(L, style, r, c) == col
                    and (style.shape == "square" or (r, c) in L.special)
                ):
                    c += 1
                paths.setdefault(col, []).append(f"M{c0 + q} {r + q}h{c - c0}v1h-{c - c0}z")
            else:
                if style.shape == "dots":
                    extra.append(f'<circle cx="{c + q + .5}" cy="{r + q + .5}" r=".46" fill="{col}"/>')
                else:
                    extra.append(f'<rect x="{c + q + .04}" y="{r + q + .04}" width=".92" height=".92" rx=".3" fill="{col}"/>')
                c += 1
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {N} {N}" width="{N * px}" height="{N * px}" role="img" aria-label="QR code">',
        f'<rect width="{N}" height="{N}" fill="{style.bg}"/>',
        '<g shape-rendering="crispEdges">',
    ]
    for col, segs in paths.items():
        out.append(f'<path fill="{col}" d="{"".join(segs)}"/>')
    out.append("</g>")
    out.extend(extra)
    if prep:
        x = q + L.a
        s = L.tile
        pad = prep.plate
        px_, py_, ps = x - pad, x - pad, s + 2 * pad
        if prep.shape == "circle":
            out.append(f'<circle cx="{x + s / 2}" cy="{x + s / 2}" r="{ps / 2}" fill="{prep.plate_color}"/>')
            clip = f'<circle cx="{x + s / 2}" cy="{x + s / 2}" r="{s / 2}"/>'
        else:
            out.append(f'<rect x="{px_}" y="{py_}" width="{ps}" height="{ps}" fill="{prep.plate_color}"/>')
            rx = s * 0.2 if prep.shape == "rounded" else 0
            clip = f'<rect x="{x}" y="{x}" width="{s}" height="{s}" rx="{rx}"/>'
        buf = io.BytesIO()
        # flat-colour logos compress far better as a small palette PNG
        prep.img.resize((256, 256), Image.LANCZOS).quantize(colors=96, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
        href = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        out.append(f'<clipPath id="qrlogo-clip">{clip}</clipPath>')
        out.append(
            f'<image x="{x}" y="{x}" width="{s}" height="{s}" xlink:href="{href}" href="{href}" clip-path="url(#qrlogo-clip)"/>'
        )
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- e-mail table

def _runs(items: List[str]) -> Iterable[Tuple[str, int]]:
    i = 0
    while i < len(items):
        j = i
        while j < len(items) and items[j] == items[i]:
            j += 1
        yield items[i], j - i
        i = j


def render_email(
    L: Layout,
    style: Style,
    prep: Optional[_Prepared],
    px: int = 5,
    cell: int = 1,
    colors: int = 3,
) -> str:
    """Table-only QR for HTML e-mail (no <img>: some drafting tools strip images).

    Layout rules that matter: one spacer row fixes every column width, and the first cell
    of each row carries the row height. Without them a rowspan cell collapses the table."""
    n, q, N = L.n, L.quiet, L.N
    a, b, t = L.a, L.b, L.tile
    side = t * px
    while cell > 1 and side % cell:
        cell -= 1
    k = side // cell

    logo_rows: List[str] = []
    if prep:
        tile = prep.img.resize((k, k), Image.LANCZOS)
        if prep.mask is not None:  # outside the shape -> plate colour
            m = np.asarray(prep.mask.resize((k, k), Image.LANCZOS)) > 127
            arr = np.asarray(tile).copy()
            arr[~m] = _logo_rgb(prep.plate_color)
            tile = Image.fromarray(arr, "RGB")
        tile = _logo.snap_palette(tile, colors)
        arr = np.asarray(tile)
        logo_rows.append("<tr>" + "".join(f"<td width={cell}></td>" for _ in range(k)) + "</tr>")
        for y in range(k):
            row = ["#%02x%02x%02x" % tuple(arr[y, x]) for x in range(k)]
            cells = "".join(
                f'<td{" colspan=%d" % w if w > 1 else ""} bgcolor={col}></td>' for col, w in _runs(row)
            )
            logo_rows.append("<tr>" + cells.replace("<td", f"<td height={cell}", 1) + "</tr>")

    def color(r: int, c: int) -> str:
        if 0 <= r < n and 0 <= c < n and L.M[r, c] and not L.in_logo(r, c):
            return _module_color(L, style, r, c)
        return style.bg

    rows = ["<tr>" + "".join(f"<td width={px}></td>" for _ in range(N)) + "</tr>"]  # column widths
    for rr in range(-q, n + q):
        cells: List[str] = []
        c = -q
        while c < n + q:
            if prep and a <= rr < b and c == a:
                if rr == a:
                    cells.append(
                        f'<td colspan="{t}" rowspan="{t}" bgcolor={prep.plate_color}>'
                        f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;table-layout:fixed;'
                        f'width:{k * cell}px;height:{k * cell}px;line-height:0;font-size:0">'
                        + "".join(logo_rows)
                        + "</table></td>"
                    )
                c += t
                continue
            seg: List[str] = []
            while c < n + q and not (prep and a <= rr < b and c == a):
                seg.append(color(rr, c))
                c += 1
            for col, w in _runs(seg):
                cells.append(
                    f'<td{" colspan=%d" % w if w > 1 else ""}{"" if col == style.bg else " bgcolor=" + col}></td>'
                )
        rows.append("<tr>" + "".join(cells).replace("<td", f"<td height={px}", 1) + "</tr>")
    return (
        f'<table cellpadding="0" cellspacing="0" bgcolor="{style.bg}" style="border-collapse:collapse;'
        f'table-layout:fixed;width:{N * px}px;height:{N * px}px;margin:0 auto;line-height:0;font-size:0">'
        + "".join(rows)
        + "</table>"
    )


def _logo_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------- one call

def generate(
    data: str,
    style: Optional[Style] = None,
    logo: Optional[LogoSpec] = None,
    ec: Optional[str] = None,
    formats: Tuple[str, ...] = ("svg", "png"),
    png_px: int = 16,
    svg_px: int = 12,
    email_px: int = 5,
    email_cell: int = 1,
    email_colors: int = 3,
    verify: bool = True,
) -> Result:
    """Build the requested formats and (by default) decode each one.

    Raises ValueError if verification is on and any format does not decode back to `data`.
    """
    unknown = set(formats) - {"svg", "png", "email"}
    if unknown:
        raise ValueError(f"unknown formats: {sorted(unknown)} (svg | png | email)")
    style = style or Style()
    L, ec = layout(data, style, logo, ec)
    prep = _prepare(logo, style, L.tile) if logo else None
    res = Result(data, L.version, L.n, ec, L.tile)
    if "png" in formats:
        res.png = render_png(L, style, prep, png_px)
    if "svg" in formats:
        res.svg = render_svg(L, style, prep, svg_px)
    if "email" in formats:
        res.email = render_email(L, style, prep, email_px, email_cell, email_colors)
        size = len(res.email.encode())
        if size > 60_000:
            res.warnings.append(
                f"e-mail table is {size // 1024} KB; Gmail clips a message at {GMAIL_CLIP // 1024} KB. "
                "Use a smaller code, --email-cell 2, or fewer --email-colors."
            )
    if verify:
        if not _verify.available():
            res.warnings.append("opencv-python-headless not installed: outputs were NOT decoded (pip install 'qrlogo[verify]')")
        else:
            if res.png is not None:
                res.checks["png"] = _verify.decode_image(res.png)
            if res.svg is not None:
                try:
                    res.checks["svg"] = _verify.decode_svg(res.svg)
                except RuntimeError as e:
                    res.warnings.append(str(e))
            if res.email is not None:
                res.checks["email"] = _verify.decode_email(res.email, style.bg, L.N)
            res.verified = True
            bad = [k for k, v in res.checks.items() if v != data]
            if bad:
                raise ValueError(
                    f"{', '.join(bad)} did not decode back to the input. "
                    "Try a smaller --logo-scale, a higher --ec, or a thicker --quiet."
                )
    return res
