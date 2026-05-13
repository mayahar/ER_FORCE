import numpy as np
import librosa
from scipy.signal import lfilter



class VoiceFeatureExtractionError(Exception):
    pass


class VoiceFeatureExtractor:
    SAMPLE_RATE = 16000
    PREEMPHASIS = 0.97
    FRAME_LENGTH_MS = 25
    HOP_LENGTH_MS = 10
    LPC_ORDER = 16
    FMIN = 50.0
    FMAX = 500.0

    @classmethod
    def preprocess_audio(cls, audio: np.ndarray, sample_rate: int):
        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1)

        audio = np.asarray(audio, dtype=np.float32)

        if sample_rate != cls.SAMPLE_RATE:
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=cls.SAMPLE_RATE)

        max_amp = np.max(np.abs(audio))
        if max_amp > 0:
            audio = audio / max_amp

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

        frames = librosa.util.frame(audio, frame_length=frame_length, hop_length=hop_length).T
        window = np.hamming(frame_length)
        return frames * window

    @classmethod
    def extract_mfcc(cls, audio: np.ndarray, sr: int, n_mfcc: int = 13):
        frame_length = cls._frame_length(sr)
        hop_length = cls._hop_length(sr)
        mfcc = librosa.feature.mfcc(
            y=audio,
            sr=sr,
            n_mfcc=n_mfcc,
            n_fft=max(512, frame_length * 2),
            hop_length=hop_length,
            win_length=frame_length,
            window="hamming",
            center=False,
        )
        return mfcc.T.astype(np.float32)

    @classmethod
    def extract_pitch(cls, audio: np.ndarray, sr: int):
        if len(audio) < cls._frame_length(sr):
            return np.array([], dtype=np.float32)

        try:
            result = librosa.pyin(
                audio,
                fmin=cls.FMIN,
                fmax=cls.FMAX,
                sr=sr,
                frame_length=cls._frame_length(sr),
                hop_length=cls._hop_length(sr),
                center=False,
            )
            if isinstance(result, tuple):
                f0 = result[0]
            else:
                f0 = result
        except Exception as exc:
            raise VoiceFeatureExtractionError(f"Pitch extraction failed: {exc}") from exc

        if f0 is None:
            return np.full((0,), np.float32)

        return np.asarray(f0, dtype=np.float32)

    @classmethod
    def _levinson_durbin(cls, r: np.ndarray, order: int):
        """
        מימוש אלגוריתם לוינסון-דרבין לחילוץ מקדמי LPC ו-PARCOR.
        מבוסס על פונקציית האוטוקורלציה r.
        """
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
        """
        פונקציית עזר לחישוב LPC או PARCOR לכל הפריימים ללא תלות ב-pysptk.
        """
        frames = cls.frame_signal(audio, sr)
        order = cls.LPC_ORDER
        
        if mode == "lpc":
            features = np.zeros((frames.shape[0], order + 1), dtype=np.float32)
        else:
            features = np.zeros((frames.shape[0], order), dtype=np.float32)

        for index, frame in enumerate(frames):
            if np.allclose(frame, 0.0):
                continue
            
            # חישוב אוטוקורלציה (מקדמים 0 עד order)
            # librosa.autocorrelate מחזירה מערך באורך המקור
            r = librosa.autocorrelate(frame)[:order + 1]
            
            if r[0] == 0:
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
        if lpc_features.ndim != 2:
            return np.zeros_like(lpc_features, dtype=np.float32)

        if lpc_features.shape[0] < 2:
            return np.zeros_like(lpc_features, dtype=np.float32)

        delta = np.diff(lpc_features, axis=0)
        padding = np.zeros((1, lpc_features.shape[1]), dtype=np.float32)
        return np.vstack([padding, delta]).astype(np.float32)

    @classmethod
    def extract_features(cls, audio: np.ndarray, sample_rate: int):
        audio, sr = cls.preprocess_audio(audio, sample_rate)
        mfcc = cls.extract_mfcc(audio, sr)
        pitch = cls.extract_pitch(audio, sr)
        lpc = cls.extract_lpc(audio, sr)
        parcor = cls.extract_parcor(audio, sr)
        delta_lpc = cls.compute_delta_lpc(lpc)

        frame_count = min(
            mfcc.shape[0],
            pitch.shape[0] if pitch.ndim == 1 else pitch.shape[0],
            lpc.shape[0],
            parcor.shape[0],
            delta_lpc.shape[0],
        )

        if frame_count == 0:
            return {
                "mfcc": np.zeros((0, mfcc.shape[1]), dtype=np.float32),
                "pitch": np.full((0,), np.float32(np.nan)),
                "lpc": np.zeros((0, lpc.shape[1]), dtype=np.float32),
                "parcor": np.zeros((0, parcor.shape[1]), dtype=np.float32),
                "delta_lpc": np.zeros((0, delta_lpc.shape[1]), dtype=np.float32),
            }

        return {
            "mfcc": mfcc[:frame_count],
            "pitch": pitch[:frame_count],
            "lpc": lpc[:frame_count],
            "parcor": parcor[:frame_count],
            "delta_lpc": delta_lpc[:frame_count],
        }
