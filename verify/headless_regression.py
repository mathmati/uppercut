# SPDX-License-Identifier: MIT
"""verify/headless_regression.py -- Uppercut headless regression (freecadcmd).

Run from the repo root (see the wrapper in the README; plain
``freecadcmd verify/headless_regression.py`` also works when invoked so that
``__name__ == "__main__"``). Exit code 0 and a final "36/36 checks pass"
line when green.

What is covered (the GUI itself is not; freecadcmd has no command manager,
so buttons, dialogs and probing through Gui.Command are out of scope here):

   assembly      1-8   toolbar ordering (Offset/FollowMe right after
                       Push/Pull, Make Group after Eraser), omission of
                       missing siblings, Move/Rotate + Tape Measure + view
                       probe logic, separator hygiene
   static xref   9     every sibling command name in assembly.SIBLINGS appears
                       as addCommand("<name>" in the sibling sources'
                       commands.py (SketchLayer, Offset and FollowMe: the
                       Kimchi build trees; the other siblings: the read-only
                       review clones; skips with a warning if a source is
                       absent)
   detection     10-11 detect_availability via the live lookup and via the
                       static source fallback against the real sources
   eraser        12-14 transaction delete on a real document, undo restores,
                       empty selection is a no-op
   paint         15-16 build_rgba palette/tuple/validation paths
   navstyle      17-19 Uppercut parameter round-trip, view-API probe order
                       (setNavigationType first, setNavigationStyle fallback),
                       Preferences/View NavigationStyle round-trip
   icons         20    every own command maps to a distinct SVG that exists
                       in Resources/Icons; workbench icon untouched
   assembly      21    an older SketchLayer (Line/Rectangle only) still
                       degrades cleanly against the expanded 5-command spec
   shortcuts     22-24 SketchUp letter-map completeness and cross-check
                       against the assembly command names, conflict-skip and
                       unavailable-skip logic with fake owners, shortcut
                       parameter round-trip
   make group    25    two boxes into one App::Part, undo restores, empty
                       selection no-op
   eraser armed  26    EraserSession arm/disarm/toggle, delete_picked only
                       acts while armed, session stays armed after a delete
   offset/follow 27-28 toolbar slots right after Push/Pull with each sibling
                       optional, sibling icon path resolution through the
                       package locator (None + uppercut_missing.svg fallback
                       when absent)
   shortcuts     29    gui_accel_owner conflict table from a fake command
                       manager (case-insensitive, broken entries skipped,
                       dead manager -> empty table)
   toolstate     30-31 radio tracker with a recording fake adapter (radio
                       clear, re-assert, inactive rules, clear_all, adapter
                       failures swallowed), Qt button-lookup adapter with
                       fake actions/toolbars (data() and objectName()
                       matching, checkable-once, unknown command no-op)
   wiring        32    toolstate call sites in commands.py / init_gui.py
                       (static xref: eraser arm/disarm, Select, restore
                       command, nav watcher attach/detach)
   navstyle      33-36 "everywhere" global preference write + restore with
                       real parameters (prior value recorded, idempotent,
                       exact restore), consent mode state machine incl.
                       legacy-boolean migration, apply/restore across ALL
                       open views with fake gui/views, watcher decision +
                       reapply logic
"""
import os
import sys
import traceback

# --- make the workbench importable from a source checkout ------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
try:
    import freecad  # FreeCAD's own namespace package (present under freecadcmd)
    freecad.__path__ = [os.path.join(_REPO_ROOT, "freecad")] + list(freecad.__path__)
except ImportError:  # extremely defensive: fall back to plain sys.path
    sys.path.insert(0, _REPO_ROOT)

# freecadcmd imports installed Mod addons at startup; if an UppercutWB copy is
# installed, freecad.UppercutWB is then already in sys.modules and the repo
# path prepend above would be ignored. Drop the cached package (and any stale
# pre-rename freecad.SketchUIWB) so the checks always run against THIS
# checkout.
for _mod in list(sys.modules):
    if _mod == "freecad.UppercutWB" or _mod.startswith("freecad.UppercutWB.") \
            or _mod == "freecad.SketchUIWB" \
            or _mod.startswith("freecad.SketchUIWB."):
        del sys.modules[_mod]

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402  # makes Part::Box creatable

from freecad.UppercutWB import (assembly, eraser, group, navstyle, paint,  # noqa: E402
                                shortcuts, toolstate)

EXPECTED_CHECKS = 36

_checks = []

SEP = assembly.SEPARATOR
ALL_SIBLING_COMMANDS = [c for sib in assembly.SIBLINGS for c in sib.commands]
FULL_HOUSE = set(ALL_SIBLING_COMMANDS) | set(assembly.STD_PROBE_COMMANDS)
SKETCHLAYER_COMMANDS = [c for c in ALL_SIBLING_COMMANDS
                        if c.startswith("SketchLayer_")]

#: Read-only review clones of the sibling addons (skip with warning if absent).
_CLONE_ROOT = os.path.expanduser(os.path.join("~", ".cache", "kimi-reviews"))
_CLONE_DIRS = {
    "sketchlayer": ("FreeCAD-SketchLayer", "SketchLayerWB"),
    "pushpull": ("FreeCAD-PushPull", "PushPullWB"),
    "offset": ("FreeCAD-Offset", "OffsetToolWB"),
    "followme": ("FreeCAD-FollowMe", "FollowMeWB"),
    "sitecontext": ("FreeCAD-SiteContext", "SiteContextWB"),
    "migrationguide": ("FreeCAD-Migration-Guide", "MigrationGuideWB"),
}

#: Siblings under active development in the Kimchi build tree (the review
#: clones only carry the released state; SketchLayer's clone predates the
#: Circle/Polygon/Arc commands, and Offset/FollowMe have no clones at all),
#: so the build tree is the xref source of truth for these when present.
_BUILD_ROOT = os.path.expanduser(os.path.join(
    "~", "OneDrive", "Documents", "Kimchi", "build"))
_BUILD_COMMANDS_PY = {
    "sketchlayer": ("FreeCAD-SketchLayer", "SketchLayerWB"),
    "offset": ("FreeCAD-Offset", "OffsetToolWB"),
    "followme": ("FreeCAD-FollowMe", "FollowMeWB"),
}


