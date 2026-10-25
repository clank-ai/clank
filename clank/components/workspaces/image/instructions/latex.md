# Writing LaTeX in this folder

Clank checks every change you make to a LaTeX file (`.tex`, `.bib`, `.cls`, `.sty`, `.bst`) before the user sees it.
A change that breaks one of these rules is refused, with the reason; fix what it says and propose the change again.

- Cite only entries of the document's bibliography (the `.bib` files its `\bibliography` or `\addbibresource` loads).
  Never invent a citation key.
- To add an entry to a `.bib` file, give it `doi = {...}`, or `eprint = {...}` with `archivePrefix = {arXiv}`. Clank
  looks the identifier up and refuses an entry whose title, first author or year its record does not match. For a work
  with neither (a book, a talk), ask the user to add it.
- Every paragraph you add or change that states a value (a decimal, a percentage, a number in scientific notation, an
  integer of three digits or more) carries, within it, a comment naming where the value comes from:
  `% source: <a file of the folder, a key of the bibliography, a DOI or an arXiv id>`. When you have not checked it,
  write `% UNVERIFIED: <what is not checked>` instead. Never present an unchecked claim as checked.
- Keep the document building: no undefined `\ref` or `\cite`, no label defined twice, no error.
- Keep the document's own macros, packages and style, and change only what you were asked to change.
- When the user sends numbered marks or comments, answer each by its number: what you changed and on which lines, or
  why you did not.
- The user reviews each change to their own `.tex` files, one by one: keep each change small and about one thing.
