"""Lay the edition out as letter-size pages and print them to PDF with headless Chromium."""

import re
import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from . import fonts
from .dates import fmt

TEMPLATES = Path(__file__).resolve().parent / "templates"

# Shrink any page whose content runs past the bottom, a couple of percent at a
# time, so a busy day still prints on exactly three sheets.
FIT_PAGES = """async () => {
  await document.fonts.ready;
  const zooms = [];
  for (const page of document.querySelectorAll('.page')) {
    const inner = page.querySelector('.inner');
    let z = 1;
    const over = () => inner.getBoundingClientRect().height > page.getBoundingClientRect().height + 0.5;
    while (over() && z > 0.8) {
      z = Math.round((z - 0.02) * 100) / 100;
      inner.style.setProperty('--z', z);
    }
    zooms.push(over() ? -z : z);
  }
  return zooms;
}"""


# Upcoming work that's a test, set in bold on A4.
TEST_LIKE = re.compile(r"\b(test|quiz|exam|assessment|midterm|final)\b", re.IGNORECASE)


def roman(n):
    out = ""
    for value, numeral in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                           (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        count, n = divmod(n, value)
        out += numeral * count
    return out


def money(usd):
    """Under a dollar in cents (23¢, 0.4¢), otherwise dollars ($1.05, $1,250)."""
    if usd < 1:
        return f"{usd * 100:.0f}¢" if usd >= 0.1 else f"{usd * 100:.1f}¢"
    return f"${usd:,.2f}" if usd < 100 else f"${usd:,.0f}"


def render(ctx, out_pdf, png=False):
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape())
    env.filters["fmt"] = fmt
    env.tests["test_like"] = lambda title: bool(TEST_LIKE.search(title or ""))
    env.filters["roman"] = roman
    env.filters["money"] = money
    page_html = env.get_template("paper.html").render(
        **ctx, fonts=fonts.ensure(), font_dir=fonts.FONT_DIR.as_uri()
    )
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    # Written next to the PDF so file:// images and fonts load from disk.
    html_path = out_pdf.with_suffix(".html")
    html_path.write_text(page_html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.emulate_media(media="print")
        page.goto(html_path.as_uri(), wait_until="networkidle")
        for n, z in enumerate(page.evaluate(FIT_PAGES), 1):
            if z < 0:
                print(f"render: page A{n} still overflows at {-z:.0%} size")
            elif z < 1:
                print(f"render: page A{n} shrunk to {z:.0%} to fit")
        page.pdf(path=str(out_pdf), prefer_css_page_size=True, print_background=True)
        browser.close()

    pages = len(re.findall(rb"/Type\s*/Page[^s]", out_pdf.read_bytes()))
    print(f"render: {pages} page{'s' if pages != 1 else ''}")
    if png and shutil.which("pdftoppm"):
        subprocess.run(
            ["pdftoppm", "-png", "-r", "110", str(out_pdf), str(out_pdf.with_suffix(""))],
            check=True,
        )
    return out_pdf
