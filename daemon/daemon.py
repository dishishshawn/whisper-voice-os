#!/usr/bin/env python3
import json
import os
import signal
import socket
import sys
import time
import numpy as np
from faster_whisper import WhisperModel

CONFIG_PATH = os.path.expanduser("~/.config/whisper-ptt/config.json")
DEFAULT_SOCKET = f"/run/user/{os.getuid()}/whisper-ptt.sock"

default_config = {
    "model": "large-v3-turbo",
    "device": "cuda",
    "compute_type": "float16",
    "language": "en",
    "beam_size": 1,
    "vad_filter": True,
    "socket_path": DEFAULT_SOCKET
}

config = default_config.copy()
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config.update(json.load(f))
    except Exception as e:
        print(f"Warning: Failed to load config from {CONFIG_PATH}: {e}", file=sys.stderr)

sock_path = config.get("socket_path", DEFAULT_SOCKET)
if os.path.exists(sock_path):
    try:
        os.unlink(sock_path)
    except OSError:
        pass

print(f"Loading Whisper model '{config['model']}' on {config['device']} ({config['compute_type']})...")
t0 = time.time()
model = WhisperModel(
    config["model"],
    device=config["device"],
    compute_type=config["compute_type"]
)
print(f"Model loaded in {time.time() - t0:.2f}s")

# Warm up CUDA kernels with dummy audio
print("Warming up CUDA kernels...")
dummy_audio = np.zeros(16000, dtype=np.float32)
try:
    _ = list(model.transcribe(dummy_audio, beam_size=1, vad_filter=False)[0])
    print("CUDA warmup complete.")
except Exception as e:
    print(f"Warmup notice: {e}", file=sys.stderr)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(sock_path)
server.listen(5)
print(f"Listening on Unix socket: {sock_path}")

def cleanup_and_exit(signum, frame):
    print("\nShutting down daemon...")
    try:
        server.close()
    except Exception:
        pass
    if os.path.exists(sock_path):
        try:
            os.unlink(sock_path)
        except OSError:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

while True:
    try:
        conn, _ = server.accept()
    except Exception:
        break

    with conn:
        try:
            data = conn.recv(4096).decode("utf-8").strip()
            if not data:
                continue

            req = json.loads(data)
            action = req.get("action", "transcribe")

            if action == "ping":
                conn.sendall(json.dumps({"status": "ok", "message": "pong"}).encode("utf-8"))
                continue

            if action == "transcribe":
                audio_path = req.get("path")
                if not audio_path or not os.path.exists(audio_path):
                    conn.sendall(json.dumps({"status": "error", "message": "File not found"}).encode("utf-8"))
                    continue

                lang = req.get("language", config.get("language", "en"))
                if lang == "auto" or not lang:
                    lang = None

                t_start = time.time()
                segments, info = model.transcribe(
                    audio_path,
                    language=lang,
                    beam_size=config.get("beam_size", 1),
                    vad_filter=config.get("vad_filter", True),
                    vad_parameters=dict(min_silence_duration_ms=500),
                    temperature=0.0
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                duration = time.time() - t_start

                # Filter out pure noise / hallucinations
                hallucinations = {"thank you.", "thank you", "thanks for watching", "subtitles by", "bye."}
                if text.lower() in hallucinations:
                    text = ""

                print(f"Transcribed {info.duration:.2f}s audio in {duration:.3f}s: '{text}'", flush=True)

                resp = {
                    "status": "ok",
                    "text": text,
                    "elapsed_sec": round(duration, 3),
                    "audio_duration": round(info.duration, 2)
                }
                conn.sendall(json.dumps(resp).encode("utf-8"))
            else:
                conn.sendall(json.dumps({"status": "error", "message": f"Unknown action: {action}"}).encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            except Exception:
                pass
