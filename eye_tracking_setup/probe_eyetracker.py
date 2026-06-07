from __future__ import annotations

import sys


def main() -> int:
    print("ERR_FORCE Tobii eye tracker probe")
    print(f"Python: {sys.executable}")
    print("")

    try:
        import tobii_research as tr
    except Exception as exc:
        print("FAIL: Python package 'tobii_research' is not available.")
        print(f"Reason: {exc.__class__.__name__}: {exc}")
        print("")
        print("Run the ERR_FORCE installer again, or install eye-tracking requirements.")
        return 1

    try:
        trackers = list(tr.find_all_eyetrackers())
    except Exception as exc:
        print("FAIL: Tobii SDK is installed, but tracker discovery failed.")
        print(f"Reason: {exc.__class__.__name__}: {exc}")
        print("")
        print("Check Tobii drivers / Eye Tracker Manager and USB/network connection.")
        return 2

    if not trackers:
        print("NO TRACKERS FOUND.")
        print("")
        print("Software side is importable, but Windows/Tobii did not report a tracker.")
        print("Install/open Tobii Eye Tracker Manager, connect the tracker, and calibrate it.")
        return 2

    print(f"FOUND {len(trackers)} tracker(s):")
    for index, tracker in enumerate(trackers):
        model = getattr(tracker, "model", "")
        serial = getattr(tracker, "serial_number", "")
        address = getattr(tracker, "address", "")
        print(f"  [{index}] {model} serial={serial} address={address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
