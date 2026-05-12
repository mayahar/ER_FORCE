import json
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("database_data.json")


def _load_database():
    if not DATABASE_PATH.exists():
        return {}

    with DATABASE_PATH.open("r", encoding="utf-8") as db_file:
        data = json.load(db_file)

    subjects = data.get("subjects", {})
    return {int(subject_id): subject for subject_id, subject in subjects.items()}


SUBJECTS_DB = _load_database()


def save_database():
    data = {
        "subjects": {
            str(subject_id): subject
            for subject_id, subject in sorted(SUBJECTS_DB.items())
        }
    }

    with DATABASE_PATH.open("w", encoding="utf-8") as db_file:
        json.dump(data, db_file, ensure_ascii=False, indent=2)
        db_file.write("\n")
