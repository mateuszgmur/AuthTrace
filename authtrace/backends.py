"""
Źródła zdarzeń klawiatury (backendy).

Oba backendy mają ten sam, NIEBLOKUJĄCY interfejs:

    backend = create_backend("auto", on_press, on_release)
    backend.start()   # nasłuch w osobnym wątku — nie blokuje GUI ani CLI
    ...
    backend.stop()

on_press / on_release dostają (key_str, t), gdzie key_str ma format pynput
("'a'", "Key.space", "<84>"), a t = time.perf_counter().

  • pynput  — Windows / macOS / Linux+X11
  • evdev   — Linux + Wayland (i konsola); czyta /dev/input/*, wymaga grupy 'input' lub roota
"""

import os
import platform
import select
import threading
import time


def choose_backend(force: str = "auto") -> str:
    """Wybiera backend dla bieżącego systemu (logika przeniesiona z collectorwayland.py)."""
    if force != "auto":
        return force
    if platform.system() != "Linux":
        return "pynput"
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if os.environ.get("WAYLAND_DISPLAY") or session == "wayland":
        return "evdev"          # pod Wayland pynput nie dostaje klawiszy z innych okien
    if session == "x11" or os.environ.get("DISPLAY"):
        return "pynput"
    return "evdev"              # konsola / brak serwera wyświetlania


def create_backend(name: str, on_press, on_release, devices=None):
    name = choose_backend(name)
    if name == "pynput":
        return PynputBackend(on_press, on_release)
    if name == "evdev":
        return EvdevBackend(on_press, on_release, devices)
    raise ValueError(f"Nieznany backend: {name}")


class BackendError(RuntimeError):
    """Backend nie może wystartować (brak biblioteki, uprawnień, urządzenia)."""


# ===================================================================== pynput
def _physical_id(key):
    """Kod fizycznego klawisza (vk) z obiektu pynput: KeyCode.vk albo Key.value.vk."""
    vk = getattr(key, "vk", None)
    if vk is None:
        vk = getattr(getattr(key, "value", None), "vk", None)
    return vk


class PynputBackend:
    name = "pynput"

    def __init__(self, on_press, on_release):
        self._on_press, self._on_release = on_press, on_release
        self._listener = None
        self._held = {}   # vk -> nazwa zapisana przy press

    def _press(self, key):
        t = time.perf_counter()
        name = str(key)
        vk = _physical_id(key)
        if vk is not None:
            self._held[vk] = name
        self._on_press(name, t)

    def _release(self, key):
        t = time.perf_counter()
        # Release dostaje TĘ SAMĄ nazwę co press. pynput wylicza znak w chwili zdarzenia,
        # więc przy AltGr+L press = 'ł', ale release (po puszczeniu AltGr) = 'l'; tak samo
        # Shift+A -> 'A' / 'a'. Bez tego dwell polskich liter był gubiony lub źle parowany.
        vk = _physical_id(key)
        name = self._held.pop(vk, None) if vk is not None else None
        self._on_release(name or str(key), t)

    def start(self):
        try:
            from pynput import keyboard
        except ImportError as e:
            raise BackendError("Brak biblioteki 'pynput'. Zainstaluj: pip install pynput") from e
        self._held.clear()
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None


# ====================================================================== evdev
PERMISSION_HINT = (
    "Brak uprawnień do /dev/input/*. Dodaj użytkownika do grupy 'input':\n"
    "    sudo usermod -aG input $USER   (potem wyloguj się i zaloguj)"
)


def _build_evdev_keymap():
    """
    Mapuje kody evdev na nazwy w formacie pynput (bez zmian względem collectorwayland.py).
    evdev podaje FIZYCZNY klawisz (układ US) — polskie znaki przez AltGr trafią jako
    Key.alt_gr + bazowa litera; dla biometrii czasowej to wystarcza.
    """
    from evdev import ecodes as ec

    letters = {getattr(ec, f"KEY_{c.upper()}"): c for c in "abcdefghijklmnopqrstuvwxyz"}
    digits = {getattr(ec, f"KEY_{d}"): d for d in "1234567890"}
    symbols = {
        ec.KEY_MINUS: "-", ec.KEY_EQUAL: "=", ec.KEY_LEFTBRACE: "[", ec.KEY_RIGHTBRACE: "]",
        ec.KEY_SEMICOLON: ";", ec.KEY_APOSTROPHE: "'", ec.KEY_GRAVE: "`",
        ec.KEY_BACKSLASH: "\\", ec.KEY_COMMA: ",", ec.KEY_DOT: ".", ec.KEY_SLASH: "/",
    }
    char_map = {**letters, **digits, **symbols}

    shifted = {k: v.upper() for k, v in letters.items()}
    shifted.update(zip([getattr(ec, f"KEY_{d}") for d in "1234567890"], "!@#$%^&*()"))
    shifted.update({
        ec.KEY_MINUS: "_", ec.KEY_EQUAL: "+", ec.KEY_LEFTBRACE: "{", ec.KEY_RIGHTBRACE: "}",
        ec.KEY_SEMICOLON: ":", ec.KEY_APOSTROPHE: '"', ec.KEY_GRAVE: "~",
        ec.KEY_BACKSLASH: "|", ec.KEY_COMMA: "<", ec.KEY_DOT: ">", ec.KEY_SLASH: "?",
    })

    special = {
        ec.KEY_SPACE: "Key.space", ec.KEY_ENTER: "Key.enter", ec.KEY_KPENTER: "Key.enter",
        ec.KEY_BACKSPACE: "Key.backspace", ec.KEY_TAB: "Key.tab", ec.KEY_ESC: "Key.esc",
        ec.KEY_LEFTSHIFT: "Key.shift", ec.KEY_RIGHTSHIFT: "Key.shift_r",
        ec.KEY_LEFTCTRL: "Key.ctrl", ec.KEY_RIGHTCTRL: "Key.ctrl_r",
        ec.KEY_LEFTALT: "Key.alt", ec.KEY_RIGHTALT: "Key.alt_gr",
        ec.KEY_LEFTMETA: "Key.cmd", ec.KEY_RIGHTMETA: "Key.cmd_r",
        ec.KEY_CAPSLOCK: "Key.caps_lock",
        ec.KEY_UP: "Key.up", ec.KEY_DOWN: "Key.down",
        ec.KEY_LEFT: "Key.left", ec.KEY_RIGHT: "Key.right",
        ec.KEY_HOME: "Key.home", ec.KEY_END: "Key.end",
        ec.KEY_PAGEUP: "Key.page_up", ec.KEY_PAGEDOWN: "Key.page_down",
        ec.KEY_INSERT: "Key.insert", ec.KEY_DELETE: "Key.delete",
    }
    for n in range(1, 13):
        special[getattr(ec, f"KEY_F{n}")] = f"Key.f{n}"
    return char_map, shifted, special


