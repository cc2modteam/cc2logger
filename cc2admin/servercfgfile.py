"""A cc2 server_config.xml generator"""
import re
from io import BytesIO
from xml.etree import ElementTree

def within_range(value: int, lower: int, upper: int):
    return lower < value < upper


class DataDict:
    tag = None
    def __init__(self):
        self.data = {}
        self.set_defaults()
        
    def set_defaults(self):
        for name in dir(self):
            getattr(self, name)

    def to_xml(self) -> ElementTree.Element:
        e = ElementTree.Element(self.tag)
        for item, value in self.data.items():
            if value in [True, False]:
                value = str(value).lower()
            e.set(item, str(value))
        return e


class validate:
    def __init__(self, default_value):
        self.default_value = default_value
        self.real_value = None
        self.public_name = None

    def check_value(self, value) -> bool:
        return False

    def parse_value(self, value):
        if self.check_value(value):
            return value
        raise ValueError()

    def __set_name__(self, owner, name):
        self.public_name = name

    def __get__(self, instance, value):
        real = instance.data.get(self.public_name, self.default_value)
        if self.public_name not in instance.data:
            instance.data[self.public_name] = real
        return real

    def __set__(self, instance, value):
        try:
            instance.data[self.public_name] = self.parse_value(value)
        except ValueError:
            raise ValueError(f"validation of {self.public_name} failed ({value})")


class validate_int(validate):
    def __init__(self, default_value: int, lowest: int, highest: int):
        super().__init__(default_value)
        self.lowest = lowest
        self.highest = highest

    def check_value(self, value: int|str) -> bool:
        if isinstance(value, str):
            value = int(value)
        return self.lowest <= value <= self.highest

    def parse_value(self, value):
        return int(value)


class validate_bool(validate):
    def check_value(self, value: int|bool) -> bool:
        if isinstance(value, str):
            value = value == "true"
        return value is True or value is False


class validate_str(validate):
    def __init__(self, default_value: str, maxlen: int):
        super().__init__(default_value)
        self.maxlen = maxlen

    def check_value(self, value) -> bool:
        if value:
            return len(value) < self.maxlen
        return True

class validate_filename(validate_str):
    def __init__(self, default_value=""):
        super().__init__(default_value, 64)

    def check_value(self, value: str) -> bool:
        value = str(value)
        if super().check_value(value):
            if "/" in value:
                return False
            if "\\" in value:
                return False

            if ".." in value:
                return False
            return True
        return False

class validate_filepath(validate_filename):
    def check_value(self, value: str) -> bool:
        parts = re.split(r"[\\/]", value)
        for part in parts:
            if not super().check_value(part):
                return False
        return len(parts) > 0


class CfgPermissionPeer(DataDict):
    """
        <peer steam_id="76561198074375146" is_banned="false" is_admin="true"/>
    """
    tag = "peer"
    steam_id = validate_int(0, 0, 2**64)
    is_banned = validate_bool(False)
    is_admin = validate_bool(False)



class CfgModValue(DataDict):
    tag = "mod"
    value = validate_filepath()


class ServerConfigXml(DataDict):
    port = validate_int(25565, 1024, 65532)
    max_players = validate_int(4, 1, 12)
    server_name = validate_str("CC2 Server", 48)
    password = validate_str("", 32)
    save_name = validate_filename()
    island_count = validate_int(12, 2, 64)
    island_count_per_team = validate_int(1, 1, 64)
    carrier_count_per_team = validate_int(1, 1, 6)
    team_count_ai = validate_int(0, 0, 8)
    team_count_human = validate_int(1, 1, 8)
    base_difficulty = validate_int(1, 1, 3)
    loadout_type = validate_int(1, 0, 2)
    blueprints = validate_int(1, 0, 2)
    game_data_path = validate_filename("rom_0")

    def __init__(self):
        super().__init__()
        self.permissions: list[CfgPermissionPeer] = []
        self.mods: list[CfgModValue] = []
        # set defaults
        for name in dir(self):
            getattr(self, name)


    def get_mods(self) -> list[str]:
        return [x.value for x in self.mods]

    def remove_mod(self, mod_folder: str):
        keep = []
        for mod in self.mods:
            if mod.value != mod_folder:
                keep.append(mod)
        self.mods.clear()
        self.mods.extend(keep)

    def add_mod(self, mod_folder: str) -> None:
        m = CfgModValue()
        m.value = mod_folder
        self.remove_mod(mod_folder)
        self.mods.append(m)

    def get_peers(self) -> set[int]:
        return set([int(x.steam_id) for x in self.permissions])
    
    def get_admins(self) -> set[int]:
        return set([x.steam_id for x in self.permissions if x.is_admin])

    def get_peer(self, steam_id: int) -> CfgPermissionPeer:
        for peer in self.permissions:
            if peer.steam_id == steam_id:
                return peer
        raise KeyError(steam_id)

    def add_peer(self, steam_id: int) -> CfgPermissionPeer:
        if steam_id in self.get_peers():
            raise PermissionError(steam_id)
        p = CfgPermissionPeer()
        p.steam_id = steam_id
        self.permissions.append(p)
        return p

    def remove_peer(self, steam_id: int) -> None:
        keep = []
        for p in self.permissions:
            if p.steam_id != steam_id:
                keep.append(p)
        self.permissions.clear()
        self.permissions.extend(keep)

    def to_xml(self) -> bytes:
        root = ElementTree.Element("data")
        for name, value in self.data.items():
            root.set(name, str(value))

        permissions = ElementTree.SubElement(root, "permissions")
        for peer in self.permissions:
            pe = peer.to_xml()
            permissions.append(pe)

        mods = ElementTree.SubElement(root, "active_mod_folders")
        for mod in self.mods:
            me = mod.to_xml()
            mods.append(me)

        out = BytesIO()
        tree = ElementTree.ElementTree(root)
        tree.write(out, xml_declaration=True, encoding="utf-8")
        return out.getvalue()

    def from_xml(self, xmlstr: bytes):
        bb = BytesIO(xmlstr)
        tree = ElementTree.parse(bb)
        root = tree.getroot()
        for name in root.attrib:
            value = root.get(name)
            setattr(self, name, value)

        permissions = root.find("permissions")
        for peer in permissions:
            p = CfgPermissionPeer()
            for name in peer.attrib:
                setattr(p, name, peer.get(name))
            self.permissions.append(p)

        mods = root.find("active_mod_folders")
        for mod in mods:
            m = CfgModValue()
            for name in mod.attrib:
                setattr(m, name, mod.get(name))
            self.mods.append(m)
