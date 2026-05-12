"""
Integration of eye tracking recording and analysis for your game.
Example showing how to use both modules together.
"""

from eye_tracker_recorder import EyeTrackerRecorder, GazeData
from eye_movement_analyzer import EyeMovementAnalyzer
import numpy as np
from typing import Dict


class GameEyeTracker:
    """Main interface for game integration"""
    
    def __init__(self, recording_duration: float = 30.0):
        self.recorder = EyeTrackerRecorder(recording_duration=recording_duration)
        self.analyzer = EyeMovementAnalyzer()
        self.metrics = None
        self.fixations = None
        self.saccades = None
    
    def initialize(self) -> bool:
        """Initialize and connect to eye tracker"""
        return self.recorder.find_and_select_eyetracker()
    
    def run_recording_and_analysis(self) -> Dict:
        """
        Run complete recording -> analysis pipeline.
        Returns metrics dict ready for game consumption.
        """
        # Record
        print("\n🎮 Starting game eye-tracking session...")
        gaze_data = self.recorder.record_for_duration()
        
        if not gaze_data:
            print("No gaze data collected!")
            return None
        
        # Prepare data for analysis
        timestamps = np.array([s.timestamp for s in gaze_data]) / 1_000_000  # microseconds to seconds
        timestamps = timestamps - timestamps[0]  # Normalize to start at 0
        
        gaze_x = np.array([s.left_x if s.left_x is not None else np.nan 
                          for s in gaze_data])
        gaze_y = np.array([s.left_y if s.left_y is not None else np.nan 
                          for s in gaze_data])
        
        # Analyze
        self.fixations, self.saccades, self.metrics = self.analyzer.analyze_gaze_data(
            gaze_x, gaze_y, timestamps
        )
        
        # Return game-ready metrics
        return self.get_game_metrics()
    
    def get_game_metrics(self) -> Dict:
        """Get metrics in a format useful for game"""
        if not self.metrics:
            return None
        
        return {
            "fixations_per_minute": round(self.metrics.fixations_per_minute, 2),
            "saccades_per_minute": round(self.metrics.saccades_per_minute, 2),
            "fixation_duration_per_minute": round(self.metrics.fixation_duration_per_minute, 2),
            "mean_fixation_duration_ms": round(self.metrics.mean_fixation_duration * 1000, 2),
            "mean_saccade_amplitude": round(self.metrics.mean_saccade_amplitude, 2),
            "total_fixations": self.metrics.num_fixations,
            "total_saccades": self.metrics.num_saccades,
            "total_duration": round(self.metrics.total_duration, 2)
        }
    
    def display_results(self):
        """Display results to console"""
        if self.metrics:
            self.analyzer.print_metrics(self.metrics)
        
        # Also export for record-keeping
        self.recorder.export_to_csv("gaze_data.csv")
        self.recorder.export_to_json("gaze_data.json")


def example_game_usage():
    """Example: How to use in your game"""
    # Initialize
    tracker = GameEyeTracker(recording_duration=15.0)  # 15 second task
    
    if not tracker.initialize():
        print("Failed to initialize eye tracker")
        return
    
    # Run task (e.g., puzzle, search task, etc.)
    print("\n🎮 Running game task...")
    metrics = tracker.run_recording_and_analysis()
    
    # Display results
    tracker.display_results()
    
    # Use metrics for game logic
    if metrics:
        print("\n📊 RESULTS FOR GAME:")
        print(f"  Fixations: {metrics['fixations_per_minute']} per minute")
        print(f"  Saccades: {metrics['saccades_per_minute']} per minute")
        print(f"  Fixation Time: {metrics['fixation_duration_per_minute']} seconds per minute")
        
        # Example: Adjust game difficulty based on metrics
        if metrics['fixations_per_minute'] > 30:
            print("  → High focus detected: Increasing difficulty!")
        elif metrics['fixations_per_minute'] < 10:
            print("  → Low focus detected: Decreasing difficulty!")


if __name__ == "__main__":
    example_game_usage()