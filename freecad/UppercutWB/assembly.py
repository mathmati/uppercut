# SPDX-License-Identifier: MIT
"""Toolbar assembly and sibling dependency detection for Uppercut.

PURE LOGIC: this module imports nothing from FreeCAD's GUI side (and no
PySide), so it is importable and fully testable headless under freecadcmd.
Everything environment-dependent (the live command manager, the location of
an installed sibling package) is injected as a callable.

Detection rule per sibling command, in order:

1. If a live lookup is supplied (GUI runtime: ``Gui.Command.get(name) is
   not None``) and it returns without raising, trust it. A False here means
   "not registered": sibling workbenches register their commands lazily on
   first activation, so init_gui force-registers installed siblings before
   calling us, and a still-missing command is treated as absent (its button
   is omitted instead of left dead).
2. If the live lookup is unavailable or raised (headless freecadcmd has no
   command manager), fall back to a static check: locate the installed
   sibling package and grep its commands.py source for
   ``addCommand("<name>"``.

A missing sibling never raises; it just yields no buttons, and
``missing_companions`` reports what to install.
"""
import importlib.util
import os
import re

# --- own command names -------------------------------------------------------
CMD_SELECT = "Uppercut_Select"
CMD_MOVE_ROTATE = "Uppercut_MoveRotate"
CMD_ROTATE = "Uppercut_Rotate"
CMD_SCALE = "Uppercut_Scale"
CMD_ERASER = "Uppercut_Eraser"
CMD_MAKE_GROUP = "Uppercut_MakeGroup"
CMD_TAPE_MEASURE = "Uppercut_TapeMeasure"
CMD_PAINT = "Uppercut_PaintBucket"
CMD_ABOUT = "Uppercut_About"
CMD_RESTORE_NAV = "Uppercut_RestoreNavigation"
CMD_MISSING_NOTE = "Uppercut_MissingCompanions"

#: Own view wrappers and the built-in command each one relays to, in order.
VIEW_COMMANDS = (
    ("Uppercut_ViewIso", "Std_ViewIsometric"),
    ("Uppercut_ViewTop", "Std_ViewTop"),
    ("Uppercut_ViewFront", "Std_ViewFront"),
    ("Uppercut_ViewRight", "Std_ViewRight"),
    ("Uppercut_ViewFitAll", "Std_ViewFitAll"),
)

#: Workbench icon, also the fallback for any own command not in ICONS.
DEFAULT_ICON = "uppercut.svg"

#: Own command name -> its icon file in Resources/Icons. Every own command
#: gets a distinct icon (the previous single shared _ICON_PATH made the
#: toolbar unreadable); the workbench itself keeps uppercut.svg. Pure data
#: so the headless regression can check completeness, distinctness and that
#: each referenced file exists.
ICONS = {
    CMD_SELECT: "uppercut_select.svg",
    CMD_MOVE_ROTATE: "uppercut_move.svg",
    CMD_ROTATE: "uppercut_rotate.svg",
    CMD_SCALE: "uppercut_scale.svg",
    CMD_ERASER: "uppercut_eraser.svg",
    CMD_MAKE_GROUP: "uppercut_group.svg",
    CMD_TAPE_MEASURE: "uppercut_measure.svg",
    CMD_PAINT: "uppercut_paint.svg",
    CMD_ABOUT: "uppercut_about.svg",
    CMD_RESTORE_NAV: "uppercut_navigation.svg",
    CMD_MISSING_NOTE: "uppercut_missing.svg",
    "Uppercut_ViewIso": "uppercut_view_iso.svg",
    "Uppercut_ViewTop": "uppercut_view_top.svg",
    "Uppercut_ViewFront": "uppercut_view_front.svg",
    "Uppercut_ViewRight": "uppercut_view_right.svg",
    "Uppercut_ViewFitAll": "uppercut_view_fitall.svg",
}

#: Built-in command probe candidates, in preference order. Verified against
#: the FreeCAD 1.1.1 install on 2026-07-18: Std_TransformManip, Std_Transform
#: and Std_Measure exist; Std_MeasureDistance was removed (unified Measure).
TRANSFORM_COMMANDS = ("Std_TransformManip", "Std_Transform")
MEASURE_COMMANDS = ("Std_Measure", "Std_MeasureDistance")

