"""The `clank` command: a client of the Clank API, like the console and the VS Code extension (design 0002 §2.15).

Each command calls the API and prints readable text, or JSON with `--json`; only `clank serve`, `clank doctor` and
`clank setup` act without the service. Each component adds its commands to the top-level group in `main.py`.
"""
