from typing import Protocol
from abc import abstractmethod
from enum import Enum

class ControllerProtocol(Protocol):

    @property
    @abstractmethod
    def server_name(self) -> str:
        pass

    @property
    @abstractmethod
    def server_port(self) -> int:
        pass

    @property
    @abstractmethod
    def save_name(self) -> str:
        pass

    @property
    @abstractmethod
    def island_count(self) -> int:
        pass

    @property
    @abstractmethod
    def base_difficulty(self) -> int:
        pass

    @property
    @abstractmethod
    def blueprints(self) -> int:
        pass

    @property
    @abstractmethod
    def loadout_type(self) -> int:
        pass

    @abstractmethod
    def get_teams(self) -> dict[int, str]:
        pass

    @abstractmethod
    def get_global_admins(self) -> dict[int, str]:
        pass

    @abstractmethod
    def get_mod_folders(self) -> list[str]:
        pass

    @abstractmethod
    def set_server_option(self, name: str, value: int | str) -> None:
        pass

    def save_config(self) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the game server"""

    @abstractmethod
    def restart(self) -> None:
        """Restart the game server"""

    @abstractmethod
    def start(self):
        """Start the game server"""

    @abstractmethod
    def status(self) -> str:
        """Get the server status"""


class Blueprints(Enum):
    default = 0
    none = 1
    all = 2

class Loadout(Enum):
    default = 0
    minimal = 1
    complete = 2