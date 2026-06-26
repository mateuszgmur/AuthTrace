import time
import stats


class TypingTest:
    def __init__(self, target):
        self.reset(target)

    def reset(self, target):
        # stan początkowy, nowy test 
        self.target = target        # tekst wzorcowy
        self.typed = ""             # co wpisal uzytkownik
        self.start_time = None      # czas 1. wcisnietego klawisza
        self.end_time = None        # czas zakonczenia (zeby zamrozic zegar)
        self.errors_made = 0        # licznik blednych wcisniec
        self.total_typed = 0        # licznik wpisanych znakow (bez backspace)
        self.finished = False

    # dekorator, zwraca True gdy start_time isset
    @property
    def started(self):
        return self.start_time is not None

    def type_char(self, ch):
        # obsługa wpisania znaku
        if self.finished:
            return
        if self.start_time is None:          # start zegara przy 1st znaku
            self.start_time = time.time()

        # pozycja kolejnego znaku na podst. dł. dotychczasowego tekstu
        pos = len(self.typed)
        if pos < len(self.target):
            # liczniki błędów i znaków
            if ch != self.target[pos]:
                self.errors_made += 1
            self.total_typed += 1
            self.typed += ch
            if len(self.typed) >= len(self.target):
                self.finished = True
                self.end_time = time.time()  # zamrazamy czas

    def backspace(self):
        # usuwa ostatni znak i nie zmniejsza licznika błędów 
        if not self.finished:
            self.typed = self.typed[:-1]

    def elapsed(self):
        # ile sekund minęło, po zakuńczeniu - czas zamrożony
        if self.start_time is None:
            return 0.0
        koniec = self.end_time if self.end_time else time.time()
        return koniec - self.start_time

    def result(self):
        # słownik z wynikami
        secs = self.elapsed()
        return {
            "wpm": round(stats.wpm(len(self.target), secs), 1),
            "accuracy": round(stats.accuracy(self.typed, self.target), 1),
            "error_rate": round(stats.error_rate(self.errors_made, self.total_typed), 1),
            "seconds": round(secs, 1),
        }
