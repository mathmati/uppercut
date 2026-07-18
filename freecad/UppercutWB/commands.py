# SPDX-License-Identifier: MIT
"""Uppercut's own FreeCAD Gui.Command subclasses.

Everything here is GUI-only (imported from init_gui's Initialize). The
testable logic behind the commands lives in assembly.py, eraser.py,
group.py, paint.py, navstyle.py and shortcuts.py; these classes are thin
adapters.
"""
import importlib
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from . import assembly, eraser, group, navstyle, paint, toolstate

_ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Resources",
    "Icons",
)


def _icon(name):
    return os.path.join(_ICON_DIR, name)


def _status(message, timeout=6000):
    """Status-bar feedback; falls back to the console when headless-ish."""
    try:
        Gui.getMainWindow().statusBar().showMessage(message, timeout)
    except Exception:  # noqa: BLE001
        pass
    App.Console.PrintMessage("Uppercut: %s\n" % message)


def _resources(menu_text, tooltip, command_name=None):
    """Resources for one own command. Each command gets its own icon from
    assembly.ICONS (distinct, hand-drawn SVGs); anything unlisted falls back
    to the workbench icon uppercut.svg."""
    icon = assembly.ICONS.get(command_name, assembly.DEFAULT_ICON)
    return {"MenuText": menu_text, "ToolTip": tooltip, "Pixmap": _icon(icon)}


class _SelectCommand(object):
    """Plain selection mode: cancels any active tool, clears the selection."""

    def GetResources(self):
        return _resources(
            "Select",
            "Plain selection mode (cancels the active tool, clears the selection)",
            assembly.CMD_SELECT,
        )

    def IsActive(self):
        return True

    def Activated(self):
        # Close an open task dialog (Pad/Pocket editor, etc.).
        try:
            Gui.Control.closeDialog()
        except Exception:  # noqa: BLE001
            pass
        # Leave any object edit mode.
        try:
            if Gui.ActiveDocument is not None:
                Gui.ActiveDocument.resetEdit()
        except Exception:  # noqa: BLE001
            pass
        # Esc to the focused widget cancels interactive tools (Draft-style
        # event-filter tools listen for it). Best-effort only.
        try:
            from PySide import QtCore, QtGui, QtWidgets

            app = QtWidgets.QApplication.instance()
            if app is not None:
                target = app.focusWidget() or Gui.getMainWindow()
                for etype in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                    app.sendEvent(target, QtGui.QKeyEvent(
                        etype, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier))
        except Exception:  # noqa: BLE001
            pass
        Gui.Selection.clearSelection()
        # Select is the neutral tool: any tool it cancelled cleared itself
        # above (Esc path); the radio takes care of anything left lit.
        toolstate.mark_active(assembly.CMD_SELECT)
        _status("Select: plain selection mode")


class _RelayCommand(object):
    """Wrapper that relays to the first available built-in command.

    One toolbar button hides the version differences between FreeCAD
    releases: the candidates are probed at click time through the command
    manager, so a renamed/removed built-in degrades to a status message
    instead of a dead button. (assembly.build_toolbar already omits the
    button entirely when no candidate was found at activation time.)
    """

    MENU_TEXT = ""
    TOOLTIP = ""
    CANDIDATES = ()
    NEEDS_SELECTION = False
    COMMAND_NAME = None  # assembly.ICONS key; subclasses set it

    def GetResources(self):
        return _resources(self.MENU_TEXT, self.TOOLTIP, self.COMMAND_NAME)

    def IsActive(self):
        return True

    def resolve(self):
        for name in self.CANDIDATES:
            try:
                if Gui.Command.get(name) is not None:
                    return name
            except Exception:  # noqa: BLE001
                continue
        return None

    def Activated(self):
        name = self.resolve()
        if name is None:
            _status("%s: no matching built-in command found (%s)"
                    % (self.MENU_TEXT, ", ".join(self.CANDIDATES)))
            return
        if self.NEEDS_SELECTION and not Gui.Selection.getSelection():
            _status("%s: select an object first" % self.MENU_TEXT)
            return
        Gui.runCommand(name)


class _MoveRotateCommand(_RelayCommand):
    MENU_TEXT = "Move/Rotate"
    TOOLTIP = ("Move/rotate the selected object with FreeCAD's transform "
               "manipulator")
    CANDIDATES = assembly.TRANSFORM_COMMANDS
    NEEDS_SELECTION = True
    COMMAND_NAME = assembly.CMD_MOVE_ROTATE


