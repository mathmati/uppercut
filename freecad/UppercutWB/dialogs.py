# SPDX-License-Identifier: MIT
"""Uppercut dialogs (GUI-only): the navigation consent prompt and the
About/companions dialog. Imported lazily from init_gui/commands so nothing
here loads at FreeCAD startup.
"""
import FreeCAD as App

from . import assembly

_VERSION = "0.1.0"

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
    """About/companions: version, and which siblings were found or are missing."""
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
    QtWidgets.QMessageBox.information(None, "About Uppercut", "\n".join(lines))
