# qrlogo

QR codes with **your logo in the middle**, for anything: a link, Wi-Fi, a contact card, a phone number.

One command gives you three files, and every one of them is **decoded again before it is accepted**, so a code that does not scan never leaves the tool:

| Format | Use it for |
|---|---|
| `.svg` | websites, print, anything vector |
| `.png` | slides, PDFs, chat |
| `.email.html` | HTML e-mail. A table of coloured cells, **no `<img>`**, so it survives drafting tools that strip images |

![example](examples/out/demo.png)

## Install

Reuse it from any project, no copying files around:

```bash
# once per machine, as a command on your PATH (recommended)
pipx install "qrlogo[all] @ git+ssh://git@github.com/lordalex/qrlogo.git"

# or inside a project's own virtualenv
pip install "qrlogo[all] @ git+ssh://git@github.com/lordalex/qrlogo.git"

# or to work on the tool itself
git clone git@github.com:lordalex/qrlogo.git && cd qrlogo
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

`[all]` = the decoding check (OpenCV) + SVG logos (cairosvg). Without it the tool still works, but it
warns that it could not decode the results. Upgrade later with `pipx upgrade qrlogo` (or re-run the
install line). Pin a release with `...qrlogo.git@v0.1.0`.

Each project keeps only its own **brand profile** (a small JSON file with colours and a logo path);
the tool itself lives here. Example: `examples/brand.example.json`.

## Use

```bash
# a link, plain
qrlogo https://example.com --logo logo.png --out out --name site

# the same, from a saved brand (colours + logo + sizes in one JSON file)
qrlogo --brand brand.json https://example.com --out out --name site

# other things people scan
qrlogo url example.com --logo logo.png                       # adds https:// for you
qrlogo wifi --ssid "Cafe Net" --password "s3cret" --logo logo.png
qrlogo vcard --contact-name "Ada Lovelace" --org "Analytical" --phone "+1 555 0100" --email ada@example.com
qrlogo mailto hello@example.com --subject "Hi"
qrlogo tel "+58 414 217 5746"
qrlogo sms "+58 414 217 5746" --body "Hola"
qrlogo geo 10.4806 -66.9036

# just show what would be encoded
qrlogo wifi --ssid Home --password x --print-data
```

Output (all in `--out`, default `./qr-out`):

```
data    : https://example.com/hello
code    : version 4, 33x33 modules, error correction H, logo 9x9 modules
png     : out/site.png (9,531 bytes)  decodes OK
svg     : out/site.svg (17,958 bytes)  decodes OK
email   : out/site.email.html (22,465 bytes)  decodes OK
```

`--formats svg,png,email` chooses what to write (default `svg,png`).

## Look

Every flag can also live in a brand profile (see `examples/brand.example.json`); flags win over the profile.

| Flag / key | What it does | Default |
|---|---|---|
| `--fg` / `fg` | module colour | `#000000` |
| `--finder` / `finder` | the three corner squares | same as `fg` |
| `--bg` / `bg` | background | `#ffffff` |
| `--quiet` / `quiet` | blank border, in modules (spec says 4, 2 still scans) | `4` |
| `--shape` / `shape` | `square`, `dots`, `rounded` | `square` |
| `--align` / `align` | colour the small alignment squares like the corners | off |
| `--logo` / `logo` | PNG, JPG or SVG. In a profile the path is relative to the JSON file | none |
| `--logo-crop` / `logo_crop` | `x0,y0,x1,y1` as fractions of the image, to cut away empty space | whole image |
| `--logo-bg` / `logo_bg` | tile background | the logo's own corner colour |
| `--logo-scale` / `logo_scale` | tile width as a share of the code | `0.27` |
| `--logo-shape` / `logo_shape` | `square`, `rounded`, `circle` | `square` |
| `--logo-plate` / `logo_plate` | blank margin around the tile, in modules | `0.35` |
| `--ec` / `ec` | error correction `L M Q H` (a logo needs `Q` or `H`) | `H` with a logo, else `M` |

The logo never covers more than 14 % of the code, and the code uses error correction H (it can lose 30 %). If a very long payload plus a big logo cannot be decoded, the tool says so and exits with an error instead of writing a bad file.

## E-mail notes

- Paste `name.email.html` into the HTML body where the code should appear. Wrap it in your own `<td>` / `<div>` for position and add a caption underneath.
- Size: about 20-30 KB. Gmail clips a message's HTML at about 102 KB, so the tool warns above 60 KB. `--email-cell 2` halves the logo's size at some loss of detail; `--email-colors` trims the logo palette.
- Why it is built the way it is: one spacer row fixes every column width and the first cell of each row carries the row height. Without those two things, the cell that holds the logo collapses the whole table into vertical bars. The tool checks the layout (`colspan`/`rowspan`) by laying the table out itself and decoding the result.
- Web links in Gmail *drafts* made by some API tools get rewritten to expire. The QR is not a link, so it is not affected, but anything you put around it may be.

## As a library

```python
from qrlogo import Style, LogoSpec, generate, payloads

res = generate(
    payloads.wifi("Cafe Net", "s3cret"),
    Style(fg="#222222", finder="#a90808", quiet=2),
    LogoSpec("logo.png", crop=(0.24, 0.27, 0.76, 0.73)),
    formats=("svg", "png", "email"),
)
res.png.save("wifi.png")
open("wifi.svg", "w").write(res.svg)
html_snippet = res.email
assert res.ok          # every format decoded back to the input
```

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

They need OpenCV; they cover plain codes, logos of different shapes, colours, long payloads, Wi-Fi and vCard text, the e-mail table layout and the brand-profile loader.
