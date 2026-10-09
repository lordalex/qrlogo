import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from qrlogo import LogoSpec, Style, generate, payloads
from qrlogo import verify
from qrlogo.cli import main as cli_main


def make_logo(path, color="#d44973"):
    im = Image.new("RGB", (400, 300), color)  # wide, to exercise padding to a square
    d = ImageDraw.Draw(im)
    d.ellipse([100, 50, 300, 250], fill="white")
    d.rectangle([180, 100, 220, 200], fill=color)
    im.save(path)
    return str(path)


class RoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not verify.available():
            raise unittest.SkipTest("opencv not installed")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.logo = make_logo(Path(cls.tmp.name) / "logo.png")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def all_formats(self, data, style=None, logo=None, **kw):
        r = generate(data, style, logo, formats=("svg", "png", "email"), **kw)
        self.assertTrue(r.ok, r.checks)
        for fmt in ("svg", "png", "email"):
            self.assertEqual(r.checks[fmt], data, fmt)
        return r

    def test_plain_url_no_logo(self):
        r = self.all_formats("https://example.com/a?b=c")
        self.assertEqual(r.tile_modules, 0)
        self.assertEqual(r.ec, "M")

    def test_logo_forces_high_error_correction(self):
        r = self.all_formats("https://example.com", logo=LogoSpec(self.logo))
        self.assertEqual(r.ec, "H")
        self.assertGreaterEqual(r.tile_modules, 3)
        self.assertEqual(r.tile_modules % 2, 1)

    def test_logo_with_low_ec_is_refused(self):
        with self.assertRaises(ValueError):
            generate("x", logo=LogoSpec(self.logo), ec="L")

    def test_long_payload(self):
        data = "https://example.com/" + "segment/" * 25 + "end"
        r = self.all_formats(data, logo=LogoSpec(self.logo))
        self.assertGreater(r.version, 5)

    def test_colours_and_alignment(self):
        style = Style(fg="#222", finder="#a90808", bg="#fff7ee", quiet=2, align=True)
        self.all_formats("https://example.com/x" + "y" * 40, style, LogoSpec(self.logo))

    def test_shapes(self):
        for shape in ("dots", "rounded"):
            r = generate("https://example.com", Style(shape=shape), LogoSpec(self.logo), formats=("svg", "png"))
            self.assertTrue(r.ok, shape)

    def test_logo_shapes(self):
        for shape in ("rounded", "circle"):
            self.all_formats("https://example.com", logo=LogoSpec(self.logo, shape=shape))

    def test_dark_logo_background_on_light_code(self):
        self.all_formats("hello", logo=LogoSpec(self.logo, bg="#1d0a2a"))

    def test_wifi_payload(self):
        self.all_formats(payloads.wifi("Café;Net", "pa:ss"), logo=LogoSpec(self.logo))

    def test_vcard_payload(self):
        self.all_formats(payloads.vcard("Ada Lovelace", org="Analytical", phone="+1 555 0100", email="ada@example.com"))

    def test_email_table_geometry(self):
        r = generate("https://example.com", Style(quiet=2), LogoSpec(self.logo), formats=("email",), email_px=4)
        grid = verify.email_grid(r.email, "#ffffff")
        n = r.n + 4
        self.assertEqual(grid.shape[:2], (n, n))
        self.assertIn('table-layout:fixed', r.email)
        self.assertNotIn("<img", r.email)

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            generate("x", formats=("pdf",))


class Cli(unittest.TestCase):
    def test_print_data_wifi(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main(["wifi", "--ssid", "Home", "--password", "secret", "--print-data"])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "WIFI:T:WPA;S:Home;P:secret;;")

    def test_brand_profile_with_relative_logo(self):
        if not verify.available():
            self.skipTest("opencv not installed")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            make_logo(d / "logo.png")
            (d / "brand.json").write_text(json.dumps({"fg": "#222222", "finder": "#a90808", "logo": "logo.png", "quiet": 2, "formats": "svg,png,email"}))
            out = d / "out"
            rc = cli_main(["--brand", str(d / "brand.json"), "--out", str(out), "--name", "t", "https://example.com"])
            self.assertEqual(rc, 0)
            for ext in ("png", "svg", "email.html"):
                self.assertTrue((out / f"t.{ext}").is_file(), ext)

    def test_url_kind_adds_scheme(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli_main(["url", "example.com", "--print-data"])
        self.assertEqual(buf.getvalue().strip(), "https://example.com")


if __name__ == "__main__":
    unittest.main()
