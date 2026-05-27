import json
import os
import time
from librosa import cite
from librosa import cite
import numpy as np
import sounddevice as sd

CALIBRATION_FILE = ".voice_calib.json"

def record_audio(prompt, duration=5, sample_rate=16000):
    print(f"\n[Instruction]: {prompt}")
    for i in range(3, 0, -1):
        print(f"starting in... {i}")
        time.sleep(1)
    print("🔴 recording...")
    recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    sd.wait()
    print("⏹️ recording completed")
    return recording.flatten()

def run_calibration():
    sample_rate = 16000
    
    print("=== Calibration system ===")
    
    # 1. הקלטת שקט
    quiet_audio = record_audio("Please remain quiet and still.", duration=4)
    
    # 2. הקלטת דיבור חלש
    faint_audio = record_audio("Please say 'ahhh' as softly as possible (but clearly, not in a whisper).", duration=4)
    
    # 3. הקלטת אההה רגיל
    normal_audio = record_audio("Please say 'ahhh' normally, steadily, and continuously.", duration=5)
    
    print("\n📊 מנתח נתונים ומחשב ספים דינמיים...")
    
    # חישוב סף אנרגיה (RMS)
    rms_quiet = float(np.sqrt(np.mean(quiet_audio**2)))
    rms_faint = float(np.sqrt(np.mean(faint_audio**2)))
    
    # קביעת הסף: מעל הרעש, מתחת לדיבור החלש
    dynamic_energy = max(rms_quiet * 2.0, rms_faint * 0.4)
    dynamic_energy = float(np.clip(dynamic_energy, 0.0002, 0.005)) # גבולות הגנה
    
    # חישוב Spectral Flux מתוך ה-Ah הנורמלי[cite: 1, 2]
    frame_len = int(round(sample_rate * 25 / 1000.0))
    hop_len = int(round(sample_rate * 10 / 1000.0))
    frame_count = 1 + max(0, (len(normal_audio) - frame_len) // hop_len)
    
    shape = (frame_count, frame_len)
    strides = (normal_audio.strides[0] * hop_len, normal_audio.strides[0])
    frames = np.lib.stride_tricks.as_strided(normal_audio, shape=shape, strides=strides)
    frame_rms = np.sqrt(np.mean(frames**2, axis=1))
    
    # לוקחים רק פריימים עוצמתיים כדי לחשב פלקס אמיתי של קול ולא של השקט מסביב
    core_frames = frames[frame_rms > (dynamic_energy * 1.5)]
    if len(core_frames) > 5:
        fft_data = np.abs(np.fft.rfft(core_frames, n=512, axis=1))
        fft_norm = fft_data / (np.sum(fft_data, axis=1, keepdims=True) + 1e-3)
        flux_per_frame = np.sqrt(np.sum(np.diff(fft_norm, axis=0)**2, axis=1))
        base_flux_std = float(np.std(flux_per_frame))
        # נותנים מרווח ביטחון של 40% עבור משתמשים אחרים
        dynamic_flux = float(np.clip(base_flux_std * 1.4, 0.035, 0.065))
    else:
        dynamic_flux = 0.045 # ברירת מחדל במקרה של כשל בחישוב

    # שמירה לקובץ ה-JSON
    config_data = {
        "MIN_ENERGY_THRESHOLD": dynamic_energy,
        "MAX_FLUX_STD": dynamic_flux,
        "CALIBRATED_AT": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(CALIBRATION_FILE, "s") as f:
        json.dump(config_data, f, indent=4)
        
    print(f"✅ calibration completed successfully! thresholds saved to local file '{CALIBRATION_FILE}'.")
    print(f"  - energy threshold selected: {dynamic_energy:.6f}")
    print(f"  - flux threshold selected: {dynamic_flux:.6f}")

if __name__ == "__main__":
    run_calibration()