def _clone_commands_py(key):
    build = _BUILD_COMMANDS_PY.get(key)
    if build:
        path = os.path.join(_BUILD_ROOT, build[0], "freecad", build[1],
                            "commands.py")
        if os.path.isfile(path):
            return path
    repo, pkgdir = _CLONE_DIRS[key]
    return os.path.join(_CLONE_ROOT, repo, "freecad", pkgdir, "commands.py")


def _clones_present():
    return all(os.path.isfile(_clone_commands_py(k)) for k in _CLONE_DIRS)


def check(name):
    def deco(fn):
        _checks.append((name, fn))
        return fn
    return deco


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def expect_raises(exc_type, fn, msg):
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(msg)


# --- 1-8: toolbar assembly ----------------------------------------------------
@check("assembly: full house produces the exact toolbar order")
def c01(fx):
    items = assembly.build_toolbar(FULL_HOUSE)
    ok(items == [
        assembly.CMD_SELECT,
        SEP,
        "SketchLayer_Line", "SketchLayer_Rectangle", "SketchLayer_Circle",
        "SketchLayer_Polygon", "SketchLayer_Arc",
        SEP,
        "PushPull_PushPull", "OffsetTool_Offset", "FollowMe_Sweep",
        SEP,
        assembly.CMD_MOVE_ROTATE,
        SEP,
        assembly.CMD_ERASER, assembly.CMD_MAKE_GROUP,
        SEP,
        assembly.CMD_TAPE_MEASURE,
        SEP,
        assembly.CMD_PAINT,
        SEP,
        "Uppercut_ViewIso", "Uppercut_ViewTop", "Uppercut_ViewFront",
        "Uppercut_ViewRight", "Uppercut_ViewFitAll",
        SEP,
        "SiteContext_AddLocation",
        SEP,
        "MigrationGuide_ShowPanel",
    ], "unexpected toolbar: %r" % (items,))


@check("assembly: missing SketchLayer omits its draw buttons, keeps the rest")
def c02(fx):
    avail = FULL_HOUSE - set(SKETCHLAYER_COMMANDS)
    items = assembly.build_toolbar(avail)
    ok(not any(c in items for c in SKETCHLAYER_COMMANDS),
       "SketchLayer buttons should be omitted")
    ok("PushPull_PushPull" in items and "SiteContext_AddLocation" in items
       and "MigrationGuide_ShowPanel" in items, "unrelated buttons went missing")
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["sketchlayer"], "missing = %r" % (missing,))
    notes = assembly.missing_notes(avail)
    ok(len(notes) == 1 and "SketchLayer" in notes[0]
       and "Addon Manager" in notes[0], "unexpected note: %r" % (notes,))


@check("assembly: missing PushPull omits the Push/Pull button only")
def c03(fx):
    avail = FULL_HOUSE - {"PushPull_PushPull"}
    items = assembly.build_toolbar(avail)
    ok("PushPull_PushPull" not in items, "Push/Pull button should be omitted")
    ok("SketchLayer_Line" in items and "SiteContext_AddLocation" in items,
       "unrelated buttons went missing")
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["pushpull"], "missing = %r" % (missing,))


@check("assembly: missing SiteContext omits the Add Location button only")
def c04(fx):
    avail = FULL_HOUSE - {"SiteContext_AddLocation"}
    items = assembly.build_toolbar(avail)
    ok("SiteContext_AddLocation" not in items,
       "Add Location button should be omitted")
    ok("MigrationGuide_ShowPanel" in items, "instructor button went missing")
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["sitecontext"], "missing = %r" % (missing,))


@check("assembly: missing Migration Guide falls back to the own About button")
def c05(fx):
    avail = FULL_HOUSE - {"MigrationGuide_ShowPanel"}
    items = assembly.build_toolbar(avail)
    ok("MigrationGuide_ShowPanel" not in items, "guide button should be omitted")
    ok(items[-1] == assembly.CMD_ABOUT,
       "instructor slot should fall back to About, got %r" % (items[-1],))
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["migrationguide"],
       "missing = %r" % (missing,))


@check("assembly: Move/Rotate needs a transform command (either candidate)")
def c06(fx):
    neither = FULL_HOUSE - set(assembly.TRANSFORM_COMMANDS)
    ok(assembly.CMD_MOVE_ROTATE not in assembly.build_toolbar(neither),
       "Move/Rotate should be omitted without any transform command")
    fallback_only = neither | {"Std_Transform"}
    ok(assembly.CMD_MOVE_ROTATE in assembly.build_toolbar(fallback_only),
       "Move/Rotate should appear with only Std_Transform available")


@check("assembly: Tape Measure needs a measure command (either candidate)")
def c07(fx):
    neither = FULL_HOUSE - set(assembly.MEASURE_COMMANDS)
    ok(assembly.CMD_TAPE_MEASURE not in assembly.build_toolbar(neither),
       "Tape Measure should be omitted without any measure command")
    fallback_only = neither | {"Std_MeasureDistance"}
    ok(assembly.CMD_TAPE_MEASURE in assembly.build_toolbar(fallback_only),
       "Tape Measure should appear with only Std_MeasureDistance available")


@check("assembly: separator hygiene with empty groups and partial views")
def c08(fx):
    bare = assembly.build_toolbar(set())  # nothing detected at all
    ok(bare == [assembly.CMD_SELECT, SEP, assembly.CMD_ERASER,
                assembly.CMD_MAKE_GROUP, SEP, assembly.CMD_PAINT, SEP,
                assembly.CMD_ABOUT],
       "unexpected bare toolbar: %r" % (bare,))
    ok(bare[0] != SEP and bare[-1] != SEP, "leading/trailing separator")
    ok(not any(a == SEP and b == SEP for a, b in zip(bare, bare[1:])),
       "double separators")
    partial = assembly.build_toolbar({"Std_ViewTop"})
    ok("Uppercut_ViewTop" in partial and "Uppercut_ViewIso" not in partial,
       "view group should contain only the probed views")


# --- 9: static cross-check against the sibling clones -------------------------
@check("static xref: spec command names match addCommand() in the sources")
def c09(fx):
    if not _clones_present():
        print("    WARNING: review clones absent at %s; cross-check skipped"
              % _CLONE_ROOT)
        return
    for sib in assembly.SIBLINGS:
        path = _clone_commands_py(sib.key)
        for name in sib.commands:
            ok(assembly.command_in_source(path, name) is True,
               "%s not found as addCommand() in %s" % (name, path))


