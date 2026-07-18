# SPDX-License-Identifier: MIT
"""Eraser core: delete the current selection in one undoable transaction.

App-side only; nothing here imports the GUI. The Uppercut_Eraser command
passes in ``Gui.Selection.getSelection()``; tests pass plain object lists
built on a real freecadcmd document, so the whole delete/undo path is
covered headless.

Two safety rules, both verified against FreeCAD 1.1 behavior:

* Deleting a container (Body, App::Part, group) also deletes what is inside
  it. Bare ``removeObject`` on a container leaves its members floating loose
  in the document, which no SketchUp user expects.
* Nothing is deleted when something OUTSIDE the deleted set still depends on
  it: removing a Sketch a Pad uses leaves the Pad permanently Invalid with
  no warning. The eraser refuses atomically and says which object is in the
  way, instead of leaving broken features behind.
"""


def _parent_group(obj):
    try:
        return obj.getParentGeoFeatureGroup()
    except Exception:  # noqa: BLE001 - older API or odd object
        return None


def _ancestor_names(obj):
    names = set()
    parent = _parent_group(obj)
    while parent is not None and parent.Name not in names:
        names.add(parent.Name)
        parent = _parent_group(parent)
    return names


def _expand(doc, objects):
    """The selected objects plus everything inside selected containers,
    containers first. Deduped; stale references dropped."""
    ordered = []
    seen = set()
    stack = []
    for obj in objects or []:
        name = getattr(obj, "Name", None)
        if name and name not in seen and doc.getObject(name) is not None:
            stack.append(obj)
    while stack:
        obj = stack.pop(0)
        if obj.Name in seen:
            continue
        seen.add(obj.Name)
        ordered.append(obj)
        for member in getattr(obj, "Group", None) or []:
            if getattr(member, "Name", None) and member.Name not in seen:
                stack.append(member)
    return ordered


def _blockers(objects):
    """(object_name, [dependent names]) for every object something outside
    the deleted set still depends on. Containers above an object do not
    count as dependents."""
    names = {obj.Name for obj in objects}
    out = []
    for obj in objects:
        ancestors = _ancestor_names(obj)
        external = []
        for dep in getattr(obj, "InList", None) or []:
            dep_name = getattr(dep, "Name", None)
            if not dep_name or dep_name in names or dep_name in ancestors:
                continue
            if dep_name not in external:
                external.append(dep_name)
        if external:
            out.append((obj.Name, external))
    return out


def delete_objects(doc, objects):
    """Delete ``objects`` (and the contents of selected containers) from
    ``doc`` inside a single transaction.

    ``objects``: iterable of App.DocumentObject (duplicates, None entries,
    and objects that are not in ``doc`` are ignored). Returns
    ``{"deleted": [names...], "blocked": [(name, [dependents])],
    "message": str}``. Deleting nothing is a no-op with a message, not an
    error. When anything outside the deleted set still depends on a
    selected object, NOTHING is deleted (atomic refusal; see module doc).
    Undo (``doc.undo()``) restores the deleted objects.
    """
    expanded = _expand(doc, objects)
    if not expanded:
        return {"deleted": [], "blocked": [],
                "message": "Eraser: nothing selected"}

    blocked = _blockers(expanded)
    if blocked:
        parts = ["%s is used by %s" % (name, ", ".join(deps))
                 for name, deps in blocked]
        return {
            "deleted": [],
            "blocked": blocked,
            "message": ("Eraser: not deleted - %s (delete or select those "
                        "too)" % "; ".join(parts)),
        }

    names = [obj.Name for obj in expanded]
    doc.openTransaction("Eraser: delete %d object(s)" % len(names))
    deleted = []
    try:
        # children before containers, so nothing is orphaned mid-way; an
        # object a container removal already took down is skipped
        for name in reversed(names):
            if doc.getObject(name) is None:
                continue
            doc.removeObject(name)
            deleted.append(name)
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    deleted.reverse()
    return {
        "deleted": deleted,
        "blocked": [],
        "message": "Eraser: deleted %d object(s): %s"
                   % (len(deleted), ", ".join(deleted)),
    }


class EraserSession(object):
    """Armed click-to-delete state (SketchUp's eraser-as-tool mode).

    App-side only. The GUI command arms a session when Eraser is invoked
    with an empty selection, feeds it objects picked under the cursor
    (``delete_picked``), and disarms on Esc or re-invoke; tests drive the
    same methods directly against a real freecadcmd document. The session
    stays armed after each delete so several objects can be clicked away in
    a row, like SketchUp.
    """

    #: Status-bar prompt shown while armed.
    PROMPT = ("Eraser: click an object to delete it "
              "(Esc or Eraser again to finish)")

    def __init__(self, doc):
        self.doc = doc
        self.armed = False
        self.last_message = ""

    def arm(self):
        self.armed = True
        self.last_message = self.PROMPT
        return self.last_message

    def disarm(self):
        self.armed = False
        self.last_message = "Eraser: finished."
        return self.last_message

    def toggle(self):
        """Re-invoking Eraser with no selection flips the armed state."""
        return self.disarm() if self.armed else self.arm()

    def delete_picked(self, obj):
        """Delete the picked object in one transaction. Returns the
        :func:`delete_objects` result, or None when the session is not
        armed or the pick missed (no state change in those cases)."""
        if not self.armed or obj is None:
            return None
        result = delete_objects(self.doc, [obj])
        self.last_message = result["message"]
        return result
