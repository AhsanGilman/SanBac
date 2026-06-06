import os
import json
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".sanbac"
DEFAULT_DB_DIR = DEFAULT_CONFIG_DIR / "db"
CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"

class Config:
    def __init__(self):
        self.config_dir = DEFAULT_CONFIG_DIR
        self.db_dir = DEFAULT_DB_DIR
        self.executables = {
            "rgi": "rgi",
            "diamond": "diamond",
            "prokka": "prokka",
            "parsnp": "parsnp",
            "mashtree": "mashtree"
        }
        self.load()

    def load(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.db_dir = Path(data.get("db_dir", str(DEFAULT_DB_DIR)))
                    execs = data.get("executables", {})
                    for k, v in execs.items():
                        if k in self.executables:
                            self.executables[k] = v
            except Exception:
                # Fallback to defaults
                pass

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "db_dir": str(self.db_dir),
            "executables": self.executables
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def get_executable(self, name):
        return self.executables.get(name, name)

    def set_executable(self, name, path):
        if name in self.executables:
            self.executables[name] = path
            self.save()

# Global config instance
config = Config()
