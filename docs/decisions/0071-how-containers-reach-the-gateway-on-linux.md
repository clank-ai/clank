# 0071. How containers reach the gateway on Linux: a socket only the edge mounts, or a guarded listener; never 0.0.0.0

- Status: Accepted: option (a), a socket only the edge mounts, as recommended (2026-10-27, at the owner's instruction,
  while design 0014's review goes on)
- Date: 2026-10-18; accepted 2026-10-27
- Decided by: proposed by Claude from the research of 2026-10-18
  ([design 0014](../design/0014-linux-and-small-machines.md) §3); decided by the owner's instruction of 2026-10-27,
  taken as the word to build design 0014's steps L5 and L6 with the recommended option: "I want to begin testing clank
  by itself on a completely separate linux computer that I have where I will only be testing the integration with the
  API keys from openrouter, so we need to make sure that this is completely set up and ready for testing."

## Context
- A workspace's agent reaches the gateway only through the edge. The edge is a container on Clank's outer network. It
  forwards the gateway's port to `host.docker.internal`, which it maps to `host-gateway`
  (`clank/components/workspaces/sandbox.py:38, 154-169`; `clank/components/workspaces/image/edge.py`).
- The gateway listens on 127.0.0.1 only (`clank/components/gateway/server.py:611`). Design 0001 §6.6 says it listens
  "on this machine only, unless the user allows other machines, and then only with a token".
- On Docker Desktop, `host.docker.internal` reaches the host's loopback. On Docker Engine, `host-gateway` resolves to
  the default bridge's address (https://docs.docker.com/reference/cli/dockerd/), where nothing listens. So on Linux
  without Docker Desktop, the agent reaches no model.
- The gateway asks no caller for credentials. It also forwards `/notion/...` to the service as the client `agent`
  (`clank/components/gateway/server.py:134-143, 607`). Whoever reaches it may use the model, and may read the owner's
  Notion as the agent.
- The edge has more jobs to come. Design 0002 makes it each sandbox's only door: to the gateway, the tool hub and the
  Clank service, and out to git or the web only by grant (§1). It enforces `net.connect`, `git.fetch` and `git.push`:
  "The sandbox has no other way out" (§2.6). The service listens on 127.0.0.1 only, as the gateway does
  (`clank/kernel/service_kinds.py:40`); the tool hub is not built yet (M8).
- The safety floor: no container sees `CLANK_HOME`
  ([design 0002 §2.6](../design/0002-the-foundation.md#26-policy), `docs/design/0002-the-foundation.md:284-287`). And
  Clank touches nothing outside `CLANK_HOME` except what the user approves in the guide (design 0001 §7.2).
- A Pi joins other networks, such as a shared Wi-Fi. A gateway on every address (`0.0.0.0`) would face them. Linux
  answers for any of its addresses on any of its interfaces.

## Decision
**Never `0.0.0.0`.** Under (a) the gateway listens on no new address at all; under (b) its one new address refuses
every peer outside Clank's outer network, other computers included. Docker Desktop keeps its path on every system. The
gateway keeps its 127.0.0.1 listener for the host's own tools. On Linux, for Docker Engine, the owner chooses (a) or
(b). **(a) is recommended.**

**(a) A Unix socket, mounted into the edge only.**
- On Linux, the gateway also listens on `gateway.sock`, in a folder of its own outside `CLANK_HOME`. By default the
  folder is `~/.cache/clank/<home id>/` (`$XDG_CACHE_HOME/clank/<home id>/` when that is set). A setting in
  `config/gateway.json`, `socket_folder`, can move it. It is the one folder Clank keeps outside `CLANK_HOME`, a
  refinement of design 0001 §7.2 that design 0014 §1 lists. The gateway removes its socket when it stops, the empty
  folder stays until Clank is removed, and `clank doctor` names it.
- The folder is the owner's alone (mode 0700), and so is the socket (0600).
  - The gateway makes the socket itself, and hands both of its listeners to Uvicorn (`Server.run(sockets=...)`).
    Uvicorn's own socket option would leave it open to every user (`uds_perms = 0o666`, `uvicorn/server.py:168` in
    Uvicorn 0.54.0).
  - The socket is bound inside its 0700 folder and set to 0600 before it listens. The process's umask is never
    changed: it is the whole process's, and the routes thread already runs (`clank/components/gateway/server.py:605`).
  - The TCP socket the gateway now makes itself reuses its address (`SO_REUSEADDR`, as asyncio set it), and a port
    another program holds ends the gateway as Uvicorn did, logged, with exit status 3.
- The folder is never inside or holding `CLANK_HOME`, the folder Clank itself runs from, or a workspace's folder, and
  never the home folder itself (as `clank/components/workspaces/folders.py:77-96` checks a workspace's folder).
  Opening a workspace refuses a folder that holds it or is inside it. The gateway checks `CLANK_HOME`, the folder
  Clank runs from and the home folder; the workspaces component, which knows every workspace and uses the gateway,
  checks the workspaces' folders.
- The gateway's status names the socket. A gateway that runs without it (one started before this change and adopted,
  or one whose folder was removed) is started again once no request is in flight.
- On Docker Engine, the edge mounts that folder read-only, as its only mount, and forwards to the socket. It runs as
  the owner's user id, so it may open the socket. Clank's outer network stays as it is, as on Docker Desktop: the
  edge's way out, which its jobs in M7 need.
- The edge mounts the folder, not the socket. A gateway that starts again makes a new socket in the same folder, and
  the edge sees it.

**(b) A second listener on the bridge address, refusing peers outside Clank's outer network.**
- On Linux, the gateway also listens on the host's address on Clank's outer network. That is the network's gateway
  address, which Docker picks when it makes the network. The edge forwards to that address.
- The gateway refuses every connection whose peer address is outside that network's subnet.

## Alternatives considered
- **(b), not recommended.** For it: no mount into the edge, no folder outside `CLANK_HOME`, the edge keeps the image's
  user, and the path stays TCP, as on Docker Desktop. Against it:
  - The address exists only once Docker has made the outer network. The gateway starts with the service, before any
    workspace opens. So it must wait for the network, or the service must make the network first. A removed network
    takes the address away.
  - A Linux host takes packets for any of its addresses on any interface. Every container on the machine, any
    program's, can reach that address. So can another computer on the same network, if it routes the bridge's subnet
    to the Pi. The peer check by address is then the only guard in front of the model and the owner's Notion, against
    other containers and other computers alike.
  - A host firewall can drop traffic from a Docker bridge to the host (ufw refuses incoming connections by default).
    Only root can allow it, and Clank never acts as root ([decision 0070](0070-a-docker-engine-adapter.md)).
- **(a) with Clank's outer network made internal**, so the edge would reach nothing but the socket. The edge is to be
  each sandbox's way out (design 0002 §1, §2.6), and M7 needs that route. Rejected: the outer network stays as it is.
- **`0.0.0.0`.** It faces every network the machine joins. Never.
- **The default bridge's address (`host-gateway`), with no peer check.** Every container on that bridge, any program's,
  would reach the model and the owner's Notion.
- **The edge on the host's network (`--network host`).** It would reach 127.0.0.1. But Docker cannot join such a
  container to other networks, so it could not be each workspace's door. And it would listen on every address of the
  host itself.
- **Docker's `host-gateway-ip` set to another address.** It is set in Docker's own `daemon.json`, a file of root's that
  Clank does not edit. And the gateway would still have to listen at that address.
- **A token the edge adds.** The gateway checks no token today. A token in the edge's command or environment can be
  read by anyone who may inspect containers. Process tokens may come with endpoints (design 0015).
- **A forwarder on the host** (socat, or ssh). Another program to install, start and watch.
- **The socket in `/tmp` or in `$XDG_RUNTIME_DIR`.** `/tmp` is every user's. systemd removes `$XDG_RUNTIME_DIR` when
  the user's last session ends, while the service may go on.

## Consequences
(a) was chosen (2026-10-27). If (a) is chosen:
- On Linux the gateway has a second listener, and its process gets the socket's path from its service. Test:
  `test_on_linux_the_gateway_also_listens_where_only_the_edge_reaches_it`.
- Only the owner's processes, root and the edge can open the socket. No network faces it, and no firewall rule is
  needed.
- Clank keeps one folder outside `CLANK_HOME`. Removing Clank means removing it too, and the doctor names it.
- `edge.py` gains a Unix target, with the standard library. The sandbox image's tag is its folder's checksum
  (`clank/components/workspaces/sandbox.py:219-226`), so every machine builds the image again once.
- On Docker Engine the edge runs as the owner's user id, not as the image's `agent`.
- If the socket's folder itself is removed and made again while the edge runs, the edge keeps the old one. So opening a
  workspace asks the gateway's health through the edge, and makes the edge again when it does not answer.
- A socket's path holds at most 107 bytes on Linux. A longer one is refused, saying so.
- A socket cannot cross a virtual machine, so Docker Desktop for Linux keeps its own path. Rootless Docker maps user
  ids, and hosts with SELinux may need a label on the mount: neither is covered.
- When the edge needs the service and the tool hub on Docker Engine (M7, M8), they take the same path: a socket each
  in the same folder. Their designs say so.

If (b) is chosen:
- The gateway has a second TCP listener with a peer check, and the service makes the outer network before it starts
  the gateway. Tests: the one above, and `test_a_peer_outside_clanks_network_is_refused`.
- Where the host has a firewall, the rule that lets the edge in is the owner's to add.

Either way:
- The escape tests on Linux also try the host's own address on each workspace's network (design 0014 §4).
- The escape tests' stand-in gateway (127.0.0.1 only, `tests/docker/test_escape.py:46`) listens where the gateway does
  on each platform.
