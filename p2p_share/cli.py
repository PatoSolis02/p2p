"""Command-line interface for the P2P file-sharing app."""

import argparse
import shlex
from pathlib import Path

from .config import DEFAULT_HOST, DEFAULT_PORT
from .peer import Peer, peer_label


HELP_TEXT = """Commands:
  help                         show this help text
  peers                        list known peers
  scan                         rescan the shared directory
  files                        list local shared files
  connect <host> <port>        connect to a peer
  search <query>               search known peers
  download <host> <port> <id>  download a file
  discover                     broadcast a discovery message
  quit                         stop the peer
"""


def build_parser():
    parser = argparse.ArgumentParser(description="Simple P2P file sharing peer")
    parser.add_argument("--shared-dir", type=Path, default=Path("shared"))
    parser.add_argument("--download-dir", type=Path, default=Path("downloads"))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


def main():
    args = build_parser().parse_args()
    peer = Peer(args.shared_dir, args.download_dir, args.host, args.port)
    peer.start()

    print(f"Peer listening on {peer.host}:{peer.port}")
    print(f"Sharing: {args.shared_dir.resolve()}")
    print(f"Downloads: {args.download_dir.resolve()}")
    print(HELP_TEXT)

    try:
        run_prompt(peer)
    finally:
        peer.stop()


def run_prompt(peer):
    while True:
        try:
            raw = input("p2p> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        parts = shlex.split(raw)
        command = parts[0].lower()

        try:
            if command in {"quit", "exit"}:
                break

            if command == "help":
                print(HELP_TEXT)

            elif command == "peers":
                print_peers(peer)

            elif command == "scan":
                count = len(peer.index.scan())
                print(f"Indexed {count} file(s).")

            elif command == "files":
                print_files(peer)

            elif command == "connect":
                require_args(parts, 3)
                connected = peer.connect(parts[1], int(parts[2]))
                print(f"Connected to {peer_label(connected[0], connected[1])}.")

            elif command == "search":
                require_args(parts, 2)
                print_search_results(peer.search_remote(" ".join(parts[1:])))

            elif command == "download":
                require_args(parts, 4)
                path = peer.download(parts[1], int(parts[2]), parts[3])
                print(f"Downloaded to {path}.")

            elif command == "discover":
                peer.broadcast_discovery()
                print("Discovery broadcast sent.")

            else:
                print(f"Unknown command: {command}. Type 'help' for options.")

        except Exception as exc:
            print(f"Error: {exc}")


def require_args(parts, minimum):
    if len(parts) < minimum:
        raise ValueError("missing command argument")


def print_peers(peer):
    peers = peer.get_peers()

    if not peers:
        print("No peers known yet.")
        return

    for index, address in enumerate(peers, start=1):
        print(f"{index}. {peer_label(address[0], address[1])}")


def print_files(peer):
    files = peer.index.all_files()

    if not files:
        print("No local files indexed.")
        return

    for record in files:
        print(
            f"{record.relative_path} | {record.size} bytes | "
            f"{record.chunks} chunk(s) | id={record.file_id}"
        )


def print_search_results(results):
    if not results:
        print("No matches found.")
        return

    for index, item in enumerate(results, start=1):
        if "error" in item:
            print(f"{index}. {item['peer']} | error: {item['error']}")
            continue

        print(
            f"{index}. {item['relative_path']} | {item['size']} bytes | "
            f"peer={item['peer']} | id={item['file_id']}"
        )


if __name__ == "__main__":
    main()