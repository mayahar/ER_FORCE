import json
import os
import time

import numpy as np

from voice.recorder import VoiceRecorder

# Direct IP avoids slow DNS discovery in standalone runs.
os.environ["TOBII_GLASSES_HOST"] = "192.168.75.51"

CALIBRATION_FILE = ".voice_calib.json"


def _device_key(device_name):
    key = str(device_name or "default").strip().lower()
    return " ".join(key.split())


def _load_existing_calibration():
    if not os.path.exists(CALIBRATION_FILE):
        return {}
    try:
        with open(CALIBRATION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def run_calibration():
    sample_rate = 16000
    recorder = VoiceRecorder(target_sample_rate=sample_rate)

    print("\n" + "=" * 60)
    print("=== VOICE TASK CALIBRATION SYSTEM ===")
    print("=" * 60)
    print("[System] Connecting to the recorder. Please wait quietly...")
    print("-" * 60)

    total_calibration_duration = 15.0
    timestamps = {}

    def execute_prompt(prompt, duration_s, label, global_start_ts):
        print(f"\n{prompt}")
        for i in range(3, 0, -1):
            print(f"Starting in... {i}")
            time.sleep(1)
        print("Recording this calibration segment now...")

        timestamps[f"{label}_start"] = time.time() - global_start_ts
        time.sleep(duration_s)
        timestamps[f"{label}_end"] = time.time() - global_start_ts
        print("Segment ended.")

    def run_prompts_sequentially(mark_start, mark_end):
        print("\n" + "=" * 60)
        print("=== HARDWARE READY: STARTING CALIBRATION ===")
        print("=" * 60)
        mark_start()
        sync_start_ts = time.time()

        execute_prompt(
            "[Task 1 of 3] Background noise and silence\n"
            "Instruction: Please stay completely quiet and still.",
            3.0,
            "quiet",
            sync_start_ts,
        )
        execute_prompt(
            "[Task 2 of 3] Weak voice\n"
            "Instruction: Please say 'Ahhhhh' as quietly as possible while staying clear.",
            4.0,
            "weak",
            sync_start_ts,
        )
        execute_prompt(
            "[Task 3 of 3] Normal voice\n"
            "Instruction: Please say 'Ahhhhh' in a normal, steady voice.",
            4.0,
            "normal",
            sync_start_ts,
        )
        mark_end()

    full_audio, actual_sample_rate = recorder.record(
        total_calibration_duration,
        task_runner=run_prompts_sequentially,
    )
    full_audio = full_audio.flatten()

    print("\n" + "-" * 60)
    print("Input device:", recorder.last_device_name or recorder.last_device)
    if recorder.last_tobii_error and recorder.active_source != "tobii":
        print("Tobii audio fallback reason:", recorder.last_tobii_error)
    print("-" * 60)
    print("Extracting calibration windows from the recorded audio...")

    if actual_sample_rate != sample_rate:
        sample_rate = int(actual_sample_rate)

    def extract_window(label, default_duration):
        start_idx = int(timestamps.get(f"{label}_start", 0) * sample_rate)
        end_idx = int(timestamps.get(f"{label}_end", default_duration) * sample_rate)

        if start_idx >= len(full_audio):
            start_idx = max(0, len(full_audio) - int(default_duration * sample_rate))
        if end_idx > len(full_audio) or end_idx <= start_idx:
            end_idx = len(full_audio)

        return full_audio[start_idx:end_idx]

    quiet_audio = extract_window("quiet", 3.0)
    weak_audio = extract_window("weak", 4.0)
    normal_audio = extract_window("normal", 4.0)

    quiet_energy = float(np.sqrt(np.mean(quiet_audio**2))) if quiet_audio.size > 0 else 0.0002
    weak_energy = float(np.sqrt(np.mean(weak_audio**2))) if weak_audio.size > 0 else 0.0015
    normal_energy = float(np.sqrt(np.mean(normal_audio**2))) if normal_audio.size > 0 else 0.0040

    if quiet_energy >= weak_energy:
        print("Warning: background RMS is higher than weak speech RMS; applying conservative correction.")
        dynamic_energy = float(weak_energy * 0.5)
    else:
        dynamic_energy = float(min((quiet_energy * 1.35), (weak_energy * 0.12)))

    dynamic_energy = float(np.clip(dynamic_energy, 0.0005, 0.003))

    frame_len = int(round(sample_rate * 25 / 1000.0))
    hop_len = int(round(sample_rate * 10 / 1000.0))
    frame_count = 1 + max(0, (len(normal_audio) - frame_len) // hop_len)

    if frame_count > 5:
        shape = (frame_count, frame_len)
        strides = (normal_audio.strides[0] * hop_len, normal_audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(normal_audio, shape=shape, strides=strides)
        frame_rms = np.sqrt(np.mean(frames**2, axis=1))

        core_frames = frames[frame_rms > (dynamic_energy * 1.2)]
        if len(core_frames) > 5:
            fft_data = np.abs(np.fft.rfft(core_frames, n=512, axis=1))
            fft_norm = fft_data / (np.sum(fft_data, axis=1, keepdims=True) + 1e-3)
            flux_per_frame = np.sqrt(np.sum(np.diff(fft_norm, axis=0) ** 2, axis=1))
            dynamic_flux = float(np.clip(np.std(flux_per_frame) * 1.5, 0.043, 0.065))
        else:
            dynamic_flux = 0.045
    else:
        dynamic_flux = 0.045

    device_name = str(recorder.last_device_name or recorder.last_device or "default")
    profile_key = _device_key(device_name)
    run_data = {
        "MIN_ENERGY_THRESHOLD": dynamic_energy,
        "MAX_FLUX_STD": dynamic_flux,
        "quiet_rms": quiet_energy,
        "weak_rms": weak_energy,
        "normal_rms": normal_energy,
        "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": device_name,
        "source": recorder.active_source,
        "profile_key": profile_key,
    }
    if recorder.last_tobii_error:
        run_data["tobii_error"] = recorder.last_tobii_error

    calib_data = _load_existing_calibration()
    profiles = calib_data.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}

    previous_profile = profiles.get(profile_key, {})
    previous_runs = previous_profile.get("runs", []) if isinstance(previous_profile, dict) else []
    if not isinstance(previous_runs, list):
        previous_runs = []

    profile_data = dict(run_data)
    profile_data["runs"] = [*previous_runs, run_data]
    profiles[profile_key] = profile_data

    calib_data.update(run_data)
    calib_data["active_profile"] = profile_key
    calib_data["profiles"] = profiles

    with open(CALIBRATION_FILE, "w") as f:
        json.dump(calib_data, f, indent=4)

    print(f"Calibration completed. Parameters saved to '{CALIBRATION_FILE}'.")
    print(f"  - Energy Threshold: {dynamic_energy:.6f}")
    print(f"  - Flux Threshold:   {dynamic_flux:.6f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_calibration()
