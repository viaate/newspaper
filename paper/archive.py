"""The archive: every past paper on a passcode-locked website.

`python -m paper archive` turns each out/<date>.pdf into page images, encrypts them with
a key made from the passcode in config.toml ([archive] passcode), and writes a static site
to site/. `--publish` pushes that site to GitHub Pages.

The files are encrypted with AES-GCM under a key derived from the passcode with PBKDF2,
which is slow on purpose; the browser derives the same key to decrypt. Without the
passcode the files are noise, but anyone who has them can try every 4-digit code, so a
short passcode keeps out the curious, not the determined. A longer one is much stronger.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw, ImageFont

from .config import ROOT

ITERATIONS = 1_000_000
DETAILS = 2  # bump when _details() learns a new field
SITE = ROOT / "site"
ISSUE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.pdf$")


def _key(passcode, salt):
    return hashlib.pbkdf2_hmac("sha256", passcode.encode(), salt, ITERATIONS, 32)


def _seal(key, data):
    iv = os.urandom(12)
    return iv + AESGCM(key).encrypt(iv, data, None)


def _webp(img, width, quality):
    img = img.convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    with tempfile.SpooledTemporaryFile() as f:
        img.save(f, "WEBP", quality=quality, method=6)
        f.seek(0)
        return f.read()


def _details(cfg, day):
    """Headline, deck and the rest from the issue's saved HTML."""
    out = {"date": day, "weekday": date.fromisoformat(day).strftime("%A")}
    page = cfg["out_dir"] / f"{day}.html"
    if not page.exists():
        return out
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    text = lambda sel: (soup.select_one(sel).get_text(" ", strip=True) if soup.select_one(sel) else "")
    out |= {"headline": text("h2.headline"), "deck": text("p.deck"), "lead": text(".lead-body p")}
    dateline = text(".dateline span")
    if m := re.search(r"Vol\.\s*([IVXLCDM]+)\s*·\s*No\.\s*(\d+)", dateline):
        out |= {"volume": m.group(1), "number": int(m.group(2))}
    if (m := re.search(r"·\s*(\S+)$", text(".nameplate .ear:last-child div:last-child"))) and m.group(1) != "Free":
        out["price"] = m.group(1)
    # A few numbers for the site's stats and trend lines (pages from before A4 lack them).
    gpas = [g.get_text(strip=True) for g in soup.select(".gpa-num")]
    if gpas:
        out["gpa"] = gpas[0]
        out["gpa_weighted"] = gpas[1] if len(gpas) > 1 else None
    if m := re.match(r"(\d+)", text(".temp")):
        out["high"] = int(m.group(1))
    for row in soup.select("table.money tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if cells and cells[0] == "Together" and len(cells) > 1:
            out["followers"] = cells[1]
    if m := re.search(r"This issue cost (\S+) to make", soup.get_text(" ", strip=True)):
        out["price"] = m.group(1).rstrip(":")
    return out


def _icon(size, rule=True):
    """The site's icon: the nameplate's blackletter T on ink, with the masthead's red rule."""
    s = size * 4  # drawn large, then shrunk, for clean edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * .2), fill=(23, 20, 15, 255))
    font = ImageFont.truetype(str(ROOT / "paper/fonts/UnifrakturMaguntia-400.ttf"), int(s * (.78 if rule else .98)))
    box = d.textbbox((0, 0), "T", font=font)
    lift = s * (.05 if rule else 0)
    d.text(((s - box[2] - box[0]) / 2, (s - box[3] - box[1]) / 2 - lift), "T", font=font, fill=(244, 239, 229, 255))
    if rule:
        d.rectangle([s * .22, s * .82, s * .78, s * .82 + s * .045], fill=(216, 56, 42, 255))
    return img.resize((size, size), Image.LANCZOS)


def build(cfg):
    """Encrypt any new or changed issues into site/ and rewrite the index. Returns the count."""
    passcode = str(cfg.get("archive", {}).get("passcode", ""))
    if not passcode:
        raise SystemExit("Set a passcode under [archive] in config.toml first.")
    data = SITE / "data"
    data.mkdir(parents=True, exist_ok=True)
    meta_path, manifest_path = SITE / "meta.json", cfg["data_dir"] / "archive.json"

    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    salt = base64.b64decode(meta["salt"]) if meta.get("salt") else os.urandom(16)
    key = _key(passcode, salt)
    fingerprint = hashlib.sha256(key).hexdigest()[:16]
    if manifest.get("key") != fingerprint:  # new passcode: start over
        shutil.rmtree(data, ignore_errors=True)
        data.mkdir(parents=True)
        manifest = {"key": fingerprint, "issues": {}}
    if manifest.get("details") != DETAILS:  # the site wants new fields: reread every issue's page
        for day, issue in manifest["issues"].items():
            manifest["issues"][day] = {"stamp": issue["stamp"], "pages": issue["pages"], **_details(cfg, day)}
        manifest["details"] = DETAILS
    # The passcode's length lets the lock screen show the right number of dots.
    meta = {"salt": base64.b64encode(salt).decode(), "iterations": ITERATIONS, "length": len(passcode),
            "numeric": passcode.isdigit(), "check": base64.b64encode(_seal(key, b"olivia-times")).decode()}

    days = sorted(m.group(1) for p in cfg["out_dir"].glob("*.pdf") if (m := ISSUE.match(p.name)))
    changed = 0
    for day in days:
        pdf = cfg["out_dir"] / f"{day}.pdf"
        stamp = str(pdf.stat().st_mtime_ns)
        if manifest["issues"].get(day, {}).get("stamp") == stamp:
            continue
        folder = data / day
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-png", "-r", "130", str(pdf), f"{tmp}/p"], check=True)
            pages = sorted(Path(tmp).glob("p-*.png"))
            for n, png in enumerate(pages, 1):
                img = Image.open(png)
                (folder / f"p{n}.bin").write_bytes(_seal(key, _webp(img, 1100, 80)))
                if n == 1:
                    (folder / "thumb.bin").write_bytes(_seal(key, _webp(img, 480, 72)))
        manifest["issues"][day] = {"stamp": stamp, **_details(cfg, day), "pages": len(pages)}
        changed += 1

    # Issues whose PDF is gone stay in the archive: it's the record.
    index = [manifest["issues"][d] | {"stamp": None} for d in sorted(manifest["issues"], reverse=True)]
    (data / "index.bin").write_bytes(_seal(key, json.dumps(index).encode()))
    meta_path.write_text(json.dumps(meta))
    (SITE / "index.html").write_text((ROOT / "paper/templates/archive.html").read_text(encoding="utf-8"), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    if not (SITE / "icon-512.png").exists():
        _icon(48, rule=False).save(SITE / "favicon.png")
        _icon(180).save(SITE / "apple-touch-icon.png")
        _icon(512).save(SITE / "icon-512.png")
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return changed


def publish(cfg):
    """Push site/ to the GitHub repo under [archive] repo, as a single commit."""
    repo = cfg.get("archive", {}).get("repo", "")
    if not repo:
        raise SystemExit("Set repo = \"owner/name\" under [archive] in config.toml to publish.")
    token = cfg["secrets"].get("ARCHIVE_GITHUB_TOKEN")
    if not token:
        raise SystemExit("Add ARCHIVE_GITHUB_TOKEN to .env to publish (see the README).")
    # The token goes in through the environment, never the command line or a saved config.
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
           "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}", "GIT_TERMINAL_PROMPT": "0"}
    git = lambda *a: subprocess.run(["git", "-C", str(SITE), *a], check=True, capture_output=True, text=True, env=env)
    if not (SITE / ".git").exists():
        git("init", "-q", "-b", "main")
    # One commit with no history: the site keeps only what's in it now, so it never bloats.
    # The last commit stays in the local object store, so a push sends only new files.
    subprocess.run(["git", "-C", str(SITE), "branch", "-D", "next"], capture_output=True)
    git("checkout", "-q", "--orphan", "next")
    git("add", "-A")
    git("-c", "user.name=The Olivia Times", "-c", "user.email=paper@localhost", "commit", "-q", "-m",
        f"Archive as of {datetime.now():%Y-%m-%d %H:%M}")
    git("branch", "-M", "next", "main")
    try:
        git("push", "-q", "--force", f"https://github.com/{repo}.git", "main")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"push to {repo} failed: {(e.stderr or '').strip()[-200:]}") from None
    owner, name = repo.split("/")
    return f"https://{owner.lower()}.github.io/{name}/"
