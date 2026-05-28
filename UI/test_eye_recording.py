import os
import sys
import time
from pathlib import Path

# תיקון נתיבים: מוסיף את תיקיית השורש של הפרויקט (Main) ל-sys.path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# עכשיו ה-import יעבור בהצלחה ולא יזרוק ModuleNotFoundError
from ui.eye_tracking_runtime import EyeTrackingRuntime
from ui.eye_tracking_runtime import _candidate_hosts


def print_host_diagnostics(runtime: EyeTrackingRuntime):
    print("\n[debug] בדיקת hosts זמינים:")
    for host in _candidate_hosts(runtime.active_host):
        try:
            import requests

            res = requests.get(f"http://{host}/rest/system.recording-unit-serial", timeout=2.0)
            print(f"    {host}: HTTP {res.status_code}, body={res.text[:80]!r}")
        except Exception as exc:
            print(f"    {host}: נכשל ({exc})")

def run_test():
    print("=" * 60)
    print("תחילת בדיקת תקשורת והקלטה מול משקפי Tobii Pro Glasses 3 (Ethernet)")
    print("=" * 60)
    
    # 1. אתחול הרנטיים
    runtime = EyeTrackingRuntime()
    
    # הדפסת ה-IP המוגדר כעת במחשב לטובת דיבאג
    current_host = os.environ.get("TOBII_GLASSES_HOST", "לא מוגדר (משתמש בברירת מחדל)")
    print(f"[*] משתנה הסביבה TOBII_GLASSES_HOST: {current_host}")
    
    # 2. בדיקת זמינות המכשיר ברשת
    print("\n[1/4] בודק חיבור למשקפיים ברשת...")
    if not runtime.ensure_tracker():
        print(f"[-] נכשל: {runtime.last_error}")
        print_host_diagnostics(runtime)
        print("\nטיפ: ודא שכבל האתרנט מחובר ושהמשקפיים דלוקים.")
        return
    print(f"[+] המשקפיים נמצאו בהצלחה! סוג מכשיר: {runtime.tracker_label}")
    print_host_diagnostics(runtime)

    # 3. ניסיון הפעלת הקלטה
    print("\n[2/4] מנסה להתחיל הקלטה (Start Recording)...")
    success, error_msg = runtime.start()
    if not success:
        print(f"[-] נכשלה הפעלת ההקלטה: {error_msg}")
        return
        
    print(f"[+] ההקלטה החלה בהצלחה!")
    print(f"[+] מזהה ייחודי של ההקלטה (UUID): {runtime.current_recording_uuid}")
    print(f"[+] סטטוס מערכת (Active): {runtime.active}")

    # 4. המרחב שבו מקליטים
    print("\n[3/4] מקליט כעת ברקע למשך 5 שניות... (אנא הסתכלו מסביב)")
    for i in range(5, 0, -1):
        print(f"    נותרו {i} שניות...")
        time.sleep(1)

    # 5. ניסיון עצירת הקלטה ומשיכת נתונים
    print("\n[4/4] מנסה לעצור הקלטה ולמשוך נתונים (Stop & Fetch)...")
    features, stop_error = runtime.stop()
    
    if stop_error:
        print(f"[-] שגיאה בעת עצירת ההקלטה או משיכת הנתונים: {stop_error}")
        return

    print("=" * 60)
    print("[+++] הבדיקה הסתיימה בהצלחה מלאה! [+++]")
    print(f"[*] סך הכל דגימות עיניים גולמיות שנמשכו: {runtime.raw_sample_count}")
    
    if features:
        print("\nמדדים ראשוניים שחולצו בהצלחה:")
        print(f" - כמות פיקסציות (Fixation Count): {features.get('fixation_count')}")
        print(f" - כמות סקאדות (Saccade Count): {features.get('saccade_count')}")
        print(f" - משך פיקסציה כולל (Fixation Duration): {features.get('fixation_duration'):.2f} שניות")
    else:
        print("\n[-] אזהרה: ההקלטה נעצרה אך לא חולצו מדדים (features ריק)")
        
    print("=" * 60)

if __name__ == "__main__":
    run_test()
