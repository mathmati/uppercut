# SPDX-License-Identifier: MIT
"""Make Group core: wrap the current selection in a new ``App::Part``.

App-side only; nothing here imports the GUI. The Uppercut_MakeGroup command
passes in ``Gui.Selection.getSelection()``; tests pass plain object lists
built on a real freecadcmd document, so the group/undo path is covered
headless.
"""


def make_group(doc, objects):
    """Move ``objects`` into a new ``App::Part`` in ``doc``, in one
    transaction.

    ``objects``: iterable of App.DocumentObject (duplicates, None entries,
    and objects that are not in ``doc`` are ignored). Returns
    ``{"group": name or None, "moved": [names...], "message": str}``.
    Grouping nothing is a no-op with a message, not an error. Undo
    (``doc.undo()``) removes the group and returns the members to the
    document root.
    """
    seen = set()
    members = []
    for obj in objects or []:
        name = getattr(obj, "Name", None)
        if not name or name in seen:
            continue
        if doc.getObject(name) is None:  # stale reference or other document
            continue
        seen.add(name)
        members.append(obj)
    if not members:
        return {
            "group": None,
            "moved": [],
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
    return {
        "group": grp.Name,
        "moved": [obj.Name for obj in members],
        "message": "Make Group: grouped %d object(s) into '%s'"
                   % (len(members), grp.Name),
    }
