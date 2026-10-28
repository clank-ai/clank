"""Citations and the bibliography (design 0020 §6): no citation the agent writes may name an entry the bibliography
does not have, and no entry it adds may be one its record does not confirm.

`cite_keys` reads every citation of a LaTeX text, in the forms natbib and biblatex give (`\\cite`, `\\citep`, `\\citet`,
`\\citealt`, `\\citeauthor`, `\\citeyear`, `\\parencite`, `\\textcite`, `\\autocite`, `\\footcite`, `\\smartcite`,
`\\supercite`, `\\fullcite`, `\\nocite`, capitalized and starred, with up to two optional arguments), comments left
out, each key with its line. `bibliographies` names the `.bib` files a document loads (`\\bibliography{a,b}`,
`\\addbibresource{x.bib}`), from its own folder. `bib_entries` reads a `.bib` file's entries (`@comment`, `@string` and
`@preamble` left out), each with its type, its line and its fields, lowercase.

`missing_citations` says, for a change, each citation it adds whose key is no entry, or that it cites with no
bibliography loaded; a key the file cited before is the owner's, not the change's. `entry_problems` checks each entry
a change to a `.bib` file adds or changes: it must have a DOI or an arXiv id (`eprint` with `archivePrefix` or
`eprinttype` arXiv, or an `arxiv` field), and the record found for it (`Lookup`: Crossref for a DOI, arXiv's API for an
id; each looked up once) must have its title (nearly: case, braces, accents and spacing aside), its first author's
family name and its year (an arXiv paper's year or the next, for a journal's version). A record that cannot be reached
leaves the entry for the owner to check.
"""

import json
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher

