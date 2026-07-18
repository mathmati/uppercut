# SPDX-License-Identifier: MIT
"""Uppercut workbench package (Modern namespaced layout).

Importing this package has no side effects beyond making the submodules
importable -- workbench/command registration happens in init_gui.py, which
is imported once by FreeCAD's Addon Manager (or a Mod/ install) when the
GUI loads this addon. assembly.py, eraser.py, paint.py and the core of
navstyle.py are GUI-free and importable headless under freecadcmd.
"""
