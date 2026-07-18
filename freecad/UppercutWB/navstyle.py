# SPDX-License-Identifier: MIT
"""Navigation-style save/set/restore, with the API probing isolated here.

FreeCAD 1.1.1 facts, verified 2026-07-18 against the installed binaries:

- The Python API on a 3D view is ``setNavigationType``/``getNavigationType``
  (FreeCAD 1.1.1's own Mod/Test/Workbench.py uses exactly those).
  ``setNavigationStyle``/``getNavigationStyle`` do NOT exist in 1.1.1; they
  are kept as probe candidates for other versions.
- Every open 3D view is reachable through
  ``Gui.getDocument(name).mdiViewsOfType("Gui::View3DInventor")`` (probed;
  there is no ``mdiViewsOfDocument``), and new 3D views come from
  ``Gui.getDocument(name).createView("Gui::View3DInventor")``.
- The user preference parameter group
  ``User parameter:BaseApp/Preferences/View``, key ``NavigationStyle``,
  holds values like ``Gui::CADNavigationStyle``; the bundled Tux addon's
  navigation indicator reads/writes it the same way. Views read it at
  creation time, so writing it only styles views opened afterwards --
  "everywhere" mode therefore also switches the views already open.
- The global default on a fresh install is ``Gui::CADNavigationStyle``,
  which orbits on Ctrl+right-drag, NOT on middle-mouse hold; the
  SketchUp-style map (middle orbit, Shift+middle pan) only comes from the
  Blender style applied here.

Consent has three outcomes (dialogs.ask_navigation_consent):
"view"   -- per-view switch, the default. On workbench Activated the style
            is applied to ALL open 3D views, and a watcher re-applies it to
            views opened or focused while the workbench is active. Leaving
            the workbench restores the saved style.
"global" -- "everywhere". Writes the GLOBAL preference
            (BaseApp/Preferences/View NavigationStyle) after recording the
            prior value, and switches the views already open. This persists
            across workbenches by design; Uppercut menu > Restore
            navigation reverts it (and the per-view switch, if any).
"none"   -- nothing is changed.

The watcher hook is the main window's ``QMdiArea.subWindowActivated``
signal (probe-verified to fire when a new view is created). Chosen over a
QTimer poll: no periodic wakeups, and the signal fires exactly when a view
appears or gets focus. It is connected on Activated and disconnected on
Deactivated.

Uppercut state lives in ``User parameter:BaseApp/Uppercut``. Nothing is
written without the consent dialog; the restore paths only act when an
apply path actually changed something (``applied`` / ``global_applied``
flags). Where several open views had different styles, the first view's
style is the one saved and restored to all (they share the user's default
in practice; documented in the README).
"""
import FreeCAD as App

PARAM_GROUP = "User parameter:BaseApp/Uppercut"
PREF_GROUP = "User parameter:BaseApp/Preferences/View"
PREF_KEY = "NavigationStyle"

#: Closest stock style to SketchUp's camera: middle-mouse orbit,
#: Shift+middle pan, wheel zoom.
UPPERCUT_STYLE = "Gui::BlenderNavigationStyle"

#: Consent outcomes stored in the NavConsentMode parameter.
CONSENT_VIEW = "view"
CONSENT_GLOBAL = "global"
CONSENT_NONE = "none"

#: MDI type string for a 3D view (probe-verified in 1.1.1).
VIEW3D_TYPE = "Gui::View3DInventor"

_GETTER_NAMES = ("getNavigationType", "getNavigationStyle")
_SETTER_NAMES = ("setNavigationType", "setNavigationStyle")


def params():
    return App.ParamGet(PARAM_GROUP)


def pref_params():
    return App.ParamGet(PREF_GROUP)


# --- state round-trip (headless-testable) ------------------------------------
def load_state(p=None):
    p = p if p is not None else params()
    return {
        "consent_asked": p.GetBool("NavConsentAsked", False),
        "consent": p.GetBool("NavConsent", False),
        "consent_mode": p.GetString("NavConsentMode", ""),
        "applied": p.GetBool("NavApplied", False),
        "saved_style": p.GetString("NavSavedStyle", ""),
        "saved_via": p.GetString("NavSavedVia", ""),
        "global_applied": p.GetBool("NavGlobalApplied", False),
        "saved_global_style": p.GetString("NavSavedGlobalStyle", ""),
    }


def store_consent(mode, p=None):
    """Record the consent outcome: CONSENT_VIEW, CONSENT_GLOBAL or
    CONSENT_NONE. The legacy NavConsent boolean mirrors "anything but
    none", so a state written by an older Uppercut (consent True, no mode
    string) still reads as CONSENT_VIEW in :func:`apply_target`."""
    p = p if p is not None else params()
    p.SetBool("NavConsentAsked", True)
    p.SetBool("NavConsent", mode in (CONSENT_VIEW, CONSENT_GLOBAL))
    p.SetString("NavConsentMode", mode)


