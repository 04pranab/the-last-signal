# THE LAST SIGNAL — Map 1: Research Station A-17

A 2D top-down LAN multiplayer game (Python 3 + Pygame). You are trapped in a huge, procedurally generated, abandoned
research station. **Information is the resource**: explore, read terminals, restore power, calibrate the signal core,
reach the Central Communications room and transmit the distress signal. Beware **THE ECHO**, an anomaly that kills lights,
jams doors, corrupts terminals, jams transmissions and feeds you false data.

Supports 1–15 players. Single player works without any network.

## Run

### Ubuntu / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Windows
```powershell
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
py main.py
```
Requires Python 3.9+ and `pygame` only (everything else is the standard library). No internet is needed.

## Host a LAN game
1. Start the game.
2. Select **Create Game** (name, player limit, optional numeric seed; empty = random).
3. Wait in the lobby. Other computers on the same LAN discover the game automatically.
4. When a player requests to join, a **PLAYER REQUEST** prompt appears: **Accept** or **Reject**.
5. Press **Start Game**.

## Join
1. Start the game.
2. Select **Find LAN Games**.
3. Select the discovered game.
4. Click **Request to Join**.
5. Wait for host approval.

*Fallback (debugging only):* the browser has a `host:port` field + **Connect** for networks that block UDP broadcast.
The host's address is shown at the bottom of the lobby. Default game port is TCP 47201; discovery uses UDP 47200.
Allow both through the firewall (Windows asks the first time you host).

Single Player on the main menu starts a private local server automatically.

## The story and what you do
**Research Station A-17 / the Underground Mining Complex** lost contact with the world. You and your crew wake up in the
central hub with a pistol. An anomaly called **the Echo** is feeding on the last signal: it kills lights, jams doors,
corrupts terminals, whispers false data, tears players through rifts and raises the dead. The only way out is the
emergency transmitter.

1. **Arm yourself.** Weapon crates (green, glowing) are hidden around the map: SMG, shotgun, rifle and the rare plasma gun.
   Some are in locked wings. Zombies drop ammo and medkits.
2. **Restore power** at the backup generator. This unlocks the red-lit restricted doors.
3. **Recover 5 signal fragments** (frequency, channel, sequence 1-3) from terminals. Notes and logs hint at where.
   Notebooks are per player: tell your crew what you found (press **T** to chat).
4. **Calibrate the signal core.** This wakes **the Echo Warden**, the boss guarding Central Communications.
5. **Destroy the Warden** (3 phases: slams, orb volleys, charges, and summoned zombies). It locks the transmitter.
6. **Transmit** the frequency / channel / sequence. Wrong codes are rejected (you see how many fields are right).
The timer is 40 minutes. Going down is not the end: you respawn at the hub after 8 seconds.

## Controls
| Key (default; all rebindable in Settings) | Action |
|---|---|
| W A S D / arrows | Move |
| Mouse | Aim |
| Left mouse / Space | Shoot (hold for automatic fire) |
| R | Reload |
| 1-5 / Q / mouse wheel | Switch weapon |
| E | Interact (terminals, crates, generator, core, medical station, camera console, transmitter) |
| T | Chat (Enter sends, Esc cancels); chat also works in the lobby |
| TAB | Notebook (everything *you* have read) |
| M | Larger minimap |
| F11 | Toggle fullscreen (starts fullscreen and scales to your screen) |
| ESC | Pause menu / close panels |

## Settings (sound and keys)
Main menu or pause menu -> **Settings**:
* **Sound on/off** (mute everything), master volume, and separate volumes for menu sounds, weapons and hits,
  doors and machines, and **horror ambience** (heartbeat, whispers, groans, jumpscare stinger). Horror ambience can be switched off on its own.
* **Every control is rebindable**: click a row, press the new key. If the key is already used the two actions swap.
  Arrow keys always work for movement; ESC (pause) is fixed. **Reset controls** restores defaults.
* Fullscreen toggle. Settings are saved per user (`%APPDATA%\the_last_signal` on Windows, `~/.config/the_last_signal` on Linux).
Default volumes are low and the random ambient sounds are rare (about one a minute); remote players' gunfire is only heard nearby.

## Weapons
| Weapon | Notes |
|---|---|
| Pistol | Start weapon, infinite ammo |
| SMG | Fast automatic, 30 rounds |
| Shotgun | 7 pellets, deadly up close |
| Rifle | Long range, pierces up to 3 enemies |
| Plasma | Rare, pierces 4 enemies |
Zombie kinds: walker, fast runner, tough brute. New zombies keep spawning, and gunfire wakes nearby ones.

