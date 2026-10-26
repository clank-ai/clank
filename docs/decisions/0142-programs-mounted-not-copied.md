# 0142. Clank's programs in the container are mounted read-only, not copied into the image

- Status: Accepted (design 0023 §7, approved by the owner on 2026-10-26; built with plan s50, task 1)
- Date: 2026-10-26
- Decided by: Claude, building design 0023, which says this choice is made first since the bridge changes most

## Context

The sandbox image copied `edge.py`, `bridge.py`, `phone_mcp.py`, `find_figures.py` and `python/sitecustomize.py` into
`/opt/clank`, and its tag was the checksum of the whole image folder, instructions included. So each change to the
bridge or to a line of the agent's instructions rebuilt a 2 GB image and remade every container (ending the agent's
sessions in them): 32 image tags were found on the owner's machine on 2026-10-26, several of them a day old. Design
0023 changes the bridge in each of its steps.

## Decision

- The image folder (`clank/components/workspaces/image/`, as the running service has it) is mounted read-only at
  `/opt/clank` in every container Clank runs: a workspace's, its setup's and the edge's (`ContainerSpec.programs`).
- The Dockerfile copies none of those files; `/opt/clank` is only made in the image, for the mount.
- The image's tag is the checksum of its Dockerfile alone: the image changes when what is installed changes, and only
  then. The layers' tags stay the checksum of the base's tag and the layer's files (the TeX layer copies its helper).
- The agent's own copies (its MCP server and instructions written into its home at each start, design 0018 §7.5)
  stay as they are: they come from the same folder.

## Alternatives considered

- **Copying, as before**: every program change a rebuild and a remake; the owner's sessions end for a one-line fix.
- **Mounting the whole package**: more than the container needs, and a path into the service's own code.
- **A volume Clank fills at start**: a copy to keep current, with a version to compare; the mount is always current.

## Consequences

- A container always runs the bridge the service runs: no version skew between the two, and no "from before
  design 0007" state for a watch (`watch.py`) once the containers are made again.
- The folder is a path of the machine in `docker run`'s arguments (a package folder, not the owner's files).
- Containers made before this run the copied programs until they are next stopped and opened, as with any new image.
