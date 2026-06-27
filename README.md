# AuthTrace
AuthTrace jest to aplikacja weryfikująca tożsamość użytkownika na podstawie charakteru pracy w systemie operacyjnym. Ma umożliwiać tworzenie profilu użytkownika i douczanie w razie potrzeby. Głównym trybem po zbudowaniu profilu jest analiza podejmowanych działań i automatyczne wylogowanie w momencie podejrzenia nieautoryzowanego dostępu.

System ten składa się z dwóch głównych aplikacji: collector.py oraz train.py. Dodatkowo mamy aplikację pomocniczą typeracer, która wspomaga tworzenie profilu użytkownika, poprzez umożliwanie przepisania tekstów w bardziej przystępny sposób. W pszyszłości system zostanie rozszerzony o moduł verify.py, który będzie odpowiedzialny za faktyczne sprawdzanie użytkownika. 

## Program typeacer 

![alt text](image.png)

## Collector.py

Collector.py jest aplikacja odpowiedzialną za zbieranie danych. Uruchamia się ją za pomocą komendy:

    python collector.py --user nazwa_użytkownika --session 1

Po jej uruchomieniu dany użytkownik przepisuje teskt w celu stworzenia profilu. Po zakończeniu przepisywania program należy zamknać klikająć ESC na klawiaturze. Zebrane sesje są zapisywane do folderu data/nazwa_użytkownika.

Collectorwayland.py jest wersją cross-platform Collector.py. Może być urochamiany na:

- Windows
- macOS
- Linux/X11
- Linux/Wayland


## Train.py

Train.py odpowiada za tworzenie profilu użytkownika na podstawie danych zebranych przez collector.py. Wykonuje następujące czynności: 

    1.Ładuje wszystkie sesje danego użytkownika,

    2.Przetwarza sesje na wektory cech,

    3.Normalizuje dane,

    4.Trenuje model One‑Class SVM, który reprezentuje styl pisania użytkownika.


Uruchamia się go za pomocą komendy:

    python train.py --user nazwa_użytkownika

 Po zakończeniu pracy wytrenowany model oraz scaler jest zapisywany do katalogu models/nazwa_użytkownika. 



