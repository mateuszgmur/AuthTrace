"""Wspólna konfiguracja: ścieżki i progi używane przy zbieraniu oraz ekstrakcji cech."""

from pathlib import Path

# Ścieżki liczone od katalogu projektu, a nie od bieżącego katalogu (CWD) —
# dzięki temu collector, typeracer i train.py zapisują/czytają te same pliki
# niezależnie od tego, skąd zostały uruchomione.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"      # data/<profil>/raw_session_N.json, features_session_N.json
MODELS_DIR = PROJECT_DIR / "models"  # models/<profil>/model.pkl, scaler.pkl

# Minimalna liczba zdarzeń (press + release), żeby sesja została zapisana
MIN_EVENTS = 20

# --- Filtry czasów [s] (wartości spoza zakresu traktujemy jako przerwę/artefakt) ---
DWELL_MAX = 2.0              # press -> release tego samego klawisza
FLIGHT_RANGE = (-0.5, 3.0)   # release poprzedniego -> press następnego (ujemny = nakładanie)
IKI_MAX = 3.0                # press -> press
ACTIVE_IKI_MAX = 2.0         # IKI liczone do "aktywnego" czasu pisania (WPM / CPS)
BIGRAM_KK_MAX = 1.5          # bigram: press -> press
BIGRAM_RK_RANGE = (-0.3, 1.5)  # bigram: release -> press
BURST_IKI_MAX = 0.15         # IKI poniżej tego progu = ta sama "seria"
BURST_MIN_LEN = 3            # seria liczy się od 3 klawiszy

# --- Próbki ---
BIGRAM_MIN_SAMPLES = 4       # bigram trafia do cech od 4 wystąpień
IQR_MIN_SAMPLES = 8          # odrzucanie outlierów IQR dopiero od 8 próbek
IQR_K = 1.5
TOP_KEYS = 20

# Klawisze specjalne, dla których liczymy osobny dwell time.
# Key.alt_gr: tak pynput (Windows/X11) i evdev raportują prawy Alt.
# Przy polskim układzie to właśnie AltGr służy do pisania ą, ę, ł... — wcześniej
# mapowany był tylko Key.alt_r, więc "alt_right" zawsze wychodził 0.
SPECIAL_KEYS = {
    "Key.shift": "shift_left",
    "Key.shift_r": "shift_right",
    "Key.space": "space",
    "Key.enter": "enter",
    "Key.backspace": "backspace",
    "Key.alt": "alt_left",
    "Key.alt_l": "alt_left",
    "Key.alt_r": "alt_right",
    "Key.alt_gr": "alt_right",
}
