import os
import sys
import numpy as np

# הגדרת נתיב השורש
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from voice.recorder import VoiceRecorder
from voice.calibrate import CALIBRATION_FILE
from voice.processing import VoiceFeatureExtractor

def run_standalone_test():
    sample_rate = 16000
    duration = 10.0
    recorder = VoiceRecorder(target_sample_rate=sample_rate)
    
    print("\n" + "="*60)
    print("=== VOICE TASK STANDALONE TEST (PERFECT SYNCHRONIZATION) ===")
    print("="*60)
    print("[מערכת] יוצר קשר ומסנכרן חומרה ברשת. נא להמתין בשקט לאישור...")
    print("-"*60)
    
    # פתיחת ההקלטה (הספירה לאחור תקרה בפנים, רק אחרי שרשת הטובי ננעלה!)
    def run_voice_prompt(mark_start, mark_end):
        import time

        print("\n" + "="*60)
        print("=== HARDWARE READY: STARTING VOICE TASK ===")
        print("="*60)
        print("Instructions: Produce a sustained 'Ah' sound. Recording is 10 seconds.")
        print("The recording will start in 3 seconds... Prepare your voice!")
        print("-"*60)
        for i in range(3, 0, -1):
            print(f"Starting in... {i}")
            time.sleep(1)
        print("\nRECORDING NOW... Say 'Ahhhhh'!")
        mark_start()
        time.sleep(duration)
        mark_end()
        print("Voice window ended.")

    audio_data, _ = recorder.record(duration, task_runner=run_voice_prompt)
    audio_data = audio_data.flatten()
    
    # טעינת ספי קליברציה
    energy_thresh = 0.0012
    flux_std_thresh = 0.045
    if os.path.exists(CALIBRATION_FILE):
        try:
            calib = VoiceFeatureExtractor.calibration_for_device(
                {
                    "name": recorder.last_device_name,
                    "source": recorder.active_source,
                }
            )
            energy_thresh = calib.get("MIN_ENERGY_THRESHOLD", energy_thresh)
            flux_std_thresh = calib.get("MAX_FLUX_STD", flux_std_thresh)
            print(f"[מערכת] נטענו ספים מכוילים בהצלחה עבור סוג מיקרופון: {calib.get('profile_key')}")
        except Exception:
            pass

    # ניתוח הנתונים (RAW ANALYSIS)
    global_rms = float(np.sqrt(np.mean(audio_data**2)))
    max_peak = float(np.max(np.abs(audio_data)))
    
    print("\n📊 RAW DATA ANALYSIS:")
    print(f"  1. Global Signal RMS (Volume) : {global_rms:.6f}")
    print(f"  2. Maximum Peak Amplitude    : {max_peak:.6f}")
    print(f"  3. Extracted Array Length    : {len(audio_data)} samples ({len(audio_data)/sample_rate:.2f}s)")
    print(f"\n✅ SYSTEM STATUS: SUCCESS (Source Used: {recorder.active_source})")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_standalone_test()
