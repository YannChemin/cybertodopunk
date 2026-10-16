// CyberTodoPunk top-bar menu.
//
// Shows "TODO" and the number of my open meeting actions for the active
// company.  The menu has the company switch, then one entry per report
// (CR_ID, the YYYYMMDD_<COMPANY>_... folder) that unrolls into its actions;
// DONE checks an action off, which writes the completion time into the
// report's ACTIONS.tex, and the action leaves the list.  All data goes
// through the `cybertodopunk` command (list --json, done, reopen, switch).
//
// SPDX-License-Identifier: Unlicense

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const APP_ID = 'io.github.yannchemin.CyberTodoPunk.desktop';
const REFRESH_SECONDS = 300;
const ITEM_WIDTH = 460;

function findCli() {
    const onPath = GLib.find_program_in_path('cybertodopunk');
    if (onPath)
        return onPath;
    for (const p of [
        GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'cybertodopunk']),
        '/usr/bin/cybertodopunk',
    ]) {
        if (GLib.file_test(p, GLib.FileTest.IS_EXECUTABLE))
            return p;
    }
    return null;
}

// Run the CLI; resolves with stdout, rejects with stderr.
function runCli(args) {
    return new Promise((resolve, reject) => {
        const cli = findCli();
        if (!cli) {
            reject(new Error('cybertodopunk is not installed'));
            return;
        }
        let proc;
        try {
            proc = Gio.Subprocess.new([cli, ...args],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        } catch (e) {
            reject(e);
            return;
        }
        proc.communicate_utf8_async(null, null, (p, res) => {
            try {
                const [, out, err] = p.communicate_utf8_finish(res);
                if (p.get_successful())
                    resolve(out);
                else
                    reject(new Error((err || out || 'failed').trim()));
            } catch (e) {
                reject(e);
            }
        });
    });
}

const TaskItem = GObject.registerClass(
class TaskItem extends PopupMenu.PopupBaseMenuItem {
    _init(task, onDone, onOpen) {
        super._init({style_class: 'ctp-task-item'});
        this._task = task;
        const column = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
            width: ITEM_WIDTH,
        });
        const text = new St.Label({text: task.text, style_class: 'ctp-task-text'});
        text.clutter_text.line_wrap = true;
        text.clutter_text.ellipsize = 0;  // Pango.EllipsizeMode.NONE
        const bits = [];
        if (task.sub)
            bits.push(task.sub);
        bits.push(task.owner);
        if (task.due && task.due !== '–' && task.due !== '-')
            bits.push(`due ${task.due}`);
        if (task.status === 'inprogress')
            bits.push('IN PROGRESS');
        const meta = new St.Label({text: bits.join('  ·  '), style_class: 'ctp-task-meta'});
        meta.clutter_text.ellipsize = 3;  // Pango.EllipsizeMode.END
        column.add_child(text);
        column.add_child(meta);
        this.add_child(column);

        const done = new St.Button({
            label: 'DONE',
            style_class: 'ctp-done-button',
            y_align: Clutter.ActorAlign.CENTER,
            can_focus: true,
        });
        done.connect('clicked', () => onDone(this));
        this.add_child(done);
        this.doneButton = done;
        this.connect('activate', () => onOpen(task));
    }

    get task() {
        return this._task;
    }
});

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, 'CyberTodoPunk');
        this._extension = extension;
        this._data = null;
        this._error = null;
        this._undo = null;

        const box = new St.BoxLayout({style_class: 'ctp-panel-box'});
        box.add_child(new St.Icon({
            gicon: Gio.icon_new_for_string(`${extension.path}/icons/cybertodopunk-symbolic.svg`),
            style_class: 'system-status-icon',
        }));
        box.add_child(new St.Label({
            text: 'TODO',
            style_class: 'ctp-panel-label',
            y_align: Clutter.ActorAlign.CENTER,
        }));
        this._count = new St.Label({
            text: '',
            style_class: 'ctp-panel-count',
            y_align: Clutter.ActorAlign.CENTER,
        });
        box.add_child(this._count);
        this.add_child(box);

        // Company switch.
        this._switchItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        this._switchBox = new St.BoxLayout({style_class: 'ctp-switch', x_expand: true});
        this._switchItem.add_child(this._switchBox);
        this.menu.addMenuItem(this._switchItem);

        // The reports, in a scroll view so that a long list stays on screen.
        // The section is not added with addMenuItem (it lives inside the
        // scroll view), so it is wired to the menu by hand: its submenus
        // need the top menu (one open at a time) and the open/close signal.
        this._groups = new PopupMenu.PopupMenuSection();
        this._groups._setParent(this.menu);
        this.menu.connect('open-state-changed', (_m, open) => {
            if (open)
                this._groups.open();
            else
                this._groups.close();
        });
        this._scroll = new St.ScrollView({
            style_class: 'ctp-scroll',
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            overlay_scrollbars: true,
            child: this._groups.actor,
        });
        const holder = new PopupMenu.PopupMenuSection();
        holder.actor.add_child(this._scroll);
        this.menu.addMenuItem(holder);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._undoItem = this.menu.addAction('Undo last DONE', () => this._undoLast());
        this._undoItem.visible = false;
        this.menu.addAction('Refresh', () => this.refresh());
        this.menu.addAction('Open CyberTodoPunk', () => this._launch());

        this.menu.connect('open-state-changed', (_m, open) => {
            if (open)
                this.refresh();
        });
        this.refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
            this.refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    async refresh() {
        try {
            const out = await runCli(['list', '--json', '--all-companies']);
            this._data = JSON.parse(out);
            this._error = null;
        } catch (e) {
            this._error = e.message;
        }
        if (!this._destroyed)
            this._render();
    }

    _active() {
        return this._data?.active ?? this._data?.companies?.[0] ?? '';
    }

    _groupsOf(company) {
        return (this._data?.groups ?? []).filter(g => g.company === company && g.tasks.length);
    }

    _countOf(company) {
        return this._groupsOf(company).reduce((n, g) => n + g.tasks.length, 0);
    }

    _render() {
        const active = this._active();
        const n = this._data ? this._countOf(active) : 0;
        this._count.text = this._data ? `${n}` : '!';
        this._count.visible = !this._data || n > 0;

        this._switchBox.destroy_all_children();
        for (const c of this._data?.companies ?? []) {
            const b = new St.Button({
                label: `${c.toUpperCase()} ${this._countOf(c)}`,
                style_class: 'ctp-company-button',
                toggle_mode: true,
                checked: c === active,
                x_expand: true,
                can_focus: true,
            });
            b.connect('clicked', () => this._switch(c));
            this._switchBox.add_child(b);
        }
        this._switchItem.visible = (this._data?.companies?.length ?? 0) > 1;

        this._groups.removeAll();
        if (this._error) {
            this._groups.addMenuItem(new PopupMenu.PopupMenuItem(this._error, {reactive: false}));
            return;
        }
        if (!this._data.user) {
            this._groups.addMenuItem(new PopupMenu.PopupMenuItem(
                'Set your full name in CyberTodoPunk', {reactive: false}));
        }
        const groups = this._groupsOf(active);
        if (!groups.length) {
            this._groups.addMenuItem(new PopupMenu.PopupMenuItem(
                `Nothing to do for ${active}`, {reactive: false}));
        }
        for (const g of groups) {
            const sub = new PopupMenu.PopupSubMenuMenuItem(g.cr_id);
            sub.add_style_class_name('ctp-group-item');
            // The outer scroll view does the scrolling.  When the whole menu
            // reaches the screen height, the submenu would turn on its own
            // scrollbar, and a scroll view nested in ours is squeezed to
            // its minimum height: the report unrolls into an empty list.
            sub.menu._needsScrollbar = () => false;
            sub._ctpCount = new St.Label({
                text: `${g.tasks.length}`,
                style_class: 'ctp-group-count',
                y_align: Clutter.ActorAlign.CENTER,
            });
            sub.insert_child_below(sub._ctpCount, sub._triangleBin);
            for (const t of g.tasks) {
                sub.menu.addMenuItem(new TaskItem(t,
                    item => this._done(item, sub, g),
                    () => this._open(g.path)));
            }
            this._groups.addMenuItem(sub);
        }
        const errors = this._data.errors?.length ?? 0;
        if (errors) {
            this._groups.addMenuItem(new PopupMenu.PopupMenuItem(
                `${errors} ACTIONS.tex unreadable: run "cybertodopunk check"`, {reactive: false}));
        }
    }

    async _switch(company) {
        if (!this._data || company === this._active()) {
            this._render();
            return;
        }
        this._data.active = company;
        this._render();
        try {
            await runCli(['switch', company]);
        } catch (e) {
            Main.notifyError('CyberTodoPunk', e.message);
        }
    }

    async _done(item, sub, group) {
        const t = item.task;
        try {
            await runCli(['done', t.file, t.id]);
        } catch (e) {
            Main.notifyError('CyberTodoPunk', e.message);
            return;
        }
        this._undo = {file: t.file, id: t.id};
        this._undoItem.label.text = `Undo DONE: ${t.text.slice(0, 40)}${t.text.length > 40 ? '…' : ''}`;
        this._undoItem.visible = true;
        group.tasks = group.tasks.filter(x => !(x.file === t.file && x.id === t.id));
        item.destroy();
        if (group.tasks.length) {
            sub._ctpCount.text = `${group.tasks.length}`;
        } else {
            sub.destroy();
        }
        const n = this._countOf(this._active());
        this._count.text = `${n}`;
        this._count.visible = n > 0;
    }

    async _undoLast() {
        if (!this._undo)
            return;
        try {
            await runCli(['reopen', this._undo.file, this._undo.id]);
        } catch (e) {
            Main.notifyError('CyberTodoPunk', e.message);
        }
        this._undo = null;
        this._undoItem.visible = false;
        this.refresh();
    }

    _open(path) {
        try {
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(path, null),
                global.create_app_launch_context(0, -1));
        } catch (e) {
            Main.notifyError('CyberTodoPunk', e.message);
        }
    }

    _launch() {
        const app = Gio.DesktopAppInfo.new(APP_ID);
        if (app)
            app.launch([], global.create_app_launch_context(0, -1));
    }

    destroy() {
        this._destroyed = true;
        if (this._timer) {
            GLib.source_remove(this._timer);
            this._timer = 0;
        }
        super.destroy();
    }
});

export default class CyberTodoPunkExtension extends Extension {
    enable() {
        this._indicator = new Indicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
