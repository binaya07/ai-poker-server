"""No-limit Hold'em regressions and rules invariants."""
from copy import deepcopy
import random

import pytest

from app.engine import Card, PokerEngine, Suit
from tests.test_engine import game_with_players


@pytest.mark.parametrize("kwargs", [{"big_blind": True}, {"small_blind": 1.5}, {"starting_stack": "100"}, {"big_blind": 0}, {"small_blind": 30}])
def test_invalid_table_chip_configuration(kwargs):
    with pytest.raises(ValueError):
        PokerEngine(**kwargs)


def test_heads_up_transition_does_not_repeat_big_blind():
    game = game_with_players(3)
    game.start_hand()
    act(game, "fold")
    act(game, "fold")
    game.players["p1"].stack = 0
    game.start_hand()
    assert game.dealer == "p3"
    assert game.last_big_blind == "p2"
    assert game.current_turn == "p3"


def act(game, action="call", amount=0):
    result = game.place_action(game.current_turn, action, amount)
    assert result["ok"], result


@pytest.mark.parametrize("count", [2, 3, 9, 20])
def test_complete_streets_deal_and_burn_exact_cards(count):
    game = game_with_players(count)
    deck = [Card(rank, suit) for suit in Suit for rank in range(2, 15)]
    game._build_deck = lambda: deck.copy()
    game.start_hand()
    seats = game.player_order[1:] + game.player_order[:1]
    for index, pid in enumerate(seats):
        assert game.players[pid].hole_cards == [deck[-1-index], deck[-1-count-index]]
    remaining = deck[:-2*count]
    board = []
    for phase, cards_to_deal in [("PREFLOP", 0), ("FLOP", 3), ("TURN", 1), ("RIVER", 1)]:
        if cards_to_deal:
            remaining.pop()
            board.extend(remaining.pop() for _ in range(cards_to_deal))
        assert game.phase == phase
        assert game.community_cards == board
        assert game.deck == remaining
        if phase != "PREFLOP":
            assert game.current_turn == "p2"
            assert game.current_bet == 0
            assert game.minimum_raise == 20
            assert all(p.bet == 0 for p in game.players.values())
        for _ in range(count):
            act(game)
    assert game.phase == "SHOWDOWN"
    game.finalize_showdown()
    assert sum(p.stack for p in game.players.values()) == count * 1000
    before = game.snapshot()
    game.finalize_showdown()
    assert game.snapshot() == before


@pytest.mark.parametrize("action,amount", [(None, 0), ([], 0), ({}, 0), ("all-in", 0), ("raise", True), ("raise", 40.5), ("raise", "40"), ("raise", -1), ("raise", 39), ("raise", 1001), ("check", 0), ("bet", 40), ("call", 10), ("fold", 1)])
def test_invalid_actions_do_not_mutate_any_state(action, amount):
    game = game_with_players()
    game.start_hand()
    before = deepcopy(game.__dict__)
    assert not game.place_action(game.current_turn, action, amount)["ok"]
    assert game.__dict__ == before


def test_turn_and_phase_guards():
    game = game_with_players()
    assert not game.place_action("p1", "call")["ok"]
    game.start_hand()
    assert not game.place_action("p2", "call")["ok"]
    assert not game.place_action("unknown", "call")["ok"]
    while game.phase != "SHOWDOWN":
        act(game)
    assert not game.place_action("p1", "call")["ok"]


def test_last_full_raise_sets_minimum_and_full_raise_reopens():
    game = game_with_players(3)
    game.start_hand()
    act(game, "raise", 60)
    assert game.minimum_raise == 40
    assert not game.place_action("p2", "raise", 80)["ok"]
    act(game, "raise", 100)
    act(game)
    act(game, "raise", 140)
    assert game.current_bet == 140


def test_cumulative_short_all_ins_reopen_per_player():
    game = game_with_players(5)
    game.players["p5"].stack = 30
    game.players["p2"].stack = 40
    game.start_hand()
    act(game)  # p4 calls 20
    act(game, "raise", 30)  # p5 short all-in
    act(game)  # p1 calls 30
    act(game, "raise", 40)  # p2 short all-in
    act(game)  # p3 calls 40
    assert game.current_turn == "p4"
    act(game)  # p4 could raise (faces 20), but calls
    assert game.current_turn == "p1"
    assert not game.place_action("p1", "raise", 60)["ok"]  # only faces 10

    game = game_with_players(4)
    game.players["p1"].stack = 30
    game.players["p2"].stack = 40
    game.start_hand()
    act(game)  # p4 calls 20
    act(game, "raise", 30)
    act(game, "raise", 40)
    act(game)
    assert game.current_turn == "p4"
    act(game, "raise", 60)
    assert game.minimum_raise == 20


