# P2P File Sharing Project

This project is a simple peer-to-peer file-sharing application written in
Python.

## Requirements

- Python 3.11 or newer
- Install documentation tools with:

```powershell
pip install -r requirements.txt
```

## Run Two Peers

Terminal 1:

```powershell
python -m p2p_share.cli --shared-dir shared_a --download-dir downloads_a --port 9001
```

Terminal 2:

```powershell
python -m p2p_share.cli --shared-dir shared_b --download-dir downloads_b --port 9002
```

## Example Commands

```text
connect 127.0.0.1 9001
scan
files
search notes
type txt
message 127.0.0.1 9001 hello
messages
download 127.0.0.1 9001 <file_id>
quit
```

## Extra Features

Because the group has three students, these extra features were added:

- Download progress bar
- Peer chat and messaging
- File type filtering
