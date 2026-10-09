"""Builders for the strings phone cameras understand (Wi-Fi, vCard, mailto, ...)."""
from urllib.parse import quote

bs = chr(92)  # a single backslash


def _esc(s: str) -> str:
    """Escape for the WIFI: format."""
    for ch in (bs, ';', ',', ':', '"'):
        s = s.replace(ch, bs + ch)
    return s


def _vesc(s: str) -> str:
    """Escape for vCard values."""
    return s.replace(bs, bs + bs).replace("\n", bs + "n").replace(";", bs + ";").replace(",", bs + ",")


def url(value: str) -> str:
    """Add https:// when the value has no scheme (example.com -> https://example.com)."""
    value = value.strip()
    if "://" in value or value.lower().startswith(("mailto:", "tel:", "sms:", "geo:")):
        return value
    return "https://" + value


def wifi(ssid: str, password: str = "", auth: str = "WPA", hidden: bool = False) -> str:
    """Join-this-network code. auth: WPA (covers WPA2/WPA3), WEP or nopass."""
    auth = {"nopass": "nopass", "none": "nopass"}.get(auth.lower(), auth.upper())
    out = f"WIFI:T:{auth};S:{_esc(ssid)};"
    if auth != "nopass":
        out += f"P:{_esc(password)};"
    if hidden:
        out += "H:true;"
    return out + ";"


def mailto(to: str, subject: str = "", body: str = "") -> str:
    parts = []
    if subject:
        parts.append("subject=" + quote(subject))
    if body:
        parts.append("body=" + quote(body))
    return f"mailto:{to}" + ("?" + "&".join(parts) if parts else "")


def tel(number: str) -> str:
    return "tel:" + number.replace(" ", "")


def sms(number: str, body: str = "") -> str:
    return f"sms:{number.replace(' ', '')}" + (f"?body={quote(body)}" if body else "")


def geo(lat: float, lon: float) -> str:
    return f"geo:{lat},{lon}"


def vcard(name: str, org: str = "", title: str = "", phone: str = "", email: str = "", website: str = "") -> str:
    """vCard 3.0 contact. `name` is 'First Last'."""
    bits = name.strip().split()
    family = bits[-1] if len(bits) > 1 else ""
    given = " ".join(bits[:-1]) if len(bits) > 1 else name.strip()
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"N:{_vesc(family)};{_vesc(given)};;;", f"FN:{_vesc(name.strip())}"]
    if org:
        lines.append(f"ORG:{_vesc(org)}")
    if title:
        lines.append(f"TITLE:{_vesc(title)}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{_vesc(phone)}")
    if email:
        lines.append(f"EMAIL:{_vesc(email)}")
    if website:
        lines.append(f"URL:{_vesc(website)}")
    lines.append("END:VCARD")
    return "\n".join(lines)
