"""
Tobii Pro Eye Tracker Recording and Real-Time Gaze Data Collection
Automatically starts recording, collects gaze data, and returns extracted data to the application.
"""
import importlib
import sys

from eye_tracking_analysis.stdout_safe import install_safe_stdio

install_safe_stdio()


def _load_tobii_research():
    try:
        return importlib.import_module("tobii_research")
    except Exception as first_exc:
        print(
            "Warning: Could not import installed Tobii Research module "
            f"'tobii_research' ({first_exc.__class__.__name__}: {first_exc}). "
            "Run eye_tracking_setup\\setup_colleague.cmd to install Python 3.10 dependencies."
        )
        return None


tr = _load_tobii_research()
import time
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional
from datetime import datetime
from threading import Lock
import json


def _safe_print(*args, sep=" ", end="\n", flush=False):
    message = sep.join(str(arg) for arg in args) + end
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    if hasattr(stream, "buffer"):
        stream.buffer.write(message.encode(encoding, errors="replace"))
    else:
        stream.write(message.encode(encoding, errors="replace").decode(encoding, errors="replace"))
    if flush:
        stream.flush()


def _get_gaze_value(gaze_data: Any, key: str, default=None):
    if isinstance(gaze_data, Mapping):
        return gaze_data.get(key, default)
    return getattr(gaze_data, key, default)


