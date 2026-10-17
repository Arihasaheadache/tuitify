import os
import sys
import asyncio
from typing import List, Dict, Any
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import ContentSwitcher, Static, ListView, ListItem, Input, Label
from textual.binding import Binding
from textual.reactive import reactive
from mpv_check import ensure_mpv_installed
from player import MusicPlayer
from storage import StorageManager
from search import SearchEngine


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
        txt.append(f"{title:<28} ", style="white")
        txt.append(f"{artist:<20} ", style="white")
        txt.append(f"{dur:>6}", style="white")
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
        txt.append(f"{title:<17} ", style="white")
        txt.append(f"{artist:<11} ", style="white")
        txt.append(f"{dur:>5}", style="white")
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
        txt.append("[ALBUM] ", style="white")
        txt.append(f"{title:<30} ", style="white")
        txt.append(f"{artist:<20} ", style="white")
        txt.append(f"{year:>4}", style="white")
        yield Static(txt)


class ArtistRow(ListItem):
    def __init__(self, data: Dict[str, Any]):
        super().__init__()
        self.artist_data = data

    def compose(self) -> ComposeResult:
        name = self.artist_data.get("name", "Unknown")[:30]
        subs = self.artist_data.get("subscribers", "")
        txt = Text(no_wrap=True, overflow="ellipsis")
        txt.append("[ARTIST] ", style="white")
        txt.append(f"{name:<32} ", style="white")
        txt.append(f"{subs}", style="white")
        yield Static(txt)


class BottomBar(Static):
    """Horizontal bottom bar showing current song info"""
    current_title = reactive("Nothing Playing")
    current_artist = reactive("")
    time_str = reactive("00:00 / 00:00")
    pos_sec = reactive(0)
    dur_sec = reactive(0)
    volume_val = reactive(100)
    is_muted = reactive(False)
    is_paused = reactive(False)

    # CRITICAL: Prevent this widget from ever being focused
    can_focus = False

    def render(self):
        status = "⏸" if self.is_paused else "▶"
        vol_display = "M" if self.is_muted else f"{self.volume_val}"

        bar_len = 30
        if self.dur_sec > 0:
            filled = int((self.pos_sec / self.dur_sec) * bar_len)
            filled = max(0, min(bar_len, filled))
        else:
            filled = 0
        bar = "█" * filled + "░" * (bar_len - filled)

        title_artist = f"{self.current_title[:30]} - {self.current_artist[:20]}"
        line = f"{status} {title_artist:<55} | [{bar}] {self.time_str} | Vol:{vol_display}"

        return Text(line, style="white on black")