COMMANDS = (
    r"[Cc]ite(?:p|t|alt|alp|author|year|yearpar|num|text)?|[Pp]arencite|[Tt]extcite|[Aa]utocite|[Ff]ootcite|"
    r"[Ss]martcite|[Ss]upercite|[Ff]ullcite|nocite"
)
CITE = re.compile(rf"\\(?:{COMMANDS})\*?\s*(?:\[[^\]]*\]\s*){{0,2}}\{{([^}}]*)\}}")
BIBLIOGRAPHY = re.compile(r"\\bibliography\s*\{([^}]*)\}")
RESOURCE = re.compile(r"\\addbibresource\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
ENTRY = re.compile(r"@\s*([A-Za-z]+)\s*[{(]\s*([^,\s]+)\s*,")
SKIPPED = {"comment", "string", "preamble"}
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
SAME_TITLE = 0.9  # how alike two titles must be, from 0 to 1
SECONDS = 20.0
Fetch = Callable[[str], bytes]


@dataclass(frozen=True)
class Cited:
    """One citation: its key and its line."""

    key: str
    line: int


@dataclass
class Entry:
    """A bibliography entry: its type, its key, its line, and its fields by lowercase name."""

    kind: str
    key: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Record:
    """What a DOI's or an arXiv id's record says: title, first author's family name, year; none when it has no such
    work."""

    title: str
    author: str
    year: int


def uncommented(text: str) -> str:
    """The text with its comments blanked out (from an unescaped % to its line's end), its lines where they were."""
    return re.sub(r"(?<!\\)%.*", "", text)


def cite_keys(text: str) -> list[Cited]:
    """Every citation's keys, in order, with their lines; `\\nocite{*}` is none."""
    found: list[Cited] = []
    plain = uncommented(text)
    for match in CITE.finditer(plain):
        line = plain.count("\n", 0, match.start()) + 1
        for key in match.group(1).split(","):
            if key.strip() and key.strip() != "*":
                found.append(Cited(key.strip(), line))
    return found


def bibliographies(text: str) -> list[str]:
    """The `.bib` files a document loads, from its folder."""
    plain = uncommented(text)
    named = [name.strip() for match in BIBLIOGRAPHY.finditer(plain) for name in match.group(1).split(",")]
    files = [name if name.endswith(".bib") else f"{name}.bib" for name in named if name]
    return files + [match.group(1).strip() for match in RESOURCE.finditer(plain)]


def bib_entries(text: str) -> dict[str, Entry]:
    """The entries of a `.bib` file, by key."""
    found: dict[str, Entry] = {}
    for match in ENTRY.finditer(text):
        kind = match.group(1).lower()
        if kind in SKIPPED:
            continue
        body = _body(text, match.end())
        entry = Entry(kind, match.group(2), text.count("\n", 0, match.start()) + 1, _fields(body))
        found[entry.key] = entry
    return found


def missing_citations(before: str | None, after: str, known: set[str], *, loaded: bool) -> list[str]:
    """Each citation the change adds whose key is no entry of the document's bibliographies, as a refusal."""
    had = {each.key for each in cite_keys(before or "")}
    problems = []
    for cited in cite_keys(after):
        if cited.key in had:
            continue
        if not loaded:
            problems.append(
                f"\\cite{{{cited.key}}} on line {cited.line}: the document loads no bibliography (\\bibliography or "
                "\\addbibresource), so no citation can be checked: cite only once the user's bibliography is loaded"
            )
        elif cited.key not in known:
            problems.append(
                f"\\cite{{{cited.key}}} on line {cited.line}: no bibliography of the document has an entry "
                f"{cited.key}; cite an entry that is there, or propose the entry with its DOI or arXiv id"
            )
    return problems


class Lookup:
    """Records of DOIs (Crossref) and arXiv ids (arXiv's API), each fetched once; `fetch` reads a URL."""

    def __init__(self, fetch: Fetch | None = None) -> None:
        self.fetch: Fetch = fetch or _fetch
        self._known: dict[str, Record | None] = {}

    def doi(self, doi: str) -> Record | None:
        """The work a DOI names, or None when Crossref has none; OSError when it cannot be reached."""
        key = f"doi:{doi.lower()}"
        if key not in self._known:
            try:
                answer = json.loads(self.fetch(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"))
            except LookupError:
                self._known[key] = None
            else:
                work = answer.get("message") or {}
                authors = work.get("author") or [{}]
                year = ((work.get("issued") or {}).get("date-parts") or [[0]])[0][0] or 0
                titles = work.get("title") or [""]
                self._known[key] = Record(titles[0], str(authors[0].get("family") or ""), int(year))
        return self._known[key]

    def arxiv(self, id: str) -> Record | None:
        """The paper an arXiv id names, or None when arXiv has none; OSError when it cannot be reached."""
        key = f"arxiv:{id.lower()}"
        if key not in self._known:
            atom = "{http://www.w3.org/2005/Atom}"
            found = ElementTree.fromstring(self.fetch(f"https://export.arxiv.org/api/query?id_list={id}"))
            entry = found.find(f"{atom}entry")
            title = entry.findtext(f"{atom}title") if entry is not None else None
            if entry is None or not title or (entry.findtext(f"{atom}id") or "").endswith("/api/errors"):
                self._known[key] = None
            else:
                name = entry.findtext(f"{atom}author/{atom}name") or ""
                published = (entry.findtext(f"{atom}published") or "0")[:4]
                self._known[key] = Record(" ".join(title.split()), name.split()[-1] if name else "", int(published))
        return self._known[key]


def entry_problems(before: str | None, after: str, lookup: Lookup) -> tuple[list[str], list[str]]:
    """The refusals for the entries a change to a `.bib` file adds or changes, and those that could not be looked up
    (for the owner)."""
    had = bib_entries(before or "")
    problems: list[str] = []
    unchecked: list[str] = []
    for key, entry in bib_entries(after).items():
        old = had.get(key)
        if old is not None and _identity(old) == _identity(entry):
            continue
        named = f"@{entry.kind}{{{key}}}"
        doi, arxiv = entry.fields.get("doi", "").strip(), _arxiv(entry)
        if not doi and not arxiv:
            problems.append(
                f"{named} on line {entry.line}: it has no DOI and no arXiv id, so it cannot be checked: give its doi "
                "or its eprint (with archivePrefix = {arXiv}); for a work with neither, ask the user to add it"
            )
            continue
        where = f"DOI {doi}" if doi else f"arXiv {arxiv}"
        try:
            record = lookup.doi(doi) if doi else lookup.arxiv(arxiv)
        except (OSError, ValueError, ElementTree.ParseError) as error:
            unchecked.append(f"{named}: {where} could not be looked up ({error}): the user checks it")
            continue
        if record is None:
            problems.append(f"{named} on line {entry.line}: {where} has no such paper; give the right identifier")
            continue
        wrong = _mismatches(entry, record, arxiv_only=not doi)
        if wrong:
            problems.append(
                f"{named} on line {entry.line}: {where} says: {record.title!r}, {record.author}, {record.year}; the "
                f"entry has {', '.join(wrong)}. Correct the entry from the record, or give the right identifier"
            )
    return problems, unchecked


def _mismatches(entry: Entry, record: Record, *, arxiv_only: bool) -> list[str]:
    """What of the entry the record does not confirm: its title, its first author, its year."""
    wrong = []
    title = entry.fields.get("title", "")
    if SequenceMatcher(None, _plain(title), _plain(record.title)).ratio() < SAME_TITLE:
        wrong.append(f"title {title!r}")
    first = _first_author(entry.fields.get("author", ""))
    if record.author and _plain(record.author) not in _plain(first):
        wrong.append(f"first author {first or '(none)'}")
    year = _year(entry)
    allowed = {record.year, record.year + 1} if arxiv_only else {record.year}
    if record.year and year not in allowed:
        wrong.append(f"year {year or '(none)'}")
    return wrong


def _identity(entry: Entry) -> tuple[str, ...]:
    return tuple(entry.fields.get(name, "") for name in ("title", "author", "year", "date", "doi", "eprint", "arxiv"))


def _arxiv(entry: Entry) -> str:
    fields = entry.fields
    prefix = (fields.get("archiveprefix") or fields.get("eprinttype") or "").lower()
    if fields.get("eprint") and prefix == "arxiv":
        return fields["eprint"].strip().removeprefix("arXiv:")
    return fields.get("arxiv", "").strip().removeprefix("arXiv:")


def _first_author(authors: str) -> str:
    first = re.split(r"\s+and\s+", authors.strip())[0]
    return first.split(",")[0].strip() if "," in first else (first.split()[-1] if first.split() else "")


def _year(entry: Entry) -> int:
    found = re.search(r"\d{4}", entry.fields.get("year") or entry.fields.get("date") or "")
    return int(found.group()) if found else 0


def _plain(text: str) -> str:
    """Letters and digits only, lowercase, accents and LaTeX's braces and commands left out."""
    text = re.sub(r"\\[a-zA-Z]+\s*", "", text)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed.lower() if char.isalnum())


def _body(text: str, start: int) -> str:
    """An entry's text from after its key to its closing brace, braces matched."""
    depth = 1
    for index in range(start, len(text)):
        if text[index] in "{(":
            depth += 1
        elif text[index] in "})":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return text[start:]


def _fields(body: str) -> dict[str, str]:
    """An entry's fields: `name = {value}`, `"value"` or a bare word, by lowercase name."""
    fields: dict[str, str] = {}
    index = 0
    while True:
        found = re.compile(r"\s*([A-Za-z][\w-]*)\s*=\s*").match(body, index) or re.compile(
            r"[^A-Za-z]*([A-Za-z][\w-]*)\s*=\s*"
        ).match(body, index)
        if found is None:
            return fields
        index = found.end()
        value, index = _value(body, index)
        fields[found.group(1).lower()] = " ".join(value.split())
        comma = body.find(",", index)
        if comma < 0:
            return fields
        index = comma + 1


def _value(body: str, index: int) -> tuple[str, int]:
    if index < len(body) and body[index] == "{":
        depth, start = 0, index
        for at in range(index, len(body)):
            if body[at] == "{":
                depth += 1
            elif body[at] == "}":
                depth -= 1
                if depth == 0:
                    return body[start + 1 : at], at + 1
        return body[start + 1 :], len(body)
    if index < len(body) and body[index] == '"':
        end = body.find('"', index + 1)
        end = len(body) if end < 0 else end
        return body[index + 1 : end], end + 1
    found = re.compile(r"[^,}\s]+").match(body, index)
    return (found.group(), found.end()) if found else ("", index)


def _fetch(url: str) -> bytes:
    """A URL's answer; LookupError for a 404 (no such work), OSError when it cannot be reached."""
    request = urllib.request.Request(url, headers={"User-Agent": "Clank (https://clank-ai.github.io)"})
    try:
        with urllib.request.urlopen(request, timeout=SECONDS) as answer:
            data: bytes = answer.read()
            return data
    except urllib.error.HTTPError as error:
        error.close()  # its answer's body, unread, is let go of here
        if error.code == 404:
            raise LookupError(f"404 for {url}") from error
        raise OSError(f"{url} answered {error.code}") from error
