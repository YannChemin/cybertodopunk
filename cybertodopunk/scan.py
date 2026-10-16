"""Find the ACTIONS.tex files of the meeting reports and pick my actions.

A report folder is named ``YYYYMMDD_<COMPANY>[_<subject>]`` (for example
``20261014_ACME_NORTHWIND``); that name is the report's CR_ID in the lists.  Its
ACTIONS.tex may sit in the folder itself or deeper (one per meeting, as in
``20261014_GLOBEX_Summit_Bilaterals/meetings/D2-04_Partner/ACTIONS.tex``).

SPDX-License-Identifier: Unlicense
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import actions as act

# Never worth descending into.
PRUNE = {"mp3", "transcripts", "node_modules", "__pycache__", "venv", "backups", "site-packages"}
_DATE = re.compile(r"^(\d{8})_(.+)$")
_TEAM_WORDS = {"TOUS", "TOUTES", "ALL", "TEAM", "EQUIPE", "EQ"}


def fold(text):
    """Upper case without accents, for name matching."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


_LATEX_SUBS = [
    (re.compile(r"\\(?:,|;|:| |quad|qquad)|(?<!\\)~"), " "),
    (re.compile(r"\\\(\\sim\\\)|\$\\sim\$"), "~"),
    (re.compile(r"\$\\times\$|\\times"), "×"),
    (re.compile(r"\\newline|\\\\"), " "),
    (re.compile(r"\\([&%_#$])"), r"\1"),
    (re.compile(r"---"), "—"),
    (re.compile(r"--"), "–"),
    (re.compile(r"``|''"), '"'),
    (re.compile(r"\\[A-Za-z@]+\*?(\[[^\]]*\])?"), ""),
    (re.compile(r"[{}]"), ""),
]


def latex_to_text(text):
    """Plain text of a short LaTeX snippet, for the lists."""
    for pattern, repl in _LATEX_SUBS:
        text = pattern.sub(repl, text)
    return " ".join(text.split())


def surname(full_name):
    """The token written in capitals ("Jane DOE"), else the last one."""
    tokens = [t for t in re.split(r"\s+", full_name.strip()) if t]
    if not tokens:
        return ""
    caps = [t for t in tokens if len(t) > 1 and t.upper() == t and any(c.isalpha() for c in t)]
    return caps[-1] if caps else tokens[-1]


def my_tokens(cfg):
    out = []
    for t in [surname(cfg.full_name), *cfg.aliases]:
        t = fold(t.strip())
        if t and t not in out:
            out.append(t)
    return out


def _has_word(haystack, word):
    return re.search(rf"(?<![A-Z0-9]){re.escape(word)}(?![A-Z0-9])", haystack) is not None


def is_mine(owner, tokens):
    owner = fold(latex_to_text(owner))
    return any(_has_word(owner, t) for t in tokens)


def is_team(owner, company):
    """True for actions owned by the whole company: "ACME", "ACME + UMBRELLA", "ACME — all"."""
    owner = fold(latex_to_text(owner))
    company = fold(company)
    for part in re.split(r"[+,/;&]", owner):
        part = part.strip()
        if part == company:
            return True
        m = re.match(rf"^{re.escape(company)}\s*[—–-]+\s*(.*)$", part)
        if m and set(re.findall(r"[A-Z]+", m.group(1))) <= _TEAM_WORDS and m.group(1):
            return True
    return False


def company_of(dirname, companies):
    """``(date, company)`` when ``dirname`` is ``YYYYMMDD_<COMPANY>[_...]``."""
    m = _DATE.match(dirname)
    if not m:
        return None
    rest = m.group(2).upper()
    for c in sorted(companies, key=len, reverse=True):
        cu = c.upper()
        if rest == cu or rest.startswith(cu + "_"):
            return m.group(1), c
    return None


@dataclass
class Task:
    file: str
    sub: str
    action: act.Action

    def to_dict(self):
        a = self.action
        return {
            "file": self.file,
            "id": a.id,
            "sub": self.sub,
            "owner": latex_to_text(a.owner),
            "due": latex_to_text(a.due),
            "status": a.status,
            "completed": a.completed,
            "text": latex_to_text(a.description),
            "line": a.line,
        }


@dataclass
class Group:
    company: str
    cr_id: str
    date: str
    path: str
    tasks: list = field(default_factory=list)
    files: list = field(default_factory=list)

    def to_dict(self):
        return {
            "company": self.company,
            "cr_id": self.cr_id,
            "date": self.date,
            "path": self.path,
            "files": self.files,
            "tasks": [t.to_dict() for t in self.tasks],
        }


def find_action_files(paths):
    """Every ACTIONS.tex under ``paths``, each once (symlinks resolved)."""
    seen = set()
    for root in paths:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in PRUNE]
            if act.FILENAME in filenames:
                p = os.path.realpath(os.path.join(dirpath, act.FILENAME))
                if p not in seen:
                    seen.add(p)
                    yield p


def _group_dir(path, companies):
    """Nearest ancestor folder named YYYYMMDD_<COMPANY>..., with its date and company."""
    d = Path(path).parent
    for p in [d, *d.parents]:
        hit = company_of(p.name, companies)
        if hit:
            return p, hit
    return None, None


def scan(cfg, everyone=False, include_done=False, companies=None):
    """Groups of tasks, newest report first, and the files that failed.

    ``everyone`` lists every action, not only mine; ``include_done`` keeps
    the completed ones; ``companies`` restricts to those companies.
    """
    tokens = my_tokens(cfg)
    wanted = set(companies or cfg.companies)
    groups, errors = {}, []
    for f in find_action_files(cfg.search_paths):
        gdir, hit = _group_dir(f, cfg.companies)
        if not gdir or hit[1] not in wanted:
            continue
        date, company = hit
        try:
            items = act.parse_file(f)
        except (OSError, UnicodeDecodeError, act.ActionsError) as exc:
            errors.append({"file": f, "error": str(exc)})
            continue
        key = str(gdir)
        g = groups.setdefault(key, Group(company, gdir.name, date, key))
        g.files.append(f)
        rel = os.path.relpath(os.path.dirname(f), gdir)
        sub = "" if rel == "." else Path(rel).name
        for a in items:
            if a.is_placeholder or (not include_done and not a.is_open):
                continue
            mine = is_mine(a.owner, tokens) or (cfg.include_team and is_team(a.owner, company))
            if everyone or mine:
                g.tasks.append(Task(f, sub, a))
    out = sorted(groups.values(), key=lambda g: (g.date, g.cr_id), reverse=True)
    for g in out:
        g.files.sort()
        g.tasks.sort(key=lambda t: (t.sub, t.file, t.action.line))
    return out, errors
