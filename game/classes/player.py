"""
kyros/player.py
Player class. Inherits from Enlightened (or NotEnlightened if race changes).
Handles all player-specific systems: inventory, journal, status menu,
aliases, save codes, respawn, bond pets, map notes, achievements,
reputation, wanted level, guild membership, and multiplayer state.
"""

from __future__ import annotations
import json
import os
import random
import string
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from .character import (
    Character, Enlightened, NotEnlightened, Monster,
    Stats, Resistances, Skill, Title, Blessing, Buff,
    EvolutionTrack, RARITY_TIERS, GRADE_NAMES, BLESSING_LEVELS,
    EVOLUTION_THRESHOLDS, GRADE_MAX_LEVELS,
)
from .npc_objects import (
    GossipEntry, Relationship, WealthState, Bounty,
    Sentence, ReputationEntry, Investment,
    RELATIONSHIP_TYPES, REPUTATION_TIERS,
    JAIL_MIN_FAIL, JAIL_BONUS_CAP,
)


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

DEATH_GOLD_LOSS      = 0.5        # lose 50% of gold on death
ITEM_DROP_COUNT      = 2          # items dropped from inventory on death
ITEM_DESPAWN_TIMER   = 3600       # real seconds before dropped items despawn
BOND_PET_SAPIENT_GRADE = 2        # grade index where bond pets become sapient (C = index 4, adjusted below)
BOND_SAPIENT_GRADE_IDX = 4        # C grade index in GRADE_NAMES
RESURRECT_MANA_PER_LVL= 50        # mana cost to resurrect = level * 50
PVP_DISCONNECT_WIN   = True       # disconnecting from PvP counts as a loss


# ─────────────────────────────────────────────────────────────────────────────
#  ITEM
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Item:
    """A single item instance in the game world."""
    name:       str
    rarity:     str  = "common"    # from RARITY_TIERS
    item_type:  str  = "misc"      # weapon / armor / consumable / crafting / misc / key
    stats:      dict = field(default_factory=dict)   # stat bonuses while equipped
    description:str  = ""
    quantity:   int  = 1
    equipped:   bool = False
    crafted:    bool = False       # True if player-crafted

    @property
    def rarity_index(self) -> int:
        return RARITY_TIERS.index(self.rarity) if self.rarity in RARITY_TIERS else 0


# ─────────────────────────────────────────────────────────────────────────────
#  DROPPED ITEM (death drops)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DroppedItem:
    """An item dropped at a location on death. Despawns after ITEM_DESPAWN_TIMER."""
    item:       Item
    location:   str
    dropped_at: float = field(default_factory=time.time)

    @property
    def is_despawned(self) -> bool:
        return (time.time() - self.dropped_at) >= ITEM_DESPAWN_TIMER


# ─────────────────────────────────────────────────────────────────────────────
#  JOURNAL ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JournalEntry:
    """
    A single journal entry. Metaphysical — only the player can see it.
    NPCs who encounter it think it is a physical book and forget about it
    after the investigation unless its content is linked to a crime.
    AI tags entries to NPCs/locations/items it recognizes.
    Unrecognized content is stored as free text.
    """
    text:        str
    timestamp:   float = field(default_factory=time.time)
    tags:        list[str] = field(default_factory=list)   # NPC names, locations, items
    is_free:     bool = True    # True = unstructured note; False = AI-tagged reference

    @property
    def display_timestamp(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.timestamp))


# ─────────────────────────────────────────────────────────────────────────────
#  MAP NOTE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MapNote:
    """A player annotation pinned to a map location."""
    location:  str
    text:      str
    timestamp: float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  ACHIEVEMENT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Achievement:
    """
    An achievement earned by the player.
    Some are hardcoded triggers; others are AI-granted.
    Achievements have rarity tiers.
    """
    name:        str
    description: str
    rarity:      str   = "common"
    earned_at:   float = field(default_factory=time.time)
    title:       Optional[Title] = None   # some achievements grant a title


# ─────────────────────────────────────────────────────────────────────────────
#  BOND PET
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BondPet:
    """
    A bonded animal companion. Very rare drop from animals.
    One bond at a time. At C grade becomes sapient and AI-driven.
    Has its own tier system (same G-Primordial).
    Resurrect cost: level * 50 mana (can be paid incrementally).
    """
    name:          str
    species:       str
    race_track:    EvolutionTrack = field(default_factory=lambda: EvolutionTrack("beast"))
    stats:         Stats          = field(default_factory=Stats)
    skills:        list[Skill]    = field(default_factory=list)
    health:        float          = 20.0
    max_health:    float          = 20.0
    is_dead:       bool           = False
    resurrect_mana_paid: float    = 0.0   # mana paid so far toward resurrection
    sapient:       bool           = False  # True at C grade
    npc_instance:  object         = None   # NPC instance when sapient
    sell_value:    float          = 500.0

    @property
    def resurrect_cost(self) -> float:
        return self.race_track.level * RESURRECT_MANA_PER_LVL

    @property
    def resurrect_remaining(self) -> float:
        return max(0.0, self.resurrect_cost - self.resurrect_mana_paid)

    def pay_resurrect_mana(self, amount: float) -> tuple[float, bool]:
        """
        Pay mana toward resurrection. Returns (amount_paid, is_resurrected).
        Does not have to be paid all at once.
        """
        actual = min(amount, self.resurrect_remaining)
        self.resurrect_mana_paid += actual
        if self.resurrect_mana_paid >= self.resurrect_cost:
            self.is_dead             = False
            self.health              = self.max_health
            self.resurrect_mana_paid = 0.0
            return actual, True
        return actual, False

    def check_sapience(self) -> bool:
        """Become sapient at C grade (index 4)."""
        if not self.sapient and self.race_track.grade_index >= BOND_SAPIENT_GRADE_IDX:
            self.sapient = True
        return self.sapient