def apply_target(state):
    """Where the consent state wants the SketchUp style applied:
    "global", "view" or "none"."""
    mode = state.get("consent_mode", "")
    if mode == CONSENT_GLOBAL:
        return "global"
    if mode == CONSENT_VIEW or (not mode and state.get("consent")):
        return CONSENT_VIEW
    return "none"


def store_applied(saved_style, saved_via, p=None):
    p = p if p is not None else params()
    p.SetBool("NavApplied", True)
    p.SetString("NavSavedStyle", saved_style)
    p.SetString("NavSavedVia", saved_via)


def clear_applied(p=None):
    p = p if p is not None else params()
    p.SetBool("NavApplied", False)


# --- view API probing (headless-testable with fakes) --------------------------
def _resolve(obj, names):
    for attr in names:
        fn = getattr(obj, attr, None)
        if callable(fn):
            return fn
    return None


def style_getter(view):
    """The view's navigation-style getter, or None (probes 1.1.1 name first)."""
    return _resolve(view, _GETTER_NAMES)


def style_setter(view):
    """The view's navigation-style setter, or None (probes 1.1.1 name first)."""
    return _resolve(view, _SETTER_NAMES)


def get_view_style(view):
    fn = style_getter(view)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:  # noqa: BLE001 - a broken view must not break activation
        return None


def set_view_style(view, style):
    fn = style_setter(view)
    if fn is None:
        return False
    try:
        fn(style)
    except Exception:  # noqa: BLE001 - fall through to the preference path
        return False
    return True


# --- view enumeration (headless-testable with injected lister/gui) ------------
def all_3d_views(gui, list_documents=None):
    """Every open 3D view across all documents.

    ``gui``: FreeCADGui or a fake with ``getDocument(name)`` returning an
    object with ``mdiViewsOfType``. ``list_documents`` is injectable for
    tests; defaults to ``App.listDocuments``. Never raises.
    """
    if gui is None:
        return []
    list_documents = list_documents or App.listDocuments
    try:
        names = list(list_documents().keys())
    except Exception:  # noqa: BLE001
        return []
    views = []
    for name in names:
        try:
            gdoc = gui.getDocument(name)
        except Exception:  # noqa: BLE001 - doc may lack a GUI side
            continue
        try:
            views.extend(gdoc.mdiViewsOfType(VIEW3D_TYPE))
        except Exception:  # noqa: BLE001 - older API or no 3D views
            continue
    return views


def _active_view(gui):
    try:
        doc = gui.ActiveDocument
    except Exception:  # noqa: BLE001
        return None
    if doc is None:
        return None
    return getattr(doc, "ActiveView", None)


# --- per-view apply / restore (GUI-time; gui module injected) ------------------
def apply_sketchup_style(gui, list_documents=None):
    """Save the current style and switch EVERY open 3D view to
    UPPERCUT_STYLE. The first readable view style is the one saved and
    later restored to all views.

    Returns how the style was applied: "view", "preference" (no view
    accepted it; the global preference is the fallback), or "failed".
    """
    views = all_3d_views(gui, list_documents=list_documents)
    saved = ""
    changed = 0
    for view in views:
        current = get_view_style(view)
        if current is None:
            continue
        if not saved:
            saved = current
        if current == UPPERCUT_STYLE:
            continue
        if set_view_style(view, UPPERCUT_STYLE):
            changed += 1
    if saved:
        # at least one view had a readable style (saved is the first one)
        store_applied(saved, "view")
        return "view"
    # Fallback: the user preference (same mechanism the Tux indicator uses).
    try:
        pref = pref_params()
        current = pref.GetString(PREF_KEY, "")
        pref.SetString(PREF_KEY, UPPERCUT_STYLE)
        store_applied(current, "preference")
        return "preference"
    except Exception:  # noqa: BLE001
        return "failed"


def restore_style(gui, list_documents=None):
    """Restore the style saved by apply_sketchup_style, if one was applied.

    Sets every open 3D view back to the saved style; when the apply had
    gone through the global preference ("preference" via) the preference
    is written back too. Returns "restored", "nothing" (nothing was
    applied), or "failed".
    """
    state = load_state()
    if not state["applied"]:
        return "nothing"
    via_pref = state["saved_via"] == "preference"
    # An empty saved_style with the preference via is meaningful: the global
    # preference was UNSET before we wrote it (a fresh install), and restoring
    # means unsetting it again. Only a non-preference apply with no saved
    # style is truly nothing to do.
    if not state["saved_style"] and not via_pref:
        return "nothing"
    ok = False
    if state["saved_style"]:
        for view in all_3d_views(gui, list_documents=list_documents):
            if set_view_style(view, state["saved_style"]):
                ok = True
    if via_pref or not ok:
        try:
            pref = pref_params()
            if state["saved_style"]:
                pref.SetString(PREF_KEY, state["saved_style"])
            else:
                try:
                    pref.RemString(PREF_KEY)
                except Exception:  # noqa: BLE001
                    pref.SetString(PREF_KEY, "")
            ok = True
        except Exception:  # noqa: BLE001 - a view-side restore may still hold
            pass
    if ok:
        clear_applied()
        return "restored"
    return "failed"


