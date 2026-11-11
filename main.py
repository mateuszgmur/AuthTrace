"""
AuthTrace — główny punkt wejścia: TypeRacer z wbudowanym collectorem.

    python main.py                    # backend wybierany automatycznie
    python main.py --backend evdev    # Linux/Wayland (wymaga grupy 'input')
"""

import argparse
import tkinter as tk

from typeracer.gui import TypeRacerApp


def main():
    p = argparse.ArgumentParser(description="AuthTrace — TypeRacer + collector")
    p.add_argument("--backend", default="auto", choices=["auto", "pynput", "evdev"])
    p.add_argument("--device", action="append", help="Ścieżka /dev/input/eventX (evdev)")
    args = p.parse_args()

    root = tk.Tk()
    TypeRacerApp(root, backend=args.backend, devices=args.device)
    root.mainloop()


if __name__ == "__main__":
    main()
