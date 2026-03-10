import asyncio
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Static, ListItem, ListView, Label
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

class WelcomeScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="welcome_box"):
            yield Label("T U I T I F Y", id="welcome_label")
            yield Input(placeholder="Search for music...", id="start_search")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value:
            self.app.perform_search(event.value)

class SearchResultsScreen(Screen):
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

class QueueScreen(Screen):
    BINDINGS = [Binding("escape,q,u", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="search_container"):
            yield Label("UP NEXT", id="welcome_label")
            if not self.app.active_radio:
                yield Static("Queue is empty.", id="song_info")
            else:
                yield ListView(*(ListItem(Static(f"{s['title']} - {s['artist']}")) for s in self.app.active_radio))
        yield Footer()

class PlayerScreen(Screen):
    BINDINGS = [
        Binding("u", "view_queue", "Queue"),
        Binding("b", "back_to_search", "Search"),
        Binding("space", "toggle_play", "Play/Pause"),
        Binding("equal", "vol_up", "Vol +"),
        Binding("minus", "vol_down", "Vol -"),
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
            next_song = self.app.active_radio.pop(0)
            self.app.start_playing(next_song['id'], next_song['title'], next_song['artist'])

    def action_view_queue(self): self.app.push_screen(QueueScreen())
    def action_back_to_search(self): self.app.switch_screen(WelcomeScreen())
    def action_toggle_play(self): self.app.player.toggle_pause()
    def action_vol_up(self): self.app.player.set_volume(self.app.player.get_volume() + 5)
    def action_vol_down(self): self.app.player.set_volume(self.app.player.get_volume() - 5)

class Tuitify(App):
    CSS_PATH = "main.tcss"
    def on_mount(self) -> None:
        self.searcher = MusicSearcher()
        self.player = MusicPlayer()
        self.active_radio = []
        self.push_screen(WelcomeScreen())

    def perform_search(self, query):
        self.run_worker(self._search_task(query))

    async def _search_task(self, query):
        results = self.searcher.get_combined_results(query)
        self.switch_screen(SearchResultsScreen(results))

    async def seed_radio_in_background(self, video_id):
        # Fetches a list of related songs to create an automatic queue.
        self.active_radio = self.searcher.get_radio_queue(video_id)

    def start_playing(self, video_id, title="Unknown", artist="Unknown"):
        self.player.play_song(video_id, title, artist)
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