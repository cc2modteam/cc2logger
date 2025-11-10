from typing import Optional, cast
from abc import ABC
from datetime import datetime
from .resolver import Vehicle

class MessageBase:
    def __init__(self):
        self.timestamp: Optional[datetime] = None
        self.type: str = "unknown"
        self._data: dict = {}

    def parse(self, data: dict):
        self._data = data
        self.timestamp = datetime.fromisoformat(data.get("timestamp"))


class TeamMessageBase(MessageBase, ABC):
    def __init__(self):
        super().__init__()
        self.team: int = 0

    def parse(self, data: dict):
        super().parse(data)
        self.team = int(data.get("team", data.get("team_id", self.team)))

class PlayerMessageBase(TeamMessageBase, ABC):
    def __init__(self):
        super().__init__()
        self.player_name: str = ""
        self.player_id: int = 0

    def parse(self, data: dict):
        super().parse(data)
        self.player_name = data.get("player_name", self.player_name)
        self.player_id = int(data.get("player_id", self.player_id))

class PlayerJoined(PlayerMessageBase):
    """Player joined the game"""

class PlayerLeft(PlayerMessageBase):
    """Player left the game"""

class PlayerChat(PlayerMessageBase):
    """Player sent a chat message"""
    def __init__(self):
        super().__init__()
        self.message: str = ""

    def parse(self, data: dict):
        super().parse(data)
        self.message = data.get("message", self.message)

class DestroyedVehicle(TeamMessageBase):
    """A vehicle was destroyed"""
    def __init__(self):
        super().__init__()
        self.vehicle_id: int = 0
        self.vehicle_type: int = 0

    def parse(self, data: dict):
        super().parse(data)
        self.vehicle_id = int(data.get("vehicle_id", self.vehicle_id))
        self.vehicle_type = int(data.get("vehicle_type", self.vehicle_type))

    @property
    def vehicle_type_name(self) -> str:
        return Vehicle.lookup(self.vehicle_type).name


class CapturedIsland(TeamMessageBase):
    def __init__(self):
        super().__init__()
        self.island_id: int = 0

    def parse(self, data: dict):
        super().parse(data)
        self.island_id = int(data.get("island_id", self.island_id))
        # yes, could lookup island name here


class MessageFactory:
    def __init__(self):
        self.dispatch = {
            "player_joined": PlayerJoined,
            "player_left": PlayerLeft,
            "chat": PlayerChat,
            "destroy_vehicle": DestroyedVehicle,
            "island_captured": CapturedIsland,
        }

    def parse(self, data: dict) -> Optional[MessageBase]:
        data_type = data.get("type", "")
        cls: type = self.dispatch.get(data_type, None)
        if cls:
            msg = cast(MessageBase, cls())
            msg.parse(data)
            return msg
        return None
