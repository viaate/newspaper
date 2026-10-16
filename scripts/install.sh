#!/usr/bin/env bash
# Set up the morning paper on an always-on Linux machine (made for Bazzite; works on
# any systemd distro). Rerun it after changing [schedule] in config.toml.
#
#   bash scripts/install.sh
#
# Everything lives in this folder and your user account: no sudo, no system packages,
# which suits Bazzite's read-only system image.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"

echo "== Python packages"
[ -x "$PY" ] || python3 -m venv .venv
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt

echo "== Chromium (lays out the pages)"
"$PY" -m playwright install chromium

[ -f config.toml ] || cp config.example.toml config.toml
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
mkdir -p data/photos out

echo "== Checking Chromium can start"
if ! "$PY" - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch().close()
EOF
then
  cat <<'MSG'
Chromium couldn't start, which usually means a system library is missing.
On Bazzite, run the paper inside a Distrobox container instead:
  distrobox create --name paper --image fedora:latest
  distrobox enter paper -- bash scripts/install.sh
MSG
  exit 1
fi

echo "== Scheduling"
# Print times from config.toml; each build starts 15 minutes before its print.
read -r WEEKDAY WEEKEND < <("$PY" - <<'EOF'
import tomllib
s = tomllib.load(open("config.toml", "rb")).get("schedule", {})
print(s.get("weekday", "06:50"), s.get("weekend", "07:30"))
EOF
)
earlier() { date -d "$1 15 minutes ago" +%H:%M; }

UNITS="$HOME/.config/systemd/user"
mkdir -p "$UNITS"
for job in build print; do
  cat > "$UNITS/olivia-times-$job.service" <<EOF
[Unit]
Description=The Olivia Times ($job)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=$PY -m paper $job
EOF
done

timer() {  # name, weekday time, weekend time
  cat > "$UNITS/olivia-times-$1.timer" <<EOF
[Unit]
Description=The Olivia Times ($1)

[Timer]
OnCalendar=Mon..Fri *-*-* $2:00
OnCalendar=Sat,Sun *-*-* $3:00
# If the computer was off at print time, don't print late.
Persistent=false

[Install]
WantedBy=timers.target
EOF
}
timer build "$(earlier "$WEEKDAY")" "$(earlier "$WEEKEND")"
timer print "$WEEKDAY" "$WEEKEND"

# Catch-up: if the computer was off at build time, make that day's paper once it's back
# (for the archive; it never prints). Checks after startup and then hourly in the day.
cat > "$UNITS/olivia-times-catchup.service" <<EOF
[Unit]
Description=The Olivia Times (catch up after the computer was off)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=$PY -m paper catchup
EOF
cat > "$UNITS/olivia-times-catchup.timer" <<EOF
[Unit]
Description=The Olivia Times (catch up after the computer was off)

[Timer]
OnBootSec=5min
OnCalendar=*-*-* 08..21:10:00

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now olivia-times-build.timer olivia-times-print.timer olivia-times-catchup.timer

# If Claude Code is installed, keep a remote-control session running in tmux, started
# again after every reboot, so it stays reachable from the Claude app.
CLAUDE_BIN="$(command -v claude || echo "$HOME/.local/bin/claude")"
TMUX_BIN="$(command -v tmux || true)"
if [ -x "$CLAUDE_BIN" ] && [ -n "$TMUX_BIN" ]; then
  cat > "$UNITS/olivia-times-claude.service" <<EOF
[Unit]
Description=Claude remote-control for The Olivia Times
Wants=network-online.target
After=network-online.target

[Service]
Type=forking
WorkingDirectory=$ROOT
Environment=PATH=$(dirname "$CLAUDE_BIN"):/usr/local/bin:/usr/bin:/bin
ExecStart=$TMUX_BIN new-session -d -s paper -c $ROOT $CLAUDE_BIN remote-control
ExecStop=$TMUX_BIN kill-session -t paper
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  # Replace a hand-started tmux session so the service owns it.
  "$TMUX_BIN" kill-session -t paper 2>/dev/null || true
  systemctl --user enable olivia-times-claude.service
  systemctl --user restart olivia-times-claude.service
fi
# Keep the timers running when nobody is logged in.
loginctl enable-linger "$USER" 2>/dev/null || echo "(Run 'sudo loginctl enable-linger $USER' so it prints even when you're logged out.)"

echo
systemctl --user list-timers 'olivia-times-*' --no-pager || true
cat <<EOF

Installed. Prints at $WEEKDAY on weekdays and $WEEKEND on weekends.
Next:
  1. Put your keys in $ROOT/.env        (nano .env)
  2. Try it:   $PY -m paper build --sample     -> out/<date>-sample.pdf
  3. Avatar:   copy photos into data/photos/, then  $PY -m paper avatar make data/photos/*
  4. Printer:  see the README, then  $PY -m paper run
Logs: journalctl --user -u olivia-times-build -u olivia-times-print
EOF
