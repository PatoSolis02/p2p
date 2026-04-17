import json, time, base64, shutil, socket, hashlib, tempfile, threading, socketserver
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
        """
        Handle one request from another peer.
        """
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

        self.messages = []
        self.message_lock = threading.Lock()


    def start(self):
        """
        Start TCP peer server.
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

        if self.discovery_port > 0:
            try:
                self.start_discovery_listener()
                self.broadcast_discovery()
            except OSError:
                self.udp_socket = None


    def stop(self):
        """
        Stop peer.
        """
        if self.udp_socket is not None:
            self.udp_socket.close()
            self.udp_socket = None

        self.stop_event.set()

        if self.tcp_server is not None:
            self.tcp_server.shutdown()
            self.tcp_server.server_close()
            self.tcp_server = None


    def add_peer(self, host, port):
        """
        Save peer address.

        :param host: peer host to add.
        :param port: peer port to add.
        :return: tuple of added peer.
        """
        peer = (host, int(port))
        with self.peer_lock:
            self.known_peers.add(peer)

        return peer


    def get_peers(self):
        """
        Return saved peers.

        :return: sorted list of tuples.
        """
        with self.peer_lock:
            return sorted(self.known_peers)


    def handle_request(self, request, remote_host):
        """
        Handle one JSON command.

        :param request: dict with "action" key and other keys depending on action.
        :param remote_host: host of peer that sent request.
        :return: dict with "status" key and other keys depending on action.
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
        
        if action == "SEARCH_TYPE":
            file_type = str(request.get("file_type", ""))
            return {"status": "ok", "files": self.get_files_by_type(file_type)}

        if action == "CHAT":
            text = str(request.get("message", ""))
            sender_port = int(request.get("port", 0))
            sender = peer_label(remote_host, sender_port)
            self.save_message(sender, text)
            return {"status": "ok"}

        if action == "GET_META":
            record = self.index.get(str(request["file_id"]))
            if record is None:
                return {"status": "error", "message": "file not found"}
            return {"status": "ok", "file": record.to_public_dict()}

        if action == "GET_CHUNK":
            return self.send_chunk(request)

        return {"status": "error", "message": f"unknown action: {action}"}


    def connect(self, host, port):
        """
        Connect to another peer.

        :param host: peer host to connect to.
        :param port: peer port to connect to.
        :return: tuple of connected peer.
        """
        response = self.send_request(host, port, {
            "action": "HELLO",
            "port": self.port,
        })
        self.check_response(response)

        return self.add_peer(host, port)


    def search_remote(self, query):
        """
        Search all known peers.

        :param query: search query string.
        :return: list of dicts with peer and file metadata for each search result.
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

        :param query: optional search query string to filter results.
        :return: list of dicts with file metadata for each matching file.
        """
        if query:
            records = self.index.search(query)
        else:
            records = self.index.all_files()

        return [record.to_public_dict() for record in records]


    def send_request(self, host, port, message):
        """
        Send one request to another peer.

        :param host: peer host to connect to.
        :param port: peer port to connect to.
        :param message: dict to send as JSON command.
        :return: dict response from peer.
        """
        with socket.create_connection((host, int(port)), timeout=SOCKET_TIMEOUT) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            send_message(sock, message)
            return receive_message(sock)


    def check_response(self, response):
        """
        Raise error if another peer returned an error.

        :param response: dict response from peer.
        """
        if response.get("status") != "ok":
            raise ValueError(str(response.get("message", "peer returned an error")))


    def send_chunk(self, request):
        """
        Send one file chunk to another peer.

        :param request: dict with "file_id" and "chunk_index" keys.
        :return: dict with status, chunk index, base64-encoded data, and sha256 hex digest keys.
        """
        file_id = str(request["file_id"])
        chunk_number = int(request["chunk_index"])
        record = self.index.get(file_id)
        if record is None:
            return {"status": "error", "message": "file not found"}

        if chunk_number < 0 or chunk_number >= record.chunks:
            return {"status": "error", "message": "chunk index out of range"}
        chunk = self.index.chunk(file_id, chunk_number)

        return {
            "status": "ok",
            "chunk_index": chunk_number,
            "data": base64.b64encode(chunk).decode("ascii"),
            "sha256": hashlib.sha256(chunk).hexdigest(),
        }


    def download_chunk(self, host, port, file_id, chunk_number):
        """
        Download one chunk from another peer.

        :param host: peer host to connect to.
        :param port: peer port to connect to.
        :param file_id: ID of file to download from peer.
        :param chunk_number: index of chunk to download.
        :return: bytes of downloaded chunk.
        """
        response = self.send_request(host, port, {
            "action": "GET_CHUNK",
            "file_id": file_id,
            "chunk_index": chunk_number,
        })
        self.check_response(response)

        chunk = base64.b64decode(str(response["data"]).encode("ascii"))
        peer_hash = str(response["sha256"])
        if hashlib.sha256(chunk).hexdigest() != peer_hash:
            raise ValueError(f"peer sent bad chunk {chunk_number}")

        return chunk


    def download(self, host, port, file_id, progress_callback=None):
        """
        Download a file from another peer.

        :param host: peer host to connect to.
        :param port: peer port to connect to.
        :param file_id: ID of file to download from peer.
        :param progress_callback: function to call with download progress.
        :return: path to downloaded file.
        """
        response = self.send_request(host, port, {
            "action": "GET_META",
            "file_id": file_id,
        })
        self.check_response(response)

        metadata = response["file"]
        target_path = self.safe_download_path(str(metadata["relative_path"]))
        target_path.parent.mkdir(parents=True, exist_ok=True)

        expected_file_hash = str(metadata["sha256"])
        expected_chunk_hashes = list(metadata["chunk_hashes"])
        total_chunks = int(metadata["chunks"])
        final_hash = hashlib.sha256()
        with tempfile.NamedTemporaryFile(delete=False, dir=target_path.parent) as temp_file:
            temp_path = Path(temp_file.name)
            try:
                for chunk_number in range(total_chunks):
                    chunk = self.download_chunk(host, port, file_id, chunk_number)
                    chunk_hash = hashlib.sha256(chunk).hexdigest()
                    if chunk_hash != expected_chunk_hashes[chunk_number]:
                        raise ValueError(f"chunk {chunk_number} failed hash check")
                    temp_file.write(chunk)
                    final_hash.update(chunk)
                    if progress_callback is not None:
                        progress_callback(chunk_number + 1, total_chunks)
            except Exception:
                temp_file.close()
                temp_path.unlink(missing_ok=True)
                raise

        if final_hash.hexdigest() != expected_file_hash:
            temp_path.unlink(missing_ok=True)
            raise ValueError("downloaded file failed final hash check")
        shutil.move(str(temp_path), target_path)

        return target_path


    def safe_download_path(self, relative_path):
        """
        Make sure downloads stay inside downloads folder.

        :param relative_path: path relative to downloads folder returned by peer.
        :return: absolute path to target file.
        """
        target = (self.download_dir / relative_path).resolve()
        root = self.download_dir.resolve()
        if root != target and root not in target.parents:
            raise ValueError("peer returned unsafe download path")

        return target


    def broadcast_discovery(self):
        """
        Send a UDP discovery message.
        """
        if self.discovery_port <= 0:
            return

        message = json.dumps({
            "service": "p2p-share",
            "port": self.port,
        }).encode("utf-8")

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for host in ("255.255.255.255", "127.0.0.1"):
                try:
                    udp.sendto(message, (host, self.discovery_port))
                except OSError:
                    pass


    def start_discovery_listener(self):
        """
        Start listening for UDP discovery messages.
        """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind(("", self.discovery_port))
        self.udp_socket.settimeout(0.5)

        thread = threading.Thread(target=self.discovery_loop, daemon=True)
        thread.start()


    def discovery_loop(self):
        """
        Listen for other peers.
        """
        while not self.stop_event.is_set():
            try:
                payload, address = self.udp_socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                message = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            if message.get("service") != "p2p-share":
                continue

            port = int(message.get("port", 0))
            if port <= 0:
                continue
            if port == self.port and address[0] in {"127.0.0.1", self.host}:
                continue

            self.add_peer(address[0], port)
            try:
                self.connect(address[0], port)
            except (OSError, ProtocolError, ValueError):
                time.sleep(0.1)


    def send_chat(self, host, port, text):
        """
        Send a chat message to another peer.

        :param host: peer host to connect to.
        :param port: peer port to connect to.
        :param text: message text to send.
        """
        response = self.send_request(host, port, {
            "action": "CHAT",
            "port": self.port,
            "message": text,
        })

        self.check_response(response)


    def save_message(self, sender, text):
        """
        Save a received message.

        :param sender: string label of peer that sent message.
        :param text: message text to save.
        """
        with self.message_lock:
            self.messages.append({"from": sender, "message": text,})


    def get_messages(self):
        """
        Return received messages.

        :return: list of dicts with "from" and "message" keys.
        """
        with self.message_lock:
            return list(self.messages)


    def search_type_remote(self, file_type):
        """
        Search known peers by file extension.

        :param file_type: file extension to search for.
        :return: list of dicts with peer and file metadata for each search result.
        """
        results = []

        for host, port in self.get_peers():
            try:
                response = self.send_request(host, port, {
                    "action": "SEARCH_TYPE",
                    "file_type": file_type,
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


    def get_files_by_type(self, file_type):
        """
        Return local files matching an extension.

        :param file_type: file extension to search for.
        :return: list of dicts with file metadata.
        """
        records = self.index.search_by_type(file_type)
        return [record.to_public_dict() for record in records]


def peer_label(host, port):
    """
    Format a peer address.

    :param host: peer host.
    :param port: peer port.
    :return: string label for peer.
    """
    return f"{host}:{port}"
