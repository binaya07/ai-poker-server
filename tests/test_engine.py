import pytest

from app.engine import Card, PokerEngine, Suit


def game_with_players(count=2, stack=1_000):
    game = PokerEngine(starting_stack=stack, small_blind=10, big_blind=20)
    for index in range(count):
        game.add_player(f"p{index + 1}", f"Player {index + 1}")
    return game


def test_heads_up_button_posts_small_blind_and_acts_first_preflop():
    game = game_with_players()
    game.start_hand()

    assert game.dealer == "p1"
    assert game.players["p1"].bet == 10
    assert game.players["p2"].bet == 20
    assert game.pot == 30
    assert game.current_turn == "p1"


def test_preflop_call_reaches_flop_only_after_big_blind_checks():
    game = game_with_players()
    game.start_hand()
    assert game.place_action("p1", "call")["ok"]
    assert game.phase == "PREFLOP"
    assert game.current_turn == "p2"
    assert game.place_action("p2", "check")["ok"]
    assert game.phase == "FLOP"
    assert len(game.community_cards) == 3
    assert game.current_turn == "p2"  # First to act after the button heads-up.


def test_raise_amount_is_a_total_street_bet_and_reopens_action():
    game = game_with_players(3)
    game.start_hand()
    assert game.current_turn == "p1"
    assert game.place_action("p1", "raise", 60)["ok"]
    assert game.current_bet == 60
    assert game.current_turn == "p2"
    assert game.place_action("p2", "call")["ok"]
    assert game.current_turn == "p3"
    assert game.place_action("p3", "call")["ok"]
    assert game.phase == "FLOP"
    assert game.pot == 180


def test_short_stack_can_call_all_in_and_side_pot_is_paid_correctly():
    game = game_with_players(3, stack=100)
    game.phase = "RIVER"
    game.community_cards = [
        Card(2, Suit.CLUBS), Card(3, Suit.DIAMONDS), Card(7, Suit.HEARTS),
        Card(9, Suit.SPADES), Card(11, Suit.CLUBS),
    ]
    # p1 wins the 150-chip main pot; p2 wins the 100-chip side pot over p3.
    for pid, cards, contribution in [
        ("p1", [Card(14, Suit.SPADES), Card(14, Suit.HEARTS)], 50),
        ("p2", [Card(13, Suit.SPADES), Card(13, Suit.HEARTS)], 100),
        ("p3", [Card(12, Suit.SPADES), Card(12, Suit.HEARTS)], 100),
    ]:
        player = game.players[pid]
        player.hole_cards = cards
        player.stack = 0
        player.all_in = True
        player.hand_contribution = contribution
    game.pot = 250

    game._resolve_showdown()

    assert game.players["p1"].stack == 150
    assert game.players["p2"].stack == 100
    assert game.players["p3"].stack == 0
    assert game.pot == 0
    assert game.phase == "WAITING"


def test_fold_awards_the_entire_pot_without_dealing_more_cards():
    game = game_with_players()
    game.start_hand()
    result = game.place_action("p1", "fold")

    assert result["ok"]
    assert game.phase == "WAITING"
    assert game.pot == 0
    assert game.players["p2"].stack == 1_010


@pytest.mark.parametrize(
    ("cards", "expected"),
    [
        ([Card(14, Suit.SPADES), Card(13, Suit.SPADES), Card(12, Suit.SPADES), Card(11, Suit.SPADES), Card(10, Suit.SPADES), Card(2, Suit.HEARTS), Card(3, Suit.CLUBS)], (8, [14])),
        # The flush must be selected from five suited cards within a seven-card hand.
        ([Card(14, Suit.HEARTS), Card(11, Suit.HEARTS), Card(9, Suit.HEARTS), Card(6, Suit.HEARTS), Card(2, Suit.HEARTS), Card(13, Suit.CLUBS), Card(12, Suit.SPADES)], (5, [14, 11, 9, 6, 2])),
        # Two triplets make a full house; the higher triplet is used as trips.
        ([Card(14, Suit.HEARTS), Card(14, Suit.CLUBS), Card(14, Suit.SPADES), Card(13, Suit.HEARTS), Card(13, Suit.CLUBS), Card(13, Suit.SPADES), Card(2, Suit.CLUBS)], (6, [14, 13])),
        ([Card(14, Suit.HEARTS), Card(5, Suit.CLUBS), Card(4, Suit.SPADES), Card(3, Suit.HEARTS), Card(2, Suit.CLUBS)], (4, [5])),
    ],
)
def test_best_of_seven_hand_evaluation(cards, expected):
    assert PokerEngine.evaluate_best_hand(cards) == expected


def test_private_snapshots_only_reveal_the_requesting_player_cards():
    game = game_with_players()
    game.start_hand()
    own = next(player for player in game.snapshot("p1")["players"] if player["id"] == "p1")
    opponent = next(player for player in game.snapshot("p1")["players"] if player["id"] == "p2")
    assert own["hole_cards"][0]["label"] != "??"
    assert opponent["hole_cards"][0]["label"] == "??"
