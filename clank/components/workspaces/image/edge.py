"""The edge's one program (design 0004 §3): it forwards ports to the host, and nothing else.

`python3 edge.py LISTEN_PORT TARGET_HOST TARGET_PORT [LISTEN_PORT TARGET_HOST TARGET_PORT ...]` joins every connection
made to a LISTEN_PORT (on every address of its container) to its TARGET_HOST:TARGET_PORT, bytes both ways, until both
sides are done: a side that has finished sending says so to the other (half-close), so an answer still comes back to
a request that has been sent whole. A connection the target refuses is closed at once. The gateway's port is the
first pair, the proxy's the second (design 0024 §2). It uses the standard library only, so it runs from any image
with Python.
"""

import asyncio
import sys

CHUNK = 65536


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


async def join(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, host: str, port: int) -> None:
    """One connection, joined to the target."""
    try:
        target_reader, target_writer = await asyncio.open_connection(host, port)
    except OSError:
        client_writer.close()
        return
    await asyncio.gather(pipe(client_reader, target_writer), pipe(target_reader, client_writer))
    for writer in (target_writer, client_writer):
        writer.close()


async def serve(listen_port: int, host: str, port: int) -> asyncio.AbstractServer:
    """Listen on every address, joining each connection to the target; the server, serving."""

    async def joined(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await join(reader, writer, host, port)

    server = await asyncio.start_server(joined, host=None, port=listen_port)
    print(f"edge: port {listen_port} goes to {host}:{port}", flush=True)
    return server


async def serve_all(pairs: list[tuple[int, str, int]]) -> None:
    """Every pair served, until ended."""
    servers = [await serve(listen_port, host, port) for listen_port, host, port in pairs]
    await asyncio.gather(*(server.serve_forever() for server in servers))


def main(argv: list[str]) -> int:
    """Forward until ended."""
    given = argv[1:]
    if not given or len(given) % 3:
        print(
            "usage: edge.py LISTEN_PORT TARGET_HOST TARGET_PORT [LISTEN_PORT TARGET_HOST TARGET_PORT ...]",
            file=sys.stderr,
        )
        return 2
    pairs = [(int(given[i]), given[i + 1], int(given[i + 2])) for i in range(0, len(given), 3)]
    asyncio.run(serve_all(pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
