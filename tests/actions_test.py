"""ACTIONS.tex parsing, in-place updates and LaTeX compilation.

SPDX-License-Identifier: Unlicense
"""

import shutil
import subprocess

import pytest

from cybertodopunk import actions as act


def sample(tmp_path, items=None):
    items = items or [
        act.Action("A01", "ACME --- DOE", "14/10", "todo", "", "Send the minutes ({\\bf final} version)"),
        act.Action("A02", "UMBRELLA + ACME", "--", "inprogress", "", "Workshop \\& demo"),
    ]
    return act.write_new(tmp_path / act.FILENAME, items)


def test_round_trip(tmp_path):
    f = sample(tmp_path)
    got = act.parse_file(f)
    assert [a.id for a in got] == ["A01", "A02"]
    assert got[0].owner == "ACME --- DOE"
    assert got[0].description == "Send the minutes ({\\bf final} version)"
    assert got[1].status == "inprogress"


def test_complete_changes_only_two_arguments(tmp_path):
    f = sample(tmp_path)
    before = f.read_text(encoding="utf-8")
    act.complete(f, "A01", "2026-10-16 14:32")
    after = f.read_text(encoding="utf-8")
    assert after.replace("{done}{2026-10-16 14:32}", "{todo}{}", 1) == before
    a = act.parse_file(f)[0]
    assert (a.status, a.completed, a.is_open) == ("done", "2026-10-16 14:32", False)
    act.reopen(f, "A01")
    assert f.read_text(encoding="utf-8") == before


def test_comments_and_definitions_are_ignored(tmp_path):
    f = sample(tmp_path)
    text = f.read_text(encoding="utf-8").replace(
        "\\end{actionplan}", "% \\actionitem{X}{x}{x}{todo}{}{x}\n\\end{actionplan}")
    f.write_text(text, encoding="utf-8")
    assert len(act.parse_file(f)) == 2


def test_errors_are_loud(tmp_path):
    f = sample(tmp_path)
    text = f.read_text(encoding="utf-8")
    f.write_text(text.replace("{inprogress}", "{maybe}"), encoding="utf-8")
    with pytest.raises(act.ActionsError, match="unknown status"):
        act.parse_file(f)
    f.write_text(text.replace("{A02}", "{A01}"), encoding="utf-8")
    with pytest.raises(act.ActionsError, match="duplicate"):
        act.parse_file(f)
    f.write_text(text, encoding="utf-8")
    with pytest.raises(act.ActionsError, match="no action"):
        act.complete(f, "A99")


def test_placeholders(tmp_path):
    a = act.Action("A01", "<<ORG>>", "--", "todo", "", "<<Description>>")
    assert a.is_placeholder
    assert act.Action("A01", "\\tbc{Owner}", "--", "todo", "", "x").is_placeholder
    assert not act.Action("A01", "ACME", "--", "todo", "", "x").is_placeholder


DOC = r"""\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage[%s]{babel}
\usepackage{xcolor,colortbl,longtable,array,booktabs}
\begin{document}
\input{ACTIONS}
\end{document}
"""


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="no pdflatex")
@pytest.mark.parametrize("lang", ["french", "english"])
def test_compiles(tmp_path, lang):
    f = sample(tmp_path)
    act.complete(f, "A01", "2026-10-16 14:32")
    (tmp_path / "doc.tex").write_text(DOC % lang, encoding="utf-8")
    run = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
                         cwd=tmp_path, capture_output=True, text=True, errors="replace")
    assert run.returncode == 0, run.stdout[-2000:]
    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", "doc.pdf", "-"], cwd=tmp_path,
                              capture_output=True, text=True).stdout
        assert "14:32" in text
        assert ("Fait" if lang == "french" else "Done") in text