class _TapeMeasureCommand(_RelayCommand):
    MENU_TEXT = "Tape Measure"
    TOOLTIP = "Measure distances and angles (FreeCAD's unified Measure tool)"
    CANDIDATES = assembly.MEASURE_COMMANDS
    COMMAND_NAME = assembly.CMD_TAPE_MEASURE


def _make_view_command(own_name, std_name, menu_text):
    return type(own_name.replace("Uppercut_", "") + "Command", (_RelayCommand,), {
        "MENU_TEXT": menu_text,
        "TOOLTIP": "Switch to the %s view" % menu_text.lower(),
        "CANDIDATES": (std_name,),
        "COMMAND_NAME": own_name,
    })


_VIEW_LABELS = {
    "Uppercut_ViewIso": "Isometric",
    "Uppercut_ViewTop": "Top",
    "Uppercut_ViewFront": "Front",
    "Uppercut_ViewRight": "Right",
    "Uppercut_ViewFitAll": "Fit All",
}


class _DraftToolCommand(object):
    """Wrapper over a Draft command, probed at click time.

    Draft registers its GUI commands lazily (on Draft workbench activation,
    or when DraftTools is imported), so a startup probe can come back empty
    even though Draft is installed: resolve() first asks the command
    manager, then tries importing DraftTools to force registration, then
    gives up with a status message. That probe-at-runtime guard is the
    documented contract; the tool's behavior is whatever Draft's command
    does in this FreeCAD build (freecadcmd has no command manager, so only
    the guard structure is exercised headless).
    """

    MENU_TEXT = ""
    TOOLTIP = ""
    DRAFT_COMMAND = ""
    COMMAND_NAME = None  # assembly.ICONS key; subclasses set it

    def GetResources(self):
        return _resources(self.MENU_TEXT, self.TOOLTIP, self.COMMAND_NAME)

    def IsActive(self):
        return True

    def resolve(self):
        try:
            if Gui.Command.get(self.DRAFT_COMMAND) is not None:
                return self.DRAFT_COMMAND
        except Exception:  # noqa: BLE001
            pass
        try:
            import DraftTools  # noqa: F401 - force-registers Draft commands
            if Gui.Command.get(self.DRAFT_COMMAND) is not None:
                return self.DRAFT_COMMAND
        except Exception:  # noqa: BLE001
            pass
        return None

    def Activated(self):
        name = self.resolve()
        if name is None:
            _status("%s: %s not found (Draft workbench unavailable?)"
                    % (self.MENU_TEXT, self.DRAFT_COMMAND))
            return
        Gui.runCommand(name)


class _RotateCommand(_DraftToolCommand):
    MENU_TEXT = "Rotate"
    TOOLTIP = ("Rotate the selection with the Draft workbench's rotate tool "
               "(Draft_Rotate; Draft tool behavior)")
    DRAFT_COMMAND = "Draft_Rotate"
    COMMAND_NAME = assembly.CMD_ROTATE


class _ScaleCommand(_DraftToolCommand):
    MENU_TEXT = "Scale"
    TOOLTIP = ("Scale the selection with the Draft workbench's scale tool "
               "(Draft_Scale; Draft tool behavior)")
    DRAFT_COMMAND = "Draft_Scale"
    COMMAND_NAME = assembly.CMD_SCALE


