"""
CC2 Dedicated Server Control Harness
"""
import os
import platform
import sys
import time
import subprocess
import xml.etree.ElementTree as ET
from threading import Thread
from datetime import datetime
from pathlib import Path
from typing import Optional
from argparse import ArgumentParser

from cc2logger.parser import CC2GameFollower, CC2GameParser, generate_lua_stats_page
from cc2logger.messages import PlayerChat

CFG = Path.cwd() / "cc2-config.toml"

CONTAINER = "cc2-server"
XML_CFG = "server_config.xml"

parser = ArgumentParser(description=__doc__)
parser.add_argument("--game-dir", type=Path, default=Path("Carrier Command 2"), help="Directory to the cc2 installation")
parser.add_argument("--config", type=str, help="Switch config file")


def read_server_config(server_config: Path) -> dict:
    settings = {}
    tree = ET.parse(server_config)
    root = tree.getroot()
    exclude = {"password", "game_data_path", "port"}
    for name, value in root.attrib.items():
        if name.lower() not in exclude:
            try:
                value = int(value, 10)
            except ValueError:
                pass
            settings[name] = value

    settings["admin_users"] = set()
    settings["mods"] = set()
    settings["server_name"] = root.attrib.get("server_name")

    for item in root:
        if isinstance(item, ET.Element):
            if item.tag == "permissions":
                for child in item:
                    if child.tag == "peer":
                        ident = child.attrib.get("steam_id")
                        if child.attrib.get("is_admin").lower() == "true":
                            settings["admin_users"].add(ident)
            if item.tag == "active_mod_folders":
                for child in item:
                    settings["mods"].add(child.attrib.get("value"))

    return settings

def main():
    opts = parser.parse_args()
    os.chdir(opts.game_dir)
    controller = ServerController(Path.cwd())

    if opts.config:
        controller.apply_config(opts.config)

    while not controller.quit:
        controller.run()
        time.sleep(2)


def is_linux() -> bool:
    return platform.system() == "Linux"


def get_admin_users(active_config: dict):
    return active_config.get("admin_users", set())



def gather_player_stats(game_dir: Path):
    print("generating server stats ..")
    parser = CC2GameParser()
    logs_dir = game_dir / "logs"
    parser.read_path(logs_dir)

    rev_mod = game_dir / "mods" / "rev" / "content" / "scripts"

    if rev_mod.exists():
        server_stats_lua = generate_lua_stats_page(parser)
        if server_stats_lua:
            print(f"stats ({len(server_stats_lua)} bytes)")
            (rev_mod / "library_custom_9.lua").write_bytes(server_stats_lua.encode("utf-8"))


