"""
kyros/character.py
Base Character class. All living entities in Kyros inherit from this.
Subclasses: Enlightened, NotEnlightened, Monster
Player and NPC inherit from those.
"""

from __future__ import annotations
import time
import random
import math
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STAT_GEAR_CAP        = 0.20   # gear cannot contribute more than 20% of base stat
STAT_ELIXIR_CAP      = 0.15   # elixirs cannot contribute more than 15% of base stat
STR_MULT             = 1.1    # damage formula multiplier
CON_MULT             = 0.6    # defense formula multiplier
CRIT_BASE            = 0.3    # crit% per point of dexterity
DODGE_BASE           = 0.2    # dodge% per point of dexterity
CRIT_MULT            = 1.5    # damage multiplier on crit
SNEAK_BONUS_MULT     = 1.5    # bonus damage multiplier on successful sneak attack
MANA_REGEN_INTERVAL  = 60     # real seconds between mana regen ticks

# Evolution level thresholds — same for class, profession, race
EVOLUTION_THRESHOLDS = [0, 10, 25, 50, 100, 200, 350, 550, 800, 1100, 1500, 2000]
GRADE_NAMES          = ["G", "F", "E", "D", "C", "B", "A", "S",
                         "God", "Godking", "Primordial"]
GRADE_MAX_LEVELS     = [9, 24, 49, 99, 199, 349, 549, 799, 1099, 1499, 1999, 99999]

# Rarity tiers
RARITY_TIERS = ["trash", "common", "uncommon", "rare", "epic",
                "legendary", "mythic", "divine"]

# Blessing levels
BLESSING_LEVELS = ["lesser", "minor", "greater", "major", "divine", "true"]


# ─────────────────────────────────────────────────────────────────────────────
#  STATS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Stats:
    """
    The eight core stats shared by all characters.
    base    : permanent base value from leveling/race/class
    gear    : bonus from equipped gear (capped at 20% of base)
    elixir  : permanent bonus from elixirs (capped at 15% of base)
    """
    strength:     float = 5.0
    constitution: float = 2.0
    dexterity:    float = 3.0
    agility:      float = 3.0
    intelligence: float = 3.0
    wisdom:       float = 3.0
    perception:   float = 3.0
    charisma:     float = 3.0

    # Gear and elixir bonuses tracked separately for cap enforcement
    _gear:   dict = field(default_factory=lambda: {s: 0.0 for s in
                          ["strength","constitution","dexterity","agility",
                           "intelligence","wisdom","perception","charisma"]})
    _elixir: dict = field(default_factory=lambda: {s: 0.0 for s in
                          ["strength","constitution","dexterity","agility",
                           "intelligence","wisdom","perception","charisma"]})

    def effective(self, stat: str) -> float:
        """
        Return the effective stat value after applying gear and elixir bonuses,
        enforcing caps. Gear: max 20% of base. Elixir: max 15% of base.
        """
        base        = getattr(self, stat, 0.0)
        gear_bonus  = min(self._gear.get(stat, 0.0),   base * STAT_GEAR_CAP)
        elixir_bonus= min(self._elixir.get(stat, 0.0), base * STAT_ELIXIR_CAP)
        return base + gear_bonus + elixir_bonus

    def add_gear_bonus(self, stat: str, amount: float) -> float:
        """
        Add a gear bonus. Returns actual amount applied after cap.
        Excess is silently dropped — item is still equipped.
        """
        base     = getattr(self, stat, 0.0)
        cap      = base * STAT_GEAR_CAP
        current  = self._gear.get(stat, 0.0)
        allowed  = max(0.0, cap - current)
        applied  = min(amount, allowed)
        self._gear[stat] = current + applied
        return applied

    def remove_gear_bonus(self, stat: str, amount: float) -> None:
        self._gear[stat] = max(0.0, self._gear.get(stat, 0.0) - amount)

    def add_elixir_bonus(self, stat: str, amount: float) -> float:
        """Permanent elixir bonus, capped at 15% of base."""
        base     = getattr(self, stat, 0.0)
        cap      = base * STAT_ELIXIR_CAP
        current  = self._elixir.get(stat, 0.0)
        allowed  = max(0.0, cap - current)
        applied  = min(amount, allowed)
        self._elixir[stat] = current + applied
        return applied

    def apply_free_points(self, allocations: dict[str, float]) -> None:
        """Apply manually allocated free stat points."""
        for stat, amount in allocations.items():
            if hasattr(self, stat):
                setattr(self, stat, getattr(self, stat) + amount)


