#!/usr/bin/env python3
import json
import os
import socket
import sys

def main():
    if len(sys.argv) < 3:
        print("Usage: client.py <sock_path> <audio_path>", file=sys.stderr)
        sys.exit(1)

    sock_path = sys.argv[1]
    audio_path = sys.argv[2]

    if not os.path.exists(audio_path):
        sys.exit(0)

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(15.0)
        s.connect(sock_path)
        payload = json.dumps({"action": "transcribe", "path": audio_path}).encode("utf-8")
        s.sendall(payload)

        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        s.close()

        raw = b"".join(chunks).decode("utf-8")
        resp = json.loads(raw)
        if resp.get("status") == "ok":
            text = resp.get("text", "").strip()
            print(text)
            sys.exit(0)
        else:
            err = resp.get("message", "Unknown error")
            print(f"Daemon error: {err}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Client exception: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
