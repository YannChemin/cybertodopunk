"""Main window: my open actions per report, and the settings.

SPDX-License-Identifier: Unlicense
"""

import os

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import actions as act  # noqa: E402
from .. import config as conf  # noqa: E402
from .. import scan  # noqa: E402

REFRESH_SECONDS = 60


class TaskRow(Gtk.Box):
    """One action: text, owner/due line, status pill, START and DONE buttons."""

    def __init__(self, window, task):
        super().__init__(spacing=10, css_classes=["ctp-row"])
        self.window = window
        self.task = task
        d = task.to_dict()
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, spacing=2)
        title = Gtk.Label(label=d["text"], xalign=0, wrap=True,
                          wrap_mode=Pango.WrapMode.WORD_CHAR, css_classes=["ctp-title"])
        bits = [d["owner"]]
        if d["due"] and d["due"] not in ("–", "-"):
            bits.append(f"due {d['due']}")
        bits.append(d["id"])
        if d["sub"]:
            bits.insert(0, d["sub"])
        meta = Gtk.Label(label="  ·  ".join(bits), xalign=0, wrap=True, css_classes=["ctp-meta"])
        texts.append(title)
        texts.append(meta)
        self.append(texts)

        pill = Gtk.Label(label={"todo": "TO DO", "inprogress": "ACTIVE", "done": "DONE"}[d["status"]],
                         css_classes=["ctp-pill", d["status"]], valign=Gtk.Align.CENTER)
        self.append(pill)
        if d["status"] == "todo":
            start = Gtk.Button(label="START", valign=Gtk.Align.CENTER, css_classes=["ctp-start"],
                               tooltip_text="Mark in progress")
            start.connect("clicked", lambda *_: window.set_status(self, "inprogress"))
            self.append(start)
        if d["status"] == "done":
            undo = Gtk.Button(label="REOPEN", valign=Gtk.Align.CENTER, css_classes=["ctp-start"])
            undo.connect("clicked", lambda *_: window.set_status(self, "todo"))
            self.append(undo)
        else:
            done = Gtk.Button(label="DONE", valign=Gtk.Align.CENTER, css_classes=["ctp-done"],
                              tooltip_text="Check off: writes the completion time into ACTIONS.tex")
            done.connect("clicked", lambda *_: window.set_status(self, "done"))
            self.append(done)


