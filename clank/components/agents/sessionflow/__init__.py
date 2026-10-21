"""A session's flow (design 0012 §6, decisions 0049 and 0050): what one OpenCode session did, step by step, kept in the
service for the Monitor to draw and its Watch for rules to read. Not design 0013's flows of boxes, which live in
`clank/components/flows/`.

`flow.py` keeps one session's flow from the bridge's lines and pages of its history; `branches.py` works out its main
branches (a Clank plan's steps, the todo list's items, or the owner's messages); `pairing.py` pairs its steps with the
gateway's requests; `kept.py` keeps a flow for every session the watchers see.
"""
