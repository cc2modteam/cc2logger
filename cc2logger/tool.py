"""CC2 basic game log parser"""
from argparse import ArgumentParser
from pathlib import Path
from .parser import CC2GameParser, generate_lua_stats_page


parser = ArgumentParser(description=__doc__, prog="cc2logger")
parser.add_argument("PATH", type=Path, help="CC2 game jsonl file or folder full of jsonl logs to load")
parser.add_argument("--stats", action="store_true", help="Generate player/server stats for lua")


def main():
    opts = parser.parse_args()

    gp = CC2GameParser()

    files = []
    if opts.PATH.is_file():
        files.append(opts.PATH)
    elif opts.PATH.is_dir():
        files = sorted(list(opts.PATH.glob("game_log_*.jsonl")))

    for item in files:
        print(f"read {item}")
        gp.read(item)

    if opts.stats:
        with open("test.lua", "w") as fd:
            print(generate_lua_stats_page(gp), file=fd)
        return

    # print some basic stuff
    if len(files) == 1:
        print(f"Game started      : {gp.first_message.timestamp}")
    else:
        print(f"Logs started      : {gp.first_message.timestamp}")

    print(f"Duration          : {int(gp.duration.total_seconds() / 60):-5} mins")
    print("Players           :")
    for steamid, player in sorted(gp.players.items(), reverse=True, key=lambda x: x[1].total_playtime):
        print(f" {int(player.total_playtime / 60):4} mins  {player.player_name}")

    if len(files) == 1:
        print("Teams             :")
        for team_id in sorted(gp.teams.keys()):
            print(f" Team {team_id}:")
            for player in gp.teams[team_id].values():
                if team_id in player.teams:
                    print(f"  {player}: {int(player.teams[team_id].total_seconds() / 60)} mins")

    print(f"Islands captured : {gp.island_captures:-4}")
    print(f"Units destroyed  : {sum(gp.destroyed_stats.values()):-4}")
    for name in sorted(gp.destroyed_stats.keys()):
        count = gp.destroyed_stats[name]
        if count:
            print(f" {name:16}: {count:-4}")
