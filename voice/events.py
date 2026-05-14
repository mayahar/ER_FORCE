from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, Dict


@dataclass
class VoiceEvent:
    event_id: str
    prompt_text: str
    duration: float
    trigger_time: float
    prompt_type: str = "phrase"
    event_type: Optional[str] = None
    status: str = "pending"
    timestamp: Optional[float] = None
    audio_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "prompt_text": self.prompt_text,
            "duration": self.duration,
            "trigger_time": self.trigger_time,
            "prompt_type": self.prompt_type,
            "event_type": self.event_type,
            "status": self.status,
            "timestamp": self.timestamp,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "metadata": self.metadata,
            "error": self.error,
        }
