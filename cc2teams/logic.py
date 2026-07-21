
import random
from typing import Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from sqlitedict import SqliteDict
from dataclasses_sqlitedict import SingleRowDataModel
from cc2admin.logic import lookup_username, get_steam_avatar, lookup_steam_user, webserver_cfg


db_dir = Path.cwd() / "teams-db"
db_dir.mkdir(exist_ok=True)


def can_manage(obj, user) -> bool:
    uid = -1
    if hasattr(obj, "owners"):
        if isinstance(user, Player):
            if user.admin:
                return True
            uid = user.steam_id
        elif isinstance(user, int):
            uid = user
        return uid in obj.owners
    return False

def get_table_type_dict(t):
    res = {}
    if hasattr(t, "db") and hasattr(t, "read"):
        for vid in t.db.keys():
            res[vid] = t.read(str(vid))
    return res


@dataclass
class Player(SingleRowDataModel):
    steam_id: int
    db = SqliteDict(str(db_dir / "player.sqlite"), autocommit=False)

    @property
    def prefix(self) -> str:
        return "player"

    @property
    def primary_key(self) -> str:
        return str(self.steam_id)

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
class PlayerTeam(SingleRowDataModel):
    id: str
    name: str
    homepage: str = ""
    approved: bool = False
    public: bool = False
    created: Optional[datetime] = None
    owners: list[int] = field(default_factory=list)
    members: list[int] = field(default_factory=list)
    pending_join: list[int] = field(default_factory=list)

    db = SqliteDict(str(db_dir / "playerteam.sqlite"), autocommit=False)

    @property
    def prefix(self) -> str:
        return "team"

    @property
    def primary_key(self) -> str:
        return self.id

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        if other and isinstance(other, type(self)):
            return self.name < other.name
        return False

    def delete(self):
        db.delete_team(self)

    def can_manage(self, user: int|Player) -> bool:
        return can_manage(self, user)

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

    @property
    def players(self) -> set[Player]:
        owners = self.get_owner_players()
        return owners.union(self.get_member_players())

    @property
    def pending_players(self) -> set[Player]:
        pend = set()
        for sid in self.pending_join:
            p = db.get_player(sid)
            if p:
                pend.add(p)
                self.write()

        return pend

    def add_member(self, steam_id) -> bool:
        p = db.get_player(steam_id)
        if p:
            self.members.append(p.steam_id)
            self.write()
            return True
        return False

    def add_pending(self, steam_id) -> bool:
        steam_id = int(steam_id)
        if steam_id not in self.members and steam_id not in self.pending_join:
            self.pending_join.append(steam_id)
            self.write()
            return True
        return False

    def remove_user(self, steam_id: int) -> None:
        if steam_id in self.pending_players:
            self.pending_join.remove(steam_id)
        if steam_id in self.members:
            self.members.remove(steam_id)
        self.write()


@dataclass
class EventTeam(PlayerTeam):
    event: str = ""

    db = SqliteDict(str(db_dir / "eventteam.sqlite"), autocommit=False)

    @property
    def prefix(self) -> str:
        return "event_team"

    @property
    def players(self) -> set[Player]:
        return self.get_member_players()

    def delete(self):
        db.delete_event_team(self)


@dataclass
class Event(PlayerTeam):
    id: str
    name: str
    start: Optional[datetime] = None
    duration: timedelta = timedelta(hours=1)
    public: bool = False
    locked: bool = False
    teams: list[str] = field(default_factory=list)
    owners: list[int] = field(default_factory=list)

    team_size: int = 6
    reserve_size: int = 1

    db = SqliteDict(str(db_dir / "event.sqlite"), autocommit=False)

    def __lt__(self, other):
        if self.start:
            if hasattr(other, "start"):
                return self.start < other.start
        return True

    def delete(self):
        for teamid in self.teams:
            team = db.get_event_team(teamid)
            if team:
                team.delete()
        db.delete_event(self)

    @property
    def prefix(self) -> str:
        return "event"

    @property
    def primary_key(self) -> str:
        return self.id

    def get_member_players(self) -> set[Player]:
        return set()

    def add_member(self, steam_id) -> bool:
        return False

    def remove_user(self, steam_id: int) -> None:
        pass

    @property
    def pending_players(self) -> set[Player]:
        return set()

    @property
    def players(self) -> set[Player]:
        return set()

    @property
    def ended(self) -> bool:
        now = datetime.now()
        end_time = self.start + self.duration
        return now > end_time

    def can_manage(self, user: int|Player) -> bool:
        return can_manage(self, user)

    @property
    def event_teams(self) -> list[EventTeam]:
        r = list(EventTeam.read(x) for x in self.teams)
        return r

    def leave_teams(self, player: Player):
        for t in self.event_teams:
            if player.steam_id in t.members:
                t.remove_user(player.steam_id)
                t.write()

    def join_team(self, team: EventTeam, player: Player):
        self.leave_teams(player)
        if len(team.members) < self.team_size:
            team.add_member(player.steam_id)
        else:
            team.add_pending(player.steam_id)
        team.write()

