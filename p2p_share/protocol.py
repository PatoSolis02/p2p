import json

from .config import MAX_MESSAGE_SIZE

class ProtocolError(Exception):
    """
    Raised when a peer sends a bad message.
    """

def send_message(sock, message):
    """
    Send one JSON message ending with a newline.

    :param sock: socket to send message on.
    :param message: dictionary to send as JSON message.
    """
    data = json.dumps(message).encode("utf-8") + b"\n"
    if len(data) > MAX_MESSAGE_SIZE:
        raise ProtocolError("message is too large")
    sock.sendall(data)


def receive_message(sock):
    """
    Receive one JSON message ending with a newline.

    :param sock: socket to receive message from.
    :return: dictionary parsed from JSON message.
    """
    chunks = []
    total = 0
    while True:
        byte = sock.recv(1)
        if byte == b"":
            raise ProtocolError("connection closed")
        if byte == b"\n":
            break

        chunks.append(byte)
        total += 1
        if total > MAX_MESSAGE_SIZE:
            raise ProtocolError("message is too large")
    try:
        message = json.loads(b"".join(chunks).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid JSON") from exc

    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")

    return message