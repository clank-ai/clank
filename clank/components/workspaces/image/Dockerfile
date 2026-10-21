# Clank's sandbox image (design 0004 §3, decision 0033: Clank's own): where agents work, one container per workspace.
# Ubuntu 24.04 with Python 3.12, Node.js 22, git, the build tools and ripgrep, and OpenCode at the version Clank knows;
# a user `agent` (uid 1000) whose home is a volume of each workspace's own, its ~/.venv (the folder's own software,
# installed by a workspace's setup) first on the PATH. The edge runs from it too (edge.py). Its tag
# is the checksum of this folder (`sandbox.image_tag`), so a change here builds a new image.
FROM ubuntu:24.04

ARG OPENCODE_VERSION=1.19.0
ARG NODE_MAJOR=22
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install --yes --no-install-recommends \
      ca-certificates curl gnupg git build-essential python3 python3-pip python3-venv ripgrep less nano \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list \
 && apt-get update \
 && apt-get install --yes --no-install-recommends nodejs \
 && npm install --global "opencode-ai@${OPENCODE_VERSION}" \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

# Ubuntu's image has a user `ubuntu` with uid 1000; the agent takes its place.
RUN userdel --remove ubuntu 2>/dev/null; useradd --create-home --uid 1000 --shell /bin/bash agent

COPY edge.py bridge.py phone_mcp.py /opt/clank/
# Every Python finds Clank's sitecustomize: when Matplotlib saves a raster figure in the folder, its geometry is written
# under .clank/figures/ for the annotator (design 0008 §3); nothing else changes, and nothing at all without Matplotlib.
COPY python/ /opt/clank/python/

# A workspace's own software is installed into ~/.venv (design 0004 §10): first on the PATH, so the agent, its terminal
# and the MCP servers it starts find it without being told; and `python` is Python 3 with or without it. The folder is
# mounted from the machine, owned by another user than `agent`, which git refuses ("dubious ownership") until told the
# folder is safe: every session of the model battery stumbled on it (2026-10-15).
RUN ln -s /usr/bin/python3 /usr/local/bin/python && git config --system --add safe.directory /workspace
ENV PATH=/home/agent/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONPATH=/opt/clank/python

USER agent
WORKDIR /workspace
