"""Turn a story's photo into a grainy black-and-white newsprint picture."""

import re
from io import BytesIO

import requests
from PIL import Image, ImageOps

UA = {"User-Agent": "Mozilla/5.0 (newspaper bot; personal use)"}
OG_IMAGE = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]+content=["']([^"']+)""", re.I
)


def find_image(url):
    """The page's share image (og:image), if it has one."""
    try:
        page = requests.get(url, headers=UA, timeout=15)
        page.raise_for_status()
    except requests.RequestException:
        return None
    match = OG_IMAGE.search(page.text[:200_000])
    return match.group(1) if match else None


def newsprint(image_url, out_path, width=1400, aspect=2):
    """Download, crop to `aspect`, and dither to 1-bit like newsprint. Returns the path or None."""
    try:
        r = requests.get(image_url, headers=UA, timeout=20)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
        img.load()
    except (requests.RequestException, OSError):
        return None
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.fit(img, (width, round(width / aspect)))
    img = ImageOps.autocontrast(img, cutoff=1)
    # A fine 1-bit dither reads as newsprint and prints cleanly on a laser printer.
    img.convert("1").save(out_path)
    return out_path
