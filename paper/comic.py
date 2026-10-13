"""The daily comic: a black-and-white strip starring your avatar, drawn by Gemini.

One-time setup makes a cartoon avatar from a few photos:

    python -m paper avatar make data/photos/*.jpg   # draws options A-D
    python -m paper avatar pick B                     # keeps the one you like

After that, only the cartoon avatar is sent to Gemini each day, never the photos.
"""

import base64
import re
import shutil
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps

from . import spend

API ="https://generativelanguage.googleapis.com/v1beta"

# Strip titles for when the writer isn't available; it usually makes up its own.
TITLES = {
    "The Simpsons": "The {name}sons",
    "Bob's Burgers": "{name}'s Burgers",
    "Futurama": "{name}rama",
    "King of the Hill": "Queen of the Hill",
    "Daria": "{name}, Unimpressed",
    "BoJack Horseman": "{name} Horseman",
    "Rick and Morty": "{name} and Morty",
    "Archer": "Agent {name}",
    "Family Guy": "Family Gal",
    "American Dad!": "American Teen!",
    "South Park": "Mission Hills Park",
    "Solar Opposites": "Polar Opposites",
}


def style_for(day, styles):
    """A different show each day, cycling through the list."""
    return styles[day.toordinal() % len(styles)]


def fallback_title(style, name):
    return TITLES.get(style, "{name} Today").format(name=name)


def avatar_path(cfg):
    return cfg["data_dir"] / "avatar" / "avatar.png"


# ------------------------------------------------------------------ Gemini

def _model(cfg, key):
    if cfg["comic"].get("model"):
        return cfg["comic"]["model"]
    r = requests.get(f"{API}/models", params={"key": key, "pageSize": 200}, timeout=30)
    r.raise_for_status()
    names = [
        m["name"].removeprefix("models/") for m in r.json().get("models", [])
        if "image" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    if not names:
        raise RuntimeError("no Gemini image model is available to this key")
    # Newest version first; within it prefer flash (fast, cheap) over pro, the full model
    # over "lite" (which keeps faces and lettering less well), and stable over preview.
    def rank(name):
        version = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
        return (
            float(version.group(1)) if version else 0.0,
            "flash" in name,
            "lite" not in name,
            "preview" not in name,
        )
    return max(names, key=rank)


def _generate(cfg, prompt, images=(), aspect="21:9", what="comic"):
    key = cfg["secrets"]["GEMINI_API_KEY"]
    parts = [{"text": prompt}]
    for img in images:
        parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(img).decode()}})
    model = _model(cfg, key)
    image_config = {"aspectRatio": aspect}
    if cfg["comic"].get("size"):
        image_config["imageSize"] = cfg["comic"]["size"]

    def post(config):
        return requests.post(
            f"{API}/models/{model}:generateContent",
            params={"key": key},
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": config},
            },
            timeout=300,
        )

    r = post(image_config)
    if r.status_code == 400 and "imageSize" in image_config:
        # Older image models don't take a size; they make 1K images.
        r = post({"aspectRatio": aspect})
    r.raise_for_status()
    spend.record_gemini(cfg, what, r.json().get("usageMetadata", {}))
    for candidate in r.json().get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if data:
                return base64.b64decode(data)
    raise RuntimeError("Gemini returned no image")


def _ink(png_bytes, out_path):
    """Force pure black-and-white-and-gray, whatever the model sent back."""
    img = Image.open(BytesIO(png_bytes))
    img = ImageOps.autocontrast(img.convert("L"), cutoff=0.5)
    img.save(out_path)
    return out_path


def _png(path):
    buf = BytesIO()
    Image.open(path).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ daily strip

def draw(cfg, comic, style, out_path):
    """Draw today's strip. Returns the image path, or None if it can't be drawn."""
    avatar = avatar_path(cfg)
    if not (cfg["comic"].get("enabled", True) and cfg["secrets"]["GEMINI_API_KEY"] and avatar.exists()):
        return None
    panels = "\n".join(
        f'Panel {i}: {p["scene"]} Speech balloon from her: "{p["balloon"]}". '
        f'Small caption under the panel: "{p["caption"]}".'
        for i, p in enumerate(comic["panels"], 1)
    )
    prompt = f"""A daily newspaper comic strip: {len(comic["panels"])} panels in one horizontal row.
Black ink on white paper only. No color. Simple cross-hatching for shadows.
Draw it in the art style of the animated TV show {style}.
The star is the girl in the reference image ({cfg["comic"].get("look", "a teenage girl")}),
redrawn as a {style}-style character. Keep her face and hair recognizable.
No characters from {style} appear; she is the only recurring character.

In the top-left corner, letter the strip's title "{comic["title"]}" in lettering that looks
like the {style} logo, and right under it, in small plain capitals: "INSPIRED BY {style.upper()}".

{panels}

Clean panel borders, crisp readable lettering, no other words, no signature."""
    try:
        png = _generate(cfg, prompt, [_png(avatar)])
    except (requests.RequestException, RuntimeError, KeyError) as e:
        print(f"comic: couldn't draw today's strip: {e}")
        return None
    return _ink(png, out_path)


# ------------------------------------------------------------------ avatar setup

AVATAR_PROMPTS = [
    "clean, simple newspaper-comic line art, friendly expression",
    "slightly exaggerated cartoon proportions, big expressive eyes",
    "classic Sunday-funnies inking with bold outlines",
    "minimal modern webcomic style with thin even lines",
]


def make_avatars(cfg, photos):
    """Draw four avatar options (A-D) from your photos into data/avatar/."""
    if not cfg["secrets"]["GEMINI_API_KEY"]:
        raise SystemExit("Add GEMINI_API_KEY to .env first.")
    refs = [_png(p) for p in photos[:4]]
    folder = cfg["data_dir"] / "avatar"
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for letter, style in zip("ABCD", AVATAR_PROMPTS):
        prompt = f"""Turn the person in these photos into a cartoon character for a daily
newspaper comic strip. Black ink on white only, {style}.
Show the same character twice side by side: facing forward, and three-quarters view,
head to toe, neutral standing pose, plain white background. Keep her hair, face shape
and overall look recognizable ({cfg["comic"].get("look", "")}). No text."""
        path = folder / f"option-{letter}.png"
        _ink(_generate(cfg, prompt, refs, aspect="4:3", what="avatar"), path)
        made.append(path)
        print(f"drew avatar option {letter}: {path}")
    return made


def pick_avatar(cfg, letter):
    folder = cfg["data_dir"] / "avatar"
    choice = folder / f"option-{letter.upper()}.png"
    if not choice.exists():
        raise SystemExit(f"No option {letter.upper()}. Run `python -m paper avatar make <photos>` first.")
    shutil.copyfile(choice, avatar_path(cfg))
    print(f"Avatar set to option {letter.upper()}.")
    return avatar_path(cfg)


def avatar_options(cfg):
    folder = cfg["data_dir"] / "avatar"
    return [(p.stem[-1], p) for p in sorted(folder.glob("option-*.png"))] if folder.exists() else []


def photo_paths(paths):
    return [Path(p) for p in paths if Path(p).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
