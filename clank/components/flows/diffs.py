"""Two tries of a box compared (design 0013 §8, §10): what changed in a deliverable from one try to another.

When a box ends, the runner copies each deliverable into the try's folder (`<box>/try-<k>/deliverables/`), so any two
tries can be compared after the folder's file has moved on. `compare` is a unified diff of two copies, three lines of
context, and the lines changed counted as board D3 says them ("changed since try 1: 7 lines"): a block replaced counts
its longer side, one added or removed its own lines. Comparing is the owner's: `clank flow diff`, the Flow view's `d`,
and a gate, which says beside each file it shows how much changed since the try before.

**Within seconds, whatever the file.** Python's `difflib` matching every line exactly takes minutes on a large file of
repeated lines (pretty-printed JSON, a CSV: 186 seconds for 102 KB), and a gate must not wait for it, nor the machine
work for it (design 0004's no stutter). So the lines both copies begin and end with are set aside first, and what
remains is matched exactly while each side has at most `EXACT` lines; past that, lines repeated through it are not used
to match on (`difflib`'s *autojunk*, as its own unified diff does), which may count a block of them as replaced. The
diff and the count come from the same match, so they always agree.
"""

import difflib
from collections.abc import Iterator
from dataclasses import dataclass

LARGEST_SHOWN = 200_000  # bytes of each copy a gate's question compares; a larger one is compared when asked
EXACT = 1_000  # lines of each side, past their common beginning and end, matched exactly
CONTEXT = 3
Opcode = tuple[str, int, int, int, int]


@dataclass(frozen=True)
class Compared:
    """Two tries' copies of a file, compared."""

    path: str
    a: int
    b: int
    changed: int
    added: int
    removed: int
    diff: str

    @property
    def said(self) -> str:
        """How much changed, as board D3 says it."""
        if not self.changed:
            return f"unchanged since try {self.a}"
        return f"changed since try {self.a}: {self.changed:,} line" + ("" if self.changed == 1 else "s")


def compare(path: str, before: str, after: str, a: int, b: int) -> Compared:
    """The copy of try `a` (`before`) against the copy of try `b` (`after`)."""
    old, new = _lines(before), _lines(after)
    codes = _opcodes(old, new)
    changed = added = removed = 0
    for tag, i1, i2, j1, j2 in codes:
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
        added += j2 - j1
        removed += i2 - i1
    diff = "".join(_unified(old, new, codes, f"{path} (try {a})", f"{path} (try {b})")) if changed else ""
    return Compared(path, a, b, changed, added, removed, diff)


def text_of(raw: bytes) -> str | None:
    """A copy's text, or None when it is not text (not UTF-8, or holding a NUL)."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return None if "\x00" in text else text


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").splitlines()


def _opcodes(old: list[str], new: list[str]) -> list[Opcode]:
    """How `old` becomes `new`, as `difflib`'s opcodes: their common beginning and end set aside, the rest matched."""
    shortest = min(len(old), len(new))
    head = 0
    while head < shortest and old[head] == new[head]:
        head += 1
    tail = 0
    while tail < shortest - head and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    left, right = old[head : len(old) - tail], new[head : len(new) - tail]
    codes: list[Opcode] = [("equal", 0, head, 0, head)] if head else []
    if left or right:
        matcher = difflib.SequenceMatcher(None, left, right, autojunk=max(len(left), len(right)) > EXACT)
        codes += [(tag, i1 + head, i2 + head, j1 + head, j2 + head) for tag, i1, i2, j1, j2 in matcher.get_opcodes()]
    if tail:
        codes.append(("equal", len(old) - tail, len(old), len(new) - tail, len(new)))
    return codes


def _unified(old: list[str], new: list[str], codes: list[Opcode], fromfile: str, tofile: str) -> Iterator[str]:
    """The unified diff of `codes`, as `difflib.unified_diff` writes it."""
    yield f"--- {fromfile}\n"
    yield f"+++ {tofile}\n"
    for group in _groups(codes):
        first, last = group[0], group[-1]
        yield f"@@ -{_range(first[1], last[2])} +{_range(first[3], last[4])} @@\n"
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                yield from (f" {line}\n" for line in old[i1:i2])
                continue
            yield from (f"-{line}\n" for line in old[i1:i2])
            yield from (f"+{line}\n" for line in new[j1:j2])


def _groups(codes: list[Opcode]) -> Iterator[list[Opcode]]:
    """The changes, each with `CONTEXT` lines around it, those close together in one group (as `difflib` groups)."""
    codes = list(codes)
    if codes[0][0] == "equal":
        tag, i1, i2, j1, j2 = codes[0]
        codes[0] = tag, max(i1, i2 - CONTEXT), i2, max(j1, j2 - CONTEXT), j2
    if codes[-1][0] == "equal":
        tag, i1, i2, j1, j2 = codes[-1]
        codes[-1] = tag, i1, min(i2, i1 + CONTEXT), j1, min(j2, j1 + CONTEXT)
    group: list[Opcode] = []
    for tag, i1, i2, j1, j2 in codes:
        if tag == "equal" and i2 - i1 > 2 * CONTEXT:
            group.append((tag, i1, min(i2, i1 + CONTEXT), j1, min(j2, j1 + CONTEXT)))
            yield group
            group = []
            i1, j1 = max(i1, i2 - CONTEXT), max(j1, j2 - CONTEXT)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        yield group


def _range(start: int, stop: int) -> str:
    """A hunk's lines, as a unified diff writes them: its first line and how many, from 1."""
    beginning, length = start + 1, stop - start
    if length == 1:
        return str(beginning)
    return f"{beginning - 1 if not length else beginning},{length}"