# --- "everywhere" (global preference) apply / restore --------------------------
def apply_global_style(gui, p=None, pref=None, list_documents=None):
    """"Everywhere" mode: write the GLOBAL navigation preference after
    recording its prior value, and switch the views already open (they do
    not pick up a preference change live). Idempotent: a repeat call while
    already applied does not overwrite the recorded prior value."""
    p = p if p is not None else params()
    pref = pref if pref is not None else pref_params()
    state = load_state(p)
    prior = state["saved_global_style"] if state["global_applied"] \
        else pref.GetString(PREF_KEY, "")
    pref.SetString(PREF_KEY, UPPERCUT_STYLE)
    p.SetString("NavSavedGlobalStyle", prior)
    p.SetBool("NavGlobalApplied", True)
    for view in all_3d_views(gui, list_documents=list_documents):
        set_view_style(view, UPPERCUT_STYLE)


def restore_global_style(gui, p=None, pref=None, list_documents=None):
    """Undo apply_global_style: the global preference back to the recorded
    prior value, and the open views back as well (best effort). Returns
    "restored", "nothing" (never applied), or "failed"."""
    p = p if p is not None else params()
    pref = pref if pref is not None else pref_params()
    state = load_state(p)
    if not state["global_applied"]:
        return "nothing"
    saved = state["saved_global_style"]
    try:
        if saved:
            pref.SetString(PREF_KEY, saved)
        else:
            pref.RemString(PREF_KEY)
    except Exception:  # noqa: BLE001
        return "failed"
    if gui is not None and saved:
        for view in all_3d_views(gui, list_documents=list_documents):
            set_view_style(view, saved)
    p.SetBool("NavGlobalApplied", False)
    return "restored"


def restore_navigation(gui, list_documents=None):
    """The menu restore: undoes whichever switch Uppercut actually made
    (the "everywhere" global write and/or the per-view switch). Returns
    "restored", "nothing", or "failed"."""
    outcomes = (
        restore_global_style(gui, list_documents=list_documents),
        restore_style(gui, list_documents=list_documents),
    )
    if "restored" in outcomes:
        return "restored"
    if "failed" in outcomes:
        return "failed"
    return "nothing"


# --- keep-applied watcher (GUI-only; decision logic headless-testable) ---------
def watcher_should_apply(state):
    """True when the watcher should keep forcing the per-view style: the
    consent target is per-view and a per-view switch is in effect."""
    return apply_target(state) == CONSENT_VIEW and bool(state.get("applied"))


def reapply_to_views(gui, list_documents=None):
    """Switch any open 3D view that is not on UPPERCUT_STYLE back to it.
    Returns the views that were changed."""
    changed = []
    for view in all_3d_views(gui, list_documents=list_documents):
        current = get_view_style(view)
        if current is not None and current != UPPERCUT_STYLE:
            if set_view_style(view, UPPERCUT_STYLE):
                changed.append(view)
    return changed


class _ViewWatcher(object):
    """Re-applies the per-view style when a view is created or focused
    while the workbench is active. Connected on Activated, disconnected on
    Deactivated; a Qt failure here must never break workbench switching."""

    def __init__(self):
        self._mdi = None
        self._slot = None

    def attach(self, gui):
        self.detach()
        try:
            from PySide import QtWidgets
            window = gui.getMainWindow()
            mdi = window.findChild(QtWidgets.QMdiArea)
            if mdi is None:
                return False
            self._slot = lambda _subwindow: self._on_view_activated(gui)
            mdi.subWindowActivated.connect(self._slot)
            self._mdi = mdi
            return True
        except Exception:  # noqa: BLE001
            self._mdi = None
            self._slot = None
            return False

    def detach(self):
        if self._mdi is not None and self._slot is not None:
            try:
                self._mdi.subWindowActivated.disconnect(self._slot)
            except Exception:  # noqa: BLE001
                pass
        self._mdi = None
        self._slot = None

    def _on_view_activated(self, gui):
        try:
            if watcher_should_apply(load_state()):
                reapply_to_views(gui)
        except Exception:  # noqa: BLE001 - the hook must never break the GUI
            pass


_watcher = _ViewWatcher()


def watch_views(gui):
    """Connect the keep-applied hook (no-op when already connected)."""
    return _watcher.attach(gui)


def unwatch_views():
    """Disconnect the keep-applied hook."""
    _watcher.detach()
