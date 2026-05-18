from score.fatigue_scoring import compute_fatigue_score


def ask_float(name):
    val = input(f"{name}: ")
    return float(val) if val.strip() != "" else None


def ask_block(title, keys):
    print(f"\n--- {title} ---")
    data = {}
    for k in keys:
        data[k] = ask_float(k)
    return data


def main():

    print("\n=== FATIGUE PLAYGROUND ===")
    print("Leave empty to skip a value\n")

    # -------------------------
    # BASELINE
    # -------------------------
    print("\n### BASELINE ###")

    baseline_voice = ask_block("VOICE (baseline)", [
        "dLPC", "PARCOR", "LPC", "Pitch", "MFCC"
    ])

    baseline_eye = ask_block("EYE (baseline)", [
        "fixation_duration", "fixation_count", "saccade_count"
    ])

    baseline_game = ask_block("GAME (baseline)", [
        "score"
    ])

    # -------------------------
    # CURRENT
    # -------------------------
    print("\n### CURRENT ###")

    current_voice = ask_block("VOICE (current)", [
        "dLPC", "PARCOR", "LPC", "Pitch", "MFCC"
    ])

    current_eye = ask_block("EYE (current)", [
        "fixation_duration", "fixation_count", "saccade_count"
    ])

    current_game = ask_block("GAME (current)", [
        "score"
    ])

    # -------------------------
    # SUBJECT INFO (optional)
    # -------------------------
    sex = input("\nSex (male/female, optional): ").strip() or None

    # -------------------------
    # BUILD DATA
    # -------------------------
    data = {
        "subject_id": "debug",
        "session_id": "debug",
        "subject_info": {"sex": sex} if sex else {},
        "baseline": {
            "voice": baseline_voice,
            "eye": baseline_eye,
            "game": baseline_game
        },
        "current": {
            "voice": current_voice,
            "eye": current_eye,
            "game": current_game
        }
    }

    # -------------------------
    # RUN MODEL
    # -------------------------
    result = compute_fatigue_score(data)

    print("\n========================")
    print("FINAL RESULT")
    print("========================")

    print(f"\nFatigue Score: {result['score']:.2f}")

    print("\n--- Modality Scores ---")
    for k, v in result["scores"].items():
        if v is not None:
            print(f"{k}: {v:.3f}")

    print("\n--- Feature Contributions ---")

    for modality, feats in result["feature_contributions"].items():
        print(f"\n[{modality.upper()}]")

        for fname, fdata in feats.items():
            val = fdata["value"]
            direction = fdata["direction"]

            arrow = "↑ fatigue" if direction == 1 else "↓ fatigue"

            print(
                f"{fname:20s} | contrib={val:.4f} | score={fdata['raw_score']:.3f} | {arrow}"
            )


if __name__ == "__main__":
    main()