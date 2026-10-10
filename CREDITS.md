# Credits

All third-party art, fonts and audio are by **Kenney** (https://kenney.nl), released under **Creative Commons Zero (CC0 1.0)**.
The original license files are preserved in `assets/licenses/`.

## Packs used

| Pack | Used for |
|---|---|
| `kenney_top-down-shooter` | Teal/white/wood floor tiles, bed/sofa/crate/lab-burner/sink tiles, bush decorations and the pistol sprite |
| `kenney_platformer-characters` | Front/back view crew characters (Player, Female, Adventurer, Soldier) and the zombie, with walk/hurt/attack poses |
| `kenney_ui-pack-space-expansion` | Panel and button frames (9-slice, tinted at runtime), Kenney Future fonts |
| `kenney_game-icons` | HUD icons (signal bars) |
| `kenney_interface-sounds` | Menu click, join request, join/leave, error, success, glitch and confirmation sounds |
| `kenney_sci-fi-sounds` | Doors, terminals, generator, transmitter, Echo, shots, hits, victory and failure sounds |
| `kenney_light-masks-1.0` | The visibility light mask around the player (`assets/common/lighting/light_mask.png`) |
| `kenney_input-prompts_1.5` | The "E" key prompt icon |

## Not original artwork, but derived

* Wall tiles, the server/hazard/storage/dark/medical floors are *derived* from the Kenney floor tiles by tinting/overlay
  (`tools/build_assets.py`).
* Terminals, consoles, generator, signal core, transmitter, server racks, lab tables, shelves, lockers, pipes, panels,
  holo table, scanner, doors, barrels and metal crates are **drawn procedurally by `tools/build_assets.py`** (project code,
  in the Kenney flat style) because none of the supplied 2D packs contains top-down sci-fi machinery. They are not Kenney artwork.

## Map 2 (Underground Mining Complex) assets
Dirt/rock floors are derived (tinted + noise) from Kenney top-down-shooter floor tiles. The rock walls, ore carts, rails,
drill, pump, TNT crates, ore piles, support beams and lanterns, plus the weapon crates, medical station, camera console,
pickups and blood/scorch/crack decals, are drawn by `tools/build_assets.py` (project code, not Kenney artwork).
The heartbeat, whisper, groan and jumpscare stinger sounds are synthesised at runtime in `game/audio.py`.

## Packs inspected but NOT used

`kenney_space-station-kit` and `kenney_modular-space-kit_1.0` are 3D-only (FBX/OBJ/GLB) and were deliberately skipped.
`kenney_roguelike-*` (16 px fantasy/city), `kenney_modular-characters`, `kenney_sci-fi-rts` (Mars RTS units), `kenney_tiny-factory` (16 px) and the
remaining packs do not fit a 64 px top-down research station and are not included in the project.
