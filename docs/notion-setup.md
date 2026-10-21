# Setting up Notion for Clank

How to set up your Notion so Clank's local agent can read your research databases and propose changes that you review
in VS Code before anything is written (design 0010). You do all of this yourself, in Notion; nothing here needs Claude
Code. Clank assumes no layout: the layouts in part 3 are suggestions to start from, and you can change them, or add
databases, at any time.

## 1. One home page for your research

1. In Notion, make a page named **Research** (any name works). Every database Clank should see goes inside it.
2. Sharing this one page with Clank (part 2) shares everything inside it, including databases you add later. Anything
   outside it stays invisible to Clank.

## 2. The Clank integration

1. Open **Settings → Connections → Develop or manage integrations** (or go to notion.so/profile/integrations), then
   **New integration**:
   - Name: **Clank**; type: **Internal**; workspace: yours.
   - Capabilities: **Read content**, **Update content**, **Insert content**. Leave comments and user information off.
2. Save, then copy the **Internal Integration Secret**. Keep it private: it is the key to everything you share.
3. Open your **Research** page, then **•••** (top right) → **Connections** → add **Clank**. Confirm that it may see
   the page and the pages inside it.
4. Connect Clank: in a terminal, run `clank notion connect` and paste the secret when asked. It is not shown as you
   type. Clank keeps it in its secrets folder, readable only by you.
5. Check: `clank notion status` says which integration and workspace Clank reached, and `clank notion databases` lists
   every database Clank can see, with its properties. A database missing from that list is not shared yet.

To take access away at any time: **Connections** on the Research page → remove Clank, or delete the integration.

## 3. The databases

Make each one as a full-page database inside **Research** (type `/database` and choose the full-page kind). The layout
below is only an example, two databases with a relation between them; the types matter more than the names. Make the
**Papers** database first, then **Concepts**, then add the relation between them.

### Papers

| property | type | what it holds |
| --- | --- | --- |
| Title | Title | the paper's title |
| Authors | Text | "Doe, Roe" (surnames, in order) |
| Year | Number | 2021 (in the number format without commas) |
| Venue | Text | "J. Example Stud. 12, 345", or "arXiv preprint" |
| arXiv | Text | "2101.00001" (the id only) |
| DOI | URL | the DOI link, when it has one |
| Keywords | Multi-select | sampling, graphs, numerics, ... (your vocabulary; reuse options rather than adding near duplicates) |
| Reading | Status or Select | To read, Reading, Notes written, Done |
| Concepts | Relation → Concepts | added in step 4 below |

**A template for each paper's notes page** (in the database's **New** menu → **New template**), so every page has
the same sections:

1. **Summary**: two or three sentences.
2. **Setup**: the model, the method, the conventions.
3. **Definitions**: each one with where it is in the paper ("§3.2, Eq. (12)").
4. **Results**: each with its figure, table or equation number.
5. **Implementation**: exactly what to reproduce: parameters, sizes, seeds, choices the paper makes.
6. **My notes**: anything else.

### Concepts

A concept is a quantity, a method or a definition your work uses.

| property | type | what it holds |
| --- | --- | --- |
| Name | Title | "Mixing time" |
| Symbol | Text | "t_mix" |
| Definition | Text | one line; the full definition goes on the page |
| Category | Select | your own categories, such as quantities, methods, definitions |
| Defined in | Relation → Papers | the papers that define or use it |
| Where | Text | where in those papers: "Doe & Roe 2021: §3, Eq. (5); Fig. 2" |
| Code | Text | the function that computes it, such as `analysis.mixing_time` |
| Computed by | URL or Text | the script that computes it from your saved results (a path, or a link to the file) |
| Status | Select | Draft, Checked, Published |
| Related | Relation → Concepts | other concepts it builds on |

**A template for each concept's page:**

1. **Definition**: the formula (type `/equation` for a block equation, `$$` for one inside a line).
2. **Conventions**: units, normalization, what is averaged over.
3. **In the literature**: each paper as a mention (type `@` and the paper's title), then the place:
   "@Doe, Roe 2021, §3, Eq. (5)".
4. **How it is computed**: the script, the function, and the checks it passes.
5. **Notes.**

### 4. The relation between them

1. In **Papers**, add the property **Concepts**: type **Relation**, pointing to **Concepts**, with **Show on
   Concepts** turned on. Name the other side **Defined in**. (If you already made **Defined in** on Concepts, make it
   two-way instead.)
2. Cite in pages with mentions (`@` and the entry's title), followed by the section, equation, figure or table. Clank's
   agent writes its citations the same way.

### Later: more databases

Once Papers and Concepts have entries, more databases (a **Results** database, each big run with its plots, its data
and links to its concepts and scripts; a database per project, linking to the others) follow the same pattern.

## 5. A test database first

Before Clank works with your real databases, check it once with made-up data:

1. Inside **Research**, make a page **Clank test** holding a small **Papers (test)** database with the same
   properties as Papers, and two or three entries you make up ("A test paper", "Someone, Else", 2001, ...).
2. Ask the agent to read it, then to propose one change and one new entry and submit them.
3. Review them in VS Code: **Notion changes** in the activity bar (the database icon; the status bar says how many
   wait) lists the batch; click it to open its review. Uncheck a field or a row to leave it staged, then **Approve N
   checked**; or **Reject…** with a reason. Check the result in Notion. From a terminal instead: `clank notion
   batches`, `clank notion show <batch>`, `clank notion approve <batch>` (or `--only p1`), `clank notion reject
   <batch>`.
4. Send one back: comment on a field or a paragraph (the speech bubble beside it), then **Send back with 1 comment**.
   The agent (its OpenCode window must be open) revises the batch and answers the comment; the revision comes back to
   the view, the answer under your comment.
5. Delete the test page when you are satisfied.
