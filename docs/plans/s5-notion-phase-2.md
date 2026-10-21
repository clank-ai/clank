# Notion, phase 2: implementation plan

> At the owner's request (2026-10-17): "go ahead and start phase 2, and just immediately test things and commit and
> push to github, and move on to phase 3". As for the plan mode's plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0010 §11, phase 2: the review in VS Code (§6), as the owner chose it from the mockups (D: the table of
a database with its changes, and the chosen entry's fields and page): the Notion changes view, the count waiting in
the status bar, the review page, and approval of what is checked, some fields of an entry included.

**Spec:** [design 0010](../design/0010-notion.md) §6 and §8.

## Global Constraints

- Never the owner's Notion: the service's tests use the fake Notion; the extension's use a fake API and headless Edge.
- The page shows and asks; approving, rejecting and opening a link go through the extension to the service.
- The owner is the sole author of every commit; American English; tests named as sentences.

## Tasks

- [x] **Approval in parts:** `approve(..., parts={proposal: [property names, "page", "removal"]})` writes only those;
  what is written is kept on the proposal (`done`: the parts, the entry, its last edit after Clank's write, which the
  next part is checked against); a new entry is made with its title and its other parts are written to it later; a
  batch in brief says how many proposals wait (`left`) (`tests/components/notion/test_review_service.py`).
- [x] **The tables:** `GET notion/batches/<id>/tables[?everything=true]`: each database of the batch with its columns
  and rows marked same, added, changed or removed, a changed cell with what it was; the changed rows and their
  neighbors, or every row (`tables.py`, the same tests).
- [x] **The view and the count:** `vscode/src/core/notion.ts` (`NotionReviews`: the batches read on connecting and
  followed with the events; open, rows, approve, reject; `treeOf`, the words), wired into the controller
  (`vscode/test/notion.test.ts`); `vscode/src/notion.ts` (the tree, the status bar's item and the view's badge, the
  page's panel); the view container, its commands and menus in `package.json`.
- [x] **The page:** `vscode/media/notion.html|css|js`: the table, the database tabs, the checkboxes (a new entry's
  title kept with its other parts), Fields, Page and As in Notion, the choices kept when shown again
  (`vscode/test/notion.page.test.ts`, in headless Edge; `test/browser.ts` shared with the annotator's test).
- [x] **Documents:** design 0010 (*as built*), this plan, `docs/notion-setup.md` part 5, the extension's README; the
  extension 0.7.0.
