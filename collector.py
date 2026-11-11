"""
collector.py — tryb konsolowy zbierania danych (bez GUI).

Główny sposób zbierania to teraz `python main.py` (typeracer + collector).
Ten skrypt zostaje do sesji "swobodnego pisania" w dowolnym programie.

    python collector.py --user mateusz            # numer sesji nadawany automatycznie
    python collector.py --user mateusz --session 7
    python collector.py --backend evdev           # wymuszenie backendu (Linux/Wayland)
    python collector.py --list-devices            # urządzenia evdev (Linux)
    python collector.py --reextract [--user X]    # przelicz features_*.json z raw_*.json

Zatrzymanie sesji: ESC.
"""

import argparse
import json
import sys
import threading

from authtrace import config
from authtrace.backends import BackendError, list_devices
from authtrace.features import extract_features
from authtrace.profiles import ProfileStore
from authtrace.session import CollectorSession, SessionTooShort


def print_summary(features: dict, path) -> None:
    f = features
    print("\n✅ Sesja zakończona!")
    print(f"   Klawiszy:       {f['meta']['total_keystrokes']}")
    print(f"   Czas sesji:     {f['meta']['session_duration']:.1f}s")
    print(f"   Typing speed:   {f['typing_speed']['wpm']:.1f} WPM")
    for label, key in (("Dwell time", "dwell_time"), ("Flight time", "flight_time"), ("IKI", "iki")):
        print(f"   {label + ':':<15} {f[key]['mean'] * 1000:.1f} ms "
              f"(avg, outliers={f[key]['outliers_removed']})")
    print(f"   Error rate:     {f['error_rate'] * 100:.1f}%")
    print(f"   Bigram par:     {len(f['bigram_stats'])} unikalnych par "
          f"(>={config.BIGRAM_MIN_SAMPLES} próbek, IQR od {config.IQR_MIN_SAMPLES})")
    print("\n   --- Klawisze specjalne ---")
    for name, d in f["special_keys"].items():
        print(f"   {name:<14} count={d['count']:<5} dwell_avg={d['dwell']['mean'] * 1000:.1f} ms"
              f"  (outliers={d['dwell']['outliers_removed']})")
    print(f"\n💾 Zapisano: {path}")


def record(args) -> int:
    store = ProfileStore()
    if args.session is not None and args.session in store.session_ids(args.user):
        print(f"❌ Sesja {args.session} profilu '{args.user}' już istnieje. "
              f"Pomiń --session, aby użyć kolejnego numeru ({store.next_session_id(args.user)}).")
        return 1

    esc_released = threading.Event()

    def on_event(e):
        if e["event"] == "release" and e["key"] == "Key.esc":
            esc_released.set()

    session = CollectorSession(args.user, backend=args.backend, devices=args.device,
                               store=store, on_event=on_event)
    try:
        session.start()
    except BackendError as e:
        print(f"❌ {e}")
        return 1

    print(f"🎹 Użytkownik: {args.user} | Backend: {session.backend_name}")
    print("📝 Pisz cokolwiek... Wciśnij ESC aby zakończyć.\n")
    try:
        esc_released.wait()
    except KeyboardInterrupt:
        print("\n(przerwano Ctrl+C — zapisuję to, co zebrano)")

    try:
        result = session.finish(session_id=args.session)
    except SessionTooShort:
        print("⚠️  Za mało danych. Pisz dłużej następnym razem.")
        return 1
    print(f"   Sesja nr:       {result.session_id}")
    print_summary(result.features, result.features_path)
    return 0


def reextract(args) -> int:
    """Przelicza cechy z surowych zdarzeń — ujednolica pliki zapisane różnymi wersjami collectora."""
    store = ProfileStore()
    users = [args.user] if args.user else store.names()
    count = 0
    for user in users:
        for raw in sorted(store.path(user).glob("raw_session_*.json")):
            feat = raw.with_name(raw.name.replace("raw_", "features_"))
            with open(raw, encoding="utf-8") as f:
                features = extract_features(json.load(f))
            with open(feat, "w", encoding="utf-8") as f:
                json.dump(features, f, indent=2, ensure_ascii=False)
            count += 1
            print(f"   ♻️  {user}/{feat.name}")
    print(f"\nPrzeliczono {count} sesji. Po tej operacji wytrenuj modele ponownie (train.py).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="AuthTrace — zbieranie danych z klawiatury (CLI)")
    p.add_argument("--user", default=None, help="Nazwa profilu (katalog w data/)")
    p.add_argument("--session", type=int, default=None,
                   help="Numer sesji (domyślnie kolejny wolny)")
    p.add_argument("--backend", default="auto", choices=["auto", "pynput", "evdev"])
    p.add_argument("--device", action="append",
                   help="Ścieżka /dev/input/eventX (evdev; można podać kilka razy)")
    p.add_argument("--list-devices", action="store_true", help="Wypisz urządzenia evdev")
    p.add_argument("--reextract", action="store_true",
                   help="Przelicz features_session_*.json z raw_session_*.json")
    args = p.parse_args()

    if args.list_devices:
        try:
            for path, name in list_devices():
                print(f"{path:22} {name}")
        except BackendError as e:
            print(f"❌ {e}")
            return 1
        return 0
    if args.reextract:
        return reextract(args)

    args.user = args.user or "default"
    if not ProfileStore.is_valid_name(args.user):
        print("❌ Nazwa profilu: litery, cyfry, '_' lub '-' (bez spacji).")
        return 1
    return record(args)


if __name__ == "__main__":
    sys.exit(main())
