import numpy as np
from scipy.fftpack import dct
from scipy.signal import lfilter, resample_poly, medfilt


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

    ================================================================================
    1. פירוט קודי השגיאה ומתי הם מתרחשים (לפי סדר קדימויות פיזי בקוד):
    ================================================================================
    * MUTE:
      - מתי: עוצמת הסיגנל הכוללת (Global RMS) נמוכה מ-0.0001 או האמפליטודה המקסימלית נמוכה מ-0.001.
      - משמעות: המיקרופון מושתק, כבוי, או שלא הופק שום צליל משמעותי (אפילו לא נשימה או רעש רקע).
      - עדיפות: ראשון. אם אין סיגנל, הריצה נעצרת מיד.

    * HARDWARE_SHORT:
      - מתי: אורך מערך האודיו קטן פיזית מאורך של פריים בודד (25 מילישניות, פחות מ-400 דגימות ב-16kHz).
      - משמעות: כשל טכני/מכני חמור (קריסת דרייבר המיקרופון, נעילת הסיגנל ע"י אפליקציה אחרת, או הקלטה שנסגרה מיד).
      - עדיפות: שני. מפריד כשל חומרתי מכשל התנהגותי של המשתמש.

    * SPEECH:
      - מתי: מזוהה תנודתיות ספקטרלית דינמית (Spectral Flux גבוה) המאפיינת דיבור מילולי/הברתי ולא צליל מונוטוני,
             ובמקביל לא הצטברו 5 שניות של "אה" נקי ותקין.
      - משמעות: הנבדק דיבר, אמר מילים או משפטים במקום להפיק צליל יציב ורציף.
      - עדיפות: שלישי (נבדק רק אם לא הגענו לרף ה-5 שניות של צליל תקין).

    * SHORT:
      - מתי: סך כל קטעי ה"אה" הנקיים והתקינים שנמצאו קטן מ-5 שניות (אך גדול מ-0.5 שניות).
      - משמעות: כשל התנהגותי. הנבדק הפסיק את הפקת הצליל מוקדם מדי. המערכת דורשת הקלטה חוזרת ארוכה יותר.
      - עדיפות: רביעי. קורה רק אם המשתמש לא דיבר (לא נזרק SPEECH) אך פשוט קיצר בזמן.

    * SILENT:
      - מתי: אורך ה"אה" התקין קטן מ-0.5 שניות, או שלא נמצאו פריימים תקינים בכלל (אך האודיו לא מוגדר כ-MUTE).
      - משמעות: הנבדק לחש, נשף קלות, או שהיה רעש רקע חלש ומיתר הקול לא רטט בפועל.
      - עדיפות: חמישי (סוף שלב קדם-העיבוד).

    * UNSTABLE_PITCH:
      - מתי: מקדם המשתנות של תדר היסודי (Pitch CV = Pitch Std / Pitch Mean) גבוה מ-0.55 (55%).
      - משמעות: הקול של הנבדק רעד בצורה קיצונית, או שהשתנתה האינטונציה בצורה חדה (שירה/זמזום מנגינה).
      - עדיפות: שישי (שלב בקרת האיכות הסופית, לאחר מעבר קדם-העיבוד).

    ================================================================================
    2. הסבר מתמטי ואקוסטי על המדדים המרכזיים:
    ================================================================================
    * Spectral Flux (שטף ספקטרלי):
      - מודד את קצב השינוי של הגרף הספקטרלי (תדרים) בין פריים לפריים ע"י חישוב המרחק האוקלידי בין וקטורי ה-FFT.
      - צליל "אההה" יציב מניב Spectral Flux נמוך מאוד וקבוע. דיבור מילולי (עיצורים ותנועות משתנות) מקפיץ את ה-Flux.
      - אנחנו מחשבים את סטיית התקן של השטף (Flux STD); אם היא עוברת את `0.045`, זהו סימן מובהק לדיבור (SPEECH).

    * Pitch CV (Coefficient of Variation):
      - מחושב כסטיית התקן של הפיץ' חלקי ממוצע הפיץ' (בקטעים שזוהה בהם קול).
      - מדד זה מייצג את "רוטציה והרעד" של מיתרי הקול. רף של `0.55` מאפשר גמישות רבה (עבור חולים או קולות עייפים), 
        אך חוסם תנודות קיצוניות שאינן מאפשרות הפקת מדדים אמינים.

    ================================================================================
    3. לוגיקת סדר העדיפויות ומניעת דריסות (Anti-Overriding Logic):
    ================================================================================
    כדי למנוע מצב שבו מילה קטנה בתחילת ההקלטה תפסול 7 שניות של "אה" מדהים ויציב, הלוגיקה עובדת כך:
    א. המערכת קודם כל אוספת ומסכמת את משך הזמן של הסגמנטים התקינים (`total_valid_duration`).
    ב. תנאי עליון: אם הצטברו לפחות 5 שניות של "אה" נקי - ההקלטה מתקבלת מיד! נתוני הדיבור/רעש האחרים נזרקים והקוד ממשיך לחילוץ.
    ג. רק אם אין 5 שניות של דאטה תקין, המערכת נכנסת לשרשרת אבחון מדורגת (SPEECH -> SHORT -> SILENT) כדי לקבוע את סיבת הכשל המדויקת ביותר עבור ה-UI.
    """

    SAMPLE_RATE = 16000
    PREEMPHASIS = 0.97
    FRAME_LENGTH_MS = 25
    HOP_LENGTH_MS = 10
    LPC_ORDER = 12 
    
    FMIN = 40.0
    FMAX = 500.0
    
    MIN_ENERGY_THRESHOLD = 0.0004      
    MIN_TOTAL_SPEECH_DURATION_S = 5.0  
    MAX_FLUX_STD = 0.045000            
    MAX_PITCH_REL_VARIATION = 0.550000 

    @classmethod
    def preprocess_audio(cls, audio: np.ndarray, sample_rate: int):
        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1)

        audio = np.asarray(audio, dtype=np.float32)

        # 1. בדיקת השתקה / חוסר מיקרופון גלובלי
        global_rms = float(np.sqrt(np.mean(audio**2)))
        max_amplitude = float(np.max(np.abs(audio)))
        if global_rms < 0.0001 or max_amplitude < 0.001:
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
        
        # 2. הפרדה לשגיאה טכנית: הקובץ קצר מכדי להכיל אפילו פריים בודד (בעיית חומרה/דרייבר)
        if len(audio) < frame_length:
            return None, "HARDWARE_SHORT"

        frame_count = 1 + max(0, (len(audio) - frame_length) // hop_length)
        shape = (frame_count, frame_length)
        strides = (audio.strides[0] * hop_length, audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(audio, shape=shape, strides=strides)

        frame_rms = np.sqrt(np.mean(frames**2, axis=1))
        speech_frames = (frame_rms > cls.MIN_ENERGY_THRESHOLD).astype(np.int32)
        smoothed_speech = medfilt(speech_frames, kernel_size=5)

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
            
            if seg_duration < 0.3:
                continue

            any_speech_detected_at_all = True
            seg_frames = frames[s:e]
            seg_rms = frame_rms[s:e]
            
            core_seg_frames = seg_frames[seg_rms > (cls.MIN_ENERGY_THRESHOLD * 2.5)]
            if len(core_seg_frames) > 5:
                fft_data = np.abs(np.fft.rfft(core_seg_frames, n=512, axis=1))
                fft_norm = fft_data / (np.sum(fft_data, axis=1, keepdims=True) + 1e-3)
                flux_per_frame = np.sqrt(np.sum(np.diff(fft_norm, axis=0)**2, axis=1))
                flux_std = float(np.std(flux_per_frame))
                
                if flux_std > cls.MAX_FLUX_STD:
                    speech_rejected_due_to_flux = True
                    continue

            start_sample = s * hop_length
            end_sample = min(len(audio), e * hop_length + (frame_length - hop_length))
            valid_audio_segments.append(audio[start_sample:end_sample])
            total_valid_duration += seg_duration

        # 3. בדיקת רף ה-5 שניות של צליל "אה" תקין ונקי
        if total_valid_duration >= cls.MIN_TOTAL_SPEECH_DURATION_S and len(valid_audio_segments) > 0:
            pass 
        
        # 4. אם אין מספיק דאטה תקין, נפעיל אבחון סיבות לפי סדר עדיפויות מוגדר:
        else:
            # א. האם נפסל קול בגלל דיבור/מילים דינמיות?
            if speech_rejected_due_to_flux or (any_speech_detected_at_all and len(valid_audio_segments) == 0):
                return None, "SPEECH"
            
            # ב. שגיאה התנהגותית: הפיק צליל "אה" תקין, אך הפסיק מוקדם מדי (פחות מ-5 שניות)
            if total_valid_duration > 0.5:
                return None, "SHORT"
            
            # ג. לא נקלט קול משמעותי בכלל (לחישה, נשימה או שקט)
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
            smoothed_valid = medfilt(pitches[valid_indices], kernel_size=5)
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
    def extract_features(cls, raw_audio: np.ndarray, sample_rate: int):
        preprocessed_res = cls.preprocess_audio(raw_audio, sample_rate)
        
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
        lpc = cls.extract_lpc(working_audio, working_sr)
        parcor = cls.extract_parcor(working_audio, working_sr)
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