"""
Simple threaded TCP server for command messages and status queries
"""
import json
import typing

from http import HTTPStatus
from threading import Thread
from ..types import ControllerProtocol
from cc2control.servercfgfile import ServerConfigXml
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


class ControlRequestHandler(SimpleHTTPRequestHandler):
    server_version = "CC2Admin Control Service"

    @property
    def ctx(self) -> "ServerCtx":
        return typing.cast(ControlServer, self.server).context

    def make_headers(self, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.end_headers()

    def send_resp(self, msg: dict) -> None:
        self.wfile.write(json.dumps(msg).encode("utf-8"))

    def do_HEAD(self):
        self.make_headers(HTTPStatus.METHOD_NOT_ALLOWED)

    def do_GET(self):
        func = self.ctx.endpoints["GET"].get(self.path, None)
        if not func:
            self.make_headers(HTTPStatus.NOT_FOUND)
        else:
            self.make_headers()
            self.send_resp(func(self.path))

    def do_POST(self):
        func: typing.Callable[[dict], dict]|None = self.ctx.endpoints["POST"].get(self.path, None)
        if not func:
            self.make_headers(HTTPStatus.NOT_FOUND)
        else:
            try:
                req_size = int(self.headers.get("Content-Length", 0))
                if req_size < 2 or req_size > 512:
                    self.send_response(HTTPStatus.BAD_REQUEST, "size out of range")
                    return
                msg = self.rfile.read(req_size).decode("utf-8")
                data = json.loads(msg)
                result = func(data)
                self.make_headers()
                self.send_resp(result)
            except Exception as err:
                self.log_error(f"{type(err)} {err}")
                self.make_headers(HTTPStatus.INTERNAL_SERVER_ERROR)


class ServerCtx:
    def __init__(self, controller: ControllerProtocol, server: "ControlServer"):
        self.controller = controller
        self.mainthread: Thread|None = None
        self.server = server
        self.endpoints = {
            "GET": {
                "/": self.get_status,
            },
            "POST": {
                "/start": self.post_start,
                "/stop": self.post_stop,
                "/restart": self.post_restart,
                "/cfg": self.post_set_option,
                "/is_admin": self.post_lookup_admin,
            }
        }

    def start(self) -> None:
        self.server.context = self
        t = Thread(daemon=True, target=self.server.serve_forever)
        self.mainthread = t
        t.start()

    def get_status(self, path) -> dict:

        all_props = ServerConfigXml.properties().keys()
        hide_props = set()

        settings = {
            "mods_list": self.controller.get_mod_folders()
        }
        for name in all_props:
            if name in hide_props:
                continue
            if hasattr(self.controller, name):
                settings[name] = getattr(self.controller, name)

        return {
            "server_name": self.controller.server_name,
            "status": self.controller.status(),
            "players": self.controller.get_teams(),
            "settings": settings,
        }

    def post_lookup_admin(self, req: dict) -> str:
        steam_id = req.get("steam_id", 0)
        if steam_id:
            try:
                steam_id = int(steam_id)
                admins = self.controller.get_global_admins()
                if steam_id in admins:
                    return admins.get(steam_id)
            except ValueError:
                pass
        return ""

    def post_start(self, req: dict) -> dict:
        self.controller.start()
        return {
            "status": "starting"
        }

    def post_stop(self, req: dict) -> dict:
        self.controller.stop()
        return {
            "status": "stopping"
        }

    def post_restart(self, req: dict) -> dict:
        self.post_stop(req)
        return self.post_start(req)

    def post_set_option(self, req: dict) -> dict:
        for name, value in req.items():
            if isinstance(value, int) or isinstance(value, str):
                self.controller.set_server_option(name, value)
        self.controller.save_config()
        return {}


class ControlServer(ThreadingHTTPServer):
    def __init__(self, addr, handler):
        super().__init__(addr, handler)
        self.context: ServerCtx|None = None


def start_server(controller: ControllerProtocol, port=11131, addr="127.0.0.1") -> ServerCtx:
    print(f"Start control service. port={port}")
    ctx = ServerCtx(controller, ControlServer((addr, port), ControlRequestHandler))
    ctx.start()
    return ctx



