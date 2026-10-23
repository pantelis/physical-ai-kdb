"""Find where a quote sits on a PDF page, from the page's characters in content-stream order.

Page text from an extractor reorders lines (two columns at the same height come out
interleaved), so a sentence can be on the page and still be missing from its text. Matching
the character stream avoids that. Spacing, ligatures, curly quotes, dashes and a hyphen that
breaks a word across lines are ignored; a hyphen that ends a line is tried both dropped and kept.
"""

from __future__ import annotations

import unicodedata

QUOTES = {"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"'}
DASHES = {"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(QUOTES.get(c, DASHES.get(c, c)) for c in text if not c.isspace())


def _reading_order(chars: list[dict]) -> list[dict]:
    """Characters line by line, top to bottom, and left to right within a line."""
    lines: list[list[dict]] = []
    for ch in sorted(chars, key=lambda c: c["bottom"]):
        if lines and abs(ch["bottom"] - lines[-1][0]["bottom"]) <= 2.5:
            lines[-1].append(ch)
        else:
            lines.append([ch])
    return [ch for line in lines for ch in sorted(line, key=lambda c: c["x0"])]


def _find(chars: list[dict], target: str, drop_breaks: bool) -> list[list[dict]]:
    flat, owner = [], []
    for i, ch in enumerate(chars):
        n = norm(ch["text"])
        nxt = chars[i + 1] if i + 1 < len(chars) else None
        if drop_breaks and n == "-" and nxt is not None and nxt["top"] > ch["bottom"]:
            continue  # a hyphen that breaks a word across lines
        flat.append(n)
        owner += [i] * len(n)
    stream = "".join(flat)
    out, at = [], stream.find(target)
    while at >= 0:
        out.append([chars[j] for j in sorted(set(owner[at : at + len(target)]))])
        at = stream.find(target, at + 1)
    return out


def _matches(page, text: str) -> list[list[dict]]:
    """The characters of every occurrence of text on the page.

    The PDF's drawing order comes first, because it keeps the columns of a two-column page apart.
    When that finds nothing, reading order is tried, for text drawn out of order, such as small
    capitals that a PDF draws after the rest of their line.
    """
    target = norm(text)
    if not target:
        return []
    for order in (page.chars, _reading_order(page.chars)):
        # A hyphen at the end of a line may split a word (manip-ulation) or belong to it
        # (LIBERO-SPATIAL), so both readings are tried.
        hits, seen = [], set()
        for hit in _find(order, target, True) + _find(order, target, False):
            key = tuple(id(c) for c in hit)
            if key not in seen:
                seen.add(key)
                hits.append(hit)
        if hits:
            return hits
    return []


def _box(page, chars: list[dict]) -> list[float]:
    top, bottom = min(c["top"] for c in chars), max(c["bottom"] for c in chars)
    return [round(min(c["x0"] for c in chars), 2), round(page.height - bottom, 2),
            round(max(c["x1"] for c in chars), 2), round(page.height - top, 2)]


def find_quote(page, text: str) -> list[list[float]]:
    """Return the bbox of every occurrence of text on a pdfplumber page.

    Each bbox is [x0, y0, x1, y1] in PDF points with the origin at the bottom left, the union
    of the matched characters. The list is empty when the text is not on the page.
    """
    return [_box(page, hit) for hit in _matches(page, text)]


def find_quote_lines(page, text: str) -> list[list[list[float]]]:
    """Like find_quote, but give each occurrence as one box per line of text, top line first.

    A highlight drawn from these boxes covers only the quoted words, where one bbox for a
    quote that starts or ends partway through a line also covers its neighbours.
    """
    out = []
    for hit in _matches(page, text):
        lines, current = [], [hit[0]]
        for prev, ch in zip(hit, hit[1:]):
            if ch["top"] > prev["bottom"] or ch["bottom"] < prev["top"] or ch["x0"] < prev["x0"] - 1:
                lines.append(current)
                current = []
            current.append(ch)
        lines.append(current)
        out.append([_box(page, line) for line in lines])
    return out


def inside(span: list[float], bbox: list[float], slack: float = 2.0) -> bool:
    """True when span lies within bbox, allowing a little slack on each side."""
    return (span[0] >= bbox[0] - slack and span[1] >= bbox[1] - slack
            and span[2] <= bbox[2] + slack and span[3] <= bbox[3] + slack)
