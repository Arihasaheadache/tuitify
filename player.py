import os
import time
import yt_dlp
import vlc
import json
import threading
from websocket import create_connection

# DLL Setup
dll_path = os.path.abspath("dll")
if os.path.exists(dll_path):
    os.add_dll_directory(dll_path)

class MusicPlayer:
    class NullLogger:
        # Suppresses yt-dlp console output by overriding its logger.
        def debug(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    def __init__(self):
        self.instance = vlc.Instance('--no-video', '--quiet', '--control=ntsm') 
        self.player = self.instance.media_player_new()
        self.ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'no_warnings': True, 'logger': self.NullLogger()}
        
        self.current_metadata = {"title": "Unknown", "artist": "Unknown"}
        self.ws_url = "ws://127.0.0.1:8974"

    def broadcast_to_rainmeter(self):
        # Sends current song metadata to a local WebSocket for Rainmeter integration.
        def _send():
            try:
                curr, total = self.get_time()
                state_map = {"Playing": 1, "Paused": 2, "Stopped": 0}
                state_val = state_map.get(self.get_state(), 0)

                data = {
                    "player": "Tuitify",
                    "title": self.current_metadata["title"],
                    "artist": self.current_metadata["artist"],
                    "album": "YouTube Music",
                    "status": state_val,
                    "position": curr,
                    "duration": total,
                    "volume": self.get_volume()
                }
                
                ws = create_connection(self.ws_url, timeout=0.1)
                ws.send(json.dumps(data))
                ws.close()
            except:
                pass 

        threading.Thread(target=_send, daemon=True).start()

    def play_song(self, video_id, title="Unknown", artist="Unknown"):
        # Extracts a direct stream URL from a YouTube video ID and plays it.
        self.current_metadata = {"title": title, "artist": artist}
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                stream_url = info['url']
            
            media = self.instance.media_new(stream_url)
            self.player.set_media(media)
            self.player.play()
        except Exception as e:
            pass

    def toggle_pause(self): self.player.pause()
    def stop(self): self.player.stop()
    def seek(self, seconds): 
        curr = self.player.get_time()
        self.player.set_time(max(0, curr + (seconds * 1000)))

    def set_volume(self, volume): self.player.audio_set_volume(max(0, min(volume, 100)))
    def get_volume(self): return self.player.audio_get_volume()
    def get_time(self): return self.player.get_time() // 1000, self.player.get_length() // 1000
    def format_time(self, seconds): return f"{max(0, seconds) // 60:02d}:{max(0, seconds) % 60:02d}"
    
    def get_state(self):
        s = self.player.get_state().value
        return {0: "Nothing", 1: "Opening", 2: "Buffering", 3: "Playing", 4: "Paused", 5: "Stopped", 6: "Ended"}.get(s, "Error")
    
    def is_finished(self): return self.get_state() == "Ended"