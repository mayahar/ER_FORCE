import numpy as np
from scipy.fftpack import dct
from scipy.signal import lfilter, resample_poly


class VoiceFeatureExtractionError(Exception):
    pass


class VoiceFeatureExtractor:
    SAMPLE_RATE = 16000
    PREEMPHASIS = 0.97
    FRAME_LENGTH_MS = 25
    HOP_LENGTH_MS = 10
    LPC_ORDER = 12 
    FMIN = 50.0
    FMAX = 500.0
    
    # -------------------------------------------------------------
    # ספים מעודכנים להגנה כפולה: מניעת אזעקות שווא + חסימת דיבור
    # -------------------------------------------------------------
    MIN_ENERGY_THRESHOLD = 0.0004      
    MIN_TOTAL_SPEECH_DURATION_S = 2.5  
    MAX_FLUX_STD = 0.035000            # סף ליברלי לנשימות
    MAX_PITCH_STD = 88.000000          # סף יציבות תדר קשיח: מונע אינטונציה של דיבור חופשי

    @classmethod
    def preprocess_audio(cls, audio: np.ndarray, sample_rate: int):
        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1)

        audio = np.asarray(audio, dtype=np.float32)

        if sample_rate != cls.SAMPLE_RATE:
            gcd = np.gcd(int(sample_rate), int(cls.SAMPLE_RATE))
            audio = resample_poly(
                audio,
                cls.SAMPLE_RATE // gcd,
                int(sample_rate) // gcd,
            ).astype(np.float32)

        frame_length = cls._frame_length(cls.SAMPLE_RATE)
        hop_length = cls._hop_length(cls.SAMPLE_RATE)
        
        if len(audio) < frame_length:
            raise VoiceFeatureExtractionError("Audio file is too short.")

        frame_count = 1 + max(0, (len(audio) - frame_length) // hop_length)
        shape = (frame_count, frame_length)
        strides = (audio.strides[0] * hop_length, audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)

        # 1. בדיקת עוצמה ומשך זמן מצטבר
        frame_rms = np.sqrt(np.mean(frames**2, axis=1))
        speech_frames = frame_rms > cls.MIN_ENERGY_THRESHOLD
        speech_duration = (np.sum(speech_frames) * cls.HOP_LENGTH_MS) / 1000.0

        if speech_duration < cls.MIN_TOTAL_SPEECH_DURATION_S:
            raise VoiceFeatureExtractionError("Valid speech duration too short.")

        # 2. ניתוח תבנית השטף הספקטרלי (סינון חלונות מעבר לנשימה)
        # כדי למנוע מהנשימות להקפיץ את המדד, ניקח רק פרימים שהם בלב הדיבור (עוצמה גבוהה מהסף)
        core_speech_frames = frame_rms > (cls.MIN_ENERGY_THRESHOLD * 2.5)
        valid_frames = frames[core_speech_frames]
        
        if len(valid_frames) > 10:
            fft_data = np.abs(np.fft.rfft(valid_frames, n=512, axis=1))
            fft_norm = fft_data / (np.sum(fft_data, axis=1, keepdims=True) + 1e-3)
            flux_per_frame = np.sqrt(np.sum(np.diff(fft_norm, axis=0)**2, axis=1))
            flux_std = float(np.std(flux_per_frame))
            
            if flux_std > cls.MAX_FLUX_STD:
                raise VoiceFeatureExtractionError("Audio contains highly dynamic speech patterns (Flux).")

        # 3. ניקוי רעשים דיגיטלי
        try:
            from scipy.signal import butter, sosfilt
            sos = butter(4, [60.0, 4000.0], btype='bandpass', fs=cls.SAMPLE_RATE, output='sos')
            audio = sosfilt(sos, audio)
        except ImportError:
            pass

        # 4. נרמול עוצמה גלובלי
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
    def extract_features(cls, audio: np.ndarray, sample_rate: int):
        try:
            audio, sr = cls.preprocess_audio(audio, sample_rate)
        except VoiceFeatureExtractionError:
            return {
                "mfcc": None, "pitch": None, "lpc": None, "parcor": None, "delta_lpc": None
            }
        
        mfcc = cls.extract_mfcc(audio, sr)
        pitch = cls.extract_pitch(audio, sr)
        lpc = cls.extract_lpc(audio, sr)
        parcor = cls.extract_parcor(audio, sr)
        delta_lpc = cls.compute_delta_lpc(lpc)

        # -------------------------------------------------------------
        # שכבת הגנה שנייה: בדיקת אי יציבות תדר קול (Pitch Instability)
        # -------------------------------------------------------------
        valid_pitches = pitch[~np.isnan(pitch)]
        if valid_pitches.size > 2:
            pitch_std = float(np.std(valid_pitches))
            # אם התדר קופץ ורוקד כמו בדיבור חופשי (מעל 88.0) - נפסול
            if pitch_std > cls.MAX_PITCH_STD:
                return {
                    "mfcc": None, "pitch": None, "lpc": None, "parcor": None, "delta_lpc": None
                }

        target_frames = pitch.shape[0]

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

        if target_frames == 0:
            return {
                "mfcc": None, "pitch": None, "lpc": None, "parcor": None, "delta_lpc": None
            }

        return {
            "mfcc": adjust_time_dimension(mfcc, target_frames),
            "pitch": pitch,
            "lpc": adjust_time_dimension(lpc, target_frames),
            "parcor": adjust_time_dimension(parcor, target_frames),
            "delta_lpc": adjust_time_dimension(delta_lpc, target_frames),
        }