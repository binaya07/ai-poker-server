# Bayou Poker Server

No-limit Texas Hold'em. The server manages cards, turns,
blinds, legal bets, and payouts. The bot/client submits actions over WebSocket.

## Run the server

**Python 3.11+**, from the project root:

```sh
python -m pip install -r requirements.txt
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```

**Docker Compose**:

```sh
docker compose up --build
# Stop and remove containers:
docker compose down
```

Settings in [`config.toml`](config.toml):

```toml
turn_timeout_seconds = 15
starting_stack = 1000
small_blind = 10
big_blind = 20
```

## Connect and join locally

Connect to `ws://localhost:8000/ws`; If using Docker Compose, use
`ws://poker-server:8000/ws`. Send JSON text messages:

```json
{"type":"join","player_id":"group-1","name":"Group 1 Bot"}
```

Use a unique, non-empty ID and name (names are truncated to 24 characters).
One socket controls one player. A successful join returns `state`.
Joining mid-hand waits until the next deal.

Rejoining with the same ID keeps the seat/stack and closes the old socket with
code `4001`; Disconnecting folds a live non-all-in hand;
all-in hands and decided showdowns remain eligible. Reconnection does not undo
a fold or refill chips. Players with zero chips sit out subsequent hands.

## Game state

State messages have the shape `{"type":"state","payload":{...}}`.
The payload contains:

| Field | Meaning |
|---|---|
| `phase` | `WAITING`, `PREFLOP`, `FLOP`, `TURN`, `RIVER`, `SHOWDOWN` |
| `hand_number` | Hand counter; use it to reset per-hand strategy memory |
| `current_turn` | Player ID to act, or `null`; **only act when this is your ID** |
| `pot` | Committed chips, including this street's bets |
| `current_bet` | Total street bet to match; use this, not the largest player bet |
| `minimum_raise` | Minimum full **increase**, not the total raise target |
| `small_blind`, `big_blind` | Configured blind amounts |
| `dealer` | Dealer/button player ID, initially `null` |
| `small_blind_player`, `big_blind_player` | Blind-player IDs, initially `null`; persist until the next deal, including after folds/payout; UI shows SB/BB |
| `community_cards` | Board cards: 0 preflop, then 3/4/5 |
| `players` | Player objects below, in join order |
| `last_action` | Latest event or `null`; not a complete history |
| `can_start` | Table idle with enough connected players who have chips; also check `paused` before requesting a deal |
| `running`, `paused` | Continuous-play and instructor-pause flags |
| `speed` | `{"action_delay": seconds, "showdown_reveal": seconds}` |

Each player has `id`, `name`, `stack` (uncommitted chips), `bet` (street
contribution, reset each street), `folded`, `all_in`, `connected`, and `hole_cards`.

A visible card is `{"rank":14,"suit":"spades","label":"AS"}`. Ranks are
2-14 (J=11, Q=12, K=13, A=14); suits are `hearts`, `diamonds`, `clubs`, `spades`.
Hidden cards are `{"rank":"?","suit":"?","label":"??"}`; an undealt hand is `[]`.
You see your own cards; opponents' non-folded hands are revealed at showdown.
Use `rank`/`suit` for strategy, not display labels.

`last_action.type` is `deal`, `check`, `call`, `raise`, `fold`, or `payout`.
Actions have `player`; calls/raises include chips added as `amount`, and raises
also include the street-total `target`. Opening `bet` is reported as `raise`.
`deal` includes `dealer`, `small_blind`, `big_blind` **player IDs**.
`payout` has `winners` and `pot`; contested showdowns also have a `payouts`
mapping of player IDs to chips. Repeated snapshots can repeat the same event.

## Submit an action

```json
{"type":"action","action":"raise","amount":60}
```

| Action | Rule |
|---|---|
| `check` | Only when your `bet == current_bet` |
| `call` | Pays `min(current_bet - bet, stack)`; short calls go all-in; zero-cost calls check |
| `fold` | Gives up the hand |
| `bet` | Opens betting only when `current_bet == 0` |
| `raise` | Increases the street bet; also accepted as an opening bet |

For `bet`/`raise`, `amount` is the desired **total for this street**, not extra
chips. With `bet=10`, raising to `60` adds `50` chips.

- Full raise target: at least `current_bet + minimum_raise`.
- Maximum target: your `bet + stack`. Only an all-in can increase by less than
  `minimum_raise`. There is no separate `all-in` action: call short or raise to the maximum.
- Short all-ins reopen raising for a previous bettor/caller only when the
  cumulative increase they face reaches a full raise. A prior check can still
  raise an opening bet. You cannot bet/raise against only all-in opponents.
- Amounts must be non-negative integers, not floats or booleans. For
  `call`/`check`/`fold`, omit `amount` or send `0`; the server calculates payment.

## Replies, errors, and timeout

The submitting bot receives `action_result`:

```json
{"type":"action_result","payload":{"ok":false,"error":"Cannot check while facing a bet"}}
```

On success, `payload` contains `ok:true`, `phase`, `pot`, `current_turn`,
`action`, and private engine `state`.
**Wait for the next `state` message to act**, not the result's embedded state.

Malformed messages or join/start failures return:

```json
{"type":"error","message":"Join the table first"}
```

Rejection changes no chips or turns and keeps the connection open. Correct your
action if it is still your turn; do not repeatedly retry the same invalid move.
Out-of-turn requests are rejected. Illegal actions may trigger an unchanged
state broadcast; malformed messages may return only an error.

Each announced turn has **15 seconds by default** to submit a valid action.
Invalid messages and repeated broadcasts do not reset it. On expiry the server
**checks if allowed, otherwise folds**, then broadcasts the result. The event
includes `last_action.timeout = {"player":"group-1","action":"fold"}`
(or `check`), even when the fold awards the pot. Pausing suspends the countdown;
action pacing does not consume the next turn's response time.

## Working bot example

[`scripts/student_bot.py`](scripts/student_bot.py) is a complete connection example:
it joins, reads state/results/errors, avoids duplicate requests, and checks or calls.
Replace this decision in `run_bot` with your strategy:

```python
me = next(p for p in state["players"] if p["id"] == player_id)
action = "check" if me["bet"] == state["current_bet"] else "call"
await ws.send(json.dumps({"type": "action", "action": action}))
```

With the server running, use two terminals (activate the environment in each):

```sh
python scripts/student_bot.py group-1
python scripts/student_bot.py group-2
```

Then click **Start** in the browser. An optional second argument sets the URL:
`python scripts/student_bot.py group-1 ws://SERVER_HOST:8000/ws`.

For three ready-made demo bots: 

`python scripts/demo_bots.py` or 
`docker compose --profile demo up --build`.


## Server Tests (No need to run these for bot/client side implementation)
```sh
python -m pytest -q
# With a freshly started local server, play one complete test hand:
python scripts/smoke_bots.py
# Equivalent server + test bots in Docker:
docker compose --profile smoke up --build --abort-on-container-exit --exit-code-from poker-smoke
docker compose down
```
