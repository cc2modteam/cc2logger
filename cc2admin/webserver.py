import threading
import time
import yaml
from secrets import token_bytes
from flask import Flask, render_template, request, redirect, session
from pysteamsignin.steamsignin import SteamSignIn
from http import HTTPStatus
from .logic import context, public_hostname
from cc2control.types import Blueprints, Loadout


app = Flask(__name__)
app.secret_key = token_bytes(24)

@app.route("/")
def home():
    steam_id = session.get("steam_id")
    return render_template("index.html",
                           context=context,
                           blueprints=Blueprints,
                           loadout=Loadout,
                           steam_id=steam_id,
                           username=context.lookup_admin(steam_id)
                           )


@app.route("/settings")
def settings():
    steam_id = session.get("steam_id")
    return render_template("settings.html",
                           context=context,
                           blueprints=Blueprints,
                           loadout=Loadout,
                           steam_id=steam_id,
                           username=context.lookup_admin(steam_id)
                           )

@app.route("/wait")
def wait_page():
    steam_id = session.get("steam_id")
    return render_template("wait.html",
                           context=context,
                           steam_id=steam_id,
                           username=context.lookup_admin(steam_id)
                           )

@app.route("/configure", methods=["POST"])
def configure():
    steam_id = session.get("steam_id")
    if not steam_id or context.lookup_admin(steam_id) == "":
        return render_template("error.html",
                               message="Not authenticated",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value

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
    return redirect("/wait")

admin_actions = {
    "start": context.start_server,
    "stop": context.stop_server,
}

@app.route("/action/<action>", methods=["POST"])
def actions(action: str):
    steam_id = session.get("steam_id")
    if not steam_id or context.lookup_admin(steam_id) == "":
        return render_template("error.html",
                               message="Not authenticated",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value

    if action in admin_actions:
        bg = threading.Thread(target=admin_actions[action], daemon=True)
        bg.start()
        return redirect("/wait")

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

    admin_username = context.lookup_admin(steam_id)
    if admin_username != "":
        session["steam_id"] = steam_id
    else:
        del session["steam_id"]

    return redirect("/")