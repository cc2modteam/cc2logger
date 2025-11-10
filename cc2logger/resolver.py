from enum import Enum

class Vehicle(Enum):
    Albatross = 8
    Barge = 16
    Bear = 6
    Carrier = 0
    Droid = 97
    Jetty = 64
    Lifeboat = 57
    Manta = 10
    Mule = 88
    Needlefish = 77
    Petrel = 14
    Razorbill = 12
    Seal = 2
    Swordfish = 79
    Turret = 59
    VirusBot = 58
    Walrus = 4

    @classmethod
    def lookup(cls, value):
        for item in cls:
            if item.value == value:
                return item
        raise KeyError(value)

    @classmethod
    def reverse_lookup(cls, name):
        for item in cls:
            if item.name == name:
                return item
        raise KeyError(name)