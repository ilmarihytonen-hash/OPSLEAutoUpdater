import shutil


def find_terminal() -> str | None:
    for candidate in ("x-terminal-emulator", "konsole", "xfce4-terminal"):
        terminal = shutil.which(candidate)
        if terminal:
            return terminal
    return None
