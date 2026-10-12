# The Olivia Times

A three-page newspaper, written fresh every morning and printed on letter paper next to the
bed, so the day starts without a phone. Inspired by Karen X. Cheng's newspaper bot.

| Page | What's on it |
|---|---|
| **A1 · Front page** | A headline about your day, today's agenda, Grade Watch (anything under 92.5 flagged, with what would fix it and the change since yesterday), what's due this week, weather, Snow Day Watch, and the emails that need a look |
| **A2 · The Briefing** | Five tech stories with newsprint photos, Kansas City news, and the world in brief |
| **A3 · Puzzles & Funnies** | A black-and-white daily comic starring your cartoon avatar, drawn in a different adult cartoon's style each day; a crossword built from your week; a "Dear Olivia" advice column; a jumble; classifieds; yesterday's answers |

Claude Haiku 5.5 writes the words. Grades, dates and times are printed exactly as Schoology
and your email give them; the writer is told never to invent or round them.

## What it costs

| | |
|---|---|
| Printer | Brother black-and-white laser (HL-L2400 series or similar), about $90–130. Get one that says AirPrint. |
| Paper and toner | About 3 sheets a day, roughly $2–3 a month |
| Writing (Claude Haiku 5.5) | About a penny a day; $20 of credit lasts years |
| Comic (Gemini image model) | A few cents a day; optional |
| Weather, news, Schoology | Free |

## Setup

Everything runs on a computer that's always on. The keys stay on that computer, in `.env`.
This repository is public: never commit `.env`, `config.toml` or anything in `data/` (they're
in `.gitignore`).

### 1. Install

**Linux**

```
git clone https://github.com/viaate/newspaper && cd newspaper
bash scripts/install.sh
```

That makes a virtual environment, installs everything, and schedules the paper to build at
6:35 and print at 6:50 every day.

**Windows** (PowerShell)

```
git clone https://github.com/viaate/newspaper; cd newspaper
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy config.example.toml config.toml
copy .env.example .env
```

Also install [SumatraPDF](https://www.sumatrapdfreader.org), which prints silently. Then schedule it:

```
schtasks /create /tn "Olivia Times build" /sc daily /st 06:35 /tr "cmd /c cd /d $PWD && .venv\Scripts\python -m paper build"
schtasks /create /tn "Olivia Times print" /sc daily /st 06:50 /tr "cmd /c cd /d $PWD && .venv\Scripts\python -m paper print"
```

### 2. Keys

Open `.env` and fill in what you have. Anything missing just leaves that section out.

| Key | Where it comes from |
|---|---|
| `SCHOOLOGY_KEY`, `SCHOOLOGY_SECRET` | Sign in at `https://pembroke.schoology.com/api`. It shows a Consumer Key and Secret. |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API keys. Add credit under Billing. |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key. Image generation needs billing turned on. |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Your personal Gmail. Turn on 2-Step Verification, then make an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). |

**School email.** The school account doesn't allow outside apps, so the school account
forwards a digest itself: follow the steps at the top of
[`apps_script/school_digest.gs`](apps_script/school_digest.gs). It emails the day's school
mail to your personal Gmail at about 5:30 a.m., and the paper reads it from there.

### 3. Your avatar (for the comic)

Copy 3–5 clear photos of yourself into `data/photos/`, then:

```
python -m paper avatar make data/photos/*
```

That draws four cartoon versions of you, `data/avatar/option-A.png` to `option-D.png`. Pick one:

```
python -m paper avatar pick B
```

The photos are sent to Google once, for this step. After that, only the cartoon avatar is sent
each morning.

### 4. Printer

Connect the Brother to Wi-Fi, then find its IP address on its screen or in your router.

- **Linux:** `sudo lpadmin -p brother -E -v ipp://PRINTER-IP/ipp/print -m everywhere`, then set
  `name = "brother"` under `[printer]` in `config.toml`.
- **Windows:** add it in Settings → Printers & scanners. Put its name in `config.toml`, or leave
  it blank to use the default printer.

### 5. Try it

```
python -m paper build --sample   # sample grades and email; makes out/<date>-sample.pdf
python -m paper build            # the real thing, without printing
python -m paper run              # build and print
```

## How it works

```
paper/
  sources/schoology.py  grades, missing work and due dates (Schoology REST API, OAuth 1.0a)
  sources/gmail.py      recent mail over IMAP, plus the school digest
  sources/weather.py    Open-Meteo, falling back to weather.gov
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
raw data.

Settings like the paper's name, the grade threshold, the news feeds and the list of cartoon
styles are in `config.toml`.
