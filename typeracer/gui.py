"""
Okno TypeRacer zintegrowane z collectorem AuthTrace.

  1) budowa okna,
  2) wybór profilu collectora (= katalog data/<profil>) i prowadzenie sesji,
  3) przechwytywanie klawiszy dla silnika testu i kolorowanie tekstu.

Dwa niezależne strumienie klawiszy:
  • tkinter  -> _on_key -> engine (kolorowanie, WPM na ekranie; nic nie zapisuje)
  • backend collectora (pynput/evdev) -> CollectorSession -> data/<profil>/ (biometria)

Nagrywanie jest włączone tylko wtedy, gdy: wybrano profil, test trwa,
okno ma fokus i fokus NIE jest w polu nazwy profilu (_sync_recording).
"""

import tkinter as tk
from tkinter import messagebox, ttk

from authtrace.backends import BackendError
from authtrace.profiles import ProfileStore
from authtrace.session import CollectorSession, SessionTooShort

from . import config, texts
from .engine import TypingTest


class TypeRacerApp:
    def __init__(self, root, backend="auto", devices=None):
        self.root = root
        root.title("AuthTrace — TypeRacer")
        root.geometry(config.WINDOW_SIZE)

        self.store = ProfileStore()
        self.backend, self.devices = backend, devices
        self.profile = None          # nazwa aktywnego profilu
        self.session = None          # CollectorSession aktywnego profilu
        self._finishing = False      # chwila po ostatnim znaku: czekamy na release klawisza
        self.test = TypingTest(texts.random_text())

        self._build_ui()
        self._load_text()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # ------------------------------------------------------------- BUDOWA OKNA
    def _build_ui(self):
        top = tk.Frame(self.root, padx=10, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="Profil:").pack(side="left")
        self.profile_box = ttk.Combobox(top, values=self.store.names(), width=18)
        self.profile_box.pack(side="left", padx=5)
        self.profile_box.bind("<<ComboboxSelected>>", self._change_profile)
        self.profile_box.bind("<Return>", self._change_profile)
        self.profile_label = tk.Label(top, text="wybierz profil lub wpisz nowy i Enter", fg="#555")
        self.profile_label.pack(side="left", padx=10)

        # pasek sesji: ● REC / pauza + liczniki
        bar = tk.Frame(self.root, padx=10)
        bar.pack(fill="x")
        self.rec_dot = tk.Label(bar, text="●", fg=config.COLORS["rec_off"])
        self.rec_dot.pack(side="left")
        self.session_label = tk.Label(bar, text="brak sesji", fg="#555")
        self.session_label.pack(side="left", padx=5)

        c = config.COLORS
        self.text_widget = tk.Text(self.root, wrap="word", height=6,
                                   font=config.FONT_TEXT, padx=10, pady=10,
                                   relief="flat", bg=c["background"])
        self.text_widget.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        self.text_widget.tag_config("correct", foreground=c["correct"])
        self.text_widget.tag_config("wrong", foreground=c["wrong_fg"], background=c["wrong_bg"])
        self.text_widget.tag_config("pending", foreground=c["pending"])
        self.text_widget.tag_config("current", underline=True)

        self.info = tk.Label(self.root, text="", font=config.FONT_INFO, pady=6)
        self.info.pack()

        btns = tk.Frame(self.root, pady=8)
        btns.pack()
        tk.Button(btns, text="Nowy tekst", command=self._new_text).pack(side="left", padx=5)
        tk.Button(btns, text="Powtórz", command=self._restart).pack(side="left", padx=5)
        if not config.SESSION_PER_TEXT:
            tk.Button(btns, text="Zapisz sesję", command=self._save_and_continue).pack(side="left", padx=5)

        # klawisze dla silnika łapiemy globalnie w oknie - nie ma osobnego pola do wpisywania
        self.root.bind("<Key>", self._on_key)
        # zmiana fokusu (pole profilu, inne okno) od razu włącza/wyłącza nagrywanie
        self.root.bind_all("<FocusIn>", lambda e: self.root.after_idle(self._sync_recording), add="+")
        self.root.bind_all("<FocusOut>", lambda e: self.root.after(10, self._sync_recording), add="+")

    # ----------------------------------------------------------------- PROFILE
    def _change_profile(self, event=None):
        name = self.profile_box.get().strip()
        if not name or name == self.profile:
            self.root.focus_set()
            return
        if not self.store.is_valid_name(name):
            messagebox.showwarning("Profil", "Nazwa profilu: litery, cyfry, '_' lub '-' (bez spacji).")
            return

        self._end_session()                       # zapisz sesję poprzedniego profilu
        try:
            self.session = self._start_session(name)
        except BackendError as e:
            messagebox.showerror("Collector", f"Nie udało się uruchomić nasłuchu klawiatury:\n\n{e}")
            self.profile = None
            self._show_profile()
            return
        self.profile = name
        self.profile_box["values"] = self.store.names()
        self._show_profile()
        self._restart()                           # świeży test = czysty początek sesji

    def _start_session(self, name):
        session = CollectorSession(name, backend=self.backend, devices=self.devices, store=self.store)
        session.pause()                           # nagrywanie włączy _sync_recording
        session.start()
        return session

    def _show_profile(self):
        if not self.profile:
            self.profile_label.config(text="wybierz profil lub wpisz nowy i Enter")
            return
        s = self.store.summary(self.profile)
        model = "jest" if s["model"] else "brak"
        self.profile_label.config(text=f"zapisanych sesji: {s['sessions']} | model: {model}")

    # ------------------------------------------------------------------ SESJA
    def _end_session(self):
        """
        Zatrzymuje bieżącą sesję (zmiana profilu / zamknięcie okna). Zwraca SessionResult|None.
        W trybie SESSION_PER_TEXT w buforze jest co najwyżej NIEDOKOŃCZONY tekst
        (skończone są już zapisane), więc go odrzucamy zamiast zapisywać.
        """
        if not self.session:
            return None
        session, self.session = self.session, None
        try:
            return session.finish(save=not config.SESSION_PER_TEXT)
        except SessionTooShort:
            return None

    def _save_current(self):
        """Zapisuje bieżącą sesję; nasłuch trwa dalej i zbiera już kolejną."""
        if not self.session:
            return None
        try:
            result = self.session.save()
        except SessionTooShort:
            result = None
        self._show_profile()
        return result

    def _save_and_continue(self):
        result = self._save_current()
        self.info.config(text=f"Zapisano sesję #{result.session_id}" if result
                         else "Za mało danych — sesja nie została zapisana")

    def _sync_recording(self):
        """Jedno miejsce decydujące, czy collector ma teraz zapisywać klawisze."""
        if not self.session:
            self.rec_dot.config(fg=config.COLORS["rec_off"])
            return
        focus = self.root.focus_get()             # None = fokus w innym programie
        active = ((not self.test.finished or self._finishing)
                  and focus is not None
                  and focus is not self.profile_box)
        (self.session.resume if active else self.session.pause)()
        self.rec_dot.config(fg=config.COLORS["rec_on" if active else "rec_off"])

    def _poll(self):
        """Odświeża pasek sesji (liczniki rosną w wątku backendu)."""
        self._sync_recording()
        if self.session:
            nr = self.store.next_session_id(self.profile)
            self.session_label.config(
                text=f"sesja #{nr} | klawiszy: {self.session.keystrokes} | "
                     f"backend: {self.session.backend_name}")
        else:
            self.session_label.config(text="brak sesji — dane nie są zbierane")
        self.root.after(config.STATUS_REFRESH_MS, self._poll)

    def _on_close(self):
        result = self._end_session()
        if result:
            print(f"💾 Zapisano sesję #{result.session_id}: {result.features_path}")
        self.root.destroy()

    # --------------------------------------------------------- STEROWANIE TESTEM
    def _new_text(self):
        self.test.reset(texts.random_text())
        self._load_text()

    def _restart(self):
        self.test.reset(self.test.target)
        self._load_text()

    def _load_text(self):
        if self.session and config.SESSION_PER_TEXT:
            self.session.discard()                # przerwany tekst nie trafia do sesji
        self.text_widget.config(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", self.test.target)
        self.text_widget.config(state="disabled")
        self._render()
        self.info.config(text="Zacznij pisać..." if self.profile else "Najpierw wybierz profil")
        self.root.focus_set()
        self._sync_recording()

    def _on_key(self, event):
        # bez profilu nie ma sesji -> nie ma sensu pisać; ignorujemy też pole nazwy profilu
        if not self.profile or self.test.finished or self.root.focus_get() is self.profile_box:
            return

        was_started = self.test.started
        if event.keysym == "BackSpace":
            self.test.backspace()
        elif len(event.char) == 1 and event.char.isprintable():
            self.test.type_char(event.char)
            if not was_started and self.test.started:
                self._tick()                     # zegar startuje przy 1. znaku
        else:
            return                               # Shift, strzałki itp. - pomijamy

        self._render()
        if self.test.finished:
            self._finish()

    # ----------------------------------------------------------------- RYSOWANIE
    def _render(self):
        for tag in ("correct", "wrong", "pending", "current"):
            self.text_widget.tag_remove(tag, "1.0", "end")

        typed, target = self.test.typed, self.test.target
        for i, ch in enumerate(target):
            if i < len(typed):
                tag = "correct" if typed[i] == ch else "wrong"
            else:
                tag = "pending"
            self.text_widget.tag_add(tag, f"1.0+{i}c", f"1.0+{i + 1}c")

        pos = len(typed)                         # podkreślenie bieżącego znaku
        if pos < len(target):
            self.text_widget.tag_add("current", f"1.0+{pos}c", f"1.0+{pos + 1}c")

    def _tick(self):
        if self.test.started and not self.test.finished:
            self.info.config(text=f"Czas: {self.test.elapsed():.1f}s")
            self.root.after(100, self._tick)

    def _finish(self):
        r = self.test.result()
        self._result_line = (f"Czas: {r['seconds']}s  |  {r['wpm']:.0f} WPM  |  "
                             f"Dokładność: {r['accuracy']}%  |  Błąd: {r['error_rate']}%")
        self.info.config(text=self._result_line)
        # tkinter widzi PRESS ostatniego znaku, a jego RELEASE przyjdzie za ~100 ms —
        # nagrywamy jeszcze chwilę, potem pauza i (w trybie per-tekst) zapis.
        self._finishing = True
        self.root.after(config.FINISH_GRACE_MS, self._after_finish)

    def _after_finish(self):
        self._finishing = False
        self._sync_recording()                   # test skończony -> pauza nagrywania
        if not self.test.finished:               # w międzyczasie kliknięto "Powtórz"/"Nowy tekst"
            return
        if config.SESSION_PER_TEXT:
            result = self._save_current()
            suffix = f"  |  💾 sesja #{result.session_id}" if result else "  |  za mało danych"
            self.info.config(text=self._result_line + suffix)
