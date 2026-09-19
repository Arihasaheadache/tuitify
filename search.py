import concurrent.futures
from typing import List, Dict, Any, Optional
from ytmusicapi import YTMusic

class SearchEngine:
    def __init__(self):
        self.yt = YTMusic()
        self.cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    def search_songs_now(self, query: str) -> List[Dict[str, Any]]:
        query_clean = query.strip().lower()
        if query_clean not in self.cache:
            self.cache[query_clean] = {"songs": [], "albums": [], "artists": []}

        raw_songs = self.yt.search(query, filter="songs", limit=15)
        parsed_songs = []
        for s in raw_songs:
            artists = ", ".join([a['name'] for a in s.get('artists', [])])
            parsed_songs.append({
                "type": "song",
                "id": s.get('videoId'),
                "title": s.get('title', 'Unknown'),
                "artist": artists or "Unknown",
                "duration": s.get('duration', '--:--')
            })
        self.cache[query_clean]["songs"] = parsed_songs

        self.executor.submit(self._fetch_albums_task, query, query_clean)
        self.executor.submit(self._fetch_artists_task, query, query_clean)

        return parsed_songs

    def _fetch_albums_task(self, raw_query: str, cache_key: str):
        try:
            raw = self.yt.search(raw_query, filter="albums", limit=10)
            albums = []
            for a in raw:
                artists = ", ".join([art['name'] for art in a.get('artists', [])])
                albums.append({
                    "type": "album",
                    "id": a.get('browseId'),
                    "title": a.get('title', 'Unknown'),
                    "artist": artists or "Unknown",
                    "year": a.get('year', '')
                })
            self.cache[cache_key]["albums"] = albums
        except Exception:
            pass

    def _fetch_artists_task(self, raw_query: str, cache_key: str):
        try:
            raw = self.yt.search(raw_query, filter="artists", limit=10)
            artists = []
            for art in raw:
                artists.append({
                    "type": "artist",
                    "id": art.get('browseId'),
                    "name": art.get('artist', 'Unknown'),
                    "subscribers": art.get('subscribers', '')
                })
            self.cache[cache_key]["artists"] = artists
        except Exception:
            pass

    def get_cached(self, query: str, category: str) -> List[Dict[str, Any]]:
        query_clean = query.strip().lower()
        return self.cache.get(query_clean, {}).get(category, [])

    def get_album_details(self, browse_id: str) -> Dict[str, Any]:
        try:
            raw = self.yt.get_album(browse_id)
            tracks = []
            for t in raw.get("tracks", []):
                tracks.append({
                    "type": "song",
                    "id": t.get("videoId"),
                    "title": t.get("title"),
                    "artist": raw.get("artists", [{}])[0].get("name", "Unknown"),
                    "duration": t.get("duration", "--:--")
                })
            return {
                "title": raw.get("title", "Unknown Album"),
                "artist": ", ".join([a['name'] for a in raw.get('artists', [])]),
                "year": raw.get("year", ""),
                "tracks": tracks
            }
        except Exception:
            return {"title": "Error", "artist": "", "tracks": []}

    def get_artist_details(self, browse_id: str) -> Dict[str, Any]:
        try:
            raw = self.yt.get_artist(browse_id)
            
            # Extract top songs
            songs = []
            for s in raw.get("songs", {}).get("results", [])[:5]:
                artists = ", ".join([a['name'] for a in s.get('artists', [])])
                songs.append({
                    "type": "song",
                    "id": s.get("videoId"),
                    "title": s.get("title"),
                    "artist": artists or raw.get("name", "Unknown"),
                    "duration": s.get("duration", "--:--")
                })

            # Extract artist albums / singles
            albums = []
            raw_albums = raw.get("albums", {}).get("results", [])
            for a in raw_albums:
                albums.append({
                    "type": "album",
                    "id": a.get("browseId"),
                    "title": a.get("title", "Unknown Album"),
                    "artist": raw.get("name", "Unknown"),
                    "year": a.get("year", "")
                })

            return {
                "name": raw.get("name", "Unknown"),
                "description": raw.get("description") or "No biography available.",
                "subscribers": raw.get("subscribers", ""),
                "top_songs": songs,
                "albums": albums
            }
        except Exception:
            return {"name": "Error", "description": "", "subscribers": "", "top_songs": [], "albums": []}

    def get_radio_queue(self, video_id: str) -> List[Dict[str, str]]:
        try:
            watch_playlist = self.yt.get_watch_playlist(videoId=video_id, limit=20)
            tracks = []
            for item in watch_playlist.get("tracks", []):
                if item.get("videoId") == video_id:
                    continue
                artists = ", ".join([a['name'] for a in item.get('artists', [])])
                tracks.append({
                    "id": item.get("videoId"),
                    "title": item.get("title", "Unknown"),
                    "artist": artists or "Unknown",
                    "duration": item.get("length", "--:--")
                })
            return tracks
        except Exception:
            return []