"""File indexing and hashing for shared files."""

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from .config import CHUNK_SIZE


@dataclass
class FileRecord:
    """
    Information about one shared file.
    """

    file_id: str
    name: str
    relative_path: str
    size: int
    sha256: str
    chunk_size: int
    chunk_hashes: tuple

    @property
    def chunks(self):
        if self.size == 0:
            return 1
        return math.ceil(self.size / self.chunk_size)

    def to_public_dict(self):
        return {
            "file_id": self.file_id,
            "name": self.name,
            "relative_path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
            "chunk_size": self.chunk_size,
            "chunks": self.chunks,
            "chunk_hashes": list(self.chunk_hashes),
        }


class FileIndex:
    """
    Keeps track of files in the shared folder.
    """

    def __init__(self, shared_dir, chunk_size=CHUNK_SIZE):
        self.shared_dir = Path(shared_dir).resolve()
        self.chunk_size = chunk_size
        self.records = {}
        self.paths = {}

    def scan(self):
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        self.records = {}
        self.paths = {}

        for path in sorted(self.shared_dir.rglob("*")):
            if path.is_file():
                record = self.build_record(path)
                self.records[record.file_id] = record
                self.paths[record.file_id] = path

        return self.all_files()

    def all_files(self):
        return sorted(self.records.values(), key=lambda item: item.relative_path)

    def search(self, query):
        query = query.lower().strip()

        if not query:
            return self.all_files()

        return [
            record
            for record in self.all_files()
            if query in record.name.lower()
            or query in record.relative_path.lower()
        ]

    def get(self, file_id):
        return self.records.get(file_id)

    def chunk(self, file_id, chunk_number):
        path = self.paths[file_id]

        with path.open("rb") as file_obj:
            file_obj.seek(chunk_number * self.chunk_size)
            return file_obj.read(self.chunk_size)

    def build_record(self, path):
        file_hash = hashlib.sha256()
        chunk_hashes = []
        size = 0

        with path.open("rb") as file_obj:
            while True:
                chunk = file_obj.read(self.chunk_size)

                if chunk == b"":
                    break

                size += len(chunk)
                file_hash.update(chunk)
                chunk_hashes.append(hashlib.sha256(chunk).hexdigest())

        if size == 0:
            chunk_hashes.append(hashlib.sha256(b"").hexdigest())

        relative_path = path.relative_to(self.shared_dir).as_posix()
        digest = file_hash.hexdigest()
        file_id = hashlib.sha256(
            f"{relative_path}:{size}:{digest}".encode()
        ).hexdigest()

        return FileRecord(
            file_id=file_id,
            name=path.name,
            relative_path=relative_path,
            size=size,
            sha256=digest,
            chunk_size=self.chunk_size,
            chunk_hashes=tuple(chunk_hashes),
        )