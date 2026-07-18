# SPDX-License-Identifier: MIT
"""verify/drivers/highlight_driver.py -- GUI checks for the active-tool
highlight and the navigation-style application.

Run inside the FreeCAD GUI (a window flashes open); from the repo root with
the generic runner:

    freecad.exe verify/run_gui.py            # paths via GUI_DRIVER/GUI_LOG env

What it asserts, for real, against the installed addon (sync the repo's
``freecad/`` tree into the Mod copy first -- the runner used for the
2026-07-18 verification did):

1. Per-view consent mode switches EVERY open 3D view to the Blender style
   (``getNavigationType()``), and a view created afterwards is switched too
   (the QMdiArea keep-applied hook).
2. Arming a tool (SketchLayer_Line via ``Gui.runCommand``, exactly what the
   toolbar button runs) makes its QAction checked while the others stay
   unchecked; Esc clears it; starting Circle while Line runs moves the
   highlight (radio); a typed rectangle commit clears it; the armed Eraser
   highlights and Esc disarms; Select highlights as the neutral tool; a
   one-shot command (Fit All) never lights.
3. "Everywhere" mode writes the global preference and the menu restore
   reverts it (and the views) to the recorded prior value.

The consent state is set programmatically (no modal dialog), and the user's
Uppercut parameters plus the global NavigationStyle preference are restored
afterwards (to the FRESH state: consent un-asked, so the next real GUI
start shows the three-way dialog once).

Result is printed and written to
``verify/out/highlight_driver.result.txt`` (grep that file; GUI startup
scripts do not reliably propagate process exit codes).
"""
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_OUT_DIR = os.path.join(_REPO_ROOT, "verify", "out")

import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide import QtCore, QtGui, QtWidgets  # noqa: E402

from freecad.UppercutWB import assembly, navstyle, toolstate  # noqa: E402

_ADAPTER = toolstate.QtActionAdapter()


def pump(n=6):
    app = QtWidgets.QApplication.instance()
    for _ in range(n):
        app.processEvents()
    try:
        Gui.updateGui()
    except Exception:
        pass


def send_key(key, text=""):
    """The ShortcutOverride + KeyPress pair a real keypress produces, through
    the application-level event filters (same idiom as draw_commit_driver)."""
    mw = Gui.getMainWindow()
    override = QtGui.QKeyEvent(QtCore.QEvent.ShortcutOverride, key,
                               QtCore.Qt.NoModifier, text)
    QtWidgets.QApplication.sendEvent(mw, override)
    press = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key,
                            QtCore.Qt.NoModifier, text)
    QtWidgets.QApplication.sendEvent(mw, press)
    pump()


def actions_of(name):
    acts = _ADAPTER.find_actions(name)
    assert acts, "no toolbar action found for %s" % name
    return acts


def checked(name):
    return all(a.isChecked() for a in actions_of(name))


def unchecked(name):
    return not any(a.isChecked() for a in actions_of(name))


def views3d(doc_name):
    return Gui.getDocument(doc_name).mdiViewsOfType(navstyle.VIEW3D_TYPE)


def check_nav_all_blender(doc_name, context):
    styles = [v.getNavigationType() for v in views3d(doc_name)]
    assert styles and all(s == navstyle.UPPERCUT_STYLE for s in styles), \
        "%s: nav styles = %r" % (context, styles)
    print("       nav styles %s: %r" % (context, styles))


_RESULTS = []
_CHECKS = []


def check(name):
    def deco(fn):
        _CHECKS.append((name, fn))
        return fn
    return deco


def run_checks(fx):
    for name, fn in _CHECKS:
        try:
            fn(fx)
        except Exception:  # noqa: BLE001 - record and continue
            _RESULTS.append((name, False, traceback.format_exc()))
            print("[FAIL] %s\n%s" % (name, _RESULTS[-1][2]))
        else:
            _RESULTS.append((name, True, ""))
            print("[ ok ] %s" % name)


@check("per-view consent switches the active view to the Blender style")
def g01(fx):
    check_nav_all_blender(fx.doc_name, "after workbench activation")


@check("a view created afterwards is switched too (keep-applied hook)")
def g02(fx):
    gdoc = Gui.getDocument(fx.doc_name)
    before = len(views3d(fx.doc_name))
    gdoc.createView(navstyle.VIEW3D_TYPE)
    pump(10)
    assert len(views3d(fx.doc_name)) == before + 1, "second view not created"
    check_nav_all_blender(fx.doc_name, "after createView")


