# Generic GUI runner (freecad.exe pattern from the gui-runners examples):
# executes one driver with __name__/__file__ injected and stdout redirected.
# Driver and log paths come from the GUI_DRIVER / GUI_LOG environment
# variables (FreeCAD does not forward extra argv reliably).
import os
import sys
import traceback

P = os.environ.get("GUI_DRIVER", "")
O = os.environ.get("GUI_LOG", "")

if O:
    _f = open(O, "w", buffering=1)
    sys.stdout = _f
    sys.stderr = _f
print("RUNNER_STARTED driver=%r" % P)
try:
    exec(compile(open(P).read(), P, "exec"), {"__name__": "__main__", "__file__": P})
except SystemExit as e:
    print("SYSTEM_EXIT code=%r" % (e.code,))
except BaseException:
    traceback.print_exc()
print("RUNNER_DONE")
if O:
    _f.flush()