#: Every built-in command the workbench probes at runtime.
STD_PROBE_COMMANDS = (
    TRANSFORM_COMMANDS
    + MEASURE_COMMANDS
    + tuple(std for _own, std in VIEW_COMMANDS)
)

SEPARATOR = "Separator"


class Sibling(object):
    """One companion addon Uppercut draws toolbar buttons from."""

    def __init__(self, key, title, package, commands, install_hint, provides,
                 icon=None):
        self.key = key
        self.title = title
        self.package = package
        self.commands = tuple(commands)
        self.install_hint = install_hint
        self.provides = provides
        self.icon = icon


#: Companion addons, in toolbar order of their first appearance.
SIBLINGS = (
    Sibling(
        key="sketchlayer",
        title="SketchLayer",
        package="freecad.SketchLayerWB",
        commands=("SketchLayer_Line", "SketchLayer_Rectangle",
                  "SketchLayer_Circle", "SketchLayer_Polygon",
                  "SketchLayer_Arc"),
        install_hint=("install 'SketchLayer' from the Addon Manager, or see "
                      "github.com/mathmati/FreeCAD-SketchLayer"),
        provides=("Line/Rectangle/Circle/Polygon/Arc drawing in the 3D view "
                  "with inference cues and type-to-dimension"),
        icon="sketchlayer.svg",
    ),
    Sibling(
        key="pushpull",
        title="PushPull",
        package="freecad.PushPullWB",
        commands=("PushPull_PushPull",),
        install_hint=("install 'PushPull' from the Addon Manager, or see "
                      "github.com/mathmati/FreeCAD-PushPull"),
        provides="Push/Pull direct modeling (click-drag a face to Pad/Pocket)",
        icon="pushpull.svg",
    ),
    Sibling(
        key="offset",
        title="Offset",
        package="freecad.OffsetToolWB",
        commands=("OffsetTool_Offset",),
        install_hint=("install 'Offset' from the Addon Manager, or see "
                      "github.com/mathmati/FreeCAD-Offset"),
        provides=("Offset a planar face's boundary inward/outward, in its "
                  "own plane"),
        icon="offsettool.svg",
    ),
    Sibling(
        key="followme",
        title="FollowMe",
        package="freecad.FollowMeWB",
        commands=("FollowMe_Sweep",),
        install_hint=("install 'FollowMe' from the Addon Manager, or see "
                      "github.com/mathmati/FreeCAD-FollowMe"),
        provides="Follow Me: sweep a profile face along a path of edges",
        icon="followme.svg",
    ),
    Sibling(
        key="sitecontext",
        title="SiteContext",
        package="freecad.SiteContextWB",
        commands=("SiteContext_AddLocation",),
        install_hint=("install 'SiteContext' from the Addon Manager, or see "
                      "github.com/mathmati/FreeCAD-SiteContext"),
        provides="Add Location: OpenStreetMap site background and terrain",
        icon="sitecontext.svg",
    ),
    Sibling(
        key="migrationguide",
        title="Migration Guide",
        package="freecad.MigrationGuideWB",
        commands=("MigrationGuide_ShowPanel",),
        install_hint=("install 'Migration Guide' from the Addon Manager, or see "
                      "github.com/mathmati/FreeCAD-Migration-Guide"),
        provides="Instructor panel (migration guide and guided tour)",
        icon="migrationguide.svg",
    ),
)

_SIBLING_BY_KEY = {sib.key: sib for sib in SIBLINGS}

_ADDCOMMAND_RE = 'addCommand\\(\\s*["\']%s["\']'


