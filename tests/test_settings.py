import os

import pygame
import pytest

import game.config as config
from game.settings import ACTIONS, DEFAULT_KEYS, Settings


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return Settings()


def test_defaults_and_persistence(settings):
    assert settings.keys == DEFAULT_KEYS and not settings.mute and 0 < settings.master < 1
    settings.master = 0.2
    settings.mute = True
    settings.vol["ambient"] = 0.05
    settings.bind("interact", pygame.K_f)
    settings.save()
    s2 = Settings()
    assert s2.master == 0.2 and s2.mute and s2.vol["ambient"] == 0.05 and s2.keys["interact"] == pygame.K_f


def test_rebind_swaps_duplicates(settings):
    settings.bind("reload", pygame.K_e)            # E was "interact"
    assert settings.keys["reload"] == pygame.K_e and settings.keys["interact"] == pygame.K_r
    assert len(set(settings.keys.values())) == len(settings.keys)


def test_reset_and_bad_file(settings):
    settings.bind("up", pygame.K_i)
    settings.reset_keys()
    assert settings.keys == DEFAULT_KEYS
    settings.path.parent.mkdir(parents=True, exist_ok=True)
    settings.path.write_text('{"master": "loud", "keys": {"up": "x", "down": 99999999999}, "vol": 5}')
    s = Settings()
    assert 0 <= s.master <= 1 and s.keys["up"] == DEFAULT_KEYS["up"] and s.keys["down"] == DEFAULT_KEYS["down"]


def test_audio_respects_mute_categories_and_master(settings):
    pygame.init()
    from game.audio import Audio
    a = Audio(settings)
    if not a.enabled:
        pytest.skip("no audio device")
    played = []

    class Fake:
        def __init__(self, n): self.n = n
        def set_volume(self, v): self.v = v
        def play(self): played.append((self.n, self.v))

    a.sounds = {n: Fake(n) for n in ("click", "heartbeat", "shot", "door_open")}
    a.play("click", 1.0, 0.0)
    assert played and played[-1][1] == pytest.approx(settings.master * settings.vol["ui"])
    settings.ambient_on = False
    n = len(played)
    a.play("heartbeat", 1.0, 0.0)
    assert len(played) == n                         # horror ambience off
    settings.mute = True
    a.play("shot", 1.0, 0.0)
    a.play("click", 1.0, 0.0)
    assert len(played) == n                         # fully muted
    settings.mute = False
    settings.vol["effects"] = 0.0
    a.play("shot", 1.0, 0.0)
    assert len(played) == n                         # zero volume skipped


def test_settings_screen_rebinds_key_in_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from game.game import App
    from game.ui.settings_screen import SettingsScreen
    app = App()
    scr = SettingsScreen(app, app.scr)
    app.goto(scr)
    scr.draw(app.screen)
    aid, rect = next((a, r) for a, r in scr.rows if a == "reload")
    scr.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=rect.center, button=1))
    assert scr.waiting == "reload"
    scr.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, unicode="g", mod=0))
    assert app.settings.keys["reload"] == pygame.K_g and scr.waiting is None
    mute = scr.mute_btn
    scr.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=mute.rect.center, button=1))
    assert app.settings.mute is True
    scr.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0))
    assert app.scr is not scr
    app.shutdown()
