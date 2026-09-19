import os
import sys
import asyncio
from typing import List, Dict, Any

from rich.text import Text
from rich.align import Align
from rich.console import Group

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import ContentSwitcher, Static, ListView, ListItem, Input, Label
from textual.binding import Binding
from textual.reactive import reactive

from mpv_check import ensure_mpv_installed
from player import MusicPlayer
from storage import StorageManager
from search import SearchEngine

VINYL_FRAMES = [
    """
       .-------.
      /   ___   \\
     |   / O \\   |
     |   \\___/   |
      \\         /
       '-------'
    """,
    """
       .-------.
      /   /|\\   \\
     |   --O--   |
     |    \\|/    |
      \\         /
       '-------'
    """,
    """
       .-------.
      /   \\|/   \\
     |   --O--   |
     |    /|\\    |
      \\         /
       '-------'
    """,
    """
       .-------.
      /    |    \\
     |   ( O )   |
     |     |     |
      \\         /
       '-------'
    """
]

class NavItem(ListItem):
    def __init__(self, title: str, section_id: str):
        super().__init__(id=f"nav_{section_id}")
        self.section_id = section_id
        self.title_text = title

    def compose(self) -> ComposeResult:
        yield Label(f"  {self.title_text}")

class SongRow(ListItem):
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        self.song_data = data

    def compose(self) -> ComposeResult:
        title = self.song_data.get("title", "Unknown")[:26]
        artist = self.song_data.get("artist", "Unknown")[:18]
        dur = self.song_data.get("duration", "--:--")
        txt = Text(no_wrap=True, overflow="ellipsis")
        txt.append(f"{title:<28} ", style="bold white")
        txt.append(f"{artist:<20} ", style="bold #79c0ff")
        txt.append(f"{dur:>6}", style="bold #7ee787")
        yield Static(txt)

class QueueRow(ListItem):
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        self.song_data = data

    def compose(self) -> ComposeResult:
        title = self.song_data.get("title", "Unknown")[:16]
        artist = self.song_data.get("artist", "Unknown")[:10]
        dur = self.song_data.get("duration", "--:--")
        txt = Text(no_wrap=True, overflow="ellipsis")
        txt.append(f"{title:<17} ", style="bold white")
        txt.append(f"{artist:<11} ", style="bold #79c0ff")
        txt.append(f"{dur:>5}", style="bold #7ee787")
        yield Static(txt)

class AlbumRow(ListItem):
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        self.album_data = data

    def compose(self) -> ComposeResult:
        title = self.album_data.get("title", "Unknown")[:28]
        artist = self.album_data.get("artist", "Unknown")[:18]
        year = self.album_data.get("year", "")
        txt = Text(no_wrap=True, overflow="ellipsis")
        txt.append("[ALBUM] ", style="bold yellow")
        txt.append(f"{title:<30} ", style="bold white")
        txt.append(f"{artist:<20} ", style="bold #d2a8ff")
        txt.append(f"{year:>4}", style="bold #8b949e")
        yield Static(txt)

class ArtistRow(ListItem):
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        self.artist_data = data

    def compose(self) -> ComposeResult:
        name = self.artist_data.get("name", "Unknown")[:30]
        subs = self.artist_data.get("subscribers", "")
        txt = Text(no_wrap=True, overflow="ellipsis")
        txt.append("[ARTIST] ", style="bold #f0883e")
        txt.append(f"{name:<32} ", style="bold white")
        txt.append(f"{subs}", style="bold #58a6ff")
        yield Static(txt)

class PlayerWidget(Static):
    current_title = reactive("Nothing Playing")
    current_artist = reactive("")
    time_str = reactive("00:00 / 00:00")
    pos_sec = reactive(0)
    dur_sec = reactive(0)
    volume_val = reactive(100)
    is_muted = reactive(False)
    frame_idx = reactive(0)
    is_paused = reactive(False)

    def render(self):
        raw_vinyl = VINYL_FRAMES[self.frame_idx if not self.is_paused else 0].strip("\n")
        vinyl_text = Text(raw_vinyl, style="cyan bold")

        status = "⏸ PAUSED" if self.is_paused else "▶ PLAYING"
        status_text = Text(status, style="yellow bold" if self.is_paused else "green bold")
        title_text = Text(self.current_title[:28], style="bold white")
        artist_text = Text(self.current_artist[:28], style="dim cyan")

        bar_len = 26
        if self.dur_sec > 0:
            filled = int((self.pos_sec / self.dur_sec) * bar_len)
            filled = max(0, min(bar_len, filled))
        else:
            filled = 0
        bar = "/" * filled + "-" * (bar_len - filled)

        bar_text = Text(f"[{bar}]", style="bold yellow")
        time_text = Text(self.time_str, style="bold white")

        vol_display = "MUTED" if self.is_muted else f"{self.volume_val}%"
        vol_text = Text(f"VOL: {vol_display}", style="magenta bold")

        return Group(
            Align.center(vinyl_text),
            Text(""),
            Align.center(status_text),
            Align.center(title_text),
            Align.center(artist_text),
            Text(""),
            Align.center(bar_text),
            Align.center(time_text),
            Text(""),
            Align.center(vol_text)
        )

