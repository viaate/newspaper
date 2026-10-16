"""How much toner is left, so the paper can say when to buy more.

Read from the printer itself: CUPS's saved copy of its "marker-levels" when the printer is
a saved queue, otherwise by asking the printer over IPP with `ipptool` (its address from
[printer] uri in config.toml, or found with `ippfind`). If neither works, estimated from
pages printed since the last cartridge, counted here. After putting in a new cartridge:
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


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _numbers(text):
    values = [int(v) for v in re.split(r"[,\s]+", text.strip()) if v.lstrip("-").isdigit()]
    return [v for v in values if 0 <= v <= 100]  # -1/-2/-3 mean unknown


def _printer_uri(cfg):
    if cfg["printer"].get("uri"):
        return cfg["printer"]["uri"]
    found = _run(["ippfind", "--ls"]).split()
    return next((w for w in found if w.startswith("ipp")), "")


def _reported(cfg):
    """(percent, low_percent) from the printer itself, or None if it can't be read."""
    printer = cfg["printer"].get("name", "")
    saved = re.search(r"marker-levels=(\S+)", _run(["lpoptions"] + (["-p", printer] if printer else [])))
    if saved and _numbers(saved.group(1).replace(",", " ")):
        return min(_numbers(saved.group(1).replace(",", " "))), None
    uri = _printer_uri(cfg)
    if not uri:
        return None
    out = _run(["ipptool", "-tv", uri, "get-printer-attributes.test"])
    levels = re.search(r"marker-levels \(.*?\) = ([-\d, ]+)", out)
    low = re.search(r"marker-low-levels \(.*?\) = ([-\d, ]+)", out)
    if not levels or not _numbers(levels.group(1)):
        return None
    return min(_numbers(levels.group(1))), (max(_numbers(low.group(1))) if low and _numbers(low.group(1)) else None)


def level(cfg):
    """{"percent", "source": "printer" | "estimate", "low"}. "low" uses the printer's own
    low mark when it gives one, else LOW."""
    reported = _reported(cfg)
    if reported:
        percent, low_mark = reported
        return {"percent": percent, "source": "printer", "low": percent <= (low_mark or LOW)}
    state = _state(cfg)
    percent = max(0, round(100 * (1 - state["printed"] / max(1, state["rated_pages"]))))
    return {"percent": percent, "source": "estimate", "low": percent <= LOW}
