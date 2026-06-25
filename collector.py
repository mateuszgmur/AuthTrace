"""
collector.py — Zbiera surowe dane klawiatury i zapisuje do JSON
Uruchom: python collector.py --user mateusz --session 1
Zatrzymaj: wcisnij ESC
"""

import time
import json
import argparse
import statistics
from pathlib import Path
from pynput import keyboard

press_times: dict = {}
raw_events: list  = []

def on_press(key):
    key_str = str(key)
    t = time.perf_counter()
    press_times[key_str] = t
    raw_events.append({"event": "press", "key": key_str, "t": t})

def on_release(key):
    key_str = str(key)
    t = time.perf_counter()
    raw_events.append({"event": "release", "key": key_str, "t": t})
    if key == keyboard.Key.esc:
        return False

def remove_outliers_iqr(data: list, k: float = 1.5) -> list:
    if len(data) < 8:
        return data  # za mało próbek — zwróć bez zmian
    q1 = statistics.quantiles(data, n=4)[0]
    q3 = statistics.quantiles(data, n=4)[2]
    iqr = q3 - q1
    low  = q1 - k * iqr
    high = q3 + k * iqr
    cleaned = [x for x in data if low <= x <= high]
    return cleaned if cleaned else data

def stats(data: list) -> dict:
    if not data:
        return {"mean": 0, "std": 0, "min": 0, "max": 0, "median": 0, "count": 0, "outliers_removed": 0}
    cleaned = remove_outliers_iqr(data)
    return {
        "mean":             round(sum(cleaned) / len(cleaned), 6),
        "std":              round(statistics.stdev(cleaned), 6) if len(cleaned) > 1 else 0.0,
        "min":              round(min(cleaned), 6),
        "max":              round(max(cleaned), 6),
        "median":           round(statistics.median(cleaned), 6),
        "count":            len(cleaned),
        "outliers_removed": len(data) - len(cleaned),
    }

def is_char_key(key_str: str) -> bool:
    if key_str.startswith("Key."):
        return False
    if key_str.startswith("<") and key_str.endswith(">"):
        return False
    return True

def bigram_mean(data: list) -> float:
    cleaned = remove_outliers_iqr(data)
    return round(sum(cleaned) / len(cleaned), 6)

