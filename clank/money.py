"""How Clank writes an amount of US dollars and a count of tokens (design 0016 §11), the same in the service's words
(the cost lines, the questions, Add a model's steps) and in every client: cents from a dollar up, two significant
digits below, an estimate marked ≈; a model's window in thousands of tokens. It imports nothing of the console's, so
the service's word-making modules and every client use it alike.
"""

import math


def money(usd: float | None, estimated: bool = False) -> str:
    """US dollars as Clank shows a cost: $3.10, $0.84, $0.012, $0.00002; an estimate marked ≈; nothing known, a dash."""
    if usd is None:
        return "—"
    if usd >= 1 or usd <= 0:
        shown = f"{max(usd, 0):,.2f}"
    else:
        digits = max(2, 1 - math.floor(math.log10(usd)))
        shown = f"{usd:.{digits}f}".rstrip("0")
        shown += "0" * (2 - len(shown.split(".")[1]))
    return f"{'≈ ' if estimated else ''}${shown}"


def dollars(text: str) -> float | None:
    """A limit as typed, in US dollars, as the service takes it: a number ($5, 12.50, 1,000), or None for empty or
    none; `ValueError` says what to type."""
    shown = text.strip().lower()
    if shown in ("", "none"):
        return None
    try:
        return float(shown.lstrip("$").replace(",", ""))
    except ValueError:
        raise ValueError(f"{text.strip()} is not an amount: type US dollars, such as 5 or 12.50, or none") from None


def tokens(number: int) -> str:
    """A number of tokens, briefly, as a model's window is said: 262K, 33K, 900."""
    return f"{number / 1000:.0f}K" if number >= 1000 else str(number)


def size(count: float) -> str:
    """A number of bytes, briefly: 812 KB, 15.3 GB, 1.8 TB (powers of 1024, as the system reports memory)."""
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024:
            return f"{count:.0f} {unit}" if unit in ("B", "KB") or count >= 100 else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} TB"