# --- 10-11: detection ---------------------------------------------------------
@check("detection: live lookup governs when the command manager answers")
def c10(fx):
    all_live = assembly.detect_availability(live_lookup=lambda name: True)
    ok(all_live == set(ALL_SIBLING_COMMANDS),
       "all-live detection = %r" % (all_live,))
    none_live = assembly.detect_availability(live_lookup=lambda name: False)
    ok(none_live == set(),
       "registered-nowhere detection should be empty, got %r" % (none_live,))
    flaky = assembly.detect_availability(
        live_lookup=lambda name: (_ for _ in ()).throw(RuntimeError("no GUI")),
        package_dir_locator=lambda package: None)
    ok(flaky == set(),
       "raising lookup with no installed package should be empty, got %r"
       % (flaky,))


@check("detection: static source fallback against the real sources")
def c11(fx):
    pkg_to_dir = {
        "freecad." + pkg: os.path.dirname(_clone_commands_py(key))
        for key, (_repo, pkg) in _CLONE_DIRS.items()
    }
    if _clones_present():
        found = assembly.detect_availability(
            live_lookup=None,
            package_dir_locator=lambda package: pkg_to_dir.get(package))
        ok(found == set(ALL_SIBLING_COMMANDS),
           "static detection against clones = %r" % (found,))
    else:
        print("    WARNING: review clones absent; static-positive case skipped")
    absent = assembly.detect_availability(
        live_lookup=None, package_dir_locator=lambda package: None)
    ok(absent == set(), "nothing-installed detection should be empty")
    _found, missing = assembly.companions_report(absent)
    ok(len(missing) == 6, "all six companions should report missing")
    ok(len(assembly.missing_notes(absent)) == 6, "expected six install hints")


# --- 12-14: eraser core on a real document ------------------------------------
@check("eraser: transaction delete removes the selected boxes")
def c12(fx):
    fx.doc = App.newDocument("UppercutVerify")
    # freecadcmd creates documents with UndoMode 0 (no undo recording); the
    # GUI default is 1. The eraser only needs an enabled undo stack.
    fx.doc.UndoMode = 1
    fx.box1 = fx.doc.addObject("Part::Box", "EraserBox1")
    fx.box2 = fx.doc.addObject("Part::Box", "EraserBox2")
    fx.keeper = fx.doc.addObject("Part::Box", "Keeper")
    fx.doc.recompute()
    result = eraser.delete_objects(fx.doc, [fx.box1, fx.box2, fx.box1, None])
    ok(result["deleted"] == ["EraserBox1", "EraserBox2"],
       "deleted = %r" % (result["deleted"],))
    ok(fx.doc.getObject("EraserBox1") is None
       and fx.doc.getObject("EraserBox2") is None, "boxes still in the document")
    ok(fx.doc.getObject("Keeper") is not None, "unselected object was removed")
    ok("deleted 2 object(s)" in result["message"],
       "unexpected message: %s" % result["message"])


@check("eraser: undo restores the deleted boxes")
def c13(fx):
    fx.doc.undo()
    ok(fx.doc.getObject("EraserBox1") is not None
       and fx.doc.getObject("EraserBox2") is not None,
       "undo did not restore the boxes")
    ok(fx.doc.getObject("Keeper") is not None, "keeper lost after undo")


@check("eraser: empty selection is a no-op with a message")
def c14(fx):
    before = sorted(o.Name for o in fx.doc.Objects)
    result = eraser.delete_objects(fx.doc, [])
    ok(result["deleted"] == [], "empty selection deleted something")
    ok("nothing selected" in result["message"],
       "unexpected message: %s" % result["message"])
    after = sorted(o.Name for o in fx.doc.Objects)
    ok(before == after, "document changed on an empty selection")


# --- 15-16: paint RGBA core ----------------------------------------------------
@check("paint: palette names build the expected RGBA tuple")
def c15(fx):
    ok(paint.build_rgba("Red") == (0.85, 0.20, 0.15, 1.0),
       "Red = %r" % (paint.build_rgba("Red"),))
    ok(paint.build_rgba(" light gray ") == (0.75, 0.75, 0.75, 1.0),
       "palette lookup should trim and ignore case")
    ok(len(paint.PALETTE) >= 8, "palette unexpectedly small")


@check("paint: tuple input and validation of bad input")
def c16(fx):
    ok(paint.build_rgba((0.5, 0.25, 0.125)) == (0.5, 0.25, 0.125, 1.0),
       "rgb tuple = %r" % (paint.build_rgba((0.5, 0.25, 0.125)),))
    ok(paint.build_rgba((0.1, 0.2, 0.3, 0.4)) == (0.1, 0.2, 0.3, 0.4),
       "rgba tuple not passed through")
    expect_raises(ValueError, lambda: paint.build_rgba("No such color"),
                  "unknown name accepted")
    expect_raises(ValueError, lambda: paint.build_rgba((0.1, 0.2)),
                  "two-component tuple accepted")
    expect_raises(ValueError, lambda: paint.build_rgba((0.1, 0.2, 2.5)),
                  "out-of-range component accepted")
    expect_raises(ValueError, lambda: paint.build_rgba((0.1, 0.2, 0.3), alpha=7),
                  "out-of-range alpha accepted")


# --- 17-19: navigation style ---------------------------------------------------
@check("navstyle: Uppercut parameter round-trip (consent + saved style)")
def c17(fx):
    p = navstyle.params()
    try:
        navstyle.store_consent(navstyle.CONSENT_VIEW)
        navstyle.store_applied("Gui::CADNavigationStyle", "view")
        state = navstyle.load_state()
        ok(state["consent_asked"] is True and state["consent"] is True,
           "consent state = %r" % (state,))
        ok(state["consent_mode"] == navstyle.CONSENT_VIEW,
           "consent mode = %r" % (state,))
        ok(state["applied"] is True
           and state["saved_style"] == "Gui::CADNavigationStyle"
           and state["saved_via"] == "view", "applied state = %r" % (state,))
        navstyle.clear_applied()
        ok(navstyle.load_state()["applied"] is False, "clear_applied failed")
    finally:
        p.SetBool("NavConsentAsked", False)
        p.SetBool("NavConsent", False)
        p.SetString("NavConsentMode", "")
        p.SetBool("NavApplied", False)
        p.SetString("NavSavedStyle", "")
        p.SetString("NavSavedVia", "")


