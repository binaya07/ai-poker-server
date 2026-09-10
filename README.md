# Bayou Poker

A Texas Hold'em server built for bot-vs-bot tournaments and a live, read-only poker-table visualization.

The repository includes:

- A Python websocket server for game orchestration
- A Texas Hold'em engine with blinds, betting rounds, community cards, and showdown logic
- A browser UI
- Bot-controlled hand starts, reconnect handling, and disconnect folds
- Docker support for local deployment and an end-to-end websocket smoke test
- Unit tests for engine rules plus websocket admission/observer behavior

## Local development

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start the server:
   ```bash
   uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
   ```

4. Open the browser at:
   ```text
   http://localhost:8000/
   ```

## Websocket protocol

The server exposes a websocket endpoint at `/ws`.

### Join message

```json
{
  "type": "join",
  "name": "Bot Group 1",
  "player_id": "group-1"
}
```

### Start hand message

Any seated bot may start a hand once the table has at least two connected players with chips:

```json
{
  "type": "start_hand"
}
```

### Action message

```json
{
  "type": "action",
  "action": "raise",
  "amount": 60
}
```

For `raise`, `amount` is the player's desired **total wager for the current betting round**. It is not an extra amount added to an existing bet. The server validates the minimum raise, available stack, turn, and all other rules. `call`, `check`, and `fold` may omit `amount`.

Allowed actions:
- `check`
- `call`
- `fold`
- `raise`

### Server messages

The server sends state snapshots such as:

```json
{
  "type": "state",
  "payload": {
    "phase": "PREFLOP",
    "pot": 30,
    "current_turn": "group-3",
    "players": [],
    "community_cards": []
  }
}
```

Action results:

```json
{
  "type": "action_result",
  "payload": {
    "ok": true,
    "phase": "FLOP",
    "current_turn": "group-5"
  }
}
```

Errors:

```json
{
  "type": "error",
  "message": "Need at least two connected players to start"
}
```

### Observer message

The bundled web page subscribes with this message. It does not occupy a seat, create chips, reveal bot cards, or send poker actions:

```json
{ "type": "observe" }
```

Each joined bot receives a snapshot that includes only its own hole cards. Observers receive public state with all live hole cards hidden.

## Bot client example

Students can create their own websocket bot client like this:

```python
import asyncio
import json
import websockets

async def main():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({
            "type": "join",
            "name": "Bot Group 1",
            "player_id": "group-1",
        }))

        while True:
            message = json.loads(await websocket.recv())
            msg_type = message.get("type")

            if msg_type == "state":
                state = message["payload"]
                print("State:", state)

                if state.get("current_turn") == "group-1":
                    await websocket.send(json.dumps({
                        "type": "action",
                        "action": "call",
                        "amount": 0
                    }))

            elif msg_type == "action_result":
                print("Action result:", message["payload"])

asyncio.run(main())
```

## Testing

Run the unit and websocket tests locally:

```bash
pytest -q
```

The test suite covers blind/action order, legal betting transitions, folds,
all-ins and side pots, best-five-of-seven hand evaluation, private snapshots,
and observer/websocket admission rules.

For a full containerized check that includes real websocket traffic, run:

```bash
docker compose --profile smoke up --build --abort-on-container-exit --exit-code-from poker-smoke
```

Compose starts the server, waits for `/health`, then `poker-smoke` connects
three simple call/check bots. The command succeeds only after the server deals,
plays, and pays out one complete hand. Stop and remove the containers afterward
with `docker compose down`.

## Docker deployment

Build the image:

```bash
docker build -t ai-poker-server .
```

Run it directly:

```bash
docker run -p 8000:8000 ai-poker-server
```

Run the server and spectator UI with Compose:

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000) for the read-only table,
and use `http://localhost:8000/health` for a machine-readable health check.
