"""The Documents panel's backend (proposal docs/superpowers/proposals/2026-09-03-documents-panel.md):
a heading parser, the markdown corpus of the workspace's registered repos, the flat row view the panel
renders, heading search, and DocumentsStore — the QObject QML sees as `app.documents`."""
from __future__ import annotations

import re

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SETEXT_1 = re.compile(r"^ {0,3}=+[ \t]*$")
_SETEXT_2 = re.compile(r"^ {0,3}-+[ \t]*$")
_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?[ \t]+(\S.*)$")


def split_number(text: str) -> tuple[str, str]:
    """'4.6 Checks' -> ('4.6', 'Checks'); '2. Workspace' -> ('2', 'Workspace'); anything else -> ('', text)."""
    m = _NUMBER.match(text.strip())
    return (m.group(1), m.group(2).strip()) if m else ("", text.strip())


def parse_headings(text: str) -> list[dict]:
    """Every ATX or setext heading outside fenced code, in source order, as
    {index, level, number, title, line}. `index` is the ordinal among all headings — the same ordinal Qt's
    markdown engine gives the heading block, which is how the document tab finds it (spec §3, §4)."""
    out: list[dict] = []
    fence: tuple[str, int] | None = None   # (char, length) of the open fence
    lines = text.split("\n")
    prev_blank = True
    prev_is_para = False                   # previous line could be the text of a setext heading

    def add(level: int, raw: str, line: int):
        number, title = split_number(raw)
        out.append({"index": len(out), "level": level, "number": number, "title": title, "line": line})

    for i, line in enumerate(lines):
        stripped = line.strip()
        if fence:
            m = _FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and line.strip() == m.group(1):
                fence = None
            prev_is_para = False
            prev_blank = True
            continue
        m = _FENCE.match(line)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            prev_is_para = False
            prev_blank = True
            continue
        m = _ATX.match(line)
        if m and stripped:
            add(len(m.group(1)), m.group(2) or "", i)
            prev_is_para = False
            prev_blank = False
            continue
        if prev_is_para and not prev_blank:
            if _SETEXT_1.match(line):
                add(1, lines[i - 1], i - 1)
                prev_is_para = False
                prev_blank = False
                continue
            if _SETEXT_2.match(line):
                add(2, lines[i - 1], i - 1)
                prev_is_para = False
                prev_blank = False
                continue
        prev_blank = not stripped
        prev_is_para = bool(stripped) and not line.startswith("    ") and not stripped.startswith(("|", ">", "-", "*", "+"))
    return out


def title_and_sections(headings: list[dict]) -> tuple[str, list[dict]]:
    """Spec §1: the first heading, when it is the document's only H1, is the title and not a section."""
    if headings and headings[0]["level"] == 1 and sum(1 for h in headings if h["level"] == 1) == 1:
        return headings[0]["title"], headings[1:]
    return "", list(headings)
