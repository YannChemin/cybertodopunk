# CYBERTODO//PUNK

My actions from meeting reports, in the GNOME top bar.

Meeting reports (comptes rendus) are LaTeX files in folders named
`YYYYMMDD_<COMPANY>_<subject>`, for example `20261014_ACME_NORTHWIND`. Their action
plan lives in an **`ACTIONS.tex`** next to the report, which the report
includes with `\input{ACTIONS}`. CyberTodoPunk finds these files, keeps the
actions whose owner is me, one list per company, and checks them off by
writing the completion time back into `ACTIONS.tex`. The next compilation
of the report shows when each action was done.

The look is [MetaMonitor](https://github.com/YannChemin/MetaMonitor)'s
Night City palette: void background, acid yellow, neon cyan, square cards with
a yellow notch, Orbitron and Rajdhani.

## Install

```sh
make deb                                        # builds dist/cybertodopunk_<version>_all.deb
sudo apt install ./dist/cybertodopunk_0.1.0_all.deb
# or, per user, without a package:
make install                                    # into ~/.local
```

Then enable the *CyberTodoPunk* extension (`gnome-extensions enable
cybertodopunk@yannchemin.github.io`, or the Extensions app). GNOME Shell
46–49 loads a new extension after you log out and back in. Debian 13 already
has every dependency (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`).

Set your name once, in the window (*Settings*) or on the command line:

```sh
cybertodopunk config name "Jane DOE"
```

## The top bar

`TODO` and the number of my open actions in the active company. The menu
holds:

- the **company switch** (ACME / GLOBEX / ...), each with its count; the choice
  is saved, so the bar, the window and the CLI agree;
- one entry per **report** (CR_ID, the folder name), newest first, that
  unrolls into its actions: text, owner, due date and, for meetings held in
  one report (`meetings/D2-04_Partner/`), the meeting;
- **DONE** on each action: writes `done` and `YYYY-MM-DD HH:MM` into
  `ACTIONS.tex`, and the action leaves the list. *Undo last DONE* reopens it.

Clicking an action opens its report folder. The list refreshes when the menu
opens and every 5 minutes.

## The window

`cybertodopunk` without arguments. *Actions*: the same lists with a filter,
START (mark in progress) and DONE buttons, and toasts with UNDO. The menu shows
completed actions (with REOPEN) or every owner's actions. *Settings*:

| Setting | Effect |
|---|---|
| Full name | `Jane DOE`: the surname, the word in capitals (else the last word), is looked for in the owner column, as a whole word, ignoring case and accents. |
| Aliases | Other spellings found in owner columns (`Jane`, `JD`). |
| Whole-company actions | Also list actions owned by the company itself: `ACME`, `ACME + UMBRELLA`, `ACME — all`. |
| Search paths | `~/Documents` is always searched; add other folders. Hidden folders, `mp3/`, `transcripts/`, `backups/` and the like are skipped. |
| Companies | The `<COMPANY>` of the folder names; each gets its own list. |

Settings are in `~/.config/cybertodopunk/config.json` (`CYBERTODOPUNK_CONFIG`
overrides the path).

## ACTIONS.tex

```latex
\begin{actionplan}

\actionitem{A01}{ACME --- DOE}{14/10}{todo}{}
  {Share the demo code with the partners}

\actionitem{A02}{ACME + NORTHWIND}{--}{done}{2026-10-16 14:32}
  {Send the minutes to all attendees}

\end{actionplan}
```

One `\actionitem` per action, six arguments:

| # | Argument | Content |
|---|---|---|
| 1 | ID | Unique in the file: `A01`, `A02`, ... |
| 2 | Owner | `ORG --- SURNAME`, `ORG`, `ORG + ORG`. |
| 3 | Due | Free text: `14/10`, `--`, `Mi-avr.\ 2027`. |
| 4 | Status | `todo`, `inprogress` or `done`. |
| 5 | Completed | Empty while open; `YYYY-MM-DD HH:MM` once done. |
| 6 | Description | Any LaTeX. |

The preamble of the file (written by `cybertodopunk new` and `convert`, and in
`latex/ACTIONS-TEMPLATE.tex`) defines `actionplan` and `\actionitem`: the
four-column longtable of the ACME reports (action, owner, due, status),
shaded every other row, headed in French or English according to babel. It
uses the report's own `\owner`, `\deadline`, `\todo`, `\inprogress`,
`\done` and colours when it defines them, and fallbacks otherwise. A done
action shows *Fait/Done* and its completion time. The definitions are
guarded, so one report can input several ACTIONS.tex files (one per
meeting).

Checking an action off rewrites only its status and completion arguments,
atomically; comments, layout and the other actions stay byte for byte.
Actions containing `<<...>>`, `@NAME@` or `\tbc{...}` are template
placeholders and are ignored. A file that does not parse (unknown status,
duplicate ID, missing argument) is reported, not guessed at:
`cybertodopunk check` lists every file and its errors.

## Command line

```text
cybertodopunk                                   the window
cybertodopunk list [--json] [--company C | --all-companies] [--everyone] [--done]
cybertodopunk done FILE ID [--at "YYYY-MM-DD HH:MM"]
cybertodopunk start FILE ID | reopen FILE ID
cybertodopunk switch COMPANY
cybertodopunk config [show | name NAME | alias add|rm X | path add|rm DIR
                      | company add|rm NAME | team on|off]
cybertodopunk new [DIR]                         empty ACTIONS.tex
cybertodopunk convert REPORT.tex... [--dry-run] [--input PATH]
cybertodopunk check [DIR...]
```

`convert` moves the hand-written action `longtable` of an older report (rows
`Description & \owner{..} & \deadline{..} & \todo \\`) into a new
ACTIONS.tex, and replaces the table with `\input{ACTIONS}`; the section title
and `\arraystretch` stay in the report. `--input` sets the `\input` path for
a report compiled from another folder (`meetings/D2-04_Partner/ACTIONS`).

## Development

```sh
make test         # pytest: parser, in-place updates, matching, conversion, pdflatex builds
make shell-test   # extension and window in a throwaway headless GNOME Shell
make run          # the window from the source tree
make deb          # dist/cybertodopunk_<version>_all.deb (version from debian/changelog,
                  # which must match cybertodopunk/__init__.py)
```

`make shell-test` (or `tests/shell/run_nested_shell.sh [OUTDIR]`) starts
`gnome-shell --headless` on a private D-Bus bus with throwaway XDG and home
folders holding sample reports. It checks the indicator and its count, opens
the menu and a report, clicks DONE and checks ACTIONS.tex, switches company,
then opens the window. Screenshots and logs go to OUTDIR. Your desktop session
is not touched.

## Licence

Unlicense (public domain). Orbitron and Rajdhani are under the SIL Open Font
Licence (`data/fonts/OFL-*.txt`).
