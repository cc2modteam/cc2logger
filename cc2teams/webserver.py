"""CC2 Team manager server"""
import datetime
import uuid
from http import HTTPStatus
from secrets import token_bytes
from pathlib import Path
from typing import Optional

from flask import Flask, request, redirect, session, abort
from pysteamsignin.steamsignin import SteamSignIn
import profanity_check
from cc2admin.logic import public_hostname
from cc2admin.webserver import render_template as base_render_template
from .logic import db, Player, PlayerTeam, Event
import cc2admin

static_dir = Path(cc2admin.__file__).parent / "static"

app = Flask(__name__, static_folder=static_dir)
app.secret_key = token_bytes(24)
app.url_map.strict_slashes = False

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
    user = authenticated()
    if user:
        p = db.get_player(player)
        if not p:
            abort(404)
        return render_template("player.html", player=p)
    return redirect("/login")

@app.route("/players")
def view_players():
    user = authenticated()
    players = []
    if user:
        player_ids = db.player_ids()
        for pid in player_ids:
            players.append(db.get_player(pid))

    return render_template("players.html", players=players)

@app.route("/team/<team>/")
def view_team(team: str):
    t = db.get_team(team)
    if not t:
        abort(404)
    return render_template("team.html", team=t)


@app.post("/team/<string:team>/player/join")
def join_team(team: str):
    user = authenticated()
    if user:
        t = db.get_team(team)
        if t:
            t.add_pending(user.steam_id)
            return redirect(f"/team/{t.id}")
        return redirect("/")
    return redirect("/login")


@app.post("/team/<string:team>/delete/")
def delete_team(team: str):
    return delete_subject(db.get_team(team))

@app.post("/event/<string:evt>/delete/")
def delete_event(evt: str):
    return delete_subject(db.get_event(evt))

def delete_subject(t):
    user = authenticated()
    if user:
        form = request.form
        confirm_action = form.get("confirm")
        if confirm_action != "yes":
            return redirect(f"/confirm/{t.prefix}/{t.id}/delete/")

        if t and t.can_manage(user):
            t.delete()
        return redirect("/")
    return redirect("/login")

@app.route("/new/team")
def new_team_form():
    if not authenticated():
        redirect("/login")
    return render_template("new-team.html")

@app.route("/new/event")
def new_event_form():
    if not authenticated():
        redirect("/login")
    return render_template("new-event.html")


@app.post("/team/new")
def create_team():
    return create_team_object("team", PlayerTeam, check_name=lambda x: db.team_name_exists(x))


@app.post("/event/new")
def create_event():
    def created_event(evt: Event):
        evt.created = datetime.datetime.now()
        data = request.form
        start = data.get("start_date", None)
        if start:
            dt = datetime.datetime.strptime(start, "%Y-%m-%dT%H:%M")
            evt.start = dt
        hrs = data.get("evt_hours")
        mins = data.get("evt_mins")
        if hrs and mins:
            if hrs.isnumeric() and mins.isnumeric():
                ts = datetime.timedelta(hours=int(hrs), minutes=int(mins))
                evt.duration = ts

    return create_team_object("event", Event, check_name=None, custom=created_event)


@app.route("/events")
def list_events():
    events = db.events
    return render_template("/events.html", events=events)


@app.route("/event/<string:evt>")
def view_event(evt: str):
    e = db.get_event(evt)
    if not e:
        abort(HTTPStatus.NOT_FOUND)
    return render_template("/event.html", event=e)


