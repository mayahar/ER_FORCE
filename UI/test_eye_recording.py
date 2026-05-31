import os
import sys
import time
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.hardware_config import eye_tracker_mode, using_glasses
from core.session_manager import create_session
from ui.eye_runtime import EyeTrackingRuntime
from ui.eye_tracking_runtime import _candidate_hosts


def print_host_diagnostics(runtime: EyeTrackingRuntime) -> None:
    if not using_glasses():
        return

    print("\n[debug] available glasses hosts:")
    for host in _candidate_hosts(getattr(runtime, "active_host", None)):
        try:
            import requests

            res = requests.get(f"http://{host}/rest/system.recording-unit-serial", timeout=2.0)
            print(f"    {host}: HTTP {res.status_code}, body={res.text[:80]!r}")
        except Exception as exc:
            print(f"    {host}: failed ({exc})")


def run_test() -> None:
    print("=" * 60)
    print(f"Eye recording test | mode={eye_tracker_mode()}")
    if using_glasses():
        current_host = os.environ.get("TOBII_GLASSES_HOST", "not set")
        print(f"TOBII_GLASSES_HOST: {current_host}")
    print("=" * 60)

    runtime = EyeTrackingRuntime()

    print("\n[1/4] Checking eye tracker connection...")
    if not runtime.ensure_tracker():
        print(f"[-] Connection failed: {runtime.last_error}")
        print_host_diagnostics(runtime)
        if using_glasses():
            print("Tip: check the Ethernet/Wi-Fi connection and make sure the glasses are powered on.")
        else:
            print("Tip: check that the Tobii bar is connected and visible in Tobii Pro Eye Tracker Manager.")
        return

    print(f"[+] Eye tracker found: {runtime.tracker_label or 'connected'}")
    print_host_diagnostics(runtime)

    print("\n[2/4] Starting recording...")
    session = create_session("eye_test")
    runtime.configure_session(type("TestController", (), {"session": session})())
    print(f"[+] Session directory: {session.root}")
    if not runtime.start_recording():
        print(f"[-] Recording failed to start: {runtime.last_error}")
        return

    print("[+] Recording started.")
    if using_glasses():
        print(f"[+] Recording UUID: {getattr(runtime, 'current_recording_uuid', None)}")
    print(f"[+] Active: {runtime.active}")

    print("\n[3/4] Recording for 5 seconds...")
    for i in range(5, 0, -1):
        print(f"    {i} seconds remaining...")
        time.sleep(1)

    print("\n[4/4] Stopping recording and extracting features...")
    features = runtime.stop_recording()
    if runtime.last_error:
        print(f"[-] Stop/extract failed: {runtime.last_error}")
        return

    print("=" * 60)
    print("[+++] Eye recording test completed successfully.")
    print(f"Raw samples: {runtime.raw_sample_count}")

    if features:
        print("\nExtracted features:")
        print(f" - fixation_count: {features.get('fixation_count')}")
        print(f" - saccade_count: {features.get('saccade_count')}")
        print(f" - fixation_duration: {features.get('fixation_duration')}")
    else:
        print("\n[-] Recording stopped, but no features were extracted.")
    print("=" * 60)


if __name__ == "__main__":
    run_test()
