import os
import sys
import json
import time
import socket
import tempfile
import subprocess
import threading
from typing import Optional, Tuple, Dict, Any
import yt_dlp

class MusicPlayer:
    def __init__(self, mpv_bin: str = "mpv"):
        self.mpv_bin = mpv_bin
        self.process: Optional[subprocess.Popen] = None
        self.ipc_path = self._generate_ipc_path()
        self.current_song: Dict[str, str] = {"title": "Nothing Playing", "artist": ""}
        self.is_paused = False
        self._lock = threading.Lock()
        self._is_terminating = False

        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
        self.ydl = yt_dlp.YoutubeDL(self.ydl_opts)

        self._spawn_daemon()

    def _generate_ipc_path(self) -> str:
        if sys.platform == "win32":
            return r"\\.\pipe\tuitify_mpv_socket"
        return os.path.join(tempfile.gettempdir(), f"tuitify_mpv_{os.getpid()}.sock")

    def _spawn_daemon(self):
        if sys.platform != "win32" and os.path.exists(self.ipc_path):
            try:
                os.unlink(self.ipc_path)
            except OSError:
                pass

        cmd = [
            self.mpv_bin,
            "--idle=yes",
            "--no-video",
            "--no-terminal",
            f"--input-ipc-server={self.ipc_path}",
            "--audio-display=no",
            "--gapless-audio=yes"
        ]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        time.sleep(0.25)

    def _send_command(self, command: list, timeout: float = 0.2) -> Optional[Dict[str, Any]]:
        """Non-blocking command dispatcher with strict timeout prevention."""
        if self._is_terminating:
            return None

        # Non-blocking lock attempt to avoid deadlocking during teardown
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            return None

        try:
            payload = json.dumps({"command": command}) + "\n"
            if sys.platform == "win32":
                with open(self.ipc_path, "r+b", buffering=0) as pipe:
                    pipe.write(payload.encode("utf-8"))
                    res = pipe.readline().decode("utf-8")
                    return json.loads(res) if res else None
            else:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout)
                    sock.connect(self.ipc_path)
                    sock.sendall(payload.encode("utf-8"))
                    res = sock.recv(4096).decode("utf-8")
                    for line in res.splitlines():
                        if line.strip():
                            return json.loads(line)
        except Exception:
            return None
        finally:
            self._lock.release()

        return None

    def play_song(self, video_id: str, title: str = "Unknown", artist: str = "Unknown") -> bool:
        if self._is_terminating:
            return False

        self.current_song = {"title": title, "artist": artist}
        self.is_paused = False

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            info = self.ydl.extract_info(video_url, download=False)
            stream_url = info.get('url')
            if stream_url and not self._is_terminating:
                self._send_command(["loadfile", stream_url, "replace"])
                return True
        except Exception:
            return False
        return False

    def toggle_pause(self) -> bool:
        self._send_command(["cycle", "pause"])
        self.is_paused = not self.is_paused
        return self.is_paused

    def stop(self):
        """Immediately stops audio playback without hanging."""
        self._send_command(["stop"], timeout=0.1)
        self.is_paused = False

    def seek(self, seconds: int):
        self._send_command(["seek", seconds, "relative"])

    def set_volume(self, volume: int):
        vol = max(0, min(volume, 100))
        self._send_command(["set_property", "volume", vol])

    def get_volume(self) -> int:
        if self._is_terminating:
            return 100
        res = self._send_command(["get_property", "volume"])
        if res and "data" in res and res["data"] is not None:
            return int(res["data"])
        return 100

    def get_time(self) -> Tuple[int, int]:
        if self._is_terminating:
            return 0, 0
        pos_res = self._send_command(["get_property", "time-pos"])
        dur_res = self._send_command(["get_property", "duration"])

        pos = int(pos_res["data"]) if pos_res and pos_res.get("data") is not None else 0
        dur = int(dur_res["data"]) if dur_res and dur_res.get("data") is not None else 0
        return pos, dur

    def is_finished(self) -> bool:
        if self._is_terminating:
            return False
        res = self._send_command(["get_property", "idle-active"])
        if res and "data" in res:
            return bool(res["data"])
        return False

    def format_time(self, seconds: int) -> str:
        s = max(0, seconds)
        return f"{s // 60:02d}:{s % 60:02d}"

    def quit(self):
        """Signals shutdown flag, terminates mpv directly, and cleans up sockets."""
        self._is_terminating = True

        # Quick asynchronous quit signal to daemon
        try:
            self._send_command(["quit"], timeout=0.05)
        except Exception:
            pass

        # Immediate process kill
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        # Remove socket file
        if sys.platform != "win32" and os.path.exists(self.ipc_path):
            try:
                os.unlink(self.ipc_path)
            except OSError:
                pass