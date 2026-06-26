"""
Zbiera surowe dane klawiatury i zapisuje do JSON
Wersja cross-platform:
  • Windows / macOS / Linux+X11  -> backend "pynput"
  • Linux + Wayland (i konsola)  -> backend "evdev" (czyta /dev/input/*)

Uruchom (Windows/macOS/X11):  python collector.py --user maks --session 1
Uruchom (Linux/Wayland):      sudo python collector.py --user maks --session 1
                              (albo dodaj usera do grupy 'input' i bez sudo)
Lista urządzeń (Linux):       python collector.py --list-devices
Wymuszenie backendu:          python collector.py --backend evdev
Zatrzymaj:                    wciśnij ESC
"""

import os
import sys
import time                   # do mierzenia czasu
import json                   # zapis/odczyt plikow JSON
import argparse               # obsluga argumentow z terminala
import platform               # wykrywanie systemu / sesji
import statistics             # gotowe funkcje stdev, median
from pathlib import Path      # praca ze sciezkami

# Struktury danych (wspólne dla obu backendów)
press_times: dict = {}
raw_events: list  = []

def record_press(key_str: str, t: float) -> None:
    press_times[key_str] = t
    raw_events.append({"event": "press", "key": key_str, "t": t})

def record_release(key_str: str, t: float) -> None:
    raw_events.append({"event": "release", "key": key_str, "t": t})


# BACKEND 1: pynput (Windows / macOS / Linux+X11) — działa jak oryginał
def run_pynput() -> None:
    try:
        from pynput import keyboard
    except ImportError:
        print("❌ Brak biblioteki 'pynput'. Zainstaluj:  pip install pynput")
        sys.exit(1)

    def on_press(key):
        record_press(str(key), time.perf_counter())

    def on_release(key):
        record_release(str(key), time.perf_counter())
        if key == keyboard.Key.esc:
            return False

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


# BACKEND 2: evdev (Linux/Wayland) — czyta surowe zdarzenia z jądra
def _perm_error() -> None:
    print("\n🔒 Brak uprawnień do odczytu /dev/input/* .")
    print("   Opcja A (szybko):    sudo python collector.py --user ... --session ...")
    print("   Opcja B (na stałe):  sudo usermod -aG input $USER   (potem wyloguj/zaloguj)")

