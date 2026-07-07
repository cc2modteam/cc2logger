"""Main logic for webserver"""
import os
import ssl

import yaml
import requests
from dataclasses import dataclass, field
from pathlib import Path
from cachetools import cached, TTLCache
from requests.adapters import HTTPAdapter

from cc2control.controller import ServerController

public_hostname = str(os.environ.get("CC2_WEBSERVER_HOST", "http://localhost:5000"))


@dataclass
class WebserverConfig:
    hostname: str
    backends: dict[str, str] = field(default=dict)
    admins: dict[int, str] = field(default=dict)

    def lookup_admin(self, steam_id: str|int) -> str|None:
        if steam_id:
            return self.admins.get(int(steam_id), "")
        return ""


def load_webserver_config() -> WebserverConfig:
    with open(Path.cwd() / "admin.yml") as fd:
        data = yaml.safe_load(fd)

    hostname = data.get("hostname", "localhost")
    backends = data.get("backends", {})
    admins = data.get("admin-users", {})

    return WebserverConfig(hostname=hostname, backends=backends, admins=admins)


class CC2:

    def __init__(self, backend_cfg: dict):
        self.cfg = backend_cfg
        self.host = backend_cfg.get("host")

    def control_path(self, path: str = "") -> str:
        return f"{self.host}/{path}"

    @cached(cache=TTLCache(maxsize=2, ttl=30))
    def get_session(self, host) -> requests.Session:
        s = requests.Session()
        ssl.create_default_context()

        if host.startswith("https://"):

            class Adapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    context = ssl.create_default_context()
                    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
                    super().init_poolmanager(*args, *kwargs, ssl_context=context)

            s.mount("https://", Adapter())

            key = self.cfg.get("key", None)
            crt = self.cfg.get("cert", None)
            ca = self.cfg.get("ca", None)
            if key and crt and ca:
                s.verify = ca
                s.cert = (crt, key)

        return s

    @property
    def session(self) -> requests.Session:
        return self.get_session(self.cfg.get("host"))

    def get_json(self, path: str = ""):
        resp = self.session.get(self.control_path(path))
        resp.raise_for_status()
        return resp.json()

    def post_json(self, data: dict, path: str = ""):
        resp = self.session.post(self.control_path(path), json=data)
        resp.raise_for_status()
        return resp.json()

    @cached(cache=TTLCache(maxsize=1, ttl=4))
    def server_status(self) -> dict:
        return self.get_json()

    @property
    def status(self) -> dict:
        try:
            return self.server_status()
        except requests.HTTPError as err:
            return {
                "server_name": "Server Error",
                "status": f"Error {type(err)}",
                "game_stats": {},
                "settings": {},
            }
        except requests.ConnectionError as err:
            print(str(err))
            return {
                "server_name": "Offline",
                "status": "backend not running",
                "game_stats": {},
                "settings": {},
            }

    def server_name(self) -> str:
        return self.status.get("server_name")

    def start_server(self):
        self.post_json({}, "start")

    def stop_server(self):
        self.post_json({}, "stop")


webserver_cfg = load_webserver_config()
backends = {}

for name, be in webserver_cfg.backends.items():
    backends[name] = CC2(be)