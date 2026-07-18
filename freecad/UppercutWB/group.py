# SPDX-License-Identifier: MIT
"""Make Group core: wrap the current selection in a new ``App::Part``.

App-side only; nothing here imports the GUI. The Uppercut_MakeGroup command
passes in ``Gui.Selection.getSelection()``; tests pass plain object lists
built on a real freecadcmd document, so the group/undo path is covered
headless.

Two safety rules, both verified against FreeCAD 1.1 behavior:

* An object living inside a PartDesign Body (or any GeoFeatureGroup) is
  never pulled out: App::Part.addObject would steal it AND drag its
  dependencies along, emptying the Body. Such selections are skipped with
  a message; group the Body itself instead.
* When a container and something inside it are both selected (Ctrl+A does
  this), only the container is grouped; the child entry is dropped.
"""


def _parent_group(obj):
    try:
        return obj.getParentGeoFeatureGroup()
    except Exception:  # noqa: BLE001 - older API or odd object
        return None


def _ancestors(obj):
    """The chain of containers above ``obj`` (nearest first)."""
    out = []
    seen = set()
    parent = _parent_group(obj)
    while parent is not None and parent.Name not in seen:
        out.append(parent)
        seen.add(parent.Name)
        parent = _parent_group(parent)
    return out


def make_group(doc, objects):
    """Move ``objects`` into a new ``App::Part`` in ``doc``, in one
    transaction.

    ``objects``: iterable of App.DocumentObject (duplicates, None entries,
    and objects that are not in ``doc`` are ignored). Objects inside a Body
    or other feature group are skipped (see module doc); children of a
    selected container are deduped to the container. Returns
    ``{"group": name or None, "moved": [names...], "skipped": [names...],
    "message": str}``. Grouping nothing is a no-op with a message, not an
    error. Undo (``doc.undo()``) removes the group and returns the members
    to where they were.
    """
    seen = set()
    candidates = []
    for obj in objects or []:
        name = getattr(obj, "Name", None)
        if not name or name in seen:
            continue
        if doc.getObject(name) is None:  # stale reference or other document
            continue
        seen.add(name)
        candidates.append(obj)

    selected_names = set(seen)
    members, skipped = [], []
    for obj in candidates:
        ancestors = _ancestors(obj)
        # a selected ancestor covers this object; drop the child quietly
        if any(a.Name in selected_names for a in ancestors):
            continue
        # never pull a feature out of its Body/feature group
        if ancestors:
            skipped.append(obj.Name)
            continue
        members.append(obj)

    if not members:
        if skipped:
            return {
                "group": None,
                "moved": [],
                "skipped": skipped,
                "message": ("Make Group: %s belong(s) to a body or group; "
                            "select the body itself to group it"
                            % ", ".join(skipped)),
            }
        return {
            "group": None,
            "moved": [],
            "skipped": [],
            "message": "Make Group: nothing to group (select objects first)",
        }

    doc.openTransaction("Make Group (%d object(s))" % len(members))
    try:
        grp = doc.addObject("App::Part", "Group")
        for obj in members:
            grp.addObject(obj)
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    message = ("Make Group: grouped %d object(s) into '%s'"
               % (len(members), grp.Name))
    if skipped:
        message += ("; skipped %s (inside a body or group)"
                    % ", ".join(skipped))
    return {
        "group": grp.Name,
        "moved": [obj.Name for obj in members],
        "skipped": skipped,
        "message": message,
    }
