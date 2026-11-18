"""Zbiera i zapisuje jedną sesję klawiatury."""

import threading

from authtrace import config
from authtrace.backends import create_backend
from authtrace.features import extract_features
from database import save_session as db_save_session, save_user


class SessionResult:
    def __init__(self, session_id: int, features: dict):
        self.session_id = session_id
        self.features = features


class SessionTooShort(Exception):
    """Za mało zdarzeń, żeby zapisać sesję."""


class CollectorSession:
    def __init__(self, profile: str, backend="auto", devices=None, on_event=None):
        """backend może być nazwą albo fabryką backendu używaną w testach."""
        self.profile = profile
        self.user_id = save_user(profile)
        self._on_event = on_event
        self._events = []
        self._down = set()
        self._lock = threading.Lock()
        self._recording = True
        self.keystrokes = 0
        if callable(backend):
            self._backend = backend(self._press, self._release)
        else:
            self._backend = create_backend(backend, self._press, self._release, devices)
        self.backend_name = getattr(self._backend, "name", "custom")

    # ------------------------------------------------ callbacki z wątku backendu
    def _record(self, kind: str, key: str, t: float):
        if not self._recording:
            return
        event = {"event": kind, "key": key, "t": t}
        with self._lock:
            if kind == "press":
                self._down.add(key)
                self.keystrokes += 1
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
    def get_event_count(self):
        return len(self._events)

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
            self.keystrokes = 0

    def save(self, session_id = None):
        """Zapisuje sesję i czyści bufor. Nasłuch może działać dalej."""
        with self._lock:
            events = list(self._events)
        if len(events) < config.MIN_EVENTS:
            raise SessionTooShort(f"Za mało danych ({len(events)} zdarzeń, min. {config.MIN_EVENTS}).")

        features = extract_features(events)
        if session_id is None:
            from database import get_next_session_number
            session_id = get_next_session_number(self.user_id)

        db_session_id = db_save_session(self.user_id, session_id, events, features)
        self.discard()
        return SessionResult(db_session_id, features)

    def finish(self, save: bool = True, session_id: int = None) -> SessionResult:
        """Zatrzymuje nasłuch; przy save=True zapisuje sesję (patrz save())."""
        self._backend.stop()
        return self.save(session_id) if save else None
