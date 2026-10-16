#!/usr/bin/env bash
# MODULE:    run_nested_shell.sh
# AUTHOR(S): Yann Chemin
# PURPOSE:   Smoke-test the CyberTodoPunk GNOME Shell extension and window in a
#            throwaway headless gnome-shell, without touching the desktop
#            session and without leaving any process behind.
# SPDX-License-Identifier: Unlicense
#
# Usage: tests/shell/run_nested_shell.sh [OUTDIR]
#
# Adapted from MetaMonitor's harness (https://github.com/YannChemin/MetaMonitor):
# gnome-shell --headless on its own private D-Bus session bus, with throwaway
# XDG/HOME directories holding a few sample reports. Checks that the TODO
# indicator is in the top bar with the right count, that its menu opens and
# a report unrolls, that DONE writes the completion time into ACTIONS.tex and
# that the company switch is saved; then opens the window. Screenshots
# (menu.png, window-tasks.png, window-settings.png) and logs go to OUTDIR (default: a temporary
# directory, printed at the end). Exit status 0 when every check passes.
#
# A no-op ibus-daemon is put first on PATH: on a private bus gnome-shell
# starts its own, which survives the test, spins and grows without bound.

set -uo pipefail

if [[ "${1:-}" == "--inner" ]]; then
    shift
    WORK=$1
    OUT=$2
    EXT=$3
    HELPER=$4
    TOP=$5
    printf '%s\n' "$DBUS_SESSION_BUS_ADDRESS" > "$WORK/bus"
    export XDG_DATA_HOME=$WORK/data XDG_CONFIG_HOME=$WORK/config \
        XDG_CACHE_HOME=$WORK/cache HOME=$WORK/home GSETTINGS_BACKEND=keyfile
    export PATH="$WORK/stub:$PATH"
    gsettings set org.gnome.shell disable-user-extensions false
    gsettings set org.gnome.shell enabled-extensions "['$EXT', '$HELPER']"
    gsettings set org.gnome.shell welcome-dialog-last-shown-version '999'
    DISPLAY_NAME=ctp-test-$$
    gnome-shell --headless --virtual-monitor 1400x900 --wayland-display "$DISPLAY_NAME" \
        > "$OUT/shell.log" 2>&1 &
    shell=$!
    trap 'kill "$shell" 2>/dev/null; wait "$shell" 2>/dev/null' EXIT

    eval_js() {
        gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
            --method org.gnome.Shell.Eval "$1" 2>&1
    }
    shot() {
        gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell/Screenshot \
            --method org.gnome.Shell.Screenshot.Screenshot false false "$OUT/$1" \
            >> "$OUT/result.txt" 2>&1
    }
    for _ in $(seq 60); do
        eval_js "1" | grep -q "^(true" && break
        kill -0 "$shell" 2>/dev/null || { echo "gnome-shell exited, see $OUT/shell.log"; exit 1; }
        sleep 1
    done
    sleep 4
    fail=0
    check() {
        local name=$1 expect=$2 got
        got=$(eval_js "$3")
        echo "$name: $got" >> "$OUT/result.txt"
        if [[ "$got" == *"$expect"* ]]; then
            echo "ok   $name"
        else
            echo "FAIL $name: $got"
            fail=1
        fi
    }
    IND="Main.panel.statusArea['$EXT']"
    check "indicator" "present" "$IND ? 'present' : 'missing'"
    check "count" '"3"' "$IND._count.text"
    check "menu" "opened" "$IND.menu.open(); 'opened'"
    sleep 2
    check "reports" "2" "$IND._groups._getMenuItems().length"
    check "unroll" "2 tasks" \
        "const s = $IND._groups._getMenuItems()[0]; s.setSubmenuShown(true); s.menu._getMenuItems().length + ' tasks'"
    sleep 1
    shot menu.png
    check "done-click" "clicked" \
        "$IND._groups._getMenuItems()[0].menu._getMenuItems()[0].doneButton.emit('clicked', 1); 'clicked'"
    sleep 2
    if grep -q '{done}{20' "$HOME/Documents/Report/20261014_ACME_NORTHWIND/ACTIONS.tex"; then
        echo "ok   done-written"
    else
        echo "FAIL done-written"; fail=1
    fi
    check "count-after" '"2"' "$IND._count.text"
    check "switch" "switched" "$IND._switch('GLOBEX'); 'switched'"
    sleep 2
    if grep -q '"active_company": "GLOBEX"' "$XDG_CONFIG_HOME/cybertodopunk/config.json"; then
        echo "ok   switch-saved"
    else
        echo "FAIL switch-saved"; fail=1
    fi
    check "state" "true" "Main.extensionManager.lookup('$EXT')?.state === 1"
    eval_js "$IND.menu.close(); Main.overview.hide(); 1" > /dev/null

    # The window, on the test shell's display: unrolled, then the settings.
    # No settings portal on the private bus: libadwaita would wait for it.
    eval_js "$IND._switch('ACME'); 1" > /dev/null
    sleep 1
    for page in tasks settings; do
        ADW_DISABLE_PORTAL=1 WAYLAND_DISPLAY=$DISPLAY_NAME GDK_BACKEND=wayland \
            python3 "$TOP/tests/shell/window_driver.py" "$page" >> "$OUT/app.log" 2>&1 &
        app=$!
        sleep 6
        check "window-$page" "CyberTodoPunk" \
            "global.get_window_actors().map(a => a.meta_window.get_title()).join(',')"
        shot "window-$page.png"
        kill "$app" 2>/dev/null
        wait "$app" 2>/dev/null
        sleep 1
    done
    exit $fail
