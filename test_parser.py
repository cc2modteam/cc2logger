import pytest
from pathlib import Path
from cc2logger import parser

TOP = Path(__file__).parent.absolute()


def test_parse_newlines():
    logfile = TOP / "logs" / "real-game-2025-10-31.jsonl"

    p = parser.CC2GameParser()
    p.open(logfile)
    messages = []

    while True:
        msg = p.read_one()
        if not msg:
            break
        messages.append(msg)

    assert messages[5].message == "test with a  newline inside"

    assert p.island_captures == 4
    assert len(p.players) == 3
    assert "Bredroll" in p.player_names.values()

    assert len(messages) == 146


def test_follower():
    logdir = TOP / "logs"
    messages = []
    p = parser.CC2GameFollower()
    p.open_latest(logdir)
    while True:
        msg = p.read_one()
        if not msg:
            break
        messages.append(msg)
    assert True

    assert len(p.players) == 2
