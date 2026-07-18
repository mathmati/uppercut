# FreeCAD Uppercut

Uppercut is the direct-modeling interface we always wished FreeCAD had.

It takes the best ideas from the easiest modelers to use (SketchUp's
push/pull and inference drawing, Fusion 360's press-pull, Plasticity's
direct modeling) and builds them into FreeCAD 1.1 as one native workbench,
then takes them further: every drag, offset, and sweep commits an ordinary
parametric feature, so direct modeling and FreeCAD's full feature tree are
always both available. One toolbar covers the whole draw-extrude-measure
loop, assembled from six companion addons plus small glue tools of its own,
with single-letter shortcuts for the main tools.

## What it is

Uppercut is an umbrella workbench. The drawing, push/pull, offset, follow-me,
site-context and instructor functions come from sibling addons I already
maintain; Uppercut detects them, puts their commands on one simple toolbar
in a fixed order, and adds the missing glue tools itself (Select, Move/Rotate,
Rotate, Scale, Eraser, Make Group, Tape Measure, Paint Bucket, standard
views). The idea is the SketchUp toolbar layout: everything a beginner needs
on one row, nothing else in the way.

Detection works in two steps. Sibling workbenches register their commands
lazily (on first activation of their own workbench), so at startup Uppercut
imports each installed sibling's commands module and calls its register(),
then asks the command manager (`Gui.Command.get`) which commands actually
exist. Where no command manager is available (headless freecadcmd), it falls
back to a static check: the installed sibling's commands.py source must
contain `addCommand("<name>"`. A companion that is not installed, or that
fails to load, never raises anything: its buttons are left out, and the
Uppercut menu gets a "Missing companions" note that says what to install.
The About/companions dialog lists the same information with one-line install
hints.

## Companions