def _build_evdev_keymap():
    """Mapuje kody klawiszy z evdev na format zgodny z pynput.

    Litery/cyfry/symbole zwracane są przez repr() znaku ('a' -> "'a'"),
    dokładnie jak robi to pynput. Klawisze specjalne -> "Key.xxx".
    Uwaga: evdev podaje FIZYCZNY klawisz (niezależnie od układu), więc
    znaki spoza układu US (np. polskie ąćęłńóśźż przez AltGr) trafią jako
    bazowy klawisz fizyczny — dla biometrii czasowej to nie problem.
    """
    from evdev import ecodes as ec

    letters = {getattr(ec, f"KEY_{c.upper()}"): c for c in "abcdefghijklmnopqrstuvwxyz"}
    digits = {
        ec.KEY_1: "1", ec.KEY_2: "2", ec.KEY_3: "3", ec.KEY_4: "4", ec.KEY_5: "5",
        ec.KEY_6: "6", ec.KEY_7: "7", ec.KEY_8: "8", ec.KEY_9: "9", ec.KEY_0: "0",
    }
    symbols = {
        ec.KEY_MINUS: "-", ec.KEY_EQUAL: "=",
        ec.KEY_LEFTBRACE: "[", ec.KEY_RIGHTBRACE: "]",
        ec.KEY_SEMICOLON: ";", ec.KEY_APOSTROPHE: "'",
        ec.KEY_GRAVE: "`", ec.KEY_BACKSLASH: "\\",
        ec.KEY_COMMA: ",", ec.KEY_DOT: ".", ec.KEY_SLASH: "/",
    }
    char_map = {**letters, **digits, **symbols}

    # Wersje z wciśniętym Shift (układ US)
    char_map_shift = {k: v.upper() for k, v in letters.items()}
    char_map_shift.update({
        ec.KEY_1: "!", ec.KEY_2: "@", ec.KEY_3: "#", ec.KEY_4: "$", ec.KEY_5: "%",
        ec.KEY_6: "^", ec.KEY_7: "&", ec.KEY_8: "*", ec.KEY_9: "(", ec.KEY_0: ")",
        ec.KEY_MINUS: "_", ec.KEY_EQUAL: "+",
        ec.KEY_LEFTBRACE: "{", ec.KEY_RIGHTBRACE: "}",
        ec.KEY_SEMICOLON: ":", ec.KEY_APOSTROPHE: '"',
        ec.KEY_GRAVE: "~", ec.KEY_BACKSLASH: "|",
        ec.KEY_COMMA: "<", ec.KEY_DOT: ">", ec.KEY_SLASH: "?",
    })

    special = {
        ec.KEY_SPACE: "Key.space",
        ec.KEY_ENTER: "Key.enter", ec.KEY_KPENTER: "Key.enter",
        ec.KEY_BACKSPACE: "Key.backspace",
        ec.KEY_TAB: "Key.tab",
        ec.KEY_ESC: "Key.esc",
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
    # Klawisze funkcyjne F1..F12
    for n in range(1, 13):
        special[getattr(ec, f"KEY_F{n}")] = f"Key.f{n}"

    return char_map, char_map_shift, special

def _code_to_str(code, shifted, char_map, char_map_shift, special) -> str:
    if code in special:
        return special[code]
    if shifted and code in char_map_shift:
        return repr(char_map_shift[code])     # repr() -> format jak w pynput
    if code in char_map:
        return repr(char_map[code])
    return f"<{code}>"                         # nieznany klawisz (jak pynput dla vk)

def _find_keyboards():
    """Wykrywa urządzenia będące klawiaturą (mają KEY_A, KEY_Z i spację)."""
    from evdev import InputDevice, list_devices, ecodes as ec
    kbs = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except (PermissionError, OSError):
            continue
        keys = dev.capabilities().get(ec.EV_KEY, [])
        if ec.KEY_A in keys and ec.KEY_Z in keys and ec.KEY_SPACE in keys:
            kbs.append(dev)
        else:
            dev.close()
    return kbs

def run_evdev(device_paths=None) -> None:
    try:
        from evdev import InputDevice, ecodes as ec
    except ImportError:
        print("❌ Brak biblioteki 'evdev'. Zainstaluj:  pip install evdev")
        sys.exit(1)
    import select

    char_map, char_map_shift, special = _build_evdev_keymap()

    # Wybór urządzeń
    if device_paths:
        devices = []
        for p in device_paths:
            try:
                devices.append(InputDevice(p))
            except PermissionError:
                _perm_error(); return
            except OSError as e:
                print(f"❌ Nie można otworzyć {p}: {e}"); return
    else:
        devices = _find_keyboards()

    if not devices:
        print("❌ Nie znaleziono klawiatury (albo brak uprawnień).")
        print("   Sprawdź:  python collector.py --list-devices")
        _perm_error()
        return

    print("🎧 Nasłuchuję na: " + ", ".join(f"{d.path} ({d.name})" for d in devices))

    dev_map = {d.fd: d for d in devices}
    shift_active = 0   # licznik aktualnie wciśniętych Shiftów (L/R)
    stop = False

    try:
        while not stop:
            r, _, _ = select.select(dev_map, [], [])
            for fd in r:
                for event in dev_map[fd].read():
                    if event.type != ec.EV_KEY:
                        continue
                    t = time.perf_counter()
                    code, val = event.code, event.value   # val: 1=down, 0=up, 2=repeat

                    is_shift = code in (ec.KEY_LEFTSHIFT, ec.KEY_RIGHTSHIFT)
                    key_str = _code_to_str(code, shift_active > 0,
                                           char_map, char_map_shift, special)

                    if val == 1:        # press
                        if is_shift:
                            shift_active += 1
                        record_press(key_str, t)
                    elif val == 0:      # release
                        if is_shift and shift_active > 0:
                            shift_active -= 1
                        record_release(key_str, t)
                        if code == ec.KEY_ESC:
                            stop = True
                            break
                    # val == 2 (auto-repeat) ignorujemy
                if stop:
                    break
    finally:
        for d in devices:
            d.close()

def list_devices_cmd() -> None:
    try:
        from evdev import InputDevice, list_devices
    except ImportError:
        print("❌ Brak biblioteki 'evdev'. Zainstaluj:  pip install evdev")
        return
    paths = list_devices()
    if not paths:
        print("Brak urządzeń wejściowych lub brak uprawnień.")
        _perm_error()
        return
    for p in paths:
        try:
            d = InputDevice(p)
            print(f"{p:22} {d.name}")
            d.close()
        except PermissionError:
            print(f"{p:22} (brak uprawnień)")


# Feature extraction (BEZ ZMIAN — niezależne od platformy)
def stats(data: list) -> dict:
    if not data:
        return {"mean": 0, "std": 0, "min": 0, "max": 0, "median": 0}
    return {
        "mean":   sum(data) / len(data),
        "std":    statistics.stdev(data) if len(data) > 1 else 0.0,
        "min":    min(data),
        "max":    max(data),
        "median": statistics.median(data),
    }

def extract_features(events: list) -> dict:
    presses  = [e for e in events if e["event"] == "press"]
    releases = [e for e in events if e["event"] == "release"]

    # Indeks release per klawisz (do dwell time)
    release_map: dict = {}
    for e in releases:
        release_map.setdefault(e["key"], []).append(e["t"])

    #Dwell time — jak długo klawisz wciśnięty
    dwell_times = []
    for e in presses:
        k = e["key"]
        if k in release_map and release_map[k]:
            dt = release_map[k].pop(0) - e["t"]
            if 0 < dt < 2.0:
                dwell_times.append(dt)

    #Flight time — od release jednego do press następnego
    flight_times = []
    for i in range(1, len(presses)):
        prev_key = presses[i-1]["key"]
        rels = [e["t"] for e in releases
                if e["key"] == prev_key and e["t"] > presses[i-1]["t"]]
        if rels:
            ft = presses[i]["t"] - min(rels)
            if -0.5 < ft < 3.0:
                flight_times.append(ft)

    #Inter-Key Interval — czas press -> press
    iki = []
    for i in range(1, len(presses)):
        delta = presses[i]["t"] - presses[i-1]["t"]
        if 0 < delta < 3.0:
            iki.append(delta)

    #Szybkosc pisania
    total_chars = len([e for e in presses if not e["key"].startswith("Key.")])
    duration = presses[-1]["t"] - presses[0]["t"] if len(presses) > 1 else 0.0
    active_time = sum(v for v in iki if v < 2.0)
    wpm = (total_chars / 5) / (active_time / 60) if active_time > 0 else 0.0
    cps = total_chars / active_time if active_time > 0 else 0.0

    #Pary klawiszy
    bigrams: dict = {}
    for i in range(1, len(presses)):
        pair = f"{presses[i-1]['key']}|{presses[i]['key']}"
        delta = presses[i]["t"] - presses[i-1]["t"]
        if 0 < delta < 1.5:
            bigrams.setdefault(pair, []).append(delta)
    bigram_means = {k: sum(v)/len(v) for k, v in bigrams.items() if len(v) >= 3}

    #Najczesciej klikane klawisze
    freq: dict = {}
    for e in presses:
        freq[e["key"]] = freq.get(e["key"], 0) + 1
    top_keys = dict(sorted(freq.items(), key=lambda x: x[1], reverse=True)[:20])

    #Error rate — ile razy Backspace vs ile znakow
    backspace_count = freq.get("Key.backspace", 0)
    error_rate = backspace_count / total_chars if total_chars > 0 else 0.0

    #Burst patterns — serie szybkich klawiszy < 150ms
    burst_lengths = []
    current_burst = 1
    for i in range(1, len(iki)):
        if iki[i] < 0.15:
            current_burst += 1
        else:
            if current_burst > 2:
                burst_lengths.append(current_burst)
            current_burst = 1
    avg_burst = sum(burst_lengths) / len(burst_lengths) if burst_lengths else 0.0

    #Shift ratio — jak często używasz Shift
    shift_count = freq.get("Key.shift", 0) + freq.get("Key.shift_r", 0)
    shift_ratio = shift_count / total_chars if total_chars > 0 else 0.0

    return {
        "meta": {
            "total_keystrokes": len(presses),
            "total_chars":      total_chars,
            "session_duration": round(duration, 3),
        },
        "dwell_time":    stats(dwell_times),
        "flight_time":   stats(flight_times),
        "iki":           stats(iki),
        "typing_speed": {
            "wpm": round(wpm, 2),
            "cps": round(cps, 4),
        },
        "error_rate":    round(error_rate, 4),
        "avg_burst_len": round(avg_burst, 4),
        "shift_ratio":   round(shift_ratio, 4),
        "top_keys":      top_keys,
        "bigram_means":  bigram_means,
    }


# Wybór backendu
def choose_backend(force: str) -> str:
    if force != "auto":
        return force
    if platform.system() != "Linux":
        return "pynput"
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or session == "wayland"
    if wayland:
        return "evdev"                      # pynput nie dostaje klawiszy pod Wayland
    if session == "x11" or os.environ.get("DISPLAY"):
        return "pynput"                     # pod X11 pynput działa bez roota
    return "evdev"                          # konsola / brak serwera wyświetlania


# main loop
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user",    default="default", help="Nazwa użytkownika")
    parser.add_argument("--session", default="1",       help="Numer sesji")
    parser.add_argument("--backend", default="auto",
                        choices=["auto", "pynput", "evdev"],
                        help="Wymuś backend (domyślnie auto-wykrywanie)")
    parser.add_argument("--device", action="append",
                        help="Ścieżka /dev/input/eventX (Linux; można podać wielokrotnie)")
    parser.add_argument("--list-devices", action="store_true",
                        help="Wypisz urządzenia wejściowe i zakończ (Linux)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices_cmd()
        return

    out_dir = Path("data") / args.user
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = choose_backend(args.backend)
    print(f"🎹 Użytkownik: {args.user} | Sesja: {args.session} | Backend: {backend}")
    print("📝 Pisz cokolwiek... Wciśnij ESC aby zakończyć.\n")

    if backend == "evdev":
        run_evdev(args.device)
    else:
        run_pynput()

    if len(raw_events) < 20:
        print("⚠️  Za mało danych. Pisz dłużej następnym razem.")
        return

    features = extract_features(raw_events)

    raw_path  = out_dir / f"raw_session_{args.session}.json"
    feat_path = out_dir / f"features_session_{args.session}.json"

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_events, f, indent=2, ensure_ascii=False)

    with open(feat_path, "w", encoding="utf-8") as f:
        json.dump(features, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Sesja zakończona!")
    print(f"   Klawiszy:     {features['meta']['total_keystrokes']}")
    print(f"   Czas sesji:   {features['meta']['session_duration']:.1f}s")
    print(f"   Typing speed: {features['typing_speed']['wpm']:.1f} WPM")
    print(f"   Dwell time:   {features['dwell_time']['mean']*1000:.1f} ms (avg)")
    print(f"   Flight time:  {features['flight_time']['mean']*1000:.1f} ms (avg)")
    print(f"   Error rate:   {features['error_rate']*100:.1f}%")
    print(f"\n💾 Zapisano: {feat_path}")

if __name__ == "__main__":
    main()
