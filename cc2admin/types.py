from typing import Protocol
from abc import abstractmethod

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

    @abstractmethod
    def get_teams(self) -> dict[int, str]:
        pass

    @abstractmethod
    def get_mod_folders(self) -> list[str]:
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