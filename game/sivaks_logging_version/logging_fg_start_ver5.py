import subprocess
import datetime
import xml.etree.ElementTree as ET
import time
import shutil
import os
import sys
import csv
import math

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None
    messagebox = None


def resolve_f16_aircraft_paths(script_dir):
    """
    Use the bundled aircraft path directly (saves disk by avoiding a second copy under data/Aircraft/f16).

    FlightGear supports multiple aircraft roots via --fg-aircraft=path[:path...]. By adding the
    bundle root (sivaks_logging_version/Aircraft) we can resolve Aircraft/f16/* references
    without copying into $FG_ROOT/data/Aircraft.
    """
    bundle_root = os.path.join(script_dir, "Aircraft")
    bundle_f16_dir = os.path.join(bundle_root, "f16")
    if not os.path.isdir(bundle_f16_dir):
        raise FileNotFoundError(f"Missing bundled F-16 folder: {bundle_f16_dir}")
    return bundle_root, bundle_f16_dir


def generate_xml_log_file(config_output_dir, interval_ms=1000, properties=[], csv_export_folder=None):
    """
    Function to generate XML log file for FlightGear logging.

    Parameters:
        - config_output_dir: Where to write the XML config file.
        - interval_ms: Interval in milliseconds (default is 1000).
        - properties: List of properties to include in the log.
        - csv_export_folder: Where FlightGear is allowed to write the CSV (defaults to config_output_dir).

    Returns:
        - xml_filename: Name of the XML file generated.
    """
    # Generate filename based on current datetime
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    xml_filename = f"sivaks_logging_{now}.xml"

    # Create XML structure
    logging = ET.Element("PropertyList")
    log = ET.SubElement(logging, "logging")
    log_element = ET.SubElement(log, "log", n="0")
    enabled = ET.SubElement(log_element, "enabled", type="bool")
    enabled.text = "true"
    interval = ET.SubElement(log_element, "interval-ms", type="long")
    interval.text = str(interval_ms)
    filename_element = ET.SubElement(log_element, "filename")
    csv_dir = csv_export_folder or config_output_dir
    filename_element.text = os.path.join(csv_dir, xml_filename.replace(".xml", ".csv"))
    delimiter = ET.SubElement(log_element, "delimiter")
    delimiter.text = ","

    for prop in properties:
        entry = ET.SubElement(log_element, "entry")
        enabled = ET.SubElement(entry, "enabled", type="bool")
        enabled.text = "true"
        title = ET.SubElement(entry, "title")
        title.text = prop.split("/")[-1]
        property_tag = ET.SubElement(entry, "property")
        property_tag.text = prop

    os.makedirs(config_output_dir, exist_ok=True)
    tree = ET.ElementTree(logging)
    # Caller decides where the config file lives; we return the XML text via file path.
    tree.write(os.path.join(config_output_dir, xml_filename), encoding="utf-8", xml_declaration=True)

    return xml_filename

def _cleanup_old_sessions(logs_root, keep_last=12):
    """
    Keep only the newest N session_* folders under logs_root.
    """
    try:
        if not os.path.isdir(logs_root):
            return
        dirs = []
        for name in os.listdir(logs_root):
            if not name.startswith("session_"):
                continue
            p = os.path.join(logs_root, name)
            if os.path.isdir(p):
                dirs.append((name, p))
        dirs.sort(key=lambda t: t[0], reverse=True)  # session_YYYYMMDD_HHMMSS
        for _, p in dirs[keep_last:]:
            shutil.rmtree(p, ignore_errors=True)
    except Exception as e:
        print(f"Log cleanup skipped: {e}")

