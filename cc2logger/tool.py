"""CC2 basic game log parser"""
from argparse import ArgumentParser
from pathlib import Path
from .parser import CC2GameParser


parser = ArgumentParser(description=__doc__, prog="cc2logger")
parser.add_argument("FILE", type=Path, help="CC2 game jsonl file to load")


def main():
    opts = parser.parse_args()

    gp = CC2GameParser()
    gp.read(opts.FILE)

    # print some basic stuff
    print(f"Game started     : {gp.first_message.timestamp}")
    print(f"Duration         : {int(gp.duration.total_seconds() / 60)} mins")
    print("Players           :")
    for name in sorted(gp.player_names.values()):
        print(f" {name}")
    print("Teams             :")
    for team_id in sorted(gp.teams.keys()):
        print(f" Team {team_id}:")
        for player in gp.teams[team_id].values():
            print(f"  {player}: {int(player.teams[team_id].total_seconds() / 60)} mins")

    print(f"Islands captured : {gp.island_captures}")
    print(f"Units destroyed : {sum(gp.destroyed_stats.values())}")
    for name in sorted(gp.destroyed_stats.keys()):
        count = gp.destroyed_stats[name]
        if count:
            print(f" {name}: {count}")
