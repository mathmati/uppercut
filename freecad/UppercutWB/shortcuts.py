# SPDX-License-Identifier: MIT
"""Single-letter tool shortcuts (SketchUp muscle memory).

The map is pure data; conflict detection and application are separate, so
everything except the final GUI composition runs headless under freecadcmd:

  * :func:`desired_map` -- ordered (accelerator, command) pairs.
  * :func:`plan_bindings` -- split the map into bindings to apply and
    bindings to skip (target command unavailable, or the accelerator is
    already owned by another command). Skipping never clobbers an existing
    binding; the caller surfaces a status-bar note instead.
  * :func:`apply_bindings` -- write the bindings to
    ``User parameter:BaseApp/Shortcut``, the same store FreeCAD's
    Customize > Keyboard dialog uses, so the user can remap afterwards.
  * :func:`gui_accel_owner` / :func:`apply_all` -- the GUI-time composition:
    build the accelerator->command table through ``Gui.Command``
    introspection, plan, apply. If the introspection API is missing or
    raises, the table is empty (no conflicts detected) and every desired
    binding is applied; stock FreeCAD 1.1.1 ships no single-letter
    accelerators, so that fallback is safe there.

Typed-input safety (verified by inspection, 2026-07-18): while a SketchLayer
draw tool is active, its application-level event filter accepts
ShortcutOverride for every bare letter and Space (SketchLayerWB/commands.py,
``_is_bare_letter_or_space``), so these accelerators cannot fire mid-draw,
and the KeyPress is then consumed by the same filter. The keys the tools
actually type (digits, '.', ',', 'x', 's') still reach the tool first; the
SketchLayer headless suite pins those buffer rules (checks 23-24, 31, 33).
"""
import FreeCAD as App

#: FreeCAD's own shortcut store (what Customize > Keyboard writes).
PARAM_GROUP = "User parameter:BaseApp/Shortcut"

#: The desired SketchUp-style map, in toolbar order. Pure data. FollowMe has
#: no default letter on purpose (SketchUp does not ship one either).
DESIRED_SHORTCUTS = (
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
)

#: Own commands among the map targets; always available once registered, so
#: apply_all adds them to whatever the sibling detection found.
OWN_SHORTCUT_COMMANDS = frozenset(
    cmd for _accel, cmd in DESIRED_SHORTCUTS if cmd.startswith("Uppercut_"))


def desired_map():
    """The desired (accelerator, command) pairs, as a list."""
    return list(DESIRED_SHORTCUTS)


def plan_bindings(available, accel_owner=None):
    """Split the desired map into ``(apply, skipped)``.

    ``available``: iterable of command names that exist (detected siblings
    plus own commands). ``accel_owner``: optional callable
    ``accelerator -> owning command name or None`` (see
    :func:`gui_accel_owner`); a raising lookup is treated as "no conflict
    known". A skipped entry is ``(accelerator, command, reason)`` and never
    gets applied: existing user or workbench bindings win over our defaults.
    """
    avail = set(available)
    apply_list, skipped = [], []
    for accel, command in DESIRED_SHORTCUTS:
        if command not in avail:
            skipped.append((accel, command, "command unavailable"))
            continue
        owner = None
        if accel_owner is not None:
            try:
                owner = accel_owner(accel)
            except Exception:  # noqa: BLE001 - unknown means no conflict
                owner = None
        if owner and owner != command:
            skipped.append((accel, command, "conflicts with %s" % owner))
            continue
        apply_list.append((accel, command))
    return apply_list, skipped


def apply_bindings(bindings, p=None):
    """Write ``(accelerator, command)`` pairs to the shortcut parameter
    group (same store Customize > Keyboard uses; remappable there)."""
    p = p if p is not None else App.ParamGet(PARAM_GROUP)
    for accel, command in bindings:
        p.SetString(command, accel)


def gui_accel_owner(gui):
    """Accelerator -> owning command name, from the live command manager.

    Reads ``cmd.getShortcut()`` where the API exists; commands without the
    method or that raise are skipped. Returns a callable that answers None
    for every accelerator when the manager itself is unusable.
    """
    try:
        names = list(gui.listCommands())
    except Exception:  # noqa: BLE001
        names = []
    table = {}
    for name in names:
        try:
            cmd = gui.Command.get(name)
            shortcut = cmd.getShortcut() if cmd is not None else None
        except Exception:  # noqa: BLE001 - unknown binding, skip
            continue
        if shortcut:
            table.setdefault(shortcut.strip().lower(), name)

    def owner(accel):
        return table.get(accel.strip().lower())

    return owner


def apply_all(gui, available, p=None):
    """Plan against the live command manager and apply. Returns
    ``(applied, skipped)`` so the caller can note conflicts in the status
    bar. Own commands are added to ``available`` unconditionally."""
    avail = set(available) | OWN_SHORTCUT_COMMANDS
    try:
        owner = gui_accel_owner(gui)
    except Exception:  # noqa: BLE001 - treat as "no conflicts known"
        owner = None
    apply_list, skipped = plan_bindings(avail, accel_owner=owner)
    apply_bindings(apply_list, p=p)
    return apply_list, skipped
