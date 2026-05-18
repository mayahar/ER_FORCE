"""
Tobii Pro Eye Tracker Recording and Real-Time Gaze Data Collection
Automatically starts recording, collects gaze data, and returns extracted data to the application.
"""
import importlib
import os
import sys

from eye_tracking_analysis.stdout_safe import install_safe_stdio

install_safe_stdio()

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SDK_DIR = os.path.join(ROOT_DIR, "TobiiPro_SDK")


def _load_tobii_research():
    try:
        return importlib.import_module("tobii_research")
    except Exception:
        for path in (ROOT_DIR, SDK_DIR):
            if path not in sys.path:
                sys.path.insert(0, path)
        try:
            return importlib.import_module("tobii_research")
        except Exception as exc:
            print(
                f"Warning: Could not import Tobii SDK module 'tobii_research' ({exc.__class__.__name__}: {exc})"
            )
            return None


tr = _load_tobii_research()
import time
from dataclasses import dataclass
from typing import List, Optional, Callable
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
        
        # Extract gaze points (normalized 0-1 on display area)
        left_point = gaze_data["left_gaze_point_on_display_area"]
        right_point = gaze_data["right_gaze_point_on_display_area"]
        timestamp = gaze_data["system_time_stamp"]
        
        # Extract pupil diameters
        left_pupil = gaze_data["left_pupil_diameter"]
        right_pupil = gaze_data["right_pupil_diameter"]
        
        # Determine validity
        left_validity = gaze_data["left_gaze_point_validity"]
        right_validity = gaze_data["right_gaze_point_validity"]
        validity = "both_valid" if (left_validity == 1 and right_validity == 1) else \
                   "left_valid" if left_validity == 1 else \
                   "right_valid" if right_validity == 1 else "invalid"
        
        sample = GazeData(
            timestamp=timestamp,
            left_x=left_point[0] if left_validity else None,
            left_y=left_point[1] if left_validity else None,
            right_x=right_point[0] if right_validity else None,
            right_y=right_point[1] if right_validity else None,
            left_pupil_diameter=left_pupil,
            right_pupil_diameter=right_pupil,
            validity=validity
        )
        
        with self.data_lock:
            self.gaze_data_buffer.append(sample)
    
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
                    "validity": sample.validity
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
                        'Left_Pupil_Diameter', 'Right_Pupil_Diameter', 'Validity'
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
                            sample.validity
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