## Map functions
* **Medical stations** (hub and medical wing): heal 70 HP, 45 s cooldown per player.
* **Camera consoles** (security and server wings, need power): mark every zombie and the boss on your minimap for 22 s.
* **Weapon crates**, **ammo / medkit pickups**, restricted wings behind the generator.
* **Echo events**: lights out, door malfunction, terminal corruption, false messages, signal interference, zombie surge,
  **rifts** (a random player is teleported across the map), **jumpscares** and **phantoms** (hallucinations + whispers).
  Dread audio is synthesised at runtime: heartbeat speeds up near enemies.

## Maps (choose on the main menu for single player, or in Create Game)
All maps are generated from a seed, validated (everything reachable) and packed densely: 40-50 rooms in a compact area,
extra shortcut links between neighbouring rooms, and zombies, loot caches and ammo/medkit pickups along every path, so
travelling between rooms is never empty running.
1. **Research Station A-17**: bright labs, server wing, archive, communications.
2. **Underground Mining Complex**: dark tunnels with lantern light, ore carts, rails, drills, pump house, blast vault.
3. **The Dead Zone (open world)**: ~40 walled outposts scattered over open grass and wasteland, linked by roads, with
   forests, rocks and car wrecks. Nothing forces a route.
   * **Day and night** (7-minute cycle): bright days with long sight, dark nights with a short light radius, more and
     keener zombies, orange dusk and dawn. The time of day is shown top right.
   * **Campfires**: 6 outdoor camps plus one in the Survivor Camp. Press the interact key to light one: it becomes your
     **respawn point** and heals 30 HP (once a minute).
   * **Supply drops**: every 2-3 minutes a crate lands somewhere on the map with a weapon, ammo and a medkit. It is marked
     on the world map, with a beam of light and an edge arrow showing distance; zombies are drawn to it. Race for it.
   * **Roaming zombies**: idle zombies wander the countryside in packs instead of standing still.
   * **Discovery**: entering a place for the first time shows its name. Press the map key (**M**) for the **world map** with
     the explored area, named places, campfires, supply drops and your crew.
Each map is one class implementing `BaseMapGenerator`, so more maps can be added the same way.

## Architecture (short)
* `game/maps/` – `BaseMapGenerator` framework (rooms, corridors, doors, walls, retry/validate loop), `validator.py`,
  and `research_station.py` (Map 1). Future maps implement the same interface and register in `maps/__init__.py`.
* `game/state.py` – the **authoritative world** (movement, doors, objectives, clues, Echo, timer). No networking inside.
* `game/networking/` – length-prefixed JSON over TCP (`protocol.py`, schema-validated), selectors based `server.py`,
  `client.py`, UDP broadcast `discovery.py`.
* Clients send *intents* only (movement vector, interact, transmit). The server owns positions, doors, objects, clues,
  objectives, Echo, timer and phase. Clients predict their own movement and are reconciled to the server.
* The map is generated on the host and sent to clients as compressed data (without the answers), so generation never
  has to match across machines/Python versions.
* `game/rendering/`, `game/ui/` – chunk-cached world renderer (only visible chunks are drawn), HUD, menus.

## Tools / tests
```bash
pip install pytest
python -m pytest tests -q          # 126 tests: 100 seeds, validator, protocol abuse, collision, rules, multiplayer
python server.py --auto-accept     # optional headless dedicated server
python client.py --connect 127.0.0.1:47201 --name Bot   # headless debug client
python tools/build_assets.py /path/to/extracted/asset [/path/to/second/asset/root]   # rebuild assets (needs Pillow)
```

## Known limitations (v1)
* Players do not collide with each other (avoids jams in corridors with 15 players).
* The Echo is an event system, not a roaming enemy (by design for Map 1); zombies are the roaming enemy.
* Characters use a front/back view (Among Us style) while the floors and furniture stay top-down tiles, so the look is a hybrid.
* The art is the supplied Kenney 2D packs plus procedurally drawn machinery, with lighting, shadows, decals and glows added
  by the renderer. It is atmospheric but not hand-painted professional art.
* Reconnect: a dropped client automatically retries for 40 s using its token and keeps its slot (90 s server side).
* Machinery sprites (terminals, racks, generator, transmitter…) are procedurally drawn by `tools/build_assets.py` because the
  supplied 2D packs have no top-down sci-fi machinery; see `CREDITS.md`.
* Audio is skipped silently when no audio device exists.
* Tested on Linux (headless SDL). It is pure Python/pygame with `pathlib` paths and no OS specific calls, but a real
  Windows run was **not** performed in this environment.
