"""How much toner is left, so the paper can say when to buy more.

Read from the printer itself when CUPS has its supply level (driverless printers like the
Brother report "marker-levels"); otherwise estimated from pages printed since the last
cartridge, counted here. After putting in a new cartridge:
    python -m paper toner reset [pages]   # pages it's rated for; default 1200 (TN830)
"""

import json
import re
import subprocess
from datetime import date

LOW = 15                 # percent: print the reminder at or below this
STARTER_PAGES = 700      # the cartridge that comes in the box
TN830_PAGES = 1200


def _path(cfg):
    return cfg["data_dir"] / "toner.json"


def _state(cfg):
    path = _path(cfg)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"rated_pages": STARTER_PAGES, "printed": 0, "since": date.today().isoformat()}


def _write(cfg, state):
    path = _path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def count_pages(cfg, pdf):
    """Add a printed PDF's pages to the count."""
    pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    state = _state(cfg)
    state["printed"] += pages
    _write(cfg, state)


def reset(cfg, rated_pages=TN830_PAGES):
    _write(cfg, {"rated_pages": rated_pages, "printed": 0, "since": date.today().isoformat()})


def _reported(printer):
    """The printer's own toner percentage via CUPS, or None if it doesn't report one."""
    try:
        cmd = ["lpoptions"] + (["-p", printer] if printer else [])
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    levels = re.search(r"marker-levels=(\S+)", out)
    if not levels:
        return None
    values = [int(v) for v in levels.group(1).split(",") if v.lstrip("-").isdigit()]
    values = [v for v in values if 0 <= v <= 100]  # -1/-2/-3 mean unknown
    return min(values) if values else None


def level(cfg):
    """{"percent", "source": "printer" | "estimate", "low"}."""
    percent = _reported(cfg["printer"].get("name", ""))
    source = "printer"
    if percent is None:
        state = _state(cfg)
        percent = max(0, round(100 * (1 - state["printed"] / max(1, state["rated_pages"]))))
        source = "estimate"
    return {"percent": percent, "source": source, "low": percent <= LOW}
