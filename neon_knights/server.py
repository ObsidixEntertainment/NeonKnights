from __future__ import annotations

import argparse
import asyncio
from asyncio import StreamReader, StreamWriter

from .engine import GameSession
from .models import Character
from .world import ANCESTRIES


async def handle_client(reader: StreamReader, writer: StreamWriter) -> None:
    address = writer.get_extra_info("peername")
    await send(writer, "Neon Knights MUD")
    await send(writer, "Enter a handle:")
    name = await read_line(reader)
    if not name:
        writer.close()
        await writer.wait_closed()
        return

    await send(writer, "Choose an ancestry:")
    for key, ancestry in ANCESTRIES.items():
        await send(writer, f"- {ancestry.name} ({key})")

    ancestry_key = ""
    while ancestry_key not in ANCESTRIES:
        await send(writer, "Ancestry key:")
        ancestry_key = (await read_line(reader)).lower()
        if not ancestry_key:
            writer.close()
            await writer.wait_closed()
            return

    session = GameSession(Character(name=name, ancestry=ancestry_key))
    await send(writer, session.intro())

    while session.running:
        await prompt(writer)
        raw = await read_line(reader)
        if not raw:
            break
        await send(writer, session.handle(raw))

    print(f"Disconnected {address}")
    writer.close()
    await writer.wait_closed()


async def send(writer: StreamWriter, text: str) -> None:
    writer.write((text.replace("\n", "\r\n") + "\r\n").encode("utf-8"))
    await writer.drain()


async def prompt(writer: StreamWriter) -> None:
    writer.write(b"\r\n> ")
    await writer.drain()


async def read_line(reader: StreamReader) -> str:
    data = await reader.readline()
    return data.decode("utf-8", errors="ignore").strip()


async def run_server(host: str, port: int) -> None:
    server = await asyncio.start_server(handle_client, host, port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Neon Knights server listening on {sockets}")
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Neon Knights MUD server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4444, type=int)
    args = parser.parse_args()

    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()

