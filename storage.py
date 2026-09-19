import os
import json
from typing import List, Dict, Any

CONFIG_DIR = os.path.expanduser("~/.config/tuitify")
CONFIG_FILE = os.path.join(CONFIG_DIR, "data.json")

DEFAULT_SCHEMA: Dict[str, Any] = {
    "recent": {
        "history": []
    },
    "pinned": {
        "songs": []
    },
    "settings": {
        "volume": 100,
        "default_search_filter": "songs"
    }
}

class StorageManager:
    def __init__(self):
        self._ensure_config_exists()
        self.data = self._load()

    def _ensure_config_exists(self):
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        if not os.path.exists(CONFIG_FILE):
            self._save(DEFAULT_SCHEMA)

    def _load(self) -> Dict[str, Any]:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, val in DEFAULT_SCHEMA.items():
                    if key not in data:
                        data[key] = val
                return data
        except Exception:
            return DEFAULT_SCHEMA.copy()

    def _save(self, data: Dict[str, Any]):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_recent_songs(self, limit: int = 5) -> List[Dict[str, str]]:
        return self.data.get("recent", {}).get("history", [])[:limit]

    def add_recent_song(self, song: Dict[str, str]):
        history = self.data.setdefault("recent", {}).setdefault("history", [])
        history = [s for s in history if s.get("id") != song.get("id")]
        history.insert(0, song)
        self.data["recent"]["history"] = history[:50]
        self._save(self.data)

    def remove_recent_song(self, video_id: str):
        history = self.data.setdefault("recent", {}).setdefault("history", [])
        self.data["recent"]["history"] = [s for s in history if s.get("id") != video_id]
        self._save(self.data)

    def get_pinned_songs(self, limit: int = 5) -> List[Dict[str, str]]:
        return self.data.get("pinned", {}).get("songs", [])[:limit]

    def toggle_pinned_song(self, song: Dict[str, str]) -> bool:
        """Toggles pinned status. Returns True if pinned, False if unpinned."""
        pinned = self.data.setdefault("pinned", {}).setdefault("songs", [])
        exists = any(s.get("id") == song.get("id") for s in pinned)
        if exists:
            self.data["pinned"]["songs"] = [s for s in pinned if s.get("id") != song.get("id")]
            self._save(self.data)
            return False
        else:
            pinned.insert(0, song)
            self.data["pinned"]["songs"] = pinned[:20]
            self._save(self.data)
            return True

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.data.get("settings", {}).get(key, default)

    def set_setting(self, key: str, val: Any):
        self.data.setdefault("settings", {})[key] = val
        self._save(self.data)