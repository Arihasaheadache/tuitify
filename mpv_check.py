import os
import sys
import shutil
import platform
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

def get_package_manager():
    """Detects the host OS and available package manager."""
    system = sys.platform

    if system == "darwin":
        if shutil.which("brew"):
            return "brew", ["brew", "install", "mpv"], "brew install mpv"
        return "mac_manual", None, "brew install mpv (install Homebrew first at https://brew.sh)"

    elif system == "win32":
        if shutil.which("winget"):
            return "winget", ["winget", "install", "shinchiro.mpv", "--accept-source-agreements", "--accept-package-agreements"], "winget install shinchiro.mpv"
        if shutil.which("scoop"):
            return "scoop", ["scoop", "install", "mpv"], "scoop install mpv"
        if shutil.which("choco"):
            return "choco", ["choco", "install", "mpv", "-y"], "choco install mpv"
        return "win_manual", None, "Download portable mpv from https://mpv.io or run: winget install shinchiro.mpv"

    elif system.startswith("linux"):
        distro_managers = [
            ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "mpv"], "sudo pacman -S mpv"),
            ("apt", ["sudo", "apt", "update", "&&", "sudo", "apt", "install", "-y", "mpv"], "sudo apt update && sudo apt install mpv"),
            ("dnf", ["sudo", "dnf", "install", "-y", "mpv"], "sudo dnf install mpv"),
            ("zypper", ["sudo", "zypper", "install", "-y", "mpv"], "sudo zypper install mpv"),
            ("apk", ["sudo", "apk", "add", "mpv"], "sudo apk add mpv"),
        ]
        for name, cmd, manual in distro_managers:
            if shutil.which(name):
                return name, cmd, manual
        return "linux_manual", None, "Use your package manager to install 'mpv'."

    return "unknown", None, "Please install mpv from https://mpv.io"


def ensure_mpv_installed() -> str:
    """Returns absolute path to mpv executable, prompting if missing."""
    mpv_path = shutil.which("mpv")
    if mpv_path:
        return mpv_path

    if sys.platform == "win32":
        local_win = os.path.abspath(os.path.join("bin", "mpv.exe"))
        if os.path.exists(local_win):
            return local_win

    mgr_name, install_cmd, manual_str = get_package_manager()

    console.clear()
    msg = (
        "[bold red]mpv was not found on your system.[/bold red]\n\n"
        "Tuitify requires mpv in headless IPC mode for audio playback.\n\n"
        f"[bold]Detected OS:[/bold] {platform.system()} ({platform.release()})\n"
        f"[dim]Manual command: {manual_str}[/dim]"
    )
    console.print(Panel(msg, title="[bold yellow]Dependency Check[/bold yellow]", border_style="yellow"))

    if not install_cmd:
        console.print(f"\n[red]No automated package manager detected.[/red]")
        console.print(f"Install manually: [green]{manual_str}[/green]\n")
        sys.exit(1)

    choice = Confirm.ask("\n[bold]Install mpv automatically?[/bold]", default=True)
    if not choice:
        console.print(f"\n[dim]Manual command:[/dim]\n  [green]{manual_str}[/green]\n")
        sys.exit(0)

    try:
        if "&&" in install_cmd:
            ret = subprocess.run(" ".join(install_cmd), shell=True)
        else:
            ret = subprocess.run(install_cmd)

        if ret.returncode != 0:
            console.print(f"\n[red]Install command exited with code {ret.returncode}.[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Installation failed:[/red] {e}")
        sys.exit(1)

    mpv_path = shutil.which("mpv")
    if not mpv_path:
        console.print("\n[yellow]mpv installed, but not found in active PATH. Restart terminal.[/yellow]")
        sys.exit(0)

    return mpv_path