@check("the adapter finds every tool's action by its command name")
def g03(fx):
    for name in ("SketchLayer_Line", "SketchLayer_Circle", "Uppercut_Eraser",
                 "Uppercut_Select", "PushPull_PushPull"):
        actions_of(name)
        print("       action found: %s" % name)


@check("arming Line checks its button, and only its button")
def g04(fx):
    Gui.runCommand("SketchLayer_Line")
    pump()
    assert toolstate.active() == "SketchLayer_Line", \
        "active() = %r" % toolstate.active()
    assert checked("SketchLayer_Line"), "Line button not checked"
    for other in ("SketchLayer_Rectangle", "SketchLayer_Circle",
                  "SketchLayer_Polygon", "SketchLayer_Arc", "Uppercut_Eraser"):
        assert unchecked(other), "%s should not be checked" % other
    fx.session = sys.modules["freecad.SketchLayerWB.commands"].\
        _LineCommand._session
    assert fx.session is not None and fx.session.controller.active, \
        "no live Line session"


@check("Esc clears the highlight (and cancels the session)")
def g05(fx):
    send_key(QtCore.Qt.Key_Escape)
    assert toolstate.active() is None, "active() = %r" % toolstate.active()
    assert unchecked("SketchLayer_Line"), "Line still checked after Esc"
    assert not fx.session.controller.active, "Line session still active"


@check("radio: starting Circle while Line runs moves the highlight")
def g06(fx):
    Gui.runCommand("SketchLayer_Line")
    pump()
    assert checked("SketchLayer_Line"), "Line not armed for the radio test"
    Gui.runCommand("SketchLayer_Circle")
    pump()
    assert toolstate.active() == "SketchLayer_Circle", \
        "active() = %r" % toolstate.active()
    assert checked("SketchLayer_Circle"), "Circle button not checked"
    assert unchecked("SketchLayer_Line"), "Line should have cleared (radio)"
    send_key(QtCore.Qt.Key_Escape)
    assert unchecked("SketchLayer_Circle") and toolstate.active() is None, \
        "Circle did not clear on Esc"


@check("a typed rectangle commit clears the highlight")
def g07(fx):
    Gui.runCommand("SketchLayer_Rectangle")
    pump()
    assert checked("SketchLayer_Rectangle"), "Rectangle button not checked"
    session = sys.modules["freecad.SketchLayerWB.commands"].\
        _RectangleCommand._session
    ctl = session.controller
    assert ctl.add_point(App.Vector(0, 0, 0)) is None, "first corner finished?!"
    ctl.move_to(App.Vector(5, 5, 0))
    keys = {"3": QtCore.Qt.Key_3, "0": QtCore.Qt.Key_0,
            ",": QtCore.Qt.Key_Comma, "2": QtCore.Qt.Key_2}
    for ch in "30,20":
        send_key(keys[ch], ch)
    assert ctl.typed_buffer == "30,20", "typed_buffer = %r" % ctl.typed_buffer
    send_key(QtCore.Qt.Key_Return, "\r")
    obj = ctl.committed_object
    assert obj is not None and abs(obj.Shape.Area - 600.0) < 1e-6, \
        "rectangle did not commit: %s" % ctl.last_message
    assert toolstate.active() is None, "active() = %r" % toolstate.active()
    assert unchecked("SketchLayer_Rectangle"), "Rectangle still checked"


@check("the armed Eraser highlights; Esc disarms and clears")
def g08(fx):
    Gui.Selection.clearSelection()
    Gui.runCommand("Uppercut_Eraser")
    pump()
    assert toolstate.active() == "Uppercut_Eraser", \
        "active() = %r" % toolstate.active()
    assert checked("Uppercut_Eraser"), "Eraser button not checked while armed"
    send_key(QtCore.Qt.Key_Escape)
    assert toolstate.active() is None, "active() = %r" % toolstate.active()
    assert unchecked("Uppercut_Eraser"), "Eraser still checked after Esc"


