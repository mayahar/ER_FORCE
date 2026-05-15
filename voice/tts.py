import subprocess
import sys


def speak_text(text: str, timeout: float = 15.0) -> None:
    if not text:
        return

    if sys.platform != "win32":
        raise RuntimeError("Text-to-speech is only supported on Windows in this implementation")

    escaped_text = str(text).replace('"', '""')
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak(\"{escaped_text}\");"
    )

    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