def command_in_source(commands_py_path, name):
    """True if ``commands_py_path`` contains ``addCommand("<name>"``.

    Returns None when the file cannot be read (unknown, not absent). Never
    raises on a missing file.
    """
    try:
        with open(commands_py_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    return re.search(_ADDCOMMAND_RE % re.escape(name), text) is not None


def find_package_dir(package):
    """Directory of an installed (namespace) subpackage, or None.

    Uses importlib.util.find_spec, which imports parent packages but not the
    target package body, so no sibling GUI code runs here. Returns the first
    search location for namespace packages.
    """
    try:
        spec = importlib.util.find_spec(package)
    except (ImportError, AttributeError, ValueError):
        return None
    if spec is None:
        return None
    locations = spec.submodule_search_locations
    if not locations:
        return None
    return list(locations)[0]


def sibling_icon_path(sibling, package_dir_locator=None):
    """Absolute path to a sibling's own toolbar SVG, or None.

    Resolves ``<package root>/Resources/Icons/<icon>`` through the same
    :func:`find_package_dir` mechanism detection uses: the art stays in the
    sibling's Resources, nothing is copied into Uppercut. ``sibling`` is a
    :class:`Sibling` or a key from SIBLINGS. Returns None when the package
    or the file is absent; callers fall back to ``uppercut_missing.svg``
    (the Missing-companions note already uses it). Never raises.
    """
    sib = sibling if isinstance(sibling, Sibling) else _SIBLING_BY_KEY[sibling]
    if not sib.icon:
        return None
    locator = package_dir_locator or find_package_dir
    try:
        pkg_dir = locator(sib.package)
    except Exception:  # noqa: BLE001 - treat as not installed
        pkg_dir = None
    if not pkg_dir:
        return None
    path = os.path.normpath(os.path.join(
        pkg_dir, os.pardir, os.pardir, "Resources", "Icons", sib.icon))
    return path if os.path.isfile(path) else None


def detect_availability(live_lookup=None, package_dir_locator=None):
    """Return the set of available sibling command names.

    ``live_lookup``: callable(command_name) -> bool, e.g. backed by
    ``Gui.Command.get``. If it raises for a name, the static fallback is
    used for that name. If ``live_lookup`` is None (no command manager,
    e.g. headless freecadcmd), only the static fallback runs.

    ``package_dir_locator``: callable(package) -> directory or None.
    Defaults to :func:`find_package_dir`. Injected by tests.

    Never raises on a missing or broken sibling.
    """
    locator = package_dir_locator or find_package_dir
    available = set()
    for sib in SIBLINGS:
        pkg_dir = None
        located = False
        for name in sib.commands:
            present = None
            if live_lookup is not None:
                try:
                    present = bool(live_lookup(name))
                except Exception:  # noqa: BLE001 - unusable lookup, fall back
                    present = None
            if present is None:
                if not located:
                    located = True
                    try:
                        pkg_dir = locator(sib.package)
                    except Exception:  # noqa: BLE001 - treat as not installed
                        pkg_dir = None
                if pkg_dir:
                    present = command_in_source(
                        os.path.join(pkg_dir, "commands.py"), name) is True
                else:
                    present = False
            if present:
                available.add(name)
    return available


def build_toolbar(available):
    """Ordered toolbar item list (with SEPARATOR between non-empty groups).

    ``available``: iterable of present command names: detected sibling
    commands plus the probed Std_* built-ins. Own unconditional tools
    (Select, Eraser, Make Group, Paint Bucket, About) are always available;
    conditional wrappers (Move/Rotate, Tape Measure, views) appear only
    when at least one of their probe candidates is present. The
    Offset/FollowMe sibling buttons sit right after Push/Pull, in the same
    group, when their addons are detected.
    """
    avail = set(available)
    sketchlayer, pushpull, offset, followme, sitecontext, migrationguide = \
        SIBLINGS

    groups = [
        [CMD_SELECT],
        [c for c in sketchlayer.commands if c in avail],
        [c for c in (pushpull.commands + offset.commands + followme.commands)
         if c in avail],
        [CMD_MOVE_ROTATE] if any(c in avail for c in TRANSFORM_COMMANDS) else [],
        [CMD_ERASER, CMD_MAKE_GROUP],
        [CMD_TAPE_MEASURE] if any(c in avail for c in MEASURE_COMMANDS) else [],
        [CMD_PAINT],
        [own for own, std in VIEW_COMMANDS if std in avail],
        [c for c in sitecontext.commands if c in avail],
        [migrationguide.commands[0]
         if migrationguide.commands[0] in avail else CMD_ABOUT],
    ]

    items = []
    for group in groups:
        if not group:
            continue
        if items:
            items.append(SEPARATOR)
        items.extend(group)
    return items


def companions_report(available):
    """(found, missing) sibling lists, given the detected command set."""
    avail = set(available)
    found, missing = [], []
    for sib in SIBLINGS:
        if all(c in avail for c in sib.commands):
            found.append(sib)
        else:
            missing.append(sib)
    return found, missing


def missing_notes(available):
    """One-line install hints for each missing companion (menu/about text)."""
    _found, missing = companions_report(available)
    return ["%s: not found (%s)" % (sib.title, sib.install_hint)
            for sib in missing]
