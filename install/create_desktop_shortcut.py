"""Create a Desktop shortcut for ERR Force - Unicode-safe.

We call the Win32 COM interfaces (IShellLinkW + IPersistFile) directly via
ctypes instead of going through WScript.Shell / cscript: those choke on
Cyrillic Desktop paths like 'C:\\Users\\<user>\\OneDrive\\Рабочий стол',
mangling the non-ASCII characters and producing ERROR_INVALID_NAME.
ctypes uses native UTF-16 (wide) strings so Unicode paths just work.
"""

from __future__ import annotations

import ctypes
import os
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# --- COM constants -----------------------------------------------------------
CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2

# CLSID_ShellLink = {00021401-0000-0000-C000-000000000046}
CLSID_ShellLink = ctypes.c_byte * 16
_CLSID_SHELLLINK = CLSID_ShellLink(
    0x01, 0x14, 0x02, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0xC0, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x46,
)
# IID_IShellLinkW = {000214F9-0000-0000-C000-000000000046}
IID_IShellLinkW = CLSID_ShellLink(
    0xF9, 0x14, 0x02, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0xC0, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x46,
)
# IID_IPersistFile = {0000010B-0000-0000-C000-000000000046}
IID_IPersistFile = CLSID_ShellLink(
    0x0B, 0x01, 0x00, 0x00,
    0x00, 0x00,
    0x00, 0x00,
    0xC0, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x46,
)

ole32 = ctypes.windll.ole32
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = ctypes.HRESULT
ole32.CoCreateInstance.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
ole32.CoCreateInstance.restype = ctypes.HRESULT
ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None


