Implement the plan in this file: $ARGUMENTS

(When no file is named above, ask the user which plan to implement: plans are Markdown files whose header says
`kind: plan`.)

The plan is the single source. Read it whole before anything else, then the folder's AGENTS.md for how work runs here.

1. When the header's status is `draft`, or its Open questions are not empty, ask the user (question tool) whether to
   go on.
2. Set the header to `status: implementing`.
3. Take the first step not ticked and do exactly what it says. Then tick it (`- [x]`) and add one line to the plan's
   Log: the date, what was done, the files it made, and any deviation. Then take the next step.
4. Follow the plan exactly. When a step is wrong or ambiguous, or a check fails, stop and ask with the question tool
   instead of improvising. Never change the plan's Question, Parameters or Plots without asking.
5. Run the work as the plan's Cost and the folder's AGENTS.md say (long runs in the background, each with its own
   output folder). Write each run's actual runtime and size in the Log beside the plan's cost; when one exceeds the
   plan's cost by more than half, stop and ask.
6. The last step makes the deliverables exactly as the plan's Deliverables section says: every number in them from a
   script's output or a saved file, never your own arithmetic, and every plot embedded.
7. When every step is ticked, set `status: done` and tell the user where the deliverables are.

When the session grows long, stop at the end of a step: the next session goes on with `/implement $ARGUMENTS`, from
the first step not ticked.
