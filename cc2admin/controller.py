import tomllib
import time
import shutil
import subprocess
import xml.etree.ElementTree as ET
import sys
from pathlib import Path


from cc2logger.parser import CC2GameFollower, CC2GameParser, generate_lua_stats_page
from cc2logger.messages import PlayerChat

CFG = Path.cwd() / "cc2-config.toml"

CONTAINER = "cc2-server"
XML_CFG = "server_config.xml"
DOCKER = shutil.which("docker")


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

    for item in root:
        if isinstance(item, ET.Element):
            if item.tag == "permissions":
                for child in item:
                    if child.tag == "peer":
                        ident = child.attrib.get("steam_id")
                        if child.attrib.get("is_admin").lower() == "true":
                            settings["admin_users"].add(ident)

    return settings

def main():
    with CFG.open("rb") as fd:
        cfg = tomllib.load(fd)
    run(cfg)


def docker_volume_exec(volume: str, args: list, stdin=None):
    cmdline = [
        DOCKER, "run", "-v", f"{volume}:/vol", "-w", "/vol", "--rm", "-i", "alpine:3.2"
    ] + args
    if stdin is None:
        subprocess.run(cmdline, shell=False, check=True)
    else:
        proc = subprocess.Popen(cmdline, stdin=subprocess.PIPE)
        proc.communicate(stdin)
        proc.wait()


def stop_server(cfg: dict):
    subprocess.run(cfg["stop-server"], shell=True, check=False)
    time.sleep(2)

def run_server(cfg: dict, cfg_xml: Path):
    subprocess.check_call(cfg["run-server"], shell=True)
    while not cfg_xml.exists():
        print(f"waiting for {cfg_xml.name}..")
        time.sleep(2)


def is_alive():
    try:
        output = subprocess.check_output([
            DOCKER, "exec", CONTAINER, "ps", "-e", "-o", "pid,cmd"
        ], encoding="utf-8", shell=False, stderr=subprocess.STDOUT)

        for line in output.splitlines():
            words = line.strip().split()
            if len(words) == 2:
                if words[1] == "/carriercommand/dedicated_server.exe":
                    return True

    except subprocess.CalledProcessError as err:
        pass

    return False


def change_config(cfg, new_config: str):
    stop_server(cfg)

    volume = cfg["docker-volume"]
    cfg_dir = Path(cfg["server-configs-dir"])
    available = {x.name for x in cfg_dir.glob("*.xml")}
    if f"{new_config}.xml" in available:
        docker_volume_exec(volume, ["rm", "-f", XML_CFG])
        print(f"Write {new_config} to server config")
        use_file = cfg_dir / f"{new_config}.xml"
        content = use_file.read_bytes()
        docker_volume_exec(volume, ["tee", XML_CFG], content)
        print("Done")
    else:
        print(f"Config {new_config} does not exist")


def get_admin_users(active_config: dict):
    return active_config.get("admin_users", set())


def run(cfg):
    # run the server
    server_dir = Path(cfg["server-install-dir"])
    cfg_xml = server_dir / XML_CFG

    change_config(cfg, "default")
    last_stats_update = 0

    while True:
        run_server(cfg, cfg_xml)
        while not is_alive():
            time.sleep(5)
            print("waiting for startup..")

        print("server up")
        # server up, run the log follower
        active_config = read_server_config(cfg_xml)

        admin_users = get_admin_users(active_config)

        follower = CC2GameFollower()
        follower.open_latest(server_dir / "logs")
        print("waiting for commands..")
        while True:
            msg = follower.read_one()
            if not msg:
                time.sleep(2)
                if not is_alive():
                    print("server exited")
                    break
            if isinstance(msg, PlayerChat):
                if str(msg.player_id) in admin_users:
                    do_admin_command(msg, cfg, follower)

            if time.monotonic() - last_stats_update > 120:
                last_stats_update = time.monotonic()
                gather_player_stats(cfg)



def do_admin_command(msg, cfg, follower):
    if msg.message.startswith("/"):
        words = msg.message.lstrip("/").split()
        if len(words):
            cmd = words[0]

            if cmd == "restart":
                print(f"Stop Server from {msg.player_name}")
                stop_server(cfg)
            elif cmd == "config":
                if len(words) == 2:
                    print(f"Swap config tp {words[1]} from {msg.player_name}")
                    change_config(cfg, words[1])
            elif cmd == "shutdown":
                stop_server(cfg)
                sys.exit(0)


def gather_player_stats(cfg):
    server_dir = Path(cfg["server-install-dir"])
    parser = CC2GameParser()
    logs_dir = server_dir / "logs"
    parser.read_path(logs_dir)

    server_stats_lua = generate_lua_stats_page(parser)
    if server_stats_lua:
        custom9 = Path("rom_0") / "scripts" / "library_custom_9.lua"
        docker_volume_exec(cfg["docker-volume"],
                           ["tee", str(custom9)])