"""Main logic for webserver"""
import os
import requests
from cachetools import cached, TTLCache
from cc2control.controller import ServerController

listen_port = int(os.environ.get("CC2_CONTROLLER_PORT", ServerController.DEFAULT_PORT))
public_hostname = str(os.environ.get("CC2_WEBSERVER_HOST", "http://localhost:5000"))


class CC2:

    def __init__(self):
        self.port = listen_port

    def control_path(self, path: str = "") -> str:
        return f"http://localhost:{self.port}/{path}"

    def get_json(self, path: str = ""):
        resp = requests.get(self.control_path(path))
        resp.raise_for_status()
        return resp.json()

    def post_json(self, data: dict, path: str = ""):
        resp = requests.post(self.control_path(path), json=data)
        resp.raise_for_status()
        return resp.json()

    @cached(cache=TTLCache(maxsize=32, ttl=4))
    def lookup_admin(self, steam_id: int|str) -> str:
        if steam_id:
            try:
                steam_id = int(steam_id)
                admin_username = self.post_json({"steam_id": steam_id}, "is_admin")
                return admin_username
            except ConnectionError:
                pass
            except ValueError:
                pass
        return ""

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
                "settings": {},
            }
        except requests.ConnectionError:
            return {
                "server_name": "Offline",
                "status": "backend not running",
                "settings": {},
            }

    def server_name(self) -> str:
        return self.status.get("server_name")

    def start_server(self):
        self.post_json({}, "start")

    def stop_server(self):
        self.post_json({}, "stop")


context = CC2()
