"""What Claude worked on overnight.

Claude Code keeps each session's transcript on this PC under
<config dir>/projects/<project>/<session>.jsonl. Sessions with activity since last
night ([overnight] since, 9 P.M. by default) are summarized from that: the project, when
it ran, what was asked, Claude's last words, and the git commits made there since.
claude.ai/code sessions that ran in the cloud arrive as data/overnight/cloud-*.json,
written each morning by a Claude routine (see the README).
"""

import json
import os
import re
import subprocess
from datetime import datetime, time, timedelta
from pathlib import Path

META = re.compile(r"<(system-reminder|command-[a-z]+|local-command-[a-z]+)>.*?</\1>", re.DOTALL)
# The morning routine that writes cloud-*.json starts its prompt with this; it isn't news.
ROUTINE_TAG = "[olivia-times-overnight]"


def window_start(cfg, now):
    hh, mm = map(int, cfg.get("overnight", {}).get("since", "21:00").split(":"))
    start = datetime.combine(now.date(), time(hh, mm)).astimezone()
    return start - timedelta(days=1) if start > now else start


def _text(content):
    """The words in a message, or "" for tool results and Claude Code's own notes."""
    if isinstance(content, list):
        if any(b.get("type") == "tool_result" for b in content if isinstance(b, dict)):
            return ""
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return re.sub(r"\s+", " ", META.sub("", content or "")).strip()


def _commits(cwd, since):
    if not (Path(cwd) / ".git").exists():
        return []
    run = subprocess.run(["git", "-C", cwd, "log", f"--since={since.isoformat()}", "--pretty=%s", "-n", "8"],
                         capture_output=True, text=True, timeout=20)
    return run.stdout.splitlines() if run.returncode == 0 else []


def _local(cfg, folder, account, since):
    paper_data = str(cfg["data_dir"])
    out = []
    for path in (folder / "projects").glob("*/*.jsonl"):
        if datetime.fromtimestamp(path.stat().st_mtime).astimezone() < since:
            continue
        asks, replies, stamps, cwd = [], [], [], None
        for line in path.open(encoding="utf-8", errors="replace"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") not in ("user", "assistant") or e.get("isSidechain") or not e.get("timestamp"):
                continue
            when = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).astimezone()
            if when < since:
                continue
            text = _text((e.get("message") or {}).get("content"))
            stamps.append(when)
            cwd = e.get("cwd") or cwd
            if text:
                (asks if e["type"] == "user" else replies).append(text)
        if not stamps or not cwd or cwd.startswith(paper_data) or (asks and asks[0].startswith(ROUTINE_TAG)):
            continue
        out.append({
            "account": account, "where": "this PC", "project": Path(cwd).name,
            "start": min(stamps), "end": max(stamps), "requests": len(asks),
            "first_ask": asks[0][:300] if asks else "", "last_reply": replies[-1][:400] if replies else "",
            "commits": _commits(cwd, since),
        })
    return out


def _cloud(cfg, since):
    out = []
    for path in sorted((cfg["data_dir"] / "overnight").glob("cloud-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        written = datetime.fromisoformat(data.get("written", "1970-01-01T00:00:00+00:00"))
        if written < since:  # yesterday's file; the routine didn't run this morning
            continue
        for s in data.get("sessions", []):
            out.append({
                "account": data.get("account", "Claude"), "where": "claude.ai/code",
                "project": s.get("project") or s.get("title", "Session"),
                "start": datetime.fromisoformat(s["start"]) if s.get("start") else None,
                "end": datetime.fromisoformat(s["end"]) if s.get("end") else None,
                "requests": s.get("requests"), "first_ask": s.get("asked", "")[:300],
                "last_reply": s.get("outcome", "")[:400], "commits": s.get("commits", []),
            })
    return out


def sessions(cfg, now=None):
    now = now or datetime.now().astimezone()
    since = window_start(cfg, now)
    found = []
    accounts = cfg.get("claude", {}).get("accounts") or [{"name": "Claude", "config_dir": ""}]
    for account in accounts:
        folder = Path(os.path.expanduser(account.get("config_dir") or "~/.claude"))
        if folder.exists():
            found += _local(cfg, folder, account["name"], since)
    found += _cloud(cfg, since)
    try:
        from . import codex
        found += codex.sessions(cfg, since)
    except Exception as e:  # Codex's log format is its own business; don't lose Claude's
        print(f"overnight: codex: {e}")
    return sorted(found, key=lambda s: s["start"] or now)
