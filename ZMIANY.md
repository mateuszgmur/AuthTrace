# Przebudowa: uporządkowanie collectora i scalenie z TypeRacerem

Gałąź: `refactor/collector-typeracer`

## 1. Cel

1. Uprościć i oczyścić kod collectora.
2. Połączyć collector z TypeRacerem **funkcjonalnie** (bez sklejania wszystkiego w jeden plik):
   - profile collectora (`data/<profil>`) wybierane z GUI, bez dawnych profili TypeRacera ze statystykami WPM,
   - sesja collectora uruchamiana razem z TypeRacerem.

Warunek brzegowy: `train.py` i już zebrane dane mają dalej działać, a nowe sesje mają być porównywalne ze starymi.

## 2. Stan wyjściowy — co było nie tak

| # | Problem | Skutek |
|---|---------|--------|
| P1 | Dwa collectory (`collector.py`, `collectorwayland.py`) z **dwiema różnymi wersjami** `extract_features`. Wersja Wayland jest starsza: brak usuwania outlierów (IQR), brak `special_keys`, `bigram_means` zamiast `bigram_stats`, inaczej liczy `total_chars`. | Pliki cech w repo są niespójne: `data/maks`, `data/maks_old`, `data/mateusz_old` mają stary format, `data/mateusz`, `data/malgorzata` nowy. Np. `dwell_time.std` dla maks/sesja 1: 67 ms w zapisanym pliku vs 23 ms po IQR — cecha z wagą ×2 w `train.py` różni się 2–3×, więc modele różnych osób uczono na różnie liczonych cechach. |
| P2 | Collector był blokujący (`listener.join()`, `select()` bez timeoutu) i oparty na zmiennych globalnych. | Nie dało się go uruchomić z GUI — tkinter ma własną pętlę zdarzeń. |
| P3 | **Polskie znaki gubiły dwell time.** pynput wylicza znak w chwili zdarzenia: AltGr+L daje press `'ł'`, a release (po puszczeniu AltGr) `'l'`. Parowanie press↔release po nazwie się rozjeżdżało. | W 34 surowych sesjach z repo jest 1006 releasów bez pary — głównie `l, e, o, a, c, z` (ł, ę, ó, ą, ć, ż). Dwell dla tych liter był odrzucany albo sparowany z niewłaściwym naciśnięciem. |
| P4 | `SPECIAL_KEYS` mapował tylko `Key.alt_r`, a pynput/evdev zgłaszają prawy Alt jako `Key.alt_gr` (w danych: ~900 naciśnięć na osobę). | `special_keys.alt_right` zawsze 0 — martwa cecha. |
| P5 | Numer sesji podawany ręcznie (`--session`), zapis bez sprawdzania. | Łatwo nadpisać starą sesję. |
| P6 | Ścieżki względem bieżącego katalogu (`Path("data")`, `"texts1.txt"`, `"profiles.json"`). | TypeRacer działał tylko po uruchomieniu z `typeracer/`; collector/train zapisywały tam, skąd je uruchomiono. |
| P7 | Pierwsze zdarzenie sesji to często release Entera, którym uruchomiono skrypt (widać w `data/mateusz/raw_session_1.json`). | Release bez press przesuwa parowanie FIFO dla Entera do końca sesji. |
| P8 | Bałagan w repo: `main.py` = szablon PyCharma, `__pycache__` w gicie (mimo `.gitignore`), `tekst.txt` = starsza kopia `typeracer/texts1.txt`, `typeracer/profiles.json` ze statystykami. | Utrudnia orientację w projekcie. |
| P9 | Wydajność: flight time i bigramy przeszukiwały całą listę releasów dla każdego naciśnięcia (O(n²), dwa razy), dwell liczony dwa razy. | Przy dłuższych sesjach niepotrzebnie wolno. |

## 3. Obrana droga (kolejność kroków)

