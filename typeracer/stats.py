def chars_to_words(num_chars):
    # standard w typingu: 1 słowo = 5 znakow, statystyka niezależna od spacji
    return num_chars / 5


def wpm(num_chars, seconds):
    # WPM = słowa (znaki/5) / minutę
    if seconds <= 0:
        return 0.0
    minutes = seconds / 60
    return chars_to_words(num_chars) / minutes


def accuracy(typed, target):
    # procent znaków, które zgadzają się z wzorcem 
    if not target:
        return 0.0
    # dla każdej zgadzającej się poz. -> 1, sumuje -> liczba zgadzających się znaków
    correct = sum(1 for i, ch in enumerate(target) if i < len(typed) and typed[i] == ch)
    return correct / len(target) * 100


def error_rate(errors_made, total_typed):
    # liczy rowniez poprawione backspacem
    if total_typed == 0:
        return 0.0
    return errors_made / total_typed * 100