class ServerController:
    def __init__(self, game_folder: Path):
        self.game_folder: Path = game_folder
        self.server_process: Optional[subprocess.Popen] = None
        self.server_output: Path = self.game_folder / "server.log"
        self.server_xml: Path = self.game_folder / "server_config.xml"
        self.server_configs: Path = game_folder / "configs"
        self.follower: Optional[CC2GameFollower] = None
        self.current_server_config = read_server_config(self.server_xml)
        self.chat_thread: Optional[ChatThread] = None
        self.quit = False
        self.linux_pid = -1

    def get_pid(self) -> int:
        if not is_linux():
            return self.server_process.pid
        # look in /proc for a process called "dedicated_server.exe" that has the same cwd as we do
        for item in os.listdir("/proc"):
            try:
                pid = int(item, 10)
            except ValueError:
                continue
            procdir = Path("/proc") / item
            cmdline = procdir / "cmdline"
            if cmdline.exists():
                text = cmdline.read_text(encoding="utf-8").strip()
                if text.startswith("dedicated_server.exe"):
                    cwd = Path(os.readlink(procdir / "cwd"))
                    if cwd == Path.cwd():
                        return pid

        raise EnvironmentError("cannot find server process")

    def wait_stopped(self):
        if is_linux():
            procdir = Path("/proc") / str(self.linux_pid)
            while procdir.exists():
                time.sleep(1)
        while self.server_process and self.server_process.poll() is None:
            time.sleep(1)

    def get_runner(self) -> str:
        if is_linux():
            return os.environ.get("CC2_SERVER_RUNNER", "") + " "
        return ""

    def apply_config(self, name: str) -> None:
        new_cfg = self.server_configs / f"{name}.xml"
        self.server_xml.write_bytes(new_cfg.read_bytes())
        self.current_server_config = read_server_config(self.server_xml)

    @property
    def admin_users(self) -> set:
        return get_admin_users(self.current_server_config)

    def stop(self) -> None:
        if self.chat_thread:
            self.chat_thread.quit = True

        if self.server_process:
            print("Stopping server..")
            if is_linux():
                try:
                    print(f"Killing {self.linux_pid}")
                    os.kill(self.linux_pid, 9)
                except EnvironmentError:
                    pass
                except OSError:
                    pass
            self.server_process.kill()
            self.wait_stopped()
            print("Stopped.")

    def start(self) -> None:
        self.stop()
        print("Starting server")
        output = self.server_output.open("ab")
        shell = False
        runner = self.get_runner()
        if runner:
            shell = True
            cmdline = f"{runner} dedicated_server.exe".strip()
        else:
            cmdline = ["dedicated_server.exe"]
        self.server_process = subprocess.Popen(cmdline,
                                               cwd=str(self.game_folder),
                                               shell=shell,
                                               stderr=subprocess.STDOUT,
                                               stdout=output)
        time.sleep(5)
        if is_linux():
            self.linux_pid = self.get_pid()
            print(f"PID = {self.linux_pid}")
        else:
            print(f"PID = {self.server_process.pid}")

        self.current_server_config = read_server_config(self.server_xml)
        print(f"Server: {self.current_server_config['server_name']}")
        for mod in self.current_server_config.get("mods"):
            print(f"Mod Folder: {mod}")
        for admin in self.current_server_config.get("admin_users"):
            print(f"Admin: {admin}")

        self.follower = CC2GameFollower()
        self.follower.open_latest(self.game_folder / "logs")
        self.chat_thread = ChatThread(self)
        self.chat_thread.start()

    def run(self) -> None:
        try:
            while not self.quit:
                self.start()
                self.wait_stopped()
            if self.chat_thread:
                self.chat_thread.join()
                self.chat_thread = None
        except KeyboardInterrupt:
            self.stop()
            sys.exit()


class ChatThread(Thread):
    def __init__(self, controller: ServerController):
        super().__init__(daemon=True)
        self.controller = controller
        self.quit = False

    def run(self):
        last_stats = 0
        stats_interval = 600

        while not self.quit:

            elapsed = time.monotonic() - last_stats
            last_stats = time.monotonic()
            if elapsed > stats_interval:
                gather_player_stats(self.controller.game_folder)

            try:
                msg = self.controller.follower.read_one()
                if not msg:
                    time.sleep(2)
                    continue
                if isinstance(msg, PlayerChat):
                    prefix = " "
                    admin = str(msg.player_id) in self.controller.admin_users
                    if admin:
                        prefix = "@"
                    print(f"{datetime.now().isoformat()} <{prefix}{msg.player_name}> {msg.message}")
                    if admin:
                        message = msg.message
                        if message.startswith("/"):
                            command = message.lstrip("/")
                            words = command.split()

                            if words[0] == "restart":
                                self.stop()
                            if words[0] == "shutdown":
                                self.controller.quit = True
                                self.stop()
                            if words[0] == "config":
                                cfg_name = words[1]
                                if "/" in cfg_name:
                                    break
                                if "\\" in cfg_name:
                                    break
                                if ":" in cfg_name:
                                    break
                                self.stop()
                                self.controller.apply_config(cfg_name)
            except Exception as err:
                print(f"chat thread got {err}, quitting")
                self.quit = True

    def stop(self):
        self.quit = True
        self.controller.stop()