def _cleanup_export_folder(export_folder, keep_last=10):
    """
    Clean up old sivaks_logging_*.{csv,xml} in the FlightGear Export folder.
    Keeps the newest N by mtime.
    """
    try:
        if not os.path.isdir(export_folder):
            return
        keep_last = int(keep_last)
        candidates = []
        for name in os.listdir(export_folder):
            low = name.lower()
            if not low.startswith("sivaks_logging_"):
                continue
            if not (low.endswith(".csv") or low.endswith(".xml")):
                continue
            p = os.path.join(export_folder, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            candidates.append((st.st_mtime_ns, p))
        candidates.sort(key=lambda t: t[0], reverse=True)
        for _, p in candidates[keep_last:]:
            try:
                os.remove(p)
            except OSError:
                pass
    except Exception as e:
        print(f"Export cleanup skipped: {e}")

def evaluate_flight_score(csv_path):
    """
    Compute weighted end score from one event per unique balloon-level.
    Score uses distance quality, speed quality, and vertical speed quality.
    """
    # Scoring targets/tolerances (tune here).
    SPEED_TARGET_KT = 350.0
    SPEED_FULL_TOL_KT = 20.0     # full score if within ±20kt
    SPEED_ZERO_TOL_KT = 120.0    # reaches 0 by ±120kt (linear from full tol)

    events = []
    prev_level = None
    with open(csv_path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            level_raw = (row.get("balloon-level") or "").strip()
            hit_raw = (row.get("balloon-hit") or "").strip()
            if level_raw == "" or hit_raw == "":
                continue
            try:
                level_int = int(float(level_raw))
                hit_int = int(float(hit_raw))
            except ValueError:
                continue

            # Count exactly once per balloon pass (new integer balloon-level).
            if level_int <= 0 or level_int == prev_level:
                continue

            # If hit_int == 0 (rare transient), skip this row and wait for stable value.
            if hit_int == 0:
                continue

            def to_float(name, default=0.0):
                raw = (row.get(name) or "").strip()
                if raw == "":
                    return default
                try:
                    return float(raw)
                except ValueError:
                    return default

            lat1 = to_float("latitude-deg")
            lon1 = to_float("longitude-deg")
            alt1 = to_float("altitude-ft")
            lat2 = to_float("balloon-lat")
            lon2 = to_float("balloon-lon")
            alt2 = to_float("balloon-alt")
            speed_kt = to_float("airspeed-kt")
            vert_fpm = to_float("indicated-speed-fpm")

            # Haversine horizontal distance (feet).
            r_ft = 20925524.9
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
            c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
            horizontal_ft = r_ft * c
            vertical_ft = abs(alt2 - alt1)
            dist_ft = math.sqrt((horizontal_ft * horizontal_ft) + (vertical_ft * vertical_ft))

            # Quality scores (0-100 each).
            # Distance: 150ft perfect, 600ft very poor.
            if dist_ft <= 150.0:
                dist_score = 100.0
            elif dist_ft >= 600.0:
                dist_score = 0.0
            else:
                dist_score = (600.0 - dist_ft) / (600.0 - 150.0) * 100.0

            # Speed target 350kt:
            # - Full score within ±20kt
            # - Then linearly degrades to 0 by ±120kt
            speed_err = abs(speed_kt - SPEED_TARGET_KT)
            if speed_err <= SPEED_FULL_TOL_KT:
                speed_score = 100.0
            elif speed_err >= SPEED_ZERO_TOL_KT:
                speed_score = 0.0
            else:
                speed_score = (SPEED_ZERO_TOL_KT - speed_err) / (SPEED_ZERO_TOL_KT - SPEED_FULL_TOL_KT) * 100.0

            # Vertical speed target near 0fpm, best under 2000, zero by 7000.
            vert_abs = abs(vert_fpm)
            if vert_abs <= 2000.0:
                vert_score = 100.0
            elif vert_abs >= 7000.0:
                vert_score = 0.0
            else:
                vert_score = (7000.0 - vert_abs) / (7000.0 - 2000.0) * 100.0

            # Event score (bounded 0-100 without saturation):
            # Convert sub-scores to a weighted quality score in [0, 1],
            # then map to:
            # - hit: base + (100-base)*quality
            # - miss: 0 + 100*quality
            w_dist = 0.60
            w_speed = 0.30
            w_vert = 0.10
            w_sum = w_dist + w_speed + w_vert
            quality = (
                (w_dist * dist_score)
                + (w_speed * speed_score)
                + (w_vert * vert_score)
            ) / (w_sum * 100.0)
            quality = max(0.0, min(1.0, quality))

            if hit_int > 0:
                base = 40.0
                event_score = base + ((100.0 - base) * quality)
            else:
                event_score = 100.0 * quality
            events.append({
                "balloon_level": level_int,
                "hit": hit_int > 0,
                "dist_ft": dist_ft,
                "horizontal_ft": horizontal_ft,
                "vertical_ft": vertical_ft,
                "dist_score": dist_score,
                "speed_kt": speed_kt,
                "speed_score": speed_score,
                "vert_fpm": vert_fpm,
                "vert_score": vert_score,
                "score": event_score,
            })
            prev_level = level_int

    hits = sum(1 for e in events if e["hit"])
    misses = sum(1 for e in events if not e["hit"])
    total = hits + misses
    avg_dist = (sum(e["dist_ft"] for e in events) / total) if total > 0 else 0.0
    avg_event_score = (sum(e["score"] for e in events) / total) if total > 0 else 0.0
    score = int(round(avg_event_score, 0)) if total > 0 else 0

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "score": score,
        "grade": grade,
        "avg_dist_ft": avg_dist,
        "events": events,
    }

def show_final_results(session_folder, csv_path):
    result = evaluate_flight_score(csv_path)
    report_path = os.path.join(session_folder, "final_score.txt")
    breakdown_path = os.path.join(session_folder, "score_breakdown.csv")

    # Save per-balloon breakdown to help explain the score.
    try:
        events = result.get("events", []) or []
        fieldnames = [
            "balloon_level",
            "hit",
            "dist_ft",
            "horizontal_ft",
            "vertical_ft",
            "dist_score",
            "speed_kt",
            "speed_score",
            "vert_fpm",
            "vert_score",
            "score",
        ]
        with open(breakdown_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for e in events:
                writer.writerow({k: e.get(k) for k in fieldnames})
    except Exception as e:
        breakdown_path = None
        print(f"Failed to write score breakdown CSV: {e}")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(
            "CorrActions Final Results\n"
            "=========================\n"
            f"CSV: {csv_path}\n"
            f"Balloons counted: {result['total']}\n"
            f"Hits: {result['hits']}\n"
            f"Misses: {result['misses']}\n"
            f"Average distance to balloon center (ft): {result['avg_dist_ft']:.1f}\n"
            f"Score: {result['score']}/100\n"
            f"Grade: {result['grade']}\n"
            + (f"Breakdown: {breakdown_path}\n" if breakdown_path else "")
        )

    show_popup = os.environ.get("SIVAKS_SHOW_RESULTS_POPUP", "").strip().lower() in ("1", "true", "yes", "y", "on")

    if show_popup and tk is not None and messagebox is not None:
        root = tk.Tk()
        root.title("CorrActions - Final Results")
        root.configure(bg="#0f172a")
        root.geometry("560x360")
        root.resizable(False, False)

        if result["score"] >= 85:
            accent = "#22c55e"
        elif result["score"] >= 70:
            accent = "#f59e0b"
        else:
            accent = "#ef4444"

        title = tk.Label(root, text="Flight Performance Summary", fg="#e2e8f0", bg="#0f172a", font=("Segoe UI", 18, "bold"))
        title.pack(pady=(16, 8))

        score_line = tk.Label(
            root,
            text=f"Score {result['score']}/100    Grade {result['grade']}",
            fg=accent,
            bg="#0f172a",
            font=("Segoe UI", 20, "bold"),
        )
        score_line.pack(pady=(6, 12))

        stats_text = (
            f"Balloons counted: {result['total']}\n"
            f"Hits: {result['hits']}    Misses: {result['misses']}\n"
            f"Average distance to center: {result['avg_dist_ft']:.1f} ft"
        )
        stats = tk.Label(root, text=stats_text, fg="#cbd5e1", bg="#0f172a", font=("Segoe UI", 12), justify="center")
        stats.pack(pady=(4, 14))

        extra = f"\nBreakdown:\n{breakdown_path}" if breakdown_path else ""
        report_lbl = tk.Label(root, text=f"Saved report:\n{report_path}{extra}", fg="#94a3b8", bg="#0f172a", font=("Segoe UI", 9), justify="center")
        report_lbl.pack(pady=(0, 14))

        ok_btn = tk.Button(root, text="Close", font=("Segoe UI", 11, "bold"), bg=accent, fg="#0b1020", activebackground=accent, relief="flat", padx=20, pady=8, command=root.destroy)
        ok_btn.pack()
        root.eval("tk::PlaceWindow . center")
        root.mainloop()
    else:
        text = (
            f"Final Score: {result['score']}/100\n"
            f"Grade: {result['grade']}\n"
            f"Hits: {result['hits']} | Misses: {result['misses']}\n"
            f"Average distance: {result['avg_dist_ft']:.1f} ft\n"
            f"Saved report: {report_path}"
        )
        print(text)

def run_flightgear(fg_bin_path, fg_aircraft, aircraft_dir, aircraft, airport, xml_filename, export_folder, fg_command_args=None):
    """
    Function to run FlightGear simulator with specified parameters.

    Parameters:
        - fg_bin_path: Path to FlightGear executable.
        - fg_aircraft: Path to directory containing the FlightGear aircraft.
        - aircraft_dir: Directory containing the aircraft model files.
        - aircraft: Aircraft model to use.
        - airport: Airport ICAO code.
        - xml_filename: Name of the XML logging file.
        - export_folder: Path to the export folder.
        - fg_command_args: Additional command-line arguments for FlightGear (optional).
    """
    # Session folder is the directory containing the generated XML config.
    # We'll also write FlightGear logs there so we can see what scenery/map is being loaded.
    session_folder = os.path.dirname(os.path.abspath(xml_filename))

    # Basic command to run FlightGear
    command = [fg_bin_path,
               '--fg-aircraft=' + fg_aircraft,
               '--airport=' + airport,
               '--aircraft-dir=' + aircraft_dir,
               '--aircraft=' + aircraft,
               '--config=' + xml_filename,
               '--log-level=info',
               '--log-dir=' + session_folder]

    # Add additional command-line arguments if provided
    if fg_command_args:
        command.extend(fg_command_args)

    # Ensure Export folder exists (FlightGear writes CSV here).
    os.makedirs(export_folder, exist_ok=True)

    # We expect the CSV filename to match the XML base name.
    csv_filename_local = os.path.basename(xml_filename).replace(".xml", ".csv")
    csv_filename_export = os.path.join(export_folder, csv_filename_local)

    # If a stale file exists from a prior run, remove it so existence checks are meaningful.
    try:
        if os.path.exists(csv_filename_export):
            os.remove(csv_filename_export)
    except OSError:
        pass

    started_at = time.time()

    # Run FlightGear (blocking until it exits)
    subprocess.run(command)

    # Wait for the CSV to appear (FlightGear may flush on exit with a delay)
    time.sleep(2)

    def _is_nonempty_file(path):
        try:
            return os.path.exists(path) and os.path.getsize(path) > 0
        except OSError:
            return False

    # Retry longer and with a fallback to the newest non-empty sivaks_logging_*.csv written after launch.
    attempts = 0
    max_attempts = 18  # ~3 minutes at 10s intervals
    while attempts < max_attempts and not _is_nonempty_file(csv_filename_export):
        attempts += 1
        time.sleep(10)

        if not os.path.exists(csv_filename_export):
            print(f"CSV file not found yet: {csv_filename_export}")
        else:
            print(f"CSV file still empty: {csv_filename_export}")

        # Fallback: some FG setups can write a CSV with a different timestamp/name.
        try:
            candidates = []
            for name in os.listdir(export_folder):
                low = name.lower()
                if not (low.startswith("sivaks_logging_") and low.endswith(".csv")):
                    continue
                p = os.path.join(export_folder, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if st.st_mtime >= started_at and st.st_size > 0:
                    candidates.append((st.st_mtime, p))
            candidates.sort(key=lambda t: t[0], reverse=True)
            if candidates:
                newest = candidates[0][1]
                if newest != csv_filename_export:
                    csv_filename_export = newest
                    csv_filename_local = os.path.basename(newest)
        except Exception:
            pass

    if not _is_nonempty_file(csv_filename_export):
        raise FileNotFoundError(
            "No non-empty CSV was produced in the FlightGear Export folder. "
            f"Expected: {os.path.join(export_folder, os.path.basename(xml_filename).replace('.xml', '.csv'))}"
        )
        
    # Store every run in a dedicated session folder.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runs_root = os.path.join(script_dir, "runs")
    os.makedirs(runs_root, exist_ok=True)
    session_id = datetime.datetime.now().strftime("session_%Y%m%d_%H%M%S")
    session_folder = os.path.join(runs_root, session_id)
    os.makedirs(session_folder, exist_ok=True)

    # Save CSV in session folder (and keep the config XML there too).
    session_xml_path = os.path.join(session_folder, os.path.basename(xml_filename))
    session_csv_path = os.path.join(session_folder, csv_filename_local)
    try:
        if os.path.isfile(xml_filename) and os.path.abspath(os.path.dirname(xml_filename)) != os.path.abspath(session_folder):
            shutil.copy(xml_filename, session_xml_path)
        elif os.path.isfile(xml_filename):
            session_xml_path = os.path.abspath(xml_filename)
    except Exception:
        pass
    shutil.copy(csv_filename_export, session_csv_path)

    # Optional cleanup: after we have the session copy, we can delete the Export copy
    # to prevent the global Export folder from growing without bound.
    # Set SIVAKS_DELETE_EXPORT_AFTER_COPY=1 to enable.
    delete_export_after_copy = os.environ.get("SIVAKS_DELETE_EXPORT_AFTER_COPY", "").strip().lower() in (
        "1", "true", "yes", "y", "on"
    )
    if delete_export_after_copy:
        try:
            if os.path.exists(csv_filename_export):
                os.remove(csv_filename_export)
        except OSError:
            pass

    # Copy CSV file from export folder to current directory
    # shutil.copy(export_folder + xml_filename.replace(".xml", ".csv"), f"{xml_filename.replace('.xml', '')}.csv")
    
        # Edit the first line of the CSV file
    with open(session_csv_path, 'r+', encoding="utf-8") as file:
        lines = file.readlines()
        lines[0] = "Time,axis0_aileron,axis1_elevator,axis2_throttle_all,axis3_rudder," + lines[0].split(',', 5)[-1]  # Replace the beginning of the first line
        # '/controls/flight/aileron',
        # '/controls/flight/elevator',
        # '/controls/engines/throttle-all',
        # '/controls/flight/rudder',
        file.seek(0)
        file.writelines(lines)

    # Report filenames to command prompt
    print(f"Session folder: {session_folder}")
    print(f"XML File: {session_xml_path}")
    print(f"CSV File: {session_csv_path}")
    show_final_results(session_folder, session_csv_path)

    # Run Zohar's analytics script with arguments
    # time.sleep(5)

    output_script = os.path.join(script_dir, "output.py")
    try:
        # Optional: run the analytics/dashboard script (can be disabled).
        # Set SIVAKS_RUN_DASHBOARD=0 to skip.
        run_dashboard = os.environ.get("SIVAKS_RUN_DASHBOARD", "1").strip().lower() not in ("0", "false", "no", "n", "off")
        if run_dashboard:
            # Use the active interpreter so this works on any machine/user.
            subprocess.run([sys.executable, output_script, session_csv_path], cwd=script_dir, check=True)
    except Exception as e:
        print(f"Failed to launch score dashboard: {e}")


# Example usage
if __name__ == "__main__":
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    bundle_aircraft_root, bundle_f16_dir = resolve_f16_aircraft_paths(_script_dir)

    _fg_root = os.path.normpath(os.path.join(_script_dir, ".."))
    fg_bin_path = os.path.join(_fg_root, "bin", "fgfs.exe")
    if not os.path.isfile(fg_bin_path):
        fg_bin_path = os.path.join(_fg_root, "bin", "fgfs")

    # $FG_ROOT/data/Aircraft (Generic, Instruments, …) + bundled aircraft root.
    # IMPORTANT: Multiple roots are separated by ';' on Windows.
    fg_aircraft = os.path.join(_fg_root, "data", "Aircraft") + ";" + bundle_aircraft_root
    # F-16 flyable from the bundle (no duplicate copy under data/Aircraft/f16)
    aircraft_dir = bundle_f16_dir
    aircraft = "f16-block-52"

    # Airport ICAO code
    airport = "PHTO"

    # Path to export folder (FlightGear writes the live CSV here)
    export_folder = os.path.join(os.getenv('APPDATA'), "flightgear.org\\Export")

    # Cleanup policy (safe defaults)
    # - keep_last_sessions: how many runs to keep under sivaks_logging_version/runs
    # - keep_last_exports: how many sivaks_logging_*.csv/xml files to keep in FlightGear Export
    keep_last_sessions = int(os.environ.get("SIVAKS_KEEP_LAST_SESSIONS", "12"))
    keep_last_exports = int(os.environ.get("SIVAKS_KEEP_LAST_EXPORTS", "10"))


    # F-16 CorrActions tutorial <name> (see Aircraft/f16/Tutorials/*.xml in this folder).
    autostart_tutorial_name = "CorrActions DEFAULT"

    # Additional command-line arguments (optional)
    # (Reverted: do not force scenery/terrain/visibility optimizations.)
    fg_command_args = [
        '--disable-splash-screen',
        # Hide the top menubar (can also be toggled with F10).
        '--prop:/sim/menubar/visibility=false',
        # Speed-up: avoid parsing AI traffic schedules (not needed for CorrActions balloons).
        '--disable-ai-traffic',
        # Speed-up: do not use the TerraSync scenery folder (loads a lot of tiles).
        # Use only the bundled FG_ROOT scenery.
        '--fg-scenery=' + os.path.join(_fg_root, "data", "Scenery"),
        '--prop:/nasal/local_weather/enabled=false',
        '--metar=XXXX 012345Z 15003KT 19SM FEW072 FEW350 25/07 Q1028 NOSIG',
        '--prop:/environment/weather-scenario=Core high pressure region',
        '--prop:/sim/rendering/texture-cache/cache-enabled=true',
        # TerraSync needs working DNS for terrasync.flightgear.org; disable to avoid ALRT spam when offline/DNS fails.
        '--disable-terrasync',
        '--disable-sentry',
        '--state=take-off',
        '--prop:/sim/sivaks/autostart-tutorial-enabled=true',
        '--prop:/sim/sivaks/autostart-tutorial=' + autostart_tutorial_name,
    ]

    # Optional: skip JSBSim trim at startup (can be unstable for some aircraft/states).
    # Set SIVAKS_NOTRIM=1 if you want to try it again.
    if os.environ.get("SIVAKS_NOTRIM", "").strip().lower() in ("1", "true", "yes", "y", "on"):
        fg_command_args.append("--notrim")

    # Run folder for this session (create early so config XML is not left in the script root).
    _runs_root = os.path.join(_script_dir, "runs")
    os.makedirs(_runs_root, exist_ok=True)
    _session_id = datetime.datetime.now().strftime("session_%Y%m%d_%H%M%S")
    _session_folder = os.path.join(_runs_root, _session_id)
    os.makedirs(_session_folder, exist_ok=True)

    _cleanup_old_sessions(_runs_root, keep_last=keep_last_sessions)
    _cleanup_export_folder(export_folder, keep_last=keep_last_exports)

    # Generate XML log file into the session folder and run FlightGear.
    xml_filename_only = generate_xml_log_file(
        _session_folder,
        20,
        properties=[
#        '/input/joysticks/js/axis/binding/setting',
#        '/input/joysticks/js/axis[1]/binding/factor',
#        '/input/joysticks/js/axis[2]/binding/setting',
#        '/input/joysticks/js/axis[3]/binding/setting',
# doesn't work, idea: Use instead their flight and engine control bindings directly
        '/controls/flight/aileron',
        '/controls/flight/elevator',
        '/controls/engines/throttle-all',
        '/controls/flight/rudder',
        '/instrumentation/altimeter/indicated-altitude-ft',
        '/instrumentation/airspeed-indicator/indicated-speed-kt',
        '/instrumentation/vertical-speed-indicator/indicated-speed-fpm',
        '/instrumentation/gps/indicated-track-magnetic-deg',
        '/instrumentation/heading-indicator/indicated-heading-deg',        
        '/velocities/airspeed-kt',
        '/velocities/groundspeed-kt',
        '/position/altitude-agl-ft',
        '/position/altitude-ft',
        '/position/latitude-deg',
        '/position/longitude-deg',
        '/algorithm/game/balloon-lat',
        '/algorithm/game/balloon-lon',
        '/algorithm/game/balloon-alt',
        '/algorithm/game/balloon-level',
        '/algorithm/game/balloon-hit'
        ],
        csv_export_folder=export_folder,
    )
    xml_config_path = os.path.join(_session_folder, xml_filename_only)
    run_flightgear(fg_bin_path, fg_aircraft, aircraft_dir, aircraft, airport, xml_config_path, export_folder, fg_command_args)
