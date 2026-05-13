from __future__ import annotations

import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _import_tobii():
    root = _repo_root()
    sdk_root = root / "TobiiPro_SDK"
    for path in (root, sdk_root):
        candidate = str(path)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    import tobii_research as tr

    return tr


def main() -> int:
    try:
        tr = _import_tobii()
    except Exception as exc:
        print("Tobii Pro SDK is not ready yet.")
        print(f"Import error: {exc!r}")
        print("Install Tobii Pro SDK, then run eye_tracking_setup\\sync_sdk_native.ps1")
        return 1

    print(f"Tobii Pro SDK version: {tr.__version__}")
    trackers = tr.find_all_eyetrackers()
    if not trackers:
        print("No Tobii eye trackers found.")
        print("Check USB connection, Tobii Pro Fusion support, and Eye Tracker Manager.")
        return 2

    for index, tracker in enumerate(trackers):
        print(f"[{index}] model={tracker.model} serial={tracker.serial_number} address={tracker.address}")
        try:
            display = tracker.get_display_area()
            print(
                "    display area: "
                f"width={display.width} height={display.height} "
                f"offset=({display.x}, {display.y})"
            )
        except Exception as exc:
            print(f"    display area unavailable: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
