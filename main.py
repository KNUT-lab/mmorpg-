from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import pygame


WIDTH, HEIGHT = 1280, 720
WORLD_W, WORLD_H = 2240, 1440
FPS = 60
DATA_DIR = Path(__file__).with_name("profiles")
SETTINGS_FILE = Path(__file__).with_name("settings.json")

INK = (16, 18, 24)
STONE = (42, 45, 52)
STONE_2 = (53, 55, 62)
PARCHMENT = (218, 205, 175)
RED = (174, 44, 53)
GOLD = (210, 166, 68)
CYAN = (82, 190, 195)
GREEN = (78, 153, 100)

STAGES = (
    {"name": "Ashen Crypt", "floor": (43, 44, 49), "wall": (83, 76, 70), "accent": (205, 108, 55)},
    {"name": "Drowned Catacomb", "floor": (32, 49, 49), "wall": (59, 91, 83), "accent": (67, 183, 157)},
    {"name": "Frostbound Keep", "floor": (40, 48, 60), "wall": (91, 107, 126), "accent": (117, 184, 221)},
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def length(vector: pygame.Vector2) -> float:
    return math.hypot(vector.x, vector.y)


def circle_hit(a: pygame.Vector2, ar: float, b: pygame.Vector2, br: float) -> bool:
    return a.distance_squared_to(b) <= (ar + br) ** 2


@dataclass(frozen=True)
class Item:
    name: str
    slot: str
    power: int
    rarity: str
    color: tuple[int, int, int]


RARITIES = [
    ("Worn", (145, 145, 150), 0),
    ("Forged", (78, 153, 100), 2),
    ("Runic", (80, 130, 210), 5),
    ("Abyssal", (169, 80, 210), 9),
]


def make_item(depth: int, boss: bool = False) -> Item:
    if boss:
        return Item("Crown of the Hollow King", "charm", 15 + depth * 3, "Legendary", GOLD)
    roll = random.random()
    tier = 0 if roll < 0.48 else 1 if roll < 0.78 else 2 if roll < 0.95 else 3
    rarity, color, bonus = RARITIES[tier]
    slot = random.choice(("weapon", "armor", "charm"))
    nouns = {
        "weapon": ("Longsword", "Cleaver", "Ash Spear"),
        "armor": ("Plate", "Brigandine", "Grave Mantle"),
        "charm": ("Wolf Sigil", "Bone Ring", "Ember Idol"),
    }
    return Item(
        f"{rarity} {random.choice(nouns[slot])}",
        slot,
        depth * 2 + random.randint(1, 4) + bonus,
        rarity,
        color,
    )


class Particle:
    def __init__(self, pos: pygame.Vector2, color: tuple[int, int, int], speed: float = 180):
        self.pos = pygame.Vector2(pos)
        angle = random.random() * math.tau
        self.vel = pygame.Vector2(math.cos(angle), math.sin(angle)) * random.uniform(30, speed)
        self.life = random.uniform(0.25, 0.65)
        self.max_life = self.life
        self.color = color

    def update(self, dt: float) -> bool:
        self.life -= dt
        self.pos += self.vel * dt
        self.vel *= 0.92
        return self.life > 0

    def draw(self, screen: pygame.Surface, camera: pygame.Vector2) -> None:
        radius = max(1, int(4 * self.life / self.max_life))
        pygame.draw.circle(screen, self.color, self.pos - camera, radius)


class DamageText:
    def __init__(self, pos: pygame.Vector2, text: str, color: tuple[int, int, int]):
        self.pos = pygame.Vector2(pos)
        self.text = text
        self.color = color
        self.life = 0.8

    def update(self, dt: float) -> bool:
        self.life -= dt
        self.pos.y -= 34 * dt
        return self.life > 0


class Actor:
    def __init__(self, x: float, y: float, radius: float):
        self.pos = pygame.Vector2(x, y)
        self.radius = radius
        # The collision capsule is slightly smaller than the artwork so shoulders,
        # swords and capes do not snag on every dungeon corner.
        self.collision_radius = radius * 0.78
        self.hp = self.max_hp = 100.0
        self.flash = 0.0


class Player(Actor):
    def __init__(self):
        super().__init__(180, 720, 22)
        self.level = 1
        self.xp = 0
        self.xp_next = 80
        self.souls = 0
        self.depth = 1
        self.stamina = self.max_stamina = 100.0
        self.facing = pygame.Vector2(1, 0)
        self.attack_cd = 0.0
        self.attack_time = 0.0
        self.attack_id = 0
        self.roll_time = 0.0
        self.roll_cd = 0.0
        self.roll_dir = pygame.Vector2()
        self.invuln = 0.0
        self.flasks = 3
        self.max_flasks = 3
        self.skill_cd = 0.0
        self.burst_cd = 0.0
        self.equipment: dict[str, Item] = {
            "weapon": Item("Pilgrim Sword", "weapon", 2, "Starter", (160, 160, 165)),
            "armor": Item("Tattered Mail", "armor", 1, "Starter", (140, 140, 145)),
            "charm": Item("Empty Reliquary", "charm", 0, "Starter", (120, 120, 125)),
        }

    @property
    def damage(self) -> int:
        return 13 + self.level * 3 + self.equipment["weapon"].power

    @property
    def defense(self) -> int:
        return self.level + self.equipment["armor"].power + self.equipment["charm"].power // 3

    def gain_xp(self, amount: int, game: Game) -> None:
        self.xp += amount
        self.souls += amount
        while self.xp >= self.xp_next:
            self.xp -= self.xp_next
            self.level += 1
            self.xp_next = int(self.xp_next * 1.45)
            self.max_hp += 15
            self.max_stamina += 8
            self.hp = self.max_hp
            self.stamina = self.max_stamina
            game.notice(f"LEVEL {self.level} — strength and vitality increased", GOLD)

    def hurt(self, amount: float, direction: pygame.Vector2, game: Game) -> None:
        if self.invuln > 0:
            return
        actual = max(1, int(amount - self.defense * 0.45))
        self.hp -= actual
        self.pos += direction * 14
        self.invuln = 0.5
        self.flash = 0.14
        game.add_burst(self.pos, RED, 10)
        game.damage_texts.append(DamageText(self.pos, str(actual), (245, 100, 100)))
        if self.hp <= 0:
            game.player_died()

    def update(self, dt: float, game: Game) -> None:
        keys = pygame.key.get_pressed()
        move = pygame.Vector2(
            int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if move.length_squared():
            move.normalize_ip()
            if self.roll_time <= 0:
                self.facing = move

        self.attack_cd = max(0, self.attack_cd - dt)
        self.attack_time = max(0, self.attack_time - dt)
        self.roll_cd = max(0, self.roll_cd - dt)
        self.roll_time = max(0, self.roll_time - dt)
        self.invuln = max(0, self.invuln - dt)
        self.flash = max(0, self.flash - dt)
        self.skill_cd = max(0, self.skill_cd - dt)
        self.burst_cd = max(0, self.burst_cd - dt)

        if self.roll_time > 0:
            game.move_actor(self, self.roll_dir * 520 * dt)
        else:
            game.move_actor(self, move * 235 * dt)
            self.stamina = min(self.max_stamina, self.stamina + 27 * dt)

    def roll(self, game: Game) -> None:
        if self.roll_cd > 0 or self.stamina < 25:
            return
        self.roll_dir = self.facing.normalize() if self.facing.length_squared() else pygame.Vector2(1, 0)
        self.roll_time = 0.28
        self.roll_cd = 0.4
        self.invuln = 0.34
        self.stamina -= 25
        game.add_burst(self.pos, (100, 105, 115), 7)

    def attack(self, game: Game) -> None:
        if self.attack_cd > 0 or self.roll_time > 0 or self.stamina < 14:
            return
        self.attack_cd = 0.36
        self.attack_time = 0.16
        self.attack_id += 1
        self.stamina -= 14
        game.player_strike(82, self.damage, 0.62)

    def whirlwind(self, game: Game) -> None:
        if self.level < 2:
            game.notice("Whirlwind unlocks at level 2", (180, 180, 185))
            return
        if self.skill_cd or self.stamina < 45:
            return
        self.skill_cd = 5.0
        self.stamina -= 45
        game.player_strike(130, int(self.damage * 1.35), -1)
        game.add_burst(self.pos, CYAN, 22)

    def soul_burst(self, game: Game) -> None:
        if self.level < 4:
            game.notice("Soul Burst unlocks at level 4", (180, 180, 185))
            return
        if self.burst_cd or self.souls < 25:
            return
        self.burst_cd = 8.0
        self.souls -= 25
        game.player_strike(240, int(self.damage * 1.8), -1)
        game.add_burst(self.pos, (150, 95, 230), 45)


class Enemy(Actor):
    def __init__(self, x: float, y: float, depth: int, kind: str = "hollow"):
        radius = 42 if kind == "boss" else 25 if kind == "knight" else 20
        super().__init__(x, y, radius)
        self.kind = kind
        scale = 1 + (depth - 1) * 0.28
        base_hp = 420 if kind == "boss" else 82 if kind == "knight" else 42 if kind == "archer" else 48
        self.max_hp = self.hp = base_hp * scale
        self.damage = (30 if kind == "boss" else 18 if kind == "knight" else 14 if kind == "archer" else 11) * scale
        self.speed = 100 if kind == "boss" else 78 if kind == "knight" else 92 if kind == "archer" else 105
        self.attack_cd = random.random()
        self.windup = 0.0
        self.stun = 0.0
        self.last_hit = -1
        self.dead = False
        self.phase = 1

    def hurt(self, damage: int, direction: pygame.Vector2, game: Game) -> None:
        if self.dead:
            return
        self.hp -= damage
        self.flash = 0.12
        self.stun = 0.12 if self.kind != "boss" else 0.04
        self.pos += direction * (13 if self.kind != "boss" else 4)
        game.add_burst(self.pos, RED, 7)
        game.damage_texts.append(DamageText(self.pos, str(damage), PARCHMENT))
        if self.hp <= 0:
            self.dead = True
            game.enemy_died(self)

    def update(self, dt: float, game: Game) -> None:
        self.flash = max(0, self.flash - dt)
        self.attack_cd = max(0, self.attack_cd - dt)
        self.stun = max(0, self.stun - dt)
        if self.dead or self.stun > 0:
            return
        to_player = game.player.pos - self.pos
        distance = length(to_player)
        direction = to_player.normalize() if distance else pygame.Vector2()

        if self.kind == "boss" and self.phase == 1 and self.hp < self.max_hp * 0.5:
            self.phase = 2
            self.speed *= 1.3
            self.damage *= 1.2
            game.notice("THE HOLLOW KING ENTERS A FRENZY", RED)
            game.add_burst(self.pos, RED, 40)

        if self.kind == "archer":
            blocked = game.blocked_between(self.pos, game.player.pos)
            if distance < 145:
                game.move_actor(self, -direction * self.speed * dt)
            elif distance > 345 or blocked:
                chase = direction.rotate(72 if int(self.pos.x + self.pos.y) % 2 else -72) if blocked else direction
                game.move_actor(self, chase * self.speed * dt)
            elif self.attack_cd <= 0:
                self.attack_cd = 1.65
                game.projectiles.append(Projectile(self.pos + direction * 24, direction, self.damage, GOLD))
                game.add_burst(self.pos + direction * 18, GOLD, 3)
            return

        attack_range = self.radius + game.player.radius + (24 if self.kind == "boss" else 8)
        if distance > attack_range:
            game.move_actor(self, direction * self.speed * dt)
        elif self.attack_cd <= 0 and not game.blocked_between(self.pos, game.player.pos):
            self.attack_cd = 1.7 if self.kind == "boss" and self.phase == 1 else 1.05
            game.player.hurt(self.damage, direction, game)
            if self.kind == "boss" and self.phase == 2:
                game.add_burst(self.pos, RED, 12)


class Loot:
    def __init__(self, pos: pygame.Vector2, item: Item):
        self.pos = pygame.Vector2(pos)
        self.item = item
        self.phase = random.random() * math.tau


class Projectile:
    def __init__(self, pos: pygame.Vector2, direction: pygame.Vector2, damage: float, color=GOLD):
        self.pos = pygame.Vector2(pos)
        self.previous = pygame.Vector2(pos)
        self.velocity = direction.normalize() * 390
        self.damage = damage
        self.color = color
        self.life = 2.2
        self.radius = 5

    def update(self, dt: float, game: Game) -> bool:
        self.life -= dt
        self.previous.update(self.pos)
        self.pos += self.velocity * dt
        if self.life <= 0 or game.blocked_between(self.previous, self.pos):
            game.add_burst(self.pos, self.color, 4)
            return False
        if circle_hit(self.pos, self.radius, game.player.pos, game.player.collision_radius):
            direction = self.velocity.normalize()
            game.player.hurt(self.damage, direction, game)
            game.add_burst(self.pos, self.color, 7)
            return False
        return True

    def draw(self, screen: pygame.Surface, camera: pygame.Vector2) -> None:
        p = self.pos - camera
        direction = self.velocity.normalize()
        side = direction.rotate(90)
        pygame.draw.line(screen, (85, 55, 34), p - direction * 15, p + direction * 7, 4)
        pygame.draw.polygon(screen, self.color, [
            p + direction * 11, p + direction * 3 + side * 4, p + direction * 3 - side * 4,
        ])
        pygame.draw.line(screen, (165, 136, 91), p - direction * 14 - side * 5, p - direction * 8, 2)
        pygame.draw.line(screen, (165, 136, 91), p - direction * 14 + side * 5, p - direction * 8, 2)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("ASHEN REALMS")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("georgia", 19)
        self.small = pygame.font.SysFont("consolas", 14)
        self.title_font = pygame.font.SysFont("georgia", 58, bold=True)
        self.big_font = pygame.font.SysFont("georgia", 34, bold=True)
        self.player = Player()
        self.state = "menu"
        self.active_profile = 1
        self.profile_name = ""
        self.name_buffer = ""
        self.settings = {"screen_shake": True, "difficulty": "Normal"}
        self.load_settings()
        self.running = True
        self.enemies: list[Enemy] = []
        self.loot: list[Loot] = []
        self.projectiles: list[Projectile] = []
        self.particles: list[Particle] = []
        self.damage_texts: list[DamageText] = []
        self.notices: list[list] = []
        self.camera = pygame.Vector2()
        self.shake = 0.0
        self.kills = 0
        self.boss_spawned = False
        self.victory = False
        self.stage_index = 0
        self.theme = STAGES[0]
        self.walls = self.build_walls(0)
        self.floor_tiles = self.make_floor()
        self.new_dungeon()

    def profile_path(self, slot: int | None = None) -> Path:
        return DATA_DIR / f"profile_{slot or self.active_profile}.json"

    def load_settings(self) -> None:
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
            self.settings.update({key: saved[key] for key in self.settings if key in saved})
        except (OSError, TypeError, json.JSONDecodeError):
            pass

    def save_settings(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2))

    def build_walls(self, stage: int) -> list[pygame.Rect]:
        t = 48
        boundary = [
            pygame.Rect(0, 0, WORLD_W, t),
            pygame.Rect(0, WORLD_H - t, WORLD_W, t),
            pygame.Rect(0, 0, t, WORLD_H),
            pygame.Rect(WORLD_W - t, 0, t, WORLD_H),
        ]
        layouts = (
            [
                pygame.Rect(430, 0, 55, 520), pygame.Rect(430, 690, 55, 750),
                pygame.Rect(890, 250, 55, 440), pygame.Rect(890, 850, 55, 590),
                pygame.Rect(1300, 0, 55, 470), pygame.Rect(1300, 650, 55, 520),
                pygame.Rect(1300, 1330, 55, 110), pygame.Rect(1720, 260, 55, 920),
            ],
            [
                pygame.Rect(420, 220, 55, 1220), pygame.Rect(820, 0, 55, 530),
                pygame.Rect(820, 710, 55, 420), pygame.Rect(820, 1310, 55, 130),
                pygame.Rect(1210, 260, 55, 1180), pygame.Rect(1580, 0, 55, 410),
                pygame.Rect(1580, 610, 55, 520), pygame.Rect(1580, 1300, 55, 140),
                pygame.Rect(1880, 230, 55, 980),
            ],
            [
                pygame.Rect(360, 0, 55, 400), pygame.Rect(360, 590, 55, 850),
                pygame.Rect(710, 250, 55, 940), pygame.Rect(1060, 0, 55, 570),
                pygame.Rect(1060, 750, 55, 690), pygame.Rect(1410, 210, 55, 1020),
                pygame.Rect(1760, 0, 55, 480), pygame.Rect(1760, 680, 55, 760),
            ],
        )
        return boundary + layouts[stage % len(layouts)]

    def make_floor(self) -> list[tuple[int, int, int]]:
        rng = random.Random(4407)
        tiles = []
        for x in range(48, WORLD_W - 48, 64):
            for y in range(48, WORLD_H - 48, 64):
                tiles.append((x, y, rng.randint(-6, 7)))
        return tiles

    def new_dungeon(self) -> None:
        self.stage_index = (self.player.depth - 1) % len(STAGES)
        self.theme = STAGES[self.stage_index]
        self.walls = self.build_walls(self.stage_index)
        self.player.pos.update(180, 720)
        self.player.hp = self.player.max_hp
        self.player.stamina = self.player.max_stamina
        self.player.flasks = self.player.max_flasks
        self.enemies.clear()
        self.loot.clear()
        self.projectiles.clear()
        self.particles.clear()
        self.kills = 0
        self.boss_spawned = False
        self.victory = False
        stage_spawns = (
            [
                (620, 280, "archer"), (720, 700, "knight"), (630, 1120, "hollow"),
                (1080, 420, "hollow"), (1140, 980, "archer"), (1490, 240, "hollow"),
                (1500, 730, "knight"), (1500, 1210, "archer"),
            ],
            [
                (610, 120, "archer"), (650, 650, "knight"), (650, 1220, "hollow"),
                (1030, 170, "archer"), (1030, 650, "knight"), (1030, 1240, "hollow"),
                (1400, 170, "archer"), (1420, 720, "knight"),
            ],
            [
                (520, 180, "archer"), (520, 720, "knight"), (520, 1280, "hollow"),
                (880, 180, "archer"), (880, 650, "knight"), (880, 1260, "hollow"),
                (1240, 150, "archer"), (1240, 700, "knight"),
            ],
        )
        spawns = stage_spawns[self.stage_index]
        for x, y, kind in spawns:
            enemy = Enemy(x, y, self.player.depth, kind)
            modifier = {"Story": 0.75, "Normal": 1.0, "Brutal": 1.35}[self.settings["difficulty"]]
            enemy.hp *= modifier
            enemy.max_hp *= modifier
            enemy.damage *= modifier
            self.enemies.append(enemy)
        self.notice(f"{self.theme['name'].upper()} — defeat 8 wardens", self.theme["accent"])

    def save(self) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        data = {
            "profile_name": self.profile_name or f"Wanderer {self.active_profile}",
            "level": self.player.level,
            "xp": self.player.xp,
            "xp_next": self.player.xp_next,
            "souls": self.player.souls,
            "depth": self.player.depth,
            "max_hp": self.player.max_hp,
            "max_stamina": self.player.max_stamina,
            "equipment": {
                slot: {
                    "name": item.name, "slot": item.slot, "power": item.power,
                    "rarity": item.rarity, "color": item.color,
                }
                for slot, item in self.player.equipment.items()
            },
        }
        self.profile_path().write_text(json.dumps(data, indent=2))

    def load(self, slot: int | None = None) -> bool:
        if slot is not None:
            self.active_profile = slot
        path = self.profile_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            p = self.player
            self.profile_name = data.get("profile_name", f"Wanderer {self.active_profile}")
            for key in ("level", "xp", "xp_next", "souls", "depth", "max_hp", "max_stamina"):
                setattr(p, key, data[key])
            p.equipment = {
                slot: Item(v["name"], v["slot"], v["power"], v["rarity"], tuple(v["color"]))
                for slot, v in data["equipment"].items()
            }
            self.new_dungeon()
            return True
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def start_profile(self, slot: int, name: str) -> None:
        self.active_profile = slot
        self.profile_name = name.strip()[:18] or f"Wanderer {slot}"
        self.player = Player()
        self.new_dungeon()
        self.save()
        self.state = "playing"

    def profile_summary(self, slot: int) -> str:
        path = self.profile_path(slot)
        if not path.exists():
            return "Empty — create character"
        try:
            data = json.loads(path.read_text())
            return f"{data.get('profile_name', 'Wanderer')}   LV {data.get('level', 1)}   Depth {data.get('depth', 1)}"
        except (OSError, TypeError, json.JSONDecodeError):
            return "Corrupted save"

    def notice(self, text: str, color: tuple[int, int, int] = PARCHMENT) -> None:
        self.notices.append([text, color, 3.0])

    def add_burst(self, pos: pygame.Vector2, color: tuple[int, int, int], count: int) -> None:
        self.particles.extend(Particle(pos, color) for _ in range(count))
        if self.settings["screen_shake"]:
            self.shake = min(10, self.shake + count * 0.08)

    @staticmethod
    def circle_overlaps_rect(pos: pygame.Vector2, radius: float, rect: pygame.Rect) -> bool:
        nearest_x = clamp(pos.x, rect.left, rect.right)
        nearest_y = clamp(pos.y, rect.top, rect.bottom)
        return (pos.x - nearest_x) ** 2 + (pos.y - nearest_y) ** 2 < radius ** 2

    def blocked_between(self, start: pygame.Vector2, end: pygame.Vector2) -> bool:
        return any(wall.inflate(4, 4).clipline(start, end) for wall in self.walls)

    def push_actor_out_of_walls(self, actor: Actor) -> None:
        radius = actor.collision_radius
        for _ in range(4):
            moved = False
            for wall in self.walls:
                nearest = pygame.Vector2(
                    clamp(actor.pos.x, wall.left, wall.right),
                    clamp(actor.pos.y, wall.top, wall.bottom),
                )
                offset = actor.pos - nearest
                distance = offset.length()
                if 0 < distance < radius:
                    actor.pos += offset / distance * (radius - distance + 0.5)
                    moved = True
                elif distance == 0 and wall.collidepoint(actor.pos):
                    exits = [
                        (actor.pos.x - wall.left, pygame.Vector2(-1, 0)),
                        (wall.right - actor.pos.x, pygame.Vector2(1, 0)),
                        (actor.pos.y - wall.top, pygame.Vector2(0, -1)),
                        (wall.bottom - actor.pos.y, pygame.Vector2(0, 1)),
                    ]
                    gap, direction = min(exits, key=lambda item: item[0])
                    actor.pos += direction * (gap + radius + 0.5)
                    moved = True
            if not moved:
                break

    def move_actor(self, actor: Actor, delta: pygame.Vector2) -> None:
        self.push_actor_out_of_walls(actor)
        # Substeps prevent fast dodge rolls from tunnelling through narrow walls.
        radius = actor.collision_radius
        steps = max(1, math.ceil(max(abs(delta.x), abs(delta.y)) / max(4, radius * 0.45)))
        step = delta / steps
        for _ in range(steps):
            actor.pos.x += step.x
            if any(self.circle_overlaps_rect(actor.pos, radius, wall) for wall in self.walls):
                actor.pos.x -= step.x
            actor.pos.y += step.y
            if any(self.circle_overlaps_rect(actor.pos, radius, wall) for wall in self.walls):
                actor.pos.y -= step.y
        actor.pos.x = clamp(actor.pos.x, radius, WORLD_W - radius)
        actor.pos.y = clamp(actor.pos.y, radius, WORLD_H - radius)
        self.push_actor_out_of_walls(actor)

    def player_strike(self, reach: float, damage: int, arc: float) -> None:
        hit = False
        for enemy in self.enemies:
            if enemy.dead or self.player.pos.distance_to(enemy.pos) > reach + enemy.radius:
                continue
            if self.blocked_between(self.player.pos, enemy.pos):
                continue
            direction = (enemy.pos - self.player.pos).normalize() if enemy.pos != self.player.pos else self.player.facing
            if arc < 0 or self.player.facing.dot(direction) >= arc:
                enemy.hurt(damage, direction, self)
                hit = True
        if hit:
            self.shake = max(self.shake, 4)

    def enemy_died(self, enemy: Enemy) -> None:
        reward = 160 if enemy.kind == "boss" else 32 if enemy.kind == "knight" else 20
        self.player.gain_xp(int(reward * (1 + (self.player.depth - 1) * 0.15)), self)
        self.add_burst(enemy.pos, GOLD if enemy.kind == "boss" else RED, 26)
        if enemy.kind == "boss":
            self.loot.append(Loot(enemy.pos, make_item(self.player.depth, True)))
            self.victory = True
            self.save()
            self.notice("THE HOLLOW KING HAS FALLEN", GOLD)
        else:
            self.kills += 1
            if random.random() < 0.42:
                self.loot.append(Loot(enemy.pos, make_item(self.player.depth)))
            if self.kills == 8 and not self.boss_spawned:
                self.boss_spawned = True
                boss = Enemy(2050, 720, self.player.depth, "boss")
                modifier = {"Story": 0.75, "Normal": 1.0, "Brutal": 1.35}[self.settings["difficulty"]]
                boss.hp *= modifier
                boss.max_hp *= modifier
                boss.damage *= modifier
                self.enemies.append(boss)
                self.notice("THE SEALED CHAMBER OPENS", RED)

    def pickup(self) -> None:
        nearby = [drop for drop in self.loot if self.player.pos.distance_to(drop.pos) < 64]
        if not nearby:
            return
        drop = nearby[0]
        old = self.player.equipment[drop.item.slot]
        if drop.item.power > old.power:
            self.player.equipment[drop.item.slot] = drop.item
            self.notice(f"Equipped {drop.item.name}  +{drop.item.power}", drop.item.color)
        else:
            gained = max(4, drop.item.power * 2)
            self.player.souls += gained
            self.notice(f"Salvaged {drop.item.name} for {gained} souls", (170, 170, 180))
        self.loot.remove(drop)
        self.save()

    def use_flask(self) -> None:
        if self.player.flasks and self.player.hp < self.player.max_hp:
            self.player.flasks -= 1
            self.player.hp = min(self.player.max_hp, self.player.hp + self.player.max_hp * 0.48)
            self.add_burst(self.player.pos, GOLD, 18)

    def player_died(self) -> None:
        lost = self.player.souls // 3
        self.player.souls -= lost
        self.notice(f"YOU DIED — {lost} souls lost", RED)
        self.new_dungeon()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        if event.type != pygame.KEYDOWN:
            return
        if self.state == "menu":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = "profiles"
            elif event.key == pygame.K_s:
                self.state = "settings"
            elif event.key == pygame.K_ESCAPE:
                self.running = False
            return
        if self.state == "profiles":
            if event.key == pygame.K_ESCAPE:
                self.state = "menu"
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                slot = event.key - pygame.K_0
                if self.load(slot):
                    self.state = "playing"
                else:
                    self.active_profile = slot
                    self.name_buffer = ""
                    self.state = "naming"
            return
        if self.state == "naming":
            if event.key == pygame.K_ESCAPE:
                self.state = "profiles"
            elif event.key == pygame.K_BACKSPACE:
                self.name_buffer = self.name_buffer[:-1]
            elif event.key == pygame.K_RETURN:
                self.start_profile(self.active_profile, self.name_buffer)
            elif event.unicode.isprintable() and (event.unicode.isalnum() or event.unicode in " -_"):
                self.name_buffer = (self.name_buffer + event.unicode)[:18]
            return
        if self.state == "settings":
            if event.key == pygame.K_ESCAPE:
                self.save_settings()
                self.state = "menu"
            elif event.key == pygame.K_1:
                self.settings["screen_shake"] = not self.settings["screen_shake"]
            elif event.key == pygame.K_2:
                choices = ["Story", "Normal", "Brutal"]
                current = choices.index(self.settings["difficulty"])
                self.settings["difficulty"] = choices[(current + 1) % len(choices)]
            return
        if event.key == pygame.K_ESCAPE:
            self.state = "menu"
            self.save()
        elif event.key in (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT):
            self.player.roll(self)
        elif event.key in (pygame.K_f, pygame.K_j):
            self.player.attack(self)
        elif event.key == pygame.K_q:
            self.player.whirlwind(self)
        elif event.key == pygame.K_r:
            self.player.soul_burst(self)
        elif event.key == pygame.K_e:
            self.pickup()
        elif event.key == pygame.K_h:
            self.use_flask()
        elif event.key == pygame.K_n and self.victory:
            self.player.depth += 1
            self.new_dungeon()
            self.save()

    def update(self, dt: float) -> None:
        self.player.update(dt, self)
        for enemy in list(self.enemies):
            enemy.update(dt, self)
        self.enemies = [enemy for enemy in self.enemies if not enemy.dead]
        self.projectiles = [projectile for projectile in self.projectiles if projectile.update(dt, self)]
        self.particles = [p for p in self.particles if p.update(dt)]
        self.damage_texts = [text for text in self.damage_texts if text.update(dt)]
        for notice in self.notices:
            notice[2] -= dt
        self.notices = [notice for notice in self.notices if notice[2] > 0]
        self.shake = max(0, self.shake - 22 * dt)
        target = self.player.pos - pygame.Vector2(WIDTH / 2, HEIGHT / 2)
        target.x = clamp(target.x, 0, WORLD_W - WIDTH)
        target.y = clamp(target.y, 0, WORLD_H - HEIGHT)
        self.camera += (target - self.camera) * min(1, dt * 7)

    def draw_floor(self, camera: pygame.Vector2) -> None:
        self.screen.fill(INK)
        view = pygame.Rect(camera.x - 70, camera.y - 70, WIDTH + 140, HEIGHT + 140)
        for x, y, shade in self.floor_tiles:
            rect = pygame.Rect(x - camera.x, y - camera.y, 62, 62)
            if view.collidepoint(x, y):
                floor = tuple(clamp(channel + shade, 0, 255) for channel in self.theme["floor"])
                pygame.draw.rect(self.screen, floor, rect)
                seam = tuple(max(0, channel - 14) for channel in self.theme["floor"])
                pygame.draw.line(self.screen, seam, rect.topleft, rect.topright)
                pygame.draw.line(self.screen, seam, rect.topleft, rect.bottomleft)
                if (x * 7 + y * 11) % 13 == 0:
                    pygame.draw.lines(self.screen, (28, 29, 34), False, [
                        (rect.x + 9, rect.y + 19), (rect.x + 25, rect.y + 26),
                        (rect.x + 20, rect.y + 40), (rect.x + 35, rect.y + 48),
                    ], 2)
        for wall in self.walls:
            rect = wall.move(-camera.x, -camera.y)
            pygame.draw.rect(self.screen, (18, 19, 23), rect.move(7, 9))
            wall_fill = tuple(max(15, channel - 35) for channel in self.theme["wall"])
            pygame.draw.rect(self.screen, wall_fill, rect)
            pygame.draw.rect(self.screen, self.theme["wall"], rect, 3)
            for y in range(rect.top + 12, rect.bottom, 28):
                pygame.draw.line(self.screen, (45, 44, 45), (rect.left, y), (rect.right, y), 2)
                offset = 16 if (y // 28) % 2 else 0
                for x in range(rect.left + offset, rect.right, 38):
                    pygame.draw.line(self.screen, (29, 29, 33), (x, y - 12), (x, y), 1)
            if rect.colliderect(self.screen.get_rect()) and wall.width < 100:
                flame = pygame.Vector2(rect.centerx, max(70, min(HEIGHT - 70, rect.centery)))
                pygame.draw.line(self.screen, (72, 52, 37), flame + (0, 12), flame + (0, 27), 5)
                pygame.draw.circle(self.screen, self.theme["accent"], flame, 7)
                pygame.draw.circle(self.screen, (245, 214, 128), flame + (0, 2), 3)

    def draw_enemy(self, enemy: Enemy, camera: pygame.Vector2) -> None:
        p = enemy.pos - camera
        if enemy.kind == "boss":
            color = (205, 55, 58) if enemy.flash else (86, 38, 43)
            direction = (self.player.pos - enemy.pos).normalize() if self.player.pos != enemy.pos else pygame.Vector2(1, 0)
            side = direction.rotate(90)
            pygame.draw.ellipse(self.screen, (12, 12, 15), pygame.Rect(p.x - 52, p.y + 24, 104, 27))
            cape = [p - direction * 35 - side * 35, p - direction * 60, p - direction * 35 + side * 35]
            pygame.draw.polygon(self.screen, (48, 17, 24), cape)
            pygame.draw.circle(self.screen, (18, 17, 20), p, 48)
            pygame.draw.circle(self.screen, color, p, 40)
            pygame.draw.arc(self.screen, (131, 121, 118), pygame.Rect(p.x - 42, p.y - 42, 84, 84), 0, math.tau, 5)
            head = p + direction * 18
            pygame.draw.circle(self.screen, (56, 49, 53), head, 17)
            pygame.draw.circle(self.screen, GOLD, head - side * 7 + direction * 8, 4)
            pygame.draw.circle(self.screen, GOLD, head + side * 7 + direction * 8, 4)
            crown_base = head - direction * 12
            for offset in (-12, 0, 12):
                tip = crown_base + side * offset - direction * (20 + (5 if offset == 0 else 0))
                pygame.draw.polygon(self.screen, GOLD, [crown_base + side * (offset - 6), crown_base + side * (offset + 6), tip])
            hand = p + side * 39
            sword_end = hand + direction * 67
            pygame.draw.line(self.screen, (72, 45, 30), hand - direction * 17, hand, 10)
            pygame.draw.line(self.screen, (151, 145, 148), hand, sword_end, 13)
            pygame.draw.line(self.screen, (222, 210, 194), hand, sword_end, 4)
            pygame.draw.polygon(self.screen, (218, 212, 199), [
                sword_end + direction * 12, sword_end + side * 7, sword_end - side * 7,
            ])
        else:
            direction = (self.player.pos - enemy.pos).normalize() if self.player.pos != enemy.pos else pygame.Vector2(1, 0)
            side = direction.rotate(90)
            stride = math.sin(pygame.time.get_ticks() * 0.008 + enemy.pos.x) * 5
            base = (180, 65, 66) if enemy.flash else (80, 87, 94) if enemy.kind == "knight" else (64, 83, 70) if enemy.kind == "archer" else (94, 86, 77)
            pygame.draw.ellipse(self.screen, (14, 15, 18), pygame.Rect(p.x - 24, p.y + 12, 48, 14))
            pygame.draw.line(self.screen, (48, 43, 40), p - side * 8, p - side * 10 - direction * (13 + stride), 7)
            pygame.draw.line(self.screen, (48, 43, 40), p + side * 8, p + side * 10 - direction * (13 - stride), 7)
            torso = [p + direction * 17, p + side * 17, p - direction * 16, p - side * 17]
            pygame.draw.polygon(self.screen, (18, 18, 21), [point + (3, 4) for point in torso])
            pygame.draw.polygon(self.screen, base, torso)
            pygame.draw.polygon(self.screen, (133, 125, 112), torso, 2)
            head = p + direction * 11
            pygame.draw.circle(self.screen, (111, 97, 81), head, 10)
            pygame.draw.circle(self.screen, (188, 62, 51), head - side * 4 + direction * 5, 2)
            pygame.draw.circle(self.screen, (188, 62, 51), head + side * 4 + direction * 5, 2)
            if enemy.kind == "archer":
                hood = [head + direction * 14, head + side * 14 - direction * 6, head - side * 14 - direction * 6]
                pygame.draw.polygon(self.screen, (38, 56, 45), hood)
                pygame.draw.polygon(self.screen, (92, 119, 91), hood, 2)
                bow_center = p + side * 18
                bow_box = pygame.Rect(bow_center.x - 17, bow_center.y - 17, 34, 34)
                bow_angle = math.atan2(direction.y, direction.x)
                pygame.draw.arc(self.screen, (175, 124, 67), bow_box, bow_angle - 1.5, bow_angle + 1.5, 4)
                pygame.draw.line(self.screen, (205, 198, 169), bow_center - direction.rotate(50) * 15, bow_center - direction.rotate(-50) * 15, 1)
                quiver = p - side * 13 - direction * 12
                pygame.draw.line(self.screen, (92, 57, 35), quiver, quiver - direction * 24, 7)
                for offset in (-4, 0, 4):
                    pygame.draw.line(self.screen, GOLD, quiver + side * offset - direction * 18, quiver + side * offset - direction * 29, 2)
            else:
                hand = p + side * 15
                blade_tip = hand + direction * (36 if enemy.kind == "knight" else 29)
                pygame.draw.line(self.screen, (63, 43, 34), hand - direction * 8, hand, 6)
                pygame.draw.line(self.screen, (185, 186, 180), hand, blade_tip, 5)
                pygame.draw.polygon(self.screen, (220, 218, 205), [
                    blade_tip + direction * 5, blade_tip + side * 3, blade_tip - side * 3,
                ])
            if enemy.kind == "knight":
                pygame.draw.arc(self.screen, (155, 157, 162), pygame.Rect(p.x - 24, p.y - 25, 48, 43), math.pi, math.tau, 5)
                shield = p - side * 20
                pygame.draw.circle(self.screen, (58, 67, 76), shield, 13)
                pygame.draw.circle(self.screen, (167, 167, 162), shield, 13, 3)
                pygame.draw.line(self.screen, (167, 167, 162), shield + (-8, 0), shield + (8, 0), 2)
        if enemy.hp < enemy.max_hp:
            self.bar(pygame.Rect(p.x - 28, p.y - enemy.radius - 17, 56, 6), enemy.hp / enemy.max_hp, RED)

    def draw_player(self, camera: pygame.Vector2) -> None:
        p = self.player.pos - camera
        facing = self.player.facing.normalize() if self.player.facing.length_squared() else pygame.Vector2(1, 0)
        side = facing.rotate(90)
        armor = self.player.equipment["armor"]
        weapon = self.player.equipment["weapon"]
        charm = self.player.equipment["charm"]
        shadow = pygame.Rect(p.x - 24, p.y + 12, 48, 16)
        pygame.draw.ellipse(self.screen, (15, 15, 18), shadow)
        stride = math.sin(pygame.time.get_ticks() * 0.012) * (2 if self.player.roll_time else 6)
        pygame.draw.line(self.screen, (54, 52, 57), p - side * 8, p - side * 10 - facing * (16 + stride), 8)
        pygame.draw.line(self.screen, (54, 52, 57), p + side * 8, p + side * 10 - facing * (16 - stride), 8)
        pygame.draw.circle(self.screen, (111, 105, 101), p - side * 10 - facing * (17 + stride), 5)
        pygame.draw.circle(self.screen, (111, 105, 101), p + side * 10 - facing * (17 - stride), 5)
        cape = p - facing * 15
        pygame.draw.polygon(self.screen, (48, 35, 43), [
            cape - side * 15, cape + side * 15, cape - facing * 23,
        ])
        armor_color = (235, 235, 240) if self.player.flash else armor.color
        body = [p + facing * 16, p + side * 18, p - facing * 17, p - side * 18]
        pygame.draw.polygon(self.screen, (24, 25, 30), [point + (3, 4) for point in body])
        pygame.draw.polygon(self.screen, armor_color, body)
        pygame.draw.polygon(self.screen, (205, 204, 194), body, 3)
        # Plate bands become more elaborate as armor power rises.
        for offset in range(-8, 10, 8):
            width = 11 + min(6, armor.power // 3)
            pygame.draw.line(self.screen, (67, 68, 73), p + facing * offset - side * width, p + facing * offset + side * width, 2)
        helmet = p + facing * 8
        pygame.draw.circle(self.screen, (125, 130, 137), helmet, 11)
        pygame.draw.line(self.screen, (35, 38, 44), helmet - side * 8, helmet + side * 8, 3)
        if armor.power >= 6:
            crest = helmet - facing * 11
            pygame.draw.polygon(self.screen, armor.color, [
                crest - side * 3, crest - facing * 14, crest + side * 7,
            ])
        off_hand = p - side * 19
        shield_size = 9 + min(7, armor.power // 3)
        pygame.draw.circle(self.screen, (45, 51, 58), off_hand, shield_size)
        pygame.draw.circle(self.screen, armor.color, off_hand, shield_size, 3)
        pygame.draw.line(self.screen, armor.color, off_hand - side * (shield_size - 3), off_hand + side * (shield_size - 3), 2)
        # Sword length and glow directly reflect the equipped weapon.
        hand = p + side * 17 + facing * 3
        sword_length = 30 + min(18, weapon.power)
        sword_end = hand + facing * (sword_length + (12 if self.player.attack_time else 0))
        pygame.draw.line(self.screen, (74, 48, 31), hand - facing * 10, hand, 7)
        pygame.draw.line(self.screen, GOLD, hand - side * 7, hand + side * 7, 4)
        pygame.draw.line(self.screen, weapon.color, hand, sword_end, 8)
        pygame.draw.line(self.screen, (235, 235, 225), hand + side * 1, sword_end + side * 1, 3)
        pygame.draw.polygon(self.screen, (240, 238, 222), [
            sword_end + facing * 7, sword_end + side * 4, sword_end - side * 4,
        ])
        pygame.draw.circle(self.screen, charm.color, p - side * 14, 4 + min(3, charm.power // 5))
        if self.player.attack_time:
            facing_angle = math.atan2(facing.y, facing.x)
            box = pygame.Rect(p.x - 74, p.y - 74, 148, 148)
            pygame.draw.arc(self.screen, weapon.color, box, facing_angle - 0.9, facing_angle + 0.9, 5)

    def draw_loot(self, drop: Loot, camera: pygame.Vector2) -> None:
        y = math.sin(pygame.time.get_ticks() / 250 + drop.phase) * 5
        p = drop.pos - camera + pygame.Vector2(0, y)
        glow = pygame.Surface((70, 70), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*drop.item.color, 38), (35, 35), 31)
        self.screen.blit(glow, p - pygame.Vector2(35, 35))
        pygame.draw.line(self.screen, drop.item.color, p + (0, 13), p + (0, 37), 4)
        if drop.item.slot == "weapon":
            pygame.draw.line(self.screen, (76, 48, 31), p + (-9, 12), p + (-3, 5), 6)
            pygame.draw.line(self.screen, drop.item.color, p + (-3, 5), p + (12, -14), 7)
            pygame.draw.polygon(self.screen, PARCHMENT, [p + (16, -20), p + (7, -13), p + (13, -9)])
            pygame.draw.line(self.screen, GOLD, p + (-10, 3), p + (4, 14), 4)
        elif drop.item.slot == "armor":
            pygame.draw.polygon(self.screen, drop.item.color, [
                p + (-16, -11), p + (-7, -17), p + (0, -11), p + (7, -17),
                p + (16, -11), p + (12, 15), p + (-12, 15),
            ])
            pygame.draw.line(self.screen, PARCHMENT, p + (-10, 2), p + (10, 2), 2)
            pygame.draw.polygon(self.screen, PARCHMENT, [
                p + (-16, -11), p + (-7, -17), p + (0, -11), p + (7, -17),
                p + (16, -11), p + (12, 15), p + (-12, 15),
            ], 2)
        else:
            pygame.draw.circle(self.screen, drop.item.color, p, 13, 6)
            pygame.draw.circle(self.screen, PARCHMENT, p, 13, 2)
            pygame.draw.circle(self.screen, (22, 22, 27), p, 5)

    def bar(self, rect: pygame.Rect, ratio: float, color: tuple[int, int, int]) -> None:
        pygame.draw.rect(self.screen, (17, 18, 22), rect)
        inner = rect.inflate(-4, -4)
        pygame.draw.rect(self.screen, color, (inner.x, inner.y, inner.w * clamp(ratio, 0, 1), inner.h))
        pygame.draw.rect(self.screen, (115, 112, 108), rect, 1)

    def text(self, text: str, pos, color=PARCHMENT, font=None, anchor="topleft") -> pygame.Rect:
        surface = (font or self.font).render(text, True, color)
        rect = surface.get_rect()
        setattr(rect, anchor, pos)
        self.screen.blit(surface, rect)
        return rect

    def draw_hud(self) -> None:
        panel = pygame.Surface((390, 130), pygame.SRCALPHA)
        panel.fill((10, 11, 15, 210))
        self.screen.blit(panel, (18, 17))
        self.text(f"LV {self.player.level}   DESCENT {self.player.depth}   {self.theme['name']}", (34, 28), self.theme["accent"], self.small)
        self.bar(pygame.Rect(34, 52, 340, 18), self.player.hp / self.player.max_hp, RED)
        self.bar(pygame.Rect(34, 76, 300, 13), self.player.stamina / self.player.max_stamina, GREEN)
        self.bar(pygame.Rect(34, 96, 250, 10), self.player.xp / self.player.xp_next, CYAN)
        self.text(f"{int(self.player.hp)}/{int(self.player.max_hp)}", (380, 61), PARCHMENT, self.small, "midright")
        self.text(f"Souls {self.player.souls}    Flasks {self.player.flasks}", (34, 116), PARCHMENT, self.small)

        objective = "Slay the Hollow King" if self.boss_spawned else f"Wardens slain: {self.kills}/8"
        self.text(objective, (WIDTH - 28, 28), GOLD if self.boss_spawned else PARCHMENT, self.font, "topright")
        weapon = self.player.equipment["weapon"]
        armor = self.player.equipment["armor"]
        self.text(f"{weapon.name} +{weapon.power}", (WIDTH - 28, 56), weapon.color, self.small, "topright")
        self.text(f"{armor.name} +{armor.power}", (WIDTH - 28, 76), armor.color, self.small, "topright")

        if self.boss_spawned:
            boss = next((e for e in self.enemies if e.kind == "boss"), None)
            if boss:
                self.text("THE HOLLOW KING", (WIDTH // 2, HEIGHT - 65), PARCHMENT, self.small, "center")
                self.bar(pygame.Rect(WIDTH // 2 - 300, HEIGHT - 48, 600, 16), boss.hp / boss.max_hp, RED)

        nearby = next((drop for drop in self.loot if self.player.pos.distance_to(drop.pos) < 64), None)
        if nearby:
            self.text(f"[E] Take {nearby.item.name}  +{nearby.item.power}", (WIDTH // 2, HEIGHT - 105), nearby.item.color, self.font, "center")
        if self.victory:
            self.text("DUNGEON CONQUERED", (WIDTH // 2, 90), GOLD, self.big_font, "center")
            self.text("Press N to descend into a stronger dungeon", (WIDTH // 2, 132), PARCHMENT, self.font, "center")

        y = 165
        for message, color, life in reversed(self.notices[-4:]):
            alpha_color = tuple(int(c * min(1, life)) for c in color)
            self.text(message, (34, y), alpha_color, self.small)
            y += 23
        self.text("Move WASD  •  Attack F/J  •  Dodge Space  •  Flask H  •  Skills Q/R", (WIDTH // 2, HEIGHT - 18), (135, 135, 142), self.small, "midbottom")

    def draw_menu(self) -> None:
        self.screen.fill((13, 14, 18))
        for i in range(90):
            x = (i * 149) % WIDTH
            y = (i * 83 + pygame.time.get_ticks() // (25 + i % 8)) % HEIGHT
            pygame.draw.circle(self.screen, (54, 35, 30), (x, y), 1 + i % 3)
        self.text("ASHEN REALMS", (WIDTH // 2, 150), PARCHMENT, self.title_font, "center")
        self.text("A PYTHON SOULSLIKE", (WIDTH // 2, 205), GOLD, self.small, "center")
        pygame.draw.line(self.screen, GOLD, (WIDTH // 2 - 210, 235), (WIDTH // 2 + 210, 235), 1)
        self.text("ENTER  Character profiles", (WIDTH // 2, 325), PARCHMENT, self.font, "center")
        self.text("S  Settings", (WIDTH // 2, 366), PARCHMENT, self.font, "center")
        self.text("ESC  Leave the realm", (WIDTH // 2, 407), (150, 150, 156), self.font, "center")
        self.text("Defeat wardens • Face the boss • Claim stronger relics • Descend again", (WIDTH // 2, 535), (145, 145, 150), self.small, "center")
        self.text("All visuals are procedurally drawn at runtime — no external assets", (WIDTH // 2, 565), (105, 105, 112), self.small, "center")

    def draw_profiles(self) -> None:
        self.screen.fill((13, 14, 18))
        self.text("CHOOSE YOUR WANDERER", (WIDTH // 2, 105), PARCHMENT, self.big_font, "center")
        self.text("Each profile has independent equipment, levels and dungeon progress", (WIDTH // 2, 150), (145, 145, 152), self.small, "center")
        for slot in range(1, 4):
            rect = pygame.Rect(WIDTH // 2 - 350, 200 + (slot - 1) * 120, 700, 88)
            pygame.draw.rect(self.screen, (26, 28, 34), rect)
            pygame.draw.rect(self.screen, GOLD if self.profile_path(slot).exists() else (76, 76, 82), rect, 2)
            self.text(str(slot), (rect.x + 28, rect.centery), GOLD, self.big_font, "midleft")
            self.text(self.profile_summary(slot), (rect.x + 88, rect.centery), PARCHMENT, self.font, "midleft")
        self.text("Press 1, 2 or 3 to play/create  •  ESC back", (WIDTH // 2, 610), (155, 155, 162), self.small, "center")

    def draw_naming(self) -> None:
        self.screen.fill((13, 14, 18))
        self.text(f"CREATE PROFILE {self.active_profile}", (WIDTH // 2, 190), GOLD, self.big_font, "center")
        self.text("Name your wanderer", (WIDTH // 2, 250), PARCHMENT, self.font, "center")
        rect = pygame.Rect(WIDTH // 2 - 240, 300, 480, 64)
        pygame.draw.rect(self.screen, (27, 29, 35), rect)
        pygame.draw.rect(self.screen, (155, 151, 142), rect, 2)
        cursor = "_" if pygame.time.get_ticks() // 450 % 2 else ""
        self.text(self.name_buffer + cursor, rect.center, PARCHMENT, self.big_font, "center")
        self.text("Type a name and press ENTER  •  ESC cancel", (WIDTH // 2, 405), (145, 145, 152), self.small, "center")

    def draw_settings(self) -> None:
        self.screen.fill((13, 14, 18))
        self.text("SETTINGS", (WIDTH // 2, 155), PARCHMENT, self.big_font, "center")
        shake = "ON" if self.settings["screen_shake"] else "OFF"
        self.text(f"1  Screen shake:  {shake}", (WIDTH // 2, 285), GOLD, self.font, "center")
        self.text(f"2  Difficulty:  {self.settings['difficulty']}", (WIDTH // 2, 335), GOLD, self.font, "center")
        self.text("Story 75%  •  Normal 100%  •  Brutal 135% enemy power", (WIDTH // 2, 385), (135, 135, 142), self.small, "center")
        self.text("ESC save and return", (WIDTH // 2, 500), PARCHMENT, self.small, "center")

    def draw(self) -> None:
        if self.state == "menu":
            self.draw_menu()
            pygame.display.flip()
            return
        if self.state == "profiles":
            self.draw_profiles()
            pygame.display.flip()
            return
        if self.state == "naming":
            self.draw_naming()
            pygame.display.flip()
            return
        if self.state == "settings":
            self.draw_settings()
            pygame.display.flip()
            return
        jitter = pygame.Vector2(random.uniform(-self.shake, self.shake), random.uniform(-self.shake, self.shake))
        camera = self.camera + jitter
        self.draw_floor(camera)
        for drop in self.loot:
            self.draw_loot(drop, camera)
        for enemy in self.enemies:
            self.draw_enemy(enemy, camera)
        for projectile in self.projectiles:
            projectile.draw(self.screen, camera)
        self.draw_player(camera)
        for particle in self.particles:
            particle.draw(self.screen, camera)
        for floating in self.damage_texts:
            self.text(floating.text, floating.pos - camera, floating.color, self.small, "center")
        self.draw_hud()
        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)
            for event in pygame.event.get():
                self.handle_event(event)
            if self.state == "playing":
                self.update(dt)
            self.draw()
        if self.profile_name:
            self.save()
        self.save_settings()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
