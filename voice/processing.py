import os
import json
import numpy as np
from scipy.fftpack import dct
from scipy.signal import lfilter, resample_poly


class VoiceFeatureExtractionError(Exception):
    """חריגה מותאמת אישית עבור כשלים בחילוץ פיצ'רים אקוסטיים"""
    def __init__(self, message, error_code=None, partial_features=None):
        super().__init__(message)
        self.error_code = error_code
        self.partial_features = partial_features or {
            "mfcc": None, "pitch": None, "lpc": None, "parcor": None, "delta_lpc": None
        }


class VoiceFeatureExtractor:
    """
    מערכת חכמה לסינון, עיבוד וחילוץ מאפיינים אקוסטיים (Features) מקול אנושי.
    המערכת מותאמת למשימות קליניות של הפקת צליל מתמשך ("אההה") ומיועדת להבטיח איכות דאטה מקסימלית.
    """

    SAMPLE_RATE = 16000
    PREEMPHASIS = 0.97
    FRAME_LENGTH_MS = 25
    HOP_LENGTH_MS = 10
    LPC_ORDER = 12 
    
    FMIN = 40.0
    FMAX = 500.0
    
    # ספים אופטימליים למניעת רעשי רקע תוך שמירה על רגישות לקול אנושי
    MIN_ENERGY_THRESHOLD = 0.001      
    MIN_TOTAL_SPEECH_DURATION_S = 5.0  
    MAX_FLUX_STD = 0.045000            
    MAX_PITCH_REL_VARIATION = 0.550000

    CALIB_FILE = ".voice_calib.json"

    @classmethod
    def _device_key(cls, input_device=None) -> str:
        if isinstance(input_device, dict):
            name = input_device.get("name") or input_device.get("device") or input_device.get("source")
        else:
            name = input_device
        key = str(name or "default").strip().lower()
        return " ".join(key.split())

    @classmethod
    def _microphone_type(cls, input_device=None) -> str:
        if isinstance(input_device, dict):
            source = (
                input_device.get("source")
                or input_device.get("active_source")
                or input_device.get("final_audio_source")
            )
            if source in {"local", "tobii"}:
                return source
            name = input_device.get("name") or input_device.get("device")
        else:
            name = input_device
        return "tobii" if "tobii" in str(name or "").lower() else "local"

    @classmethod
    def _load_calibration_config(cls) -> dict:
        if not os.path.exists(cls.CALIB_FILE):
            return {}
        try:
            with open(cls.CALIB_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to load calibration file, using defaults: {e}")
            return {}

    @classmethod
    def calibration_for_device(cls, input_device=None) -> dict:
        config = cls._load_calibration_config()
        defaults = {
            "MIN_ENERGY_THRESHOLD": cls.MIN_ENERGY_THRESHOLD,
            "MAX_FLUX_STD": cls.MAX_FLUX_STD,
        }

        microphone_type = cls._microphone_type(input_device)
        profile = config.get(microphone_type)
        if isinstance(profile, dict):
            return {
                "MIN_ENERGY_THRESHOLD": profile.get("MIN_ENERGY_THRESHOLD", defaults["MIN_ENERGY_THRESHOLD"]),
                "MAX_FLUX_STD": profile.get("MAX_FLUX_STD", defaults["MAX_FLUX_STD"]),
                "quiet_rms": profile.get("quiet_rms"),
                "weak_rms": profile.get("weak_rms"),
                "normal_rms": profile.get("normal_rms"),
                "profile_key": microphone_type,
            }

        # Backward compatibility for calibration files created before the
        # per-microphone-type format.
        profiles = config.get("profiles")
        if isinstance(profiles, dict):
            key = cls._device_key(input_device)
            profile = profiles.get(key)
            if profile is None and isinstance(input_device, dict):
                profile = profiles.get(cls._device_key(input_device.get("source")))
            if profile is None and input_device is None:
                active_key = config.get("active_profile")
                profile = profiles.get(active_key) if active_key else None
            if isinstance(profile, dict):
                return {
                    "MIN_ENERGY_THRESHOLD": profile.get("MIN_ENERGY_THRESHOLD", defaults["MIN_ENERGY_THRESHOLD"]),
                    "MAX_FLUX_STD": profile.get("MAX_FLUX_STD", defaults["MAX_FLUX_STD"]),
                    "quiet_rms": profile.get("quiet_rms"),
                    "weak_rms": profile.get("weak_rms"),
                    "normal_rms": profile.get("normal_rms"),
                    "profile_key": profile.get("profile_key") or cls._device_key(input_device),
                }
            if input_device is not None:
                return {**defaults, "profile_key": "default"}

        return {
            "MIN_ENERGY_THRESHOLD": config.get("MIN_ENERGY_THRESHOLD", defaults["MIN_ENERGY_THRESHOLD"]),
            "MAX_FLUX_STD": config.get("MAX_FLUX_STD", defaults["MAX_FLUX_STD"]),
            "quiet_rms": config.get("quiet_rms"),
            "weak_rms": config.get("weak_rms"),
            "normal_rms": config.get("normal_rms"),
            "profile_key": "legacy",
        }

    @classmethod
    def preprocess_audio(cls, audio: np.ndarray, sample_rate: int, calibration: dict | None = None):
        calibration = calibration or {}
        min_energy_threshold = float(calibration.get("MIN_ENERGY_THRESHOLD", cls.MIN_ENERGY_THRESHOLD))
        max_flux_std = float(calibration.get("MAX_FLUX_STD", cls.MAX_FLUX_STD))
        quiet_rms = calibration.get("quiet_rms")
        weak_rms = calibration.get("weak_rms")
        if quiet_rms is not None or weak_rms is not None:
            threshold_candidates = [min_energy_threshold]
            if quiet_rms is not None:
                threshold_candidates.append(float(quiet_rms) * 1.35)
            if weak_rms is not None:
                threshold_candidates.append(float(weak_rms) * 0.12)
            min_energy_threshold = float(np.clip(min(threshold_candidates), 0.0005, 0.003))

        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1)

        audio = np.asarray(audio, dtype=np.float32)

        # 1. בדיקת השתקה / חוסר מיקרופון גלובלי
        global_rms = float(np.sqrt(np.mean(audio**2)))
        max_amplitude = float(np.max(np.abs(audio)))
        mute_rms_threshold = min(0.0015, max(0.00035, min_energy_threshold * 0.45))
        if global_rms < mute_rms_threshold and max_amplitude < 0.01:
            return None, "MUTE"

        if sample_rate != cls.SAMPLE_RATE:
            gcd = np.gcd(int(sample_rate), int(cls.SAMPLE_RATE))
            audio = resample_poly(
                audio,
                cls.SAMPLE_RATE // gcd,
                int(sample_rate) // gcd,
            ).astype(np.float32)

        frame_length = cls._frame_length(cls.SAMPLE_RATE)
        hop_length = cls._hop_length(cls.SAMPLE_RATE)
        
        # 2. הפרדה לשגיאה טכנית: הקובץ קצר מכדי להכיל פריים בודד
        if len(audio) < frame_length:
            return None, "HARDWARE_SHORT"

        frame_count = 1 + max(0, (len(audio) - frame_length) // hop_length)
        shape = (frame_count, frame_length)
        strides = (audio.strides[0] * hop_length, audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)

        frame_rms = np.sqrt(np.mean(frames**2, axis=1))
        speech_frames = (frame_rms > min_energy_threshold).astype(np.int32)

        # --- מנגנון סגירה מורפולוגית (Morphological Closing) חכם מותאם אישית ---
        # חיבור "חורים" קטנים של שקט (עד 15 פריימים = 150 מילישניות) בתוך רצף הדיבור
        # שלב א: הרחבה (Dilation) - הפיכת שקט קצר לדיבור
        kernel_size = 15
        dilated = np.copy(speech_frames)
        for i in range(len(speech_frames)):
            if speech_frames[i] == 1:
                start = max(0, i - kernel_size // 2)
                end = min(len(speech_frames), i + kernel_size // 2 + 1)
                dilated[start:end] = 1
        
        # שלב ב: שחיקה (Erosion) - החזרת הגבולות המקוריים של הסגמנט הרציף
        smoothed_speech = np.copy(dilated)
        for i in range(len(dilated)):
            start = max(0, i - kernel_size // 2)
            end = min(len(dilated), i + kernel_size // 2 + 1)
            if np.any(dilated[start:end] == 0):
                smoothed_speech[i] = 0
        # ----------------------------------------------------------------------

        padded = np.pad(smoothed_speech, (1, 1), 'constant', constant_values=0)
        diffs = np.diff(padded)
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]

        valid_audio_segments = []
        total_valid_duration = 0.0
        
        any_speech_detected_at_all = False
        speech_rejected_due_to_flux = False

        for s, e in zip(starts, ends):
            seg_len_frames = e - s
            seg_duration = (seg_len_frames * cls.HOP_LENGTH_MS) / 1000.0
            
            # סגמנטים קצרים מאוד (פחות מ-300 מילישניות) ששרדו ייפסלו
            if seg_duration < 0.3:
                continue

            any_speech_detected_at_all = True
            seg_frames = frames[s:e]
            seg_rms = frame_rms[s:e]
            
            core_seg_frames = seg_frames[seg_rms > (min_energy_threshold * 1.5)]
            if len(core_seg_frames) > 5:
                fft_data = np.abs(np.fft.rfft(core_seg_frames, n=512, axis=1))
                fft_norm = fft_data / (np.sum(fft_data, axis=1, keepdims=True) + 1e-3)
                flux_per_frame = np.sqrt(np.sum(np.diff(fft_norm, axis=0)**2, axis=1))
                flux_std = float(np.std(flux_per_frame))
                
                if flux_std > max_flux_std:
                    speech_rejected_due_to_flux = True
                    continue

            start_sample = s * hop_length
            end_sample = min(len(audio), e * hop_length + (frame_length - hop_length))
            valid_audio_segments.append(audio[start_sample:end_sample])
            total_valid_duration += seg_duration

        # 3. בדיקת רף ה-5 שניות של צליל "אה" תקין ונקי
        if total_valid_duration >= cls.MIN_TOTAL_SPEECH_DURATION_S and len(valid_audio_segments) > 0:
            pass 
        
        # 4. אבחון סיבות לכשל במידה ואין מספיק זמן מצטבר
        else:
            if speech_rejected_due_to_flux or (any_speech_detected_at_all and len(valid_audio_segments) == 0):
                return None, "SPEECH"
            
            if total_valid_duration > 0.5:
                return None, "SHORT"
            
            return None, "SILENT"

        if len(valid_audio_segments) == 0:
            return None, "SILENT"

        audio = np.concatenate(valid_audio_segments)

        global_rms = np.sqrt(np.mean(audio**2))
        if global_rms > 1e-5:
            target_rms = 0.1
            audio = audio * (target_rms / global_rms)

        if np.max(np.abs(audio)) > 1.0:
            audio = audio / np.max(np.abs(audio))

        audio = lfilter([1.0, -cls.PREEMPHASIS], [1.0], audio)
        return audio, cls.SAMPLE_RATE

    @classmethod
    def _frame_length(cls, sr: int) -> int:
        return int(round(sr * cls.FRAME_LENGTH_MS / 1000.0))

    @classmethod
    def _hop_length(cls, sr: int) -> int:
        return int(round(sr * cls.HOP_LENGTH_MS / 1000.0))

    @classmethod
    def frame_signal(cls, audio: np.ndarray, sr: int):
        frame_length = cls._frame_length(sr)
        hop_length = cls._hop_length(sr)
        if len(audio) < frame_length:
            padding = frame_length - len(audio)
            audio = np.pad(audio, (0, padding), mode="constant")

        frame_count = 1 + max(0, (len(audio) - frame_length) // hop_length)
        shape = (frame_count, frame_length)
        strides = (audio.strides[0] * hop_length, audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides).copy()
        window = np.hamming(frame_length)
        return frames * window

    @classmethod
    def extract_mfcc(cls, audio: np.ndarray, sr: int, n_mfcc: int = 13):
        frames = cls.frame_signal(audio, sr)
        n_fft = max(512, cls._frame_length(sr) * 2)
        spectrum = np.fft.rfft(frames, n=n_fft, axis=1)
        power = np.maximum(np.abs(spectrum) ** 2, np.finfo(np.float32).eps)
        coeffs = dct(np.log(power), type=2, axis=1, norm="ortho")[:, :n_mfcc]
        return coeffs.astype(np.float32)

    @classmethod
    def extract_pitch(cls, audio: np.ndarray, sr: int):
        if len(audio) < cls._frame_length(sr):
            return np.array([], dtype=np.float32)

        frames = cls.frame_signal(audio, sr)
        min_lag = max(1, int(sr / cls.FMAX))
        max_lag = min(frames.shape[1] - 1, int(sr / cls.FMIN))
        pitches = np.full((frames.shape[0],), np.nan, dtype=np.float32)

        for index, frame in enumerate(frames):
            frame = frame - np.mean(frame)
            energy = float(np.dot(frame, frame))
            if energy <= 1e-6:
                continue
            corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
            search = corr[min_lag:max_lag + 1]
            if search.size == 0:
                continue
            lag = int(np.argmax(search)) + min_lag
            peak = corr[lag] / max(corr[0], np.finfo(np.float32).eps)
            if peak >= 0.25:
                pitches[index] = float(sr / lag)

        valid_indices = ~np.isnan(pitches)
        if np.sum(valid_indices) > 5:
            import scipy.signal as signal
            smoothed_valid = signal.medfilt(pitches[valid_indices], kernel_size=5)
            pitches[valid_indices] = smoothed_valid

        return pitches

    @classmethod
    def _levinson_durbin(cls, r: np.ndarray, order: int):
        a = np.zeros(order + 1, dtype=np.float64)
        k = np.zeros(order, dtype=np.float64)
        a[0] = 1.0
        e = r[0]

        for i in range(1, order + 1):
            s = 0.0
            for j in range(1, i):
                s += a[j] * r[i - j]
            if e == 0:
                ki = 0.0
            else:
                ki = (r[i] - s) / e
            k[i - 1] = ki
            a[i] = ki
            for j in range(1, (i // 2) + 1):
                aj = a[j]
                aij = a[i - j]
                a[j] = aj - ki * aij
                if j != i - j:
                    a[i - j] = aij - ki * aj
            e *= (1.0 - ki * ki)
        return a, k

    @classmethod
    def _compute_frame_lpc_features(cls, audio: np.ndarray, sr: int, mode="lpc"):
        frames = cls.frame_signal(audio, sr)
        order = cls.LPC_ORDER

        if mode == "lpc":
            features = np.zeros((frames.shape[0], order + 1), dtype=np.float32)
        else:
            features = np.zeros((frames.shape[0], order), dtype=np.float32)

        for index, frame in enumerate(frames):
            if np.allclose(frame, 0.0):
                continue
            r = np.correlate(frame, frame, mode="full")[len(frame) - 1:len(frame) + order]
            if r.shape[0] < order + 1 or r[0] == 0:
                continue
            try:
                lpc_coeffs, parcor_coeffs = cls._levinson_durbin(r, order)
                if mode == "lpc":
                    features[index] = lpc_coeffs.astype(np.float32)
                else:
                    features[index] = parcor_coeffs.astype(np.float32)
            except Exception:
                continue
        return features

    @classmethod
    def _compute_lpc_and_parcor_features(cls, audio: np.ndarray, sr: int):
        frames = cls.frame_signal(audio, sr)
        order = cls.LPC_ORDER
        lpc_features = np.zeros((frames.shape[0], order + 1), dtype=np.float32)
        parcor_features = np.zeros((frames.shape[0], order), dtype=np.float32)

        for index, frame in enumerate(frames):
            if np.allclose(frame, 0.0):
                continue
            r = np.correlate(frame, frame, mode="full")[len(frame) - 1:len(frame) + order]
            if r.shape[0] < order + 1 or r[0] == 0:
                continue
            try:
                lpc_coeffs, parcor_coeffs = cls._levinson_durbin(r, order)
                lpc_features[index] = lpc_coeffs.astype(np.float32)
                parcor_features[index] = parcor_coeffs.astype(np.float32)
            except Exception:
                continue

        return lpc_features, parcor_features

    @classmethod
    def extract_lpc(cls, audio: np.ndarray, sr: int):
        return cls._compute_frame_lpc_features(audio, sr, mode="lpc")

    @classmethod
    def extract_parcor(cls, audio: np.ndarray, sr: int):
        return cls._compute_frame_lpc_features(audio, sr, mode="parcor")

    @classmethod
    def compute_delta_lpc(cls, lpc_features: np.ndarray):
        if lpc_features.ndim != 2 or lpc_features.shape[0] < 2:
            return np.zeros_like(lpc_features, dtype=np.float32)
        delta = np.diff(lpc_features, axis=0)
        padding = np.zeros((1, lpc_features.shape[1]), dtype=np.float32)
        return np.vstack([padding, delta]).astype(np.float32)

    @classmethod
    def extract_features(cls, raw_audio: np.ndarray, sample_rate: int, input_device=None):
        calibration = cls.calibration_for_device(input_device)
        preprocessed_res = cls.preprocess_audio(raw_audio, sample_rate, calibration=calibration)
        
        empty_features = {
            "mfcc": None, "pitch": None, "lpc": None, "parcor": None, "delta_lpc": None
        }

        if isinstance(preprocessed_res, tuple) and preprocessed_res[0] is None:
            raise VoiceFeatureExtractionError(
                f"Audio preprocessing failed with code: {preprocessed_res[1]}", 
                error_code=preprocessed_res[1],
                partial_features=empty_features
            )

        working_audio, working_sr = preprocessed_res

        mfcc = cls.extract_mfcc(working_audio, working_sr)
        pitch = cls.extract_pitch(working_audio, working_sr)
        lpc, parcor = cls._compute_lpc_and_parcor_features(working_audio, working_sr)
        delta_lpc = cls.compute_delta_lpc(lpc)

        valid_pitches = pitch[~np.isnan(pitch)]
        if valid_pitches.size > 2:
            pitch_mean = float(np.mean(valid_pitches))
            pitch_std = float(np.std(valid_pitches))
            if pitch_mean > 0:
                pitch_cv = pitch_std / pitch_mean
                if pitch_cv > cls.MAX_PITCH_REL_VARIATION:
                    raise VoiceFeatureExtractionError(
                        "Audio pitch stability verification failed.", 
                        error_code="UNSTABLE_PITCH",
                        partial_features=empty_features
                    )

        target_frames = pitch.shape[0]
        if target_frames == 0:
            raise VoiceFeatureExtractionError(
                "No valid audio frames detected.", 
                error_code="SILENT",
                partial_features=empty_features
            )

        def adjust_time_dimension(arr, target_len):
            curr_len = arr.shape[0]
            if curr_len == target_len:
                return arr
            if curr_len > target_len:
                return arr[:target_len]
            pad_width = target_len - curr_len
            if arr.ndim == 1:
                return np.pad(arr, (0, pad_width), mode='edge')
            else:
                return np.pad(arr, ((0, pad_width), (0, 0)), mode='edge')

        return {
            "mfcc": adjust_time_dimension(mfcc, target_frames),
            "pitch": pitch,
            "lpc": adjust_time_dimension(lpc, target_frames),
            "parcor": adjust_time_dimension(parcor, target_frames),
            "delta_lpc": adjust_time_dimension(delta_lpc, target_frames),
        }