class DynamicFooter(Static):
    hints = reactive("↑/↓: Navigate  •  Alt+E: Select  •  Tab: Main  •  Space: Play/Pause  •  Ctrl+Q: Quit")

    def watch_hints(self, new_hints: str) -> None:
        t = Text()
        t.append("  ", style="default")
        parts = new_hints.split(" • ")
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            t.append(part, style="bold #58a6ff")
            if i < len(parts) - 1:
                t.append("   •   ", style="dim #8b949e")
        self.update(t)

class TuitifyApp(App):
    CSS = """
    Screen {
        background: #0d1117;
        layout: vertical;
    }

    #app_body {
        height: 1fr;
        layout: horizontal;
    }

    #sec_menu {
        width: 18%;
        height: 100%;
        border-right: solid #30363d;
        padding: 1 0;
    }

    #menu_title {
        text-align: center;
        text-style: bold;
        color: #58a6ff;
        margin-top: 1;
        margin-bottom: 1;
    }

    #menu_list {
        background: transparent;
        border: none;
    }

    /* Fixed vertical padding so height: 1 does not squash text */
    #menu_list ListItem {
        height: 1;
        padding: 0 1;
        color: #8b949e;
    }

    #menu_list ListItem:hover {
        background: #161b22;
        color: #c9d1d9;
    }

    #menu_list ListItem.-selected {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }

    #sec_main {
        width: 54%;
        height: 100%;
        border-right: solid #30363d;
        padding: 1 2;
    }

    #switcher {
        height: 1fr;
    }

    .view_container {
        height: 1fr;
        layout: vertical;
    }

    .main_header {
        text-style: bold;
        color: #58a6ff;
        margin-top: 1;
        margin-bottom: 1;
    }

    .sub_header {
        text-style: bold;
        color: #f0883e;
        margin-top: 1;
        margin-bottom: 1;
    }

    .artist_about_box {
        background: #161b22;
        border: solid #30363d;
        padding: 1;
        margin-bottom: 1;
        color: #c9d1d9;
        height: auto;
        max-height: 8;
    }

    #search_bar {
        border: solid #30363d;
        background: #161b22;
        color: #c9d1d9;
        margin-top: 1;
        margin-bottom: 1;
        height: 3;
    }

    #search_bar:focus {
        border: double #58a6ff;
    }

    .filter_pill {
        color: #8b949e;
        margin-bottom: 1;
    }

    #sec_player {
        width: 28%;
        height: 100%;
        padding: 1 1;
        layout: vertical;
    }

    #player_widget {
        height: auto;
        border: round #30363d;
        background: #161b22;
        padding: 1 1;
        margin-bottom: 1;
    }

    #queue_container {
        height: 1fr;
        border: round #30363d;
        padding: 0 1;
        layout: vertical;
    }

    #queue_label {
        color: #58a6ff;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
        text-align: center;
    }

    #queue_list {
        height: 1fr;
        max-height: 100%;
        background: transparent;
        border: none;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
        scrollbar-color: #3b4252 #161b22;
    }

    ListView {
        background: transparent;
        border: none;
        height: auto;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
        scrollbar-color: #3b4252 #161b22;
    }

    #recent_list, #pinned_list {
        max-height: 8;
    }

    #search_results_list, #album_tracks_list {
        max-height: 100%;
        height: 1fr;
    }

    /* Base List Item layout */
    ListItem {
        height: 1;
        padding: 0 1;
        overflow: hidden;
    }

    ListItem Static {
        height: 1;
        overflow: hidden;
    }

    ListItem:hover {
        background: #21262d;
    }

    /* High contrast selection styles: bright clear background & bold foreground */
    ListItem.-selected {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }

    ListView:focus > ListItem.-selected {
        background: #238636;
        color: #ffffff;
        text-style: bold;
    }

    #dynamic_footer {
        dock: bottom;
        height: 1;
        width: 100%;
        background: #161b22;
        color: #f0f6fc;
        padding: 0;
    }
    """

    BINDINGS = [
        Binding("tab", "cycle_focus", "Focus Tab", show=False),
        Binding("escape,alt+b", "go_back", "Back", show=False),
        Binding("alt+e", "activate_selected", "Select / Play", show=False),
        Binding("alt+s", "focus_search", "Search", show=False),
        Binding("alt+t", "toggle_search_filter", "Toggle Filter", show=False),
        Binding("space", "toggle_play", "Play/Pause", show=False),
        Binding("alt+p", "pin_active_song", "Pin Song", show=False),
        Binding("alt+d", "delete_song", "Delete Song", show=False),
        Binding("alt+j", "seek_backward", "Seek -5s", show=False),
        Binding("alt+l", "seek_forward", "Seek +5s", show=False),
        Binding("alt+i", "vol_up", "Vol +5", show=False),
        Binding("alt+k", "vol_down", "Vol -5", show=False),
        Binding("alt+m", "toggle_mute", "Mute", show=False),
        Binding("alt+q", "toggle_queue_view", "Queue Toggle", show=False),
        Binding("ctrl+q", "force_quit", "Quit", show=False),
    ]

    def __init__(self, mpv_bin: str):
        super().__init__()
        self.mpv_bin = mpv_bin
        self.player = MusicPlayer(mpv_bin=mpv_bin)
        self.storage = StorageManager()
        self.engine = SearchEngine()

        self.current_pane = 0
        self.search_filters = ["songs", "albums", "artists"]
        self.active_filter_idx = 0
        self.last_search_query = ""
        self.queue: List[Dict[str, str]] = []
        self.pre_mute_vol = 100
        self.current_playing_song: Dict[str, Any] = {}
        self.registered_intervals = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="app_body"):
            with Vertical(id="sec_menu"):
                yield Label("T U I T I F Y", id="menu_title")
                yield ListView(
                    NavItem("Home", "home_view"),
                    NavItem("Search", "search_view"),
                    NavItem("Your Music", "music_view"),
                    NavItem("Settings", "settings_view"),
                    id="menu_list"
                )

            with Vertical(id="sec_main"):
                with ContentSwitcher(initial="home_view", id="switcher"):
                    # 1. HOME VIEW
                    with Vertical(id="home_view", classes="view_container"):
                        yield Label("Welcome back.", classes="main_header")
                        yield Label("Recently Played", classes="sub_header")
                        yield ListView(id="recent_list")
                        yield Label("Pinned Songs", classes="sub_header")
                        yield ListView(id="pinned_list")

                    # 2. SEARCH VIEW
                    with Vertical(id="search_view", classes="view_container"):
                        yield Input(placeholder="Type to search and hit Enter...", id="search_bar")
                        yield Label("Filter: [SONGS] (Press alt+t to toggle | Esc to go back)", id="filter_indicator", classes="filter_pill")
                        yield ListView(id="search_results_list")

                    # 3. ALBUM DRILLDOWN VIEW
                    with Vertical(id="album_view", classes="view_container"):
                        yield Label("Album Details", id="album_title_lbl", classes="main_header")
                        yield Label("Artist Info", id="album_subtitle_lbl", classes="filter_pill")
                        yield ListView(id="album_tracks_list")

                    # 4. ARTIST DRILLDOWN VIEW
                    with VerticalScroll(id="artist_view", classes="view_container"):
                        yield Label("Artist Name", id="artist_name_lbl", classes="main_header")
                        yield Label("Subscribers", id="artist_subs_lbl", classes="filter_pill")
                        yield Label("About", classes="sub_header")
                        yield Static("", id="artist_about_lbl", classes="artist_about_box")
                        yield Label("Top Songs", classes="sub_header")
                        yield ListView(id="artist_top_songs_list")
                        yield Label("Albums & Singles", classes="sub_header")
                        yield ListView(id="artist_albums_list")

                    # 5. YOUR MUSIC VIEW
                    with Vertical(id="music_view", classes="view_container"):
                        yield Label("Your Library", classes="main_header")
                        yield Label("Coming Soon - Local & Cloud playlists.", classes="filter_pill")

                    # 6. SETTINGS VIEW
                    with Vertical(id="settings_view", classes="view_container"):
                        yield Label("Settings", classes="main_header")
                        yield Label("Storage path: ~/.config/tuitify/data.json", classes="filter_pill")

            with Vertical(id="sec_player"):
                yield PlayerWidget(id="player_widget")
                with Vertical(id="queue_container"):
                    yield Label("UP NEXT (RADIO)", id="queue_label")
                    yield ListView(id="queue_list")

        yield DynamicFooter(id="dynamic_footer")

    def on_mount(self) -> None:
        self.registered_intervals.append(self.set_interval(0.25, self._tick_animation))
        self.registered_intervals.append(self.set_interval(1.0, self._tick_player_status))
        self.refresh_home_data()
        self.query_one("#menu_list", ListView).focus()
        self.update_footer_hints()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        widget = event.widget
        if widget is not None:
            try:
                ancestors = set(widget.ancestors) | {widget}
                if self.query_one("#sec_menu") in ancestors:
                    self.current_pane = 0
                elif self.query_one("#sec_main") in ancestors:
                    self.current_pane = 1
                elif self.query_one("#sec_player") in ancestors:
                    self.current_pane = 2
            except Exception:
                pass
        self.update_footer_hints()

    def on_unmount(self) -> None:
        for timer in self.registered_intervals:
            try:
                timer.stop()
            except Exception:
                pass
        if hasattr(self, "player") and self.player:
            self.player.quit()

    def action_force_quit(self) -> None:
        if hasattr(self, "player") and self.player:
            self.player.stop()
            self.player.quit()
        for timer in self.registered_intervals:
            try:
                timer.stop()
            except Exception:
                pass
        self.exit()

    # ----------------- ROUTING & DATA REFRESH ----------------- #

    @property
    def active_view_id(self) -> str:
        return self.query_one("#switcher", ContentSwitcher).current or "home_view"

    def switch_view(self, view_id: str):
        self.query_one("#switcher", ContentSwitcher).current = view_id
        if view_id == "home_view":
            self.refresh_home_data()
        self.update_footer_hints()

    def refresh_home_data(self):
        r_list = self.query_one("#recent_list", ListView)
        r_list.clear()
        recent_songs = self.storage.get_recent_songs(5)
        if not recent_songs:
            r_list.append(ListItem(Label("No recent songs yet.")))
        else:
            for s in recent_songs:
                r_list.append(SongRow(s))

        p_list = self.query_one("#pinned_list", ListView)
        p_list.clear()
        pinned_songs = self.storage.get_pinned_songs(5)
        if not pinned_songs:
            p_list.append(ListItem(Label("No pinned songs yet.")))
        else:
            for s in pinned_songs:
                p_list.append(SongRow(s))

    def show_album_drilldown(self, details: Dict[str, Any]):
        self.query_one("#album_title_lbl", Label).update(f"Album: {details.get('title')}")
        self.query_one("#album_subtitle_lbl", Label).update(f"Artist: {details.get('artist')} ({details.get('year')})  [Esc to Back]")
        
        t_list = self.query_one("#album_tracks_list", ListView)
        t_list.clear()
        for t in details.get("tracks", []):
            t_list.append(SongRow(t))

        self.switch_view("album_view")
        t_list.focus()

    def show_artist_drilldown(self, details: Dict[str, Any]):
        self.query_one("#artist_name_lbl", Label).update(f"Artist: {details.get('name')}")
        sub_info = details.get('subscribers', '')
        self.query_one("#artist_subs_lbl", Label).update(f"{sub_info}  [Esc to Back]" if sub_info else "[Esc to Back]")
        self.query_one("#artist_about_lbl", Static).update(details.get('description', 'No biography available.'))

        s_list = self.query_one("#artist_top_songs_list", ListView)
        s_list.clear()
        for s in details.get("top_songs", []):
            s_list.append(SongRow(s))

        a_list = self.query_one("#artist_albums_list", ListView)
        a_list.clear()
        for a in details.get("albums", []):
            a_list.append(AlbumRow(a))

        self.switch_view("artist_view")
        s_list.focus()

    # ----------------- PLAYBACK & QUEUE ----------------- #

    def play_track(self, song: Dict[str, Any], seed_radio: bool = True):
        self.current_playing_song = song
        pw = self.query_one("#player_widget", PlayerWidget)
        pw.current_title = song.get("title", "Unknown")
        pw.current_artist = song.get("artist", "Unknown")

        self.storage.add_recent_song(song)
        self.player.play_song(song["id"], song["title"], song["artist"])
        
        if seed_radio:
            asyncio.create_task(self._seed_auto_queue(song["id"]))

    async def _seed_auto_queue(self, video_id: str):
        loop = asyncio.get_running_loop()
        radio_tracks = await loop.run_in_executor(None, lambda: self.engine.get_radio_queue(video_id))
        self.queue = radio_tracks
        self._refresh_queue_widget()

    def _refresh_queue_widget(self):
        q_list = self.query_one("#queue_list", ListView)
        q_list.clear()
        for t in self.queue:
            q_list.append(QueueRow(t))

    def play_from_queue_index(self, index: int):
        if 0 <= index < len(self.queue):
            selected_song = self.queue[index]
            self.queue = self.queue[index + 1:]
            self._refresh_queue_widget()
            self.play_track(selected_song, seed_radio=False)

    def _tick_animation(self):
        pw = self.query_one("#player_widget", PlayerWidget)
        pw.frame_idx = (pw.frame_idx + 1) % len(VINYL_FRAMES)
        pw.is_paused = self.player.is_paused

    def _tick_player_status(self):
        pw = self.query_one("#player_widget", PlayerWidget)
        pos, dur = self.player.get_time()
        pw.pos_sec = pos
        pw.dur_sec = dur
        pw.volume_val = self.player.get_volume()
        pw.time_str = f"{self.player.format_time(pos)} / {self.player.format_time(dur)}"

        if self.player.is_finished() and self.queue:
            next_song = self.queue.pop(0)
            self._refresh_queue_widget()
            self.play_track(next_song, seed_radio=False)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self.last_search_query = query
        self.active_filter_idx = 0
        
        loop = asyncio.get_running_loop()
        songs = await loop.run_in_executor(None, lambda: self.engine.search_songs_now(query))
        self._populate_search_results(songs, "song")

    def _populate_search_results(self, results: List[Dict[str, Any]], result_type: str):
        list_view = self.query_one("#search_results_list", ListView)
        list_view.clear()
        for item in results:
            if result_type == "song":
                list_view.append(SongRow(item))
            elif result_type == "album":
                list_view.append(AlbumRow(item))
            elif result_type == "artist":
                list_view.append(ArtistRow(item))
        list_view.focus()
        self.update_footer_hints()

    # ----------------- KEYBOARD & ACTIONS ----------------- #

    def update_footer_hints(self):
        try:
            footer = self.query_one("#dynamic_footer", DynamicFooter)
        except Exception:
            return

        focused = self.focused
        if isinstance(focused, Input):
            footer.hints = "Enter: Search  •  Tab: Switch Section  •  Ctrl+Q: Quit"
            return

        if self.current_pane == 0:
            footer.hints = "↑/↓: Navigate  •  Alt+E: Select  •  Tab: Main  •  Space: Play/Pause  •  Ctrl+Q: Quit"
        elif self.current_pane == 1:
            vid = self.active_view_id
            if vid == "home_view":
                footer.hints = "↑/↓: Move  •  Alt+E: Play  •  Alt+D: Delete Song  •  Alt+P: Pin  •  Space: Play/Pause  •  Tab: Queue"
            elif vid == "search_view":
                footer.hints = "↑/↓: Move  •  Alt+E: Open/Play  •  Alt+T: Filter  •  Alt+S: Search  •  Space: Play/Pause  •  Tab: Queue"
            elif vid in ("album_view", "artist_view"):
                footer.hints = "↑/↓: Move  •  Alt+E: Play/Open  •  Esc: Back  •  Space: Play/Pause  •  Tab: Queue"
            else:
                footer.hints = "Tab: Switch Section  •  Space: Play/Pause  •  Ctrl+Q: Quit"
        elif self.current_pane == 2:
            footer.hints = "↑/↓: Move  •  Alt+E: Seek to Song  •  Alt+J/L: ±5s  •  Alt+I/K: Vol ±5  •  Alt+M: Mute  •  Space: Play/Pause  •  Tab: Menu"

    def action_cycle_focus(self):
        self.current_pane = (self.current_pane + 1) % 3
        try:
            if self.current_pane == 0:
                self.query_one("#menu_list", ListView).focus()
            elif self.current_pane == 1:
                active_view = self.query_one(f"#{self.active_view_id}")
                lists = active_view.query(ListView)
                if lists:
                    lists.first().focus()
                else:
                    inp = active_view.query(Input)
                    if inp:
                        inp.first().focus()
            elif self.current_pane == 2:
                self.query_one("#queue_list", ListView).focus()
        except Exception:
            pass
        self.update_footer_hints()

    async def action_activate_selected(self):
        focused = self.focused

        # Menu navigation
        if isinstance(focused, ListView) and focused.id == "menu_list":
            selected = focused.highlighted_child
            if isinstance(selected, NavItem):
                self.switch_view(selected.section_id)

        # Queue direct seeking
        elif isinstance(focused, ListView) and focused.id == "queue_list":
            idx = focused.index
            if idx is not None:
                self.play_from_queue_index(idx)

        # Content lists
        elif isinstance(focused, ListView):
            selected = focused.highlighted_child
            if isinstance(selected, SongRow):
                self.play_track(selected.song_data, seed_radio=True)
            elif isinstance(selected, AlbumRow):
                loop = asyncio.get_running_loop()
                details = await loop.run_in_executor(None, lambda: self.engine.get_album_details(selected.album_data["id"]))
                self.show_album_drilldown(details)
            elif isinstance(selected, ArtistRow):
                loop = asyncio.get_running_loop()
                details = await loop.run_in_executor(None, lambda: self.engine.get_artist_details(selected.artist_data["id"]))
                self.show_artist_drilldown(details)

    def action_delete_song(self):
        if self.active_view_id != "home_view":
            return

        focused = self.focused
        if isinstance(focused, ListView):
            selected = focused.highlighted_child
            if isinstance(selected, SongRow):
                song_id = selected.song_data.get("id")
                if not song_id:
                    return

                if focused.id == "recent_list":
                    self.storage.remove_recent_song(song_id)
                elif focused.id == "pinned_list":
                    self.storage.toggle_pinned_song(selected.song_data)

                self.refresh_home_data()

    def action_pin_active_song(self):
        if self.current_playing_song and self.current_playing_song.get("id"):
            self.storage.toggle_pinned_song(self.current_playing_song)
            if self.active_view_id == "home_view":
                self.refresh_home_data()

    def action_go_back(self):
        if self.active_view_id in ("album_view", "artist_view"):
            self.switch_view("search_view")
            if self.last_search_query:
                inp = self.query_one("#search_bar", Input)
                inp.value = self.last_search_query
                target = self.search_filters[self.active_filter_idx]
                cached_items = self.engine.get_cached(self.last_search_query, target)
                res_type = "song" if target == "songs" else ("album" if target == "albums" else "artist")
                self._populate_search_results(cached_items, res_type)

    def action_focus_search(self):
        if self.active_view_id != "search_view":
            self.switch_view("search_view")
        self.query_one("#search_bar", Input).focus()
        self.update_footer_hints()

    def action_toggle_search_filter(self):
        if self.active_view_id != "search_view" or not self.last_search_query:
            return
        self.active_filter_idx = (self.active_filter_idx + 1) % len(self.search_filters)
        target = self.search_filters[self.active_filter_idx]
        
        lbl = self.query_one("#filter_indicator", Label)
        lbl.update(f"Filter: [{target.upper()}] (Press alt+t to toggle | Esc to go back)")

        cached_items = self.engine.get_cached(self.last_search_query, target)
        res_type = "song" if target == "songs" else ("album" if target == "albums" else "artist")
        self._populate_search_results(cached_items, res_type)

    def action_toggle_play(self):
        if isinstance(self.focused, Input):
            return
        self.player.toggle_pause()

    def action_seek_forward(self):
        self.player.seek(5)

    def action_seek_backward(self):
        self.player.seek(-5)

    def action_vol_up(self):
        self.player.set_volume(self.player.get_volume() + 5)

    def action_vol_down(self):
        self.player.set_volume(self.player.get_volume() - 5)

    def action_toggle_mute(self):
        pw = self.query_one("#player_widget", PlayerWidget)
        pw.is_muted = not pw.is_muted
        if pw.is_muted:
            self.pre_mute_vol = self.player.get_volume()
            self.player.set_volume(0)
        else:
            self.player.set_volume(self.pre_mute_vol)

    def action_toggle_queue_view(self):
        q_cont = self.query_one("#queue_container")
        q_cont.display = not q_cont.display

    def on_list_view_selected(self, event: ListView.Selected):
        asyncio.create_task(self.action_activate_selected())


if __name__ == "__main__":
    mpv_bin = ensure_mpv_installed()
    app = TuitifyApp(mpv_bin=mpv_bin)
    app.run()