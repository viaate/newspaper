#!/usr/bin/env bash
# Set up the morning paper on a Linux machine that stays on.
#   bash scripts/install.sh            # install, then build at 6:35 and print at 6:50 daily
#   BUILD_AT="30 6" PRINT_AT="50 6" bash scripts/install.sh   # other times (minute hour)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium

[ -f config.toml ] || cp config.example.toml config.toml
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
mkdir -p data/photos out

BUILD_AT="${BUILD_AT:-35 6}"
PRINT_AT="${PRINT_AT:-50 6}"
LOG="$ROOT/out/cron.log"
{
  crontab -l 2>/dev/null | grep -v '# olivia-times' || true
  echo "$BUILD_AT * * * cd $ROOT && .venv/bin/python -m paper build >> $LOG 2>&1 # olivia-times"
  echo "$PRINT_AT * * * cd $ROOT && .venv/bin/python -m paper print >> $LOG 2>&1 # olivia-times"
} | crontab -

echo
echo "Installed. Next:"
echo "  1. Put your keys in $ROOT/.env (nano .env)"
echo "  2. Try it:   .venv/bin/python -m paper build --sample   (makes out/<date>-sample.pdf)"
echo "  3. Avatar:   copy photos to data/photos/, then .venv/bin/python -m paper avatar make data/photos/*"
echo "  4. Printer:  see README, then .venv/bin/python -m paper run"
