# SPDX-License-Identifier: MIT
"""UNVERIFIED: Uppercut GUI driver for manual runs.

STATUS: NOT RUN in the 2026-07-18 build session. The session only exercised
freecadcmd, which has no command manager (Gui.Command is absent there), so
workbench activation, toolbar population, sibling detection through
Gui.Command.get, and the consent dialog could not be driven headlessly.
Run manually with the FreeCAD GUI executable from the repo root:

    freecad.exe verify/drivers/uppercut_driver.py

(or paste into the Macro editor). It activates the Uppercut workbench,
asserts the "Uppercut" toolbar exists, and saves a screenshot next to this
script. Requires the addon to be installed (Mod/ or Addon Manager) so that
the workbench is registered.
"""
import os

import FreeCAD as App
import FreeCADGui as Gui


def run():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    Gui.activateWorkbench("UppercutWorkbench")
    active = Gui.activeWorkbench().__class__.__name__
    assert active == "UppercutWorkbench", "active workbench is %r" % active

    from PySide import QtWidgets

    main = Gui.getMainWindow()
    titles = [bar.windowTitle()
              for bar in main.findChildren(QtWidgets.QToolBar)]
    assert any("Uppercut" in title for title in titles), \
        "no 'Uppercut' toolbar found among %r" % (titles,)

    if App.ActiveDocument is None:
        App.newDocument("UppercutDriver")
    Gui.SendMsgToActiveView("ViewFit")
    shot = os.path.join(out_dir, "uppercut_toolbar.png")
    Gui.ActiveDocument.ActiveView.saveImage(shot, 1280, 800)
    print("UPPERCUT DRIVER OK: toolbar present, screenshot at %s" % shot)


if __name__ == "__main__":
    run()