class _EraserCommand(object):
    """Two SketchUp eraser modes:

    * invoked WITH a selection: delete it in one undoable transaction;
    * invoked with NO selection: arm a click-to-delete session -- each
      click deletes the object under the cursor, Esc or re-invoking Eraser
      disarms (the session state lives in eraser.EraserSession).
    """

    _session = None      # eraser.EraserSession while armed
    _view = None
    _sg_callback = None
    _key_filter = None

    def GetResources(self):
        return _resources(
            "Eraser",
            "Delete the selected objects (single undo step, no "
            "confirmation); with nothing selected, click objects to delete "
            "them (Esc to finish)",
            assembly.CMD_ERASER,
        )

    def IsActive(self):
        return True

    def Activated(self):
        doc = App.ActiveDocument
        if doc is None:
            _status("Eraser: no active document")
            return
        # Re-invoking while armed disarms (SketchUp toggle).
        if _EraserCommand._session is not None and \
                _EraserCommand._session.armed:
            self._disarm()
            return
        selection = Gui.Selection.getSelection()
        if selection:
            result = eraser.delete_objects(doc, selection)
            _status(result["message"])
            return
        self._arm(doc)

    # -- armed click-to-delete session ----------------------------------
    def _arm(self, doc):
        session = eraser.EraserSession(doc)
        session.arm()
        _EraserCommand._session = session
        gui_doc = Gui.ActiveDocument
        view = getattr(gui_doc, "ActiveView", None) if gui_doc else None
        if view is not None:
            _EraserCommand._view = view
            _EraserCommand._sg_callback = view.addEventCallback(
                "SoEvent", self._on_event)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            _EraserCommand._key_filter = _EraserKeyFilter(self)
            app.installEventFilter(_EraserCommand._key_filter)
        toolstate.mark_active(assembly.CMD_ERASER)
        _status(session.last_message)

    def _disarm(self):
        session = _EraserCommand._session
        message = session.disarm() if session is not None else "Eraser: finished."
        self._teardown_callbacks()
        _EraserCommand._session = None
        toolstate.mark_inactive(assembly.CMD_ERASER)
        _status(message)

    def _teardown_callbacks(self):
        if _EraserCommand._view is not None and \
                _EraserCommand._sg_callback is not None:
            try:
                _EraserCommand._view.removeEventCallback(
                    "SoEvent", _EraserCommand._sg_callback)
            except Exception:  # noqa: BLE001
                pass
        _EraserCommand._sg_callback = None
        _EraserCommand._view = None
        if _EraserCommand._key_filter is not None:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.removeEventFilter(_EraserCommand._key_filter)
            _EraserCommand._key_filter = None

    def _on_event(self, arg):
        session = _EraserCommand._session
        if session is None or not session.armed:
            self._teardown_callbacks()
            return
        etype = arg.get("Type")
        if etype == "SoKeyboardEvent" and arg.get("Key") == "ESCAPE":
            self._disarm()
            return
        if etype != "SoMouseButtonEvent":
            return
        if arg.get("Button") != "BUTTON1" or arg.get("State") != "DOWN":
            return
        obj = self._picked_object(arg.get("Position"))
        result = session.delete_picked(obj)
        if result is not None:
            _status(result["message"])

    def _picked_object(self, pos):
        """The top object under the cursor, via the view's own pick info."""
        if pos is None or _EraserCommand._view is None:
            return None
        try:
            info = _EraserCommand._view.getObjectInfo((pos[0], pos[1]))
        except Exception:  # noqa: BLE001
            return None
        if not info:
            return None
        name = info.get("Object")
        doc = App.ActiveDocument
        if not name or doc is None:
            return None
        return doc.getObject(name)


class _EraserKeyFilter(QtCore.QObject):
    """Esc handling for the armed eraser (application-level, so the 3D
    view's own shortcuts cannot swallow it -- the PushPull idiom)."""

    def __init__(self, command):
        super().__init__()
        self._command = command

    def eventFilter(self, obj, event):
        session = _EraserCommand._session
        if session is None or not session.armed:
            return False
        # check the type first: an application-level filter sees EVERY event
        # (timers, child events, action changes), and only key events have
        # key() -- probing it on anything else throws inside Qt's delivery
        etype = event.type()
        if etype not in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            return False
        if event.key() != QtCore.Qt.Key_Escape:
            return False
        if etype == QtCore.QEvent.ShortcutOverride:
            event.accept()
            return False
        self._command._disarm()
        return True


class _MakeGroupCommand(object):
    """Wraps the selection in a new App::Part (one undoable transaction)."""

    def GetResources(self):
        return _resources(
            "Make Group",
            "Wrap the selected objects in a new group (App::Part), one "
            "undoable step",
            assembly.CMD_MAKE_GROUP,
        )

    def IsActive(self):
        return True

    def Activated(self):
        doc = App.ActiveDocument
        if doc is None:
            _status("Make Group: no active document")
            return
        selection = Gui.Selection.getSelection()
        if not selection:
            _status("Make Group: select objects first")
            return
        result = group.make_group(doc, selection)
        _status(result["message"])


class _PaintBucketCommand(object):
    """Palette popup; colors the selected objects (per-object, not per-face)."""

    def GetResources(self):
        return _resources(
            "Paint Bucket",
            "Apply a color to the selected objects (whole objects, not faces)",
            assembly.CMD_PAINT,
        )

    def IsActive(self):
        return True

    def Activated(self):
        selection = Gui.Selection.getSelection()
        if not selection:
            _status("Paint Bucket: select an object first")
            return
        try:
            from PySide import QtGui, QtWidgets
        except ImportError:
            _status("Paint Bucket: PySide unavailable")
            return
        menu = QtWidgets.QMenu(Gui.getMainWindow())
        for label, rgb in paint.PALETTE:
            pixmap = QtGui.QPixmap(16, 16)
            pixmap.fill(QtGui.QColor.fromRgbF(rgb[0], rgb[1], rgb[2]))
            menu.addAction(QtGui.QIcon(pixmap), label)
        chosen = menu.exec_(QtGui.QCursor.pos())
        if chosen is None:
            return
        rgba = paint.build_rgba(chosen.text())
        count = paint.apply_to_view_objects(
            [obj.ViewObject for obj in selection], rgba)
        _status("Paint Bucket: colored %d object(s) %s" % (count, chosen.text()))


