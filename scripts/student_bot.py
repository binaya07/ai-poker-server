"""Minimal student bot: check when free, otherwise call. No reconnect loop."""
import asyncio
import json
import sys

import websockets


async def run_bot(player_id, url):
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "join", "player_id": player_id, "name": player_id}))
        pending, last_turn = False, None
        async for raw in ws:
            message = json.loads(raw)
            if message["type"] == "error":
                print("Server error:", message["message"], flush=True)
                pending = False
            elif message["type"] == "action_result":
                pending = False
                if not message["payload"]["ok"]:
                    print("Rejected:", message["payload"]["error"], flush=True)
            elif message["type"] == "state":
                state = message["payload"]
                if pending or state["current_turn"] != player_id:
                    continue
                # Repeated broadcasts are not necessarily new turns.
                turn = (state["hand_number"], state["phase"], state["current_bet"],
                        tuple((p["id"], p["bet"], p["folded"], p["all_in"]) for p in state["players"]))
                if turn == last_turn:
                    continue
                me = next(p for p in state["players"] if p["id"] == player_id)
                action = "check" if me["bet"] == state["current_bet"] else "call"
                # Replace the choice above with your strategy.
                await ws.send(json.dumps({"type": "action", "action": action}))
                pending, last_turn = True, turn


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: python scripts/student_bot.py PLAYER_ID [WS_URL]")
    try:
        asyncio.run(run_bot(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else "ws://localhost:8000/ws"))
    except KeyboardInterrupt:
        pass
