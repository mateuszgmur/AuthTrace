"""
Profile użytkowników.

Profil = katalog data/<nazwa>/ z plikami sesji. Nie ma osobnej bazy (dawny
typeracer/profiles.json ze statystykami WPM został usunięty) — jedynym źródłem
prawdy są pliki, które i tak czyta train.py.
"""

import re
from pathlib import Path

from authtrace import config

# Litery (także polskie), cyfry, "_" i "-". Blokuje spacje, "/", "..": nazwa
# profilu staje się nazwą katalogu, więc nie może wyjść poza data/.
_NAME_RE = re.compile(r"[\w-]{1,40}")
_SESSION_RE = re.compile(r"features_session_(\d+)\.json")


class ProfileStore:
    def __init__(self, data_dir: Path = config.DATA_DIR, models_dir: Path = config.MODELS_DIR):
        self.data_dir = Path(data_dir)
        self.models_dir = Path(models_dir)

    @staticmethod
    def is_valid_name(name: str) -> bool:
        return bool(_NAME_RE.fullmatch(name))

    def names(self) -> list:
        if not self.data_dir.exists():
            return []
        return sorted(p.name for p in self.data_dir.iterdir() if p.is_dir())

    def create(self, name: str) -> Path:
        if not self.is_valid_name(name):
            raise ValueError("Nazwa profilu: litery, cyfry, '_' lub '-' (bez spacji), max 40 znaków.")
        path = self.data_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, name: str) -> Path:
        return self.data_dir / name

    def session_ids(self, name: str) -> list:
        """Numery zapisanych sesji, posortowane rosnąco (numerycznie, nie 1, 10, 2...)."""
        d = self.path(name)
        if not d.exists():
            return []
        ids = (_SESSION_RE.fullmatch(p.name) for p in d.iterdir())
        return sorted(int(m.group(1)) for m in ids if m)

    def next_session_id(self, name: str) -> int:
        """Kolejny wolny numer — koniec z ręcznym --session i nadpisywaniem starych sesji."""
        ids = self.session_ids(name)
        return ids[-1] + 1 if ids else 1

    def has_model(self, name: str) -> bool:
        return (self.models_dir / name / "model.pkl").exists()

    def summary(self, name: str) -> dict:
        return {"sessions": len(self.session_ids(name)), "model": self.has_model(name)}
