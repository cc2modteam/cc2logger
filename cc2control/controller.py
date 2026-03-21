"""
CC2 Dedicated Server Control Harness

This usually runs under wine or on windows and listens on a local TCP socket.

"""
import os
import platform
import sys
import time
import yaml
import subprocess
from threading import Thread
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from argparse import ArgumentParser
from .types import ControllerProtocol
from .service.server import start_server

from cc2logger.parser import CC2GameFollower, CC2GameParser, generate_lua_stats_page, Player
from cc2logger.messages import PlayerChat
from .servercfgfile import ServerConfigXml

CFG = Path.cwd() / "cc2-config.toml"

CONTAINER = "cc2-server"
XML_CFG = "server_config.xml"

parser = ArgumentParser(description=__doc__)
parser.add_argument("--game-dir", type=Path, default=Path("Carrier Command 2"), help="Directory to the cc2 installation")
parser.add_argument("--config", type=str, help="Switch config file")
parser.add_argument("--debug", default=False, action="store_true")


def read_server_config(server_config: Path) -> Tuple[dict, ServerConfigXml]:
    settings = {}

    cfg = ServerConfigXml()
    cfg.from_xml(server_config.read_bytes())

    settings["admin_users"] = set(cfg.get_admins())
    settings["mods"] = set(cfg.get_mods())
    settings["server_name"] = cfg.server_name

    return settings, cfg

def main():
    opts = parser.parse_args()
    os.chdir(opts.game_dir)
    if opts.debug:
        os.environ["DEBUG"] = "1"
    controller = ServerController(Path.cwd())

    if opts.config:
        controller.apply_config(opts.config)

    controller.run()
    print(f"Listening for control on port {controller.listen_port}")

    while not controller.quit:
        time.sleep(2)


def is_linux() -> bool:
    return platform.system() == "Linux"


def get_admin_users(active_config: dict):
    return active_config.get("admin_users", set())


def debug(msg):
    if "DEBUG" in os.environ:
        print(msg)


def gather_player_stats(game_dir: Path):
    print("generating server stats ..")
    cp = CC2GameParser()
    logs_dir = game_dir / "logs"
    cp.read_path(logs_dir)

    rev_mod = game_dir / "mods" / "rev" / "content" / "scripts"

    if rev_mod.exists():
        server_stats_lua = generate_lua_stats_page(cp)
        if server_stats_lua:
            debug(f"stats ({len(server_stats_lua)} bytes)")
            (rev_mod / "library_custom_9.lua").write_bytes(server_stats_lua.encode("utf-8"))


class ServerController(ControllerProtocol):

    DEFAULT_PORT = 43432

    def __init__(self, game_folder: Path):
        self.game_folder: Path = game_folder
        self.server_process: Optional[subprocess.Popen] = None
        self.server_output: Path = self.game_folder / "server.log"
        self.server_xml: Path = self.game_folder / "server_config.xml"
        self.server_configs: Path = game_folder / "configs"
        self.follower: Optional[CC2GameFollower] = None
        self.current_server_config, self.server_cfg = read_server_config(self.server_xml)
        self.chat_thread: Optional[ChatThread] = None
        self.quit = False
        self.linux_pid = -1
        self.listen_port = int(os.environ.get("CC2_CONTROLLER_PORT", self.DEFAULT_PORT))
        self.server_ctx = None

    @property
    def server_name(self) -> str:
        return self.server_cfg.server_name

    @property
    def server_port(self) -> int:
        return self.server_cfg.port

    @property
    def save_name(self) -> str:
        return self.server_cfg.save_name

    @property
    def island_count(self) -> int:
        return self.server_cfg.island_count

    @property
    def base_difficulty(self) -> int:
        return self.server_cfg.base_difficulty

    @property
    def blueprints(self) -> int:
        return self.server_cfg.blueprints

    @property
    def loadout_type(self) -> int:
        return self.server_cfg.loadout_type

    def set_sever_option(self, name: str, value: int|str) -> None:
        prop = self.server_cfg.properties().get(name)
        if prop and isinstance(value, prop):
            self.stop()
            print(f"setting {name}")
            setattr(self.server_cfg, name, value)
            return
        raise ValueError()

    def get_mod_folders(self) -> list[str]:
        return [x.value for x in self.server_cfg.mods]

    def get_teams(self) -> dict[int, str]:
        teams = {}
        admins = self.get_global_admins().keys()
        if self.follower:
            for t, pl in self.follower.teams.items():
                if t not in teams:
                    teams[t] = []
                for p in pl.values():
                    p: Player
                    if not p.left:
                        name = f"{p.player_name}"
                        if p.player_id in admins:
                            name += "*"
                        teams[t].append(name)
        return teams

    def restart(self) -> None:
        self.stop()
        self.start()

    def status(self) -> str:
        if self.server_process and self.server_process.poll() is None:
            return "Running"
        return "Stopped"

    def get_admin_yml(self) -> dict:
        admin_yml = self.game_folder / "admin.yml"
        d = {}
        if admin_yml.exists():
            with admin_yml.open("r") as yy:
                d = yaml.safe_load(yy)
        return d

    def get_global_admins(self) -> dict[int, str]:
        d = self.get_admin_yml()
        return d.get("admin-users", {})

    def get_runner_cfg(self) -> str:
        d = self.get_admin_yml()
        return d.get("runner-script", {}).get(platform.system(), "")


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
        return self.get_runner_cfg()

    def apply_config(self, name: str) -> None:
        new_cfg = self.server_configs / f"{name}.xml"
        self.server_xml.write_bytes(new_cfg.read_bytes())
        self.current_server_config, self.server_cfg = read_server_config(self.server_xml)

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

        # configure admins
        self.current_server_config, self.server_cfg = read_server_config(self.server_xml)
        for admin in self.get_global_admins():
            if admin not in self.server_cfg.get_peers():
                p = self.server_cfg.add_peer(admin)
                p.is_admin = True
        self.server_xml.write_bytes(self.server_cfg.to_xml())
        self.current_server_config, self.server_cfg = read_server_config(self.server_xml)
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

        self.current_server_config, self.server_cfg = read_server_config(self.server_xml)

        print(f"Server: {self.current_server_config['server_name']}")
        for mod in self.current_server_config.get("mods"):
            print(f"Mod Folder: {mod}")
        for admin in self.current_server_config.get("admin_users"):
            print(f"Admin: {admin}")

        self.follower = CC2GameFollower()
        self.follower.debug_enabled = "DEBUG" in os.environ
        self.follower.open_latest(self.game_folder / "logs")
        self.chat_thread = ChatThread(self)
        self.chat_thread.start()

    def run_game(self) -> None:
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

    def run(self):
        start_server(self, port=self.listen_port)


class ChatThread(Thread):
    def __init__(self, controller: ServerController):
        super().__init__(daemon=True)
        self.controller = controller
        self.quit = False

    def run(self):
        last_stats = 0
        stats_interval = 600
        print("--")
        while not self.quit:

            elapsed = time.monotonic() - last_stats
            if elapsed > stats_interval:
                last_stats = time.monotonic()
                gather_player_stats(self.controller.game_folder)

            try:
                msg = self.controller.follower.read_one()
                if not msg:
                    time.sleep(2)
                    continue
                debug(f"{type(msg)}, {str(msg)}")
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