@check("navstyle: view API probe order (set/getNavigationType first)")
def c18(fx):
    class TypeOnly(object):
        def __init__(self):
            self.style = "Gui::CADNavigationStyle"

        def getNavigationType(self):
            return self.style

        def setNavigationType(self, style):
            self.style = style

    class StyleOnly(object):
        def __init__(self):
            self.style = "Gui::CADNavigationStyle"

        def getNavigationStyle(self):
            return self.style

        def setNavigationStyle(self, style):
            self.style = style

    class NoApi(object):
        pass

    v = TypeOnly()
    ok(navstyle.set_view_style(v, navstyle.UPPERCUT_STYLE) is True,
       "setNavigationType path rejected")
    ok(v.style == navstyle.UPPERCUT_STYLE, "style = %r" % (v.style,))
    ok(navstyle.get_view_style(v) == navstyle.UPPERCUT_STYLE,
       "getNavigationType path failed")
    v2 = StyleOnly()
    ok(navstyle.set_view_style(v2, navstyle.UPPERCUT_STYLE) is True,
       "setNavigationStyle fallback rejected")
    ok(navstyle.get_view_style(v2) == navstyle.UPPERCUT_STYLE,
       "getNavigationStyle fallback failed")
    v3 = NoApi()
    ok(navstyle.style_setter(v3) is None, "NoApi should have no setter")
    ok(navstyle.set_view_style(v3, navstyle.UPPERCUT_STYLE) is False,
       "NoApi set should report failure")
    ok(navstyle.get_view_style(v3) is None, "NoApi get should report None")


@check("navstyle: Preferences/View NavigationStyle round-trip and restore")
def c19(fx):
    pref = navstyle.pref_params()
    original = pref.GetString(navstyle.PREF_KEY, "")
    try:
        pref.SetString(navstyle.PREF_KEY, navstyle.UPPERCUT_STYLE)
        ok(pref.GetString(navstyle.PREF_KEY, "") == navstyle.UPPERCUT_STYLE,
           "preference write did not stick")
    finally:
        pref.SetString(navstyle.PREF_KEY, original)
    ok(pref.GetString(navstyle.PREF_KEY, "") == original,
       "original preference was not restored (now %r)"
       % (pref.GetString(navstyle.PREF_KEY, ""),))


# --- 20: own command icons ------------------------------------------------------
@check("icons: every own command maps to a distinct, existing SVG")
def c20(fx):
    own = [assembly.CMD_SELECT, assembly.CMD_MOVE_ROTATE, assembly.CMD_ROTATE,
           assembly.CMD_SCALE, assembly.CMD_ERASER, assembly.CMD_MAKE_GROUP,
           assembly.CMD_TAPE_MEASURE, assembly.CMD_PAINT, assembly.CMD_ABOUT,
           assembly.CMD_RESTORE_NAV, assembly.CMD_MISSING_NOTE]
    own += [name for name, _std in assembly.VIEW_COMMANDS]
    ok(sorted(assembly.ICONS.keys()) == sorted(own),
       "ICONS keys != own commands: %r" % (sorted(assembly.ICONS.keys()),))
    icons_dir = os.path.join(_REPO_ROOT, "Resources", "Icons")
    files = list(assembly.ICONS.values())
    ok(len(set(files)) == len(files), "icons not distinct: %r" % (files,))
    for name, filename in assembly.ICONS.items():
        ok(filename != assembly.DEFAULT_ICON,
           "%s reuses the workbench icon" % name)
        ok(os.path.isfile(os.path.join(icons_dir, filename)),
           "missing icon file for %s: %s" % (name, filename))
    ok(os.path.isfile(os.path.join(icons_dir, assembly.DEFAULT_ICON)),
       "workbench icon %s missing" % assembly.DEFAULT_ICON)


# --- 21: partial sibling spec ---------------------------------------------------
@check("assembly: an older SketchLayer (Line/Rectangle only) degrades cleanly")
def c21(fx):
    avail = FULL_HOUSE - {"SketchLayer_Circle", "SketchLayer_Polygon",
                          "SketchLayer_Arc"}
    items = assembly.build_toolbar(avail)
    ok("SketchLayer_Line" in items and "SketchLayer_Rectangle" in items,
       "buttons of the installed old SketchLayer went missing")
    ok("SketchLayer_Circle" not in items and "SketchLayer_Polygon" not in items
       and "SketchLayer_Arc" not in items,
       "unavailable new-tool buttons should be omitted")
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["sketchlayer"],
       "missing = %r" % (missing,))
    notes = assembly.missing_notes(avail)
    ok(len(notes) == 1 and "SketchLayer" in notes[0],
       "unexpected note: %r" % (notes,))


# --- 22-24: single-letter shortcuts ----------------------------------------------
@check("shortcuts: the SketchUp letter map is complete and collision-free")
def c22(fx):
    pairs = shortcuts.desired_map()
    ok(pairs == [
        ("Space", "Uppercut_Select"),
        ("L", "SketchLayer_Line"),
        ("R", "SketchLayer_Rectangle"),
        ("C", "SketchLayer_Circle"),
        ("A", "SketchLayer_Arc"),
        ("G", "SketchLayer_Polygon"),
        ("P", "PushPull_PushPull"),
        ("E", "Uppercut_Eraser"),
        ("T", "Uppercut_TapeMeasure"),
        ("B", "Uppercut_PaintBucket"),
        ("M", "Uppercut_MoveRotate"),
        ("F", "OffsetTool_Offset"),
        ("Q", "Uppercut_Rotate"),
        ("S", "Uppercut_Scale"),
    ], "map = %r" % (pairs,))
    accels = [accel for accel, _cmd in pairs]
    ok(len(set(accels)) == len(accels), "accelerators collide: %r" % (accels,))
    own = {assembly.CMD_SELECT, assembly.CMD_ERASER, assembly.CMD_MAKE_GROUP,
           assembly.CMD_TAPE_MEASURE, assembly.CMD_PAINT,
           assembly.CMD_MOVE_ROTATE, assembly.CMD_ROTATE, assembly.CMD_SCALE}
    for _accel, cmd in pairs:
        if cmd.startswith("Uppercut_"):
            ok(cmd in own, "%s is not a known own command" % cmd)
            ok(cmd in shortcuts.OWN_SHORTCUT_COMMANDS,
               "%s missing from OWN_SHORTCUT_COMMANDS" % cmd)
        else:
            ok(cmd in ALL_SIBLING_COMMANDS,
               "%s is not a known sibling command" % cmd)
    # Make Group deliberately has no letter (selection-only tool)
    ok(assembly.CMD_MAKE_GROUP not in [cmd for _a, cmd in pairs],
       "Make Group should stay unbound")