# ─────────────────────────────────────────────────────────────────────────────
#  ALIAS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Alias:
    """
    A player alias used in specific circumstances.
    e.g. guild alias, criminal alias, regional alias.
    NPCs who know this alias track it separately from the true name.
    """
    alias:     str
    context:   str    # "guild", "criminal", "regional", etc.
    location:  str    # where this alias is known
    created_at:float  = field(default_factory=time.time)
    known_by:  list[str] = field(default_factory=list)   # NPC names


# ─────────────────────────────────────────────────────────────────────────────
#  RESPAWN POINT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RespawnPoint:
    """An unlocked respawn location."""
    name:      str
    location:  str
    unlocked_at: float = field(default_factory=time.time)
    is_default:  bool  = False


# ─────────────────────────────────────────────────────────────────────────────
#  SAVE CODE
# ─────────────────────────────────────────────────────────────────────────────

SAVE_CODE_SYMBOLS = (
    string.ascii_uppercase +
    string.ascii_lowercase +
    string.digits +
    "}[&#(%"
)

def generate_save_code(
    world_name:       str,
    race_tier:        str,
    class_tier:       str,
    profession_tier:  str,
    race_name:        str,
    class_name:       str,
    profession_name:  str,
) -> str:
    """
    Generate a save code in the format:
    worldname-racetier-classtier-professiontier-racename-classname-professionname-RANDOM

    Random sequence: 6 chars, must contain at least:
    - 1 uppercase letter
    - 1 lowercase letter
    - 1 digit
    - 1 symbol from }[&#(%

    Single player only — multiplayer uses server-side state.
    """
    def make_random_sequence() -> str:
        symbols  = "}[&#(%"
        required = [
            random.choice(string.ascii_uppercase),
            random.choice(string.ascii_lowercase),
            random.choice(string.digits),
            random.choice(symbols),
        ]
        remaining_pool = SAVE_CODE_SYMBOLS
        remaining      = [random.choice(remaining_pool) for _ in range(2)]
        seq = required + remaining
        random.shuffle(seq)
        return "".join(seq)

    random_seq = make_random_sequence()

    parts = [
        world_name.replace("-", "_"),
        race_tier,
        class_tier,
        profession_tier,
        race_name.replace("-", "_"),
        class_name.replace("-", "_"),
        profession_name.replace("-", "_") if profession_name else "none",
        random_seq,
    ]
    return "-".join(parts)


def validate_save_code(code: str) -> bool:
    """Basic structural validation of a save code."""
    parts = code.split("-")
    if len(parts) != 8:
        return False
    random_seq = parts[7]
    if len(random_seq) != 6:
        return False
    has_upper  = any(c in string.ascii_uppercase for c in random_seq)
    has_lower  = any(c in string.ascii_lowercase for c in random_seq)
    has_digit  = any(c in string.digits for c in random_seq)
    has_symbol = any(c in "}[&#(%" for c in random_seq)
    return all([has_upper, has_lower, has_digit, has_symbol])


