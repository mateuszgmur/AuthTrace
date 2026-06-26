# TypeRacer (tkinter)

## Struktura (od najprostszego do najbardziej zlozonego)

| Plik          | Rola                                           |
| ------------- | ---------------------------------------------- |
| `config.py`   | stale (kolory, sciezki, czcionki)              |
| `texts.py`    | dane: wczytuje teksty                          |
| `stats.py`    | matematyka: WPM, dokladnosc, error rate        |
| `engine.py`   | model: stan testu i jego logika                |
| `profiles.py` | warstwa danych: zapis/odczyt JSON              |
| `gui.py`      | widok: okno, klawisze, kolorowanie             |
| `main.py`     | punkt wejscia                                  |

## Przeplyw danych

```
uzytkownik naciska klawisz
        |
   gui._on_key()                  <- warstwa GUI
        |
   engine.type_char(ch)           <- model aktualizuje stan (typed, bledy, czas)
        |
   gui._render()                  <- GUI czyta stan silnika i maluje tekst
        |
   (gdy koniec) engine.result()   <- stats liczy WPM/dokladnosc
        |
   profiles.add_result()          <- warstwa danych zapisuje do JSON
```

## Rozbudowa

- Wykres postepow z historii profilu (`matplotlib`).
- ~~Wczytywanie tekstow z pliku `.txt` w `texts.py`~~ 