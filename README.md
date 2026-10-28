# Ashen Realms

A compact, Python-only Soulslike dungeon crawler. Fight through a handcrafted
dungeon, defeat its wardens and boss, collect randomized equipment, unlock
skills, level up, and descend into increasingly difficult runs.

The project uses no downloaded art. Characters, dungeon tiles, weapons,
particles, loot, lighting accents, and UI are all drawn procedurally with
Pygame at runtime.

## Features

- Weighty melee combat with stamina, invulnerability-frame dodge rolls, flasks,
  hit reactions, and screen shake
- Hollow, armored knight, and ranged archer enemies plus a two-phase boss
- Three rotating stages: Ashen Crypt, Drowned Catacomb, and Frostbound Keep
- Wall-blocked arrows and melee strikes, corner-safe movement, and dodge collision
- Random weapon, armor, and charm drops across multiple rarity tiers
- Character XP, souls, stat growth, equipment upgrades, and persistent saves
- Three named character profiles with independent progression
- Persistent screen-shake and Story/Normal/Brutal difficulty settings
- Unlockable Whirlwind and Soul Burst skills
- Repeatable dungeon descents with scaling enemies
- Completely code-generated visual assets

This is a complete single-player gameplay vertical slice. A production MMORPG
would additionally require authoritative servers, accounts, databases,
matchmaking, anti-cheat, and live operations.

## Run

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Controls

| Action | Key |
| --- | --- |
| Move | `WASD` or arrow keys |
| Attack | `F` or `J` |
| Dodge roll | `Space` or `Shift` |
| Pick up / equip loot | `E` |
| Drink flask | `H` |
| Whirlwind (level 2) | `Q` |
| Soul Burst (level 4) | `R` |
| Next descent after victory | `N` |
| Menu / save | `Esc` |

Loot upgrades are equipped automatically and visibly change the hero's armor,
sword color, and sword size. Weaker drops are salvaged into souls. Progress is
stored independently under `profiles/`; preferences are stored in
`settings.json`.