@check("shortcuts: conflicts and unavailable commands are skipped, not clobbered")
def c23(fx):
    everything = set(ALL_SIBLING_COMMANDS) | shortcuts.OWN_SHORTCUT_COMMANDS
    applied, skipped = shortcuts.plan_bindings(
        everything, accel_owner=lambda accel: None)
    ok(len(applied) == len(shortcuts.desired_map()) and not skipped,
       "clean run should apply all, skipped = %r" % (skipped,))

    def conflict(accel):
        return "Std_SomeExistingCommand" if accel == "L" else None
    applied, skipped = shortcuts.plan_bindings(everything,
                                               accel_owner=conflict)
    ok(("L", "SketchLayer_Line") not in applied,
       "conflicting 'L' binding was applied")
    ok(len(skipped) == 1 and skipped[0][0] == "L"
       and "Std_SomeExistingCommand" in skipped[0][2],
       "skip entry = %r" % (skipped,))

    def own_already(accel):
        return "SketchLayer_Line" if accel == "L" else None
    applied, skipped = shortcuts.plan_bindings(everything,
                                               accel_owner=own_already)
    ok(("L", "SketchLayer_Line") in applied and not skipped,
       "re-binding a command's own accelerator must not count as a conflict")

    applied, skipped = shortcuts.plan_bindings(
        everything - {"SketchLayer_Line"}, accel_owner=lambda accel: None)
    ok(len(skipped) == 1 and skipped[0][1] == "SketchLayer_Line"
       and "unavailable" in skipped[0][2], "skip entry = %r" % (skipped,))

    def boom(accel):
        raise RuntimeError("no GUI")
    applied, skipped = shortcuts.plan_bindings(everything, accel_owner=boom)
    ok(not skipped, "a raising owner lookup must not skip anything")


@check("shortcuts: apply writes User parameter:BaseApp/Shortcut entries")
def c24(fx):
    p = App.ParamGet(shortcuts.PARAM_GROUP)
    try:
        shortcuts.apply_bindings(
            [("L", "SketchLayer_Line"), ("E", "Uppercut_Eraser")], p=p)
        ok(p.GetString("SketchLayer_Line", "") == "L",
           "round-trip L = %r" % p.GetString("SketchLayer_Line", ""))
        ok(p.GetString("Uppercut_Eraser", "") == "E",
           "round-trip E = %r" % p.GetString("Uppercut_Eraser", ""))
    finally:
        p.RemString("SketchLayer_Line")
        p.RemString("Uppercut_Eraser")
    ok(p.GetString("SketchLayer_Line", "") == "", "cleanup left L behind")


# --- 25: make group ---------------------------------------------------------------
@check("make group: two boxes wrapped in one App::Part; undo restores them")
def c25(fx):
    doc = fx.doc  # UndoMode is already 1 (enabled by the eraser checks)
    box1 = doc.addObject("Part::Box", "GroupBox1")
    box2 = doc.addObject("Part::Box", "GroupBox2")
    doc.recompute()
    result = group.make_group(doc, [box1, box2, box1, None])
    ok(result["moved"] == ["GroupBox1", "GroupBox2"],
       "moved = %r" % (result["moved"],))
    grp = doc.getObject(result["group"])
    ok(grp is not None and grp.TypeId == "App::Part",
       "TypeId is %s" % (grp.TypeId if grp is not None else None))
    ok([o.Name for o in grp.Group] == ["GroupBox1", "GroupBox2"],
       "Group = %r" % ([o.Name for o in grp.Group],))
    ok("grouped 2 object(s)" in result["message"],
       "unexpected message: %s" % result["message"])
    doc.undo()
    ok(doc.getObject(result["group"]) is None, "group survived undo")
    ok(doc.getObject("GroupBox1") is not None
       and doc.getObject("GroupBox2") is not None,
       "boxes did not come back after undo")
    result = group.make_group(doc, [])
    ok(result["group"] is None and result["moved"] == []
       and "nothing" in result["message"],
       "empty selection should be a no-op: %r" % (result,))


# --- 26: eraser armed session -----------------------------------------------------
@check("eraser: armed click-to-delete session (arm, delete picked, disarm)")
def c26(fx):
    doc = fx.doc
    session = eraser.EraserSession(doc)
    ok(not session.armed, "session should start disarmed")
    ok(session.delete_picked(fx.keeper) is None,
       "delete_picked while disarmed must not act")
    ok(doc.getObject("Keeper") is not None, "keeper lost while disarmed")
    session.arm()
    ok(session.armed, "arm failed")
    ok("click an object" in session.last_message,
       "arm prompt = %r" % session.last_message)
    victim = doc.addObject("Part::Box", "ClickVictim")
    doc.recompute()
    result = session.delete_picked(victim)
    ok(result is not None and result["deleted"] == ["ClickVictim"],
       "deleted = %r" % (result["deleted"] if result else None,))
    ok(doc.getObject("ClickVictim") is None, "victim survived the click")
    ok(session.armed, "session should stay armed for the next click")
    session.toggle()
    ok(not session.armed, "toggle (re-invoke) should disarm")
    session.toggle()
    ok(session.armed, "second toggle should re-arm")
    session.disarm()
    ok(not session.armed, "disarm failed")


