"""CC2 Team manager server"""
from http import HTTPStatus
from secrets import token_bytes
from pathlib import Path
from flask import Flask, request, redirect, session, abort
from pysteamsignin.steamsignin import SteamSignIn

from cc2admin.logic import public_hostname, lookup_steam_user
from cc2admin.webserver import render_template as base_render_template
from .logic import db, Player
import cc2admin

static_dir = Path(cc2admin.__file__).parent / "static"

app = Flask(__name__, static_folder=static_dir)
app.secret_key = token_bytes(24)

def authenticated() -> Player|None:
    uid = session.get("steam_id", "")
    if uid:
        return db.get_player(int(uid))
    return None

def render_template(
    template, **kwargs
) -> str:
    kwargs["db"] = db
    kwargs["user"] = authenticated()
    return base_render_template(template, **kwargs)


@app.route("/login")
def login():
    l = SteamSignIn()
    return l.RedirectUser(l.ConstructURL(f"{public_hostname}/steam-login"))


@app.route("/player/<player>/")
def view_player(player: str):
    p = db.get_player(player)
    return render_template("player.html", player=p)


@app.route("/team/<team>/")
def view_team(team: str|int):
    t = db.get_team(team)
    if not t:
        abort(404)
    return render_template("team.html", team=t)


@app.post("/team/<int:team>/player/join")
def join_team(team: int):
    user = authenticated()
    if user:
        t = db.get_team(team)
        if t:
            t.add_pending(user.steam_id)
            return redirect(f"/team/{t.id}")
        return redirect("/")
    return redirect("/login")


@app.post("/team/<int:team>/<string:action>/<string:apply>/<string:value>")
def team_action(team: int, action: str, apply: str, value: str):
    user = authenticated()
    if user:
        t = db.get_team(team)
        if not t:
            abort(HTTPStatus.NOT_FOUND)
        if t:
            if action == "player" and apply == "remove" and int(value) == user.steam_id:
                # can remove self (leave team)
                t.remove_user(user.steam_id)
                return redirect(f"/team/{t.id}")

            if not t.can_manage(user):
                abort(HTTPStatus.FORBIDDEN)
            if action == "pending":
                uid = int(value)
                if apply in ["approve", "deny"]:
                    if uid in t.pending_join:
                        t.pending_join.remove(uid)
                        t.write()
                    if apply == "approve":
                        u = db.get_player(uid)
                        if u and uid not in t.members and uid not in t.owners:
                            t.add_member(uid)
            elif action == "player":
                if apply == "remove":
                    t.remove_user(int(value))
            elif action == "owner":
                subj = db.get_player(int(value))
                if not subj:
                    abort(HTTPStatus.BAD_REQUEST)
                if apply == "add":
                    t.owners.append(subj.steam_id)
                elif apply == "remove":
                    t.owners.remove(subj.steam_id)
                t.write()
            else:
                abort(HTTPStatus.BAD_REQUEST)
            return redirect(f"/team/{t.id}")
        return redirect("/")
    abort(HTTPStatus.UNAUTHORIZED)


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