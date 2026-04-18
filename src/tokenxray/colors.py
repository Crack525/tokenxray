"""ANSI color codes for terminal output."""


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_RED = "\033[41m"

    @staticmethod
    def disable():
        for attr in ["BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE",
                      "MAGENTA", "CYAN", "WHITE", "BG_RED", "RESET"]:
            setattr(C, attr, "")