1. **Najpierw rdzeń, potem GUI.** Wydzieliłem z collectora pakiet `authtrace/` z czystymi interfejsami. Dopiero na gotowym, przetestowanym rdzeniu oparłem TypeRacera. Odwrotna kolejność (doklejanie collectora do GUI) utrwaliłaby globalne zmienne i blokujący nasłuch.
2. **Jedna ekstrakcja cech** — wzięta 1:1 z `collector.py` (nowsza wersja, ta z IQR) i sprawdzona na wszystkich surowych sesjach z repo, że daje identyczne wyniki (patrz §6). Wersja z `collectorwayland.py` znika; z tego pliku zostaje tylko backend evdev.
3. **Backendy za wspólnym, nieblokującym interfejsem** `start()/stop()` — to jest warunek, żeby collector mógł chodzić „pod” GUI.
4. **Sesja jako obiekt** (`CollectorSession`) — wspólny dla GUI i CLI: start, pauza, zapis, numeracja.
5. **Profil = katalog `data/<profil>`** — jedno źródło prawdy, to samo, które czyta `train.py`. Profile TypeRacera (`profiles.json`) usunięte.
6. **TypeRacer jako pakiet** korzystający z rdzenia; collector startuje razem z wyborem profilu.
7. Sprzątanie repo, testy, dokumentacja.

## 4. Nowa architektura

```
main.py ──► typeracer/gui.py ──┬──► typeracer/engine.py   (kolorowanie, WPM na ekranie — nic nie zapisuje)
                               │
collector.py (CLI) ────────────┴──► authtrace/session.py ──► authtrace/backends.py  (pynput | evdev, wątek w tle)
                                          │
                                          ├──► authtrace/features.py ──► data/<profil>/features_session_N.json
                                          ├──► data/<profil>/raw_session_N.json
                                          └──► authtrace/profiles.py   (lista profili, numeracja sesji)

train.py ──► authtrace/config.py (ścieżki) + authtrace/profiles.py ──► models/<profil>/
```

Podział odpowiedzialności: `authtrace/` nie wie nic o tkinterze; `typeracer/` nie wie nic o pynput/evdev ani o formacie plików. Dzięki temu collector można też uruchomić bez GUI (CLI), a w przyszłości użyć w `verify.py`.

Dwa strumienie klawiszy w TypeRacerze są celowe: tkinter służy tylko do kolorowania tekstu, a do biometrii idą zdarzenia z backendu collectora — z tym samym zegarem (`perf_counter`) i w tym samym formacie nazw co dotychczasowe dane.

## 5. Zmiany plik po pliku

### Nowe: `authtrace/` (rdzeń)

| Plik | Co | Dlaczego |
|------|----|----------|
| `config.py` | Ścieżki `DATA_DIR`/`MODELS_DIR` liczone od katalogu projektu; wszystkie progi (2.0 s, 3.0 s, 1.5 s, 150 ms, 4 i 8 próbek…) jako nazwane stałe; `SPECIAL_KEYS` z `Key.alt_gr` i `Key.alt_l`. | P4, P6. „Magiczne liczby” były rozsiane po funkcji; teraz widać w jednym miejscu, jakie filtry stosujemy, i można je opisać w pracy. |
| `features.py` | Jedyna `extract_features`. Algorytm bez zmian; refaktor wewnętrzny: dwell liczony raz (globalny + specjalne w jednym przejściu), wyszukiwanie releasu binarnie zamiast pętli po wszystkich zdarzeniach, kwartyle liczone raz, bigramy bez potrójnego wołania IQR. Funkcja `stats` → `describe` (żeby nie myliła się z modułem `typeracer/stats.py`). | P1, P9. Wyniki identyczne ze starą wersją (§6). Logikę serii (`avg_burst_len`, np. nie liczy ostatniej serii) **celowo** zostawiłem — zmiana unieważniłaby porównywalność z zebranymi sesjami; opisane w komentarzu. |
| `backends.py` | `PynputBackend` i `EvdevBackend` ze wspólnym nieblokującym API; `choose_backend()` z dawnego `collectorwayland.py`; evdev w wątku z `select(timeout=0.2)`, żeby `stop()` działał. Release dostaje **tę samą nazwę co press** (parowanie po kodzie fizycznego klawisza `vk` / kodzie evdev). Błędy jako wyjątek `BackendError` zamiast `print` + `sys.exit`. | P2, P3. Bez tego GUI musiałoby się zamknąć, żeby skończyć sesję. Wyjątek pozwala GUI pokazać okienko z błędem, a CLI — komunikat. |
| `session.py` | `CollectorSession`: `start / pause / resume / discard / save / finish`; bufor chroniony lockiem (backend pisze z innego wątku); odrzucanie releasów bez press; zapis pod kolejnym wolnym numerem i odmowa nadpisania istniejącej sesji. Format plików bez zmian. | P2, P5, P7. Jedna implementacja dla GUI i CLI. `train.py` czyta pliki jak dotąd. |
| `profiles.py` | `ProfileStore`: lista profili = katalogi w `data/`, numeracja sesji (sortowanie numeryczne), info o modelu, walidacja nazwy (`[\w-]`, max 40 znaków). | Wymaganie 1. Nazwa profilu staje się nazwą katalogu, więc walidacja blokuje spacje, `/` i `..`. |

