import sys
import os
import soundfile as sf
import numpy as np

# ייבוא המחלקות שלך (ודאי ש-processing.py ו-session.py נמצאים באותה תיקייה)
from voice.processing import VoiceFeatureExtractor
from voice.session import VoiceSessionManager

def analyze_single_file(audio_path):
    if not os.path.exists(audio_path):
        print(f"שגיאה: הקובץ {audio_path} לא נמצא.")
        return

    print(f"מנתח את הקובץ: {audio_path}...")

    try:
        # 1. קריאת קובץ השמע מהדיסק
        audio, sample_rate = sf.read(audio_path)
        
        # 2. חילוץ הפיצ'רים הגולמיים באמצעות הקוד המתוקן של ה-Extractor
        raw_features = VoiceFeatureExtractor.extract_features(audio, sample_rate)
        
        # 3. דימוי מבנה הנתונים ש-VoiceSessionManager מצפה לקבל
        # (אנחנו עוטפים את זה בתוך רשימה של אירועים כפי שקורה בסשן האמיתי)
        mock_event_results = [{
            "mfcc": raw_features["mfcc"],
            "lpc": raw_features["lpc"],
            "parcor": raw_features["parcor"],
            "delta_lpc": raw_features["delta_lpc"],
            "pitch": raw_features["pitch"]
        }]
        
        # 4. שימוש בלוגיקת המיצוע (האגרגציה) של ה-Session Manager
        manager = VoiceSessionManager(subject_id="test_subject")
        manager._event_results = mock_event_results
        
        summary = manager._aggregate_summary()
        
        # 5. הדפסת התוצאות למסך בצורה ברורה
        print("\n=== תוצאות סופיות (האלגוריתם המתוקן) ===")
        print(f"Pitch:   {summary['Pitch']:.2f} Hz")
        print(f"MFCC:    {summary['MFCC']:.4f}")
        print(f"dLPC:    {summary['dLPC']:.4f}")
        print(f"LPC:     {summary['LPC']:.4f}")
        print(f"PARCOR:  {summary['PARCOR']:.4f}")
        print("=========================================\n")
        
    except Exception as e:
        print(f"הניתוח נכשל בשל השגיאה הבאה: {e}")

if __name__ == "__main__":
    # מאפשר להעביר את נתיב הקובץ כארגומנט בטרמינל, או להשתמש בדיפולט
    if len(sys.argv) > 1:
        file_to_analyze = sys.argv[1]
    else:
        # כאן את יכולה לשנות לנתיב של קובץ בדיקה קבוע אם את רוצה
        file_to_analyze = "sessions\\3_2026-05-16_17-19-53\\voice\\voice_phrase_1.wav" 
        
    analyze_single_file(file_to_analyze)