def _validity_is_valid(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1

    text = str(value).strip().lower()
    if text in {"0", "false", "invalid", "validity.invalid"} or text.endswith(".invalid"):
        return False
    if text in {"1", "true", "valid", "validity.valid"} or text.endswith(".valid"):
        return True

    name = getattr(value, "name", None)
    if name:
        name_text = str(name).strip().lower()
        if name_text.endswith("invalid"):
            return False
        if name_text.endswith("valid"):
            return True
    return None


def _point_coord(point, index: int):
    if point is None:
        return None
    try:
        value = point[index]
    except (IndexError, KeyError, TypeError):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _coord_if_present(point, index: int, validity: Optional[bool]):
    value = _point_coord(point, index)
    if value is None:
        return None
    if validity is False:
        return None
    return value


@dataclass
class GazeData:
    """Represents a single gaze sample"""
    timestamp: float
    left_x: float
    left_y: float
    right_x: float
    right_y: float
    left_pupil_diameter: Optional[float] = None
    right_pupil_diameter: Optional[float] = None
    validity: Optional[str] = None
    left_gaze_point_validity: Optional[bool] = None
    right_gaze_point_validity: Optional[bool] = None


class EyeTrackerRecorder:
    """Handles eye tracker recording and gaze data collection"""
    
    def __init__(self, eyetracker=None, recording_duration: float = 30.0):
        """
        Initialize the eye tracker recorder.
        
        Args:
            eyetracker: Tobii eye tracker object (if None, will find and select one)
            recording_duration: Duration of recording in seconds
        """
        self.eyetracker = eyetracker
        self.recording_duration = recording_duration
        self.gaze_data_buffer: List[GazeData] = []
        self.is_recording = False
        self.data_lock = Lock()
        self.start_time = None
        self.end_time = None
        
    def find_and_select_eyetracker(self, auto_select_first: bool = True) -> bool:
        """Find and select an eye tracker"""
        _safe_print("Looking for eye trackers...")
        if tr is None:
            _safe_print("Tobii SDK is not available. Eye tracking is disabled.")
            return False

        found_eyetrackers = tr.find_all_eyetrackers()
        
        if not found_eyetrackers:
            _safe_print("No eye trackers found.")
            return False
        
        self._print_eyetrackers(found_eyetrackers)

        if auto_select_first:
            self.eyetracker = found_eyetrackers[0]
        else:
            self.eyetracker = self._select_eyetracker(found_eyetrackers)
        
        if self.eyetracker:
            _safe_print(f"\nSelected: {self.eyetracker.model} ({self.eyetracker.serial_number})")
            _safe_print(f"  Address: {self.eyetracker.address}")
            return True
        return False
    
    def _print_eyetrackers(self, eyetrackers):
        """Print available eye trackers"""
        _safe_print("\nAvailable Eye Trackers:")
        for i, eyetracker in enumerate(eyetrackers):
            _safe_print(f"  [{i}] {eyetracker.model} - Serial: {eyetracker.serial_number}")
    
    def _select_eyetracker(self, eyetrackers):
        """Let user select an eye tracker"""
        while True:
            try:
                index = int(input("\nSelect eye tracker by index: "))
                if 0 <= index < len(eyetrackers):
                    return eyetrackers[index]
                _safe_print("Invalid index. Please try again.")
            except ValueError:
                _safe_print("Please enter a valid integer.")
    
    def _gaze_data_callback(self, gaze_data):
        """Callback function for incoming gaze data"""
        if not self.is_recording:
            return

        try:
            # Extract gaze points (normalized 0-1 on display area).
            left_point = _get_gaze_value(gaze_data, "left_gaze_point_on_display_area")
            right_point = _get_gaze_value(gaze_data, "right_gaze_point_on_display_area")
            timestamp = _get_gaze_value(gaze_data, "system_time_stamp")
            if timestamp is None:
                timestamp = _get_gaze_value(gaze_data, "device_time_stamp")
            if timestamp is None:
                timestamp = time.time()

            left_pupil = _get_gaze_value(gaze_data, "left_pupil_diameter")
            right_pupil = _get_gaze_value(gaze_data, "right_pupil_diameter")

            left_validity = _validity_is_valid(
                _get_gaze_value(gaze_data, "left_gaze_point_validity")
            )
            right_validity = _validity_is_valid(
                _get_gaze_value(gaze_data, "right_gaze_point_validity")
            )
            if left_validity is True and right_validity is True:
                validity = "both_valid"
            elif left_validity is True:
                validity = "left_valid"
            elif right_validity is True:
                validity = "right_valid"
            elif left_validity is None and right_validity is None:
                validity = "unknown"
            else:
                validity = "invalid"

            sample = GazeData(
                timestamp=float(timestamp),
                left_x=_coord_if_present(left_point, 0, left_validity),
                left_y=_coord_if_present(left_point, 1, left_validity),
                right_x=_coord_if_present(right_point, 0, right_validity),
                right_y=_coord_if_present(right_point, 1, right_validity),
                left_pupil_diameter=left_pupil,
                right_pupil_diameter=right_pupil,
                validity=validity,
                left_gaze_point_validity=left_validity,
                right_gaze_point_validity=right_validity,
            )

            with self.data_lock:
                self.gaze_data_buffer.append(sample)
        except Exception as exc:
            _safe_print(f"Warning: Failed to parse gaze sample: {exc}")
    
    def start_recording(self) -> bool:
        """Start eye tracking recording"""
        if not self.eyetracker:
            _safe_print("No eye tracker selected.")
            return False
        
        try:
            _safe_print("\nStarting recording...")
            self.is_recording = True
            self.gaze_data_buffer = []
            self.start_time = datetime.now()
            
            # Subscribe to gaze data
            self.eyetracker.subscribe_to(
                tr.EYETRACKER_GAZE_DATA,
                self._gaze_data_callback,
                as_dictionary=True
            )
            
            _safe_print(f"Recording started. Duration: {self.recording_duration}s")
            return True
        except Exception as e:
            _safe_print(f"Error starting recording: {e}")
            self.is_recording = False
            return False
    
    def stop_recording(self) -> bool:
        """Stop eye tracking recording"""
        if not self.is_recording:
            return False
        
        try:
            _safe_print("\nStopping recording...")
            self.is_recording = False
            self.end_time = datetime.now()
            
            # Unsubscribe from gaze data
            self.eyetracker.unsubscribe_from(
                tr.EYETRACKER_GAZE_DATA,
                self._gaze_data_callback
            )
            
            _safe_print(f"Recording stopped. Samples collected: {len(self.gaze_data_buffer)}")
            return True
        except Exception as e:
            _safe_print(f"Error stopping recording: {e}")
            return False
    
    def record_for_duration(self) -> List[GazeData]:
        """
        Automatically start recording for specified duration and return data.
        
        Returns:
            List of GazeData samples collected during recording
        """
        if not self.start_recording():
            return []
        
        try:
            elapsed = 0
            while elapsed < self.recording_duration:
                time.sleep(0.1)
                elapsed += 0.1
                remaining = self.recording_duration - elapsed
                if int(remaining) % 5 == 0 and remaining < self.recording_duration:
                    _safe_print(f"  Recording... {remaining:.1f}s remaining", end='\r')
        except KeyboardInterrupt:
            _safe_print("\nRecording interrupted by user.")
        finally:
            self.stop_recording()
        
        with self.data_lock:
            return self.gaze_data_buffer.copy()
    
    def get_collected_data(self) -> List[GazeData]:
        """Get the collected gaze data"""
        with self.data_lock:
            return self.gaze_data_buffer.copy()
    
    def export_to_json(self, filename: str) -> bool:
        """Export collected data to JSON file"""
        try:
            with self.data_lock:
                data = [{
                    "timestamp": sample.timestamp,
                    "left_x": sample.left_x,
                    "left_y": sample.left_y,
                    "right_x": sample.right_x,
                    "right_y": sample.right_y,
                    "left_pupil_diameter": sample.left_pupil_diameter,
                    "right_pupil_diameter": sample.right_pupil_diameter,
                    "validity": sample.validity,
                    "left_gaze_point_validity": sample.left_gaze_point_validity,
                    "right_gaze_point_validity": sample.right_gaze_point_validity,
                } for sample in self.gaze_data_buffer]
            
            with open(filename, 'w') as f:
                json.dump({
                    "metadata": {
                        "start_time": self.start_time.isoformat() if self.start_time else None,
                        "end_time": self.end_time.isoformat() if self.end_time else None,
                        "total_samples": len(data),
                        "eyetracker_model": self.eyetracker.model if self.eyetracker else None,
                        "eyetracker_serial": self.eyetracker.serial_number if self.eyetracker else None,
                    },
                    "gaze_data": data
                }, f, indent=2)
            
            _safe_print(f"Data exported to {filename}")
            return True
        except Exception as e:
            _safe_print(f"Error exporting data: {e}")
            return False
    
    def export_to_csv(self, filename: str) -> bool:
        """Export collected data to CSV file"""
        try:
            import csv
            
            with self.data_lock:
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'Timestamp', 'Left_X', 'Left_Y', 'Right_X', 'Right_Y',
                        'Left_Pupil_Diameter', 'Right_Pupil_Diameter', 'Validity',
                        'Left_Gaze_Point_Validity', 'Right_Gaze_Point_Validity'
                    ])
                    
                    for sample in self.gaze_data_buffer:
                        writer.writerow([
                            sample.timestamp,
                            sample.left_x,
                            sample.left_y,
                            sample.right_x,
                            sample.right_y,
                            sample.left_pupil_diameter,
                            sample.right_pupil_diameter,
                            sample.validity,
                            sample.left_gaze_point_validity,
                            sample.right_gaze_point_validity,
                        ])
            
            _safe_print(f"Data exported to {filename}")
            return True
        except Exception as e:
            _safe_print(f"Error exporting data: {e}")
            return False


def main():
    """Example usage"""
    # Create recorder instance
    recorder = EyeTrackerRecorder(recording_duration=10.0)
    
    # Find and select eye tracker
    if not recorder.find_and_select_eyetracker():
        return
    
    # Record for duration and get data
    gaze_data = recorder.record_for_duration()
    
    # Export data
    if gaze_data:
        recorder.export_to_csv("gaze_data.csv")
        recorder.export_to_json("gaze_data.json")
        
        _safe_print(f"\nSuccessfully collected {len(gaze_data)} gaze samples")
        _safe_print(f"  First sample: L({gaze_data[0].left_x:.3f}, {gaze_data[0].left_y:.3f})")
    else:
        _safe_print("No gaze data collected.")


if __name__ == "__main__":
    main()
