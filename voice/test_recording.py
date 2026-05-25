import time
import numpy as np
import sounddevice as sd
from processing import VoiceFeatureExtractor


def run_live_voice_test():
    duration = 10.0  
    sample_rate = 16000  
    
    print("\n" + "="*60)
    print("=== VOICE TASK VALIDATION SYSTEM (DIAGNOSTIC MODE) ===")
    print("="*60)
    print(f"Instructions: Produce a sustained, loud 'Ah' sound for {duration} seconds.")
    print("The recording will start in 3 seconds... Prepare your voice!")
    print("-"*60)
    
    for i in range(3, 0, -1):
        print(f"Starting in... {i}")
        time.sleep(1)
        
    print("\n🔴 RECORDING NOW... Say 'Ahhhhh'!")
    
    recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    sd.wait()  
    
    print("⏹️ Recording finished. Analyzing raw signals...")
    print("-"*60)
    
    audio_data = recording.flatten()
    
    global_rms = float(np.sqrt(np.mean(audio_data**2)))
    max_amplitude = float(np.max(np.abs(audio_data)))
    
    frame_len = int(round(sample_rate * 25 / 1000.0))
    hop_len = int(round(sample_rate * 10 / 1000.0))
    frame_count = 1 + max(0, (len(audio_data) - frame_len) // hop_len)
    
    shape = (frame_count, frame_len)
    strides = (audio_data.strides[0] * hop_len, audio_data.strides[0])
    frames = np.lib.stride_tricks.as_strided(audio_data, shape=shape, strides=strides)
    frame_rms = np.sqrt(np.mean(frames**2, axis=1))
    
    features = VoiceFeatureExtractor.extract_features(audio_data, sample_rate)
    
    energy_thresh = getattr(VoiceFeatureExtractor, 'MIN_ENERGY_THRESHOLD', 0.0004)
    duration_thresh = getattr(VoiceFeatureExtractor, 'MIN_TOTAL_SPEECH_DURATION_S', 2.5)
    flux_std_thresh = getattr(VoiceFeatureExtractor, 'MAX_FLUX_STD', 0.035)
    pitch_cv_thresh = getattr(VoiceFeatureExtractor, 'MAX_PITCH_REL_VARIATION', 0.38)
    
    speech_frames = frame_rms > energy_thresh
    detected_duration = (np.sum(speech_frames) * 10) / 1000.0
    
    core_speech = frame_rms > (energy_thresh * 2.5)
    valid_frames = frames[core_speech]
    flux_std = 0.0
    if len(valid_frames) > 10:
        fft_data = np.abs(np.fft.rfft(valid_frames, n=512, axis=1))
        fft_norm = fft_data / (np.sum(fft_data, axis=1, keepdims=True) + 1e-3)
        flux_per_frame = np.sqrt(np.sum(np.diff(fft_norm, axis=0)**2, axis=1))
        flux_std = float(np.std(flux_per_frame))

    # חילוץ פיץ' עצמאי לצורך לוג מפורט
    raw_pitch = VoiceFeatureExtractor.extract_pitch(audio_data, sample_rate)
    valid_pitches = raw_pitch[~np.isnan(raw_pitch)] if raw_pitch.size > 0 else np.array([])
    
    pitch_mean = float(np.mean(valid_pitches)) if valid_pitches.size > 0 else 0.0
    pitch_std = float(np.std(valid_pitches)) if valid_pitches.size > 2 else 0.0
    pitch_cv = pitch_std / pitch_mean if pitch_mean > 0 else 0.0

    print("\n📊 RAW DATA ANALYSIS:")
    print(f"  1. Global Signal RMS (Volume) : {global_rms:.6f}")
    print(f"  2. Maximum Peak Amplitude    : {max_amplitude:.6f}")
    print(f"  3. Active Speech Duration    : {detected_duration:.2f} seconds  (Required: >= {duration_thresh}s)")
    print(f"  4. Spectral Flux Volatility  : {flux_std:.6f}  (Required: <= {flux_std_thresh})")
    print(f"  5. Relative Pitch Variation  : {pitch_cv:.4f}  (Required: <= {pitch_cv_thresh})")
    print(f"     [Pitch Mean: {pitch_mean:.1f} Hz, Pitch Std: {pitch_std:.2f}]")
    print("-"*60)
    
    if features["pitch"] is None or features["mfcc"] is None:
        print("❌ PIPELINE RESULT: REJECTED (Returns Empty / None Values)")
        print("\n💡 DIAGNOSTIC CONCLUSION:")
        if global_rms < 0.0001:
            print("   -> Microphone input is silent or muted.")
        elif detected_duration < duration_thresh:
            print(f"   -> FAILED ENERGY/DURATION CHECK: Active speech was only {detected_duration:.2f}s.")
        elif flux_std > flux_std_thresh:
            print("   -> FAILED STABILITY CHECK: Dynamic speech patterns (Flux Volatility) detected!")
        elif pitch_cv > pitch_cv_thresh:
            print(f"   -> FAILED PITCH STABILITY: Voice intonation variation is too high ({pitch_cv * 100:.1f}%).")
    else:
        print("✅ PIPELINE RESULT: SUCCESS (Valid Features Extracted)")
        print(f"   -> Extracted Pitch Mean      : {pitch_mean:.1f} Hz")
        print(f"   -> Extracted Pitch Std Dev   : {pitch_std:.2f}")
        print(f"   -> Total Valid Pitch Frames  : {valid_pitches.size}")
            
    print("="*60 + "\n")


if __name__ == "__main__":
    run_live_voice_test()