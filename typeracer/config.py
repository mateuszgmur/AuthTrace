from pathlib import Path

# Ścieżka liczona od katalogu pakietu (wcześniej "texts1.txt" względem CWD —
# działało tylko przy uruchomieniu z katalogu typeracer/).
TEXTS_FILE = Path(__file__).resolve().parent / "texts1.txt"

# True  -> każdy przepisany do końca tekst = osobna sesja collectora (zapis automatyczny),
#          przerwany tekst ("Nowy tekst"/"Powtórz" w trakcie) jest odrzucany.
#          Sesje mają wtedy porównywalną długość i treść — lepsze dla modelu.
# False -> jedna sesja trwa przez wiele tekstów, aż do "Zapisz sesję" / zmiany profilu / zamknięcia.
SESSION_PER_TEXT = True

STATUS_REFRESH_MS = 200          # co ile odświeżać pasek sesji i stan nagrywania
FINISH_GRACE_MS = 400            # ile jeszcze nagrywać po ostatnim znaku (release ostatniego klawisza)

WINDOW_SIZE = "760x440"         # rozmiar okna tkinter
FONT_TEXT = ("Consolas", 16)
FONT_INFO = ("Arial", 12)

# Kolory używane do podświetlania znaków
COLORS = {
    "correct": "#2e7d32",    # zielony - znak poprawny
    "wrong_fg": "white",     # tekst błędu
    "wrong_bg": "#c62828",   # czerwone tło błędu
    "pending": "#888888",    # szary - jeszcze nie napisane
    "background": "#f5f5f5",
    "rec_on": "#c62828",     # wskaźnik nagrywania
    "rec_off": "#888888",
}
