# SPDX-License-Identifier: MIT
"""Uppercut dialogs (GUI-only): the navigation consent prompt and the
About/companions dialog. Imported lazily from init_gui/commands so nothing
here loads at FreeCAD startup.
"""
import FreeCAD as App

from . import assembly

_VERSION = "0.4.0"

_CONSENT_TEXT = (
    "Use SketchUp-style navigation? (middle-mouse orbit, Shift+middle pan, "
    "wheel zoom)\n\n"
    "This workbench only: switch the open 3D views; your previous style is "
    "restored when you leave the workbench or via Uppercut menu > Restore "
    "navigation.\n\n"
    "Everywhere: also write FreeCAD's global navigation preference, so every "
    "workbench and every new view orbits on middle-mouse hold. Restore "
    "navigation reverts it (your previous global setting is remembered)."
)


def ask_navigation_consent():
    """The one-time consent dialog. Returns the chosen mode:
    navstyle.CONSENT_VIEW (default), navstyle.CONSENT_GLOBAL ("everywhere")
    or navstyle.CONSENT_NONE."""
    from PySide import QtWidgets

    from . import navstyle

    box = QtWidgets.QMessageBox()
    box.setWindowTitle("Uppercut")
    box.setIcon(QtWidgets.QMessageBox.Question)
    box.setText(_CONSENT_TEXT)
    view_btn = box.addButton("This workbench only",
                             QtWidgets.QMessageBox.AcceptRole)
    global_btn = box.addButton("Everywhere",
                               QtWidgets.QMessageBox.AcceptRole)
    box.addButton("No thanks", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(view_btn)
    box.exec_()
    clicked = box.clickedButton()
    if clicked is global_btn:
        return navstyle.CONSENT_GLOBAL
    if clicked is view_btn:
        return navstyle.CONSENT_VIEW
    return navstyle.CONSENT_NONE


def show_about(available):
    """About/companions: version, and which siblings were found or are missing.

    With missing companions the box grows an "Install missing..." button
    that opens the one-click installer dialog."""
    from PySide import QtWidgets

    found, missing = assembly.companions_report(available)
    lines = ["Uppercut %s, running on FreeCAD %s." % (
        _VERSION, ".".join(App.Version()[0:3]))]
    lines.append("")
    lines.append("Companion addons:")
    for sib in found:
        lines.append("  found: %s (%s)" % (sib.title, sib.provides))
    for sib in missing:
        lines.append("  MISSING: %s (%s). To get its buttons: %s."
                     % (sib.title, sib.provides, sib.install_hint))
    if not missing:
        lines.append("  All companions installed.")
    lines.append("")
    lines.append("Navigation: with 'This workbench only', your previous style "
                 "is restored when you leave the workbench, or via Uppercut "
                 "menu > Restore navigation. With 'Everywhere', the global "
                 "preference stays on SketchUp-style until Restore navigation "
                 "reverts it.")
    box = QtWidgets.QMessageBox()
    box.setWindowTitle("About Uppercut")
    box.setIcon(QtWidgets.QMessageBox.Information)
    box.setText("\n".join(lines))
    install_btn = None
    if missing:
        install_btn = box.addButton("Install missing...",
                                    QtWidgets.QMessageBox.ActionRole)
    box.addButton(QtWidgets.QMessageBox.Close)
    box.exec_()
    if install_btn is not None and box.clickedButton() is install_btn:
        show_companion_install(missing)


class CompanionInstallDialog(object):
    """One-click installer for the missing companion addons.

    Thin PySide layer over companion_install.py: a checkbox per missing
    companion (all checked), the exact pinned URL each one downloads from,
    a per-item status line, and a restart note. Installs run sequentially
    on the GUI thread with processEvents-driven progress (no worker
    threads, no retries); a failed companion shows its error text and the
    rest continue.
    """

    def __init__(self, missing):
        from PySide import QtWidgets

        from . import companion_install

        self._install = companion_install
        self._qt = QtWidgets
        self._missing = list(missing)
        self._rows = []  # (sibling, checkbox, status_label)

        self.dialog = QtWidgets.QDialog()
        self.dialog.setWindowTitle("Install missing companions")
        layout = QtWidgets.QVBoxLayout(self.dialog)

        intro = QtWidgets.QLabel(
            "These companion addons were not detected. Checked ones are "
            "downloaded from the pinned github.com/mathmati addresses below "
            "and unpacked into your FreeCAD Mod folder.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        for sib in self._missing:
            checkbox = QtWidgets.QCheckBox(
                "%s (%s)" % (sib.title, sib.provides))
            checkbox.setChecked(True)
            layout.addWidget(checkbox)
            url_label = QtWidgets.QLabel(
                "    from %s" % companion_install.zip_url(sib))
            url_label.setWordWrap(True)
            layout.addWidget(url_label)
            status = QtWidgets.QLabel("    not installed yet")
            status.setWordWrap(True)
            layout.addWidget(status)
            self._rows.append((sib, checkbox, status))

        note = QtWidgets.QLabel(
            "After installing, restart FreeCAD so the new addons load; "
            "their buttons then appear on the Uppercut toolbar.")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.install_button = QtWidgets.QPushButton("Install checked")
        self.install_button.clicked.connect(self._on_install)
        buttons.addWidget(self.install_button)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.dialog.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _process_events(self):
        app = self._qt.QApplication.instance()
        if app is not None:
            app.processEvents()

    def _on_install(self):
        self.install_button.setEnabled(False)
        status_by_key = {}
        chosen = []
        for sib, checkbox, status in self._rows:
            checkbox.setEnabled(False)
            if checkbox.isChecked():
                chosen.append(sib)
                status_by_key[sib.key] = status
            else:
                status.setText("    unchecked, left as is")
        self._process_events()

        def progress(sib, phase):
            status = status_by_key.get(sib.key)
            if status is None:
                return
            if phase == "start":
                status.setText("    downloading...")
            elif phase["status"] == "installed":
                status.setText("    installed into %s" % phase["target"])
            elif phase["status"] == "skipped":
                status.setText("    already present at %s, not overwritten"
                               % phase["target"])
            else:
                status.setText("    FAILED: %s (still missing; try the "
                               "Addon Manager instead)" % phase["error"])
            self._process_events()

        mod_dir = self._install.mod_directory(App.getUserAppDataDir())
        results = self._install.install_missing(chosen, mod_dir,
                                                progress=progress)
        installed = [r for r in results if r["status"] == "installed"]
        if installed:
            self._qt.QMessageBox.information(
                self.dialog, "Uppercut",
                "Installed %d companion(s). Please restart FreeCAD to load "
                "them." % len(installed))

    def exec_(self):
        return self.dialog.exec_()


def show_companion_install(missing=None):
    """Open the companion installer. ``missing``: Sibling list; when None it
    is detected here (static check; no command manager needed)."""
    if missing is None:
        available = assembly.detect_availability()
        _found, missing = assembly.companions_report(available)
    if not missing:
        from PySide import QtWidgets

        QtWidgets.QMessageBox.information(
            None, "Uppercut", "All companion addons are already installed.")
        return
    CompanionInstallDialog(missing).exec_()
