"""The edge's one program (design 0004 §3): it forwards one port to the host, and nothing else.

`python3 edge.py LISTEN_PORT TARGET_HOST TARGET_PORT` joins every connection made to LISTEN_PORT (on every address of
its container) to TARGET_HOST:TARGET_PORT, bytes both ways, until both sides are done: a side that has finished sending
says so to the other (half-close), so an answer still comes back to a request that has been sent whole. A connection
the target refuses is closed at once. It uses the standard library only, so it runs from any image with Python.
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


async def serve(listen_port: int, host: str, port: int) -> None:
    """Listen on every address, joining each connection to the target."""

    async def joined(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await join(reader, writer, host, port)

    server = await asyncio.start_server(joined, host=None, port=listen_port)
    print(f"edge: port {listen_port} goes to {host}:{port}", flush=True)
    async with server:
        await server.serve_forever()


def main(argv: list[str]) -> int:
    """Forward until ended."""
    if len(argv) != 4:
        print("usage: edge.py LISTEN_PORT TARGET_HOST TARGET_PORT", file=sys.stderr)
        return 2
    asyncio.run(serve(int(argv[1]), argv[2], int(argv[3])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
