import tkinter as tk
from gui import TypeRacerApp


def main():
    # główne okno, budowanie aplikacji, pętla zdarzeń
    root = tk.Tk()
    TypeRacerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