def find_keyboards():
    """Urządzenia, które wyglądają na klawiaturę (mają KEY_A, KEY_Z i spację)."""
    from evdev import InputDevice, list_devices, ecodes as ec
    kbs = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue
        keys = dev.capabilities().get(ec.EV_KEY, [])
        if ec.KEY_A in keys and ec.KEY_Z in keys and ec.KEY_SPACE in keys:
            kbs.append(dev)
        else:
            dev.close()
    return kbs


def list_devices():
    """[(ścieżka, nazwa)] wszystkich urządzeń wejściowych — dla `collector.py --list-devices`."""
    try:
        from evdev import InputDevice, list_devices as _list
    except ImportError as e:
        raise BackendError("Brak biblioteki 'evdev'. Zainstaluj: pip install evdev") from e
    out = []
    for p in _list():
        try:
            d = InputDevice(p)
            out.append((p, d.name))
            d.close()
        except PermissionError:
            out.append((p, "(brak uprawnień)"))
    return out


class EvdevBackend:
    name = "evdev"
    POLL_TIMEOUT = 0.2   # co tyle sekund wątek sprawdza, czy ma się zatrzymać

    def __init__(self, on_press, on_release, device_paths=None):
        self._on_press, self._on_release = on_press, on_release
        self._device_paths = device_paths
        self._devices = []
        self._stop = threading.Event()
        self._thread = None
        self.device_names = []

    def start(self):
        try:
            from evdev import InputDevice, ecodes
        except ImportError as e:
            raise BackendError("Brak biblioteki 'evdev'. Zainstaluj: pip install evdev") from e
        self._ec = ecodes
        try:
            if self._device_paths:
                self._devices = [InputDevice(p) for p in self._device_paths]
            else:
                self._devices = find_keyboards()
        except PermissionError as e:
            raise BackendError(PERMISSION_HINT) from e
        except OSError as e:
            raise BackendError(f"Nie można otworzyć urządzenia: {e}") from e
        if not self._devices:
            raise BackendError("Nie znaleziono klawiatury.\n" + PERMISSION_HINT)

        self.device_names = [f"{d.path} ({d.name})" for d in self._devices]
        self._maps = _build_evdev_keymap()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="evdev-listener", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        for d in self._devices:
            d.close()
        self._devices = []

    def _key_str(self, code, shifted):
        char_map, shift_map, special = self._maps
        if code in special:
            return special[code]
        if shifted and code in shift_map:
            return repr(shift_map[code])   # repr() -> "'A'", jak w pynput
        if code in char_map:
            return repr(char_map[code])
        return f"<{code}>"

    def _loop(self):
        ec = self._ec
        dev_map = {d.fd: d for d in self._devices}
        shift_down = 0   # ile Shiftów (L/R) jest teraz wciśniętych
        held = {}        # kod -> nazwa z press (release dostaje tę samą nazwę, jak w pynput)
        while not self._stop.is_set():
            # timeout zamiast blokującego select() — inaczej stop() nie mógłby przerwać wątku
            ready, _, _ = select.select(dev_map, [], [], self.POLL_TIMEOUT)
            for fd in ready:
                try:
                    events = list(dev_map[fd].read())
                except OSError:      # urządzenie odłączone
                    continue
                for ev in events:
                    if ev.type != ec.EV_KEY or ev.value == 2:   # 2 = auto-repeat
                        continue
                    t = time.perf_counter()
                    is_shift = ev.code in (ec.KEY_LEFTSHIFT, ec.KEY_RIGHTSHIFT)
                    if ev.value == 1:
                        key = self._key_str(ev.code, shift_down > 0)
                        held[ev.code] = key
                        shift_down += is_shift
                        self._on_press(key, t)
                    else:
                        key = held.pop(ev.code, None) or self._key_str(ev.code, shift_down > 0)
                        shift_down = max(0, shift_down - is_shift)
                        self._on_release(key, t)
