"""The edge's one program (design 0004 §3): it forwards ports to the host, and nothing else.

`python3 edge.py LISTEN_PORT TARGET [LISTEN_PORT TARGET ...]` joins every connection made to a LISTEN_PORT (on every
address of its container) to its TARGET, bytes both ways, until both sides are done: a side that has finished sending
says so to the other (half-close), so an answer still comes back to a request that has been sent whole. A TARGET is a
host and its port, two words (`host.docker.internal 18210`, Docker Desktop's way to the host's loopback), or a Unix
socket, one word (`unix:/run/clank/gateway.sock`, Docker Engine's way: the gateway's socket, in the folder mounted at
/run/clank, design 0014 §3). A connection the target refuses is closed at once: its client hears the end, and what it
sent is read and dropped first, since closing with it unread would reset the connection (a Unix socket refuses before
anything is read). The gateway's port is the first pair, the proxy's the second (design 0024 §2). It uses the standard
library only, so it runs from any image with Python.
"""

import asyncio
import contextlib
import sys

CHUNK = 65536
DRAIN_SECONDS = 1.0  # how long a refused connection's client is read before it is closed anyway
UNIX = "unix:"
USAGE = "usage: edge.py LISTEN_PORT TARGET_HOST TARGET_PORT|LISTEN_PORT unix:SOCKET [...], each port to its target"
Forward = tuple[int, str, int]  # the port listened on, its target (a host, or unix:PATH), the target's port (0: none)


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Bytes from one side to the other, until the first is done; then the second hears that no more come."""
    try:
        while data := await reader.read(CHUNK):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
    except (ConnectionError, OSError):
        pass


async def connect(target: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """A connection to a target: the socket at a `unix:` path, else the host at its port."""
    if target.startswith(UNIX):
        if sys.platform == "win32":  # the type checker's: Unix sockets exist only off Windows
            raise OSError(f"{target} is a Unix socket, reached from Linux only")
        return await asyncio.open_unix_connection(target[len(UNIX) :])
    return await asyncio.open_connection(target, port)


async def join(
    client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, target: str, port: int
) -> None:
    """One connection, joined to the target."""
    try:
        target_reader, target_writer = await connect(target, port)
    except OSError:
        await refuse(client_reader, client_writer)
        return
    await asyncio.gather(pipe(client_reader, target_writer), pipe(target_reader, client_writer))
    for writer in (target_writer, client_writer):
        writer.close()


async def refuse(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """A connection whose target cannot be reached, closed at once: the end said first, then what the client sent read
    and dropped (for `DRAIN_SECONDS` at most), so the close does not reset it."""
    with contextlib.suppress(OSError):
        if writer.can_write_eof():
            writer.write_eof()
    with contextlib.suppress(OSError, TimeoutError):
        async with asyncio.timeout(DRAIN_SECONDS):
            while await reader.read(CHUNK):
                pass
    writer.close()


def said(target: str, port: int) -> str:
    """A target in words: `unix:PATH`, or `HOST:PORT`."""
    return target if target.startswith(UNIX) else f"{target}:{port}"


async def serve(listen_port: int, target: str, port: int) -> asyncio.AbstractServer:
    """Listen on every address, joining each connection to the target; the server, serving."""

    async def joined(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await join(reader, writer, target, port)

    server = await asyncio.start_server(joined, host=None, port=listen_port)
    print(f"edge: port {listen_port} goes to {said(target, port)}", flush=True)
    return server


async def serve_all(forwards: list[Forward]) -> None:
    """Every port served, until ended."""
    servers = [await serve(listen_port, target, port) for listen_port, target, port in forwards]
    await asyncio.gather(*(server.serve_forever() for server in servers))


def forwards(given: list[str]) -> list[Forward] | None:
    """Each port with its target, from the arguments; None when they are not in that form."""
    found: list[Forward] = []
    index = 0
    try:
        while index < len(given):
            listen, target = int(given[index]), given[index + 1]
            if target.startswith(UNIX):
                if target == UNIX:
                    return None
                found.append((listen, target, 0))
                index += 2
            else:
                found.append((listen, target, int(given[index + 2])))
                index += 3
    except (IndexError, ValueError):
        return None
    return found or None


def main(argv: list[str]) -> int:
    """Forward until ended."""
    found = forwards(argv[1:])
    if found is None:
        print(USAGE, file=sys.stderr)
        return 2
    asyncio.run(serve_all(found))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
