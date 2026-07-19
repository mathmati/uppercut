# SPDX-License-Identifier: MIT
"""One-click download/install of Uppercut's companion addons.

PURE LOGIC: no FreeCAD GUI imports and no PySide at module level, so the
module is importable and testable headless under freecadcmd. The thin
dialog on top lives in dialogs.py.

The companion list is assembly.SIBLINGS (the same registry the toolbar
detection uses; there is deliberately no second list here). Each sibling's
``repo`` names its GitHub repository AND the folder it is installed under
in the user's Mod directory: import detection (assembly.find_package_dir)
resolves ``freecad.<Pkg>WB`` through FreeCAD's addon search path, which
contains every Mod subdirectory, so the folder name itself is free -- we
use the repository name because that is what ``git clone`` and the Addon
Manager's custom-repository install produce.

SECURITY: the download URLs are hard-pinned below to the six
github.com/mathmati repositories, branch main, over HTTPS. Nothing here
accepts a user-supplied URL. Extraction refuses entries that would escape
the target directory (zip-slip) and everything is unpacked into a fresh
temporary directory first, moved into Mod/<repo> only on success, so a
failed download or a bad archive leaves nothing half-installed. An already
existing Mod/<repo> is never overwritten; that companion is skipped.
"""
import os
import shutil
import tempfile
import zipfile

from . import assembly

#: Descriptive User-Agent for the GitHub download (GitHub rejects requests
#: with none).
USER_AGENT = ("Uppercut-FreeCAD-Workbench companion installer "
              "(+https://github.com/mathmati/uppercut)")

#: Seconds before an unresponsive download gives up.
TIMEOUT = 60

#: Hard-pinned zipball URLs, one per sibling key in assembly.SIBLINGS.
#: These literals are the complete set of network locations this module
#: will ever touch; the headless regression cross-checks them 1:1 against
#: the registry and against each sibling's ``repo`` name.
PINNED_ZIP_URLS = {
    "sketchlayer":
        "https://github.com/mathmati/FreeCAD-SketchLayer/archive/refs/heads/main.zip",
    "pushpull":
        "https://github.com/mathmati/FreeCAD-PushPull/archive/refs/heads/main.zip",
    "offset":
        "https://github.com/mathmati/FreeCAD-Offset/archive/refs/heads/main.zip",
    "followme":
        "https://github.com/mathmati/FreeCAD-FollowMe/archive/refs/heads/main.zip",
    "sitecontext":
        "https://github.com/mathmati/FreeCAD-SiteContext/archive/refs/heads/main.zip",
    "migrationguide":
        "https://github.com/mathmati/FreeCAD-Migration-Guide/archive/refs/heads/main.zip",
}


def zip_url(sibling):
    """The pinned zipball URL for a Sibling (or a sibling key)."""
    key = sibling if isinstance(sibling, str) else sibling.key
    return PINNED_ZIP_URLS[key]


def zip_root_name(sibling):
    """GitHub zipball root folder: ``<Repo>-main``."""
    return sibling.repo + "-main"


def mod_directory(user_app_data_dir):
    """The user's Mod directory, derived from App.getUserAppDataDir()."""
    return os.path.join(user_app_data_dir, "Mod")


def target_directory(sibling, mod_dir):
    """Where the companion will be installed: ``Mod/<repo>``."""
    return os.path.join(mod_dir, sibling.repo)


def download_zip(url, dest_path):
    """Fetch ``url`` into ``dest_path`` (streamed, with the pinned UA)."""
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        with open(dest_path, "wb") as fh:
            shutil.copyfileobj(response, fh)


def _safe_members(zf, staging_dir):
    """Member names of ``zf`` after a zip-slip check.

    Raises ValueError on absolute paths or any entry that would resolve
    outside ``staging_dir``.
    """
    base = os.path.realpath(staging_dir)
    names = zf.namelist()
    for name in names:
        dest = os.path.realpath(os.path.join(base, name))
        if dest != base and not dest.startswith(base + os.sep):
            raise ValueError("unsafe path in archive: %r" % name)
    return names


def extract_zipball(zip_path, staging_dir, expected_root):
    """Extract a GitHub zipball into ``staging_dir``; return the root dir.

    The archive must contain exactly one top-level folder named
    ``expected_root`` (GitHub zipballs always do); anything else raises
    ValueError. Returns the absolute path of the extracted root.
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = _safe_members(zf, staging_dir)
        roots = {name.split("/", 1)[0] for name in names if name.strip("/")}
        if roots != {expected_root}:
            raise ValueError(
                "unexpected archive layout: top-level %r, expected %r"
                % (sorted(roots), expected_root))
        zf.extractall(staging_dir)
    root = os.path.join(staging_dir, expected_root)
    if not os.path.isdir(root):
        raise ValueError("archive root %r missing after extraction"
                         % expected_root)
    return root


def install_from_zip(zip_path, sibling, mod_dir):
    """Extract ``zip_path`` and move it into place as ``Mod/<repo>``.

    Refuses (result ``skipped``) when ``Mod/<repo>`` already exists.
    Extraction happens in a temporary staging directory next to Mod; the
    ``<Repo>-main`` zip root is renamed to ``<repo>`` by the final move,
    which is the only step that touches the Mod directory. On any error
    the staging directory is removed and Mod is left untouched.

    Returns "installed" or "skipped"; raises on failure.
    """
    target = target_directory(sibling, mod_dir)
    if os.path.exists(target):
        return "skipped"
    if not os.path.isdir(mod_dir):
        os.makedirs(mod_dir)
    staging = tempfile.mkdtemp(prefix="uppercut-install-", dir=mod_dir)
    try:
        root = extract_zipball(zip_path, staging, zip_root_name(sibling))
        # Re-check just before the move: never overwrite.
        if os.path.exists(target):
            return "skipped"
        os.rename(root, target)
        return "installed"
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def install_companion(sibling, mod_dir, fetch=None):
    """Download and install one companion. Never raises.

    ``fetch``: callable(url, dest_path), defaulting to :func:`download_zip`;
    injected by tests so the harness never touches the network.

    Returns a dict: ``key``, ``title``, ``status`` ("installed", "skipped"
    or "failed"), ``target`` and ``error`` (the error text, or None).
    """
    fetcher = fetch or download_zip
    result = {"key": sibling.key, "title": sibling.title, "status": "failed",
              "target": target_directory(sibling, mod_dir), "error": None}
    try:
        if os.path.exists(result["target"]):
            result["status"] = "skipped"
            return result
        tmp = tempfile.mkdtemp(prefix="uppercut-download-")
        try:
            zip_path = os.path.join(tmp, sibling.repo + ".zip")
            fetcher(zip_url(sibling), zip_path)
            result["status"] = install_from_zip(zip_path, sibling, mod_dir)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 - report, leave nothing behind
        result["status"] = "failed"
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    return result


def install_missing(siblings, mod_dir, fetch=None, progress=None):
    """Install several companions sequentially; one failure never stops the
    rest (no retries, no threads).

    ``progress``: optional callable(sibling, phase) with phase "start" or
    the finished result dict; the dialog uses it to update per-item status.

    Returns the list of per-companion result dicts.
    """
    results = []
    for sib in siblings:
        if progress is not None:
            try:
                progress(sib, "start")
            except Exception:  # noqa: BLE001 - progress must not break installs
                pass
        result = install_companion(sib, mod_dir, fetch=fetch)
        results.append(result)
        if progress is not None:
            try:
                progress(sib, result)
            except Exception:  # noqa: BLE001
                pass
    return results
