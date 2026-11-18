"""Profile użytkowników."""

import re

from authtrace import config
from database import (
    get_usernames,
    get_next_session_number,
    get_session_ids,
    save_user,
)

_NAME_RE = re.compile(r"[\w-]{1,40}")


class ProfileStore:
    def __init__(self, models_dir=config.MODELS_DIR):
        self.models_dir = models_dir
        self.user_ids = {}

    @staticmethod
    def is_valid_name(name):
        return bool(_NAME_RE.fullmatch(name))

    def get_user_id(self, name: str) -> int:
        if name not in self.user_ids:
            self.user_ids[name] = save_user(name)
        return self.user_ids[name]

    def names(self):
        return get_usernames()

    def create(self, name):
        if not ProfileStore.is_valid_name(name):
            raise ValueError("Nazwa profilu: litery, cyfry, '_' lub '-' (bez spacji), max 40 znaków.")
        return self.get_user_id(name)

    def session_ids(self, name: str) -> list:
        return get_session_ids(self.get_user_id(name))

    def next_session_id(self, name: str) -> int:
        return get_next_session_number(self.get_user_id(name))

    def has_model(self, name: str) -> bool:
        return (self.models_dir / name / "model.pkl").exists()

    def summary(self, name: str) -> dict:
        return {"sessions": len(self.session_ids(name)), "model": self.has_model(name)}
