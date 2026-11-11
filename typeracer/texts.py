import os
import random
from . import config

# w przypadku braku TEXTS_FILE
DEFAULT_TEXTS = [
    "Programowanie to sztuka rozwiazywania problemow za pomoca jasnych i logicznych instrukcji.",
    "Kazdego ranka slonce wstaje nad miastem, a ludzie spiesza sie do swoich codziennych zajec.",
    "Nauka pisania na klawiaturze bez patrzenia wymaga cierpliwosci oraz regularnych cwiczen.",
    "Maly kot siedzial na cieplym parapecie i obserwowal ptaki latajace po blekitnym niebie.",
    "Dobra ksiazka potrafi przeniesc czytelnika do zupelnie innego, fascynujacego swiata wyobrazni.",
    "Woda w gorskim potoku byla tak zimna i czysta, ze widac bylo kazdy kamien na samym dnie.",
]

def load_texts(path=config.TEXTS_FILE):
    
    if not os.path.exists(path):
        return DEFAULT_TEXTS
 
    # czyta teksty z pliku
    # każdy tekst oddziela pusta linia
    texts = []
    akapit = []                           # linie biezacego akapitu
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()           # usuwa spacje i znak konca linii (tez \r z Windows)
            if line:                      # linia z trescia -> dokleja do akapitu
                akapit.append(line)
            elif akapit:                  # pusta linia konczy akapit
                texts.append(" ".join(akapit))
                akapit = []
    if akapit:                            # ostatni akapit (gdy plik nie konczy sie pusta linia)
        texts.append(" ".join(akapit))
 
    return texts if texts else DEFAULT_TEXTS
 
TEXTS = load_texts()
 

def random_text():
    # losowy tekst z listy
    return random.choice(TEXTS)
