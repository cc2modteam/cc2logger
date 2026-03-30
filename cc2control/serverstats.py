"""Record basic short term runtime stats"""
import time
from datetime import datetime
from cc2logger.messages import DestroyedVehicle, CapturedIsland, MessageBase

class Stats:
    def __init__(self):
        self.destroyed_vehicles = []
        self.captured_islands = []
        self.started = time.monotonic()

    @property
    def age(self) -> float:
        return time.monotonic() - self.started

    def record_event(self, event: MessageBase) -> bool:
        if isinstance(event, DestroyedVehicle):
            self.destroyed_vehicles.append(event)
        elif isinstance(event, CapturedIsland):
            self.captured_islands.append(event)
        else:
            return False
        print(f"{datetime.now().isoformat()} {event}")
        return True