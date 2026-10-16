# CyberTodoPunk build and install.
#
# Per-user install (default): make install
# System/packaging install:  make install PREFIX=/usr DESTDIR=debian/cybertodopunk
# Debian package into dist/: make deb
#
# SPDX-License-Identifier: Unlicense

PREFIX ?= $(HOME)/.local
DESTDIR ?=
BINDIR = $(PREFIX)/bin
LIBDIR = $(PREFIX)/share/cybertodopunk
APPDIR = $(PREFIX)/share/applications
MANDIR = $(PREFIX)/share/man/man1
METADIR = $(PREFIX)/share/metainfo
ICONDIR = $(PREFIX)/share/icons/hicolor
EXTUUID = cybertodopunk@yannchemin.github.io
EXTDIR = $(PREFIX)/share/gnome-shell/extensions/$(EXTUUID)
APP_ID = io.github.yannchemin.CyberTodoPunk
VERSION = $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' cybertodopunk/__init__.py)
PYTHON ?= python3

.PHONY: all test shell-test run install uninstall deb clean

all:

test:
	$(PYTHON) -m pytest -q tests

# The top-bar extension in a throwaway headless gnome-shell (private D-Bus,
# temporary XDG dirs, no input method). Screenshot and results in OUT.
shell-test:
	tests/shell/run_nested_shell.sh $(OUT)

run:
	./bin/cybertodopunk

install:
	install -d $(DESTDIR)$(LIBDIR)/cybertodopunk/ui $(DESTDIR)$(LIBDIR)/bin \
		$(DESTDIR)$(LIBDIR)/latex $(DESTDIR)$(BINDIR) $(DESTDIR)$(APPDIR) \
		$(DESTDIR)$(MANDIR) $(DESTDIR)$(METADIR)
	install -m 644 cybertodopunk/*.py $(DESTDIR)$(LIBDIR)/cybertodopunk/
	install -m 644 cybertodopunk/ui/*.py cybertodopunk/ui/style.css $(DESTDIR)$(LIBDIR)/cybertodopunk/ui/
	install -m 755 bin/cybertodopunk $(DESTDIR)$(LIBDIR)/bin/
	ln -sfr $(DESTDIR)$(LIBDIR)/bin/cybertodopunk $(DESTDIR)$(BINDIR)/cybertodopunk
	install -m 644 latex/ACTIONS-TEMPLATE.tex $(DESTDIR)$(LIBDIR)/latex/
	sed 's|@BINDIR@/||g' data/$(APP_ID).desktop > $(DESTDIR)$(APPDIR)/$(APP_ID).desktop
	install -m 644 data/$(APP_ID).metainfo.xml $(DESTDIR)$(METADIR)/
	install -m 644 data/cybertodopunk.1 $(DESTDIR)$(MANDIR)/
	install -d $(DESTDIR)$(LIBDIR)/data/fonts $(DESTDIR)$(ICONDIR)/scalable/apps \
		$(DESTDIR)$(ICONDIR)/symbolic/apps $(DESTDIR)$(EXTDIR)/icons
	install -m 644 data/fonts/*.ttf data/fonts/OFL-*.txt $(DESTDIR)$(LIBDIR)/data/fonts/
	install -m 644 data/icons/hicolor/scalable/apps/$(APP_ID).svg $(DESTDIR)$(ICONDIR)/scalable/apps/
	install -m 644 data/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg $(DESTDIR)$(ICONDIR)/symbolic/apps/
	install -m 644 gnome-shell/$(EXTUUID)/metadata.json gnome-shell/$(EXTUUID)/extension.js \
		gnome-shell/$(EXTUUID)/stylesheet.css $(DESTDIR)$(EXTDIR)/
	install -m 644 gnome-shell/$(EXTUUID)/icons/*.svg $(DESTDIR)$(EXTDIR)/icons/
ifeq ($(DESTDIR),)
	-gtk-update-icon-cache -q -t $(ICONDIR) 2>/dev/null
endif

uninstall:
	rm -rf $(DESTDIR)$(EXTDIR) $(DESTDIR)$(LIBDIR)
	rm -f $(DESTDIR)$(ICONDIR)/scalable/apps/$(APP_ID).svg $(DESTDIR)$(ICONDIR)/symbolic/apps/$(APP_ID)-symbolic.svg
	rm -f $(DESTDIR)$(BINDIR)/cybertodopunk $(DESTDIR)$(MANDIR)/cybertodopunk.1
	rm -f $(DESTDIR)$(APPDIR)/$(APP_ID).desktop $(DESTDIR)$(METADIR)/$(APP_ID).metainfo.xml

# Binary package into dist/ (dpkg-buildpackage writes to the parent directory).
# The version comes from debian/changelog; keep it equal to __version__.
deb:
	@test "$$(dpkg-parsechangelog -S Version)" = "$(VERSION)" || \
		{ echo "debian/changelog version differs from __version__ $(VERSION)"; exit 1; }
	dpkg-buildpackage -us -uc -b
	mkdir -p dist
	mv ../cybertodopunk_$(VERSION)_*.deb ../cybertodopunk_$(VERSION)_*.buildinfo \
		../cybertodopunk_$(VERSION)_*.changes dist/

clean:
	find . -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache debian/cybertodopunk debian/.debhelper debian/files \
		debian/*.substvars debian/*.debhelper.log debian/debhelper-build-stamp
