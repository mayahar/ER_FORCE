import json
from datetime import date
from pathlib import Path


RESEARCH_CONFIG_PATH = Path(__file__).with_name("research_config.json")


def load_research_config():
    if not RESEARCH_CONFIG_PATH.exists():
        return {"enabled": False}

    with RESEARCH_CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def is_research_enabled():
    return bool(load_research_config().get("enabled", False))


def get_research_config():
    return load_research_config()


def get_research_participants():
    return list(load_research_config().get("participants", []))


def get_research_participant_ids():
    return sorted(
        int(participant["id"])
        for participant in get_research_participants()
        if "id" in participant
    )


def get_research_participant(subject_id):
    sid = int(subject_id)

    for participant in get_research_participants():
        if int(participant.get("id")) == sid:
            return participant

    return None


def get_current_research_day(today=None):
    config = load_research_config()
    start_date_text = config.get("start_date")

    if not start_date_text:
        return None

    today = today or date.today()
    start_date = date.fromisoformat(start_date_text)
    day_number = (today - start_date).days + 1

    if day_number < 1:
        return None

    day_config = config.get("days", {}).get(str(day_number))

    if not day_config:
        return None

    return {
        "study_id": config.get("study_id", "research"),
        "start_date": start_date_text,
        "day_number": day_number,
        "condition": day_config.get("label", f"day_{day_number}"),
        "sleep_last": day_config.get("sleep_last"),
        "sleep_previous": day_config.get("sleep_previous"),
        "is_baseline_day": bool(day_config.get("is_baseline_day", False)),
        "output_dir": config.get("output_dir", "research_results"),
    }


def get_research_output_dir(research_context, subject_id=None):
    output_dir = Path(research_context.get("output_dir", "research_results"))

    if subject_id is not None:
        output_dir = output_dir / f"participant_{subject_id}"

    return output_dir
