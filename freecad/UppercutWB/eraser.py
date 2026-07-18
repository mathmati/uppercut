# SPDX-License-Identifier: MIT
"""Eraser core: delete the current selection in one undoable transaction.

App-side only; nothing here imports the GUI. The Uppercut_Eraser command
passes in ``Gui.Selection.getSelection()``; tests pass plain object lists
built on a real freecadcmd document, so the whole delete/undo path is
covered headless.
"""


def delete_objects(doc, objects):
    """Delete ``objects`` from ``doc`` inside a single transaction.

    ``objects``: iterable of App.DocumentObject (duplicates, None entries,
    and objects that are not in ``doc`` are ignored). Returns
    ``{"deleted": [names...], "message": str}``. Deleting nothing is a
    no-op with a message, not an error. Undo (``doc.undo()``) restores the
    deleted objects.
    """
    seen = set()
    names = []
    for obj in objects or []:
        name = getattr(obj, "Name", None)
        if not name or name in seen:
            continue
        if doc.getObject(name) is None:  # stale reference or other document
            continue
        seen.add(name)
        names.append(name)
    if not names:
        return {"deleted": [], "message": "Eraser: nothing selected"}
    doc.openTransaction("Eraser: delete %d object(s)" % len(names))
    try:
        for name in names:
            doc.removeObject(name)
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    return {
        "deleted": names,
        "message": "Eraser: deleted %d object(s): %s"
                   % (len(names), ", ".join(names)),
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