# ─────────────────────────────────────────────────────────────────────────────
#  RESISTANCE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Resistances:
    """
    Percentage resistances per damage type.
    Negative values mean extra damage taken from that source.
    """
    physical: float = 0.0
    fire:     float = 0.0
    ice:      float = 0.0
    lightning:float = 0.0
    poison:   float = 0.0
    magic:    float = 0.0
    holy:     float = 0.0
    dark:     float = 0.0

    def modifier(self, damage_type: str) -> float:
        """Returns damage multiplier. 0% resistance = 1.0x, 50% = 0.5x, -50% = 1.5x."""
        resistance = getattr(self, damage_type, 0.0)
        return 1.0 - (resistance / 100.0)


# ─────────────────────────────────────────────────────────────────────────────
#  SKILL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Skill:
    """A single skill gained from class, profession, or race."""
    name:         str
    description:  str
    rarity:       str          # from RARITY_TIERS
    skill_type:   str          # "active" | "passive" | "racial" | "combat" | "noncombat"
    source:       str          # class/profession/race name
    level:        int  = 1
    comprehension:float= 0.0   # 0–100, auto-upgrades at thresholds
    is_active:    bool = True
    cooldown:     float= 0.0   # seconds
    last_used:    float= 0.0

    def can_upgrade(self) -> bool:
        return self.comprehension >= 100.0 * self.level

    def upgrade(self) -> bool:
        if self.can_upgrade():
            self.level += 1
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  TITLE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Title:
    """
    A title earned by a character. Can grant stat bonuses,
    free points, or a new skill. Cannot be lost once earned.
    Title stat bonuses do NOT count toward gear or elixir caps.
    """
    name:         str
    description:  str
    rarity:       str                      # from RARITY_TIERS
    stat_bonuses: dict[str, float] = field(default_factory=dict)
    free_points:  int              = 0
    skill:        Optional[Skill]  = None
    granted_at:   float            = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  BLESSING
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Blessing:
    """
    A divine blessing from a primordial god.
    Only one blessing at a time. Can be lost (except if Chosen).
    True blessing grants one non-combat skill chosen by the god.
    """
    god_name:     str
    level:        str              # from BLESSING_LEVELS
    description:  str
    unlocks:      list[str] = field(default_factory=list)  # classes/races/professions unlocked
    skill:        Optional[Skill] = None                    # true blessing only
    is_chosen:    bool = False     # chosen cannot lose blessing
    granted_at:   float= field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  EVOLUTION TRACK
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EvolutionTrack:
    """
    Tracks level, grade, and evolution state for class, profession, or race.
    Levels do not reset between tiers.
    """
    name:              str
    grade_index:       int   = 0      # index into GRADE_NAMES
    level:             int   = 0
    xp:                float = 0.0
    evolution_quest_active:   bool  = False
    evolution_quest_complete: bool  = False
    failed_attempt:    bool  = False
    failed_at:         float = 0.0    # real time of failed attempt
    free_points:       int   = 0      # unspent free points

    @property
    def grade(self) -> str:
        return GRADE_NAMES[min(self.grade_index, len(GRADE_NAMES)-1)]

    @property
    def next_evolution_level(self) -> int:
        idx = self.grade_index + 1
        if idx >= len(EVOLUTION_THRESHOLDS):
            return 999999
        return EVOLUTION_THRESHOLDS[idx]

    @property
    def grade_max_level(self) -> int:
        return GRADE_MAX_LEVELS[min(self.grade_index, len(GRADE_MAX_LEVELS)-1)]

    @property
    def pct_to_evolution(self) -> float:
        """Percentage progress toward next evolution threshold."""
        current_threshold = EVOLUTION_THRESHOLDS[self.grade_index]
        next_threshold    = self.next_evolution_level
        if next_threshold <= current_threshold:
            return 100.0
        progress = self.level - current_threshold
        span     = next_threshold - current_threshold
        return min(100.0, (progress / span) * 100.0)

    @property
    def is_at_grade_max(self) -> bool:
        return self.level >= self.grade_max_level

    @property
    def can_attempt_evolution(self) -> bool:
        """Can attempt if quest complete and retry cooldown passed (1 NPC year = real time)."""
        if not self.evolution_quest_complete:
            return False
        if self.failed_attempt:
            # 1 NPC year = 365 NPC days = 365 * 24 * 60 real seconds
            cooldown = 365 * 24 * 60
            return (time.time() - self.failed_at) >= cooldown
        return True

    def add_xp(self, amount: float) -> list[str]:
        """
        Add XP. Returns list of notification strings for level ups.
        XP required per level scales exponentially at higher tiers.
        """
        notifications = []
        self.xp += amount
        while True:
            xp_needed = self._xp_for_next_level()
            if self.xp >= xp_needed and self.level < self.grade_max_level:
                self.xp      -= xp_needed
                self.level   += 1
                notifications.append(
                    f"{self.name} ({self.grade}) reached Level {self.level}!"
                )
            else:
                break
        return notifications

    def _xp_for_next_level(self) -> float:
        """
        XP required scales with level and grade.
        Higher grades require exponentially more XP.
        At G grade level 1: ~100 XP. At C grade level 200: ~millions.
        """
        grade_multiplier = 1.5 ** self.grade_index
        level_multiplier = 1.0 + (self.level * 0.05)
        return 100.0 * grade_multiplier * level_multiplier