class Database:

    @staticmethod
    def player_ids() -> set[int]:
        return set(int(x) for x in Player.db.keys())

    @staticmethod
    def event_ids() -> set[str]:
        return set(x for x in Event.db.keys())

    @staticmethod
    def get_event(ident) -> Event|None:
        return Event.read(ident)

    @property
    def events(self) -> dict[str, Event]:
        return get_table_type_dict(Event)

    @property
    def playerteams(self) -> dict[str,PlayerTeam]:
        return get_table_type_dict(PlayerTeam)

    def register_player(self, steam_id) -> Player:
        p = self.get_player(steam_id)
        if not p:
            p = Player(int(steam_id))
            if p.personaname:
                p.write()
        return p

    def unregister_player(self, steam_id) -> None:
        steam_id = int(steam_id)
        if steam_id in self.players:
            del Player.db[str(steam_id)]
            Player.db.commit()

    def get_player(self, steam_id) -> Optional[Player]:
        if int(steam_id) in self.player_ids():
            p = Player.read(str(steam_id))
            return p
        return None

    def get_playerteam(self, team_name: str) -> Optional[PlayerTeam]:
        return self.playerteams.get(team_name, None)

    def get_player_teams(self, steam_id) -> list[PlayerTeam]:
        teams = []
        steam_id = int(steam_id)
        for t in self.playerteams.values():
            if steam_id in t.owners or steam_id in t.members:
                teams.append(t)
        return teams

    def team_ids(self) -> set[str]:
        return set(x for x in PlayerTeam.db.keys())

    def get_team(self, team: str) -> Optional[PlayerTeam]:
        ids = self.team_ids()
        if team in ids:
            return PlayerTeam.read(team)
        elif isinstance(team, str):
            for tid in ids:
                t = PlayerTeam.read(tid)
                if t and t.name.lower() == team.lower():
                    return t
        return None

    def get_event_team(self, team: str) -> Optional[EventTeam]:
        return EventTeam.read(team)

    def delete_team(self, team: PlayerTeam):
        if team and team.id in self.team_ids():
            del PlayerTeam.db[team.primary_key]
            PlayerTeam.db.commit()

    def team_name_exists(self, name) -> bool:
        for t in self.playerteams.values():
            if t.name.lower() == name.lower():
                return True
        return False

    def delete_event(self, event: Event):
        if event and event.id:
            del Event.db[event.primary_key]
            Event.db.commit()

    def delete_event_team(self, event: EventTeam):
        if event and event.id:
            del EventTeam.db[event.primary_key]
            EventTeam.db.commit()


db = Database()
#db.register_player(76561198309216806)
#db.register_player(76561198372252544)
#db.register_player(76561198808354666)

# canned data
# bred = Player(steam_id=76561198074375146)
# kazzik = Player(steam_id=76561198309216806)
# point = Player(steam_id=76561198372252544)
# db.players = {
#     bred.steam_id: bred,
#     kazzik.steam_id: kazzik,
#     point.steam_id: point,
# }
#
# test = PlayerTeam(1, "Test Team", "", public=True, owners=[
#     kazzik.steam_id,
# ])
# test.add_member(point.steam_id)
#
# grno = PlayerTeam(2, "GRNO", "", public=True,
#                   owners=[
#                       # bred.steam_id,
#                       kazzik.steam_id,
#                   ],
#                   members=[
#                       bred.steam_id
#                   ]
#                   )
# delta = PlayerTeam(3, "Delta Fleet", "",
#                    public=True,
#                    owners=[
#                        point.steam_id
#                    ])
# delta.add_member(point.steam_id)
# delta.add_member(bred.steam_id)
#
# db.players = {
#     bred.steam_id: bred,
#     kazzik.steam_id: kazzik,
#     point.steam_id: point,
# }
# db.playerteams = {
#     delta.id: delta,
#     grno.id: grno,
#     test.id: test,
# }
#
#
# bred.write()
# kazzik.write()
# point.write()
# grno.write()
# test.write()
# delta.write()