class _AboutCommand(object):
    """About/companions dialog: which sibling addons were found or are missing."""

    def GetResources(self):
        return _resources(
            "About/companions",
            "Uppercut version, and which companion addons were found or are "
            "missing (with install hints)",
            assembly.CMD_ABOUT,
        )

    def IsActive(self):
        return True

    def Activated(self):
        from . import dialogs

        dialogs.show_about(detect_available())


class _RestoreNavigationCommand(object):
    """Restores the navigation style(s) saved before Uppercut switched them:
    the per-view switch and/or the "everywhere" global preference write."""

    def GetResources(self):
        return _resources(
            "Restore navigation",
            "Restore the navigation style that was active before Uppercut's "
            "SketchUp-style switch (per-view and/or the global preference)",
            assembly.CMD_RESTORE_NAV,
        )

    def IsActive(self):
        return True

    def Activated(self):
        result = navstyle.restore_navigation(Gui)
        if result == "restored":
            _status("Navigation style restored")
        elif result == "nothing":
            _status("Navigation style was not changed by Uppercut; nothing to restore")
        else:
            _status("Could not restore the navigation style")


class _MissingNoteCommand(object):
    """Menu note naming the missing companions; opens the About dialog."""

    def __init__(self, titles):
        self._titles = titles

    def GetResources(self):
        return _resources(
            "Missing companions: %s" % ", ".join(self._titles),
            "These companion addons were not detected. Click for install hints.",
            assembly.CMD_MISSING_NOTE,
        )

    def IsActive(self):
        return True

    def Activated(self):
        from . import dialogs

        dialogs.show_about(detect_available())


# --- registration -------------------------------------------------------------
def ensure_sibling_commands():
    """Force-register installed siblings' commands (they register lazily).

    Sibling workbenches register their commands in their own Initialize(),
    which FreeCAD only runs on first activation of that workbench. An
    umbrella toolbar needs them now, so import each sibling's commands
    module and call its register(). A sibling that fails to import is
    skipped; its buttons are then omitted by the caller.
    """
    for sib in assembly.SIBLINGS:
        for name in sib.commands:
            try:
                if Gui.Command.get(name) is not None:
                    continue
            except Exception:  # noqa: BLE001
                pass
            try:
                module = importlib.import_module(sib.package + ".commands")
                register_fn = getattr(module, "register", None)
                if callable(register_fn):
                    register_fn()
            except Exception as exc:  # noqa: BLE001 - skip a broken sibling
                App.Console.PrintWarning(
                    "Uppercut: could not load %s (%s); its buttons are omitted\n"
                    % (sib.package, exc))


def detect_available():
    """Detected sibling command names, after best-effort registration."""
    ensure_sibling_commands()

    def live(name):
        return Gui.Command.get(name) is not None

    return assembly.detect_availability(live_lookup=live)


def register(available):
    """Register all own commands. ``available`` is the detected command set
    (sibling + probed Std_*), used only to build the missing-note label."""
    Gui.addCommand(assembly.CMD_SELECT, _SelectCommand())
    Gui.addCommand(assembly.CMD_MOVE_ROTATE, _MoveRotateCommand())
    Gui.addCommand(assembly.CMD_ROTATE, _RotateCommand())
    Gui.addCommand(assembly.CMD_SCALE, _ScaleCommand())
    Gui.addCommand(assembly.CMD_ERASER, _EraserCommand())
    Gui.addCommand(assembly.CMD_MAKE_GROUP, _MakeGroupCommand())
    Gui.addCommand(assembly.CMD_TAPE_MEASURE, _TapeMeasureCommand())
    Gui.addCommand(assembly.CMD_PAINT, _PaintBucketCommand())
    Gui.addCommand(assembly.CMD_ABOUT, _AboutCommand())
    Gui.addCommand(assembly.CMD_RESTORE_NAV, _RestoreNavigationCommand())
    for own_name, std_name in assembly.VIEW_COMMANDS:
        Gui.addCommand(own_name, _make_view_command(
            own_name, std_name, _VIEW_LABELS[own_name])())
    _found, missing = assembly.companions_report(available)
    if missing:
        Gui.addCommand(assembly.CMD_MISSING_NOTE,
                       _MissingNoteCommand([s.title for s in missing]))
