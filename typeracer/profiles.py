import json
import os
import config


class ProfileManager:
    # zapamiętuje ścieżkę i wczytuje profile
    def __init__(self, path=config.PROFILES_FILE):
        self.path = path
        self.profiles = self._load()       # slownik: nazwa -> lista wynikow

    # metoda czytająca JSONa
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # zapisuje słownik z wcięciami
    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.profiles, f, ensure_ascii=False, indent=2)

    # zwraca liste nazw profili
    def names(self):
        return list(self.profiles.keys())

    def ensure(self, name):
        # tworzy profil jeśli nie istnieje
        if name not in self.profiles:
            self.profiles[name] = []
            self._save()

    def add_result(self, name, result):
        # zapisuje podejście do profilu w pliku
        self.ensure(name)
        self.profiles[name].append(result)
        self._save()

    def summary(self, name):
        # podsumowanie: liczba gier, rekord, srednia
        results = self.profiles.get(name, [])
        if not results:
            return None
        wpms = [r["wpm"] for r in results]
        return {
            "games": len(results),
            "best": max(wpms),
            "avg": sum(wpms) / len(wpms),
        }
