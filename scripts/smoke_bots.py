"""Run a complete, low-risk Bayou Poker hand against a websocket server.

This is a smoke test, not a poker strategy example. Three bots join, the first
starts a hand, and every bot calls a bet or checks when it is their turn.
The script exits 0 only after the server pays out the hand.
"""

import asyncio
import json
import os

import websockets

WS_URL = os.environ.get("POKER_WS_URL", "ws://localhost:8000/ws")
BOT_IDS = ("smoke-gator", "smoke-crawfish", "smoke-heron")


async def bot(player_id: str, joined: asyncio.Event, start_hand: asyncio.Event, hand_complete: asyncio.Event) -> None:
    async with websockets.connect(WS_URL) as socket:
        await socket.send(json.dumps({"type": "join", "player_id": player_id, "name": player_id.replace("smoke-", "Smoke ").title()}))
        joined.set()
        started = False
        while not hand_complete.is_set():
            message = json.loads(await socket.recv())
            if message["type"] == "error":
                raise RuntimeError(f"{player_id}: {message['message']}")
            if message["type"] != "state":
                continue
            state = message["payload"]
            if player_id == BOT_IDS[0] and start_hand.is_set() and not started:
                await socket.send(json.dumps({"type": "start_hand"}))
                started = True
                continue
            if state.get("phase") == "WAITING" and state.get("hand_number") == 1 and state.get("last_action", {}).get("type") == "payout":
                hand_complete.set()
                return
            if state.get("current_turn") != player_id:
                continue
            me = next(player for player in state["players"] if player["id"] == player_id)
            highest_bet = max(player["bet"] for player in state["players"])
            action = "call" if me["bet"] < highest_bet else "check"
            await socket.send(json.dumps({"type": "action", "action": action}))


async def main() -> None:
    joined_events = [asyncio.Event() for _ in BOT_IDS]
    start_hand, hand_complete = asyncio.Event(), asyncio.Event()
    tasks = [asyncio.create_task(bot(pid, joined, start_hand, hand_complete)) for pid, joined in zip(BOT_IDS, joined_events)]
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in joined_events)), timeout=10)
        # Let the server process all three join messages before asking it to deal.
        await asyncio.sleep(0.25)
        start_hand.set()
        await asyncio.wait_for(hand_complete.wait(), timeout=30)
        print("Smoke test passed: server completed and paid out one three-bot hand.")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
