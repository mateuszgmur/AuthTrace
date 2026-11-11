"""
Ekstrakcja cech z surowych zdarzeń klawiatury.

Wejście: lista zdarzeń {"event": "press"|"release", "key": str, "t": float}
Wyjście: słownik cech zapisywany jako features_session_N.json i czytany przez train.py.

To jest JEDYNA implementacja ekstrakcji w projekcie (wcześniej collector.py
i collectorwayland.py miały dwie różne wersje, co dawało niezgodne pliki cech).
Algorytm jest przeniesiony 1:1 z collector.py — wyniki na tych samych danych
są identyczne (poza poprawką mapowania Key.alt_gr, patrz config.SPECIAL_KEYS).
"""

import statistics
from bisect import bisect_right
from collections import Counter, deque

from authtrace import config as C


# ---------------------------------------------------------------- statystyki
def remove_outliers_iqr(data: list, k: float = C.IQR_K) -> list:
    """Odrzuca wartości spoza [Q1 - k*IQR, Q3 + k*IQR]. Przy < 8 próbkach nic nie robi."""
    if len(data) < C.IQR_MIN_SAMPLES:
        return data
    q1, _, q3 = statistics.quantiles(data, n=4)
    iqr = q3 - q1
    low, high = q1 - k * iqr, q3 + k * iqr
    cleaned = [x for x in data if low <= x <= high]
    return cleaned if cleaned else data


def describe(data: list) -> dict:
    """mean/std/min/max/median po odrzuceniu outlierów + ile próbek zostało/odrzucono."""
    if not data:
        return {"mean": 0, "std": 0, "min": 0, "max": 0, "median": 0,
                "count": 0, "outliers_removed": 0}
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


def _mean_cleaned(data: list):
    """(średnia po IQR, liczba próbek po IQR, liczba odrzuconych) — albo (None, 0, 0)."""
    if not data:
        return None, 0, 0
    cleaned = remove_outliers_iqr(data)
    return round(sum(cleaned) / len(cleaned), 6), len(cleaned), len(data) - len(cleaned)


def is_char_key(key_str: str) -> bool:
    """True dla klawiszy znakowych ('a', 'ą', '1'); False dla Key.xxx i nieznanych <vk>."""
    if key_str.startswith("Key."):
        return False
    if key_str.startswith("<") and key_str.endswith(">"):
        return False
    return True


# ---------------------------------------------------------------- dopasowania
def _dwell_per_press(presses: list, releases: list) -> list:
    """
    Dla każdego press zwraca czas trzymania (release - press) albo None.
    Parowanie FIFO per klawisz: n-ty press klawisza X z n-tym release klawisza X
    (dokładnie tak jak w poprzedniej wersji, liczone raz zamiast dwa razy).
    """
    queues: dict = {}
    for e in releases:
        queues.setdefault(e["key"], deque()).append(e["t"])
    out = []
    for e in presses:
        q = queues.get(e["key"])
        out.append(q.popleft() - e["t"] if q else None)
    return out


def _release_after_lookup(releases: list):
    """
    Zwraca funkcję f(key, t) -> czas PIERWSZEGO release klawisza `key` po chwili `t`.
    Zastępuje wcześniejsze przeszukiwanie całej listy releases dla każdego press
    (O(n²), liczone dwa razy) wyszukiwaniem binarnym (O(n log n)). Wynik ten sam:
    min(t_rel > t) == pierwszy element posortowanej listy większy od t.
    """
    by_key: dict = {}
    for e in releases:
        by_key.setdefault(e["key"], []).append(e["t"])
    for times in by_key.values():
        times.sort()

    def first_after(key: str, t: float):
        times = by_key.get(key)
        if not times:
            return None
        i = bisect_right(times, t)
        return times[i] if i < len(times) else None

    return first_after


