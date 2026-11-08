import importlib.util
from pathlib import Path

import pytest

from app import config


def write_config(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_repository_defaults_from_another_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert config.load_config() == config.Settings(15.0, 1000, 10, 20)


def test_server_uses_custom_settings(tmp_path, monkeypatch):
    path = write_config(tmp_path, "turn_timeout_seconds = 2.5\nstarting_stack = 2500\nsmall_blind = 25\nbig_blind = 50\n")
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", path)
    # Load an isolated server module so other tests' running table is untouched.
    source = Path(config.__file__).with_name("server.py")
    spec = importlib.util.spec_from_file_location("app.configured_server", source)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    assert server.TURN_TIMEOUT_SECONDS == 2.5
    server.engine.add_player("bot", "Bot")
    assert server.engine.players["bot"].stack == 2500
    server.engine.players["bot"].stack = 1200
    server.engine.add_player("bot", "Reconnected Bot")
    assert server.engine.players["bot"].stack == 1200
    server.engine.add_player("opponent", "Opponent")
    state = server.engine.start_hand()
    assert state["small_blind"] == 25
    assert state["big_blind"] == 50
    assert server.engine.players["bot"].bet == 25
    assert server.engine.players["opponent"].bet == 50
    assert server.engine.pot == 75
    assert server.engine.current_bet == server.engine.minimum_raise == 50


@pytest.mark.parametrize("value", ["0", "-1", "true", '"15"', "nan", "inf", "-inf", "[]"])
def test_rejects_invalid_timeout(tmp_path, value):
    path = write_config(tmp_path, f"turn_timeout_seconds = {value}\nstarting_stack = 1000\nsmall_blind = 10\nbig_blind = 20\n")
    with pytest.raises(ValueError, match="turn_timeout_seconds"):
        config.load_config(path)


@pytest.mark.parametrize("value", ["0", "-1", "true", "1000.5", '"1000"', "[]"])
def test_rejects_invalid_stack(tmp_path, value):
    path = write_config(tmp_path, f"turn_timeout_seconds = 15\nstarting_stack = {value}\nsmall_blind = 10\nbig_blind = 20\n")
    with pytest.raises(ValueError, match="starting_stack"):
        config.load_config(path)


@pytest.mark.parametrize("text", ["", "starting_stack = 1000", "turn_timeout_seconds = 15", "turn_timeout_seconds = 15\nstarting_stack = 1000\ntimeout = 10"])
def test_missing_or_unknown_settings_are_errors(tmp_path, text):
    with pytest.raises(ValueError, match="must contain exactly"):
        config.load_config(write_config(tmp_path, text))


def test_missing_file_and_malformed_toml_are_clear_errors(tmp_path):
    with pytest.raises(ValueError, match="Cannot load configuration"):
        config.load_config(tmp_path / "missing.toml")
    with pytest.raises(ValueError, match="Cannot load configuration"):
        config.load_config(write_config(tmp_path, "starting_stack = ["))


@pytest.mark.parametrize("name", ["small_blind", "big_blind"])
@pytest.mark.parametrize("value", ["0", "-1", "true", "1.5", '"20"', "[]", "nan", "inf"])
def test_rejects_invalid_blind_amounts(tmp_path, name, value):
    values = {"turn_timeout_seconds": "15", "starting_stack": "1000",
              "small_blind": "10", "big_blind": "20"}
    values[name] = value
    path = write_config(tmp_path, "\n".join(f"{key} = {val}" for key, val in values.items()))
    with pytest.raises(ValueError, match=name):
        config.load_config(path)


@pytest.mark.parametrize("small,big", [(30, 20), (20, 20), (10, 25)])
def test_blind_ordering(tmp_path, small, big):
    path = write_config(tmp_path, f"turn_timeout_seconds = 15\nstarting_stack = 1000\nsmall_blind = {small}\nbig_blind = {big}\n")
    if small > big:
        with pytest.raises(ValueError, match="small_blind must be less than or equal"):
            config.load_config(path)
    else:
        assert config.load_config(path).small_blind == small


@pytest.mark.parametrize("missing", ["small_blind", "big_blind"])
def test_blind_settings_are_required(tmp_path, missing):
    values = {"turn_timeout_seconds": 15, "starting_stack": 1000,
              "small_blind": 10, "big_blind": 20}
    del values[missing]
    path = write_config(tmp_path, "\n".join(f"{key} = {val}" for key, val in values.items()))
    with pytest.raises(ValueError, match="must contain exactly"):
        config.load_config(path)
