"""
Tobii Pro Eye Tracker Recording and Real-Time Gaze Data Collection
Automatically starts recording, collects gaze data, and returns extracted data to the application.
"""
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SDK_DIR = os.path.join(ROOT_DIR, "TobiiPro_SDK")
for path in (ROOT_DIR, SDK_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import tobii_research as tr
import time
from dataclasses import dataclass
from typing import List, Optional, Callable
from datetime import datetime
from threading import Lock
import json


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
        print("Looking for eye trackers...")
        found_eyetrackers = tr.find_all_eyetrackers()
        
        if not found_eyetrackers:
            print("No eye trackers found.")
            return False
        
        self._print_eyetrackers(found_eyetrackers)

        if auto_select_first:
            self.eyetracker = found_eyetrackers[0]
        else:
            self.eyetracker = self._select_eyetracker(found_eyetrackers)
        
        if self.eyetracker:
            print(f"\n✓ Selected: {self.eyetracker.model} ({self.eyetracker.serial_number})")
            print(f"  Address: {self.eyetracker.address}")
            return True
        return False
    
    def _print_eyetrackers(self, eyetrackers):
        """Print available eye trackers"""
        print("\nAvailable Eye Trackers:")
        for i, eyetracker in enumerate(eyetrackers):
            print(f"  [{i}] {eyetracker.model} - Serial: {eyetracker.serial_number}")
    
    def _select_eyetracker(self, eyetrackers):
        """Let user select an eye tracker"""
        while True:
            try:
                index = int(input("\nSelect eye tracker by index: "))
                if 0 <= index < len(eyetrackers):
                    return eyetrackers[index]
                print("Invalid index. Please try again.")
            except ValueError:
                print("Please enter a valid integer.")
    
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
            print("No eye tracker selected.")
            return False
        
        try:
            print("\n→ Starting recording...")
            self.is_recording = True
            self.gaze_data_buffer = []
            self.start_time = datetime.now()
            
            # Subscribe to gaze data
            self.eyetracker.subscribe_to(
                tr.EYETRACKER_GAZE_DATA,
                self._gaze_data_callback,
                as_dictionary=True
            )
            
            print(f"✓ Recording started. Duration: {self.recording_duration}s")
            return True
        except Exception as e:
            print(f"Error starting recording: {e}")
            self.is_recording = False
            return False
    
    def stop_recording(self) -> bool:
        """Stop eye tracking recording"""
        if not self.is_recording:
            return False
        
        try:
            print("\n→ Stopping recording...")
            self.is_recording = False
            self.end_time = datetime.now()
            
            # Unsubscribe from gaze data
            self.eyetracker.unsubscribe_from(
                tr.EYETRACKER_GAZE_DATA,
                self._gaze_data_callback
            )
            
            print(f"✓ Recording stopped. Samples collected: {len(self.gaze_data_buffer)}")
            return True
        except Exception as e:
            print(f"Error stopping recording: {e}")
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
                    print(f"  Recording... {remaining:.1f}s remaining", end='\r')
        except KeyboardInterrupt:
            print("\n✗ Recording interrupted by user.")
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
            
            print(f"✓ Data exported to {filename}")
            return True
        except Exception as e:
            print(f"Error exporting data: {e}")
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
            
            print(f"✓ Data exported to {filename}")
            return True
        except Exception as e:
            print(f"Error exporting data: {e}")
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
        
        print(f"\n✓ Successfully collected {len(gaze_data)} gaze samples")
        print(f"  First sample: L({gaze_data[0].left_x:.3f}, {gaze_data[0].left_y:.3f})")
    else:
        print("No gaze data collected.")


if __name__ == "__main__":
    main()