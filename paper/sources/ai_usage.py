"""How much of each Claude subscription's 5-hour and weekly limits is used.

Claude Code reports both windows in a `rate_limit_event` when run headless with
stream-json output, signed in with its own login; each account is a separate
CLAUDE_CONFIG_DIR. The check is one tiny Haiku turn, so it barely touches the limit.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def _claude(cfg):
    return (cfg.get("claude", {}).get("command")
            or shutil.which("claude") or str(Path.home() / ".local/bin/claude"))


def _window(w):
    if not w:
        return None
    resets = w.get("resetsAt")
    return {"used": round(w.get("utilization", 0) * 100),
            "resets": datetime.fromtimestamp(resets) if resets else None}


def check_account(cfg, account):
    env = dict(os.environ)
    env.pop("CLAUDE_CONFIG_DIR", None)
    if account.get("config_dir"):  # blank = the default login (~/.claude and ~/.claude.json)
        folder = Path(os.path.expanduser(account["config_dir"]))
        if not folder.exists():
            return {"name": account["name"], "error": f"not signed in yet (no {folder})"}
        env["CLAUDE_CONFIG_DIR"] = str(folder)
    run = subprocess.run(
        [_claude(cfg), "-p", "Reply with just: OK", "--model", "haiku", "--output-format", "stream-json",
         "--verbose", "--no-session-persistence"],
        env=env, cwd=cfg["data_dir"],
        capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL,
    )
    for line in run.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result" and event.get("is_error"):
            message = str(event.get("result") or "Claude Code reported an error")
            return {"name": account["name"], "error": "not signed in yet" if "/login" in message else message[:90]}
        if event.get("type") == "rate_limit_event":
            windows = event.get("rate_limit_info", {}).get("unifiedWindows", {})
            return {"name": account["name"], "five_hour": _window(windows.get("five_hour")),
                    "week": _window(windows.get("seven_day"))}
    reason = (run.stderr or run.stdout).strip().splitlines()[-1:] or ["no usage reported"]
    return {"name": account["name"], "error": reason[0][:90]}


def claude_limits(cfg):
    accounts = cfg.get("claude", {}).get("accounts") or [{"name": "Claude", "config_dir": ""}]
    out = []
    for account in accounts:
        try:
            out.append(check_account(cfg, account))
        except (OSError, subprocess.SubprocessError) as e:
            out.append({"name": account["name"], "error": f"{type(e).__name__}: {e}"[:90]})
    return out
