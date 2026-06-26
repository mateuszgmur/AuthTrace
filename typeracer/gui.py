"""
  1) budowa okna,
  2) przechwytywanie klawiszy i przekazywanie ich do silnika,
  3) kolorowanie tekstu wg stanu silnika.

  klawisz -> _on_key -> test.type_char() -> _render() (przemalowanie)
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

import config
import texts
from engine import TypingTest
from profiles import ProfileManager


class TypeRacerApp:
    def __init__(self, root):
        # wstępne ustawienia okna
        self.root = root
        root.title("TypeRacer")
        root.geometry(config.WINDOW_SIZE)

        # menedżer profili, silnik z losowym testem
        self.profiles = ProfileManager()
        self.profil = None                       # nazwa aktywnego profilu
        self.test = TypingTest(texts.random_text())

        # budowa okna i wstawianie tekstu
        self._build_ui()
        self._load_text()

    # BUDOWA OKNA -------------------------
    def _build_ui(self):
        # pasek profilu
        top = tk.Frame(self.root, padx=10, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="Profil:").pack(side="left")
        self.profil_box = ttk.Combobox(top, values=self.profiles.names(), width=18)
        self.profil_box.pack(side="left", padx=5)
        self.profil_box.bind("<<ComboboxSelected>>", self._change_profile)
        self.profil_box.bind("<Return>", self._change_profile)
        self.stat_label = tk.Label(top, text="(wpisz nazwe profilu i Enter)", fg="#555")
        self.stat_label.pack(side="left", padx=15)

        # pole z tekstem do przepisania
        c = config.COLORS
        self.text_widget = tk.Text(self.root, wrap="word", height=6,
                                   font=config.FONT_TEXT, padx=10, pady=10,
                                   relief="flat", bg=c["background"])
        self.text_widget.pack(fill="both", expand=True, padx=10)
        self.text_widget.tag_config("correct", foreground=c["correct"])
        self.text_widget.tag_config("wrong", foreground=c["wrong_fg"], background=c["wrong_bg"])
        self.text_widget.tag_config("pending", foreground=c["pending"])
        self.text_widget.tag_config("current", underline=True)

        # wiersz z wynikiem / zegarem
        self.info = tk.Label(self.root, text="Zacznij pisać...", font=config.FONT_INFO, pady=6)
        self.info.pack()

        # przyciski
        btns = tk.Frame(self.root, pady=8)
        btns.pack()
        tk.Button(btns, text="Nowy tekst", command=self._new_text).pack(side="left", padx=5)
        tk.Button(btns, text="Powtórz", command=self._restart).pack(side="left", padx=5)

        # klawisze lapiemy globalnie - nie ma osobnego pola do wpisywania
        self.root.bind("<Key>", self._on_key)

    #   PROFILE -------------------------
    def _change_profile(self, event=None):
        name = self.profil_box.get().strip()
        if not name:
            return
        self.profiles.ensure(name)
        self.profil_box["values"] = self.profiles.names()
        self.profil = name
        self._show_summary()
        self.root.focus_set()                    # fokus wraca na test

    def _show_summary(self):
        s = self.profiles.summary(self.profil)
        if s:
            self.stat_label.config(
                text=f"{self.profil} | gier: {s['games']} | "
                     f"rekord: {s['best']:.0f} WPM | srednia: {s['avg']:.0f} WPM")
        else:
            self.stat_label.config(text=f"{self.profil} | brak wynikow")

    #   STEROWANIE TESTEM -------------------------
    # nowy losowy
    def _new_text(self):
        self.test.reset(texts.random_text())
        self._load_text()

    # ten sam od nowa
    def _restart(self):
        self.test.reset(self.test.target)
        self._load_text()

    def _load_text(self):
        # wstawia tekst wzorcowy do pola i blokuje edycje
        self.text_widget.config(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", self.test.target)
        self.text_widget.config(state="disabled")
        self._render()
        self.info.config(text="Zacznij pisac...")
        self.root.focus_set()

    def _on_key(self, event):
        # ignorujemy, gdy test skonczony albo gdy piszemy nazwe profilu
        if self.test.finished or self.root.focus_get() is self.profil_box:
            return

        was_started = self.test.started
        if event.keysym == "BackSpace":
            self.test.backspace()
        elif len(event.char) == 1 and event.char.isprintable():
            self.test.type_char(event.char)
            if not was_started and self.test.started:
                self._tick()                     # zegar startuje przy 1. znaku
        else:
            return                               # Shift, strzalki itp. - pomijamy

        self._render()
        if self.test.finished:
            self._finish()

    #   RYSOWANIE -------------------------
    def _render(self):
        # maluje tekst znak po znaku wg stanu silnika
        for tag in ("correct", "wrong", "pending", "current"):
            self.text_widget.tag_remove(tag, "1.0", "end")

        typed, target = self.test.typed, self.test.target
        # pętla po znakach wzorca
        for i, ch in enumerate(target):
            start, end = f"1.0+{i}c", f"1.0+{i + 1}c"
            if i < len(typed):
                # correct / wrong dla wpisanych
                tag = "correct" if typed[i] == ch else "wrong"
            else:
                # pending dla oczekujących
                tag = "pending"
            self.text_widget.tag_add(tag, start, end)

        pos = len(typed)                         # podkreslenie biezacego znaku
        if pos < len(target):
            self.text_widget.tag_add("current", f"1.0+{pos}c", f"1.0+{pos + 1}c")

    def _tick(self):
        # Odswieza zegar co 100 ms (tkinter nie ma watkow - uzywamy after)
        if self.test.started and not self.test.finished:
            self.info.config(text=f"Czas: {self.test.elapsed():.1f}s")
            self.root.after(100, self._tick)

    def _finish(self):
        # pobiera wynik i wyświetla podsumowanie
        r = self.test.result()
        self.info.config(text=(f"Czas: {r['seconds']}s   |   {r['wpm']:.0f} WPM   |   "
                               f"Dokladnosc: {r['accuracy']}%   |   Blad: {r['error_rate']}%"))
        # jeśli wybrany profil, dodaje datę, aktualizuje plik i statystyki
        if self.profil:
            r["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.profiles.add_result(self.profil, r)
            self._show_summary()
