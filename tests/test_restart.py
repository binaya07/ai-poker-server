import asyncio

import pytest
from fastapi.testclient import TestClient

from app import server
from tests.test_server import clean_table, _seat_two_bots_and_deal


def test_observer_restarts_match_without_reconnecting_bots():
    server.engine.max_hands = 1
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as observer, client.websocket_connect("/ws") as one, client.websocket_connect("/ws") as two:
            state = _seat_two_bots_and_deal(observer, one, two)
            sockets = {"bot-1": one, "bot-2": two}
            sockets[state["current_turn"]].send_json({"type": "action", "action": "fold"})
            assert observer.receive_json()["payload"]["match_complete"]
            observer.send_json({"type": "restart_match"})
            reset = observer.receive_json()["payload"]
            assert "match_number" not in reset
            assert reset["hand_number"] == reset["hands_completed"] == 0
            assert reset["running"] and not reset["paused"] and not reset["match_complete"]
            assert reset["community_cards"] == [] and reset["last_action"] is None
            assert reset["dealer"] is reset["small_blind_player"] is reset["big_blind_player"] is None
            assert all(p["stack"] == 1000 and p["profit_loss"] == 0 and p["hands_played"] == 0 for p in reset["players"])
            assert all(p["connected"] and not p["hole_cards"] for p in reset["players"])
            state = observer.receive_json()["payload"]
            assert state["phase"] == "PREFLOP" and state["hand_number"] == 1
            assert "match_number" not in state and state["community_cards"] == []
            sockets[state["current_turn"]].send_json({"type": "action", "action": "call"})
            assert observer.receive_json()["payload"]["current_turn"] == "bot-2"


@pytest.mark.parametrize("joined", [False, True])
def test_restart_is_observer_only(joined):
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as socket:
            if joined:
                socket.send_json({"type": "join", "player_id": "a", "name": "A"})
                socket.receive_json()
            socket.send_json({"type": "restart_match"})
            assert "Only an instructor" in socket.receive_json()["message"]
            assert server.engine.match_number == 1


def test_restart_rejected_during_live_hand():
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as observer, client.websocket_connect("/ws") as one, client.websocket_connect("/ws") as two:
            state = _seat_two_bots_and_deal(observer, one, two)
            observer.send_json({"type": "restart_match"})
            assert "must finish" in observer.receive_json()["message"]
            assert server.engine.current_turn == state["current_turn"]
            assert server.engine.match_number == 1


def test_restart_cancels_old_tasks_and_ignores_old_paced_action():
    async def scenario():
        old = server.engine
        old.max_hands = 1
        old.add_player("a", "A")
        old.add_player("b", "B")
        old.start_hand()
        old.place_action("a", "fold")
        old.remove_player("b")
        server.ACTION_DELAY_SECONDS = 0.03
        publish = asyncio.create_task(server._publish_accepted_action())
        await asyncio.sleep(0)
        timers = [asyncio.create_task(asyncio.sleep(60)) for _ in range(3)]
        server._turn_timeout_task, server._showdown_reveal_task, server._next_hand_task = timers
        await server._restart_match()
        await publish
        assert all(task.cancelled() for task in timers)
        assert server._pending_action_broadcasts == 0
        assert server.engine is not old
        assert server.engine.players["b"].connected is False
        assert server.engine.match_number == 2 and server.engine.hand_number == 0
        assert server.engine.max_hands == 1
        assert server.ACTION_DELAY_SECONDS == 0.03
        assert not server.engine.can_start_hand()
    asyncio.run(scenario())