def extract_features(events: list) -> dict:
    presses  = [e for e in events if e["event"] == "press"]
    releases = [e for e in events if e["event"] == "release"]

    release_map: dict = {}
    for e in releases:
        release_map.setdefault(e["key"], []).append(e["t"])

    # ---- Dwell time globalny ----
    release_map_copy = {k: list(v) for k, v in release_map.items()}
    dwell_times = []
    for e in presses:
        k = e["key"]
        if k in release_map_copy and release_map_copy[k]:
            dt = release_map_copy[k].pop(0) - e["t"]
            if 0 < dt < 2.0:
                dwell_times.append(dt)

    # ---- Dwell time dla klawiszy specjalnych ----
    SPECIAL_KEYS = {
        "Key.shift":     "shift_left",
        "Key.shift_r":   "shift_right",
        "Key.space":     "space",
        "Key.enter":     "enter",
        "Key.backspace": "backspace",
        "Key.alt":       "alt_left",
        "Key.alt_r":     "alt_right",
    }

    special_dwell_raw: dict = {name: [] for name in SPECIAL_KEYS.values()}
    special_press_count: dict = {name: 0 for name in SPECIAL_KEYS.values()}

    release_map_special = {k: list(v) for k, v in release_map.items()}
    for e in presses:
        k = e["key"]
        if k in SPECIAL_KEYS:
            name = SPECIAL_KEYS[k]
            special_press_count[name] += 1
            if k in release_map_special and release_map_special[k]:
                dt = release_map_special[k].pop(0) - e["t"]
                if 0 < dt < 2.0:
                    special_dwell_raw[name].append(dt)

    special_keys_stats = {
        name: {
            "dwell": stats(special_dwell_raw[name]),
            "count": special_press_count[name],
        }
        for name in SPECIAL_KEYS.values()
    }

    # ---- Flight time globalny ----
    flight_times = []
    for i in range(1, len(presses)):
        prev_key = presses[i-1]["key"]
        rels = [e["t"] for e in releases
                if e["key"] == prev_key and e["t"] > presses[i-1]["t"]]
        if rels:
            ft = presses[i]["t"] - min(rels)
            if -0.5 < ft < 3.0:
                flight_times.append(ft)

    # ---- IKI ----
    iki = []
    for i in range(1, len(presses)):
        delta = presses[i]["t"] - presses[i-1]["t"]
        if 0 < delta < 3.0:
            iki.append(delta)

    # ---- Szybkość pisania ----
    total_chars = len([e for e in presses if is_char_key(e["key"])])
    duration = presses[-1]["t"] - presses[0]["t"] if len(presses) > 1 else 0.0
    active_time = sum(v for v in iki if v < 2.0)
    wpm = (total_chars / 5) / (active_time / 60) if active_time > 0 else 0.0
    cps = total_chars / active_time if active_time > 0 else 0.0

    # ---- Bigrams: KK i RK ----
    # zbieramy od >= 4 próbek, IQR działa automatycznie tylko gdy >= 8
    bigrams: dict = {}
    for i in range(1, len(presses)):
        pair = f"{presses[i-1]['key']}|{presses[i]['key']}"
        kk = presses[i]["t"] - presses[i-1]["t"]
        prev_key = presses[i-1]["key"]
        rels = [e["t"] for e in releases
                if e["key"] == prev_key and e["t"] > presses[i-1]["t"]]
        rk = presses[i]["t"] - min(rels) if rels else None
        if 0 < kk < 1.5:
            entry = bigrams.setdefault(pair, {"kk": [], "rk": []})
            entry["kk"].append(kk)
            if rk is not None and -0.3 < rk < 1.5:
                entry["rk"].append(rk)

    bigram_stats = {
        k: {
            "kk_mean":     bigram_mean(v["kk"]),
            "kk_count":    len(remove_outliers_iqr(v["kk"])),
            "kk_outliers": len(v["kk"]) - len(remove_outliers_iqr(v["kk"])),
            "rk_mean":     bigram_mean(v["rk"]) if v["rk"] else None,
            "rk_count":    len(remove_outliers_iqr(v["rk"])) if v["rk"] else 0,
            "rk_outliers": len(v["rk"]) - len(remove_outliers_iqr(v["rk"])) if v["rk"] else 0,
        }
        for k, v in bigrams.items() if len(v["kk"]) >= 4  # zbieramy od 4, IQR wewnątrz sam pilnuje progu 8
    }

    # ---- Top keys ----
    freq: dict = {}
    for e in presses:
        freq[e["key"]] = freq.get(e["key"], 0) + 1
    top_keys = dict(sorted(freq.items(), key=lambda x: x[1], reverse=True)[:20])

    # ---- Error rate ----
    backspace_count = freq.get("Key.backspace", 0)
    error_rate = backspace_count / total_chars if total_chars > 0 else 0.0

    # ---- Burst patterns ----
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

    # ---- Shift ratio ----
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
        "special_keys":  special_keys_stats,
        "top_keys":      top_keys,
        "bigram_stats":  bigram_stats,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user",    default="default", help="Nazwa użytkownika")
    parser.add_argument("--session", default="1",       help="Numer sesji")
    args = parser.parse_args()

    out_dir = Path("data") / args.user
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"🎹 Użytkownik: {args.user} | Sesja: {args.session}")
    print("📝 Pisz cokolwiek... Wciśnij ESC aby zakończyć.\n")

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

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

    sk = features["special_keys"]
    print(f"\n✅ Sesja zakończona!")
    print(f"   Klawiszy:       {features['meta']['total_keystrokes']}")
    print(f"   Czas sesji:     {features['meta']['session_duration']:.1f}s")
    print(f"   Typing speed:   {features['typing_speed']['wpm']:.1f} WPM")
    print(f"   Dwell time:     {features['dwell_time']['mean']*1000:.1f} ms (avg, outliers={features['dwell_time']['outliers_removed']})")
    print(f"   Flight time:    {features['flight_time']['mean']*1000:.1f} ms (avg, outliers={features['flight_time']['outliers_removed']})")
    print(f"   IKI:            {features['iki']['mean']*1000:.1f} ms (avg, outliers={features['iki']['outliers_removed']})")
    print(f"   Error rate:     {features['error_rate']*100:.1f}%")
    print(f"   Bigram par:     {len(features['bigram_stats'])} unikalnych par (>=4 próbek, IQR od 8)")
    print(f"\n   --- Klawisze specjalne ---")
    for name, data in sk.items():
        dwell_ms = data['dwell']['mean'] * 1000 if data['dwell']['count'] > 0 else 0
        outliers = data['dwell']['outliers_removed']
        print(f"   {name:<14} count={data['count']:<5} dwell_avg={dwell_ms:.1f} ms  (outliers={outliers})")
    print(f"\n💾 Zapisano: {feat_path}")

if __name__ == "__main__":
    main()