# --- 27-28: Offset/FollowMe toolbar slots + icon paths ----------------------------
@check("assembly: Offset/FollowMe sit right after Push/Pull, each optional")
def c27(fx):
    avail = FULL_HOUSE - {"FollowMe_Sweep"}
    items = assembly.build_toolbar(avail)
    i_pp = items.index("PushPull_PushPull")
    ok(items[i_pp + 1] == "OffsetTool_Offset",
       "Offset should follow Push/Pull directly: %r" % (items,))
    ok("FollowMe_Sweep" not in items, "missing FollowMe should be omitted")
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["followme"],
       "missing = %r" % (missing,))
    avail = FULL_HOUSE - {"PushPull_PushPull", "OffsetTool_Offset"}
    items = assembly.build_toolbar(avail)
    ok("PushPull_PushPull" not in items and "OffsetTool_Offset" not in items,
       "absent buttons leaked: %r" % (items,))
    ok("FollowMe_Sweep" in items, "FollowMe should remain: %r" % (items,))
    _found, missing = assembly.companions_report(avail)
    ok([s.key for s in missing] == ["pushpull", "offset"],
       "missing = %r" % (missing,))


@check("assembly: sibling icons resolve via the package path (None when absent)")
def c28(fx):
    loc = {
        "freecad.OffsetToolWB": os.path.join(
            _BUILD_ROOT, "FreeCAD-Offset", "freecad", "OffsetToolWB"),
        "freecad.FollowMeWB": os.path.join(
            _BUILD_ROOT, "FreeCAD-FollowMe", "freecad", "FollowMeWB"),
    }
    # the positive path needs the sibling build trees on this machine; skip
    # with a warning when they are absent (same policy as the static xref
    # check) so the harness stays green on other machines
    if all(os.path.isdir(d) for d in loc.values()):
        off = assembly.sibling_icon_path("offset", package_dir_locator=loc.get)
        ok(off is not None and os.path.isfile(off)
           and off.endswith(os.path.join("Resources", "Icons", "offsettool.svg")),
           "offset icon = %r" % (off,))
        fm = assembly.sibling_icon_path("followme", package_dir_locator=loc.get)
        ok(fm is not None and os.path.isfile(fm)
           and fm.endswith(os.path.join("Resources", "Icons", "followme.svg")),
           "followme icon = %r" % (fm,))
    else:
        print("WARNING: sibling build trees absent, icon-resolution positive "
              "path skipped on this machine")
    ok(assembly.sibling_icon_path(
        "offset", package_dir_locator=lambda package: None) is None,
       "absent package should give None (caller uses uppercut_missing.svg)")


# --- 29: GUI accelerator introspection (with fakes) ------------------------------
@check("shortcuts: GUI accelerator introspection builds the conflict table")
def c29(fx):
    class FakeCmd(object):
        def __init__(self, shortcut):
            self._shortcut = shortcut

        def getShortcut(self):
            return self._shortcut

    class FakeCommand(object):
        @staticmethod
        def get(name):
            return {"Std_Undo": FakeCmd("Ctrl+Z"),
                    "Std_OldLineTool": FakeCmd("l")}.get(name)

    class FakeGui(object):
        Command = FakeCommand

        @staticmethod
        def listCommands():
            return ["Std_Undo", "Std_OldLineTool", "BrokenCommand"]

    owner = shortcuts.gui_accel_owner(FakeGui)
    ok(owner("Ctrl+Z") == "Std_Undo", "owner(Ctrl+Z) = %r" % owner("Ctrl+Z"))
    ok(owner("L") == "Std_OldLineTool",
       "match should be case-insensitive: %r" % owner("L"))
    ok(owner("Q") is None, "unbound accelerator should have no owner")

    class DeadGui(object):
        @staticmethod
        def listCommands():
            raise RuntimeError("no GUI")

    owner = shortcuts.gui_accel_owner(DeadGui)
    ok(owner("L") is None, "a dead manager should yield an empty table")


# --- 30-31: active-tool highlight (radio tracker + Qt adapter, both with fakes) ---
@check("toolstate: radio tracker (radio clear, re-assert, inactive, clear_all)")
def c30(fx):
    class Rec(object):
        def __init__(self):
            self.calls = []

        def set_highlight(self, name, on):
            self.calls.append((name, on))
            return 1

    rec = Rec()
    t = toolstate.RadioTracker(rec)
    ok(t.active() is None and t.lit() == set(), "tracker should start empty")
    t.mark_active("A")
    ok(t.active() == "A" and t.lit() == {"A"}, "A not active")
    ok(rec.calls == [("A", True)], "calls = %r" % (rec.calls,))
    t.mark_active("B")  # radio: A must clear
    ok(t.active() == "B" and t.lit() == {"B"}, "radio to B failed: %r" % (t.lit(),))
    ok(rec.calls[-2:] == [("A", False), ("B", True)],
       "radio sequence = %r" % (rec.calls,))
    t.mark_active("B")  # re-assert own state, no churn on A
    ok(rec.calls[-1] == ("B", True) and ("A", False) not in rec.calls[3:],
       "re-assert = %r" % (rec.calls,))
    n = len(rec.calls)
    t.mark_inactive("A")  # stray: A is neither active nor lit
    ok(t.active() == "B", "stray mark_inactive(A) cleared the owner")
    ok(len(rec.calls) == n, "stray mark_inactive(A) hit the adapter")
    t.mark_inactive("B")
    ok(t.active() is None and t.lit() == set(), "B should be fully cleared")
    ok(rec.calls[-1] == ("B", False), "calls = %r" % (rec.calls,))
    # a name that stayed lit without owning the radio slot is unlit by its
    # own mark_inactive, without touching the current owner
    t.mark_active("C")
    t._lit.add("GHOST")
    t.mark_inactive("GHOST")
    ok(t.active() == "C" and t.lit() == {"C"}, "ghost clear broke the owner")
    ok(("GHOST", False) in rec.calls, "ghost was not unlit")
    t.mark_active("D")
    t.clear_all()
    ok(t.active() is None and t.lit() == set(), "clear_all failed")
    ok(rec.calls[-1] == ("D", False), "calls = %r" % (rec.calls,))

    class Boom(object):
        def set_highlight(self, name, on):
            raise RuntimeError("no GUI")

    t2 = toolstate.RadioTracker(Boom())
    t2.mark_active("X")
    t2.mark_active("Y")  # a failing adapter must never break tracking
    t2.mark_inactive("Y")
    t2.clear_all()
    ok(t2.active() is None and t2.lit() == set(),
       "failing adapter broke the tracker")


