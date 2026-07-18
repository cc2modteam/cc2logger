import threading
from secrets import token_bytes
from flask import Flask, render_template, request, redirect, session, abort
from flask import render_template as flask_render_template
from pysteamsignin.steamsignin import SteamSignIn
from http import HTTPStatus
from .logic import backends, public_hostname, webserver_cfg, get_steam_avatar, lookup_username
from cc2control.types import Blueprints, Loadout


app = Flask(__name__)
app.secret_key = token_bytes(24)


def render_template(
    template, **kwargs
) -> str:
    steam_id = session.get("steam_id")
    avatar = ""
    if steam_id:
        avatar = get_steam_avatar(steam_id)
    kwargs["avatar"] = avatar
    kwargs["username"] = lookup_username(steam_id)
    kwargs["steam_id"] = steam_id
    return flask_render_template(template, **kwargs)


@app.route("/")
def home():
    server_names = sorted(webserver_cfg.backends.keys())
    servers = {}
    for name in server_names:
        ctx = backends[name]
        servers[name] = ctx

    return render_template("index.html", servers=servers)

@app.route("/home/<server>/")
def server_home(server):
    if server not in backends:
        abort(404)

    context = backends[server]
    return render_template("serverhome.html",
                           context=context,
                           blueprints=Blueprints,
                           loadout=Loadout,
                           server=server
                           )


@app.route("/<server>/settings")
def settings(server: str):
    if server not in backends:
        abort(404)
    context = backends[server]
    return render_template("settings.html",
                           context=context,
                           blueprints=Blueprints,
                           loadout=Loadout,
                           server=server
                           )

@app.route("/<server>/wait")
def wait_page(server: str):
    if server not in backends:
        abort(404)
    context = backends[server]
    return render_template("wait.html",
                           context=context,
                           server=server)

@app.route("/<server>/configure", methods=["POST"])
def configure(server: str):
    if server not in backends:
        abort(404)

    steam_id = session.get("steam_id")
    if not steam_id or webserver_cfg.lookup_admin(steam_id) == "":
        return render_template("error.html",
                               message="Not authenticated",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value
    context = backends[server]
    context.stop_server()
    data = request.form
    allowed = {
        "max_players",
        "server_name",
        "blueprints",
        "loadout_type",
        "team_count_ai",
        "team_count_human",
        "password",
        "island_count",
        "island_count_per_team",
        "carrier_count_per_team",
        "base_difficulty",
    }
    send = {}
    for name in allowed:
        value = data.get(name, None)
        if value is not None:
            send[name] = value
    if send:
        context.post_json(send, "/cfg")
    return redirect(f"/{server}/wait")



@app.route("/<server>/action/<action>", methods=["POST"])
def actions(server: str, action: str):
    if server not in backends:
        abort(404)
    context = backends[server]

    admin_actions = {
        "start": context.start_server,
        "stop": context.stop_server,
    }

    steam_id = session.get("steam_id")
    admin_user = webserver_cfg.lookup_admin(steam_id)
    if not steam_id or admin_user == "":
        return render_template("error.html",
                               message="Not authenticated",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value

    if action in admin_actions:
        app.logger.info("action %s from user %s %s", action, admin_user, steam_id)
        bg = threading.Thread(target=admin_actions[action], daemon=True)
        bg.start()
        return redirect(f"/{server}/wait")

    return render_template("error.html",
                           message="Unknown action",
                           code=HTTPStatus.NOT_FOUND), HTTPStatus.NOT_FOUND.value


@app.route("/login")
def login():
    l = SteamSignIn()
    return l.RedirectUser(l.ConstructURL(f"{public_hostname}/steam-login"))


@app.route("/logout")
def logout():
    del session["steam_id"]
    return redirect("/")



@app.route("/steam-login")
def steam_login():
    l = SteamSignIn()
    steam_id = l.ValidateResults(request.values)

    if steam_id is False:
        return render_template("error.html",
                               message="Steam verification failed",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value

    admin_username = webserver_cfg.lookup_admin(steam_id)
    if admin_username != "":
        session["steam_id"] = steam_id
    else:
        return render_template("error.html",
                               message="Admin access denied",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value

    return redirect("/")