@check("Select highlights as the neutral tool; one-shots never light")
def g09(fx):
    Gui.runCommand("Uppercut_Select")
    pump()
    assert toolstate.active() == assembly.CMD_SELECT, \
        "active() = %r" % toolstate.active()
    assert checked("Uppercut_Select"), "Select button not checked"
    Gui.runCommand("Uppercut_ViewFitAll")
    pump()
    assert unchecked("Uppercut_ViewFitAll"), "a one-shot command lit up"
    assert checked("Uppercut_Select"), \
        "a one-shot command disturbed the radio state"


@check("'everywhere' writes the global preference; the menu restore reverts it")
def g10(fx):
    pref = navstyle.pref_params()
    original = fx.original_pref
    navstyle.apply_global_style(Gui)
    assert pref.GetString(navstyle.PREF_KEY, "") == navstyle.UPPERCUT_STYLE, \
        "global preference not written"
    state = navstyle.load_state()
    assert state["global_applied"] and state["saved_global_style"] == original, \
        "prior global value not recorded: %r" % (state,)
    check_nav_all_blender(fx.doc_name, "while 'everywhere' is on")
    result = navstyle.restore_navigation(Gui)
    assert result == "restored", "restore_navigation = %r" % result
    assert pref.GetString(navstyle.PREF_KEY, "") == original, \
        "global preference not reverted"
    styles = [v.getNavigationType() for v in views3d(fx.doc_name)]
    assert all(s == original for s in styles), \
        "views not reverted: %r" % (styles,)
    print("       global preference reverted to %r; views: %r"
          % (original, styles))


def main():
    os.makedirs(_OUT_DIR, exist_ok=True)
    print("toolstate module: %s" % toolstate.__file__)
    print("navstyle module: %s" % navstyle.__file__)

    p = navstyle.params()
    pref = navstyle.pref_params()
    original_pref = pref.GetString(navstyle.PREF_KEY, "")

    fx = type("Fx", (), {})()
    fx.original_pref = original_pref

    try:
        # consent answered programmatically (per-view mode): no modal dialog
        navstyle.store_consent(navstyle.CONSENT_VIEW)
        doc = App.newDocument("HighlightVerify")
        App.setActiveDocument(doc.Name)
        fx.doc_name = doc.Name
        # force a real Activated() even if Uppercut was the startup workbench
        Gui.activateWorkbench("PartDesignWorkbench")
        pump()
        Gui.activateWorkbench("UppercutWorkbench")
        pump()
        assert Gui.activeWorkbench().__class__.__name__ == "UppercutWorkbench", \
            "Uppercut workbench did not activate"

        run_checks(fx)
    finally:
        # leave the machine in the FRESH state: consent un-asked, nothing
        # applied, the user's global preference untouched -- the next real
        # GUI start shows the three-way consent dialog once.
        try:
            navstyle.unwatch_views()
        except Exception:  # noqa: BLE001
            pass
        p.SetBool("NavConsentAsked", False)
        p.SetBool("NavConsent", False)
        p.SetString("NavConsentMode", "")
        p.SetBool("NavApplied", False)
        p.SetString("NavSavedStyle", "")
        p.SetString("NavSavedVia", "")
        p.SetBool("NavGlobalApplied", False)
        p.SetString("NavSavedGlobalStyle", "")
        pref.SetString(navstyle.PREF_KEY, original_pref)
        try:
            App.closeDocument(fx.doc_name)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    status, detail = "PASS", ""
    try:
        main()
    except Exception:  # noqa: BLE001
        status, detail = "FAIL", traceback.format_exc()
        print(detail)
    failed = [name for name, ok_, _tb in _RESULTS if not ok_]
    if failed:
        status = "FAIL"
        detail = "failed checks: %s\n%s" % (
            ", ".join(failed),
            "\n".join(tb for _n, ok_, tb in _RESULTS if not ok_))
    print("-" * 64)
    print("highlight_driver: %d/%d checks pass" % (
        len(_RESULTS) - len(failed), len(_RESULTS)))
    os.makedirs(_OUT_DIR, exist_ok=True)
    with open(os.path.join(_OUT_DIR, "highlight_driver.result.txt"), "w") as fh:
        fh.write("%s\n%s" % (status, detail))
    print("highlight_driver: %s" % status)
    QtCore.QTimer.singleShot(0, QtWidgets.QApplication.instance().quit)
    if status != "PASS":
        sys.exit(1)