def _vtbl(ptr, index, argtypes, restype=ctypes.HRESULT):
    """Return a callable for the COM vtable entry at the given index."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents.value
    func_addr = ctypes.cast(
        ctypes.c_void_p(vtbl + index * ctypes.sizeof(ctypes.c_void_p)),
        ctypes.POINTER(ctypes.c_void_p),
    ).contents.value
    fn_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return fn_type(func_addr)


def desktop_dir() -> Path:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
    ) as key:
        raw, _ = winreg.QueryValueEx(key, "Desktop")
    return Path(os.path.expandvars(str(raw)))


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def create_shortcut(
    link_path: Path,
    target: Path,
    workdir: Path,
    icon: Path | None,
    description: str,
    arguments: str = "",
) -> None:
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != -2147417850:  # ignore "already initialized"
        raise OSError(f"CoInitializeEx failed: 0x{hr & 0xFFFFFFFF:08X}")

    psl = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(_CLSID_SHELLLINK),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(IID_IShellLinkW),
        ctypes.byref(psl),
    )
    if hr < 0:
        raise OSError(f"CoCreateInstance(IShellLinkW) failed: 0x{hr & 0xFFFFFFFF:08X}")

    try:
        # IShellLinkW vtable indices (Unicode):
        #   0=QueryInterface, 1=AddRef, 2=Release,
        #   3=GetPath,        4=GetIDList,         5=SetIDList,
        #   6=GetDescription, 7=SetDescription,
        #   8=GetWorkingDirectory, 9=SetWorkingDirectory,
        #  10=GetArguments,  11=SetArguments,
        #  12=GetHotkey,     13=SetHotkey,
        #  14=GetShowCmd,    15=SetShowCmd,
        #  16=GetIconLocation,17=SetIconLocation,
        #  18=SetRelativePath,19=Resolve,
        #  20=SetPath
        set_path        = _vtbl(psl, 20, [wintypes.LPCWSTR])
        set_workdir     = _vtbl(psl, 9,  [wintypes.LPCWSTR])
        set_desc        = _vtbl(psl, 7,  [wintypes.LPCWSTR])
        set_args        = _vtbl(psl, 11, [wintypes.LPCWSTR])
        set_icon        = _vtbl(psl, 17, [wintypes.LPCWSTR, ctypes.c_int])

        hr = set_path(psl, str(target))
        if hr < 0:
            raise OSError(f"SetPath failed: 0x{hr & 0xFFFFFFFF:08X}")
        if arguments:
            hr = set_args(psl, arguments)
            if hr < 0:
                raise OSError(f"SetArguments failed: 0x{hr & 0xFFFFFFFF:08X}")
        hr = set_workdir(psl, str(workdir))
        if hr < 0:
            raise OSError(f"SetWorkingDirectory failed: 0x{hr & 0xFFFFFFFF:08X}")
        hr = set_desc(psl, description)
        if hr < 0:
            raise OSError(f"SetDescription failed: 0x{hr & 0xFFFFFFFF:08X}")
        if icon is not None and icon.is_file():
            hr = set_icon(psl, str(icon), 0)
            if hr < 0:
                raise OSError(f"SetIconLocation failed: 0x{hr & 0xFFFFFFFF:08X}")

        # Query IPersistFile.
        ppf = ctypes.c_void_p()
        query_interface = _vtbl(psl, 0, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
        hr = query_interface(psl, ctypes.byref(IID_IPersistFile), ctypes.byref(ppf))
        if hr < 0:
            raise OSError(f"QueryInterface(IPersistFile) failed: 0x{hr & 0xFFFFFFFF:08X}")

        try:
            # IPersistFile vtable: 0=QI, 1=AddRef, 2=Release,
            #   3=GetClassID, 4=IsDirty, 5=Load, 6=Save, 7=SaveCompleted, 8=GetCurFile
            persist_save = _vtbl(ppf, 6, [wintypes.LPCWSTR, wintypes.BOOL])
            hr = persist_save(ppf, str(link_path), True)
            if hr < 0:
                raise OSError(
                    f"IPersistFile.Save failed for {link_path!r}: "
                    f"0x{hr & 0xFFFFFFFF:08X}"
                )
        finally:
            release_pf = _vtbl(ppf, 2, [], restype=wintypes.ULONG)
            release_pf(ppf)
    finally:
        release_sl = _vtbl(psl, 2, [], restype=wintypes.ULONG)
        release_sl(psl)
        ole32.CoUninitialize()


def _pick_existing(root: Path, *names: str) -> Path | None:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    return None


def main() -> int:
    root = repo_root()
    # Prefer ERR_FORCE_fast.cmd: same env as the PyInstaller launcher but starts
    # the venv's pythonw.exe directly (no onefile extract to %%TEMP%% — much faster).
    fast_cmd = _pick_existing(root, "ERR_FORCE_fast.cmd", "ER_FORCE_fast.cmd")
    exe = _pick_existing(root, "ERR_FORCE.exe", "ER_FORCE.exe")
    fallback_cmd = root / "eye_tracking_setup" / "run_app.cmd"
    assets = root / "install" / "assets"
    icon = _pick_existing(assets, "err_force_icon.ico", "er_force_icon.ico")

    if fast_cmd is not None:
        # cmd.exe /c is more reliable than pointing the shortcut directly at a .cmd
        # file (especially on OneDrive / non-ASCII Desktop paths).
        comspec = Path(os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"))
        target = comspec
        arguments = f'/c "{fast_cmd.resolve()}"'
    elif exe is not None:
        target = exe
        arguments = ""
    elif fallback_cmd.is_file():
        comspec = Path(os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"))
        target = comspec
        arguments = f'/c "{fallback_cmd.resolve()}"'
    else:
        print(
            "Could not find ERR_FORCE_fast.cmd, ERR_FORCE.exe, or "
            "eye_tracking_setup\\run_app.cmd.\n"
            "Run eye_tracking_setup\\setup_colleague.cmd (and optionally "
            "install\\build_launcher.cmd).",
            file=sys.stderr,
        )
        return 1

    link = desktop_dir() / "ERR Force.lnk"
    legacy_link = desktop_dir() / "ER Force.lnk"
    create_shortcut(
        link_path=link,
        target=target.resolve(),
        workdir=root.resolve(),
        icon=icon,
        description="ERR Force - fatigue and eye tracking research app",
        arguments=arguments,
    )

    if legacy_link.is_file() and legacy_link != link:
        try:
            legacy_link.unlink()
        except OSError:
            pass

    if not link.is_file():
        print(f"Shortcut creation reported success but file not found at {link}", file=sys.stderr)
        return 2

    if fast_cmd is not None:
        launch_target = fast_cmd
    elif exe is not None:
        launch_target = exe
    else:
        launch_target = fallback_cmd

    print("Desktop shortcut created:")
    print(f"  {link}")
    print(f"  Target: {target.resolve()}")
    if arguments:
        print(f"  Args:   {arguments}")
    print(f"  Launches: {launch_target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
