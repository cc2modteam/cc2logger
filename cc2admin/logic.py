"""Main logic for webserver"""
import os
import requests
from cachetools import cached, TTLCache
from cc2control.controller import ServerController

listen_port = int(os.environ.get("CC2_CONTROLLER_PORT", ServerController.DEFAULT_PORT))


class CC2:

    def __init__(self):
        self.port = listen_port

    def control_path(self, path: str = "") -> str:
        return f"http://127.0.0.1:{self.port}/{path}"

    def get_json(self, path: str = ""):
        resp = requests.get(self.control_path(path))
        resp.raise_for_status()
        return resp.json()

    @cached(cache=TTLCache(maxsize=1, ttl=5))
    def server_status(self) -> dict:
        return self.get_json()

    @property
    def status(self) -> dict:
        try:
            return self.server_status()
        except requests.HTTPError as err:
            return {
                "server_name": "Server Error",
                "status": f"Error {type(err)}"
            }
        except requests.ConnectionError:
            return {
                "server_name": "Offline",
                "status": "backend not running"
            }

    def server_name(self) -> str:
        return self.status.get("server_name")


context = CC2()