@check("toolstate: Qt adapter lookup with fake toolbars/actions")
def c31(fx):
    class FakeAction(object):
        def __init__(self, data=None, object_name="", separator=False):
            self._data = data
            self._object_name = object_name
            self._separator = separator
            self.checkable = False
            self.checked = False
            self.checkable_sets = 0

        def isSeparator(self):
            return self._separator

        def data(self):
            return self._data

        def objectName(self):
            return self._object_name

        def isCheckable(self):
            return self.checkable

        def setCheckable(self, on):
            self.checkable = on
            self.checkable_sets += 1

        def setChecked(self, on):
            self.checked = on

    class FakeToolBar(object):
        def __init__(self, actions):
            self._actions = actions

        def actions(self):
            return list(self._actions)

    class FakeWindow(object):
        def __init__(self, bars):
            self._bars = bars

        def findChildren(self, cls):
            return [b for b in self._bars if isinstance(b, cls)]

    class FakeQt(object):
        QToolBar = FakeToolBar

    class FakeGui(object):
        def __init__(self, window):
            self._window = window

        def getMainWindow(self):
            return self._window

    line = FakeAction(data="SketchLayer_Line", object_name="SketchLayer_Line")
    circle_by_name = FakeAction(data=None, object_name="SketchLayer_Circle")
    sep = FakeAction(separator=True)
    other = FakeAction(data="Uppercut_Select", object_name="Uppercut_Select")
    bars = [FakeToolBar([line, sep, other]), FakeToolBar([circle_by_name])]
    ad = toolstate.QtActionAdapter(gui=FakeGui(FakeWindow(bars)), qt=FakeQt)

    ok(ad.find_actions("SketchLayer_Line") == [line],
       "data()/objectName() match failed")
    ok(ad.find_actions("SketchLayer_Circle") == [circle_by_name],
       "objectName-only match failed")
    ok(ad.find_actions("Nope_Nothing") == [], "unknown command should miss")
    n = ad.set_highlight("SketchLayer_Line", True)
    ok(n == 1, "set_highlight drove %d actions" % n)
    ok(line.checkable and line.checked and line.checkable_sets == 1,
       "line should be checkable+checked after one set")
    ad.set_highlight("SketchLayer_Line", True)
    ok(line.checkable_sets == 1, "setCheckable re-applied (must be once)")
    ad.set_highlight("SketchLayer_Line", False)
    ok(line.checkable and not line.checked, "clear failed")
    ok(not other.checkable and not other.checked, "an unrelated action was touched")
    ok(not sep.checkable, "the separator was touched")
    ok(ad.set_highlight("Nope_Nothing", True) == 0, "unknown command drove actions")


# --- 32: lifecycle wiring (static xref against this checkout's sources) --------
@check("wiring: toolstate/nav call sites in commands.py and init_gui.py")
def c32(fx):
    pkg = os.path.join(_REPO_ROOT, "freecad", "UppercutWB")
    with open(os.path.join(pkg, "commands.py"), encoding="utf-8") as fh:
        commands_src = fh.read()
    with open(os.path.join(pkg, "init_gui.py"), encoding="utf-8") as fh:
        init_src = fh.read()
    for needle in (
            "toolstate.mark_active(assembly.CMD_SELECT)",
            "toolstate.mark_active(assembly.CMD_ERASER)",
            "toolstate.mark_inactive(assembly.CMD_ERASER)",
            "navstyle.restore_navigation(Gui)"):
        ok(needle in commands_src, "%r missing from commands.py" % needle)
    for needle in (
            "navstyle.watch_views(Gui)",
            "navstyle.unwatch_views()",
            "navstyle.apply_global_style(Gui)",
            "navstyle.apply_target(state)"):
        ok(needle in init_src, "%r missing from init_gui.py" % needle)
    # the eraser highlight belongs to the armed session only (the one-shot
    # delete path must stay unlit): mark_active inside _arm, mark_inactive
    # inside _disarm
    arm = commands_src.index("def _arm(self, doc):")
    disarm = commands_src.index("def _disarm(self):")
    teardown = commands_src.index("def _teardown_callbacks(self):")
    ma = commands_src.index("toolstate.mark_active(assembly.CMD_ERASER)")
    mi = commands_src.index("toolstate.mark_inactive(assembly.CMD_ERASER)")
    ok(arm < ma < disarm, "eraser mark_active is not inside _arm")
    ok(disarm < mi < teardown, "eraser mark_inactive is not inside _disarm")


# --- 33-36: navigation "everywhere" + consent modes + all-views + watcher ------
@check("navstyle: 'everywhere' writes + restores the global preference")
def c33(fx):
    p = navstyle.params()
    pref = navstyle.pref_params()
    original = pref.GetString(navstyle.PREF_KEY, "")
    try:
        p.SetBool("NavGlobalApplied", False)
        p.SetString("NavSavedGlobalStyle", "")
        navstyle.apply_global_style(None, p=p, pref=pref)
        ok(pref.GetString(navstyle.PREF_KEY, "") == navstyle.UPPERCUT_STYLE,
           "global preference not written")
        state = navstyle.load_state(p)
        ok(state["global_applied"] is True
           and state["saved_global_style"] == original,
           "prior global value not recorded: %r" % (state,))
        # idempotent: a repeat apply must not overwrite the recorded prior
        navstyle.apply_global_style(None, p=p, pref=pref)
        ok(navstyle.load_state(p)["saved_global_style"] == original,
           "re-apply overwrote the recorded prior value")
        ok(navstyle.restore_global_style(None, p=p, pref=pref) == "restored",
           "restore_global_style did not report restored")
        ok(pref.GetString(navstyle.PREF_KEY, "") == original,
           "global preference not restored to the original")
        ok(navstyle.load_state(p)["global_applied"] is False,
           "global flag not cleared")
        ok(navstyle.restore_global_style(None, p=p, pref=pref) == "nothing",
           "a second restore should report nothing")
    finally:
        pref.SetString(navstyle.PREF_KEY, original)
        p.SetBool("NavGlobalApplied", False)
        p.SetString("NavSavedGlobalStyle", "")