fi

HERE=$(cd "$(dirname "$0")" && pwd)
TOP=$(cd "$HERE/../.." && pwd)
EXT=cybertodopunk@yannchemin.github.io
# Since GNOME 45, org.gnome.Shell.Eval only answers in unsafe mode; this
# helper extension, installed only in the throwaway data directory, turns it on.
HELPER=unsafe-eval@cybertodopunk.test
for cmd in gnome-shell dbus-run-session gdbus gsettings; do
    command -v "$cmd" >/dev/null || { echo "$cmd not found, skipping"; exit 77; }
done

WORK=$(mktemp -d "${TMPDIR:-/tmp}/ctp-shelltest.XXXXXX")
OUT=${1:-$WORK/out}
mkdir -p "$OUT" "$WORK/data/gnome-shell/extensions" "$WORK/config" "$WORK/cache" \
    "$WORK/home/Documents" "$WORK/stub"
OUT=$(cd "$OUT" && pwd)
: > "$OUT/result.txt"
cp -r "$TOP/gnome-shell/$EXT" "$WORK/data/gnome-shell/extensions/"
mkdir -p "$WORK/data/gnome-shell/extensions/$HELPER"
cat > "$WORK/data/gnome-shell/extensions/$HELPER/metadata.json" <<META
{"uuid": "$HELPER", "name": "Test helper",
 "description": "Unsafe mode for the CyberTodoPunk shell test",
 "shell-version": ["45", "46", "47", "48", "49"]}
META
cat > "$WORK/data/gnome-shell/extensions/$HELPER/extension.js" <<'JS'
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class UnsafeEval extends Extension {
    enable() {
        global.context.unsafe_mode = true;
    }

    disable() {
        global.context.unsafe_mode = false;
    }
}
JS
printf '#!/bin/sh\n# No input method in the test shell.\nexit 0\n' > "$WORK/stub/ibus-daemon"
printf '#!/bin/sh\nexec python3 %q "$@"\n' "$TOP/bin/cybertodopunk" > "$WORK/stub/cybertodopunk"
chmod +x "$WORK/stub/ibus-daemon" "$WORK/stub/cybertodopunk"

# Sample reports and settings (3 open ACME actions for DOE in 2 reports).
HOME=$WORK/home XDG_CONFIG_HOME=$WORK/config PYTHONPATH=$TOP python3 - <<'PY'
from pathlib import Path
from cybertodopunk import actions as act, config as conf
root = Path.home() / "Documents" / "Report"
A = act.Action
reports = {
    "20261014_ACME_NORTHWIND": [
        A("A01", "ACME --- DOE", "--", "todo", "",
          "Write the summary note and the list of open questions"),
        A("A02", "ACME --- SMITH", "--", "todo", "", "Estimate the budget of the next phase"),
        A("A03", "ACME --- DOE", "14/10", "inprogress", "", "Prepare the demo"),
    ],
    "20261013_ACME_INITECH": [
        A("A01", "ACME --- DOE", "19/10", "todo", "", "Send the technical note to INITECH"),
        A("A02", "ACME --- DOE", "--", "done", "2026-10-15 10:00", "Share the minutes"),
    ],
    "20261014_GLOBEX_Summit_Bilaterals/meetings/D2-04_Partner": [
        A("A01", "GLOBEX — DOE", "--", "todo", "", "Book the room for the next review."),
    ],
}
for d, items in reports.items():
    (root / d).mkdir(parents=True)
    act.write_new(root / d / act.FILENAME, items)
conf.save(conf.Config(full_name="Jane DOE", companies=["ACME", "GLOBEX"], active_company="ACME"))
PY

cleanup() {
    # Kill whatever is still attached to the test's private bus.
    if [[ -s "$WORK/bus" ]]; then
        local bus pid
        bus=$(<"$WORK/bus")
        for pid in $(pgrep -u "$(id -u)"); do
            if { tr '\0' '\n' < "/proc/$pid/environ"; } 2>/dev/null |
                grep -qxF "DBUS_SESSION_BUS_ADDRESS=$bus"; then
                kill -TERM "$pid" 2>/dev/null
            fi
        done
        sleep 1
        for pid in $(pgrep -u "$(id -u)"); do
            if { tr '\0' '\n' < "/proc/$pid/environ"; } 2>/dev/null |
                grep -qxF "DBUS_SESSION_BUS_ADDRESS=$bus"; then
                echo "killing leftover $(ps -o comm= -p "$pid") ($pid)"
                kill -KILL "$pid" 2>/dev/null
            fi
        done
    fi
    rm -rf "$WORK/data" "$WORK/config" "$WORK/cache" "$WORK/home" "$WORK/stub"
}
trap cleanup EXIT

dbus-run-session -- "$0" --inner "$WORK" "$OUT" "$EXT" "$HELPER" "$TOP" 2> "$OUT/session.log"
status=$?
echo "Results and screenshots: $OUT"
exit $status
