"""Command line: qrlogo [kind] ... (see README)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import payloads
from .core import LogoSpec, Style, generate

KINDS = ("text", "url", "wifi", "vcard", "mailto", "tel", "sms", "geo")


def _common(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("output")
    g.add_argument("--out", default="qr-out", help="folder for the files (default: ./qr-out)")
    g.add_argument("--name", default="qr", help="file name without extension (default: qr)")
    g.add_argument("--formats", default=None, help="comma list of svg,png,email (default: svg,png)")
    g.add_argument("--png-px", type=int, default=None, help="pixels per module in the PNG (default 16)")
    g.add_argument("--svg-px", type=int, default=None, help="pixels per module in the SVG's own size (default 12)")
    g.add_argument("--email-px", type=int, default=None, help="pixels per module in the e-mail table (default 5)")
    g.add_argument("--email-cell", type=int, default=None, help="pixels per logo cell in the e-mail table; 1 = sharpest, 2 = half the size")
    g.add_argument("--email-colors", type=int, default=None, help="colours kept from the logo in the e-mail table (default 3)")
    g.add_argument("--no-verify", action="store_true", help="skip decoding the results")
    g.add_argument("--print-data", action="store_true", help="print the encoded text and exit")
    s = p.add_argument_group("look (override the brand profile)")
    s.add_argument("--brand", help="JSON brand profile (colours, logo, ...); see examples/brand.example.json")
    s.add_argument("--fg", help="module colour")
    s.add_argument("--finder", help="corner-square colour")
    s.add_argument("--bg", help="background colour")
    s.add_argument("--quiet", type=int, help="blank border in modules (default 4)")
    s.add_argument("--shape", choices=("square", "dots", "rounded"), help="module shape")
    s.add_argument("--align", action="store_true", default=None, help="colour the alignment squares too")
    s.add_argument("--ec", choices=list("LMQH"), help="error correction (default H with a logo, else M)")
    l = p.add_argument_group("logo")
    l.add_argument("--logo", help="PNG/JPG/SVG logo to put in the middle")
    l.add_argument("--logo-crop", help="x0,y0,x1,y1 as fractions of the image, e.g. 0.2,0.2,0.8,0.8")
    l.add_argument("--logo-bg", help="tile background colour (default: the logo's corner colour)")
    l.add_argument("--logo-scale", type=float, help="tile width as a fraction of the code (default 0.27)")
    l.add_argument("--logo-shape", choices=("square", "rounded", "circle"))
    l.add_argument("--logo-plate", type=float, help="blank margin around the tile, in modules (default 0.35)")
    l.add_argument("--no-logo", action="store_true", help="ignore the logo from the brand profile")


def build_parser(kind: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=f"qrlogo {kind}" if kind != "text" else "qrlogo",
        description="QR code with your logo in the middle. Writes SVG/PNG/e-mail table and decodes each one.",
    )
    if kind in ("text", "url"):
        p.add_argument("data", help="what the code opens/contains")
    elif kind == "wifi":
        p.add_argument("--ssid", required=True)
        p.add_argument("--password", default="")
        p.add_argument("--auth", default="WPA", help="WPA (default), WEP or nopass")
        p.add_argument("--hidden", action="store_true")
    elif kind == "vcard":
        p.add_argument("--contact-name", required=True, dest="cname", help="'First Last'")
        p.add_argument("--org", default="")
        p.add_argument("--title", default="")
        p.add_argument("--phone", default="")
        p.add_argument("--email", default="")
        p.add_argument("--website", default="")
    elif kind == "mailto":
        p.add_argument("to")
        p.add_argument("--subject", default="")
        p.add_argument("--body", default="")
    elif kind in ("tel", "sms"):
        p.add_argument("number")
        if kind == "sms":
            p.add_argument("--body", default="")
    elif kind == "geo":
        p.add_argument("lat", type=float)
        p.add_argument("lon", type=float)
    _common(p)
    return p


def payload(kind: str, a: argparse.Namespace) -> str:
    if kind == "text":
        return a.data
    if kind == "url":
        return payloads.url(a.data)
    if kind == "wifi":
        return payloads.wifi(a.ssid, a.password, a.auth, a.hidden)
    if kind == "vcard":
        return payloads.vcard(a.cname, a.org, a.title, a.phone, a.email, a.website)
    if kind == "mailto":
        return payloads.mailto(a.to, a.subject, a.body)
    if kind == "tel":
        return payloads.tel(a.number)
    if kind == "sms":
        return payloads.sms(a.number, a.body)
    if kind == "geo":
        return payloads.geo(a.lat, a.lon)
    raise AssertionError(kind)


def load_brand(path: Optional[str]) -> dict:
    if not path:
        return {}
    p = Path(path)
    cfg = json.loads(p.read_text())
    if cfg.get("logo") and not Path(cfg["logo"]).is_absolute():
        cfg["logo"] = str((p.parent / cfg["logo"]).resolve())  # relative to the profile file
    return cfg


def _pick(cli, brand: dict, key: str, default=None):
    return cli if cli is not None else brand.get(key, default)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    kind = "text"
    if argv and argv[0] in KINDS:
        kind = argv.pop(0)
    a = build_parser(kind).parse_args(argv)
    data = payload(kind, a)
    if a.print_data:
        print(data)
        return 0

    brand = load_brand(a.brand)
    style = Style(
        fg=_pick(a.fg, brand, "fg", "#000000"),
        finder=_pick(a.finder, brand, "finder"),
        bg=_pick(a.bg, brand, "bg", "#ffffff"),
        quiet=_pick(a.quiet, brand, "quiet", 4),
        shape=_pick(a.shape, brand, "shape", "square"),
        align=bool(_pick(a.align, brand, "align", False)),
    )
    logo_path = None if a.no_logo else _pick(a.logo, brand, "logo")
    logo = None
    if logo_path:
        crop = _pick(a.logo_crop, brand, "logo_crop")
        if isinstance(crop, str):
            crop = [float(x) for x in crop.split(",")]
        if crop is not None and len(crop) != 4:
            raise SystemExit("--logo-crop needs four numbers: x0,y0,x1,y1")
        logo = LogoSpec(
            path=logo_path,
            crop=tuple(crop) if crop else None,
            bg=_pick(a.logo_bg, brand, "logo_bg"),
            scale=_pick(a.logo_scale, brand, "logo_scale", 0.27),
            shape=_pick(a.logo_shape, brand, "logo_shape", "square"),
            plate=_pick(a.logo_plate, brand, "logo_plate", 0.35),
        )
    fmts = tuple(x.strip() for x in (_pick(a.formats, brand, "formats", "svg,png")).split(",") if x.strip())
    try:
        res = generate(
            data,
            style,
            logo,
            ec=_pick(a.ec, brand, "ec"),
            formats=fmts,
            png_px=_pick(a.png_px, brand, "png_px", 16),
            svg_px=_pick(a.svg_px, brand, "svg_px", 12),
            email_px=_pick(a.email_px, brand, "email_px", 5),
            email_cell=_pick(a.email_cell, brand, "email_cell", 1),
            email_colors=_pick(a.email_colors, brand, "email_colors", 3),
            verify=not a.no_verify,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if res.png is not None:
        f = out / f"{a.name}.png"
        res.png.save(f)
        written.append(("png", f))
    if res.svg is not None:
        f = out / f"{a.name}.svg"
        f.write_text(res.svg)
        written.append(("svg", f))
    if res.email is not None:
        f = out / f"{a.name}.email.html"
        f.write_text(res.email)
        written.append(("email", f))
    print(f"data    : {data if len(data) < 80 else data[:77] + '...'}")
    print(f"code    : version {res.version}, {res.n}x{res.n} modules, error correction {res.ec}" + (f", logo {res.tile_modules}x{res.tile_modules} modules" if logo else ""))
    for fmt, f in written:
        status = ""
        if fmt in res.checks:
            status = "  decodes OK" if res.checks[fmt] == data else "  DECODE FAILED"
        print(f"{fmt:<8}: {f} ({f.stat().st_size:,} bytes){status}")
    for w in res.warnings:
        print(f"warning : {w}", file=sys.stderr)
    return 0