class GroupCard(Gtk.Box):
    """A report (CR_ID) that unrolls into its actions."""

    def __init__(self, window, group, expanded):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["ctp-group"])
        self.group = group
        head = Gtk.Button(css_classes=["ctp-group-head", "flat"])
        box = Gtk.Box(spacing=10)
        self.arrow = Gtk.Image(icon_name="pan-end-symbolic")
        title = Gtk.Label(label=group.cr_id, xalign=0, hexpand=True,
                          ellipsize=Pango.EllipsizeMode.END, css_classes=["ctp-group-title"])
        self.count = Gtk.Label(css_classes=["ctp-count"])
        folder = Gtk.Button(icon_name="folder-open-symbolic", css_classes=["flat"],
                            tooltip_text=group.path, valign=Gtk.Align.CENTER)
        folder.connect("clicked", lambda *_: window.open_path(group.path))
        for w in (self.arrow, title, self.count):
            box.append(w)
        head.set_child(box)
        top = Gtk.Box()
        head.set_hexpand(True)
        top.append(head)
        top.append(folder)
        self.append(top)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.revealer = Gtk.Revealer(child=self.rows, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.append(self.revealer)
        head.connect("clicked", lambda *_: self.set_expanded(not self.revealer.get_reveal_child()))
        for t in group.tasks:
            self.rows.append(TaskRow(window, t))
        self.update_count()
        self.set_expanded(expanded)

    def set_expanded(self, on):
        self.revealer.set_reveal_child(on)
        self.arrow.set_from_icon_name("pan-down-symbolic" if on else "pan-end-symbolic")

    @property
    def expanded(self):
        return self.revealer.get_reveal_child()

    def n_rows(self):
        n, child = 0, self.rows.get_first_child()
        while child:
            n += 1
            child = child.get_next_sibling()
        return n

    def update_count(self):
        self.count.set_label(f"{self.n_rows():02d}")


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="CyberTodoPunk")
        self.set_default_size(980, 760)
        self.set_size_request(360, 420)
        self.add_css_class("ctp-window")
        self.cfg = conf.load()
        self.cards = []
        self.expanded = set()
        self.show_done = False
        self.everyone = False
        # A company switch starts with every report folded.
        self.collapse_next = False

        header = Adw.HeaderBar()
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        wordmark = Gtk.Label(css_classes=["ctp-wordmark"])
        wordmark.set_markup(
            '<span foreground="#00f0ff">CYBER</span>TODO'
            '<span foreground="#fcee0a">//</span><span foreground="#ff2a6d">PUNK</span>'
        )
        self.tagline = Gtk.Label(css_classes=["ctp-tagline"])
        title.append(wordmark)
        title.append(self.tagline)
        header.set_title_widget(title)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Rescan (Ctrl+R)",
                             action_name="win.refresh")
        header.pack_start(refresh)
        menu = Gio.Menu()
        view = Gio.Menu()
        view.append("Show completed actions", "win.show-done")
        view.append("Show every owner's actions", "win.everyone")
        menu.append_section(None, view)
        menu.append("About CyberTodoPunk", "app.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))

        a = Gio.SimpleAction.new("refresh", None)
        a.connect("activate", lambda *_: self.refresh())
        self.add_action(a)
        for name in ("show-done", "everyone"):
            a = Gio.SimpleAction.new_stateful(name, None, GLib.Variant.new_boolean(False))
            a.connect("change-state", self._on_toggle)
            self.add_action(a)

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(self._tasks_page(), "tasks", "Actions", "object-select-symbolic")
        self.stack.add_titled_with_icon(self._settings_page(), "settings", "Settings",
                                        "preferences-system-symbolic")
        switcher = Adw.ViewSwitcherBar(stack=self.stack, reveal=True)
        header_switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.pack_end(header_switcher)

        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        tv.set_content(self.stack)
        tv.add_bottom_bar(switcher)
        switcher.set_reveal(False)
        self.toasts = Adw.ToastOverlay(child=tv)
        self.set_content(self.toasts)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        narrow.add_setter(switcher, "reveal", True)
        narrow.add_setter(header_switcher, "visible", False)
        self.add_breakpoint(narrow)

        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)
        self.connect("notify::is-active", lambda *_: self.is_active() and self.refresh())

    # Pages -------------------------------------------------------------------

    def _tasks_page(self):
        self.switch_box = Gtk.Box(css_classes=["linked", "ctp-switch"], halign=Gtk.Align.START)
        self.total = Gtk.Label(css_classes=["ctp-total"], hexpand=True, xalign=1)
        self.filter = Gtk.SearchEntry(placeholder_text="Filter actions", width_chars=22)
        self.filter.connect("search-changed", lambda *_: self._apply_filter())
        strip = Gtk.Box(spacing=14, css_classes=["ctp-strip"])
        strip.append(self.switch_box)
        strip.append(self.filter)
        strip.append(self.total)

        self.banner = Adw.Banner(button_label="Details")
        self.banner.connect("button-clicked", lambda *_: self._show_errors())
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.empty = Adw.StatusPage(icon_name="object-select-symbolic", vexpand=True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                       margin_start=16, margin_end=16, margin_top=14, margin_bottom=16)
        body.append(strip)
        body.append(self.list)
        body.append(self.empty)
        clamp = Adw.Clamp(maximum_size=1100, child=body)
        scroll = Gtk.ScrolledWindow(child=clamp, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(self.banner)
        page.append(scroll)
        return page

    def _settings_page(self):
        page = Adw.PreferencesPage(css_classes=["ctp-settings"])

        me = Adw.PreferencesGroup(
            title="IDENTITY",
            description="Actions are mine when my surname (the word in capitals, else the last "
                        "word) or an alias appears in their owner column.",
        )
        self.name_row = Adw.EntryRow(title="Full name (e.g. Jane DOE)", show_apply_button=True)
        self.name_row.set_text(self.cfg.full_name)
        self.name_row.connect("apply", self._on_name)
        self.alias_row = Adw.EntryRow(title="Aliases, comma separated (e.g. Jane, JD)",
                                      show_apply_button=True)
        self.alias_row.set_text(", ".join(self.cfg.aliases))
        self.alias_row.connect("apply", self._on_aliases)
        team = Adw.SwitchRow(title="Include whole-company actions",
                             subtitle="Owners such as “ACME”, “ACME + UMBRELLA” or “ACME — all”")
        team.set_active(self.cfg.include_team)
        team.connect("notify::active", self._on_team)
        me.add(self.name_row)
        me.add(self.alias_row)
        me.add(team)
        page.add(me)

        self.paths_group = Adw.PreferencesGroup(
            title="SEARCH PATHS",
            description="Folders searched (recursively) for ACTIONS.tex files.",
        )
        add = Gtk.Button(icon_name="list-add-symbolic", css_classes=["flat"],
                         tooltip_text="Add a folder")
        add.connect("clicked", self._on_add_path)
        self.paths_group.set_header_suffix(add)
        page.add(self.paths_group)

        self.comp_group = Adw.PreferencesGroup(
            title="COMPANIES",
            description="Report folders are named YYYYMMDD_&lt;COMPANY&gt;_&lt;subject&gt;; each company "
                        "has its own list, picked with the switch on the Actions page.",
        )
        self.comp_entry = Adw.EntryRow(title="Add a company (e.g. ACME)", show_apply_button=True)
        self.comp_entry.connect("apply", self._on_add_company)
        page.add(self.comp_group)
        self._settings_rows = []
        self._fill_settings()
        return page

    def _fill_settings(self):
        for group, row in self._settings_rows:
            group.remove(row)
        self._settings_rows = []
        for p in self.cfg.search_paths:
            row = Adw.ActionRow(title=p, use_markup=False)
            if p == conf.default_root():
                row.set_subtitle("default, always searched")
            else:
                rm = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"],
                                valign=Gtk.Align.CENTER, tooltip_text="Remove")
                rm.connect("clicked", lambda _b, p=p: self._edit(lambda c: c.extra_paths.remove(p)))
                row.add_suffix(rm)
            self.paths_group.add(row)
            self._settings_rows.append((self.paths_group, row))
        for c in self.cfg.companies:
            row = Adw.ActionRow(title=c, subtitle=f"YYYYMMDD_{c}_…", use_markup=False)
            if len(self.cfg.companies) > 1:
                rm = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"],
                                valign=Gtk.Align.CENTER, tooltip_text="Remove")
                rm.connect("clicked", lambda _b, c=c: self._remove_company(c))
                row.add_suffix(rm)
            self.comp_group.add(row)
            self._settings_rows.append((self.comp_group, row))
        self.comp_group.add(self.comp_entry)
        self._settings_rows.append((self.comp_group, self.comp_entry))

    # Settings handlers ---------------------------------------------------------

    def _edit(self, change):
        self.cfg = conf.load()
        change(self.cfg)
        if self.cfg.active_company not in self.cfg.companies:
            self.cfg.active_company = self.cfg.companies[0]
        conf.save(self.cfg)
        self._fill_settings()
        self.refresh()

    def _on_name(self, row):
        self._edit(lambda c: setattr(c, "full_name", row.get_text().strip()))
        self.toast(f"Matching owner names on “{scan.surname(self.cfg.full_name)}”")

    def _on_aliases(self, row):
        aliases = [a.strip() for a in row.get_text().split(",") if a.strip()]
        self._edit(lambda c: setattr(c, "aliases", aliases))

    def _on_team(self, row, _pspec):
        self._edit(lambda c: setattr(c, "include_team", row.get_active()))

    def _on_add_path(self, *_):
        dialog = Gtk.FileDialog(title="Add a search folder")

        def done(dlg, res):
            try:
                folder = dlg.select_folder_finish(res)
            except GLib.Error:
                return
            path = folder.get_path()
            if path and path not in self.cfg.extra_paths:
                self._edit(lambda c: c.extra_paths.append(path))

        dialog.select_folder(self, None, done)

    def _on_add_company(self, row):
        name = row.get_text().strip()
        row.set_text("")
        if name and name not in self.cfg.companies:
            self._edit(lambda c: c.companies.append(name))

    def _remove_company(self, name):
        self._edit(lambda c: c.companies.remove(name))

    # Actions page ----------------------------------------------------------------

    def _on_toggle(self, action, value):
        action.set_state(value)
        if action.get_name() == "show-done":
            self.show_done = value.get_boolean()
        else:
            self.everyone = value.get_boolean()
        self.refresh()

    def _fill_switch(self):
        child = self.switch_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.switch_box.remove(child)
            child = nxt
        first = None
        for c in self.cfg.companies:
            b = Gtk.ToggleButton(label=c.upper(), css_classes=["ctp-company"])
            if first:
                b.set_group(first)
            else:
                first = b
            b.set_active(c == self.cfg.active_company)
            b.connect("toggled", lambda btn, c=c: btn.get_active() and self._switch(c))
            self.switch_box.append(b)

    def _switch(self, company):
        if company == self.cfg.active_company:
            return
        self.cfg = conf.load()
        self.cfg.active_company = company
        conf.save(self.cfg)
        self.collapse_next = True
        self.refresh()

    def _tick(self):
        if self.get_visible():
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        self.cfg = conf.load()
        if self.collapse_next:
            self.expanded = set()
            self.collapse_next = False
        elif self.cards:
            self.expanded = {c.group.cr_id for c in self.cards if c.expanded}
        self._fill_switch()
        groups, self.errors = scan.scan(self.cfg, everyone=self.everyone,
                                        include_done=self.show_done,
                                        companies=[self.cfg.active_company])
        groups = [g for g in groups if g.tasks]
        for c in self.cards:
            self.list.remove(c)
        self.cards = [GroupCard(self, g, g.cr_id in self.expanded) for g in groups]
        for c in self.cards:
            self.list.append(c)
        who = "EVERYONE" if self.everyone else (scan.surname(self.cfg.full_name).upper()
                                                or "SET YOUR NAME")
        self.tagline.set_label(f"{self.cfg.active_company.upper()} · {who}")
        if self.errors:
            self.banner.set_title(f"{len(self.errors)} ACTIONS.tex file(s) could not be read")
        self.banner.set_revealed(bool(self.errors))
        self._apply_filter()

    def _apply_filter(self):
        needle = scan.fold(self.filter.get_text().strip())
        total = 0
        for card in self.cards:
            shown = 0
            row = card.rows.get_first_child()
            while row:
                d = row.task.to_dict()
                hay = scan.fold(" ".join((d["text"], d["owner"], d["sub"], card.group.cr_id)))
                vis = not needle or needle in hay
                row.set_visible(vis)
                shown += vis
                row = row.get_next_sibling()
            card.set_visible(shown > 0)
            if needle and shown:
                card.set_expanded(True)
            total += shown
        self.total.set_label(f"{total:02d} OPEN" if not self.show_done else f"{total:02d} ACTIONS")
        self.empty.set_visible(total == 0)
        if not self.cfg.full_name and not self.everyone:
            self.empty.set_title("Who are you?")
            self.empty.set_description("Set your full name in Settings: actions are matched "
                                       "on the surname in their owner column.")
        else:
            self.empty.set_title("Nothing left to do")
            self.empty.set_description(
                f"No open action for you in the {self.cfg.active_company} reports "
                f"(ACTIONS.tex files under {', '.join(self.cfg.search_paths)}).")

    def set_status(self, row, status):
        t = row.task
        try:
            a = act.set_status(t.file, t.action.id, status)
        except (OSError, act.ActionsError) as exc:
            self.toast(f"Could not update {t.file}: {exc}")
            return
        if status == "done":
            toast = Adw.Toast(title=f"{a.id} done at {a.completed}", timeout=8, button_label="UNDO")
            toast.connect("button-clicked", lambda *_: self._undo(t))
            self.toasts.add_toast(toast)
        self.refresh()

    def _undo(self, task):
        try:
            act.reopen(task.file, task.action.id)
        except (OSError, act.ActionsError) as exc:
            self.toast(str(exc))
        self.refresh()

    def open_path(self, path):
        Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(path, None), None)

    def toast(self, text):
        t = Adw.Toast(title=text, timeout=6)
        t.set_use_markup(False)
        self.toasts.add_toast(t)

    def _show_errors(self):
        text = "\n\n".join(f"{os.path.relpath(e['file'], os.path.expanduser('~'))}\n{e['error']}"
                           for e in self.errors)
        dlg = Adw.AlertDialog(heading="Unreadable ACTIONS.tex", body=text)
        dlg.add_response("ok", "OK")
        dlg.present(self)
