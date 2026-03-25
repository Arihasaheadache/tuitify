import asyncio
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Static, ListItem, ListView, Label, LoadingIndicator
from textual.containers import Vertical, Horizontal
from textual.binding import Binding

from search import MusicSearcher
from player import MusicPlayer

DISK_FRAMES = [
    "     .---.     \n    /     \\    \n    | (O) |    \n    \\     /    \n     '---'     ",
    "     .---.     \n    /  |  \\    \n    |--O--|    \n    \\  |  /    \n     '---'     ",
    "     .---.     \n    /  /  \\    \n    | /O\\ |    \n    \\  /  /    \n     '---'     ",
    "     .---.     \n    /  \\  \\    \n    | \\O/ |    \n    \\  \\  /    \n     '---'     "
]

class LoadingScreen(Screen):
    """A global loading screen that overlays the current view."""
    def compose(self) -> ComposeResult:
        yield LoadingIndicator()

class WelcomeScreen(Screen):
    BINDINGS = [Binding("alt+p", "show_player", "Player")]

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome_box"):
            yield Label("T U I T I F Y", id="welcome_label")
            yield Input(placeholder="Search for music...", id="start_search")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value:
            self.app.perform_search(event.value)

    def action_show_player(self):
        # Only switch to player if there is a song currently loaded
        if getattr(self.app, 'current_song', None):
            self.app.push_screen(PlayerScreen())

class SearchResultsScreen(Screen):
    BINDINGS = [Binding("alt+p", "show_player", "Player")]

    def __init__(self, results):
        super().__init__()
        self.results_map = {s['id']: f"{s['title']} - {s['artist']}" for s in results["songs"]}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="search_container"):
            yield Input(placeholder="Search again...", id="search_input")
            yield ListView(id="search_results")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value:
            self.app.perform_search(event.value)

    def on_mount(self) -> None:
        list_view = self.query_one("#search_results", ListView)
        for vid_id, label in self.results_map.items():
            list_view.append(ListItem(Static(label), id=f"vid_{vid_id}"))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        video_id = event.item.id.replace("vid_", "")
        full_label = self.results_map.get(video_id, "Unknown - Unknown")
        parts = full_label.split(" - ", 1)
        title = parts[0]
        artist = parts[1] if len(parts) > 1 else "Unknown"
        self.app.start_playing(video_id, title, artist)
        self.app.run_worker(self.app.seed_radio_in_background(video_id))

    def action_show_player(self):
        # Only switch to player if there is a song currently loaded
        if getattr(self.app, 'current_song', None):
            self.app.push_screen(PlayerScreen())

