# qrlogo: notes for agents working in or with this repo

**What it is:** a small Python CLI/library that makes QR codes with a logo in the middle and writes
SVG, PNG and an e-mail-safe HTML table. Every output is decoded again (OpenCV) before it is accepted.

**Use it, do not re-implement it.** Any project that needs a QR with a logo should call this tool with
its own brand profile (`--brand profile.json`) instead of writing a new generator. Plain black QR codes
are not acceptable for LA's brands (Violeta, QRIDIT, ...): they carry the logo.

## Commands
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[all]"
python -m unittest discover -s tests -v          # 15 tests, needs OpenCV
qrlogo --brand examples/brand.example.json https://example.com --out /tmp/qr --name demo
```

## Rules that matter
- **Never skip verification.** If a format does not decode back to the input, `generate()` raises and the
  CLI exits 1. Fix the cause (smaller `logo_scale`, higher `ec`, more `quiet`), do not add a bypass.
- **E-mail table layout is load-bearing:** one spacer `<tr>` of `<td width=px>` fixes the column widths and the
  first cell of every row carries `height`. Remove either and the rowspan logo cell collapses the table
  into vertical bars. `verify.email_grid` lays the table out like a browser and a test checks it.
- **No `<img>` in the e-mail output.** Gmail drafting tools strip images; that is the whole reason this format exists.
- **Brand data stays out of this repo.** Profiles and logos live in each project; `examples/` only has a neutral demo.
- Keep it dependency-light: qrcode, Pillow, numpy (+ optional OpenCV, cairosvg).

## Layout
`src/qrlogo/core.py` (matrix, PNG/SVG/e-mail renderers, `generate`) · `logo.py` (load/crop/tile/palette) ·
`verify.py` (decoders, e-mail table parser) · `payloads.py` (wifi/vcard/mailto/tel/sms/geo) · `cli.py`.

## Release
Bump `version` in `pyproject.toml` and `__version__`, commit, `git tag vX.Y.Z && git push --tags`.