def test_checker_can_raise_short_opening_all_in():
    game = game_with_players(3)
    game.players["p3"].stack = 25
    game.start_hand()
    for _ in range(3):
        act(game)
    act(game, "check")  # p2
    act(game, "bet", 5)  # p3 all-in
    act(game)  # p1
    act(game, "raise", 25)  # p2's check did not close raising


def test_all_in_call_runs_board_and_returns_uncalled_excess():
    game = game_with_players(stack=100)
    game.players["p2"].stack = 50
    game.start_hand()
    act(game, "raise", 100)
    act(game)
    assert game.phase == "SHOWDOWN"
    assert len(game.community_cards) == 5
    assert game.players["p1"].stack == 50
    assert game.pot == 100
    assert sum(game.pending_payout.values()) == 100
    game.finalize_showdown()
    assert sum(p.stack for p in game.players.values()) == 150


def test_no_betting_against_only_all_in_opponents():
    game = game_with_players(stack=100)
    game.players["p1"].stack = 40
    game.start_hand()
    act(game, "raise", 40)
    assert not game.place_action("p2", "raise", 100)["ok"]
    act(game)
    assert game.phase == "SHOWDOWN"


@pytest.mark.parametrize("short_stack", [4, 10, 20])
def test_heads_up_short_blind_automatically_runs_out_when_nothing_to_call(short_stack):
    game = game_with_players()
    game.players["p1"].stack = short_stack
    game.start_hand()
    if game.phase == "PREFLOP":
        act(game)
    assert game.phase == "SHOWDOWN"
    assert game.pot == short_stack * 2


def test_disconnect_preserves_all_in_hand_and_decided_showdown():
    game = game_with_players(3, stack=100)
    game.start_hand()
    act(game, "raise", 100)
    game.remove_player("p1")
    assert not game.players["p1"].folded
    act(game)
    act(game)
    payout = game.pending_payout.copy()
    game.remove_player("p2")
    assert not game.players["p2"].folded
    assert game.pending_payout == payout
    game.finalize_showdown()
    assert sum(p.stack for p in game.players.values()) == 300


def cards(text):
    suits = dict(zip("hdcs", Suit))
    ranks = {r: i for i, r in enumerate("23456789TJQKA", 2)}
    return [Card(ranks[token[0]], suits[token[1]]) for token in text.split()]


@pytest.mark.parametrize("hand,score", [
    ("As Kd 9h 7c 3s 2d 4c", (0, [14, 13, 9, 7, 4])),
    ("As Ad Kh Qc 9s 2d 4c", (1, [14, 13, 12, 9])),
    ("As Ad Kh Kc Qs Qd 4c", (2, [14, 13, 12])),
    ("As Ad Ah Kc Qs 2d 4c", (3, [14, 13, 12])),
    ("As 2d 3h 4c 5s 6d 6c", (4, [6])),
    ("Ah Kh 9h 7h 3h 2h 4c", (5, [14, 13, 9, 7, 3])),
    ("As Ad Ah Kc Ks Qd Qc", (6, [14, 13])),
    ("As Ad Ah Ac Ks Qd Qc", (7, [14, 13])),
    ("Ah 2h 3h 4h 5h Kd Qc", (8, [5])),
])
def test_every_hand_category_and_kickers(hand, score):
    assert PokerEngine.evaluate_best_hand(cards(hand)) == score


def test_board_plays_ties_and_odd_chip_left_of_button_with_folded_money():
    game = game_with_players(3)
    game.dealer_index = 0
    game.community_cards = cards("Ah Kh Qh Jh Th")
    for pid, hand in zip(game.player_order, ["2c 3c", "4c 5c", "6c 7c"]):
        p = game.players[pid]
        p.hole_cards = cards(hand)
        p.hand_contribution = 5
        p.stack -= 5
    game.players["p3"].folded = True
    game.pot = 15
    game._resolve_showdown()
    assert game.pending_payout == {"p1": 7, "p2": 8}
    game.finalize_showdown()
    assert sum(p.stack for p in game.players.values()) == 3000


def test_seeded_legal_hands_conserve_chips_and_terminate():
    rng = random.Random(42)
    for _ in range(100):
        game = game_with_players(rng.randint(2, 9))
        for p in game.players.values():
            p.stack = rng.randint(1, 200)
        total = sum(p.stack for p in game.players.values())
        game.start_hand()
        for _ in range(200):
            assert sum(p.stack for p in game.players.values()) + game.pot == total
            assert all(p.stack >= 0 and p.bet >= 0 for p in game.players.values())
            if game.phase in ("WAITING", "SHOWDOWN"):
                break
            pid = game.current_turn
            p = game.players[pid]
            choice = rng.choice(["fold", "call", "raise"])
            result = game.place_action(pid, choice, p.bet + p.stack if choice == "raise" else 0)
            if not result["ok"]:
                act(game)
        else:
            pytest.fail("Hand did not terminate")
        game.finalize_showdown()
        assert game.pot == 0
        assert sum(p.stack for p in game.players.values()) == total
