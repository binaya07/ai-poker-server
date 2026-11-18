import pytest

from tests.test_engine import game_with_players
from tests.test_rules import cards


def test_each_hand_resets_stacks_and_carries_only_net_profit():
    game = game_with_players()
    game.start_hand()
    game.place_action("p1", "fold")
    assert [p.stack for p in game.players.values()] == [990, 1010]
    assert [p.profit_loss for p in game.players.values()] == [-10, 10]
    assert [p.hands_played for p in game.players.values()] == [1, 1]
    state = game.start_hand()
    assert all(p.stack + p.bet == 1000 for p in game.players.values())
    assert [p["profit_loss"] for p in state["players"]] == [-10, 10]
    assert state["starting_stack"] == 1000
    game.place_action("p2", "fold")
    assert [p.profit_loss for p in game.players.values()] == [0, 0]
    assert game.hands_completed == 2
    assert all(p.hands_played == 2 for p in game.players.values())


def test_all_in_loss_does_not_eliminate_player_and_scores_only_after_payout():
    game = game_with_players()
    game.start_hand()
    game.players["p1"].hole_cards = cards("As Ad")
    game.players["p2"].hole_cards = cards("Ks Kd")
    game.deck = list(reversed(cards("2h 2c 3d 7h 4h 9s 5h Jc")))
    assert game.place_action("p1", "raise", 1000)["ok"]
    assert game.place_action("p2", "call")["ok"]
    assert game.phase == "SHOWDOWN"
    assert game.hands_completed == 0
    assert all(p.profit_loss == 0 and p.hands_played == 0 for p in game.players.values())
    game.finalize_showdown()
    assert [p.stack for p in game.players.values()] == [2000, 0]
    assert [p.profit_loss for p in game.players.values()] == [1000, -1000]
    before = game.snapshot()
    game.finalize_showdown()
    assert game.snapshot() == before
    assert game.can_start_hand()
    game.start_hand()
    assert all(p.stack + p.bet == 1000 and p.hole_cards and not p.folded for p in game.players.values())
    assert [p.profit_loss for p in game.players.values()] == [1000, -1000]


def test_disconnect_and_late_join_do_not_erase_or_invent_results():
    game = game_with_players(3)
    game.start_hand()
    game.place_action("p1", "call")
    game.remove_player("p2")  # Loses the posted small blind.
    game.add_player("late", "Late arrival")
    game.place_action("p3", "fold")
    assert game.phase == "WAITING"
    assert game.players["p2"].profit_loss == -10
    assert game.players["p2"].hands_played == 1
    assert game.players["late"].hands_played == 0
    assert game.players["late"].profit_loss == 0
    assert sum(p.profit_loss for p in game.players.values()) == 0
    game.add_player("p2", "Back again")
    assert game.players["p2"].profit_loss == -10
    assert game.players["p2"].stack == 990
    game.start_hand()
    assert game.players["p2"].stack + game.players["p2"].bet == 1000
    assert game.players["p2"].profit_loss == -10


def test_offline_players_do_not_get_charged_for_skipped_hands():
    game = game_with_players(3)
    game.remove_player("p3")
    game.start_hand()
    game.place_action(game.current_turn, "fold")
    assert game.players["p3"].profit_loss == game.players["p3"].hands_played == 0
    assert not game.players["p3"].hole_cards


def test_hand_limit_stops_only_after_final_payout_and_cannot_be_bypassed():
    game = game_with_players()
    game.max_hands = 2
    game.start_hand()
    game.place_action(game.current_turn, "fold")
    assert not game.match_complete
    game.start_hand()
    while game.phase != "SHOWDOWN":
        assert game.place_action(game.current_turn, "call")["ok"]
    assert game.hands_completed == 1
    assert not game.match_complete
    assert not game.can_start_hand()
    game.finalize_showdown()
    state = game.snapshot()
    assert state["match_complete"]
    assert state["hands_completed"] == state["max_hands"] == 2
    assert not game.can_start_hand()
    game.add_player("late", "Late arrival")
    with pytest.raises(ValueError, match="Hand limit"):
        game.start_hand()
    assert sum(p.profit_loss for p in game.players.values()) == 0


@pytest.mark.parametrize("value", [0, -1, True, 2.5, "10"])
def test_engine_rejects_invalid_hand_limit(value):
    from app.engine import PokerEngine
    with pytest.raises(ValueError, match="max_hands"):
        PokerEngine(max_hands=value)


def test_new_hand_clears_previous_board_and_action():
    game = game_with_players()
    game.start_hand()
    while game.phase != "SHOWDOWN":
        game.place_action(game.current_turn, "call")
    assert len(game.community_cards) == 5
    game.finalize_showdown()
    state = game.start_hand()
    assert state["phase"] == "PREFLOP"
    assert state["community_cards"] == []
    assert state["last_action"]["type"] == "deal"
    assert state["current_turn"] in [p["id"] for p in state["players"]]