class TuitifyApp(App):
    CSS = """
    Screen {
        background: black;
        color: white;
        layout: vertical;
        overflow: hidden;
    }

    /* ROOT CONTAINER: Stacks body and bottom bar */
    #root_container {
        height: 100%;
        width: 100%;
        layout: vertical;
        padding: 0 1;
    }

    /* SECTION 1: Main Body - Parent container with softened rounded border */
    #sec_main_body {
        height: 1fr;
        layout: horizontal;
        border: round #777777;
        padding: 0;
        overflow: hidden;
    }

    /* COLUMN STRUCTURE & INTERNAL DIVIDERS */
    #sec_menu, #sec_content, #sec_player_col {
        padding: 0;
        height: 100%;
    }

    #sec_menu {
        width: 18%;
        border-right: solid #777777;
    }

    #sec_content {
        width: 54%;
        border-right: solid #777777;
    }

    #sec_player_col {
        width: 28%;
    }

    /* MENU STYLING */
    #menu_title {
        text-align: center;
        text-style: bold;
        color: white;
        margin: 1 0;
        padding: 0 1;
    }

    #menu_list {
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
    }

    #menu_list ListItem {
        height: 1;
        padding: 0 2;
        color: white;
    }

    #menu_list ListItem:hover,
    #menu_list ListItem.-selected {
        background: white;
        color: black;
        text-style: bold;
    }

    /* MAIN CONTENT AREA */
    #switcher {
        height: 1fr;
        padding: 0;
    }

    .view_container {
        height: 1fr;
        layout: vertical;
        padding: 1 2;
    }

    .main_header {
        text-style: bold;
        color: white;
        margin-top: 1;
        margin-bottom: 1;
    }

    .sub_header {
        text-style: bold;
        color: white;
        margin-top: 1;
        margin-bottom: 1;
    }

    .info_box {
        background: black;
        border: round #777777;
        padding: 1;
        margin-bottom: 1;
        color: white;
        height: auto;
        max-height: 8;
    }

    #search_bar {
        border: round #777777;
        background: black;
        color: white;
        margin-top: 1;
        margin-bottom: 1;
        height: 3;
    }

    #search_bar:focus {
        border: round white;
    }

    .filter_pill {
        color: white;
        margin-bottom: 1;
    }

    /* PLAYER / QUEUE AREA */
    #queue_label {
        color: white;
        text-style: bold;
        margin: 1 0;
        padding: 0 1;
        text-align: center;
    }

    #queue_container {
        height: 1fr;
        border: round #777777;
        margin: 0 1;
        padding: 0;
        layout: vertical;
    }

    #queue_list {
        height: 1fr;
        background: transparent;
        border: none;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
        scrollbar-color: #777777 black;
        padding: 0;
    }

    /* GLOBAL LIST STYLING */
    ListView {
        background: transparent;
        border: none;
        height: auto;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
        scrollbar-color: #777777 black;
        padding: 0;
    }

    #recent_list, #pinned_list {
        max-height: 8;
    }

    #search_results_list, #album_tracks_list {
        max-height: 100%;
        height: 1fr;
    }

    ListItem {
        height: 1;
        padding: 0 1;
        overflow: hidden;
        color: white;
    }

    ListItem Static {
        height: 1;
        overflow: hidden;
    }

    ListItem:hover,
    ListItem.-selected {
        background: white;
        color: black;
        text-style: bold;
    }

    /* SECTION 2: Bottom Bar - Softened rounded border with top margin */
    #bottom_bar {
        height: 3;
        min-height: 3;
        max-height: 3;
        width: 100%;
        background: black;
        color: white;
        border: round #777777;
        margin-top: 1;
        padding: 0 1;
        overflow: hidden;
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
        Binding("alt+d", "delete_song", "Delete Item", show=False),
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
        with Vertical(id="root_container"):
            # SECTION 1: Three-column horizontal body with parent outline
            with Horizontal(id="sec_main_body"):
                with Vertical(id="sec_menu"):
                    yield Label("TUITIFY", id="menu_title")
                    yield ListView(
                        NavItem("Home", "home_view"),
                        NavItem("Search", "search_view"),
                        NavItem("Your Music", "music_view"),
                        NavItem("Settings", "settings_view"),
                        id="menu_list"
                    )

                with Vertical(id="sec_content"):
                    with ContentSwitcher(initial="home_view", id="switcher"):
                        with Vertical(id="home_view", classes="view_container"):
                            yield Label("Welcome back.", classes="main_header")
                            yield Label("Recently Played", classes="sub_header")
                            yield ListView(id="recent_list")
                            yield Label("Pinned Songs", classes="sub_header")
                            yield ListView(id="pinned_list")

                        with Vertical(id="search_view", classes="view_container"):
                            yield Input(placeholder="Type to search and hit Enter...", id="search_bar")
                            yield Label("Filter: [SONGS] (Press alt+t to toggle | Esc to go back)",
                                       id="filter_indicator", classes="filter_pill")
                            yield ListView(id="search_results_list")

                        with Vertical(id="album_view", classes="view_container"):
                            yield Label("Album Details", id="album_title_lbl", classes="main_header")
                            yield Label("Artist Info", id="album_subtitle_lbl", classes="filter_pill")
                            yield ListView(id="album_tracks_list")

                        with VerticalScroll(id="artist_view", classes="view_container"):
                            yield Label("Artist Name", id="artist_name_lbl", classes="main_header")
                            yield Label("Subscribers", id="artist_subs_lbl", classes="filter_pill")
                            yield Label("About", classes="sub_header")
                            yield Static("", id="artist_about_lbl", classes="info_box")
                            yield Label("Top Songs", classes="sub_header")
                            yield ListView(id="artist_top_songs_list")
                            yield Label("Albums & Singles", classes="sub_header")
                            yield ListView(id="artist_albums_list")

                        with Vertical(id="music_view", classes="view_container"):
                            yield Label("Your Library", classes="main_header")
                            yield Label("Coming Soon - Local & Cloud playlists.", classes="filter_pill")

                        with VerticalScroll(id="settings_view", classes="view_container"):
                            yield Label("Settings", classes="main_header")
                            yield Label("Storage path: ~/.config/tuitify/data.json", classes="filter_pill")
                            yield Label("", classes="sub_header")
                            yield Label("Keybindings", classes="sub_header")
                            yield Static(self._get_keybindings_text(), id="keybindings_display", classes="info_box")

                with Vertical(id="sec_player_col"):
                    yield Label("UP NEXT (RADIO)", id="queue_label")
                    with Vertical(id="queue_container"):
                        yield ListView(id="queue_list")

            # SECTION 2: Bottom Bar as its own bordered box
            yield BottomBar(id="bottom_bar")

    def _get_keybindings_text(self) -> str:
        bindings = [
            ("Navigation", [
                ("Tab", "Switch between sections"),
                ("↑/↓", "Navigate lists"),
                ("Alt+E", "Select/Play item"),
                ("Esc / Alt+B", "Go back"),
            ]),
            ("Playback", [
                ("Space", "Play/Pause"),
                ("Alt+J", "Seek backward 5s"),
                ("Alt+L", "Seek forward 5s"),
                ("Alt+I", "Volume up"),
                ("Alt+K", "Volume down"),
                ("Alt+M", "Toggle mute"),
            ]),
            ("Search & Filters", [
                ("Alt+S", "Focus search bar"),
                ("Alt+T", "Toggle search filter"),
                ("Enter", "Execute search"),
            ]),
            ("Library", [
                ("Alt+P", "Pin/unpin current song"),
                ("Alt+D", "Delete hovered item"),
            ]),
            ("Other", [
                ("Alt+Q", "Toggle queue view"),
                ("Ctrl+Q", "Quit application"),
            ]),
        ]

        lines = []
        for category, keys in bindings:
            lines.append(f"  {category}:")
            for key, desc in keys:
                lines.append(f"    {key:<12} {desc}")
            lines.append("")

        return "\n".join(lines)

    def on_mount(self) -> None:
        self.registered_intervals.append(self.set_interval(1.0, self._tick_player_status))
        self.refresh_home_data()
        self.query_one("#menu_list", ListView).focus()

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

    @property
    def active_view_id(self) -> str:
        return self.query_one("#switcher", ContentSwitcher).current or "home_view"

    def switch_view(self, view_id: str):
        self.query_one("#switcher", ContentSwitcher).current = view_id
        if view_id == "home_view":
            self.refresh_home_data()

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
        self.query_one("#album_subtitle_lbl", Label).update(
            f"Artist: {details.get('artist')} ({details.get('year')})  [Esc to Back]"
        )
        t_list = self.query_one("#album_tracks_list", ListView)
        t_list.clear()
        for t in details.get("tracks", []):
            t_list.append(SongRow(t))
        self.switch_view("album_view")
        t_list.focus()

    def show_artist_drilldown(self, details: Dict[str, Any]):
        self.query_one("#artist_name_lbl", Label).update(f"Artist: {details.get('name')}")
        sub_info = details.get('subscribers', '')
        self.query_one("#artist_subs_lbl", Label).update(
            f"{sub_info}  [Esc to Back]" if sub_info else "[Esc to Back]"
        )
        self.query_one("#artist_about_lbl", Static).update(
            details.get('description', 'No biography available.')
        )
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

    def play_track(self, song: Dict[str, Any], seed_radio: bool = True):
        self.current_playing_song = song
        bb = self.query_one("#bottom_bar", BottomBar)
        bb.current_title = song.get("title", "Unknown")
        bb.current_artist = song.get("artist", "Unknown")
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

    def _tick_player_status(self):
        bb = self.query_one("#bottom_bar", BottomBar)
        pos, dur = self.player.get_time()
        bb.pos_sec = pos
        bb.dur_sec = dur
        bb.volume_val = self.player.get_volume()
        bb.time_str = f"{self.player.format_time(pos)} / {self.player.format_time(dur)}"
        bb.is_paused = self.player.is_paused

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

    async def action_activate_selected(self):
        focused = self.focused
        if isinstance(focused, ListView) and focused.id == "menu_list":
            selected = focused.highlighted_child
            if isinstance(selected, NavItem):
                self.switch_view(selected.section_id)
        elif isinstance(focused, ListView) and focused.id == "queue_list":
            idx = focused.index
            if idx is not None:
                self.play_from_queue_index(idx)
        elif isinstance(focused, ListView):
            selected = focused.highlighted_child
            if isinstance(selected, SongRow):
                self.play_track(selected.song_data, seed_radio=True)
            elif isinstance(selected, AlbumRow):
                loop = asyncio.get_running_loop()
                details = await loop.run_in_executor(
                    None, lambda: self.engine.get_album_details(selected.album_data["id"])
                )
                self.show_album_drilldown(details)
            elif isinstance(selected, ArtistRow):
                loop = asyncio.get_running_loop()
                details = await loop.run_in_executor(
                    None, lambda: self.engine.get_artist_details(selected.artist_data["id"])
                )
                self.show_artist_drilldown(details)

    def action_delete_song(self):
        """Deletes hovered item from Recent or Pinned list based on context."""
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
        bb = self.query_one("#bottom_bar", BottomBar)
        bb.is_muted = not bb.is_muted
        if bb.is_muted:
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