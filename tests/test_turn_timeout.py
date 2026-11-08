import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import server
from app.engine import PokerEngine
from tests.test_server import clean_table, _seat_two_bots_and_deal


async def wait_for(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.002)
    await asyncio.wait_for(poll(), 2)


@pytest.mark.parametrize("invalid", [None, {"type": "action", "action": "check"}, {"type": "action", "action": "raise", "amount": True}])
def test_silent_or_invalid_client_times_out_to_fold(invalid):
    server.TURN_TIMEOUT_SECONDS = 0.15
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as instructor, client.websocket_connect("/ws") as one, client.websocket_connect("/ws") as two:
            state = _seat_two_bots_and_deal(instructor, one, two)
            actor = state["current_turn"]
            if invalid is not None:
                {"bot-1": one, "bot-2": two}[actor].send_json(invalid)
            # Timeout broadcasts the fallback even if the client stays silent.
            while state["phase"] != "WAITING":
                state = instructor.receive_json()["payload"]
            assert state["last_action"]["timeout"] == {"player": actor, "action": "fold"}
            assert next(p for p in state["players"] if p["id"] == actor)["folded"]
            assert sum(p["stack"] for p in state["players"]) == 2000


def test_checks_when_allowed_and_advances_to_next_street():
    server.TURN_TIMEOUT_SECONDS = 0.1
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as instructor, client.websocket_connect("/ws") as one, client.websocket_connect("/ws") as two:
            _seat_two_bots_and_deal(instructor, one, two)
            one.send_json({"type": "action", "action": "call"})
            state = instructor.receive_json()["payload"]
            assert state["current_turn"] == "bot-2"
            state = instructor.receive_json()["payload"]
            assert state["phase"] == "FLOP"
            assert state["last_action"]["timeout"] == {"player": "bot-2", "action": "check"}
            assert state["pot"] == 40
            assert not any(p["folded"] for p in state["players"])


def table():
    server.engine = PokerEngine()
    for i in range(3):
        server.engine.add_player(str(i), str(i))
    server.engine.start_hand()


def test_repeated_invalid_actions_and_broadcasts_do_not_extend_timer():
    async def scenario():
        table()
        server.TURN_TIMEOUT_SECONDS = 0.08
        await server.broadcast_state()
        original = server._turn_timeout_task
        actor = server.engine.current_turn
        for _ in range(5):
            assert not server.engine.place_action(actor, "check")["ok"]
            await server.broadcast_state()
            assert server._turn_timeout_task is original
            await asyncio.sleep(0.005)
        await wait_for(lambda: server.engine.players[actor].folded)
        server._cancel_turn_timeout()
    asyncio.run(scenario())


def test_pause_preserves_turn_and_resume_allows_timeout():
    async def scenario():
        table()
        server.TURN_TIMEOUT_SECONDS = 0.05
        server.paused = True
        before = deepcopy(server.engine.__dict__)
        await server.broadcast_state()
        await asyncio.sleep(0.15)
        assert server.engine.__dict__ == before
        server.paused = False
        await asyncio.sleep(0.01)
        assert server.engine.__dict__ == before
        await wait_for(lambda: server.engine.players["0"].folded)
        server._cancel_turn_timeout()
    asyncio.run(scenario())


def test_stale_timer_cannot_act_on_new_turn_or_hand():
    async def scenario():
        table()
        server.TURN_TIMEOUT_SECONDS = 0.05
        await server.broadcast_state()
        old = server._turn_timeout_task
        assert server.engine.place_action("0", "call")["ok"]
        before = deepcopy(server.engine.__dict__)
        await old
        assert server.engine.__dict__ == before
        await server.broadcast_state()
        old = server._turn_timeout_task
        server.engine.place_action("1", "fold")
        server.engine.place_action("2", "fold")
        server.engine.start_hand()
        before = deepcopy(server.engine.__dict__)
        await old
        assert server.engine.__dict__ == before
        server._cancel_turn_timeout()
    asyncio.run(scenario())


def test_accepted_action_cancels_timer_and_delay_does_not_charge_next_player():
    server.TURN_TIMEOUT_SECONDS = 0.1
    server.ACTION_DELAY_SECONDS = 0.25
    with TestClient(server.app) as client:
        with client.websocket_connect("/ws") as instructor, client.websocket_connect("/ws") as one, client.websocket_connect("/ws") as two:
            _seat_two_bots_and_deal(instructor, one, two)
            one.send_json({"type": "action", "action": "call"})
            state = instructor.receive_json()["payload"]
            assert state["phase"] == "PREFLOP"
            assert state["current_turn"] == "bot-2"
            assert "timeout" not in state["last_action"]
            two.send_json({"type": "action", "action": "check"})
            state = instructor.receive_json()["payload"]
            assert state["phase"] == "FLOP"
            assert "timeout" not in state["last_action"]


def test_shutdown_cancels_pending_turn_timer():
    with TestClient(server.app) as client:
        table()
        client.portal.call(server.broadcast_state)
        task = server._turn_timeout_task
    assert task.done()


def test_broadcast_during_action_delay_cannot_start_next_deadline():
    async def scenario():
        table()
        server.TURN_TIMEOUT_SECONDS = 0.03
        server.ACTION_DELAY_SECONDS = 0.12
        server.engine.place_action("0", "call")
        before = deepcopy(server.engine.__dict__)
        publishing = asyncio.create_task(server._publish_accepted_action())
        await asyncio.sleep(0)
        await server.broadcast_state()
        assert server._turn_timeout_task is None
        await asyncio.sleep(0.06)
        assert server.engine.__dict__ == before
        await publishing
        assert server._turn_timeout_task is not None
        server._cancel_turn_timeout()
    asyncio.run(scenario())


def test_successive_timeouts_check_through_showdown_without_client_actions():
    async def scenario():
        table()
        for _ in range(3):
            assert server.engine.place_action(server.engine.current_turn, "call")["ok"]
        assert server.engine.phase == "FLOP"
        server.TURN_TIMEOUT_SECONDS = 0.01
        await server.broadcast_state()
        await wait_for(lambda: server.engine.phase == "WAITING")
        assert len(server.engine.community_cards) == 5
        assert sum(p.stack for p in server.engine.players.values()) == 3000
        assert not any(p.folded for p in server.engine.players.values())
        assert server._turn_timeout_task is None
    asyncio.run(scenario())
