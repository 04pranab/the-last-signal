# The Last Signal

> **Version 2.0.0 · The Dead Zone Update**  
> A top-down co-op survival game about exploration, unreliable signals, and surviving together.

**The Last Signal** is a Python 3 and Pygame game for solo play or LAN multiplayer. Explore an abandoned research station, descend into an underground mining complex, or venture into the open-world Dead Zone. Recover signal fragments, restore power, manage supplies, and face the Echo before the transmission window closes.

## Highlights

- **Three playable maps:** Research Station A-17, the Underground Mining Complex, and the open-world Dead Zone.
- **LAN co-op:** host a game, discover sessions on the local network, request to join, and approve players from the lobby.
- **Survival systems:** weapons, ammunition, medkits, generators, locked areas, signal fragments, objectives, and a multi-phase boss.
- **The Dead Zone:** a day/night cycle, roaming zombie packs, discoverable outposts, campfire respawn points, and supply drops that attract enemies.
- **Configurable controls and audio:** rebindable keys, fullscreen mode, master and category volume controls, and independently adjustable horror ambience.
- **Procedural maps:** seeded generation with reachability validation and shortcuts between areas.
- **No account or internet required:** gameplay and LAN sessions run locally.

## Requirements

- Python 3.9 or newer
- Pygame 2.5 or newer
- Optional for development: pytest
- Optional for rebuilding assets: Pillow

The game uses the Python standard library for the remaining functionality.

## Install and run

### Linux

```bash
git clone https://github.com/04pranab/the-last-signal.git
cd the-last-signal

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

### Windows

```powershell
git clone https://github.com/04pranab/the-last-signal.git
cd the-last-signal

py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
py main.py
```

Single Player starts a private local server automatically. Settings are saved per user in the operating system's configuration directory.

## Play together on a LAN

1. Start the game on the host computer and choose **Create Game**.
2. Set the session name and player limit. A numeric seed is optional.
3. Other players on the same local network choose **Find LAN Games**.
4. They select the session and send a join request.
5. The host accepts or rejects requests in the lobby, then starts the game.

The default game connection uses TCP port **47201**. LAN discovery uses UDP port **47200**. Allow the required traffic through the host firewall. If UDP broadcast is blocked by the network, the browser's manual host-and-port connection is available as a fallback.

## Controls

| Key | Action |
|---|---|
| W A S D / arrow keys | Move |
| Mouse | Aim |
| Left mouse button / Space | Fire |
| R | Reload |
| 1–5 / Q / mouse wheel | Change weapon |
| E | Interact |
| T | Chat |
| Tab | Personal notebook |
| M | Map |
| F11 | Toggle fullscreen |
| Esc | Pause / close panels |

Controls can be rebound in **Settings**. Arrow keys remain available for movement, and Esc remains the pause key.

## Maps

### Research Station A-17
Explore labs, the archive, security and server wings, and Central Communications. Restore power, recover signal fragments, calibrate the signal core, defeat the Echo Warden, and transmit the correct signal.

### Underground Mining Complex
Navigate dark tunnels, rail lines, machinery, ore storage, and the blast vault while managing threats and supplies.

### The Dead Zone
Travel between scattered outposts across grassland, roads, and wasteland. Daylight and night change visibility and danger. Light campfires to establish respawn points, discover locations, and contest supply drops before the zombies reach them.

## Weapons and survival

The arsenal includes a pistol, SMG, shotgun, rifle, and rare plasma weapon. Zombies include walkers, fast runners, and brutes. Weapon crates, ammunition, and medkits support longer expeditions. Medical stations and camera consoles provide additional tactical options on supported maps.

## Development and tests

Install the test dependency and run the suite from the repository root:

```bash
python -m pip install pytest
python -m pytest tests -q
```

Useful development commands:

```bash
python server.py --auto-accept
python client.py --connect 127.0.0.1:47201 --name Bot
```

The optional asset builder can regenerate derived artwork from supplied source packs:

```bash
python -m pip install Pillow
python tools/build_assets.py /path/to/extracted/asset [/path/to/second/asset/root]
```

## Project layout

- `game/state.py` — authoritative game state and objectives.
- `game/maps/` — map generators and reachability validation.
- `game/networking/` — TCP game protocol, server/client, and UDP discovery.
- `game/rendering/` — world rendering, lighting, and visual effects.
- `game/ui/` — menus, lobby, HUD, and settings screens.
- `tests/` — automated tests for game rules, maps, networking, collision, assets, and settings.
- `tools/build_assets.py` — asset-generation utility.

## Known limitations

- Player-to-player collision is disabled to reduce corridor blocking in larger sessions.
- The Echo operates as a set of events rather than a roaming enemy; zombies provide roaming combat pressure.
- The character and environment art use a hybrid visual style.
- Windows compatibility is intended, but should be tested on the target Windows setup before treating it as verified.

## Credits and licensing

See [CREDITS.md](CREDITS.md) for asset attribution and [assets/licenses/](assets/licenses/) for the retained third-party license files. The game source code is licensed under the MIT License; third-party art, fonts, and audio remain subject to their own applicable licenses.

## Release notes

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the v2.0.0 change summary.

---

**Issues and contributions:** please use the repository's GitHub Issues and Pull Requests.
