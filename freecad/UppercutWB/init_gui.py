# SPDX-License-Identifier: MIT
"""Workbench registration for the Uppercut addon.

Importing this module (auto-discovered by FreeCAD's Modern-layout addon
loader from Mod/<addon>/freecad/UppercutWB/) registers the workbench with
Gui.addWorkbench(...). No expensive work happens at import/startup time:
sibling detection, command registration and toolbar building run in
Initialize(), the navigation consent flow runs on first Activated().
"""
import os

import FreeCAD as App
import FreeCADGui as Gui


class UppercutWorkbench(Gui.Workbench):
    MenuText = "Uppercut"
    ToolTip = ("Simplified SketchUp-style interface: one toolbar over the "
               "SketchLayer, PushPull, SiteContext and Migration Guide "
               "companions, plus Select, Eraser, Tape Measure and Paint Bucket")
    Icon = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "Resources",
        "Icons",
        "uppercut.svg",
    )

    #: Detected command set, kept for the per-activation shortcut apply.
    _available = frozenset()

    def Initialize(self):
        from . import assembly, commands

        # Register own commands; force-register installed siblings, then
        # detect what is actually available (live command manager first,
        # static source check as fallback).
        available = commands.detect_available()
        std_available = set()
        for name in assembly.STD_PROBE_COMMANDS:
            try:
                if Gui.Command.get(name) is not None:
                    std_available.add(name)
            except Exception:  # noqa: BLE001 - probe failures mean "absent"
                continue
        available |= std_available
        commands.register(available)
        UppercutWorkbench._available = frozenset(available)

        toolbar = assembly.build_toolbar(available)
        self.appendToolbar("Uppercut", toolbar)

        menu = list(toolbar)
        # Rotate/Scale are menu-only (no toolbar buttons): they sit next to
        # Move/Rotate, guarded by a click-time probe of the Draft commands.
        anchor = assembly.CMD_MOVE_ROTATE
        extras = [assembly.CMD_ROTATE, assembly.CMD_SCALE]
        if anchor in menu:
            menu[menu.index(anchor) + 1:menu.index(anchor) + 1] = extras
        else:
            menu.extend(extras)
        menu.append(assembly.SEPARATOR)
        menu.append(assembly.CMD_RESTORE_NAV)
        menu.append(assembly.CMD_ABOUT)
        _found, missing = assembly.companions_report(available)
        if missing:
            menu.append(assembly.CMD_MISSING_NOTE)
            menu.append(assembly.CMD_INSTALL_COMPANIONS)
        self.appendMenu("Uppercut", menu)

    def _apply_shortcuts(self, shortcuts, commands):
        """Single-letter tool shortcuts (SketchUp muscle memory), applied on
        every Activated and restored on Deactivated, so the letters exist
        only while Uppercut is the active workbench. Written to FreeCAD's
        own shortcut parameters (remappable in Customize > Keyboard while
        active); each pre-existing value is recorded first and put back on
        leave. Conflicting accelerators are skipped with a status-bar note,
        never clobbered."""
        try:
            _applied, skipped = shortcuts.apply_all(
                Gui, UppercutWorkbench._available)
        except Exception as exc:  # noqa: BLE001 - shortcuts must not break entry
            App.Console.PrintWarning(
                "Uppercut: shortcut setup failed: %s\n" % exc)
            return
        conflicts = [s for s in skipped if s[2].startswith("conflicts")]
        if conflicts:
            commands._status(
                "Uppercut: shortcut(s) not bound (already in use): "
                + ", ".join("'%s' (%s)" % (accel, reason)
                            for accel, _cmd, reason in conflicts))

    def _restore_shortcuts(self, shortcuts):
        try:
            shortcuts.restore_bindings()
        except Exception as exc:  # noqa: BLE001 - leaving must not crash
            App.Console.PrintWarning(
                "Uppercut: shortcut restore failed: %s\n" % exc)

    def Activated(self):
        from . import commands, navstyle, shortcuts

        self._apply_shortcuts(shortcuts, commands)

        try:
            state = navstyle.load_state()
            if not state["consent_asked"]:
                from . import dialogs

                mode = dialogs.ask_navigation_consent()
                navstyle.store_consent(mode)
                state = navstyle.load_state()
            target = navstyle.apply_target(state)
            if target == "global":
                if not state["global_applied"]:
                    navstyle.apply_global_style(Gui)
                    self._status_note(
                        "Uppercut: SketchUp-style navigation is now the "
                        "global preference; Uppercut menu > Restore "
                        "navigation reverts it")
            elif target == "view":
                if not state["applied"]:
                    self._apply_nav(navstyle)
                # keep the style on views opened or focused while active
                navstyle.watch_views(Gui)
        except Exception as exc:  # noqa: BLE001 - never break activation
            App.Console.PrintWarning(
                "Uppercut: navigation consent flow failed: %s\n" % exc)

    def _apply_nav(self, navstyle):
        how = navstyle.apply_sketchup_style(Gui)
        if how == "preference":
            self._status_note(
                "Uppercut: navigation switched via the user preference; "
                "restored when you leave the workbench")

    def _status_note(self, message):
        try:
            Gui.getMainWindow().statusBar().showMessage(message, 8000)
        except Exception:  # noqa: BLE001
            pass

    def Deactivated(self):
        from . import navstyle, shortcuts

        self._restore_shortcuts(shortcuts)
        try:
            navstyle.unwatch_views()
            # per-view mode restores here; "everywhere" stays until the
            # menu's Restore navigation reverts it (by design)
            navstyle.restore_style(Gui)
        except Exception as exc:  # noqa: BLE001 - restoring must not crash
            App.Console.PrintWarning(
                "Uppercut: navigation restore failed: %s\n" % exc)

    def GetClassName(self):
        return "Gui::PythonWorkbench"  # exact string, mandatory, do not change


Gui.addWorkbench(UppercutWorkbench())

# Crash insurance: if the last session ended while Uppercut was active,
# Deactivated never ran and the workbench-scoped letters leaked into this
# session. This module is imported at every GUI startup, so restore any
# recorded bindings now; with nothing recorded this is a no-op.
try:
    from . import shortcuts as _shortcuts

    _shortcuts.restore_bindings()
except Exception:  # noqa: BLE001 - insurance must never break startup
    pass
