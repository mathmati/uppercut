# SPDX-License-Identifier: MIT
"""Paint Bucket: RGBA core (pure, headless-testable) plus the GUI adapter.

The core builds and validates the (r, g, b, a) float tuple; the GUI side
(``apply_to_view_objects`` and the palette popup in commands.py) only passes
it through to ViewObject appearance properties. Per-object coloring only:
whole bodies/objects, not individual faces (disclosed in the README).
"""

#: Palette shown by the popup, in order: (label, (r, g, b)) with 0..1 floats.
PALETTE = (
    ("White", (1.0, 1.0, 1.0)),
    ("Light gray", (0.75, 0.75, 0.75)),
    ("Dark gray", (0.35, 0.35, 0.35)),
    ("Black", (0.05, 0.05, 0.05)),
    ("Red", (0.85, 0.20, 0.15)),
    ("Orange", (0.95, 0.55, 0.15)),
    ("Yellow", (0.95, 0.85, 0.20)),
    ("Green", (0.30, 0.65, 0.25)),
    ("Blue", (0.20, 0.45, 0.80)),
    ("Brown", (0.50, 0.35, 0.20)),
)

_PALETTE_BY_NAME = {label.lower(): rgb for label, rgb in PALETTE}


def _clamp01(value, what):
    v = float(value)
    if not 0.0 <= v <= 1.0:
        raise ValueError("%s %r is outside 0..1" % (what, value))
    return v


def build_rgba(color, alpha=1.0):
    """Build the (r, g, b, a) tuple of 0..1 floats for ``color``.

    ``color`` is either a palette name (case-insensitive) or an (r, g, b)
    or (r, g, b, a) sequence of numbers in 0..1. ``alpha`` applies only when
    ``color`` has no alpha of its own. Raises ValueError on anything else.
    """
    if isinstance(color, str):
        rgb = _PALETTE_BY_NAME.get(color.strip().lower())
        if rgb is None:
            raise ValueError("unknown palette color %r" % (color,))
        r, g, b = rgb
        a = alpha
    else:
        try:
            parts = list(color)
        except TypeError:
            raise ValueError("not a color: %r" % (color,))
        if len(parts) == 3:
            r, g, b = parts
            a = alpha
        elif len(parts) == 4:
            r, g, b, a = parts
        else:
            raise ValueError(
                "expected a palette name or 3/4 numbers, got %r" % (color,))
        r = _clamp01(r, "red")
        g = _clamp01(g, "green")
        b = _clamp01(b, "blue")
    return (r, g, b, _clamp01(a, "alpha"))


def apply_to_view_objects(view_objects, rgba):
    """Apply ``rgba`` to each ViewObject's appearance. Returns the count.

    GUI-only caller side: pass ``obj.ViewObject`` for each selected object.
    Per-object coloring: sets ShapeColor and a single DiffuseColor entry
    (FreeCAD broadcasts it over the shape's faces). Objects that reject the
    assignment are skipped, not fatal.
    """
    count = 0
    rgb = rgba[:3]
    for vo in view_objects or []:
        if vo is None:
            continue
        try:
            vo.ShapeColor = rgb
            vo.DiffuseColor = [rgba]
        except Exception:  # noqa: BLE001 - skip objects without a colorable view
            continue
        count += 1
    return count
