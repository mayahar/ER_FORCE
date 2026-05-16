import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

import numpy as np
import sounddevice as sd
import soundfile as sf
try:
    import pandas as pd
except ImportError:
    pd = None

from .events import VoiceEvent
from .recorder import VoiceRecorder, VoiceRecordingError
from .processing import VoiceFeatureExtractor, VoiceFeatureExtractionError
from .tts import speak_text


class VoiceSessionError(Exception):
    pass


class VoiceSessionManager:
    DEFAULT_RECORDING_ROOT = Path("temp_voice_recordings")
    DEFAULT_REPORTS_ROOT = Path("voice_reports")
    FEATURE_ARRAY_KEYS = ("mfcc", "pitch", "lpc", "parcor", "delta_lpc")

    # קובץ ה־WAV של הצליל "אאאאא"
    PROMPT_AUDIO_FILE = Path(__file__).parent / "Ahhhh.wav"

    def __init__(
        self,
        subject_id: Optional[str] = None,
        session_id: Optional[str] = None,
        events: Optional[List[VoiceEvent]] = None,
        recording_root: Optional[Path] = None,
        speak_prompts: bool = True,
    ):
        self.subject_id = str(subject_id) if subject_id is not None else None
        self.session_id = str(session_id or int(time.time()))
        self.recorder = VoiceRecorder()
        self.speak_prompts = bool(speak_prompts)
        self.start_timestamp: Optional[float] = None
        self.finish_timestamp: Optional[float] = None
        self.events = events if events is not None else self._default_events()

        if recording_root:
            self.recording_root = Path(recording_root)
        else:
            self.recording_root = Path(self.DEFAULT_RECORDING_ROOT) / self.session_id
        self.recording_root.mkdir(parents=True, exist_ok=True)

        # Pre-load prompt audio to ensure immediate transition after TTS
        self._prompt_audio_cache = None
        self._prompt_sr_cache = None
        self._preload_prompt_audio()

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._active_future: Optional[Future] = None
        self._active_event_id: Optional[str] = None
        self._finalized = False
        self._event_results: List[Dict[str, Any]] = []

    def _default_events(self) -> List[VoiceEvent]:
        return [
            VoiceEvent(
                event_id="voice_phrase_1",
                prompt_text="Sustained vowel 'Ah'",
                duration=10.0,
                trigger_time=5.0,
                prompt_type="phrase",
                event_type="phrase",
            )
        ]

    def _preload_prompt_audio(self) -> None:
        """Loads the prompt audio file into memory to minimize latency during playback."""
        try:
            if self.PROMPT_AUDIO_FILE.exists():
                audio, sr = sf.read(str(self.PROMPT_AUDIO_FILE), dtype="float32")
                if audio.ndim > 1:
                    audio = np.mean(audio, axis=1)
                self._prompt_audio_cache = audio
                self._prompt_sr_cache = int(sr)
        except Exception:
            pass

    @property
    def pending_events(self) -> List[VoiceEvent]:
        return [event for event in self.events if event.status == "pending"]

    @property
    def completed_events(self) -> List[VoiceEvent]:
        return [event for event in self.events if event.status == "completed"]

    @property
    def failed_events(self) -> List[VoiceEvent]:
        return [event for event in self.events if event.status == "failed"]

    @property
    def active_event(self) -> Optional[VoiceEvent]:
        return next((event for event in self.events if event.status == "recording"), None)

    @property
    def current_prompt(self) -> Optional[str]:
        active = self.active_event

        if active is not None:
            return f"Recording now: {active.prompt_text}"

        next_event = next((event for event in self.pending_events), None)

        if next_event is not None:
            return f"Upcoming prompt in the session: {next_event.prompt_text}"

        return None

    def start_session(self) -> None:
        self.start_timestamp = time.time()
        self.finish_timestamp = None
        self._finalized = False

    def update(self, elapsed_time: float) -> None:
        if self._finalized:
            return

        if self.active_event is not None:
            return

        for event in self.events:
            if event.status == "pending" and elapsed_time >= event.trigger_time:
                self._begin_event(event)
                break

    def trigger_gameplay_event(self, event_type: str) -> None:
        if self.active_event is not None:
            return

        target = next(
            (
                event
                for event in self.events
                if event.status == "pending" and event.event_type == event_type
            ),
            None,
        )

        if target is not None:
            self._begin_event(target)

    def _begin_event(self, event: VoiceEvent) -> None:
        event.status = "recording"
        event.timestamp = time.time()
        self._active_event_id = event.event_id
        self._active_future = self._executor.submit(self._record_event, event)

    def _play_prompt_audio(self) -> None:
        # Use cached audio for immediate response if available
        if self._prompt_audio_cache is not None:
            sd.play(self._prompt_audio_cache, self._prompt_sr_cache)
            sd.wait()
            return

        if not self.PROMPT_AUDIO_FILE.exists():
            raise FileNotFoundError(
                f"Prompt audio file not found: {self.PROMPT_AUDIO_FILE}"
            )

        audio, sr = sf.read(str(self.PROMPT_AUDIO_FILE), dtype="float32")

        # המרה למונו אם צריך
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        sd.play(audio, sr)
        sd.wait()

    def _record_event(self, event: VoiceEvent) -> None:
        try:
            if self.speak_prompts:
                try:
                    # TTS instruction
                    speak_text("Please imitate the following sound for 10 seconds")

                    # השמעת קובץ ה־WAV
                    self._play_prompt_audio()

                except Exception as exc:
                    event.metadata["tts_error"] = str(exc)

            # התחלת ההקלטה
            audio, sample_rate = self.recorder.record(event.duration)

            event.metadata["audio"] = {
                "samples": audio,
                "sr": sample_rate,
            }

            event.audio_path = self.recording_root / f"{event.event_id}.wav"

            self.recorder.save(audio, sample_rate, event.audio_path)

            event.status = "completed"
            if self.speak_prompts:
                # Announce the end of recording
                speak_text("Recording completed. Thank you!")

        except VoiceRecordingError as exc:
            event.error = str(exc)
            event.status = "failed"

        except Exception as exc:
            event.error = f"Unexpected recording failure: {exc}"
            event.status = "failed"

    def finalize_session(self) -> Dict[str, Any]:
        if self._finalized:
            return self._build_result(include_feature_arrays=False)

        if self._active_future is not None:
            try:
                active = self.active_event
                timeout = max(45.0, (active.duration if active else 10.0) + 35.0)
                self._active_future.result(timeout=timeout)
            except Exception:
                pass

        self.finish_timestamp = time.time()
        self._event_results = []

        for event in self.completed_events:
            try:
                audio, sample_rate = self._load_audio(event)

                features = VoiceFeatureExtractor.extract_features(
                    audio,
                    sample_rate,
                )

                self._event_results.append(
                    {
                        "event_id": event.event_id,
                        "prompt_text": event.prompt_text,
                        "prompt_type": event.prompt_type,
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "duration": event.duration,
                        "audio_path": (
                            str(event.audio_path)
                            if event.audio_path else None
                        ),
                        "error": event.error,
                        "mfcc": features["mfcc"].tolist(),
                        "pitch": features["pitch"].tolist(),
                        "lpc": features["lpc"].tolist(),
                        "parcor": features["parcor"].tolist(),
                        "delta_lpc": features["delta_lpc"].tolist(),
                    }
                )

            except (VoiceFeatureExtractionError, Exception) as exc:
                event.error = str(exc)
                event.status = "failed"

        self._finalized = True

        result = self._build_result(include_feature_arrays=True)
        self._save_results_to_file(result)
        return self._build_result(include_feature_arrays=False)

    def _load_audio(self, event: VoiceEvent):
        stored = event.metadata.get("audio")

        if stored is not None:
            return stored["samples"], stored["sr"]

        if event.audio_path is None:
            raise VoiceSessionError("No audio available for event")

        audio, sr = sf.read(str(event.audio_path), dtype="float32")

        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        return audio, int(sr)

    def _build_result(self, include_feature_arrays: bool = False) -> Dict[str, Any]:
        events = self._event_results
        if not include_feature_arrays:
            events = [self._compact_event_result(event) for event in self._event_results]

        return {
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "started_at": self.start_timestamp,
            "finished_at": self.finish_timestamp,
            "events": events,
            "summary": self._aggregate_summary(),
        }

    def _compact_event_result(self, event: Dict[str, Any]) -> Dict[str, Any]:
        compact = {}
        for key, value in event.items():
            if isinstance(value, (list, np.ndarray)):
                continue
            compact[key] = value
        return compact

    def _feature_array_dataframe(self, event: Dict[str, Any], feature_name: str):
        values = event.get(feature_name, [])
        array = np.asarray(values)

        if array.ndim == 0:
            array = array.reshape(1)

        if array.ndim == 1:
            df = pd.DataFrame({feature_name: array})
        else:
            flat = array.reshape(array.shape[0], -1)
            df = pd.DataFrame(
                flat,
                columns=[f"{feature_name}_{idx}" for idx in range(flat.shape[1])],
            )

        df.insert(0, "frame", range(len(df)))
        df.insert(0, "event_id", event.get("event_id"))
        df.insert(1, "audio_path", event.get("audio_path"))
        return df

    def _save_feature_workbook(self, result: Dict[str, Any], subject: str) -> None:
        workbook_path = self.recording_root / f"voice_features_{subject}_{self.session_id}.xlsx"
        sheets = [("summary", pd.DataFrame([result["summary"]]))]

        for feature_name in self.FEATURE_ARRAY_KEYS:
            frames = [
                self._feature_array_dataframe(event, feature_name)
                for event in result["events"]
                if feature_name in event
            ]
            if frames:
                feature_df = pd.concat(frames, ignore_index=True)
            else:
                feature_df = pd.DataFrame(columns=["event_id", "audio_path", "frame"])

            sheets.append((feature_name[:31], feature_df))

        self._write_xlsx(workbook_path, sheets)

    def _write_xlsx(self, path: Path, sheets) -> None:
        sheet_xml = []
        for _, df in sheets:
            sheet_xml.append(self._worksheet_xml(df))

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types_xml(len(sheets)))
            zf.writestr("_rels/.rels", self._root_rels_xml())
            zf.writestr("xl/workbook.xml", self._workbook_xml([name for name, _ in sheets]))
            zf.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(len(sheets)))
            zf.writestr("xl/styles.xml", self._styles_xml())
            for index, xml in enumerate(sheet_xml, start=1):
                zf.writestr(f"xl/worksheets/sheet{index}.xml", xml)

    def _content_types_xml(self, sheet_count: int) -> str:
        overrides = [
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        ]
        for index in range(1, sheet_count + 1):
            overrides.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + "".join(overrides)
            + "</Types>"
        )

    def _root_rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

    def _workbook_xml(self, sheet_names) -> str:
        sheets_xml = []
        for index, name in enumerate(sheet_names, start=1):
            safe_name = escape(str(name).replace(":", "_").replace("/", "_").replace("\\", "_")[:31])
            sheets_xml.append(
                f'<sheet name="{safe_name}" sheetId="{index}" r:id="rId{index}"/>'
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(sheets_xml)
            + "</sheets></workbook>"
        )

    def _workbook_rels_xml(self, sheet_count: int) -> str:
        rels = []
        for index in range(1, sheet_count + 1):
            rels.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
        rels.append(
            f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels)
            + "</Relationships>"
        )

    def _styles_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            "</styleSheet>"
        )

    def _worksheet_xml(self, df) -> str:
        rows_xml = []
        rows = [list(df.columns)] + df.astype(object).where(pd.notnull(df), None).values.tolist()

        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                cells.append(self._cell_xml(row_index, col_index, value))
            rows_xml.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            + "".join(rows_xml)
            + "</sheetData></worksheet>"
        )

    def _cell_xml(self, row_index: int, col_index: int, value) -> str:
        cell_ref = f"{self._column_name(col_index)}{row_index}"

        if value is None:
            return f'<c r="{cell_ref}"/>'

        if isinstance(value, (np.integer, int)):
            return f'<c r="{cell_ref}"><v>{int(value)}</v></c>'

        if isinstance(value, (np.floating, float)):
            value = float(value)
            if not np.isfinite(value):
                return f'<c r="{cell_ref}"/>'
            return f'<c r="{cell_ref}"><v>{value}</v></c>'

        text = escape(str(value))
        return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    def _column_name(self, col_index: int) -> str:
        name = ""
        while col_index:
            col_index, remainder = divmod(col_index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def _save_results_to_file(self, result: Dict[str, Any]) -> None:
        """
        Saves the session metrics as CSV files in the voice folder.
        """
        if pd is None:
            # Pandas is required for multi-sheet export
            return

        try:
            # שימוש ב-Session ID המקורי לשם הקובץ בתוך תיקיית הקול
            subject = self.subject_id if self.subject_id else "unknown"

            summary_df = pd.DataFrame([result["summary"]])
            
            report_events = []
            for event in result["events"]:
                report_events.append(self._compact_event_result(event))
            
            # Save summary and event details to separate CSV files
            self._save_feature_workbook(result, subject)
            
            print(f"Voice reports saved to: {self.recording_root}")

        except Exception as e:
            print(f"Error saving voice report to {self.recording_root}: {e}")
            import traceback
            traceback.print_exc()

    def _aggregate_summary(self) -> Dict[str, Any]:
        if not self._event_results:
            return {
                "dLPC": 0.0,
                "PARCOR": 0.0,
                "LPC": 0.0,
                "Pitch": 0.0,
                "MFCC": 0.0,
            }

        dLPC_list = []
        parcor_list = []
        lpc_formants_list = []
        pitch_list = []
        mfcc_list = []

        sampling_rate = 16000  # קצב הדגימה המוגדר ב-VoiceFeatureExtractor

        for event in self._event_results:
            try:
                # 1. MFCC: חישוב עוצמת הרעש/אנרגיה (RMS) של המקדם הראשון לקבלת ערך חיובי מייצג
                mfcc_array = np.asarray(event["mfcc"], dtype=np.float32)
                if mfcc_array.ndim == 2 and mfcc_array.shape[1] > 1:
                    coef_1 = mfcc_array[:, 1]
                    rms_mfcc = np.sqrt(np.nanmean(coef_1 ** 2))
                    mfcc_list.append(rms_mfcc)

                # 2. LPC: המרה של המקמדים לתדרי פורמנטים (Hz) במקום מיצוע אלגברי של פילטרים
                lpc_array = np.asarray(event["lpc"], dtype=np.float32)
                if lpc_array.size > 0 and lpc_array.ndim == 2:
                    frame_formants = []
                    for frame_lpc in lpc_array:
                        # מציאת שורשי הפולינום לקבלת תדרי התהודה
                        roots = np.roots(frame_lpc)
                        # לוקחים רק את השורשים בחצי המישור העליון (תדרים חיוביים)
                        roots = [r for r in roots if np.imag(r) >= 0]
                        # חישוב התדרים ב-Hz
                        angles = np.angle(roots)
                        freqs = sorted(angles * (sampling_rate / (2 * np.pi)))
                        
                        # פילטרציה של תדרי 0 (DC) ותדרים גבוהים מדי
                        valid_freqs = [f for f in freqs if 250 < f < 4000]
                        if valid_freqs:
                            # לוקחים את הפורמנט הראשי הדומיננטי (F1 או F2)
                            frame_formants.append(valid_freqs[0])
                    
                    if frame_formants:
                        lpc_formants_list.append(np.nanmean(frame_formants))

                # 3. PARCOR: מיצוע אנרגטי (RMS) של מקדמי ההחזר הראשונים (0 עד 3)
                parcor_array = np.asarray(event["parcor"], dtype=np.float32)
                if parcor_array.size > 0 and parcor_array.ndim == 2:
                    # מקדמי PARCOR משמעותיים נמצאים בטווח של [-1, 1], נמדוד את עצמתם (RMS)
                    rms_parcor = np.sqrt(np.nanmean(parcor_array[:, 0:3] ** 2))
                    parcor_list.append(rms_parcor)

                # 4. dLPC: מדד יציבות - ממוצע השינויים הריבועיים (פלקטואציה של הסיגנל)
                dlpc_arr = np.asarray(event["delta_lpc"], dtype=np.float32)
                if dlpc_arr.size > 0:
                    dLPC_list.append(np.sqrt(np.nanmean(dlpc_arr ** 2)))

                # 5. Pitch: ממוצע תדר יסודי לקטעי קול בלבד (נשאר מצוין כמו שהיה)
                pitch_array = np.asarray(event["pitch"], dtype=np.float32)
                voiced = pitch_array[~np.isnan(pitch_array)]
                if voiced.size > 0:
                    pitch_list.append(np.nanmean(voiced))

            except Exception:
                continue

        def _safe_mean(vals):
            if not vals: 
                return 0.0
            m = np.nanmean(vals)
            return float(m) if np.isfinite(m) else 0.0

        return {
            "dLPC": _safe_mean(dLPC_list),
            "PARCOR": _safe_mean(parcor_list),
            "LPC": _safe_mean(lpc_formants_list),  # יציג כעת את תדר התהודה הדומיננטי ב-Hz
            "Pitch": _safe_mean(pitch_list),       # יציג את ה-Pitch הקיים והטוב
            "MFCC": _safe_mean(mfcc_list),         # יציג ערך חיובי ומנורמל של הנטייה הספקטרלית
        }
