"""Networking code for one P2P file-sharing peer."""

import socket
import socketserver
import threading
from pathlib import Path

from .config import DISCOVERY_PORT, SOCKET_TIMEOUT
from .index import FileIndex
from .protocol import ProtocolError, receive_message, send_message


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    A TCP server that handles each connection in a thread.
    """

    allow_reuse_address = True
    daemon_threads = True


class PeerRequestHandler(socketserver.BaseRequestHandler):
    """
    Handle one request from another peer.
    """

    def handle(self):
        peer = self.server.peer

        try:
            request = receive_message(self.request)
            response = peer.handle_request(request, self.client_address[0])
        except (OSError, ProtocolError, ValueError, KeyError) as exc:
            response = {"status": "error", "message": str(exc)}

        send_message(self.request, response)


class Peer:
    """
    One running peer in the network.
    """

    def __init__(
        self,
        shared_dir: Path,
        download_dir: Path,
        host: str,
        port: int,
        discovery_port: int = DISCOVERY_PORT,
    ):
        self.shared_dir = Path(shared_dir)
        self.download_dir = Path(download_dir)
        self.host = host
        self.port = port
        self.discovery_port = discovery_port

        self.index = FileIndex(shared_dir)
        self.known_peers = set()
        self.peer_lock = threading.Lock()

        self.tcp_server = None
        self.udp_socket = None
        self.stop_event = threading.Event()

    def start(self):
        """
        Start the TCP peer server.
        """
        self.index.scan()
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self.tcp_server = ThreadedTCPServer(
            (self.host, self.port),
            PeerRequestHandler,
        )
        self.tcp_server.peer = self
        self.port = int(self.tcp_server.server_address[1])

        thread = threading.Thread(target=self.tcp_server.serve_forever, daemon=True)
        thread.start()

    def stop(self):
        """
        Stop the peer.
        """
        self.stop_event.set()

        if self.tcp_server is not None:
            self.tcp_server.shutdown()
            self.tcp_server.server_close()
            self.tcp_server = None

    def add_peer(self, host, port):
        """
        Save a peer address.
        """
        peer = (host, int(port))

        with self.peer_lock:
            self.known_peers.add(peer)

        return peer

    def get_peers(self):
        """
        Return saved peers.
        """
        with self.peer_lock:
            return sorted(self.known_peers)

    def handle_request(self, request, remote_host):
        """
        Handle one JSON command.
        """
        action = request.get("action")

        if action == "HELLO":
            self.add_peer(remote_host, int(request["port"]))
            return {"status": "ok", "host": self.host, "port": self.port}

        if action == "LIST":
            return {"status": "ok", "files": self.get_public_files()}

        if action == "SEARCH":
            query = str(request.get("query", ""))
            return {"status": "ok", "files": self.get_public_files(query)}

        return {"status": "error", "message": f"unknown action: {action}"}

    def connect(self, host, port):
        """
        Connect to another peer."""
        response = self.send_request(host, port, {
            "action": "HELLO",
            "port": self.port,
        })

        self.check_response(response)
        return self.add_peer(host, port)

    def search_remote(self, query):
        """
        Search all known peers.
        """
        results = []

        for host, port in self.get_peers():
            try:
                response = self.send_request(host, port, {
                    "action": "SEARCH",
                    "query": query,
                })
                self.check_response(response)
            except (OSError, ProtocolError, ValueError) as exc:
                results.append({"peer": peer_label(host, port), "error": str(exc)})
                continue

            for item in response.get("files", []):
                item = dict(item)
                item["peer"] = peer_label(host, port)
                item["peer_host"] = host
                item["peer_port"] = port
                results.append(item)

        return results

    def get_public_files(self, query=""):
        """
        Return file metadata to send to another peer.
        """
        if query:
            records = self.index.search(query)
        else:
            records = self.index.all_files()

        return [record.to_public_dict() for record in records]

    def send_request(self, host, port, message):
        """
        Send one request to another peer.
        """
        with socket.create_connection((host, int(port)), timeout=SOCKET_TIMEOUT) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            send_message(sock, message)
            return receive_message(sock)

    def check_response(self, response):
        """
        Raise an error if another peer returned an error.
        """
        if response.get("status") != "ok":
            raise ValueError(str(response.get("message", "peer returned an error")))


def peer_label(host, port):
    """
    Format a peer address.
    """
    return f"{host}:{port}"
