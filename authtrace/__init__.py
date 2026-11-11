"""
authtrace — rdzeń systemu: przechwytywanie klawiatury, ekstrakcja cech,
sesje i profile użytkowników.

Moduły:
    config    – ścieżki i progi (jedno miejsce na „magiczne liczby”)
    backends  – źródła zdarzeń klawiatury: pynput (Win/macOS/X11), evdev (Wayland)
    features  – zamiana surowych zdarzeń na wektor cech (jedna wersja dla wszystkich)
    session   – jedna sesja nagrywania: start / pauza / zapis
    profiles  – profil = katalog data/<nazwa>
"""