def create_team_object(typename: str, objtype,
                       check_name: Optional[callable] = None,
                       custom: Optional[callable] = None):
    user = authenticated()
    if user:
        data = request.form
        name = data.get("name", "").strip()
        url = data.get("homepage", "")
        reject = ""
        if name:
            if len(name) > 63:
                reject = "Name too long"
            else:
                p1 = profanity_check.predict([name])
                if 1 in p1:
                    reject = "Profanity checker rejected team name"
                p2 = profanity_check.predict([url])
                if 1 in p2:
                    reject = "Profanity checker rejected team homepage"

                if check_name:
                    existing = check_name(name)
                    if existing:
                        reject = "A team with this name already exists"

            if reject:
                return render_template("/error.html", message=reject)

            new_id = str(uuid.uuid4())
            new_team = objtype(new_id, name, url)
            new_team.owners = [user.steam_id]
            new_team.add_member(user.steam_id)
            if custom:
                custom(new_team)
            new_team.write()
            return redirect(f"/{typename}/{new_id}")

        else:
            return redirect(f"/new/{typename}")

    abort(401)


@app.post("/confirm/<string:subject_type>/<string:subject>/<string:action>/<string:apply>/<string:value>")
@app.post("/confirm/<string:subject_type>/<string:subject>/<string:action>/<string:apply>")
@app.post("/confirm/<string:subject_type>/<string:subject>/<string:action>")
def confirm(subject_type: str, subject: str, action: str, apply: str = "", value: str = ""):
    user = authenticated()
    if user:
        subject_display_type = subject_type
        if subject_type in ["team", "event"]:
            t = None
            if subject_type == "team":
                t = db.get_team(subject)
            elif subject_type == "event":
                t = db.get_event(subject)

            if not t:
                abort(HTTPStatus.NOT_FOUND)
            if t.can_manage(user):
                message = f"{subject_display_type} '{t.name}' {action} > {apply}?"
                if action == "delete":
                    message = f"Delete {subject_display_type} '{t.name}'?"
                elif action == "owner":
                    p = db.get_player(int(value))
                    if not p:
                        abort(HTTPStatus.BAD_REQUEST)
                    message = f"{apply} '{p.personaname}' as '{t.name}' manager?"

                elif action == "player":
                    if apply == "remove":
                        if value == str(user.steam_id):
                            message = f"Leave {subject_display_type} '{t.name}'?"
                        else:
                            p = db.get_player(int(value))
                            if not p:
                                abort(HTTPStatus.BAD_REQUEST)
                            message = f"Remove '{p.personaname}' from {subject_display_type} '{t.name}'?"

                    elif apply == "join":
                        message = f"Join {subject_type} '{t.name}'?"
                return render_template("confirm.html", team=t,
                                       message = message,
                                       subject_type=subject_type,
                                       subject=subject,
                                       action=action,
                                       apply=apply,
                                       value=value)
        abort(HTTPStatus.FORBIDDEN)
    abort(HTTPStatus.UNAUTHORIZED)

@app.post("/team/<string:team>/<string:action>/<string:apply>/<string:value>")
def team_action(team: str, action: str, apply: str, value: str):
    t = db.get_team(team)
    return do_subject_action(t, action, apply, value)

@app.post("/event/<string:evt>/<string:action>/<string:apply>/<string:value>")
def event_action(evt: str, action: str, apply: str, value: str):
    t = db.get_event(evt)
    return do_subject_action(t, action, apply, value)

def do_subject_action(t, action: str, apply: str, value: str):
    user = authenticated()
    if user:
        prefix = t.prefix
        form = request.form
        confirm_action = form.get("confirm")
        if confirm_action != "yes":
            return redirect(f"/confirm/{prefix}/{t}/{action}/{apply}/{value}")
        if not t:
            abort(HTTPStatus.NOT_FOUND)
        if t:
            if action == "player" and apply == "remove" and int(value) == user.steam_id:
                # can remove self (leave team)
                t.remove_user(user.steam_id)
                return redirect(f"/{prefix}/{t.id}")

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
                        if u and uid not in t.members:
                            t.add_member(uid)
            elif action == "public":
                t.public = apply == "public"
                t.write()
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
            return redirect(f"/{prefix}/{t.id}")
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

    user = db.get_player(int(steam_id))
    if not user:
        Player(int(steam_id)).write()

    return redirect("/")