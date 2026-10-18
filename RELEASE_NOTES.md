# The Last Signal v2.0.0 — The Dead Zone Update

**Release title:** The Last Signal v2.0.0: The Dead Zone Update  
**Suggested Git tag:** `v2.0.0`

## Highlights

- Added the open-world **Dead Zone** map with scattered outposts, roads, grassland, wasteland, trees, rocks, and wreckage.
- Added a day/night cycle that changes visibility and zombie pressure.
- Added campfires that can establish player respawn points and provide periodic healing.
- Added supply drops with weapons, ammunition, and medkits, visible world-map indicators, and enemy attraction.
- Added roaming zombie packs and location discovery for open-world exploration.
- Expanded settings with fullscreen control, key rebinding, master volume, category-specific audio levels, and a separate horror-ambience control.
- Improved map generation, map validation, map registration, and generated asset support.
- Expanded automated coverage for features, settings, and map generation.
- Updated the project documentation and clarified the scope of the MIT license relative to third-party assets.

## Gameplay

The release builds on the existing co-op survival loop: explore, find weapons and supplies, restore power, recover signal fragments, face the Echo Warden, and transmit the signal. Players can play alone or host/join a local-network session.

## Compatibility and verification

- Requires Python 3.9+ and Pygame 2.5+.
- The project includes an automated pytest suite. Run `python -m pytest tests -q` from the repository root to verify the checkout.
- Do not treat a platform as verified unless the game and tests have actually been run there. Windows compatibility has not been confirmed by this release note.

## Licensing

The game source code is licensed under MIT. Third-party assets retain their own applicable licenses; consult `CREDITS.md` and `assets/licenses/`.

## Before publishing the GitHub release

1. Run the full test suite and review any failures.
2. Confirm that `v2.0.0` is not already used by an existing tag or release.
3. Create the annotated tag on the final commit intended for release.
4. Publish this file's summary as the GitHub release description.
