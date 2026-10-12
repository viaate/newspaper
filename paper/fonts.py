"""Download the paper's fonts from Google Fonts (all SIL Open Font License) on first use."""

import json
import re
from pathlib import Path

import requests

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FAMILIES = (
    "UnifrakturMaguntia"
    "|Playfair+Display:700,900"
    "|Source+Serif+4:400,400i,600,700,700i"
    "|Libre+Franklin:500,700,900"
    "|Comic+Neue:700"
)
BLOCK = re.compile(r"@font-face\s*{([^}]*)}")


def _field(block, name):
    m = re.search(rf"{name}:\s*([^;]+);", block)
    return m.group(1).strip().strip("'\"") if m else ""


def ensure():
    """List of {family, weight, style, file}; downloads anything missing."""
    manifest = FONT_DIR / "fonts.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(saved, dict) and saved.get("families") == FAMILIES:
            return saved["fonts"]

    FONT_DIR.mkdir(exist_ok=True)
    # A non-browser User-Agent makes the CSS API hand back plain TTF files.
    css = requests.get(
        f"https://fonts.googleapis.com/css?family={FAMILIES}",
        headers={"User-Agent": "curl/8"}, timeout=20,
    )
    css.raise_for_status()
    fonts = []
    for block in BLOCK.findall(css.text):
        family, weight, style = _field(block, "font-family"), _field(block, "font-weight"), _field(block, "font-style")
        url = re.search(r"url\(([^)]+)\)", block).group(1)
        name = f"{family.replace(' ', '')}-{weight}{'i' if style == 'italic' else ''}.ttf"
        data = requests.get(url, timeout=30)
        data.raise_for_status()
        (FONT_DIR / name).write_bytes(data.content)
        fonts.append({"family": family, "weight": weight, "style": style, "file": name})
    manifest.write_text(json.dumps({"families": FAMILIES, "fonts": fonts}, indent=1), encoding="utf-8")
    return fonts