| Companion | What it provides | Toolbar buttons |
|---|---|---|
| [SketchLayer](https://github.com/mathmati/FreeCAD-SketchLayer) | Line/rectangle/circle/polygon/arc drawing in the 3D view with colored inference cues and type-to-dimension | Line, Rectangle, Circle, Polygon, Arc |
| [PushPull](https://github.com/mathmati/FreeCAD-PushPull) | Click-drag a planar face to a parametric Pad/Pocket/Extrusion | Push/Pull |
| [Offset](https://github.com/mathmati/FreeCAD-Offset) | Offset a planar face's boundary inward/outward in its own plane | Offset |
| [FollowMe](https://github.com/mathmati/FreeCAD-FollowMe) | Sweep a profile face along a path of edges | Follow Me |
| [SiteContext](https://github.com/mathmati/FreeCAD-SiteContext) | OpenStreetMap buildings and terrain around a picked place | Add Location |
| [Migration Guide](https://github.com/mathmati/FreeCAD-Migration-Guide) | Instructor panel for people coming from Fusion 360/SolidWorks | Instructor |

The Offset and Follow Me buttons sit right after Push/Pull. They are the
sibling addons' own commands, so their icons come from the siblings' own
`Resources/Icons` (`offsettool.svg`, `followme.svg`) through the same
package-locator mechanism detection uses; nothing is copied into Uppercut.
When a sibling is absent its button is omitted, and the Missing-companions
menu note (which uses `uppercut_missing.svg`) says what to install.

## Tool map (SketchUp tool -> Uppercut button)

| SketchUp | Uppercut | Backed by |
|---|---|---|
| Select | Select | own: cancels the active tool, clears the selection |
| Line | Line | SketchLayer_Line |
| Rectangle | Rectangle | SketchLayer_Rectangle |
| Circle | Circle | SketchLayer_Circle |
| Polygon | Polygon | SketchLayer_Polygon (type `8s` mid-tool for the side count) |
| Arc | Arc | SketchLayer_Arc (3-point; commits an open edge, not a face) |
| Push/Pull | Push/Pull | PushPull_PushPull |
| Offset | Offset | OffsetTool_Offset |
| Follow Me | Follow Me | FollowMe_Sweep |
| Move/Rotate | Move/Rotate | own wrapper over FreeCAD's transform manipulator (probes Std_TransformManip, falls back to Std_Transform) |
| Rotate | (menu only) | own wrapper over Draft_Rotate, probed at click time (Draft behavior) |
| Scale | (menu only) | own wrapper over Draft_Scale, probed at click time (Draft behavior) |
| Eraser | Eraser | own: deletes the selection in one undoable transaction; invoked with nothing selected it arms a click-to-delete session (Esc or Eraser again to finish) |
| Make Group | Make Group | own: wraps the selection in a new App::Part, one undoable step |
| Tape Measure | Tape Measure | own wrapper over the unified measure command (probes Std_Measure, falls back to Std_MeasureDistance) |
| Paint Bucket | Paint Bucket | own: small palette popup, per-object color via ViewObject appearance |
| Orbit / standard views | Iso, Top, Front, Right, Fit All | own wrappers over the Std_View* commands |
| Add Location | Add Location | SiteContext_AddLocation |
| Instructor | Instructor | MigrationGuide_ShowPanel; own About dialog if the guide is missing |

Every button has its own icon. The own commands used to share the single
workbench icon, which made the toolbar unreadable; each own command (Select,
Move/Rotate, Rotate, Scale, Eraser, Make Group, Tape Measure, Paint Bucket,
the five view buttons, About, Restore navigation, Missing companions) now
maps to a distinct hand-drawn SVG in `Resources/Icons/`, resolved through
the same icon helper as before. `uppercut.svg` stays as the workbench icon.

## Shortcuts

The main tools get SketchUp's single-letter shortcuts, written at workbench
activation into FreeCAD's own shortcut parameters
(`User parameter:BaseApp/Shortcut`), so they show up and can be remapped in
Tools > Customize > Keyboard:

| Key | Tool | Command |
|---|---|---|
| Space | Select | Uppercut_Select |
| L | Line | SketchLayer_Line |
| R | Rectangle | SketchLayer_Rectangle |
| C | Circle | SketchLayer_Circle |
| A | Arc | SketchLayer_Arc |
| G | Polygon | SketchLayer_Polygon |
| P | Push/Pull | PushPull_PushPull |
| E | Eraser | Uppercut_Eraser |
| T | Tape Measure | Uppercut_TapeMeasure |
| B | Paint Bucket | Uppercut_PaintBucket |
| M | Move/Rotate | Uppercut_MoveRotate |
| F | Offset | OffsetTool_Offset |
| Q | Rotate | Uppercut_Rotate (wraps Draft_Rotate) |
| S | Scale | Uppercut_Scale (wraps Draft_Scale) |

Two safety rules. First, a binding whose accelerator is already taken by
another command (found through `Gui.Command` accelerator introspection) is
skipped with a status-bar note instead of clobbering the existing binding;
bindings for tools whose addon is not installed are skipped too. Second,
the letters cannot fire while a SketchLayer draw tool is active: the tool's
application-level event filter gets `ShortcutOverride` first and reserves
bare letters and Space for the tool, so typing `8s` for polygon sides or
moving the mouse mid-draw never triggers an accelerator. Follow Me has no
default letter (SketchUp does not ship one either); bind one in Customize
if you want it.

## Active-tool highlight

The armed tool's toolbar button looks pressed, the way SketchUp shows it.
Arming Line, Rectangle, Circle, Polygon, Arc or the Eraser checks its
button; committing, cancelling, Esc or starting another tool clears it. At
most one button is checked at a time (radio behavior), and Select lights
as the neutral tool. One-shot commands (the view buttons, Make Group,
Paint Bucket, About) complete instantly, so they never light.

The state lives in `freecad/UppercutWB/toolstate.py`: a small radio
tracker plus a Qt adapter that finds a command's QAction in the main
window's toolbars. On FreeCAD 1.1.1 every toolbar action carries its
command name in both `objectName()` and `data()` (verified in a live GUI
probe; `Gui.Command.get(name).getAction()` returns the same action in a
one-element list), so the adapter matches on those and toggles the checked
state. The tracker logic is Qt-free and tested headless with fakes.

SketchLayer's draw tools report their start and finish through a soft hook
(`from freecad.UppercutWB import toolstate`, a no-op when Uppercut is not
installed). PushPull joins with the same three lines, placed where its
tool arms and where it commits or cancels:

```python
try:
    from freecad.UppercutWB import toolstate
except ImportError:
    toolstate = None

# where the tool arms:        if toolstate is not None: toolstate.mark_active("PushPull_PushPull")
# where it commits/cancels:   if toolstate is not None: toolstate.mark_inactive("PushPull_PushPull")
```

Nothing breaks when Uppercut is absent, and the radio tracker clears the
previous tool's button when PushPull arms.

## Eraser modes

With a selection, Eraser deletes it in one undoable transaction, no
confirmation dialog. With nothing selected, Eraser arms a click-to-delete
session: the status bar prompts "click an object to delete it", each click
deletes the object under the cursor (one undo step per object), and Esc or
invoking Eraser again disarms. The pick under the cursor uses the view's
own `getObjectInfo`, no custom picking code.

## Navigation style

First activation asks once, in a small dialog with three answers:

- "This workbench only" (the default): the open 3D views switch to
  FreeCAD's Blender style, the stock style with the SketchUp mouse map
  (middle-mouse orbit, Shift+middle pan, wheel zoom). Your previous style
  is restored when you leave the workbench, or via Uppercut menu >
  Restore navigation.
- "Everywhere": additionally writes FreeCAD's global navigation preference
  (`BaseApp/Preferences/View` key `NavigationStyle`, the same key the Tux
  indicator writes), so every workbench and every newly opened view orbits
  on middle-mouse hold. The prior global value is remembered, and Restore
  navigation reverts it. This choice is for people who want the SketchUp
  camera everywhere; it deliberately does not auto-restore on workbench
  switch.
- "No thanks": nothing is changed.

The per-view default applies to ALL open 3D views, not just the active one
(views are enumerated through
`Gui.getDocument(name).mdiViewsOfType("Gui::View3DInventor")`), and a hook
on the main window's MDI area (`subWindowActivated`, verified in a live
probe to fire for newly created views) switches views opened or focused
while the workbench is active. That hook matters because the global
default style (`Gui::CADNavigationStyle`) orbits on Ctrl+right-drag, not
on middle-mouse hold: without it, a view created mid-session silently came
up without the SketchUp mouse map, which read as a regression.

Consent, the applied flags and the saved styles live in
`App.ParamGet("User parameter:BaseApp/Uppercut")`; the restore paths only
run when Uppercut actually changed something, and no setting is changed
without the dialog. The switch uses the view's `setNavigationType()` (the
Python name in FreeCAD 1.1.1; `setNavigationStyle()` is probed too but
does not exist there). If no view accepts it, it falls back to the user
preference parameter with a status-bar note. When several open views had
different styles, the first view's style is the one saved and restored to
all (views share the user's default in practice).

## Requirements

FreeCAD 1.1 or newer (developed and verified against 1.1.1). No
dependencies beyond what FreeCAD itself ships (PySide). All four companions
are optional; any subset works.

## Verification

`verify/headless_regression.py` passes 36/36 checks under freecadcmd
(FreeCAD 1.1.1, bundled Python 3.11.14, Windows 11). Run log:
`verify/out-headless.txt`. Covered: toolbar assembly (full house with the
five SketchLayer draw commands plus Offset and Follow Me right after
Push/Pull, each sibling missing, an older Line/Rectangle-only SketchLayer,
Move/Rotate and Tape Measure probe fallbacks, separator hygiene), a static
cross-check of every sibling command name against the siblings' own
commands.py sources, dependency detection through both the live and the
static path, the eraser core on a real document (transaction delete, undo
restores, empty selection no-op) plus the armed click-to-delete session
(arm/disarm/toggle, delete only while armed), Make Group on a real document
(two boxes into one App::Part, undo restores, empty selection no-op), the
shortcut logic (SketchUp letter-map completeness, conflict-skip and
unavailable-skip with fake owners, the `BaseApp/Shortcut` parameter
round-trip, and the `Gui.Command` accelerator introspection against a fake
command manager), the sibling icon path resolution through the package
locator with the missing-icon fallback, the paint RGBA core, the own-command
icon map (every own command has a distinct SVG that exists on disk), the
active-tool highlight (the radio tracker and the Qt action lookup, both
with fakes, plus a static xref of the wiring points in commands.py and
init_gui.py), and the navigation logic (parameter round-trips, view API
probe order, the consent mode state machine including the legacy boolean
state, the "everywhere" global preference write and restore with the prior
value recorded, apply/restore across all open views with a fake gui, and
the keep-applied watcher's decision logic). Two environment quirks surfaced:
freecadcmd creates documents with `UndoMode` 0 (no undo recording), so the
eraser test enables it explicitly (the GUI default is 1); and freecadcmd
imports installed Mod addons at startup, so the regression drops a possibly
pre-imported `freecad.UppercutWB` (and any stale pre-rename
`freecad.SketchUIWB`) from `sys.modules` to test this checkout
rather than an installed copy.

`verify/drivers/highlight_driver.py` passes 10/10 in a real FreeCAD 1.1.1
GUI run (Windows 11; result file
`verify/out/highlight_driver.result.txt`, log
`verify/out/highlight_driver.log`). It activates the workbench and asserts,
live: `getNavigationType()` reports the Blender style on every open view,
including a view created after activation (the keep-applied hook); arming
Line through the real registered command checks its button and only its
button; starting Circle moves the highlight (radio); Esc clears it; a
typed rectangle commit clears it; the armed Eraser highlights and Esc
disarms it; Select lights as the neutral tool while Fit All never does;
and "everywhere" writes the global preference, with the menu restore
reverting it and the views to the recorded prior value. The run also
surfaced and fixed a real bug: the armed Eraser's event filter probed
`event.key()` before checking the event type, so it threw on non-keyboard
events (timer, action-change) delivered to the application-level filter.

`verify/drivers/uppercut_driver.py` (a smaller earlier driver: activate,
assert the toolbar exists, screenshot) remains UNVERIFIED; the highlight
driver covers the same ground and much more, for real.

## Known gaps (disclosed up front)

- Move/Rotate, Tape Measure, Rotate, Scale and the view buttons are
  one-shot wrappers over Std_/Draft commands whose tool sessions Uppercut
  does not track, so they do not get the pressed look; the highlight covers
  the SketchLayer draw tools, the armed Eraser and Select (PushPull once it
  picks up the three-line hook from the Active-tool highlight section).
- The consent dialog itself and the shortcut application are GUI-only and
  have no automated coverage; only the logic behind them is tested
  headless, and the highlight driver exercises the rest in a real GUI run.
- No freehand tool in v1. SketchLayer's Arc commits an open edge, not a face
  (same as SketchUp), and the polygon side count is set by typing `<n>s`
  mid-tool only; there is no settings field for it.
- Follow Me has no default shortcut letter; the rest of the map is in the
  Shortcuts section. Conflicting accelerators are skipped, not clobbered.
- Rotate and Scale are thin wrappers over Draft_Rotate and Draft_Scale,
  probed at click time (importing DraftTools if the command is not
  registered yet). Their behavior is whatever the Draft tools do in 1.1.1;
  the probe was verified by inspection, not headless, because freecadcmd has
  no command manager.
- Make Group produces an `App::Part` container, not a parametric component;
  moving the group moves its members (standard App::Part behavior).
- Paint Bucket colors whole objects (body level), not individual faces.
- Move/Rotate and Tape Measure are thin wrappers; their behavior is whatever
  the underlying Std_TransformManip and Std_Measure do in 1.1.1.
- Eraser deletes selected document objects. Sub-element deletion (a face or
  edge inside a body) is out of scope.
- If a companion is installed but its commands module fails to import at
  Uppercut startup, its buttons are omitted rather than left dead, and the
  menu note points at the companion.
- Not internationalized (UI strings are plain Python).

## Context and prior art

Uppercut is an umbrella over six addons I already maintain (PushPull,
SketchLayer, Offset, FollowMe, SiteContext, Migration Guide); it does not
re-implement their features, it assembles them and adds small glue tools. FreeCAD 1.1 itself
moved part of the way here: the Tux navigation indicator does per-user
navigation-style switching, the unified Measure command landed in 1.0, and
PartDesign features got interactive gizmos in 1.1. This workbench is a
curated subset aimed at users coming from SketchUp, not a replacement for
the standard workbenches. The addon name and icon steer clear of the
SketchUp trademark; "SketchUp-style" is used descriptively only.

## License

MIT, see `LICENSE`.

## Transparency

Built with AI assistance (Kimi Code); reviewed by a human.