@check("navstyle: consent mode state machine (view/global/none + legacy)")
def c34(fx):
    p = navstyle.params()
    try:
        for mode, want_consent, want_target in (
                (navstyle.CONSENT_VIEW, True, "view"),
                (navstyle.CONSENT_GLOBAL, True, "global"),
                (navstyle.CONSENT_NONE, False, "none")):
            navstyle.store_consent(mode, p=p)
            state = navstyle.load_state(p)
            ok(state["consent_asked"] is True, "asked flag lost for %r" % mode)
            ok(state["consent"] is want_consent,
               "consent bool for %r = %r" % (mode, state["consent"]))
            ok(state["consent_mode"] == mode,
               "mode for %r = %r" % (mode, state["consent_mode"]))
            ok(navstyle.apply_target(state) == want_target,
               "target for %r = %r" % (mode, navstyle.apply_target(state)))
        # legacy state from an older Uppercut: consent boolean, no mode string
        p.SetBool("NavConsentAsked", True)
        p.SetBool("NavConsent", True)
        p.SetString("NavConsentMode", "")
        ok(navstyle.apply_target(navstyle.load_state(p)) == "view",
           "legacy consent=True should map to per-view")
        p.SetBool("NavConsent", False)
        ok(navstyle.apply_target(navstyle.load_state(p)) == "none",
           "legacy consent=False should map to none")
    finally:
        p.SetBool("NavConsentAsked", False)
        p.SetBool("NavConsent", False)
        p.SetString("NavConsentMode", "")


@check("navstyle: apply/restore across ALL open views (fake gui)")
def c35(fx):
    class FakeView(object):
        def __init__(self, style):
            self.style = style

        def getNavigationType(self):
            return self.style

        def setNavigationType(self, style):
            self.style = style

    class FakeGDoc(object):
        def __init__(self, views):
            self._views = views

        def mdiViewsOfType(self, typestr):
            return list(self._views)

    class FakeGui(object):
        def __init__(self, docs):
            self._docs = docs

        def getDocument(self, name):
            return self._docs[name]

    p = navstyle.params()
    pref = navstyle.pref_params()
    original = pref.GetString(navstyle.PREF_KEY, "")
    v1 = FakeView("Gui::CADNavigationStyle")
    v2 = FakeView("Gui::CADNavigationStyle")
    v3 = FakeView("Gui::CADNavigationStyle")
    gui = FakeGui({"DocA": FakeGDoc([v1, v2]), "DocB": FakeGDoc([v3])})
    lister = lambda: {"DocA": None, "DocB": None}  # noqa: E731
    try:
        navstyle.clear_applied(p)
        how = navstyle.apply_sketchup_style(gui, list_documents=lister)
        ok(how == "view", "apply = %r" % how)
        ok([v.style for v in (v1, v2, v3)] == [navstyle.UPPERCUT_STYLE] * 3,
           "not every view switched: %r" % ([v.style for v in (v1, v2, v3)],))
        state = navstyle.load_state(p)
        ok(state["applied"] and state["saved_via"] == "view"
           and state["saved_style"] == "Gui::CADNavigationStyle",
           "saved state = %r" % (state,))
        # a view opened later starts on the user default; the watcher path
        # (reapply_to_views) switches exactly that one
        v4 = FakeView("Gui::CADNavigationStyle")
        gui._docs["DocA"]._views.append(v4)
        changed = navstyle.reapply_to_views(gui, list_documents=lister)
        ok(changed == [v4], "reapply changed %r" % (changed,))
        ok(v4.style == navstyle.UPPERCUT_STYLE, "new view not switched")
        ok(navstyle.restore_style(gui, list_documents=lister) == "restored",
           "restore did not report restored")
        ok([v.style for v in (v1, v2, v3, v4)]
           == ["Gui::CADNavigationStyle"] * 4, "not every view restored")
        ok(navstyle.restore_style(gui, list_documents=lister) == "nothing",
           "a second restore should report nothing")
        # no reachable views: the preference fallback path (and its restore)
        empty_gui = FakeGui({})
        how = navstyle.apply_sketchup_style(empty_gui, list_documents=lister)
        ok(how == "preference", "fallback = %r" % how)
        ok(pref.GetString(navstyle.PREF_KEY, "") == navstyle.UPPERCUT_STYLE,
           "preference fallback did not write")
        ok(navstyle.restore_style(empty_gui, list_documents=lister) == "restored",
           "preference restore failed")
        ok(pref.GetString(navstyle.PREF_KEY, "") == original,
           "preference fallback did not restore the original")
    finally:
        pref.SetString(navstyle.PREF_KEY, original)
        p.SetBool("NavApplied", False)
        p.SetString("NavSavedStyle", "")
        p.SetString("NavSavedVia", "")


@check("navstyle: watcher decision logic (per-view only, applied only)")
def c36(fx):
    base = {"consent_asked": True, "consent": True, "consent_mode": "view",
            "applied": True}
    ok(navstyle.watcher_should_apply(base) is True,
       "per-view + applied should watch")
    state = dict(base, consent_mode="global")
    ok(navstyle.watcher_should_apply(state) is False,
       "global mode must not watch (no per-view restore there)")
    state = dict(base, consent_mode="none", consent=False)
    ok(navstyle.watcher_should_apply(state) is False, "declined should not watch")
    state = dict(base, applied=False)
    ok(navstyle.watcher_should_apply(state) is False,
       "nothing applied -> nothing to keep applied")


def main():
    fx = type("Fixture", (), {})()
    passed = 0
    failures = []
    for idx, (name, fn) in enumerate(_checks, 1):
        try:
            fn(fx)
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures.append((idx, name, exc))
            print("[FAIL %2d] %s" % (idx, name))
            traceback.print_exc()
        else:
            passed += 1
            print("[ ok  %2d] %s" % (idx, name))
    if getattr(fx, "doc", None) is not None:
        try:
            App.closeDocument(fx.doc.Name)
        except Exception:  # noqa: BLE001
            pass
    total = passed + len(failures)
    print("-" * 64)
    print("%d/%d checks pass" % (passed, total))
    if total != EXPECTED_CHECKS:
        print("WARNING: ran %d checks, expected %d -- update EXPECTED_CHECKS"
              % (total, EXPECTED_CHECKS))
    if failures:
        print("FAILURES:")
        for idx, name, exc in failures:
            print("  %2d. %s: %s" % (idx, name, exc))
        return 1
    return 0


# Not guarded by __name__ == "__main__": stock freecadcmd (for example the
# conda-forge 1.1.0 build) does not set __name__ that way, so a guarded
# harness silently runs zero checks and still exits 0. Run unconditionally;
# os._exit propagates the code without tripping freecadcmd's SystemExit
# handling, and the flush beats freecadcmd's buffered stdout.
rc = main()
sys.stdout.flush()
os._exit(rc)
