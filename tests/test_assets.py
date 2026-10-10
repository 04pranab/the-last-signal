import json

from game.config import MAP_ASSET_DIR
from game.maps import generate_map


def test_no_missing_assets():
    man = json.loads((MAP_ASSET_DIR / "research_station" / "manifest.json").read_text())
    names = set(man["sprites"])
    for rel in list(man["floors"].values()) + [v["file"] for v in man["sprites"].values()]:
        assert (MAP_ASSET_DIR / "research_station" / rel).exists(), rel
    for seed in range(1, 40):
        m = generate_map(seed)
        for p in m.props:
            assert p.sprite in names, p.sprite
        for o in m.objects:
            fam = o.family
            if o.kind in ("generator", "core", "transmitter"):
                assert fam + "_on" in names and fam + "_off" in names
            else:
                base = fam if fam in ("console_security", "archive", "medical") else "terminal"
                assert base + "_idle" in names and base + "_read" in names
        for r in m.rooms:
            assert r.floor in man["floors"] or r.floor.startswith("teal"), r.floor


def test_game_assets_load_in_pygame():
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
    from game.audio import Audio
    from game.rendering.sprites import SpriteLibrary
    lib = SpriteLibrary()
    assert len(lib.char_raw) >= 30 and lib.char("player", "walk1") and lib.gun(0.5) and lib.light_mask and lib.ui["panel_rectangle_screws"]
    lib.font(20)
    Audio()
