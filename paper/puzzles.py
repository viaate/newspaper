"""Page 3 puzzles: a criss-cross crossword and a word jumble, plus yesterday's answers."""

import json
import random
import re

# Used when the writer can't supply today's words.
BANK = [
    ("PIXEL", "Tiny dot on a screen"),
    ("ROUTER", "Box that makes the Wi-Fi"),
    ("CACHE", "Stash of saved data"),
    ("TABLET", "iPad, for one"),
    ("BUG", "What a programmer squashes"),
    ("LAPTOP", "Computer that goes to class"),
    ("EMOJI", "Tiny face in a text"),
    ("ALGEBRA", "Where x marks the spot"),
    ("ESSAY", "Five paragraphs, give or take"),
    ("QUIZ", "Pop ___"),
]
JUMBLE_BANK = ["PLANET", "SCHOOL", "GRADES", "COFFEE", "LOCKER"]


def _word(text):
    return re.sub(r"[^A-Z]", "", text.upper())


# ------------------------------------------------------------------ crossword

def _fits(grid, word, r, c, down):
    """Number of crossings if `word` fits at (r, c), else -1."""
    dr, dc = (1, 0) if down else (0, 1)
    if grid.get((r - dr, c - dc)) or grid.get((r + dr * len(word), c + dc * len(word))):
        return -1
    crossings = 0
    for k, ch in enumerate(word):
        cell = (r + dr * k, c + dc * k)
        existing = grid.get(cell)
        if existing:
            if existing[0] != ch or existing[1 if down else 2]:
                return -1  # wrong letter, or this cell already runs the same way
            crossings += 1
        else:
            # A new letter can't sit beside another one sideways.
            side = [(cell[0] + dc, cell[1] + dr), (cell[0] - dc, cell[1] - dr)]
            if any(grid.get(s) for s in side):
                return -1
    return crossings


def _place(grid, word, r, c, down):
    dr, dc = (1, 0) if down else (0, 1)
    for k, ch in enumerate(word):
        cell = (r + dr * k, c + dc * k)
        _, d, a = grid.get(cell, (ch, False, False))
        grid[cell] = (ch, d or down, a or not down)


def _layout(words, max_size, rng):
    grid, placed = {}, []
    first = words[0]
    _place(grid, first, 0, 0, False)
    placed.append((first, 0, 0, False))
    for word in words[1:]:
        best = None
        for (r0, c0), (ch, _, _) in list(grid.items()):
            for i, letter in enumerate(word):
                if letter != ch:
                    continue
                for down in (True, False):
                    r, c = (r0 - i, c0) if down else (r0, c0 - i)
                    crossings = _fits(grid, word, r, c, down)
                    if crossings < 1:
                        continue
                    cells = list(grid) + [(r + k * down, c + k * (not down)) for k in range(len(word))]
                    rows = max(x for x, _ in cells) - min(x for x, _ in cells) + 1
                    cols = max(y for _, y in cells) - min(y for _, y in cells) + 1
                    if rows > max_size or cols > max_size:
                        continue
                    score = (crossings, -rows * cols, rng.random())
                    if best is None or score > best[0]:
                        best = (score, r, c, down)
        if best:
            _, r, c, down = best
            _place(grid, word, r, c, down)
            placed.append((word, r, c, down))
    return grid, placed


def crossword(entries, seed=0, max_size=12, tries=40):
    """Lay out (answer, clue) pairs. Returns rows of cells plus numbered clues."""
    clues = {}
    for answer, clue in entries:
        w = _word(answer)
        if 3 <= len(w) <= max_size and w not in clues:
            clues[w] = clue
    words = sorted(clues, key=len, reverse=True)
    if len(words) < 3:
        return None

    rng = random.Random(seed)
    best = None
    for attempt in range(tries):
        order = words[:1] + rng.sample(words[1:], len(words) - 1) if attempt else words
        grid, placed = _layout(order, max_size, rng)
        rows = max(r for r, _ in grid) - min(r for r, _ in grid) + 1
        cols = max(c for _, c in grid) - min(c for _, c in grid) + 1
        score = (len(placed), -rows * cols)
        if best is None or score > best[0]:
            best = (score, grid, placed)
    _, grid, placed = best

    top = min(r for r, _ in grid)
    left = min(c for _, c in grid)
    starts = {}
    for word, r, c, down in placed:
        starts.setdefault((r - top, c - left), []).append((word, down))

    numbers, across, down_clues, number = {}, [], [], 0
    height = max(r for r, _ in grid) - top + 1
    width = max(c for _, c in grid) - left + 1
    for r in range(height):
        for c in range(width):
            if (r, c) in starts:
                number += 1
                numbers[(r, c)] = number
                for word, is_down in starts[(r, c)]:
                    (down_clues if is_down else across).append(
                        {"number": number, "clue": clues[word], "length": len(word), "answer": word}
                    )
    rows = [
        [
            {"number": numbers.get((r, c))} if (r + top, c + left) in grid else None
            for c in range(width)
        ]
        for r in range(height)
    ]
    return {"rows": rows, "across": across, "down": down_clues, "width": width}


# ------------------------------------------------------------------ jumble

def jumble(words, seed=0):
    rng = random.Random(seed)
    out = []
    for w in words:
        w = _word(w)
        if not 4 <= len(w) <= 8 or len(set(w)) < 3:
            continue
        letters = list(w)
        while "".join(letters) == w:
            rng.shuffle(letters)
        out.append({"scrambled": "".join(letters), "answer": w})
    return out[:4]


# ------------------------------------------------------------------ answers

def save_answers(data_dir, day, puzzle, scrambles):
    folder = data_dir / "puzzles"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{day}.json").write_text(json.dumps({
        "across": [f"{a['number']} {a['answer']}" for a in (puzzle or {}).get("across", [])],
        "down": [f"{d['number']} {d['answer']}" for d in (puzzle or {}).get("down", [])],
        "jumble": [j["answer"] for j in scrambles],
    }), encoding="utf-8")


def yesterdays_answers(data_dir, day):
    folder = data_dir / "puzzles"
    earlier = sorted(p for p in folder.glob("*.json") if p.stem < str(day)) if folder.exists() else []
    return json.loads(earlier[-1].read_text(encoding="utf-8")) if earlier else None
