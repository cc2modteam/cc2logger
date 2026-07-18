"""CC2 Team manager server"""
from http import HTTPStatus
from secrets import token_bytes
from pathlib import Path
from flask import Flask, request, redirect, session, abort
from pysteamsignin.steamsignin import SteamSignIn

from cc2admin.logic import public_hostname, lookup_steam_user
from cc2admin.webserver import render_template as base_render_template
from .logic import db
import cc2admin

static_dir = Path(cc2admin.__file__).parent / "static"

app = Flask(__name__, static_folder=static_dir)
app.secret_key = token_bytes(24)

def render_template(
    template, **kwargs
) -> str:
    kwargs["db"] = db
    kwargs["user"] = None
    steam_id = session.get("steam_id", "")
    if steam_id:
        kwargs["user"] = db.get_player(int(steam_id))

    return base_render_template(template, **kwargs)


@app.route("/login")
def login():
    l = SteamSignIn()
    return l.RedirectUser(l.ConstructURL(f"{public_hostname}/steam-login"))


@app.route("/player/<player>/")
def view_player(player: str):
    p = db.get_player(player)
    return render_template("player.html", player=p)


@app.route("/logout")
def logout():
    del session["steam_id"]
    return redirect("/")


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/steam-login")
def steam_login():
    l = SteamSignIn()
    steam_id = l.ValidateResults(request.values)

    if steam_id is False:
        return render_template("error.html",
                               message="Steam verification failed",
                               code=HTTPStatus.UNAUTHORIZED), HTTPStatus.UNAUTHORIZED.value
    session["steam_id"] = steam_id
    return redirect("/")