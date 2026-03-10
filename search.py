import json
from ytmusicapi import YTMusic

class MusicSearcher:
    def __init__(self):
        self.yt = YTMusic()

    def get_combined_results(self, query, limit=3):
        # Searches for songs, albums, and artists and combines the results.
        output = {"songs": [], "albums": [], "artists": []}

        for cat in ["songs", "albums", "artists"]:
            raw = self.yt.search(query, filter=cat, limit=limit)
            for item in raw:
                if cat == "songs":
                    output["songs"].append({
                        "id": item.get('videoId'),
                        "title": item.get('title'),
                        "artist": ", ".join([a['name'] for a in item.get('artists', [])]),
                        "album": item.get('album', {}).get('name', 'N/A')
                    })
                elif cat == "albums":
                    output["albums"].append({
                        "browseId": item.get('browseId'),
                        "title": item.get('title'),
                        "artist": item.get('artists', [{}])[0].get('name', 'N/A')
                    })
                elif cat == "artists":
                    output["artists"].append({
                        "browseId": item.get('browseId'),
                        "name": item.get('artist') or item.get('title')
                    })
        return output

    def get_artist_details(self, artist_id):
        """For the artist 'snippet' and top tracks."""
        data = self.yt.get_artist(artist_id)
        return {
            "name": data.get('name'),
            "description": data.get('description', 'No bio available.'),
            "top_songs": [{"id": s['videoId'], "title": s['title']} for s in data.get('songs', {}).get('results', [])]
        }

    def get_radio_queue(self, video_id):
        # Gets the YouTube Music "watch playlist" which is a radio-like queue of related songs.
        watch_data = self.yt.get_watch_playlist(videoId=video_id, limit=20)
        
        radio_tracks = []
        for track in watch_data.get('tracks', [])[1:]:
            radio_tracks.append({
                "id": track.get('videoId'),
                "title": track.get('title'),
                "artist": ", ".join([a['name'] for a in track.get('artists', [])])
            })
        return radio_tracks