### TypeRacer

| Plik | Co | Dlaczego |
|------|----|----------|
| `typeracer/__init__.py` | Nowy — TypeRacer jest pakietem; importy względne (`from . import config`). | Bez tego `typeracer/gui.py` nie mógłby importować `authtrace`, a `authtrace` musiałby leżeć w `typeracer/`. |
| `typeracer/gui.py` | Combobox listuje profile z `data/`; Enter z nową nazwą tworzy profil. Wybór profilu startuje `CollectorSession` (zmiana profilu kończy poprzednią). Pasek sesji: ● nagrywanie, nr sesji, liczba klawiszy, backend. Nagrywanie tylko gdy test trwa, okno ma fokus i fokus nie jest w polu profilu. Po ostatnim znaku nagrywa jeszcze 400 ms (release ostatniego klawisza), potem zapis. Przerwany tekst odrzucany. Zamknięcie okna kończy sesję. Bez profilu nie da się pisać. Usunięte statystyki profilu (gry/rekord/średnia). | Wymagania 1 i 2. Bramkowanie fokusem jest ważne, bo pynput/evdev łapią klawiaturę **globalnie** — bez tego do sesji trafiałoby pisanie w innych programach i nazwa profilu. Wynik WPM po teście dalej jest wyświetlany (motywacja dla piszącego), ale nie jest zapisywany. |
| `typeracer/config.py` | `TEXTS_FILE` względem pakietu; usunięte `PROFILES_FILE`; nowe `SESSION_PER_TEXT`, `STATUS_REFRESH_MS`, `FINISH_GRACE_MS`. | P6. `SESSION_PER_TEXT = True` (domyślnie): jeden przepisany tekst = jedna sesja. Sesje mają tę samą treść i długość, co jest lepsze dla One-Class SVM niż sesje o losowej długości. `False` — jedna sesja przez wiele tekstów, z przyciskiem „Zapisz sesję”. |
| `typeracer/engine.py`, `texts.py` | Tylko import względny. | — |
| `typeracer/profiles.py`, `profiles.json`, `main.py` | **Usunięte.** | Profile ze statystykami nie są już potrzebne; punkt wejścia jest w głównym katalogu. |

### Pozostałe

