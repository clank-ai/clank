// "Annotate this PDF" (design 0020 §10): the service renders a PDF of the window's folder as pages (built by Clank first
// when its .tex is beside it, so SyncTeX finds each mark's line); the page to mark up is the only one, or the one
// picked. What is opened, and in what, is extension.ts's: the figure annotator, beside the agent.

import type { Api } from "./controller";
import type { Choice } from "./presenter";

interface Rendered {
  pdf: string;
  built: boolean;
  pages: Array<{ number: number; image: string }>;
}

/** The page image to mark up, from the folder; `error` in the service's words; undefined when the pick was dismissed. */
export async function pageToMark(
  api: Api,
  folder: string,
  pdf: string,
  pick: (items: Array<Choice<string>>, placeholder: string) => Promise<string | undefined>,
): Promise<{ image: string } | { error: string } | undefined> {
  let rendered: Rendered;
  try {
    rendered = await api.post<Rendered>("agents/latex/pages", { folder, pdf });
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
  if (rendered.pages.length === 1) {
    return { image: rendered.pages[0]!.image };
  }
  const how = rendered.built ? "as Clank built it (its lines found by SyncTeX)" : "as it is";
  const chosen = await pick(
    rendered.pages.map((page) => ({
      label: `Page ${page.number} of ${rendered.pages.length}`,
      detail: `${rendered.pdf}, ${how}`,
      value: page.image,
    })),
    "Which page to mark up?",
  );
  return chosen === undefined ? undefined : { image: chosen };
}
