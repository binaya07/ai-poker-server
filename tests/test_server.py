import pytest
from fastapi.testclient import TestClient

from app import server
from app.engine import PokerEngine


@pytest.fixture(autouse=True)
def clean_table():
    server.engine = PokerEngine(starting_stack=1000, small_blind=10, big_blind=20)
    server.connections.clear()
    server.spectators.clear()


def test_websocket_rejects_actions_from_an_unseated_connection():
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "action", "action": "call"})
            assert websocket.receive_json() == {"type": "error", "message": "Join the table first"}


def test_observer_does_not_take_a_poker_seat():
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "observe"})
            state = websocket.receive_json()["payload"]
            assert state["players"] == []
            assert server.engine.players == {}


def test_join_requires_stable_bot_identity():
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "join", "name": "", "player_id": "bot-1"})
            assert websocket.receive_json()["type"] == "error"


def test_start_hand_requires_two_players_with_chips():
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as websocket_one, client.websocket_connect("/ws") as websocket_two:
            websocket_one.send_json({"type": "join", "name": "Bot One", "player_id": "bot-1"})
            assert websocket_one.receive_json()["type"] == "state"
            assert server.engine.can_start_hand() is False

            websocket_two.send_json({"type": "join", "name": "Bot Two", "player_id": "bot-2"})
            assert websocket_two.receive_json()["type"] == "state"
            assert server.engine.can_start_hand() is True
