"""Read and update ACTIONS.tex, the action list of a meeting report.

An ACTIONS.tex file sits next to the report's main .tex (``CR-*.tex``),
which includes it with ``\\input{ACTIONS}`` in its action-plan section.
It renders as the usual four-column table (action, owner, due, status) and
holds one ``\\actionitem`` per action:

    \\actionitem{A01}{ACME --- DOE}{14/10}{todo}{}
      {Share the demo code with the partners}

The six arguments are the ID, owner, due date, status (``todo``,
``inprogress`` or ``done``), completion time (``YYYY-MM-DD HH:MM``, empty
while open) and description.  Checking an action off rewrites only the
status and completion arguments of that one command, so the rest of the
file (comments, layout, the other actions) is left byte for byte as it was,
and the next compilation of the report shows when the action was done.

SPDX-License-Identifier: Unlicense
"""

import datetime as _dt
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

FILENAME = "ACTIONS.tex"
MACRO = "\\actionitem"
STATUSES = ("todo", "inprogress", "done")
FORMAT_VERSION = 1
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

# Placeholders of the report templates; such actions are not real yet.
_PLACEHOLDER = re.compile(r"<<|@[A-Z]+@|\\tbc\b")


class ActionsError(ValueError):
    """An ACTIONS.tex file, or one of its actions, cannot be used."""


@dataclass
class Action:
    """One ``\\actionitem`` of an ACTIONS.tex file."""

    id: str
    owner: str
    due: str
    status: str
    completed: str
    description: str
    line: int = 0
    # Character spans of the six arguments' contents in the file text.
    spans: list = field(default_factory=list, repr=False)

    @property
    def is_open(self):
        return self.status != "done"

    @property
    def is_placeholder(self):
        return bool(_PLACEHOLDER.search(self.description) or _PLACEHOLDER.search(self.owner))


def _skip_space_and_comments(text, i):
    """Return the index of the next character that is not blank or in a comment."""
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "%":
            while i < n and text[i] != "\n":
                i += 1
        else:
            break
    return i


def _read_group(text, i):
    """Read a ``{...}`` group starting at ``text[i]``.

    Returns ``(start, end)`` of the contents (without the braces).  Escaped
    braces (``\\{``) and braces inside ``%`` comments do not count.
    """
    if i >= len(text) or text[i] != "{":
        raise ActionsError("expected '{'")
    depth = 0
    j = i
    n = len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "%":
            while j < n and text[j] != "\n":
                j += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1, j
        j += 1
    raise ActionsError("unbalanced braces")