class QueueScreen(Screen):
    BINDINGS = [Binding("escape,alt+q,alt+u", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="search_container"):
            yield Label("UP NEXT", id="welcome_label")
            if not self.app.active_radio:
                yield Static("Queue is empty.", id="song_info")
            else:
                yield ListView(*(ListItem(Static(f"{s['title']} - {s['artist']}"), id=f"q_{i}") 
                                 for i, s in enumerate(self.app.active_radio)))
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("q_"):
            index = int(event.item.id.replace("q_", ""))
            next_song = self.app.active_radio[index]
            
            # Add current and skipped songs to history
            if getattr(self.app, 'current_song', None):
                self.app.history.append(self.app.current_song)
            for s in self.app.active_radio[:index]:
                self.app.history.append(s)
            
            # Slice the queue to drop the skipped songs
            self.app.active_radio = self.app.active_radio[index+1:] 
            
            self.app.pop_screen() # Close the queue view
            self.app.start_playing(next_song['id'], next_song['title'], next_song['artist'])

class PlayerScreen(Screen):
    BINDINGS = [
        Binding("alt+u", "view_queue", "Queue"),
        Binding("alt+b", "back_to_search", "Search"),
        Binding("alt+space", "toggle_play", "Play/Pause"),
        Binding("alt+up", "vol_up", "Vol +"),
        Binding("alt+down", "vol_down", "Vol -"),
        Binding("alt+n", "next_song", "Next"),
        Binding("alt+p", "prev_song", "Prev"),
        Binding("alt+right", "seek_forward", "Seek +10s"),
        Binding("alt+left", "seek_backward", "Seek -10s"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(DISK_FRAMES[0], id="disk_area")
        yield Static("Initializing...", id="song_info")
        with Horizontal(id="player_controls"):
            yield Static("00:00/00:00", id="time_info")
            yield Static("[------------------------------]", id="ascii_bar")
            yield Static("VOL: 100%", id="vol_info")
        yield Footer()

    def on_mount(self) -> None:
        self.frame = 0
        self.set_interval(0.2, self.animate_disk)
        self.set_interval(1.0, self.update_status)
        
        # Restore song info if returning to the player while a song is loaded
        if getattr(self.app, 'current_song', None):
            title = self.app.current_song.get('title', 'Unknown')
            artist = self.app.current_song.get('artist', 'Unknown')
            self.query_one("#song_info", Static).update(f"{title} - {artist}")

    def generate_ascii_bar(self, current, total, width=30):
        # Creates a textual progress bar for the player.
        if total <= 0: return "[" + "-" * width + "]"
        progress = int((current / total) * width)
        progress = min(progress, width - 1)
        bar = "=" * progress + ">" + "-" * (width - progress - 1)
        return f"[{bar}]"

    def animate_disk(self) -> None:
        if self.app.player.get_state() == "Playing":
            self.frame = (self.frame + 1) % len(DISK_FRAMES)
            self.query_one("#disk_area", Static).update(DISK_FRAMES[self.frame])

    def update_status(self) -> None:
        curr, total = self.app.player.get_time()
        vol = self.app.player.get_volume()
        self.query_one("#time_info", Static).update(f"{self.app.player.format_time(curr)}/{self.app.player.format_time(total)}")
        self.query_one("#ascii_bar", Static).update(self.generate_ascii_bar(curr, total))
        self.query_one("#vol_info", Static).update(f"VOL: {vol}%")
        
        if self.app.player.is_finished() and self.app.active_radio:
            if getattr(self.app, 'current_song', None):
                self.app.history.append(self.app.current_song)
            next_song = self.app.active_radio.pop(0)
            self.app.start_playing(next_song['id'], next_song['title'], next_song['artist'])

    def action_view_queue(self): self.app.push_screen(QueueScreen())
    def action_back_to_search(self): self.app.pop_screen() # Just pop to reveal screen underneath
    def action_toggle_play(self): self.app.player.toggle_pause()
    def action_vol_up(self): self.app.player.set_volume(self.app.player.get_volume() + 5)
    def action_vol_down(self): self.app.player.set_volume(self.app.player.get_volume() - 5)

    def action_next_song(self):
        if self.app.active_radio:
            if getattr(self.app, 'current_song', None):
                self.app.history.append(self.app.current_song)
            next_song = self.app.active_radio.pop(0)
            self.app.start_playing(next_song['id'], next_song['title'], next_song['artist'])

    def action_prev_song(self):
        if hasattr(self.app, 'history') and self.app.history:
            if getattr(self.app, 'current_song', None):
                self.app.active_radio.insert(0, self.app.current_song)
            prev_song = self.app.history.pop()
            self.app.start_playing(prev_song['id'], prev_song['title'], prev_song['artist'])
        else:
            # Restart current song if there's no history
            self.app.player.seek(-self.app.player.get_time()[0])
            
    def action_seek_forward(self):
        self.app.player.seek(10)
        
    def action_seek_backward(self):
        self.app.player.seek(-10)

class Tuitify(App):
    CSS_PATH = "main.tcss"
    def on_mount(self) -> None:
        self.searcher = MusicSearcher()
        self.player = MusicPlayer()
        self.active_radio = []
        self.history = []
        self.current_song = None
        self.push_screen(WelcomeScreen())

    def perform_search(self, query):
        self.push_screen(LoadingScreen()) # Show loading screen
        self.run_worker(self._search_task(query))

    async def _search_task(self, query):
        # Run blocking search in a background thread
        results = await asyncio.to_thread(self.searcher.get_combined_results, query)
        self.pop_screen() # Remove loading screen
        self.switch_screen(SearchResultsScreen(results))

    async def seed_radio_in_background(self, video_id):
        # Fetches a list of related songs to create an automatic queue.
        self.active_radio = self.searcher.get_radio_queue(video_id)

    def start_playing(self, video_id, title="Unknown", artist="Unknown"):
        self.current_song = {'id': video_id, 'title': title, 'artist': artist}
        self.push_screen(LoadingScreen()) # Show loading while fetching yt-dlp URL
        self.run_worker(self._play_task(video_id, title, artist))

    async def _play_task(self, video_id, title, artist):
        # Run blocking stream extraction in a background thread
        await asyncio.to_thread(self.player.play_song, video_id, title, artist)
        self.pop_screen() # Remove loading screen
        
        # We use push_screen here because we want to be able to 
        # go back to the search results without stopping the music
        if not isinstance(self.screen, PlayerScreen):
            self.push_screen(PlayerScreen())
        self.call_after_refresh(self.set_player_info, f"{title} - {artist}")

    def set_player_info(self, full_title):
        try:
            self.screen.query_one("#song_info", Static).update(full_title)
        except:
            pass

if __name__ == "__main__":
    Tuitify().run()