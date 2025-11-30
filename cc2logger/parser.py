import json
from datetime import datetime, timedelta
from abc import abstractmethod, ABC
from typing import Optional
from pathlib import Path
from .resolver import Vehicle
from .messages import MessageBase, MessageFactory, PlayerJoined, PlayerLeft, CapturedIsland, DestroyedVehicle


class JsonlParserBase(ABC):
    def __init__(self):
        self.filepath: Optional[Path] = None
        self._fd = None
        self._rx = ""

    def open(self, filepath: Path):
        self.filepath = filepath
        self._fd = self.filepath.open("r", encoding="utf-8")

    def close(self):
        if self._fd:
            self._fd.close()

    def read(self, filepath: Path) -> None:
        try:
            self.open(filepath)
            while True:
                msg = self.read_one()
                if not msg:
                    break
        finally:
            self.close()


    @abstractmethod
    def on_message(self, data: dict) -> Optional[MessageBase]:
        pass

    def read_chunk(self):
        chunk = self._fd.readline()
        if chunk:
            self._rx += chunk.replace("\n", " ")
        else:
            return None

        return self._rx

    def read_one(self) -> Optional[MessageBase]:
        if self._fd:
            while True:
                try:
                    chunk = self.read_chunk()
                    if chunk is None:
                        self._rx = ""
                        break
                    data = json.loads(chunk)
                    self._rx = ""
                    return self.on_message(data)
                except json.JSONDecodeError:
                    pass

        return None


class Player:
    def __init__(self, player_id: int, player_name: str):
        self.player_id = player_id
        self.player_name = player_name
        self.teams: dict[int, timedelta] = {}
        self.team: int = 0
        self.joined: Optional[datetime] = None
        self.left: Optional[datetime] = None

    def update_team_left(self, event_timestamp):
        self.left = event_timestamp
        team_timespan = self.left - self.joined
        if self.team not in self.teams:
            self.teams = {self.team: team_timespan}
        else:
            self.teams[self.team] += team_timespan

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.player_name


class CC2GameParser(JsonlParserBase):

    def __init__(self):
        super().__init__()
        self.factory = MessageFactory()
        self.first_message: Optional[MessageBase] = None
        self.last_message: Optional[MessageBase] = None
        self.joined: list[PlayerJoined] = []
        self.players: dict[int, Player] = {}
        self.island_captures = 0
        self.destroyed_stats = {}
        for item in Vehicle:
            self.destroyed_stats[item.name] = 0
        self.teams: dict[int, dict[int, Player]] = {}

    def reset(self):
        self.first_message = None
        self.last_message = None
        self.joined.clear()
        self.players.clear()
        self.destroyed_stats.clear()
        self.teams.clear()

    @property
    def started(self) -> Optional[datetime]:
        if self.first_message:
            return self.first_message.timestamp
        return None

    @property
    def duration(self) -> timedelta:
        if self.first_message and self.last_message:
            return self.last_message.timestamp - self.first_message.timestamp
        return timedelta(seconds=0)

    @property
    def player_names(self) -> dict[int, str]:
        found = {}
        for msg in self.joined:
            found[msg.player_id] = msg.player_name
        return found

    def on_message(self, data: dict) -> Optional[MessageBase]:
        message = self.factory.parse(data)
        if message:
            self.last_message = message
            if not self.first_message:
                self.first_message = message
            if isinstance(message, PlayerJoined):
                self.joined.append(message)
                player = self.players.get(message.player_id, Player(message.player_id, message.player_name))
                player.team = message.team
                player.joined = message.timestamp
                self.players[player.player_id] = player

                if player.team not in self.teams:
                    self.teams[player.team] = {}
                self.teams[player.team][player.player_id] = player

            elif isinstance(message, PlayerLeft):
                player = self.players.get(message.player_id)
                player.team = message.team
                player.update_team_left(message.timestamp)
                player.team = -1

            elif isinstance(message, CapturedIsland):
                self.island_captures += 1
            elif isinstance(message, DestroyedVehicle):
                self.destroyed_stats[message.vehicle_type_name] += 1
        return message

    def read(self, filepath: Path) -> None:
        super().read(filepath)
        for player in self.players.values():
            if player.team > 0:
                player.update_team_left(self.last_message.timestamp)


class CC2GameFollower(CC2GameParser):
    def __init__(self):
        super().__init__()
        self.stop = False
        self.folder: Optional[Path] = None

    def open_latest(self, folder):
        self.folder = folder
        files = sorted(list(self.folder.glob("game_log_*.jsonl")))
        last = files[-1]
        self.open(last)

    def read_chunk(self):
        if self.stop:
            raise StopIteration()
        return super().read_chunk()

    def read_one(self) -> Optional[MessageBase]:
        try:
            return super().read_one()
        except StopIteration:
            self.reset()