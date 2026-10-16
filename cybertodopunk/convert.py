"""Move a report's hand-written action table into ACTIONS.tex.

Meeting reports written before cybertodopunk carry their action plan as a
``longtable`` whose rows read ``Description & \\owner{..} & \\deadline{..} &
\\todo \\\\``.  :func:`convert` copies those rows into an ACTIONS.tex next to
the report (one ``\\actionitem`` each) and replaces the table with
``\\input{ACTIONS}``.  The section title and any ``\\arraystretch`` line
before the table stay in the report, so the rest of it renders as before.

SPDX-License-Identifier: Unlicense
"""

import re
from pathlib import Path

from . import actions as act

# Action-plan headings of the meeting reports.
_HEADING = re.compile(
    r"\\(?:sub)*section\*?\{(?:Plan d'actions[^}]*|Action plan[^}]*|Actions)\}", re.I
)
_STATUS = {"\\done": "done", "\\todo": "todo", "\\inprogress": "inprogress"}


class ConvertError(ValueError):
    pass


def _split_top(text, sep):
    """Split ``text`` on ``sep`` outside braces, skipping ``\\``-escapes."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(text):
        if text.startswith("\\", i):
            if sep == "\\\\" and text.startswith("\\\\", i) and depth == 0:
                parts.append("".join(cur))
                cur = []
                i += 2
                continue
            cur.append(text[i : i + 2])
            i += 2
            continue
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if sep != "\\\\" and c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def _strip_comments(text):
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in text.split("\n"))


def _unwrap(cell, macro):
    """``\\macro{X}`` -> ``X``; other cell text unchanged."""
    cell = cell.strip()
    m = re.fullmatch(re.escape(macro) + r"\s*\{(.*)\}", cell, re.S)
    if m:
        inner = m.group(1)
        # Only if the braces of the macro enclose the whole cell.
        start, end = act._read_group(cell, cell.index("{"))
        if end == len(cell) - 1:
            return inner.strip()
    return cell


def _rows(body):
    """Parse the rows between ``\\endhead`` and ``\\bottomrule``."""
    rows = []
    for raw in _split_top(_strip_comments(body), "\\\\"):
        raw = raw.strip()
        raw = re.sub(r"^\\rowcolor(\[[^\]]*\])?\{[^}]*\}\s*", "", raw)
        raw = re.sub(r"^\\(hline|midrule)\s*", "", raw)
        if not raw:
            continue
        cells = _split_top(raw, "&")
        if len(cells) != 4:
            raise ConvertError(f"row with {len(cells)} cells, expected 4: {raw[:70]!r}")
        desc, owner, due, status = (" ".join(c.split()) for c in cells)
        st = status.strip()
        if st not in _STATUS:
            raise ConvertError(f"unknown status cell {st!r} in row {desc[:50]!r}")
        rows.append((desc, _unwrap(owner, "\\owner"), _unwrap(due, "\\deadline"), _STATUS[st]))
    return rows


def find_table(text):
    """Return ``(start, end)`` of the action longtable, or raise."""
    h = _HEADING.search(text)
    if not h:
        raise ConvertError("no action-plan heading")
    b = text.find("\\begin{longtable}", h.end())
    nxt = re.compile(r"\\(?:sub)*section\*?\{").search(text, h.end())
    if b < 0 or (nxt and nxt.start() < b):
        raise ConvertError("no longtable under the action-plan heading")
    e = text.find("\\end{longtable}", b)
    if e < 0:
        raise ConvertError("unterminated longtable")
    return b, e + len("\\end{longtable}")


def table_actions(table):
    """The actions of a hand-written longtable, as :class:`actions.Action`."""
    head = table.find("\\endhead")
    tail = table.rfind("\\bottomrule")
    if head < 0 or tail < 0:
        raise ConvertError("table without \\endhead or \\bottomrule")
    rows = _rows(table[head + len("\\endhead") : tail])
    return [
        act.Action(id=f"A{k:02d}", owner=o, due=d, status=s, completed="", description=desc)
        for k, (desc, o, d, s) in enumerate(rows, 1)
    ]


def convert(tex_path, input_path="ACTIONS", actions_file=None, dry_run=False, header=""):
    """Convert one report.  Returns ``(actions_file, actions)``.

    ``input_path`` is what ``\\input{}`` gets (relative to where the report is
    compiled); ``actions_file`` is where the file is written (default: next to
    ``tex_path``).
    """
    tex_path = Path(tex_path)
    text = tex_path.read_text(encoding="utf-8")
    if re.search(r"\\input\{[^}]*ACTIONS\}", text):
        raise ConvertError("already converted")
    b, e = find_table(text)
    items = table_actions(text[b:e])
    out = Path(actions_file) if actions_file else tex_path.with_name(act.FILENAME)
    if out.exists():
        raise ConvertError(f"{out} already exists")
    if dry_run:
        return out, items
    act.write_new(out, items, header=header)
    new_text = text[:b] + f"\\input{{{input_path}}}" + text[e:]
    act._atomic_write(tex_path, new_text)
    return out, items