# ---------------------------------------------------------------- główna funkcja
def extract_features(events: list) -> dict:
    presses = [e for e in events if e["event"] == "press"]
    releases = [e for e in events if e["event"] == "release"]
    release_after = _release_after_lookup(releases)

    # ---- Dwell time: globalny i dla klawiszy specjalnych (jedno przejście) ----
    dwell_times = []
    special_dwell = {name: [] for name in C.SPECIAL_KEYS.values()}
    special_count = {name: 0 for name in C.SPECIAL_KEYS.values()}
    for e, dt in zip(presses, _dwell_per_press(presses, releases)):
        ok = dt is not None and 0 < dt < C.DWELL_MAX
        if ok:
            dwell_times.append(dt)
        name = C.SPECIAL_KEYS.get(e["key"])
        if name:
            special_count[name] += 1
            if ok:
                special_dwell[name].append(dt)

    special_keys_stats = {
        name: {"dwell": describe(special_dwell[name]), "count": special_count[name]}
        for name in special_dwell
    }

    # ---- Pary kolejnych press: flight time, IKI, bigramy ----
    flight_times, iki = [], []
    bigrams: dict = {}
    for prev, cur in zip(presses, presses[1:]):
        rel = release_after(prev["key"], prev["t"])   # puszczenie poprzedniego klawisza
        kk = cur["t"] - prev["t"]                      # press -> press
        rk = cur["t"] - rel if rel is not None else None  # release -> press

        if rk is not None and C.FLIGHT_RANGE[0] < rk < C.FLIGHT_RANGE[1]:
            flight_times.append(rk)
        if 0 < kk < C.IKI_MAX:
            iki.append(kk)
        if 0 < kk < C.BIGRAM_KK_MAX:
            entry = bigrams.setdefault(f"{prev['key']}|{cur['key']}", {"kk": [], "rk": []})
            entry["kk"].append(kk)
            if rk is not None and C.BIGRAM_RK_RANGE[0] < rk < C.BIGRAM_RK_RANGE[1]:
                entry["rk"].append(rk)

    # ---- Szybkość pisania ----
    total_chars = sum(1 for e in presses if is_char_key(e["key"]))
    duration = presses[-1]["t"] - presses[0]["t"] if len(presses) > 1 else 0.0
    active_time = sum(v for v in iki if v < C.ACTIVE_IKI_MAX)
    wpm = (total_chars / 5) / (active_time / 60) if active_time > 0 else 0.0
    cps = total_chars / active_time if active_time > 0 else 0.0

    # ---- Bigramy: KK i RK (od 4 próbek; IQR sam pilnuje progu 8) ----
    bigram_stats = {}
    for pair, v in bigrams.items():
        if len(v["kk"]) < C.BIGRAM_MIN_SAMPLES:
            continue
        kk_mean, kk_count, kk_out = _mean_cleaned(v["kk"])
        rk_mean, rk_count, rk_out = _mean_cleaned(v["rk"])
        bigram_stats[pair] = {
            "kk_mean": kk_mean, "kk_count": kk_count, "kk_outliers": kk_out,
            "rk_mean": rk_mean, "rk_count": rk_count, "rk_outliers": rk_out,
        }

    # ---- Częstości klawiszy, error rate, shift ratio ----
    freq = Counter(e["key"] for e in presses)
    top_keys = dict(sorted(freq.items(), key=lambda x: x[1], reverse=True)[:C.TOP_KEYS])
    error_rate = freq["Key.backspace"] / total_chars if total_chars else 0.0
    shift_ratio = (freq["Key.shift"] + freq["Key.shift_r"]) / total_chars if total_chars else 0.0

    # ---- Serie szybkich uderzeń (IKI < 150 ms) ----
    # Uwaga: logika celowo bez zmian względem poprzedniej wersji (np. ostatnia seria
    # nie jest doliczana), żeby nowe sesje były porównywalne z już zebranymi.
    burst_lengths = []
    current = 1
    for v in iki[1:]:
        if v < C.BURST_IKI_MAX:
            current += 1
        else:
            if current >= C.BURST_MIN_LEN:
                burst_lengths.append(current)
            current = 1
    avg_burst = sum(burst_lengths) / len(burst_lengths) if burst_lengths else 0.0

    return {
        "meta": {
            "total_keystrokes": len(presses),
            "total_chars":      total_chars,
            "session_duration": round(duration, 3),
        },
        "dwell_time":    describe(dwell_times),
        "flight_time":   describe(flight_times),
        "iki":           describe(iki),
        "typing_speed":  {"wpm": round(wpm, 2), "cps": round(cps, 4)},
        "error_rate":    round(error_rate, 4),
        "avg_burst_len": round(avg_burst, 4),
        "shift_ratio":   round(shift_ratio, 4),
        "special_keys":  special_keys_stats,
        "top_keys":      top_keys,
        "bigram_stats":  bigram_stats,
    }
