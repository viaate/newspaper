# The Olivia Times

A four-page newspaper, written fresh every morning and printed on letter paper next to the
bed, so the day starts without a phone. Inspired by Karen X. Cheng's newspaper bot.

| Page | What's on it |
|---|---|
| **A1 · Front page** | A headline about your day; today's agenda (calendar events, what's due, anything an email says is today); Grade Watch (classes under 92.5, with what would fix them and the change since yesterday); new teacher comments on graded work; on Sundays, the week in review (grades, TikTok, money, what Claude built); today's school lunch (Ward Parkway), or on days without it, The Feature: one recent story picked for you from games, creator, science and tech news; weather with what to wear; Snow Day Watch; packages arriving today; emails that need a look; last night's Chiefs score (only after a game); countdowns |
| **A2 · The Briefing** | Five tech stories with newsprint photos, Kansas City news, and the world in brief. Every story is from the past week (the newest are picked first), still current, and never one the paper has run before |
| **A3 · Puzzles & Funnies** | A black-and-white daily comic starring your cartoon avatar, drawn in a different adult cartoon's style each day; a crossword built from your week; a "Dear Olivia" advice column; a jumble; a PSAT/SAT question of the day; classifieds; yesterday's answers, the PSAT one with why |
| **A4 · The Ledger** | Report card for every class with an estimated GPA (unweighted and weighted); tests and big grades marked this week; everything missing or zeroed, including what Schoology's Missing tab skips; the week ahead with tests in bold; what Claude worked on overnight; how much of each Claude account's limits is used; what the Claude and Gemini keys have spent and what's left; money in (Gumroad sales from email, and an estimate of TikTok pay); TikTok and Instagram followers and views |

It prints at 6:50 on weekdays and 7:30 on weekends. Claude Haiku 5.5 writes the words. Grades,
dates and times are printed exactly as Schoology, your calendar and your email give them; the
writer is told never to invent or round them.

## What it costs

| | |
|---|---|
| Printer | Brother black-and-white laser (HL-L2400 series or similar), about $90–130. Get one that says AirPrint. |
| Paper and toner | About 4 sheets a day, roughly $2–3 a month |
| Writing (Claude Haiku 5.5) | About 2¢ a day; $20 of credit lasts years |
| Comic (Gemini image model) | About 10¢ a comic, so about $3 a month; optional |
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
7:15 and print at 7:30 on weekends. If the computer was off at build time, a catch-up timer makes that day's paper
once it's back on (for the archive; it never prints late). Change the times under `[schedule]` in `config.toml`, then
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
mail to your personal Gmail at about 5:30 a.m., and the paper reads it from there. To keep
the digests out of your inbox, add a filter in your personal Gmail: search for the subject
"Olivia Times school digest", choose Create filter, and tick "Skip the Inbox (Archive it)" and
"Mark as read". The paper finds them in All Mail either way.

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

### 5. Page 4 extras

- **What's left on each key.** Neither key can report its own balance, so copy them into
  `[spend]` in `config.toml` with the date you read them (console.anthropic.com → Billing,
  aistudio.google.com → Billing). The paper keeps a ledger of what it spends in
  `data/spend.json` and subtracts it.
- **A second Claude account.** Sign it in once in its own folder:
  `CLAUDE_CONFIG_DIR=~/.claude-2 claude`, then type `/login`. Its limits and overnight sessions
  then show up next to the first account's. Limits are read by running one tiny Claude Code
  turn per account each morning.
- **Overnight Claude sessions.** Sessions that ran on this PC are read straight from Claude
  Code's history. claude.ai/code sessions come from the routine "Olivia Times: overnight
  digest" (claude.ai/code → Routines), which wakes a session at 6:05 each morning that lists
  last night's sessions and writes `data/overnight/cloud-main.json`.

- **Socials and money.** Public numbers only, no logins: TikTok followers and likes, every
  video's views, likes, comments, shares and saves, your top video since the last paper and
  your newest one; Instagram only shows a rounded follower count and post count without a login. TikTok pay is estimated from views
  gained since the last paper × `tiktok_qualified` × `tiktok_rpm` per 1,000 (`[social]`).
  Gumroad sales come from its "New sale of … for $…" emails.
- **The price.** The front page's price is what that issue cost to make: paper
  (`[price] paper_per_100_sheets`) plus that morning's Claude and Gemini calls. A new
  volume starts every January 1, and issue numbers start over with it.

### 6. The archive

Every issue is kept in `out/`, and `python -m paper archive` turns them into a website: a
masthead, a month-by-month grid of front pages with their headlines, search, and a page
reader. Each page is encrypted with the passcode under `[archive]` in `config.toml`, so the
site can live on GitHub Pages without anyone reading it. (A 4-digit code keeps out the
curious; a longer one keeps out the determined.)

To publish it every morning:

1. Make a public repo for it, like `times-archive`, then turn on Pages for it
   (Settings → Pages → Deploy from a branch → `main`, `/ (root)`).
2. Make a fine-grained token at github.com/settings/personal-access-tokens: only that
   repo, with Contents and Pages set to Read and write. Put it in `.env` as
   `ARCHIVE_GITHUB_TOKEN`.
3. Under `[archive]`, set `repo = "you/times-archive"` and `publish = true`, then run
   `.venv/bin/python -m paper archive publish` once.

### 7. Try it

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
  sources/news.py       The Verge, TechCrunch, Hacker News, KCUR, KSHB, BBC, plus the Feature's
                        games, creator and science feeds; a week old at most, newest first
  seen.py               every story printed (data/stories.json), so none runs twice
  sources/ai_usage.py   each Claude account's 5-hour and weekly limits, via Claude Code
  sources/overnight.py  Claude sessions since last night, from this PC and the morning routine
  grades.py             under-92.5 flags, day-over-day changes and the GPA estimate
  sources/social.py     public TikTok and Instagram numbers, and the TikTok pay estimate
  spend.py              the ledger of what the Claude and Gemini keys spend
  week.py               Sunday's week in review, from what each morning saved
  archive.py            the passcode-locked archive site (templates/archive.html)
  writer.py             Claude Haiku 5.5 writes all three pages (structured output)
  comic.py              the daily strip and the avatar, via Gemini
  puzzles.py            crossword layout, jumble, yesterday's answers
  render.py             HTML → PDF with headless Chromium; trims the Feature, then shrinks a crowded page to fit
  templates/paper.html  the layout
```

Each source is fetched on its own, so if one is down the paper still prints, with a note in
the footer. If Claude can't be reached, a plainer version of the paper is laid out from the
raw data. `print` builds the paper first if this morning's isn't there, so it never reprints
yesterday's.

The paper's name, the grade threshold, print times, countdowns, the lunch campus, the NFL
team, news feeds and the list of cartoon styles are all in `config.toml`.
