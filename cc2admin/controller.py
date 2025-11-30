import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from cc2logger.parser import CC2GameFollower
from cc2logger.messages import PlayerChat

CFG = Path.cwd() / "cc2-config.toml"


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

    return settings

def main():
    with CFG.open("rb") as fd:
        cfg = tomllib.load(fd)
    run(cfg)


def run(cfg):

    current_config = read_server_config(Path.cwd() / "server_config.xml")



