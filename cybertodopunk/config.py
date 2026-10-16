"""User settings: who I am, where to look, which companies to keep apart.

Stored as JSON in ``$XDG_CONFIG_HOME/cybertodopunk/config.json``
(``CYBERTODOPUNK_CONFIG`` overrides the path).  The app, the CLI and the
top-bar extension (through the CLI) share it.

SPDX-License-Identifier: Unlicense
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_COMPANIES = ["WORK", "HOME"]


def default_root():
    """``$HOME/Documents``, always searched."""
    return str(Path.home() / "Documents")


def config_path():
    env = os.environ.get("CYBERTODOPUNK_CONFIG")
    if env:
        return Path(env)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "cybertodopunk" / "config.json"


@dataclass
class Config:
    # "Jane DOE": the surname (the token in capitals, else the last one)
    # is what is looked for in the owner column.
    full_name: str = ""
    # Other spellings of me in owner columns: "Jane", "JD", ...
    aliases: list = field(default_factory=list)
    # Searched in addition to ~/Documents.
    extra_paths: list = field(default_factory=list)
    # Report folders are YYYYMMDD_<COMPANY>[_...].
    companies: list = field(default_factory=lambda: list(DEFAULT_COMPANIES))
    active_company: str = "WORK"
    # Also list actions owned by the whole company ("ACME", "ACME + UMBRELLA").
    include_team: bool = False

    @property
    def search_paths(self):
        seen, out = set(), []
        for p in [default_root(), *self.extra_paths]:
            p = os.path.expanduser(p)
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def to_dict(self):
        return asdict(self)


def load(path=None):
    path = Path(path) if path else config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except (OSError, ValueError):
        return Config()
    known = Config.__dataclass_fields__
    cfg = Config(**{k: v for k, v in data.items() if k in known})
    if not cfg.companies:
        cfg.companies = list(DEFAULT_COMPANIES)
    if cfg.active_company not in cfg.companies:
        cfg.active_company = cfg.companies[0]
    return cfg


def save(cfg, path=None):
    path = Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return path
