"""Discovery of the report folders, owner matching and conversion.

SPDX-License-Identifier: Unlicense
"""

import json

import pytest

from cybertodopunk import actions as act
from cybertodopunk import cli, convert, scan
from cybertodopunk import config as conf


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CYBERTODOPUNK_CONFIG", str(tmp_path / "config.json"))
    (tmp_path / "Documents").mkdir()
    return tmp_path


def make_report(root, name, items, sub=None):
    d = root / name if sub is None else root / name / sub
    d.mkdir(parents=True)
    return act.write_new(d / act.FILENAME, items)


def A(i, owner, status="todo", text="x"):
    return act.Action(i, owner, "--", status, "", text)


def test_surname_and_matching():
    assert scan.surname("Jane DOE") == "DOE"
    assert scan.surname("Jane Doe") == "Doe"
    assert scan.surname("Chloë HART-LINDQVIST") == "HART-LINDQVIST"
    cfg = conf.Config(full_name="Jane DOE", aliases=["Jane"])
    tokens = scan.my_tokens(cfg)
    assert scan.is_mine("ACME --- DOE", tokens)
    assert scan.is_mine("GLOBEX — DOE + R.\\ ROE", tokens)
    assert scan.is_mine("ACME — Jane", tokens)
    assert not scan.is_mine("ACME — DOERING", tokens)
    assert not scan.is_mine("ACME --- SMITH", tokens)


def test_team():
    assert scan.is_team("ACME + NORTHWIND", "ACME")
    assert scan.is_team("ACME", "ACME")
    assert scan.is_team("ACME — all", "ACME")
    assert not scan.is_team("ACME --- DOE", "ACME")
    assert not scan.is_team("UMBRELLA", "ACME")


def test_company_of():
    assert scan.company_of("20261014_ACME_NORTHWIND", ["ACME", "GLOBEX"]) == ("20261014", "ACME")
    assert scan.company_of("20261014_GLOBEX", ["ACME", "GLOBEX"]) == ("20261014", "GLOBEX")
    assert scan.company_of("20261014_ACMEX_A", ["ACME"]) is None
    assert scan.company_of("ACME_CR_TEMPLATE", ["ACME"]) is None


def test_latex_to_text():
    assert scan.latex_to_text("Mi-avr.\\ 2027") == "Mi-avr. 2027"
    assert scan.latex_to_text("ACME --- DOE") == "ACME — DOE"
    assert scan.latex_to_text("Workshop (\\(\\sim\\)2\\,h) \\& \\textbf{demo}") == "Workshop (~2 h) & demo"


def test_scan_groups(home):
    docs = home / "Documents" / "LaTex"
    make_report(docs, "20261014_ACME_NORTHWIND", [A("A01", "ACME --- DOE"), A("A02", "NORTHWIND"),
                                              A("A03", "ACME — DOE", "done")])
    make_report(docs, "20261014_GLOBEX_HiH", [A("A01", "GLOBEX — DOE")], sub="meetings/D2-04_Partner")
    make_report(docs, "20261013_OTHER_X", [A("A01", "DOE")])
    make_report(docs, "20261012_ACME_TPL", [A("A01", "<<NAME>> DOE")])
    cfg = conf.Config(full_name="Jane DOE", companies=["ACME", "GLOBEX"], active_company="ACME")
    groups, errors = scan.scan(cfg, companies=["ACME"])
    assert errors == []
    acme = [g for g in groups if g.tasks]
    assert [g.cr_id for g in acme] == ["20261014_ACME_NORTHWIND"]
    assert [t.action.id for t in acme[0].tasks] == ["A01"]
    groups, _ = scan.scan(cfg, companies=["GLOBEX"])
    assert groups[0].tasks[0].sub == "D2-04_Partner"
    groups, _ = scan.scan(cfg, everyone=True, include_done=True, companies=["ACME"])
    assert len([t for g in groups for t in g.tasks]) == 3


def test_cli_done_json(home, capsys):
    f = make_report(home / "Documents", "20261014_ACME_NORTHWIND", [A("A01", "ACME --- DOE")])
    conf.save(conf.Config(companies=["ACME", "GLOBEX"], active_company="ACME"))
    assert cli.main(["config", "name", "Jane", "DOE"]) == 0
    capsys.readouterr()
    assert cli.main(["list", "--json", "--all-companies"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["active"] == "ACME" and data["groups"][0]["tasks"][0]["id"] == "A01"
    assert cli.main(["done", str(f), "A01", "--at", "2026-10-16 09:00"]) == 0
    assert act.parse_file(f)[0].completed == "2026-10-16 09:00"
    capsys.readouterr()
    cli.main(["list", "--json"])
    assert json.loads(capsys.readouterr().out)["groups"] == []
    assert cli.main(["switch", "globex"]) == 0
    assert conf.load().active_company == "GLOBEX"
    assert cli.main(["switch", "NOPE"]) == 1


OLD = r"""\section{Action plan}

\renewcommand{\arraystretch}{1.35}
\begin{longtable}{@{}p{7.2cm} p{3.2cm} p{1.8cm} p{2.0cm}@{}}
\toprule
\rowcolor{tablehead}
\color{white}\textbf{Action} & \color{white}\textbf{Owner} &
\color{white}\textbf{Due} & \color{white}\textbf{Status} \\
\midrule
\endhead

Share the code \& the docs (v1) &
\owner{ACME --- DOE} & \deadline{14/10} & \done \\

\rowcolor{rowalt}
% A comment & with an ampersand \\
Run the workshop (\(\sim\)2\,h) &
\owner{UMBRELLA + ACME} & TBD & \inprogress \\

\bottomrule
\end{longtable}

\section{Timeline}
"""


def test_convert(tmp_path):
    tex = tmp_path / "CR-ACME-20261014-X.tex"
    tex.write_text(OLD, encoding="utf-8")
    out, items = convert.convert(tex)
    assert [(a.id, a.owner, a.due, a.status) for a in items] == [
        ("A01", "ACME --- DOE", "14/10", "done"),
        ("A02", "UMBRELLA + ACME", "TBD", "inprogress"),
    ]
    assert items[0].description == "Share the code \\& the docs (v1)"
    new = tex.read_text(encoding="utf-8")
    assert "\\input{ACTIONS}" in new and "longtable" not in new
    assert "\\renewcommand{\\arraystretch}{1.35}" in new
    assert [a.id for a in act.parse_file(out)] == ["A01", "A02"]
    with pytest.raises(convert.ConvertError, match="already converted"):
        convert.convert(tex)
