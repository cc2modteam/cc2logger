import sqlite3
from typing import Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from cc2admin.logic import lookup_username, get_steam_avatar, lookup_steam_user, webserver_cfg


@dataclass
class Player:
    steam_id: int
    @property
    def personaname(self) -> str:
        return lookup_username(str(self.steam_id))

    @property
    def admin(self) -> bool:
        return webserver_cfg.lookup_admin(self.steam_id) != ""

    @property
    def avatar(self) -> str:
        return get_steam_avatar(str(self.steam_id))

    @property
    def profile(self) -> str:
        user = lookup_steam_user(str(self.steam_id))
        if user:
            return user.get("player", {}).get("profileurl", "")
        return ""

    @property
    def steam(self) -> dict:
        return lookup_steam_user(str(self.steam_id))

    def __hash__(self):
        return hash(self.personaname)

    def __lt__(self, other):
        return self.personaname < other.personaname

@dataclass()
class PlayerTeam:
    name: str
    homepage: str = ""
    approved: bool = False
    owners: list[int] = field(default_factory=list)
    members: list[int] = field(default_factory=list)

    def __hash__(self):
        return hash(self.name)

    def get_owner_players(self) -> set[Player]:
        players = []
        for pid in self.owners:
            players.append(db.get_player(pid))
        return set(players)

    def get_member_players(self) -> set[Player]:
        players = self.get_owner_players()
        for pid in self.members:
            players.add(db.get_player(pid))
        return players

    def add_member(self, steam_id) -> bool:
        p = db.get_player(steam_id)
        if p:
            self.members.append(p.steam_id)
            return True
        return False


@dataclass
class EventTeam:
    event: int
    number: int
    max_players: int
    reserve_size: int
    members: list[int] = field(default_factory=list)
    invited_members: list[int] = field(default_factory=list)


@dataclass
class Event:
    id: int
    name: str
    public: bool
    start: datetime
    duration: timedelta

    @property
    def ended(self) -> bool:
        now = datetime.now()
        end_time = self.start + self.duration
        return now > end_time


class Database:
    def __init__(self):
        self.players: dict[int, Player] = {}
        self.playerteams: dict[str, PlayerTeam] = {}

    def register_player(self, steam_id) -> Player:
        p = self.get_player(steam_id)
        if not p:
            p = Player(int(steam_id))
            if p.personaname:
                self.players[p.steam_id] = p
        return p

    def unregister_player(self, steam_id) -> None:
        steam_id = int(steam_id)
        if steam_id in self.players:
            del self.players[steam_id]

    def get_player(self, steam_id) -> Optional[Player]:
        return self.players.get(int(steam_id), None)

    def get_playerteam(self, team_name: str) -> Optional[PlayerTeam]:
        return self.playerteams.get(team_name, None)

    def get_player_teams(self, steam_id) -> list[PlayerTeam]:
        teams = []
        steam_id = int(steam_id)
        for t in self.playerteams.values():
            if steam_id in t.owners or steam_id in t.members:
                teams.append(t)
        return teams


db = Database()
# canned data
bred = Player(steam_id=76561198074375146)
kazzik = Player(steam_id=76561198309216806)
point = Player(steam_id=76561198372252544)

grno = PlayerTeam("GRNO", "", owners=[
    bred.steam_id,
    kazzik.steam_id,
])
delta = PlayerTeam("Delta Fleet", "", owners=[
    point.steam_id
])

db.players = {
    bred.steam_id: bred,
    kazzik.steam_id: kazzik,
    point.steam_id: point,
}
db.playerteams = {
    delta.name: delta,
    grno.name: grno,
}