| Plik | Co | Dlaczego |
|------|----|----------|
| `main.py` | Zastąpiony (był szablon PyCharma): uruchamia TypeRacera z collectorem; `--backend`, `--device`. | Jeden oczywisty punkt startu. |
| `collector.py` | Cienki CLI na rdzeniu (~140 linii zamiast 265). `--session` opcjonalne; `--backend`, `--device`, `--list-devices` (z wersji Wayland); nowe `--reextract`; Ctrl+C zapisuje to, co zebrano. ESC kończy sesję tylko w CLI. | Zostaje do swobodnego pisania w dowolnym programie. `--reextract` naprawia P1 dla istniejących danych. |
| `collectorwayland.py` | **Usunięty** — backend evdev jest w `authtrace/backends.py`, `collector.py` sam wybiera backend. | P1. |
| `train.py` | Ścieżki z `authtrace.config`; sesje sortowane numerycznie; `sys.exit` zamiast `exit`; podpowiedź `verify.py` z właściwą nazwą użytkownika (było na sztywno „mateusz”). Wektor cech i model **bez zmian**. | P6. Celowo minimalnie — trening to osobny etap projektu. |
| `tests/test_core.py` | 9 testów: cechy, IQR, AltGr, profile, numeracja, pauza, release bez press, zbyt krótka sesja, brak nadpisywania. Atrapa backendu zamiast prawdziwej klawiatury. | Pozwala zmieniać kod bez ręcznego klikania. `python -m unittest discover tests` |
| `requirements.txt` | Nowy. | Zależności były opisane tylko w komunikatach błędów. |
| `.gitignore`, `__pycache__`, `.vscode`, `tekst.txt` | `__pycache__` i `.vscode` usunięte z repo (lokalnie zostają), `.vscode/` dodane do `.gitignore`; usunięty `tekst.txt` (starsza kopia `typeracer/texts1.txt`). | P8. |
| `README.md` | Aktualna struktura i instrukcje. | — |

## 6. Weryfikacja

- **Równoważność ekstrakcji cech:** stara `extract_features` z `collector.py` i nowa z `authtrace/features.py` uruchomione na wszystkich 34 plikach `raw_session_*.json` z repo. Wynik: wszystkie cechy identyczne; jedyna różnica to `special_keys.alt_right` w 13 sesjach (było 0, teraz 1–98 naciśnięć) — zamierzona poprawka P4.
- **Testy jednostkowe:** 9/9 OK.
- **GUI:** logika okna przetestowana na atrapie tkintera (wybór profilu, pauza przy wpisywaniu nazwy i przy braku fokusu, odrzucenie przerwanego tekstu, zapis `sesja #1`, zamknięcie okna). Nie było tu prawdziwego tkintera ani klawiatury, więc **trzeba to sprawdzić ręcznie** na Windows / X11 / Wayland.
- **train.py** uruchomiony na `data/malgorzata` — działa z nowymi ścieżkami.

## 7. Wpływ na dane i modele — co zrobić po scaleniu

1. **Przeliczyć cechy:** `python collector.py --reextract` — wszystkie `features_session_*.json` będą liczone tą samą wersją (P1, P4). Surowe pliki zostają bez zmian.
2. **Wytrenować modele od nowa:** `python train.py --user <profil>` dla każdego profilu — obecne modele `maks` uczono na cechach bez IQR, więc nie są porównywalne z resztą.
3. Poprawka P3 działa **tylko dla nowych sesji** (stare pliki raw nie mają kodu fizycznego klawisza). Stare sesje mają więc mniej próbek dwell dla polskich liter niż nowe — przy porównaniach warto trzymać się sesji zebranych jedną wersją albo zebrać sesje od nowa.

## 8. Ograniczenia i rekomendacje

- **Prywatność danych:** `raw_session_*.json` to pełny zapis tego, co ktoś napisał (także poza tekstem, jeśli collector CLI chodził w tle). Repozytorium jest publiczne — warto przenieść `data/` z gita (np. do `.gitignore` i udostępniać prywatnie) albo przynajmniej się upewnić, że w plikach nie ma haseł ani prywatnych treści.
- **Wayland:** evdev wymaga grupy `input`. Uruchamianie GUI przez `sudo` zwykle nie działa (brak dostępu do sesji graficznej).
- **macOS:** pynput wymaga uprawnień „Dostępność / Monitorowanie wejścia” dla terminala; nie testowane.
- **Alternatywa na przyszłość:** w TypeRacerze można by brać zdarzenia `KeyPress/KeyRelease` z samego tkintera (bez uprawnień, bez globalnego nasłuchu). Nie wybrałem tej drogi, bo nazwy klawiszy i zegar różniłyby się od już zebranych danych, a docelowy tryb projektu (monitorowanie pracy w systemie) i tak wymaga globalnego collectora.
- `verify.py` może korzystać z `CollectorSession` + `extract_features` + `features_to_vector` bez kopiowania kodu.