# ─────────────────────────────────────────────────────────────────────────────
#  PLAYER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Player(Enlightened):
    """
    The player character. Inherits from Enlightened.
    If the player's race changes to a non-Enlightened race,
    the base class transitions to NotEnlightened at runtime.

    Player-specific systems:
    - Inventory (unlimited items, future item limit possible)
    - Equipment slots
    - Journal (metaphysical, AI-tagged)
    - Map notes
    - Status menu
    - Aliases
    - Save codes (single player only)
    - Respawn points
    - Bond pet (one at a time)
    - Achievements
    - Reputation (tiered)
    - Wanted level (tiered)
    - Debt and credit score
    - Guild memberships
    - Gossip list
    - Relationships (hidden from NPCs)
    - Multiplayer state
    """

    def __init__(
        self,
        name:         str,
        race:         str  = "human",
        is_multiplayer: bool = False,
        world_name:   str  = "Kyros",
    ):
        super().__init__(name, race, is_player=True)

        # ── Inventory ────────────────────────────────────────────────────
        self.inventory:     list[Item]      = []
        self.equipped:      list[Item]      = []
        self.dropped_items: list[DroppedItem] = []

        # ── Journal ──────────────────────────────────────────────────────
        self.journal:       list[JournalEntry] = []

        # ── Map notes ────────────────────────────────────────────────────
        self.map_notes:     list[MapNote]   = []

        # ── Aliases ──────────────────────────────────────────────────────
        self.aliases:       list[Alias]     = []

        # ── Respawn ──────────────────────────────────────────────────────
        self.respawn_points: list[RespawnPoint] = [
            RespawnPoint("Town Square", "elya", is_default=True)
        ]
        self.active_respawn: str = "elya"
        self.current_location: str = "elya"
        self.last_prompt:    str = "town"   # exact prompt state for save/load

        # ── Bond pet ─────────────────────────────────────────────────────
        self.bond_pet:      Optional[BondPet] = None

        # ── Achievements ─────────────────────────────────────────────────
        self.achievements:  list[Achievement] = []

        # ── Reputation and wanted ────────────────────────────────────────
        self.reputation:    list[ReputationEntry] = [
            ReputationEntry("local", "elya", 0.0)
        ]
        self.wanted_level:  dict[str, float] = {
            "local": 0.0, "regional": 0.0, "kingdom": 0.0, "empire": 0.0
        }

        # ── Wealth ───────────────────────────────────────────────────────
        self.wealth:        WealthState = WealthState(0.0)
        self.debts:         list[dict]  = []

        # ── NPC systems ──────────────────────────────────────────────────
        self.gossip_list:   list[GossipEntry] = []
        self.relationships: list[Relationship] = []
        self.guild_memberships: list[dict]    = []
        self.political_offices: list[str]     = []
        self.lie_history:   list[dict]        = []
        self.investments:   list[Investment]  = []
        self.bounties_placed:   list[Bounty]  = []
        self.bounties_on_self:  list[Bounty]  = []
        self.sentence:      Optional[Sentence]= None

        # ── Multiplayer ──────────────────────────────────────────────────
        self.is_multiplayer: bool = is_multiplayer
        self.world_name:     str  = world_name
        self.in_pvp:         bool = False
        self.pvp_opponent:   Optional[str] = None

        # ── Hardcoded achievement trackers ───────────────────────────────
        self._monsters_killed:  int = 0
        self._quests_completed: int = 0
        self._deaths:           int = 0
        self._items_crafted:    int = 0

        # ── Text mode (from original game) ───────────────────────────────
        self.text_mode:     bool = False

        # ── Buff tracking for original game compatibility ─────────────────
        self.buff_active:   bool  = False
        self.buff_end_time: float = 0.0


    # ─────────────────────────────────────────────────────────────────────
    #  INVENTORY
    # ─────────────────────────────────────────────────────────────────────

    def add_item(self, item: Item, silent: bool = False) -> None:
        """Add item to inventory."""
        self.inventory.append(item)
        if not silent:
            print(f"{item.name} added to inventory.")
        self._check_hardcoded_achievements()

    def remove_item(self, item_name: str) -> Optional[Item]:
        """Remove and return first matching item from inventory."""
        for i, item in enumerate(self.inventory):
            if item.name.lower() == item_name.lower():
                return self.inventory.pop(i)
        return None

    def has_item(self, item_name: str) -> bool:
        return any(i.name.lower() == item_name.lower() for i in self.inventory)

    def equip_item(self, item_name: str) -> list[str]:
        """
        Equip an item. Applies stat bonuses (capped at 20% of base).
        Returns notification strings.
        """
        item = next((i for i in self.inventory
                     if i.name.lower() == item_name.lower()), None)
        if not item:
            return [f"{item_name} not found in inventory."]
        if item.equipped:
            return [f"{item_name} is already equipped."]

        notifications = [f"Equipped: {item.name}"]
        cap_warnings  = []
        for stat, bonus in item.stats.items():
            applied = self.stats.add_gear_bonus(stat, bonus)
            if applied < bonus:
                cap_warnings.append(
                    f"{stat} bonus capped: only +{applied:.1f} of +{bonus:.1f} applied."
                )
        notifications.extend(cap_warnings)
        item.equipped = True
        self.equipped.append(item)
        return notifications

    def unequip_item(self, item_name: str) -> list[str]:
        """Unequip an item and remove its stat bonuses."""
        item = next((i for i in self.equipped
                     if i.name.lower() == item_name.lower()), None)
        if not item:
            return [f"{item_name} is not equipped."]
        for stat, bonus in item.stats.items():
            self.stats.remove_gear_bonus(stat, bonus)
        item.equipped = False
        self.equipped.remove(item)
        return [f"Unequipped: {item.name}"]


    # ─────────────────────────────────────────────────────────────────────
    #  DEATH AND RESPAWN
    # ─────────────────────────────────────────────────────────────────────

    def on_death(self) -> list[str]:
        """
        Player death:
        - Drop 2 random items at death location (despawn after 1 hr)
        - Lose 50% of gold permanently
        - Inventory is wiped permanently
        - Respawn at active respawn point
        """
        self._deaths += 1
        notifications = ["You died."]

        # Drop 2 random items
        drops = []
        if self.inventory:
            drop_pool = [i for i in self.inventory if not i.equipped]
            random.shuffle(drop_pool)
            drop_count = min(ITEM_DROP_COUNT, len(drop_pool))
            for item in drop_pool[:drop_count]:
                dropped = DroppedItem(item=item, location=self.current_location)
                self.dropped_items.append(dropped)
                drops.append(item.name)

        # Wipe inventory permanently
        gold_lost = round(self.gold * DEATH_GOLD_LOSS)
        self.gold = self.gold - gold_lost
        self.inventory = []
        self.equipped  = []
        self.stats._gear = {s: 0.0 for s in self.stats._gear}

        notifications.append(f"Inventory cleared.")
        notifications.append(f" - {gold_lost} Gold")
        if drops:
            notifications.append(
                f"Dropped at {self.current_location}: {', '.join(drops)} "
                f"(despawns in 1 hour)."
            )

        # Respawn
        self.health      = self.max_health
        self.mana        = self.max_mana
        self.is_dead     = False
        self.current_location = self.active_respawn
        notifications.append(
            f"You respawn at {self.active_respawn}."
        )

        # PvP disconnect rule — if opponent disconnected, they lose
        if self.in_pvp:
            self.in_pvp       = False
            self.pvp_opponent = None

        self._check_hardcoded_achievements()
        return notifications

    def unlock_respawn_point(self, name: str, location: str) -> list[str]:
        """Unlock a new respawn point."""
        existing = [r.location for r in self.respawn_points]
        if location in existing:
            return [f"Respawn point at {location} already unlocked."]
        rp = RespawnPoint(name=name, location=location)
        self.respawn_points.append(rp)
        return [f"Respawn point unlocked: {name} ({location})"]

    def set_active_respawn(self, location: str) -> list[str]:
        locs = [r.location for r in self.respawn_points]
        if location not in locs:
            return [f"No respawn point at {location}."]
        self.active_respawn = location
        return [f"Active respawn set to: {location}"]

    def retrieve_dropped_items(self) -> list[str]:
        """
        Pick up dropped items at current location if not yet despawned.
        First death's drops are already gone (handled in on_death by clearing inventory).
        """
        notifications = []
        still_here = []
        for drop in self.dropped_items:
            if drop.location != self.current_location:
                still_here.append(drop)
                continue
            if drop.is_despawned:
                notifications.append(f"{drop.item.name} has despawned.")
                continue
            self.add_item(drop.item, silent=True)
            notifications.append(f"Retrieved: {drop.item.name}")
        self.dropped_items = still_here
        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  JOURNAL
    # ─────────────────────────────────────────────────────────────────────

    def add_journal_entry(
        self,
        text:          str,
        known_entities: list[str] = None,
    ) -> list[str]:
        """
        Add a journal entry. AI tags it to recognized entities.
        If no entities recognized, stored as free text.
        known_entities: list of NPC names, locations, items currently known.
        """
        tags    = []
        is_free = True

        if known_entities:
            text_lower = text.lower()
            for entity in known_entities:
                if entity.lower() in text_lower:
                    tags.append(entity)
                    is_free = False

        entry = JournalEntry(text=text, tags=tags, is_free=is_free)
        self.journal.append(entry)

        if tags:
            return [f"Journal entry added. Tagged: {', '.join(tags)}"]
        return ["Journal entry added."]

    def delete_journal_entry(self, index: int) -> list[str]:
        """Delete a journal entry by index. AI loses awareness of deleted entries."""
        if index < 0 or index >= len(self.journal):
            return ["Invalid journal entry index."]
        removed = self.journal.pop(index)
        return [f"Journal entry deleted: \"{removed.text[:40]}...\""]

    def get_journal_toc(self) -> str:
        """
        Return a table of contents for the journal.
        Tagged entries are grouped by entity.
        Free entries listed separately.
        """
        lines   = ["=== Journal ==="]
        tagged  = {}
        free    = []

        for i, entry in enumerate(self.journal):
            if entry.tags:
                for tag in entry.tags:
                    tagged.setdefault(tag, []).append((i, entry))
            else:
                free.append((i, entry))

        for entity, entries in sorted(tagged.items()):
            lines.append(f"\n[{entity}]")
            for i, e in entries:
                lines.append(f"  {i}. [{e.display_timestamp}] {e.text[:60]}")

        if free:
            lines.append("\n[Untagged Notes]")
            for i, e in free:
                lines.append(f"  {i}. [{e.display_timestamp}] {e.text[:60]}")

        return "\n".join(lines)

    def get_journal_context_for_ai(self) -> str:
        """
        Return journal content formatted for AI NPC reference.
        Metaphysical — NPCs cannot retain this after interaction ends.
        """
        if not self.journal:
            return "no journal entries"
        lines = []
        for e in self.journal:
            tag_str = f"[tags: {', '.join(e.tags)}] " if e.tags else ""
            lines.append(f"{tag_str}{e.text}")
        return "\n".join(lines)


    # ─────────────────────────────────────────────────────────────────────
    #  MAP NOTES
    # ─────────────────────────────────────────────────────────────────────

    def add_map_note(self, location: str, text: str) -> list[str]:
        note = MapNote(location=location, text=text)
        self.map_notes.append(note)
        return [f"Map note added at {location}."]

    def get_map_notes(self, location: str = None) -> list[MapNote]:
        if location:
            return [n for n in self.map_notes if n.location.lower() == location.lower()]
        return self.map_notes


    # ─────────────────────────────────────────────────────────────────────
    #  ALIASES
    # ─────────────────────────────────────────────────────────────────────

    def add_alias(self, alias: str, context: str, location: str) -> list[str]:
        """Set an alias for a specific context and location."""
        self.aliases.append(Alias(alias=alias, context=context, location=location))
        return [f"Alias set: '{alias}' ({context} in {location})"]

    def get_alias(self, context: str = None, location: str = None) -> Optional[str]:
        """Retrieve alias for a given context/location, or None for true name."""
        for a in self.aliases:
            if context and a.context.lower() == context.lower():
                return a.alias
            if location and a.location.lower() == location.lower():
                return a.alias
        return None

    def get_name_for_context(self, context: str = None, location: str = None) -> str:
        """Returns alias if one applies, otherwise true name."""
        alias = self.get_alias(context, location)
        return alias if alias else self.name


    # ─────────────────────────────────────────────────────────────────────
    #  STATUS MENU
    # ─────────────────────────────────────────────────────────────────────

    def show_status(self, mode: str = "full") -> str:
        """
        Display the full status menu.
        mode: "full" | "combat" | "finances" | "journal" | "inventory"
        Triggered by typing 'status' at any input prompt.
        """
        if mode == "combat":
            return self._status_combat()
        if mode == "finances":
            return self._status_finances()
        if mode == "journal":
            return self.get_journal_toc()
        if mode == "inventory":
            return self._status_inventory()
        return self._status_full()

    def _status_full(self) -> str:
        lines = ["=" * 50]

        # Identity line
        race_disp  = f"{self.race} ({self.race_track.grade})"
        class_disp = (f"{self.class_track.name} ({self.class_track.grade})"
                      if self.class_track else "No Class")
        prof_disp  = (f"{self.profession_track.name} ({self.profession_track.grade})"
                      if self.profession_track else "No Profession")
        lines.append(f"{self.name}")
        lines.append(f"Race:       {race_disp} | Level {self.race_track.level}")
        lines.append(f"Class:      {class_disp} | Level {self.class_track.level if self.class_track else 0}")
        lines.append(f"Profession: {prof_disp} | Level {self.profession_track.level if self.profession_track else 0}")

        # Evolution progress
        lines.append("")
        if self.race_track:
            lines.append(f"Race evolution:       {self.race_track.pct_to_evolution:.1f}%")
        if self.class_track:
            lines.append(f"Class evolution:      {self.class_track.pct_to_evolution:.1f}%")
        if self.profession_track:
            lines.append(f"Profession evolution: {self.profession_track.pct_to_evolution:.1f}%")

        # Gold
        lines.append("")
        lines.append(f"Gold: {self.gold:.0f}")

        # Core stats
        lines.append("")
        lines.append("── Stats ──────────────────────────────────")
        stat_names = ["strength","constitution","dexterity","agility",
                      "intelligence","wisdom","perception","charisma"]
        for s in stat_names:
            val = self.stats.effective(s)
            lines.append(f"  {s.capitalize():<14} {val:.1f}")

        # Derived combat stats
        lines.append("")
        lines.append("── Combat ─────────────────────────────────")
        lines.append(f"  Health:       {self.health:.0f} / {self.max_health:.0f}")
        lines.append(f"  Mana:         {self.mana:.0f} / {self.max_mana:.0f}")
        lines.append(f"  Attack Power: {self.attack_power:.1f}")
        lines.append(f"  Defense:      {self.defense:.1f}")
        lines.append(f"  Crit Chance:  {self.crit_chance:.1f}%")
        lines.append(f"  Dodge Chance: {self.dodge_chance:.1f}%")
        lines.append(f"  Speed:        {self.speed:.1f}")

        # Skills
        if self.skills:
            lines.append("")
            lines.append("── Skills ─────────────────────────────────")
            for s in self.skills:
                passive = " (passive)" if s.skill_type == "passive" else ""
                lines.append(f"  [{s.rarity}] {s.name} Lv{s.level}{passive}")
                lines.append(f"    {s.description}")

        # Titles
        if self.titles:
            lines.append("")
            lines.append("── Titles ─────────────────────────────────")
            for t in self.titles:
                lines.append(f"  [{t.rarity}] {t.name}")

        # Blessing
        if self.blessing:
            lines.append("")
            lines.append(f"── Blessing ────────────────────────────────")
            lines.append(f"  {self.blessing.god_name}: {self.blessing.level}")
            if self.blessing.is_chosen:
                lines.append("  [CHOSEN]")

        # Heretic
        if self.heretic:
            lines.append("")
            lines.append("  [HERETIC]")

        # Free points
        if self.free_points > 0:
            lines.append("")
            lines.append(f"Free stat points to allocate: {self.free_points}")

        lines.append("=" * 50)
        lines.append("Tabs: status combat | status finances | status journal | status inventory")
        return "\n".join(lines)

    def _status_combat(self) -> str:
        lines = ["=" * 40, "── Combat Status ──────────────────────"]
        lines.append(f"  Health:       {self.health:.0f} / {self.max_health:.0f}")
        lines.append(f"  Mana:         {self.mana:.0f} / {self.max_mana:.0f}")
        lines.append(f"  Attack Power: {self.attack_power:.1f}")
        lines.append(f"  Defense:      {self.defense:.1f}")
        lines.append(f"  Crit Chance:  {self.crit_chance:.1f}%")
        lines.append(f"  Dodge Chance: {self.dodge_chance:.1f}%")
        lines.append(f"  Speed:        {self.speed:.1f}")
        if self.equipped:
            lines.append("")
            lines.append("  Equipped:")
            for item in self.equipped:
                lines.append(f"    [{item.rarity}] {item.name}")
        active_buffs = self.get_active_buffs()
        if active_buffs:
            lines.append("")
            lines.append("  Active Buffs:")
            for b in active_buffs:
                remaining = ""
                if b.duration > 0:
                    secs = max(0.0, b.duration - (time.time() - b.applied_at))
                    remaining = f" ({secs:.0f}s)"
                lines.append(f"    {b.name}{remaining}")
        lines.append("=" * 40)
        return "\n".join(lines)

    def _status_finances(self) -> str:
        lines = ["=" * 40, "── Finances ───────────────────────────"]
        lines.append(f"  Gold:         {self.gold:.0f}")
        lines.append(f"  Credit Score: {self.wealth.credit_score:.0f} / 1000")
        if self.debts:
            lines.append("")
            lines.append("  Debts:")
            for d in self.debts:
                lines.append(f"    {d.get('lender','?')}: {d.get('amount',0):.0f} Gold")
        if self.investments:
            lines.append("")
            lines.append("  Investments:")
            for inv in self.investments:
                lines.append(f"    {inv.target}: {inv.amount:.0f} Gold invested")
        if self.wealth.tax_record:
            lines.append("")
            lines.append("  Tax Record:")
            for t in self.wealth.tax_record[-5:]:
                status = "PAID" if t["paid"] else "EVADED"
                lines.append(f"    [{status}] {t['period']}: {t['amount']:.0f} Gold")
        lines.append("=" * 40)
        return "\n".join(lines)

    def _status_inventory(self) -> str:
        lines = ["=" * 40, "── Inventory ──────────────────────────"]
        if not self.inventory:
            lines.append("  (empty)")
        else:
            for i, item in enumerate(self.inventory):
                equipped_tag = " [E]" if item.equipped else ""
                lines.append(f"  {i}. [{item.rarity}] {item.name}{equipped_tag}")
                if item.stats:
                    for stat, val in item.stats.items():
                        lines.append(f"       {stat}: +{val}")
        lines.append("=" * 40)
        return "\n".join(lines)


    # ─────────────────────────────────────────────────────────────────────
    #  SAVE / LOAD (SINGLE PLAYER ONLY)
    # ─────────────────────────────────────────────────────────────────────

    def save(self, prompt_context: str = "") -> str:
        """
        Generate a save code capturing full world state.
        Single player only — multiplayer uses server-side persistence.
        Returns the save code string.
        """
        if self.is_multiplayer:
            return "Save codes are not available in multiplayer."

        if prompt_context:
            self.last_prompt = prompt_context

        code = generate_save_code(
            world_name      = self.world_name,
            race_tier       = self.race_track.grade,
            class_tier      = self.class_track.grade if self.class_track else "G",
            profession_tier = self.profession_track.grade if self.profession_track else "G",
            race_name       = self.race,
            class_name      = self.class_track.name if self.class_track else "none",
            profession_name = self.profession_track.name if self.profession_track else "none",
        )

        # Serialize full state alongside the code
        state = self._serialize()
        state["save_code"] = code
        state["saved_at"]  = time.time()

        # In production this writes to saves.json keyed by code
        save_path = "saves.json"
        try:
            if os.path.exists(save_path):
                with open(save_path, "r") as f:
                    saves = json.load(f)
            else:
                saves = {}
            saves[code] = state
            with open(save_path, "w") as f:
                json.dump(saves, f, indent=2)
        except (IOError, json.JSONDecodeError):
            pass

        print(f"Game saved. Your code: {code}")
        return code

    def _serialize(self) -> dict:
        """Serialize player state to a JSON-compatible dict."""
        return {
            "name":          self.name,
            "race":          self.race,
            "level":         self.level,
            "xp":            self.xp,
            "health":        self.health,
            "mana":          self.mana,
            "gold":          self.gold,
            "last_prompt":   self.last_prompt,
            "current_location": self.current_location,
            "active_respawn":self.active_respawn,
            "text_mode":     self.text_mode,
            "stats": {
                "strength":     self.stats.strength,
                "constitution": self.stats.constitution,
                "dexterity":    self.stats.dexterity,
                "agility":      self.stats.agility,
                "intelligence": self.stats.intelligence,
                "wisdom":       self.stats.wisdom,
                "perception":   self.stats.perception,
                "charisma":     self.stats.charisma,
            },
            "free_points":   self.free_points,
            "inventory": [
                {"name": i.name, "rarity": i.rarity, "type": i.item_type,
                 "stats": i.stats, "description": i.description,
                 "quantity": i.quantity, "equipped": i.equipped}
                for i in self.inventory
            ],
            "equipped":      [i.name for i in self.equipped],
            "skills": [
                {"name": s.name, "description": s.description, "rarity": s.rarity,
                 "type": s.skill_type, "source": s.source, "level": s.level,
                 "comprehension": s.comprehension}
                for s in self.skills
            ],
            "titles": [
                {"name": t.name, "description": t.description, "rarity": t.rarity,
                 "stat_bonuses": t.stat_bonuses, "free_points": t.free_points}
                for t in self.titles
            ],
            "journal": [
                {"text": e.text, "timestamp": e.timestamp,
                 "tags": e.tags, "is_free": e.is_free}
                for e in self.journal
            ],
            "map_notes": [
                {"location": n.location, "text": n.text, "timestamp": n.timestamp}
                for n in self.map_notes
            ],
            "aliases": [
                {"alias": a.alias, "context": a.context, "location": a.location}
                for a in self.aliases
            ],
            "achievements": [
                {"name": a.name, "description": a.description, "rarity": a.rarity}
                for a in self.achievements
            ],
            "reputation":    [
                {"tier": r.tier, "location": r.location, "score": r.score}
                for r in self.reputation
            ],
            "wanted_level":  self.wanted_level,
            "wealth": {
                "value":        self.wealth.value,
                "credit_score": self.wealth.credit_score,
            },
            "class_track": {
                "name":        self.class_track.name,
                "grade_index": self.class_track.grade_index,
                "level":       self.class_track.level,
                "xp":          self.class_track.xp,
                "free_points": self.class_track.free_points,
            } if self.class_track else None,
            "profession_track": {
                "name":        self.profession_track.name,
                "grade_index": self.profession_track.grade_index,
                "level":       self.profession_track.level,
                "xp":          self.profession_track.xp,
                "free_points": self.profession_track.free_points,
            } if self.profession_track else None,
            "race_track": {
                "name":        self.race_track.name,
                "grade_index": self.race_track.grade_index,
                "level":       self.race_track.level,
                "xp":          self.race_track.xp,
                "free_points": self.race_track.free_points,
            },
            "gossip_list": [
                {"description": g.description, "score": g.score,
                 "source_npc": g.source_npc, "verified": g.verified}
                for g in self.gossip_list
            ],
            "guild_memberships": self.guild_memberships,
            "political_offices": self.political_offices,
            "bond_pet": {
                "name":    self.bond_pet.name,
                "species": self.bond_pet.species,
                "level":   self.bond_pet.race_track.level,
                "grade":   self.bond_pet.race_track.grade,
                "health":  self.bond_pet.health,
                "is_dead": self.bond_pet.is_dead,
                "resurrect_mana_paid": self.bond_pet.resurrect_mana_paid,
            } if self.bond_pet else None,
            "respawn_points": [
                {"name": r.name, "location": r.location, "is_default": r.is_default}
                for r in self.respawn_points
            ],
            "sentence": {
                "duration": self.sentence.duration_real_seconds,
                "start":    self.sentence.start_time,
                "crime":    self.sentence.crime,
                "jurisdiction": self.sentence.jurisdiction,
            } if self.sentence else None,
            "lie_history":   self.lie_history,
            "monsters_killed":  self._monsters_killed,
            "quests_completed": self._quests_completed,
            "deaths":           self._deaths,
        }

    @classmethod
    def load(cls, code: str) -> Optional["Player"]:
        """
        Load a player from a save code.
        Returns None if code not found or invalid.
        """
        if not validate_save_code(code):
            print("Invalid save code format.")
            return None

        save_path = "saves.json"
        if not os.path.exists(save_path):
            print("No save file found.")
            return None

        try:
            with open(save_path, "r") as f:
                saves = json.load(f)
        except (IOError, json.JSONDecodeError):
            print("Save file could not be read.")
            return None

        state = saves.get(code)
        if not state:
            print("Save code not found.")
            return None

        return cls._deserialize(state)

    @classmethod
    def _deserialize(cls, state: dict) -> "Player":
        """Reconstruct a Player from a serialized state dict."""
        player = cls(
            name       = state["name"],
            race       = state["race"],
        )
        player.level            = state["level"]
        player.xp               = state["xp"]
        player.health           = state["health"]
        player.mana             = state["mana"]
        player.gold             = state["gold"]
        player.last_prompt      = state.get("last_prompt", "town")
        player.current_location = state.get("current_location", "elya")
        player.active_respawn   = state.get("active_respawn", "elya")
        player.text_mode        = state.get("text_mode", False)
        player.free_points      = state.get("free_points", 0)
        player._monsters_killed = state.get("monsters_killed", 0)
        player._quests_completed= state.get("quests_completed", 0)
        player._deaths          = state.get("deaths", 0)

        # Stats
        for stat, val in state.get("stats", {}).items():
            if hasattr(player.stats, stat):
                setattr(player.stats, stat, val)

        # Inventory
        for i in state.get("inventory", []):
            item = Item(
                name=i["name"], rarity=i["rarity"], item_type=i["type"],
                stats=i["stats"], description=i["description"],
                quantity=i["quantity"], equipped=i["equipped"],
            )
            player.inventory.append(item)
            if item.equipped:
                player.equipped.append(item)

        # Skills
        for s in state.get("skills", []):
            player.skills.append(Skill(
                name=s["name"], description=s["description"], rarity=s["rarity"],
                skill_type=s["type"], source=s["source"], level=s["level"],
                comprehension=s["comprehension"],
            ))

        # Titles
        for t in state.get("titles", []):
            player.titles.append(Title(
                name=t["name"], description=t["description"], rarity=t["rarity"],
                stat_bonuses=t["stat_bonuses"], free_points=t["free_points"],
            ))

        # Journal
        for e in state.get("journal", []):
            player.journal.append(JournalEntry(
                text=e["text"], timestamp=e["timestamp"],
                tags=e["tags"], is_free=e["is_free"],
            ))

        # Map notes
        for n in state.get("map_notes", []):
            player.map_notes.append(MapNote(
                location=n["location"], text=n["text"], timestamp=n["timestamp"],
            ))

        # Aliases
        for a in state.get("aliases", []):
            player.aliases.append(Alias(
                alias=a["alias"], context=a["context"], location=a["location"],
            ))

        # Evolution tracks
        if state.get("class_track"):
            ct = state["class_track"]
            player.class_track = EvolutionTrack(
                name=ct["name"], grade_index=ct["grade_index"],
                level=ct["level"], xp=ct["xp"],
                free_points=ct.get("free_points", 0),
            )
            player.class_chosen = True
        if state.get("profession_track"):
            pt = state["profession_track"]
            player.profession_track = EvolutionTrack(
                name=pt["name"], grade_index=pt["grade_index"],
                level=pt["level"], xp=pt["xp"],
                free_points=pt.get("free_points", 0),
            )
            player.profession_chosen = True
        if state.get("race_track"):
            rt = state["race_track"]
            player.race_track = EvolutionTrack(
                name=rt["name"], grade_index=rt["grade_index"],
                level=rt["level"], xp=rt["xp"],
            )

        # Reputation
        player.reputation = [
            ReputationEntry(tier=r["tier"], location=r["location"], score=r["score"])
            for r in state.get("reputation", [])
        ]
        player.wanted_level = state.get("wanted_level", {
            "local": 0.0, "regional": 0.0, "kingdom": 0.0, "empire": 0.0
        })

        # Wealth
        w = state.get("wealth", {})
        player.wealth.value        = w.get("value", 0.0)
        player.wealth.credit_score = w.get("credit_score", 500.0)

        # Guild and political
        player.guild_memberships = state.get("guild_memberships", [])
        player.political_offices = state.get("political_offices", [])

        # Sentence
        if state.get("sentence"):
            s = state["sentence"]
            player.sentence = Sentence(
                duration_real_seconds = s["duration"],
                start_time            = s["start"],
                crime                 = s["crime"],
                jurisdiction          = s["jurisdiction"],
            )

        # Lie history and gossip
        player.lie_history  = state.get("lie_history", [])
        player.gossip_list  = []  # gossip re-populated by world on load

        # Achievements
        for a in state.get("achievements", []):
            player.achievements.append(Achievement(
                name=a["name"], description=a["description"], rarity=a["rarity"],
            ))

        # Respawn points
        player.respawn_points = [
            RespawnPoint(name=r["name"], location=r["location"], is_default=r["is_default"])
            for r in state.get("respawn_points", [{"name":"Town Square","location":"elya","is_default":True}])
        ]

        return player


    # ─────────────────────────────────────────────────────────────────────
    #  BOND PET
    # ─────────────────────────────────────────────────────────────────────

    def bond_with_pet(self, pet: BondPet) -> list[str]:
        """Bond with a new pet. Only one bond at a time."""
        if self.bond_pet:
            return [
                f"You already have a bond with {self.bond_pet.name}. "
                "You cannot bond with another creature."
            ]
        self.bond_pet = pet
        return [
            f"You have bonded with {pet.name} ({pet.species})!",
            f"Bond pets are very rare companions. Treat them well.",
        ]

    def pay_pet_resurrect_mana(self, amount: float) -> list[str]:
        """Pay mana toward bond pet resurrection."""
        if not self.bond_pet or not self.bond_pet.is_dead:
            return ["No bond pet needs resurrection."]
        if self.mana < amount:
            amount = self.mana
        if amount <= 0:
            return ["Not enough mana."]
        self.mana -= amount
        actual, resurrected = self.bond_pet.pay_resurrect_mana(amount)
        if resurrected:
            return [
                f"{self.bond_pet.name} has been resurrected!",
                f"Mana spent: {actual:.0f}",
            ]
        remaining = self.bond_pet.resurrect_remaining
        return [
            f"Mana paid: {actual:.0f}. Remaining to resurrect {self.bond_pet.name}: {remaining:.0f}",
        ]


    # ─────────────────────────────────────────────────────────────────────
    #  ACHIEVEMENTS
    # ─────────────────────────────────────────────────────────────────────

    def grant_achievement(
        self,
        name:        str,
        description: str,
        rarity:      str = "common",
        title:       Optional[Title] = None,
    ) -> list[str]:
        """Grant an achievement. Returns notification strings."""
        if any(a.name == name for a in self.achievements):
            return []   # already earned
        achievement = Achievement(
            name=name, description=description,
            rarity=rarity, title=title,
        )
        self.achievements.append(achievement)
        notifications = [f"Achievement unlocked: [{rarity}] {name}"]
        if title:
            notifications.extend(self.add_title(title))
        return notifications

    def _check_hardcoded_achievements(self) -> list[str]:
        """
        Check and grant hardcoded achievements based on tracked actions.
        Returns notifications for any newly earned achievements.
        """
        notifications = []

        checks = [
            (self._monsters_killed >= 1,   "First Blood",      "Kill your first monster.",      "common"),
            (self._monsters_killed >= 10,  "Slayer",           "Kill 10 monsters.",             "common"),
            (self._monsters_killed >= 100, "Monster Hunter",   "Kill 100 monsters.",            "uncommon"),
            (self._quests_completed >= 1,  "Quest Beginner",   "Complete your first quest.",    "common"),
            (self._quests_completed >= 10, "Seasoned Adventurer","Complete 10 quests.",         "uncommon"),
            (self._deaths >= 1,            "First Death",      "Die for the first time.",       "common"),
            (self._deaths >= 10,           "Persistent",       "Die 10 times.",                 "uncommon"),
            (len(self.inventory) >= 20,    "Hoarder",          "Carry 20 items at once.",       "common"),
            (len(self.titles) >= 5,        "Title Collector",  "Earn 5 titles.",                "uncommon"),
            (self.gold >= 1000,            "Prosperous",       "Accumulate 1000 gold.",         "common"),
            (self.gold >= 10000,           "Wealthy",          "Accumulate 10,000 gold.",       "uncommon"),
            (self.bond_pet is not None,    "Bonded",           "Bond with a creature.",         "rare"),
        ]

        for condition, name, desc, rarity in checks:
            if condition:
                notes = self.grant_achievement(name, desc, rarity)
                notifications.extend(notes)

        return notifications

    def record_kill(self, monster_name: str, xp: float, gold: float) -> list[str]:
        """Record a monster kill. Grants XP, gold, checks achievements."""
        self._monsters_killed += 1
        notifications  = self.gain_xp(xp)
        self.earn_gold(gold)
        notifications += self._check_hardcoded_achievements()
        return notifications

    def record_quest_complete(self, xp: float, gold: float) -> list[str]:
        """Record a quest completion."""
        self._quests_completed += 1
        notifications  = self.gain_xp(xp)
        self.earn_gold(gold)
        notifications += self._check_hardcoded_achievements()
        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  REPUTATION AND WANTED
    # ─────────────────────────────────────────────────────────────────────

    def update_reputation(self, tier: str, location: str, delta: float) -> None:
        for rep in self.reputation:
            if rep.tier == tier and rep.location == location:
                rep.update(delta)
                return
        self.reputation.append(ReputationEntry(
            tier=tier, location=location, score=delta
        ))

    def update_wanted(self, jurisdiction: str, delta: float) -> list[str]:
        tier = self.wanted_level.get(jurisdiction, 0.0)
        self.wanted_level[jurisdiction] = max(0.0, tier + delta)
        if delta > 0:
            return [f"Wanted level increased in {jurisdiction}."]
        return []


    # ─────────────────────────────────────────────────────────────────────
    #  MULTIPLAYER
    # ─────────────────────────────────────────────────────────────────────

    def start_pvp(self, opponent_name: str) -> list[str]:
        self.in_pvp       = True
        self.pvp_opponent = opponent_name
        return [f"PvP started against {opponent_name}."]

    def end_pvp(self, disconnected: bool = False) -> list[str]:
        opponent = self.pvp_opponent
        self.in_pvp       = False
        self.pvp_opponent = None
        if disconnected and PVP_DISCONNECT_WIN:
            return [f"{opponent} disconnected. You win the PvP."]
        return ["PvP ended."]


    # ─────────────────────────────────────────────────────────────────────
    #  HANDLE 'STATUS' INPUT AT ANY PROMPT
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def intercept_status(player: "Player", user_input: str) -> tuple[bool, str]:
        """
        Call this at every input prompt before processing.
        If user typed 'status' or a status sub-command, display and return True.
        Returns (was_status_command, display_string).
        """
        inp = user_input.strip().lower()
        if inp == "status":
            return True, player.show_status("full")
        if inp == "status combat":
            return True, player.show_status("combat")
        if inp == "status finances":
            return True, player.show_status("finances")
        if inp == "status journal":
            return True, player.show_status("journal")
        if inp == "status inventory":
            return True, player.show_status("inventory")
        if inp == "save":
            code = player.save()
            return True, f"Saved. Code: {code}"
        return False, ""


    # ─────────────────────────────────────────────────────────────────────
    #  FULL STATE DICT FOR NPC AI CONTEXT
    # ─────────────────────────────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        base = super().to_state_dict()
        base.update({
            "guild_memberships":  [g.get("guild_name","?") for g in self.guild_memberships],
            "political_offices":  self.political_offices,
            "reputation":         [
                {"tier": r.tier, "location": r.location, "score": r.score}
                for r in self.reputation
            ],
            "wanted_level":       self.wanted_level,
            "credit_score":       self.wealth.credit_score,
            "aliases":            [a.alias for a in self.aliases],
            "journal_context":    self.get_journal_context_for_ai(),
            "bond_pet":           self.bond_pet.name if self.bond_pet else None,
            "achievements":       [a.name for a in self.achievements],
            "inventory_count":    len(self.inventory),
            "equipped":           [i.name for i in self.equipped],
        })
        return base