# 0003. One terminal console both shows and controls everything

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's answer to "Where do you want to make these choices (model, engine, context, temperature,
  ...) day to day?" (chose "One terminal console")

## Context
The prototype shows its state in a web page (and a read-only terminal view) and changes it in a separate
PowerShell menu. The owner asked for the monitor to become "a terminal view similar to htop but more so for
monitoring the model as it works", and to pick the model, the engine and every setting themselves.

## Decision
One terminal application, the console, is both the monitor and the control center: a live view (model, engine,
generation speed, context, GPU and desktop load, activity, the text being generated) and keys that open pickers and
forms for the model, the engine and preset, the context and other launch options, and each role's sampling. Each
change shows what it costs (a restart, memory) before it is applied. Other front ends (menus, the editor) call the
same commands.

## Alternatives considered
- **A monitor-only terminal view, with settings in a menu.** Two places to look; the menu cannot show live effects.
- **A settings file plus commands, the view only showing what is in effect.** Transparent, but edits are a round trip
  through a file; kept as a property of the design instead (decision [0007](0007-settings-in-readable-files.md)).

## Consequences
- The web page of the prototype's monitor is not carried over.
- The console must stay light: it redraws only when something changed and at most a few times a second.
