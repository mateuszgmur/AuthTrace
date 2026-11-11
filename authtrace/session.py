"""
Sesja zbierania danych — wspólna dla trybu GUI (typeracer) i CLI (collector.py).

    session = CollectorSession("mateusz")
    session.start()            # backend nasłuchuje w tle
    session.pause()/resume()   # GUI wstrzymuje zapis, np. gdy wpisujesz nazwę profilu
    result = session.finish()  # zatrzymuje backend i zapisuje pliki (albo None)

Zapis jest taki sam jak w starym collectorze, więc train.py działa bez zmian:
    data/<profil>/raw_session_N.json
    data/<profil>/features_session_N.json
"""

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from authtrace import config
from authtrace.backends import create_backend
from authtrace.features import extract_features
from authtrace.profiles import ProfileStore


@dataclass
class SessionResult:
    session_id: int
    raw_path: Path
    features_path: Path
    features: dict


class SessionTooShort(Exception):
    """Za mało zdarzeń, żeby zapisać sesję."""


class CollectorSession:
    def __init__(self, profile: str, backend="auto", devices=None,
                 store: ProfileStore = None, on_event=None):
        """
        backend  – "auto" | "pynput" | "evdev" albo fabryka f(on_press, on_release)
                   zwracająca obiekt z start()/stop() (używane w testach)
        on_event – opcjonalny callback(event_dict) wołany z wątku backendu (np. ESC w CLI)
        """
        self.store = store or ProfileStore()
        self.profile = profile
        self.store.create(profile)
        self._on_event = on_event
        self._events = []
        self._down = set()   # klawisze, których press został zapisany, a release jeszcze nie
        self._lock = threading.Lock()
        self._recording = True
        if callable(backend):
            self._backend = backend(self._press, self._release)
        else:
            self._backend = create_backend(backend, self._press, self._release, devices)

    # ------------------------------------------------ callbacki z wątku backendu
    def _record(self, kind: str, key: str, t: float):
        if not self._recording:
            return
        event = {"event": kind, "key": key, "t": t}
        with self._lock:
            if kind == "press":
                self._down.add(key)
            elif key in self._down:
                self._down.discard(key)
            else:
                # "Sierota": release bez zapisanego press (np. Enter, którym uruchomiono
                # skrypt, albo klawisz wciśnięty w trakcie pauzy). Przesunąłby parowanie
                # FIFO w dwell time dla tego klawisza do końca sesji — odrzucamy.
                return
            self._events.append(event)
        if self._on_event:
            self._on_event(event)

    def _press(self, key, t):
        self._record("press", key, t)

    def _release(self, key, t):
        self._record("release", key, t)

    # ------------------------------------------------------------- sterowanie
    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", "custom")

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def keystrokes(self) -> int:
        with self._lock:
            return sum(1 for e in self._events if e["event"] == "press")

    def start(self):
        self._backend.start()

    def pause(self):
        self._recording = False

    def resume(self):
        self._recording = True

    def discard(self):
        """Czyści bufor (np. użytkownik przerwał tekst w połowie) — nasłuch trwa dalej."""
        with self._lock:
            self._events.clear()
            self._down.clear()

    def save(self, session_id: int = None) -> SessionResult:
        """
        Zapisuje zebrane zdarzenia jako sesję (domyślnie pod kolejnym wolnym numerem)
        i czyści bufor. Nasłuch trwa dalej — GUI może od razu zbierać kolejną sesję.
        Rzuca SessionTooShort; wtedy bufor zostaje nietknięty.
        """
        with self._lock:
            events = list(self._events)
        if len(events) < config.MIN_EVENTS:
            raise SessionTooShort(f"Za mało danych ({len(events)} zdarzeń, min. {config.MIN_EVENTS}).")
        result = save_session(self.store, self.profile, events, session_id)
        self.discard()
        return result

    def finish(self, save: bool = True, session_id: int = None) -> SessionResult:
        """Zatrzymuje nasłuch; przy save=True zapisuje sesję (patrz save())."""
        self._backend.stop()
        return self.save(session_id) if save else None


def save_session(store: ProfileStore, profile: str, events: list, session_id: int = None) -> SessionResult:
    """Liczy cechy i zapisuje parę plików raw/features pod kolejnym wolnym numerem."""
    out_dir = store.create(profile)
    sid = session_id if session_id is not None else store.next_session_id(profile)
    raw_path = out_dir / f"raw_session_{sid}.json"
    feat_path = out_dir / f"features_session_{sid}.json"
    if raw_path.exists() or feat_path.exists():
        raise FileExistsError(f"Sesja {sid} profilu '{profile}' już istnieje — nie nadpisuję.")

    features = extract_features(events)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    with open(feat_path, "w", encoding="utf-8") as f:
        json.dump(features, f, indent=2, ensure_ascii=False)
    return SessionResult(sid, raw_path, feat_path, features)
