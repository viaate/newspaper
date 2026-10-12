# The Olivia Times

A three-page newspaper, written fresh every morning and printed on letter paper next to the
bed, so the day starts without a phone. Inspired by Karen X. Cheng's newspaper bot.

| Page | What's on it |
|---|---|
| **A1 · Front page** | A headline about your day; today's agenda (calendar events, what's due, anything an email says is today); Grade Watch (classes under 92.5 flagged, with what would fix them and the change since yesterday); the week ahead; today's school lunch (Ward Parkway); weather with what to wear; Snow Day Watch; packages arriving today; emails that need a look; last night's Chiefs score (only after a game); countdowns |
| **A2 · The Briefing** | Five tech stories with newsprint photos, Kansas City news, and the world in brief |
| **A3 · Puzzles & Funnies** | A black-and-white daily comic starring your cartoon avatar, drawn in a different adult cartoon's style each day; a crossword built from your week; a "Dear Olivia" advice column; a jumble; classifieds; yesterday's answers |

It prints at 6:50 on weekdays and 7:30 on weekends. Claude Haiku 5.5 writes the words. Grades,
dates and times are printed exactly as Schoology, your calendar and your email give them; the
writer is told never to invent or round them.

## What it costs

| | |
|---|---|
| Printer | Brother black-and-white laser (HL-L2400 series or similar), about $90–130. Get one that says AirPrint. |
| Paper and toner | About 3 sheets a day, roughly $2–3 a month |
| Writing (Claude Haiku 5.5) | About a penny a day; $20 of credit lasts years |
| Comic (Gemini image model) | About 5–10¢ a comic, so $2–3 a month; optional |
| Weather, news, calendar, lunch menu, Chiefs scores, Schoology | Free |

## Setup

Everything runs on the always-on Bazzite PC. The keys stay on that computer, in `.env`. This
repository is public: never commit `.env`, `config.toml` or anything in `data/` (they're in
`.gitignore`).

### 1. Install

Open a terminal on the Bazzite PC (or `ssh` into it):

```
git clone https://github.com/viaate/newspaper && cd newspaper
bash scripts/install.sh
```

That installs everything inside the `newspaper` folder (no `sudo`, nothing added to the system)
and schedules it with systemd timers: build at 6:35 and print at 6:50 on weekdays, build at
7:15 and print at 7:30 on weekends. Change the times under `[schedule]` in `config.toml`, then
run the script again.

### 2. Keys

`nano .env` and fill in what you have. Anything missing just leaves that part out.

| Key | Where it comes from |
|---|---|
| `SCHOOLOGY_KEY`, `SCHOOLOGY_SECRET` | Sign in at `https://pembroke.schoology.com/api`. It shows a Consumer Key and Secret. |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API keys. Add credit under Billing. |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key. Image generation needs billing turned on. |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Your personal Gmail. Turn on 2-Step Verification, then make an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). |
| `CALENDAR_URLS` | Google Calendar on a computer → Settings → click your calendar → "Secret address in iCal format". Paste it here. Several calendars: separate the links with spaces. |

**School email.** The school account doesn't allow outside apps, so the school account
forwards a digest itself: follow the steps at the top of
[`apps_script/school_digest.gs`](apps_script/school_digest.gs). It emails the day's school
mail to your personal Gmail at about 5:30 a.m., and the paper reads it from there.

**Packages.** Shipping emails from the past week (Amazon, UPS, FedEx, USPS and shops) are read
from your personal Gmail, and the paper lists what's arriving today. Signing up for USPS
Informed Delivery makes it catch mail too.

### 3. Your avatar (for the comic)

Copy 3–5 clear photos of yourself into `data/photos/`, then:

```
.venv/bin/python -m paper avatar make data/photos/*
```

That draws four cartoon versions of you, `data/avatar/option-A.png` to `option-D.png`. Pick one:

```
.venv/bin/python -m paper avatar pick B
```

The photos are sent to Google once, for this step. After that, only the cartoon avatar is sent
each morning.

### 4. Printer

Connect the Brother to Wi-Fi and find its IP address (on its screen or in your router's device
list). Then add it, either in Bazzite's Settings → Printers, or with:

```
lpadmin -p brother -E -v ipp://PRINTER-IP/ipp/print -m everywhere
```

and set `name = "brother"` under `[printer]` in `config.toml`. Leave it blank to use the default
printer.

### 5. Try it

```
.venv/bin/python -m paper build --sample   # sample grades and email; makes out/<date>-sample.pdf
.venv/bin/python -m paper build            # the real thing, without printing
.venv/bin/python -m paper run              # build and print
```

If something's off on a scheduled morning: `journalctl --user -u olivia-times-build -u olivia-times-print`.

## How it works

```
paper/
  sources/schoology.py  grades, missing work and due dates (Schoology REST API, OAuth 1.0a)
  sources/gmail.py      recent mail and shipping notices over IMAP, plus the school digest
  sources/calendars.py  events from private iCal links
  sources/weather.py    Open-Meteo, falling back to weather.gov
  sources/lunch.py      today's menu from the Pembroke Hill dining page
  sources/sports.py     yesterday's Chiefs game from ESPN's public feed
  sources/news.py       The Verge, TechCrunch, Hacker News, KCUR, KSHB, BBC
  grades.py             under-92.5 flags and day-over-day changes
  writer.py             Claude Haiku 5.5 writes all three pages (structured output)
  comic.py              the daily strip and the avatar, via Gemini
  puzzles.py            crossword layout, jumble, yesterday's answers
  render.py             HTML → PDF with headless Chromium; shrinks a crowded page to fit
  templates/paper.html  the layout
```

Each source is fetched on its own, so if one is down the paper still prints, with a note in
the footer. If Claude can't be reached, a plainer version of the paper is laid out from the
raw data. `print` builds the paper first if this morning's isn't there, so it never reprints
yesterday's.

The paper's name, the grade threshold, print times, countdowns, the lunch campus, the NFL
team, news feeds and the list of cartoon styles are all in `config.toml`.
