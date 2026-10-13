"""OpenAI Codex on this PC: how much of the ChatGPT plan's Codex limits is used, and what
Codex worked on overnight.

Codex keeps each session as ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl. Its token-count
events carry the plan's rate limits (a short "primary" window and a weekly "secondary"
one), so the paper runs one tiny `codex exec` turn each morning to refresh them, then
reads the newest log. Sessions with activity since last night go in "While You Slept".
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def _home():
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def _codex(cfg):
    return (cfg.get("codex", {}).get("command") or shutil.which("codex")
            or "/home/linuxbrew/.linuxbrew/bin/codex")


def _logs(since=None):
    root = _home() / "sessions"
    logs = sorted(root.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime) if root.exists() else []
    if since:
        logs = [p for p in logs if datetime.fromtimestamp(p.stat().st_mtime).astimezone() >= since]
    return logs


def _find(obj, key):
    """The last value under `key` anywhere in a JSON object."""
    found = None
    if isinstance(obj, dict):
        for k, v in obj.items():
            found = v if k == key else (_find(v, key) or found)
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, key) or found
    return found


def _window(w, now):
    if not isinstance(w, dict) or w.get("used_percent") is None:
        return None
    resets = None
    if w.get("resets_at"):
        resets = datetime.fromtimestamp(int(w["resets_at"]))
    elif w.get("resets_in_seconds") is not None:
        resets = now + timedelta(seconds=int(w["resets_in_seconds"]))
    minutes = w.get("window_minutes") or 0
    return {"used": round(float(w["used_percent"])), "resets": resets,
            "label": "Week" if minutes >= 7 * 24 * 60 - 60 else f"{round(minutes / 60)} hours" if minutes else "Window"}


def limits(cfg):
    """{"name", "windows": [...]} or {"name", "error"}."""
    if not (_home() / "auth.json").exists():
        return {"name": "Codex", "error": "not signed in yet"}
    run = subprocess.run([_codex(cfg), "exec", "--skip-git-repo-check", "-s", "read-only", "Reply with just: OK"],
                         cwd=cfg["data_dir"], capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    now = datetime.now()
    for log in reversed(_logs()[-3:]):
        rate = None
        for line in log.open(encoding="utf-8", errors="replace"):
            try:
                rate = _find(json.loads(line), "rate_limits") or rate
            except ValueError:
                continue
        if rate:
            windows = [w for w in (_window(rate.get("primary"), now), _window(rate.get("secondary"), now)) if w]
            if windows:
                return {"name": "Codex", "windows": sorted(windows, key=lambda w: w["label"] != "Week")}
    # Out of usage, Codex reports no windows; its error says when it opens again.
    said = run.stderr + run.stdout
    if "hit your usage limit" in said:
        resets = None
        if m := re.search(r"try again at (\w{3}) (\d+)\w*, (\d{4}) (\d+:\d+ [AP]M)", said):
            resets = datetime.strptime(" ".join(m.groups()), "%b %d %Y %I:%M %p")
        return {"name": "Codex", "windows": [{"label": "Limit", "used": 100, "resets": resets}]}
    reason = said.strip().splitlines()[-1:] or ["no usage reported"]
    return {"name": "Codex", "error": reason[0][:90]}


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text"))
    return ""


def sessions(cfg, since):
    paper_data = str(cfg["data_dir"])
    out = []
    for log in _logs(since):
        cwd, asks, replies, stamps = None, [], [], []
        for line in log.open(encoding="utf-8", errors="replace"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            payload = e.get("payload") or {}
            cwd = payload.get("cwd") or cwd
            if e.get("type") != "response_item" or payload.get("type") != "message" or not e.get("timestamp"):
                continue
            when = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).astimezone()
            text = re.sub(r"\s+", " ", _text(payload.get("content"))).strip()
            if when < since or not text or text.startswith("<"):  # <environment_context> and the like
                continue
            stamps.append(when)
            (asks if payload.get("role") == "user" else replies).append(text)
        if not stamps or not cwd or cwd.startswith(paper_data):
            continue
        out.append({"account": "Codex", "where": "this PC", "project": Path(cwd).name,
                    "start": min(stamps), "end": max(stamps), "requests": len(asks),
                    "first_ask": asks[0][:300] if asks else "", "last_reply": replies[-1][:400] if replies else "",
                    "commits": []})
    return out
