# SPDX-License-Identifier: MIT
"""Active-tool highlight: which toolbar button looks pressed, and why.

SketchUp shows the armed tool as a pressed toolbar button; FreeCAD command
buttons give no such feedback by default. This module adds it. Two layers,
deliberately split so the policy is headless-testable with fakes:

* :class:`RadioTracker` -- pure logic. A radio group of one: marking a tool
  active clears the previous tool's highlight, marking inactive clears the
  tool's own. Talks to an adapter object with
  ``set_highlight(command_name, on)`` and never touches Qt itself.
* :class:`QtActionAdapter` -- the GUI side. Finds the QAction of a FreeCAD
  command in the main window's toolbars and drives its checked state.

Qt lookup findings (probed in a real FreeCAD 1.1.1 GUI run, 2026-07-18,
via verify/gui_probe.py): every toolbar QAction carries its command name in
BOTH ``objectName()`` and ``data()`` -- own commands (``Uppercut_Select``),
sibling commands (``SketchLayer_Line``, ``PushPull_PushPull``) and stock
``Std_*`` commands alike. ``Gui.Command.get(name).getAction()`` returns a
one-element list holding that same QAction. The scan below matches
``data()`` first, then ``objectName()``; the one action instance is shared
between toolbar and menu, so checking it covers both. ``setCheckable(True)``
is applied once per action, then only the checked state is toggled.

Re-assert rule: Qt unchecks a checkable action when the user clicks it
again, BEFORE the command runs. So :meth:`RadioTracker.mark_active` always
re-asserts the checked state for the current tool (idempotent), and only
clears the others when the active tool actually changes.

Sibling addons hook in with three lines (PushPull uses exactly this)::

    try:
        from freecad.UppercutWB import toolstate
    except ImportError:
        toolstate = None
    # on tool start:        if toolstate: toolstate.mark_active("PushPull_PushPull")
    # on cancel/commit:     if toolstate: toolstate.mark_inactive("PushPull_PushPull")

The module imports nothing from FreeCAD or PySide at top level, so it loads
under headless freecadcmd and from a sibling addon without side effects.
Module functions (``mark_active`` and friends) delegate to a lazily built
default tracker bound to the real Qt adapter; tests replace
``toolstate._tracker`` or construct ``RadioTracker``/``QtActionAdapter``
with fakes directly.
"""


class RadioTracker(object):
    """Tracks the one active tool command and mirrors it to an adapter.

    ``ui``: object with ``set_highlight(command_name, on)``; a failing
    adapter never breaks the tracking (highlighting is best-effort, the
    tool must keep working). ``_lit`` mirrors the names currently shown
    pressed, whether or not the adapter found a button for them (a button
    can legitimately be missing, e.g. its toolbar was never built).
    """

    def __init__(self, ui):
        self._ui = ui
        self._active = None
        self._lit = set()

    def active(self):
        """Name of the currently active tool command, or None."""
        return self._active

    def lit(self):
        """Names currently shown pressed (copy)."""
        return set(self._lit)

    def mark_active(self, name):
        """Arm ``name``; the previously active tool's highlight clears."""
        if not name:
            return
        if self._active != name:
            for other in sorted(self._lit):
                if other != name:
                    self._set(other, False)
        self._active = name
        # always re-assert (Qt auto-unchecks a checkable action on click)
        self._set(name, True)

    def mark_inactive(self, name):
        """Disarm ``name``. Clears its highlight even if some other tool
        owns the radio slot (a tool reporting it ended must not stay lit),
        but never clears the CURRENT owner's tracked state."""
        if not name:
            return
        if self._active == name:
            self._active = None
        if name in self._lit:
            self._set(name, False)

    def clear_all(self):
        """Drop every highlight and the active-tool state."""
        self._active = None
        for name in sorted(self._lit):
            self._set(name, False)

    def _set(self, name, on):
        try:
            self._ui.set_highlight(name, on)
        except Exception as exc:  # noqa: BLE001 - highlighting is best-effort
            _warn("toolstate: set_highlight(%r, %r) failed: %s" % (name, on, exc))
        if on:
            self._lit.add(name)
        else:
            self._lit.discard(name)


class QtActionAdapter(object):
    """Finds a FreeCAD command's QActions in the main window's toolbars and
    drives their checked state (the pressed look).

    ``gui`` and ``qt`` are injectable for tests; by default FreeCADGui and
    PySide's QtWidgets are imported lazily on first use, so constructing
    the adapter is safe headless.
    """

    def __init__(self, gui=None, qt=None):
        self._gui = gui
        self._qt = qt

    def _gui_mod(self):
        if self._gui is None:
            import FreeCADGui as Gui
            self._gui = Gui
        return self._gui

    def _qt_mod(self):
        if self._qt is None:
            from PySide import QtWidgets
            self._qt = QtWidgets
        return self._qt

    def find_actions(self, name):
        """All toolbar QActions whose ``data()`` or ``objectName()`` is the
        command name. Returns [] when none is found (never raises on a
        missing main window)."""
        gui = self._gui_mod()
        qt = self._qt_mod()
        try:
            window = gui.getMainWindow()
        except Exception:  # noqa: BLE001
            return []
        if window is None:
            return []
        found = []
        for bar in window.findChildren(qt.QToolBar):
            for action in bar.actions():
                try:
                    if action.isSeparator():
                        continue
                    if action.data() == name or action.objectName() == name:
                        found.append(action)
                except Exception:  # noqa: BLE001 - skip a broken action
                    continue
        return found

    def set_highlight(self, name, on):
        """Check/uncheck every action of ``name``; makes the action
        checkable first (once). Returns how many actions were driven."""
        actions = self.find_actions(name)
        for action in actions:
            if not action.isCheckable():
                action.setCheckable(True)
            action.setChecked(bool(on))
        return len(actions)


# --- module-level default tracker (production entry points) -------------------
_tracker = None


def _default_tracker():
    global _tracker
    if _tracker is None:
        _tracker = RadioTracker(QtActionAdapter())
    return _tracker


def mark_active(cmd_name):
    """Arm the highlight for ``cmd_name`` (clears the previous tool's)."""
    try:
        _default_tracker().mark_active(cmd_name)
    except Exception as exc:  # noqa: BLE001 - never break a tool over a highlight
        _warn("toolstate.mark_active(%r) failed: %s" % (cmd_name, exc))


def mark_inactive(cmd_name):
    """Clear the highlight for ``cmd_name``."""
    try:
        _default_tracker().mark_inactive(cmd_name)
    except Exception as exc:  # noqa: BLE001
        _warn("toolstate.mark_inactive(%r) failed: %s" % (cmd_name, exc))


def active():
    """The currently active tool command name, or None."""
    try:
        return _default_tracker().active()
    except Exception:  # noqa: BLE001
        return None


def clear_all():
    """Drop every highlight."""
    try:
        _default_tracker().clear_all()
    except Exception as exc:  # noqa: BLE001
        _warn("toolstate.clear_all() failed: %s" % exc)


def _warn(message):
    try:
        import FreeCAD as App
        App.Console.PrintWarning("Uppercut: %s\n" % message)
    except Exception:  # noqa: BLE001
        pass