# ─────────────────────────────────────────────────────────────────────────────
#  BUFF
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Buff:
    """A temporary stat or combat modifier."""
    name:       str
    stat:       str          # which stat is affected, or "special"
    modifier:   float        # flat bonus or multiplier
    is_pct:     bool = False # True = percentage modifier
    duration:   float= 0.0   # real seconds, 0 = permanent until removed
    applied_at: float= field(default_factory=time.time)
    source:     str  = ""

    @property
    def is_expired(self) -> bool:
        if self.duration <= 0:
            return False
        return (time.time() - self.applied_at) >= self.duration


# ─────────────────────────────────────────────────────────────────────────────
#  CHARACTER BASE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Character:
    """
    Base class for all living entities in Kyros.
    Handles: stats, combat, XP/leveling, health/mana, death,
             resistances, buffs, skills, titles, blessings.

    Subclasses:
        Enlightened  — humans, elves, dwarves and humanoid sentients
        NotEnlightened — vampires, werewolves, sentient non-humanoids
        Monster      — non-sentient creatures (slimes, wolves, etc.)
    """

    def __init__(
        self,
        name:        str,
        race:        str,
        is_player:   bool = False,
    ):
        self.name      = name
        self.race      = race
        self.is_player = is_player

        # Core stats
        self.stats       = Stats()
        self.resistances = Resistances()

        # Derived stats — computed from stats
        self._base_max_health: float = 50.0
        self._base_max_mana:   float = 30.0
        self.health:           float = self.max_health
        self.mana:             float = self.max_mana
        self.gold:             float = 0.0

        # XP and leveling
        self.xp:               float = 0.0
        self.level:            int   = 0
        self._last_regen_time: float = time.time()

        # Combat state
        self.buffs:            list[Buff]    = []
        self.in_combat:        bool          = False
        self.is_dead:          bool          = False
        self.heretic:          bool          = False

        # Skills, titles, blessings
        self.skills:           list[Skill]   = []
        self.titles:           list[Title]   = []
        self.blessing:         Optional[Blessing] = None

        # Sneak attack tracking
        self._sneak_target:    Optional[str] = None


    # ─────────────────────────────────────────────────────────────────────
    #  DERIVED STATS
    # ─────────────────────────────────────────────────────────────────────

    @property
    def max_health(self) -> float:
        """Constitution drives max health. Each point of constitution = +10 HP."""
        con   = self.stats.effective("constitution")
        bonus = sum(t.stat_bonuses.get("max_health", 0) for t in self.titles)
        buff_bonus = sum(b.modifier for b in self.buffs
                        if b.stat == "max_health" and not b.is_expired)
        return max(1.0, self._base_max_health + (con * 10.0) + bonus + buff_bonus)

    @property
    def max_mana(self) -> float:
        """Intelligence drives max mana. Each point = +5 mana."""
        intel = self.stats.effective("intelligence")
        bonus = sum(t.stat_bonuses.get("max_mana", 0) for t in self.titles)
        buff_bonus = sum(b.modifier for b in self.buffs
                        if b.stat == "max_mana" and not b.is_expired)
        return max(1.0, self._base_max_mana + (intel * 5.0) + bonus + buff_bonus)

    @property
    def attack_power(self) -> float:
        """Strength drives attack power."""
        str_  = self.stats.effective("strength")
        bonus = sum(t.stat_bonuses.get("attack_power", 0) for t in self.titles)
        buff_bonus = sum(b.modifier for b in self.buffs
                        if b.stat == "attack_power" and not b.is_expired)
        return max(1.0, (str_ * STR_MULT) + bonus + buff_bonus)

    @property
    def defense(self) -> float:
        """Constitution drives defense."""
        con   = self.stats.effective("constitution")
        bonus = sum(t.stat_bonuses.get("defense", 0) for t in self.titles)
        buff_bonus = sum(b.modifier for b in self.buffs
                        if b.stat == "defense" and not b.is_expired)
        return max(0.0, (con * CON_MULT) + bonus + buff_bonus)

    @property
    def crit_chance(self) -> float:
        """
        Dexterity drives crit chance. Accelerates at higher dex values.
        Formula: base_rate * (1 + dex^1.2 * 0.001)
        Keeps low at early levels but meaningfully scales with investment.
        """
        dex  = self.stats.effective("dexterity")
        rate = CRIT_BASE * dex * (1.0 + (dex ** 1.2) * 0.001)
        return min(75.0, rate)   # soft cap at 75%

    @property
    def dodge_chance(self) -> float:
        """
        Dexterity drives dodge chance. Same accelerating formula as crit.
        """
        dex  = self.stats.effective("dexterity")
        rate = DODGE_BASE * dex * (1.0 + (dex ** 1.2) * 0.001)
        return min(60.0, rate)   # soft cap at 60%

    @property
    def speed(self) -> float:
        """Agility drives turn order. Higher = attacks first."""
        return self.stats.effective("agility")

    @property
    def mana_regen_rate(self) -> float:
        """
        Wisdom drives mana regen per tick (60 real seconds).
        At high max_mana, regen slows so full regen takes ~1 hour minimum.
        Formula: max(1, (max_mana * base_rate) + wisdom_bonus)
        base_rate shrinks as max_mana grows.
        """
        wis       = self.stats.effective("wisdom")
        base_rate = max(0.001, 0.1 / (1.0 + self.max_mana * 0.0001))
        wis_bonus = wis * 0.00005 * self.max_mana
        return max(1.0, (self.max_mana * base_rate) + wis_bonus)


    # ─────────────────────────────────────────────────────────────────────
    #  COMBAT
    # ─────────────────────────────────────────────────────────────────────

    def calculate_attack(
        self,
        target:       "Character",
        damage_type:  str  = "physical",
        is_sneak:     bool = False,
    ) -> tuple[float, bool, bool]:
        """
        Calculate attack against target.

        Returns (damage_dealt, is_crit, is_dodged).

        Sneak attack: bonus damage if target perception check fails.
        Dodge is lowered if attacker has higher agility than target.
        """
        # Clean expired buffs first
        self.buffs  = [b for b in self.buffs  if not b.is_expired]
        target.buffs= [b for b in target.buffs if not b.is_expired]

        # Dodge calculation — lowered by attacker agility vs target agility
        agility_diff    = max(0.0, self.speed - target.speed)
        dodge_reduction = agility_diff * 0.1   # each point of agility advantage = -0.1% dodge
        effective_dodge = max(0.0, target.dodge_chance - dodge_reduction)
        is_dodged       = random.random() < (effective_dodge / 100.0)

        if is_dodged:
            return 0.0, False, True

        # Sneak attack — target perception vs attacker agility
        if is_sneak:
            perception_check = target.stats.effective("perception")
            sneak_difficulty = self.speed * 0.5
            sneak_succeeds   = perception_check < sneak_difficulty
        else:
            sneak_succeeds = False

        # Base damage
        raw    = max(1.0, self.attack_power - target.defense)
        is_crit= random.random() < (self.crit_chance / 100.0)

        if is_crit:
            raw *= CRIT_MULT
        if sneak_succeeds:
            raw *= SNEAK_BONUS_MULT

        # Resistance modifier
        res_mod = target.resistances.modifier(damage_type)
        damage  = max(1.0, raw * res_mod)

        return damage, is_crit, False

    def take_damage(self, amount: float) -> tuple[float, bool]:
        """
        Apply damage. Returns (actual_damage, is_dead).
        """
        actual      = min(self.health, amount)
        self.health = max(0.0, self.health - actual)
        if self.health <= 0:
            self.on_death()
            return actual, True
        return actual, False

    def heal(self, amount: float) -> float:
        """Heal up to max_health. Returns actual amount healed."""
        before      = self.health
        self.health = min(self.max_health, self.health + amount)
        return self.health - before

    def restore_mana(self, amount: float) -> float:
        """Restore mana up to max_mana. Returns actual amount restored."""
        before    = self.mana
        self.mana = min(self.max_mana, self.mana + amount)
        return self.mana - before

    def regen_tick(self) -> list[str]:
        """
        Called every MANA_REGEN_INTERVAL real seconds.
        Regenerates mana based on Wisdom formula.
        Returns list of notification strings.
        """
        now      = time.time()
        elapsed  = now - self._last_regen_time
        ticks    = int(elapsed / MANA_REGEN_INTERVAL)
        if ticks < 1:
            return []

        self._last_regen_time += ticks * MANA_REGEN_INTERVAL
        notifications = []

        for _ in range(ticks):
            if self.mana < self.max_mana:
                gained = self.restore_mana(self.mana_regen_rate)
                if self.is_player and gained > 0:
                    notifications.append(
                        f"Mana regenerated: +{gained:.0f} ({self.mana:.0f}/{self.max_mana:.0f})"
                    )

        return notifications

    def on_death(self) -> None:
        """Called when health reaches 0. Base implementation — overridden by subclasses."""
        self.is_dead = True


    # ─────────────────────────────────────────────────────────────────────
    #  XP AND LEVELING
    # ─────────────────────────────────────────────────────────────────────

    def gain_xp(self, amount: float) -> list[str]:
        """
        Award XP. Returns list of notification strings.
        Notifications are always shown to player.
        Only player sees gold gain messages — enforced in earn_gold.
        """
        self.xp   += amount
        notifications = [f"+{amount:.0f} XP"]
        threshold = self._xp_for_next_level()

        while self.xp >= threshold:
            self.xp     -= threshold
            self.level  += 1
            notifications.append(f"Level Up! You are now Level {self.level}!")
            self._on_level_up(notifications)
            threshold = self._xp_for_next_level()

        return notifications

    def _xp_for_next_level(self) -> float:
        """XP required for next level. Scales with level."""
        return 100.0 * (1.0 + self.level * 0.1) ** 1.5

    def _on_level_up(self, notifications: list[str]) -> None:
        """
        Called on each level up. Subclasses extend this
        to handle class/profession/race skill unlocks.
        """
        # Auto-upgrade skills that have reached comprehension threshold
        upgraded = []
        for skill in self.skills:
            if skill.can_upgrade():
                skill.upgrade()
                upgraded.append(skill.name)
        if upgraded:
            notifications.append(f"Skills upgraded: {', '.join(upgraded)}")


    # ─────────────────────────────────────────────────────────────────────
    #  GOLD
    # ─────────────────────────────────────────────────────────────────────

    def earn_gold(self, amount: float, silent: bool = False) -> None:
        """
        Add gold. Only player sees the + X Gold message.
        """
        self.gold += amount
        if self.is_player and not silent:
            print(f" + {amount:.0f} Gold")

    def spend_gold(self, amount: float) -> bool:
        """
        Deduct gold. Returns False if insufficient funds.
        """
        if self.gold < amount:
            return False
        self.gold -= amount
        if self.is_player:
            print(f" - {amount:.0f} Gold")
        return True


    # ─────────────────────────────────────────────────────────────────────
    #  BUFFS
    # ─────────────────────────────────────────────────────────────────────

    def add_buff(self, buff: Buff) -> None:
        self.buffs = [b for b in self.buffs if not b.is_expired]
        self.buffs.append(buff)

    def remove_buff(self, buff_name: str) -> None:
        self.buffs = [b for b in self.buffs if b.name != buff_name]

    def get_active_buffs(self) -> list[Buff]:
        self.buffs = [b for b in self.buffs if not b.is_expired]
        return self.buffs


    # ─────────────────────────────────────────────────────────────────────
    #  SKILLS
    # ─────────────────────────────────────────────────────────────────────

    def add_skill(self, skill: Skill) -> None:
        self.skills.append(skill)

    def get_skill(self, name: str) -> Optional[Skill]:
        for s in self.skills:
            if s.name.lower() == name.lower():
                return s
        return None

    def use_skill(self, name: str) -> Optional[str]:
        """
        Attempt to use an active skill.
        Returns description of effect or None if unavailable.
        """
        skill = self.get_skill(name)
        if not skill or not skill.is_active:
            return None
        if skill.skill_type == "passive":
            return f"{skill.name} is a passive skill."
        now = time.time()
        if (now - skill.last_used) < skill.cooldown:
            remaining = skill.cooldown - (now - skill.last_used)
            return f"{skill.name} is on cooldown ({remaining:.0f}s remaining)."
        skill.last_used = now
        return f"Used {skill.name}: {skill.description}"


    # ─────────────────────────────────────────────────────────────────────
    #  TITLES
    # ─────────────────────────────────────────────────────────────────────

    def add_title(self, title: Title) -> list[str]:
        """
        Add a title. Applies stat bonuses immediately.
        Stat bonuses from titles do not count toward any caps.
        Returns notification strings.
        """
        self.titles.append(title)
        notifications = [f"Title earned: [{title.name}] ({title.rarity})"]
        if title.stat_bonuses:
            for stat, bonus in title.stat_bonuses.items():
                notifications.append(f"  {stat} +{bonus}")
        if title.free_points > 0:
            notifications.append(f"  +{title.free_points} free stat points")
        if title.skill:
            self.add_skill(title.skill)
            notifications.append(f"  New skill: {title.skill.name}")
        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  BLESSINGS
    # ─────────────────────────────────────────────────────────────────────

    def receive_blessing(self, blessing: Blessing) -> list[str]:
        """
        Receive a divine blessing. Replaces current blessing unless Chosen.
        """
        notifications = []
        if self.blessing and self.blessing.is_chosen:
            notifications.append("Your blessing cannot be replaced — you are Chosen.")
            return notifications
        self.blessing = blessing
        notifications.append(
            f"Blessed by {blessing.god_name}: {blessing.level} blessing received!"
        )
        if blessing.skill:
            self.add_skill(blessing.skill)
            notifications.append(f"  Divine skill granted: {blessing.skill.name}")
        if blessing.unlocks:
            notifications.append(f"  Unlocked: {', '.join(blessing.unlocks)}")
        return notifications

    def lose_blessing(self) -> list[str]:
        """
        Lose current blessing (e.g. angering a god).
        Cannot lose if Chosen.
        """
        if not self.blessing:
            return []
        if self.blessing.is_chosen:
            return ["Your blessing cannot be removed — you are Chosen."]
        god = self.blessing.god_name
        self.blessing = None
        return [f"Your blessing from {god} has been revoked."]

    def set_heretic(self, value: bool) -> list[str]:
        """Mark character as heretic. Cannot be set if Chosen."""
        if self.blessing and self.blessing.is_chosen:
            return ["A Chosen cannot be branded a heretic."]
        self.heretic = value
        if value:
            return ["You have been branded a HERETIC."]
        return ["Your heretic status has been cleared."]


    # ─────────────────────────────────────────────────────────────────────
    #  IDENTIFY SKILL HELPER
    # ─────────────────────────────────────────────────────────────────────

    def get_identify_info(self, skill_rarity: str) -> dict:
        """
        Return information about this character for the Identify skill.
        Higher rarity skill reveals more — including blessings.
        """
        rarity_idx = RARITY_TIERS.index(skill_rarity) if skill_rarity in RARITY_TIERS else 0
        info = {
            "name":  self.name,
            "race":  self.race,
            "level": self.level,
        }
        if rarity_idx >= 1:   # common+
            info["health"]  = f"{self.health:.0f}/{self.max_health:.0f}"
            info["stats"]   = {s: round(self.stats.effective(s), 1)
                               for s in ["strength","constitution","dexterity",
                                         "agility","intelligence","wisdom",
                                         "perception","charisma"]}
        if rarity_idx >= 3:   # rare+
            info["titles"]  = [t.name for t in self.titles]
            info["skills"]  = [s.name for s in self.skills]
        if rarity_idx >= 5:   # legendary+
            info["blessing"]= (f"{self.blessing.god_name}: {self.blessing.level}"
                               if self.blessing else "none")
            info["heretic"] = self.heretic
        return info


    # ─────────────────────────────────────────────────────────────────────
    #  UTILITY
    # ─────────────────────────────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Snapshot of character state for NPC AI context and save system."""
        return {
            "name":         self.name,
            "race":         self.race,
            "level":        self.level,
            "health":       self.health,
            "max_health":   self.max_health,
            "mana":         self.mana,
            "max_mana":     self.max_mana,
            "gold":         self.gold,
            "attack_power": self.attack_power,
            "defense":      self.defense,
            "crit_chance":  self.crit_chance,
            "dodge_chance": self.dodge_chance,
            "speed":        self.speed,
            "stats": {
                s: round(self.stats.effective(s), 1)
                for s in ["strength","constitution","dexterity","agility",
                          "intelligence","wisdom","perception","charisma"]
            },
            "buffs":    [b.name for b in self.get_active_buffs()],
            "skills":   [s.name for s in self.skills],
            "titles":   [t.name for t in self.titles],
            "blessing": self.blessing.god_name if self.blessing else None,
            "heretic":  self.heretic,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  ENLIGHTENED SUBCLASS
# ─────────────────────────────────────────────────────────────────────────────

class Enlightened(Character):
    """
    Enlightened characters: humans, elves, dwarves, and humanoid sentients.
    Has class, profession, and full WealthState.
    Can hold one class and one optional profession simultaneously.
    """

    def __init__(self, name: str, race: str, is_player: bool = False):
        super().__init__(name, race, is_player)

        self.race_track:       EvolutionTrack            = EvolutionTrack(race)
        self.class_track:      Optional[EvolutionTrack]  = None
        self.profession_track: Optional[EvolutionTrack]  = None

        # Free stat points waiting to be allocated
        self.free_points:      int  = 0

        # Whether player has chosen their initial class (level 0 choice)
        self.class_chosen:     bool = False
        self.profession_chosen:bool = False

    @property
    def race_grade(self) -> str:
        return self.race_track.grade

    @property
    def class_grade(self) -> Optional[str]:
        return self.class_track.grade if self.class_track else None

    @property
    def profession_grade(self) -> Optional[str]:
        return self.profession_track.grade if self.profession_track else None

    def gain_xp(self, amount: float) -> list[str]:
        """
        XP feeds into class and profession tracks.
        Race level = average of class and profession levels.
        """
        notifications = super().gain_xp(amount)

        # Distribute XP to class and profession
        class_notes = []
        prof_notes  = []
        if self.class_track:
            class_notes = self.class_track.add_xp(amount)
        if self.profession_track:
            prof_notes = self.profession_track.add_xp(amount)

        # Update race level = average of class and profession
        self._sync_race_level()

        notifications.extend(class_notes)
        notifications.extend(prof_notes)
        return notifications

    def _sync_race_level(self) -> None:
        """Race level is the average of class and profession levels."""
        levels = []
        if self.class_track:
            levels.append(self.class_track.level)
        if self.profession_track:
            levels.append(self.profession_track.level)
        if levels:
            self.race_track.level = int(sum(levels) / len(levels))

    def set_class(self, class_name: str, grade_index: int = 0) -> None:
        self.class_track  = EvolutionTrack(class_name, grade_index)
        self.class_chosen = True

    def set_profession(self, profession_name: str, grade_index: int = 0) -> None:
        self.profession_track  = EvolutionTrack(profession_name, grade_index)
        self.profession_chosen = True

    def allocate_free_points(self, allocations: dict[str, float]) -> list[str]:
        """
        Spend free points on stats.
        Returns notifications of what changed.
        """
        total_requested = sum(allocations.values())
        if total_requested > self.free_points:
            return [f"Not enough free points. Have {self.free_points}, need {total_requested:.0f}."]
        self.stats.apply_free_points(allocations)
        self.free_points -= int(total_requested)
        return [f"Stats allocated: " + ", ".join(f"{s} +{v}" for s, v in allocations.items())]

    def on_death(self) -> None:
        """Enlightened NPCs die and can be removed from world."""
        super().on_death()

    def check_perfect_evolution(self) -> bool:
        """
        Perfect Evolution: all three tracks (class, race, profession)
        must be at grade max level simultaneously.
        Profession is required for perfect evolution.
        """
        if not self.profession_track:
            return False
        return (
            self.race_track.is_at_grade_max and
            (self.class_track and self.class_track.is_at_grade_max) and
            self.profession_track.is_at_grade_max
        )

    def get_perfect_evolution_bonus(self) -> int:
        """Stat bonus for perfect evolution per grade."""
        bonuses = {0: 0, 1: 100, 2: 200, 3: 400}
        grade   = self.race_track.grade_index
        return bonuses.get(grade, 400 * (grade - 2))


# ─────────────────────────────────────────────────────────────────────────────
#  NOT ENLIGHTENED SUBCLASS
# ─────────────────────────────────────────────────────────────────────────────

class NotEnlightened(Character):
    """
    Not Enlightened characters: vampires, werewolves, sentient non-humanoids.
    Has class but no profession.
    Has WealthState (same system as Enlightened).
    On race change from Enlightened: keeps one chosen attribute,
    one random attribute gets 10% XP bonus.
    """

    def __init__(self, name: str, race: str, is_player: bool = False):
        super().__init__(name, race, is_player)

        self.race_track:  EvolutionTrack           = EvolutionTrack(race)
        self.class_track: Optional[EvolutionTrack] = None
        self.free_points: int                      = 0
        self.xp_bonus_attribute: Optional[str]    = None   # 10% bonus from race change

    @property
    def race_grade(self) -> str:
        return self.race_track.grade

    def gain_xp(self, amount: float) -> list[str]:
        notifications = super().gain_xp(amount)
        bonus_amount  = amount
        if self.xp_bonus_attribute == "class" and self.class_track:
            bonus_amount = amount * 1.10
        if self.class_track:
            notifications.extend(self.class_track.add_xp(bonus_amount))
        self.race_track.level = self.class_track.level if self.class_track else 0
        return notifications

    def set_class(self, class_name: str, grade_index: int = 0) -> None:
        self.class_track = EvolutionTrack(class_name, grade_index)

    def transition_from_enlightened(
        self,
        kept_attribute: str,
        previous_class: Optional[EvolutionTrack] = None,
    ) -> list[str]:
        """
        Handle race change from Enlightened to NotEnlightened.
        kept_attribute: "class" — the one thing the character chose to keep.
        One random attribute (not necessarily the kept one) gets 10% XP bonus.
        """
        notifications = [f"{self.name} has become {self.race}!"]
        if kept_attribute == "class" and previous_class:
            self.class_track = previous_class
            notifications.append(f"Retained class: {previous_class.name}")

        # Random bonus attribute
        options = ["class", "race"]
        self.xp_bonus_attribute = random.choice(options)
        notifications.append(
            f"10% XP bonus applied to: {self.xp_bonus_attribute} (random)"
        )
        return notifications


# ─────────────────────────────────────────────────────────────────────────────
#  MONSTER SUBCLASS
# ─────────────────────────────────────────────────────────────────────────────

class Monster(Character):
    """
    Non-sentient creatures: slimes, wolves, etc.
    Combat only. No class, profession, wealth, or titles.
    Has racial skills only (more powerful than standard skills).
    """

    def __init__(
        self,
        name:          str,
        race:          str,
        loot_table:    list  = None,
        xp_reward:     float = 10.0,
        gold_reward:   float = 10.0,
        monster_type:  str   = "beast",
    ):
        super().__init__(name, race, is_player=False)
        self.loot_table  = loot_table or []
        self.xp_reward   = xp_reward
        self.gold_reward = gold_reward
        self.monster_type= monster_type

    def on_death(self) -> None:
        super().on_death()
        # Drop items handled by combat system

    def get_drops(self) -> list[tuple]:
        """
        Roll for item drops from loot table.
        Returns list of (item_name, quantity) tuples.
        """
        drops = []
        for item_name, max_qty, chance in self.loot_table:
            if random.randint(1, chance) == 1:
                qty = random.randint(1, max_qty)
                drops.append((item_name, qty))
        return drops