def _body_start(text):
    """Index just after ``\\begin{actionplan}``; the definitions come before it."""
    for m in re.finditer(r"\\begin\{actionplan\}", text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if not re.search(r"(?<!\\)%", text[line_start : m.start()]):
            return m.end()
    raise ActionsError("no \\begin{actionplan}")


def _macro_positions(text):
    """Yield the index of every ``\\actionitem`` that is not commented out."""
    pattern = re.compile(re.escape(MACRO) + r"(?![A-Za-z@])")
    for m in pattern.finditer(text, _body_start(text)):
        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[line_start : m.start()]
        # A "%" not preceded by a backslash comments the rest of the line.
        if re.search(r"(?<!\\)%", prefix):
            continue
        yield m.start()


def parse_text(text):
    """Parse the actions of an ACTIONS.tex text, in file order."""
    actions = []
    for pos in _macro_positions(text):
        line = text.count("\n", 0, pos) + 1
        i = pos + len(MACRO)
        spans = []
        try:
            for _ in range(6):
                i = _skip_space_and_comments(text, i)
                start, end = _read_group(text, i)
                spans.append((start, end))
                i = end + 1
        except ActionsError as exc:
            raise ActionsError(f"line {line}: {MACRO} needs six {{...}} arguments ({exc})") from None
        values = [text[s:e] for s, e in spans]
        status = values[3].strip()
        if status not in STATUSES:
            raise ActionsError(f"line {line}: unknown status {status!r} (use {', '.join(STATUSES)})")
        actions.append(
            Action(
                id=values[0].strip(),
                owner=" ".join(values[1].split()),
                due=" ".join(values[2].split()),
                status=status,
                completed=values[4].strip(),
                description=" ".join(values[5].split()),
                line=line,
                spans=spans,
            )
        )
    seen = set()
    for a in actions:
        if not a.id:
            raise ActionsError(f"line {a.line}: empty action ID")
        if a.id in seen:
            raise ActionsError(f"line {a.line}: duplicate action ID {a.id!r}")
        seen.add(a.id)
    return actions


def parse_file(path):
    return parse_text(Path(path).read_text(encoding="utf-8"))


def now_stamp():
    return _dt.datetime.now().strftime(TIMESTAMP_FORMAT)


def _atomic_write(path, text):
    """Replace ``path`` with ``text`` atomically, keeping its permissions."""
    path = Path(path)
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_status(path, action_id, status, completed=None):
    """Set an action's status and completion time in place.

    ``completed`` defaults to now for ``done`` and to empty otherwise.
    Returns the updated :class:`Action`.  Only the two arguments change.
    """
    if status not in STATUSES:
        raise ActionsError(f"unknown status {status!r}")
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    actions = parse_text(text)
    match = [a for a in actions if a.id == action_id]
    if not match:
        raise ActionsError(f"{path}: no action {action_id!r}")
    a = match[0]
    if completed is None:
        completed = now_stamp() if status == "done" else ""
    (s3, e3), (s4, e4) = a.spans[3], a.spans[4]
    text = text[:s3] + status + text[e3:s4] + completed + text[e4:]
    _atomic_write(path, text)
    a.status, a.completed = status, completed
    return a


def complete(path, action_id, when=None):
    return set_status(path, action_id, "done", when or now_stamp())


def reopen(path, action_id):
    return set_status(path, action_id, "todo", "")


def start(path, action_id):
    return set_status(path, action_id, "inprogress", "")


def _arg(value):
    """Brace-safe argument text (the values come from LaTeX already)."""
    return value.replace("\n", " ").strip()


def format_action(a):
    return (
        f"{MACRO}{{{_arg(a.id)}}}{{{_arg(a.owner)}}}{{{_arg(a.due)}}}"
        f"{{{a.status}}}{{{_arg(a.completed)}}}\n  {{{_arg(a.description)}}}\n"
    )


# The LaTeX side.  The definitions are guarded, so a report that inputs
# several ACTIONS.tex files (one per meeting) defines them once, and they use
# the report's own \owner, \deadline, \todo, \inprogress and \done (and its
# rowalt/tablehead colours) when it has them.
PREAMBLE = r"""%% ACTIONS.tex: the actions planned in this meeting, read and checked off by
%% cybertodopunk (https://github.com/YannChemin/cybertodopunk); format 1.
%% Included by the report with \input{ACTIONS} in its action-plan section.
%%
%% One action per \actionitem, with six arguments:
%%   \actionitem{ID}{Owner}{Due}{Status}{Completed}
%%     {Description}
%%   ID         unique in this file (A01, A02, ...)
%%   Owner      "ORG --- SURNAME", "ORG + ORG", ...; cybertodopunk shows an
%%              action to the user whose surname (or alias) appears here
%%   Due        free text: 14/10, --, Mi-avr.\ 2027, ...
%%   Status     todo | inprogress | done
%%   Completed  YYYY-MM-DD HH:MM, written by cybertodopunk when checked off;
%%              empty while the action is open
%% Edit freely between the actions; keep each \actionitem's six arguments.
\makeatletter
\@ifundefined{actionplan}{%
  \providecommand{\owner}[1]{\textbf{#1}}%
  \providecommand{\deadline}[1]{\textbf{#1}}%
  \@ifundefined{iflanguage}{\def\ctp@fr{\@secondoftwo}}%
    {\def\ctp@fr{\iflanguage{french}}}%
  \providecommand{\todo}{\textbf{\ctp@fr{À faire}{To do}}}%
  \providecommand{\inprogress}{\textbf{\ctp@fr{En cours}{In progress}}}%
  \providecommand{\done}{\textbf{\ctp@fr{Fait}{Done}}}%
  \@ifundefined{\string\color@rowalt}{\definecolor{rowalt}{RGB}{235,241,250}}{}%
  \@ifundefined{\string\color@tablehead}{\definecolor{tablehead}{RGB}{10,35,75}}{}%
  \newcount\ctp@row
  \def\ctp@status#1#2{%
    \def\ctp@s{#1}\def\ctp@t{done}%
    \ifx\ctp@s\ctp@t \done
      \if\relax\detokenize{#2}\relax\else\newline{\scriptsize\detokenize{#2}}\fi
    \else\def\ctp@t{inprogress}%
      \ifx\ctp@s\ctp@t \inprogress\else\todo\fi
    \fi}%
  % Even rows are shaded, as in the hand-written tables.
  \newcommand{\actionitem}[6]{%
    \noalign{\global\advance\ctp@row\@ne}%
    \ifodd\ctp@row\expandafter\@gobble\else\expandafter\@firstofone\fi
      {\rowcolor{rowalt}}%
    #6 & \owner{#2} & \deadline{#3} & \ctp@status{#4}{#5} \\}%
  \newenvironment{actionplan}{%
    \global\ctp@row\z@
    \begin{longtable}{@{}>{\raggedright\arraybackslash}p{7.2cm}
                        >{\raggedright\arraybackslash}p{3.4cm}
                        >{\raggedright\arraybackslash}p{1.6cm} p{2.0cm}@{}}
    \toprule
    \rowcolor{tablehead}
    \color{white}\textbf{Action} &
    \color{white}\textbf{\ctp@fr{Responsable}{Owner}} &
    \color{white}\textbf{\ctp@fr{Échéance}{Due}} &
    \color{white}\textbf{\ctp@fr{Statut}{Status}} \\
    \midrule
    \endhead
  }{%
    \bottomrule
    \end{longtable}%
  }%
}{}
\makeatother
"""


def render_file(actions, header=""):
    """Text of a new ACTIONS.tex holding ``actions``."""
    body = "\n".join(format_action(a) for a in actions)
    head = f"{header.rstrip()}\n" if header.strip() else ""
    return f"{PREAMBLE}{head}\n\\begin{{actionplan}}\n\n{body}\n\\end{{actionplan}}\n"


def write_new(path, actions, header="", overwrite=False):
    path = Path(path)
    if path.exists() and not overwrite:
        raise ActionsError(f"{path} already exists")
    _atomic_write(path, render_file(actions, header))
    return path
