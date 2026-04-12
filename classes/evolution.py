"""
kyros/evolution.py

EvolutionSystem — handles all class, profession, race, and skill evolution for Kyros.

Owns:
- Initial class selection (G grade: 6 fixed options)
- Class/profession branching at each evolution (AI-generated, based on skills/actions)
- Race evolution (tier upgrade, 1% race change offer)
- Skill generation (between-grade picks and evolution picks)
- Evolution quest generation (via QuestSystem)
- Stat point grants per level (AI-decided per class/profession/race)
- Free point grants per level
- Perfect Evolution detection and bonus
- Stat decay for delayed evolution (stacking, -1% base per IRL day after 1 day)
- Chosen system hooks (one True Blessing per god, energy cooldown)
- God/blessing system (12 primordials + thousands of lesser gods)
- Heretic branding on god switch
- Temple/shrine interaction hooks
- Land ownership shrine hook (full land system is #22)

World simulation pauses during evolution choices.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

GRADE_NAMES = ["G", "F", "E", "D", "C", "B", "A", "S", "God", "Godking", "Primordial"]
GRADE_MAX_LEVELS = [9, 24, 49, 99, 199, 349, 549, 799, 1099, 1499, 1999, 99999]
EVOLUTION_THRESHOLDS = [0, 10, 25, 50, 100, 200, 350, 550, 800, 1100, 1500, 2000]

# Skill pick intervals per grade (every N levels)
SKILL_PICK_INTERVAL = {
    0: 5,    # G: every 5 levels
    1: 10,   # F: every 10 levels
    2: 20,   # E: every 20 levels
    3: 40,   # D: every 40 levels
    4: 80,   # C: every 80 levels
    5: 160,  # B: every 160 levels
    6: 220,  # A
    7: 250,  # S
    8: 300,  # God
    9: 400,  # Godking
}

# Perfect Evolution stat bonuses (free points)
PERFECT_EVOLUTION_BONUS = {
    0: 0,    # G (no bonus at G)
    1: 100,  # F
    2: 200,  # E
    3: 400,  # D
    4: 800,  # C
    5: 1600, # B
    6: 3200, # A
    7: 6400, # S
}

# Decay constants
DECAY_GRACE_PERIOD  = 60 * 60 * 24      # 1 IRL day before decay starts
DECAY_RATE_PER_DAY  = 0.01              # -1% of base stat per IRL day per stack
DECAY_TICK_INTERVAL = 60 * 60 * 24      # check decay once per IRL day

# Race change chance at evolution
RACE_CHANGE_CHANCE  = 0.01              # 1%

# Initial class options at G grade
INITIAL_CLASSES = [
    "Mage",
    "Archer",
    "Healer",
    "Heavy Warrior",
    "Medium Warrior",
    "Light Warrior",
]

# Rarity tiers (inferior is below common)
RARITY_TIERS = ["inferior", "common", "uncommon", "rare", "epic",
                "legendary", "mythic", "divine"]

# Blessing levels (same for primordials and lesser gods)
BLESSING_LEVELS = ["lesser", "minor", "greater", "major", "divine", "true"]

# True blessing energy cooldown (real seconds)
# If chosen died quickly (< 1 IRL day as chosen): long cooldown
TRUE_BLESSING_QUICK_DEATH_COOLDOWN = 60 * 60 * 24 * 7   # 1 week
TRUE_BLESSING_NORMAL_COOLDOWN      = 60 * 60 * 24        # 1 day


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude_json(
    system:     str,
    messages:   list,
    max_tokens: int = 800,
) -> dict | list:
    if not ANTHROPIC_API_KEY:
        return {}
    payload = json.dumps({
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data    = payload,
        headers = {
            "Content-Type":      "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key":         ANTHROPIC_API_KEY,
        },
        method = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data  = json.loads(resp.read().decode())
            blocks= data.get("content", [])
            text  = " ".join(b["text"] for b in blocks if b.get("type") == "text")
            clean = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(clean)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SkillOption:
    """A skill option presented to the player for selection."""
    name:         str
    description:  str
    rarity:       str        # from RARITY_TIERS
    skill_type:   str        # active / passive / racial / ritual
    source:       str        # class/profession/race name
    preview_effect: str = "" # brief mechanical preview


@dataclass
class ClassOption:
    """
    A class, profession, or race option at evolution.
    AI-generated based on current class, skills, and actions.
    """
    name:          str
    description:   str        # must state if race-specific
    rarity:        str        # from RARITY_TIERS
    is_race_specific: bool = False
    required_race: str   = "" # if race-specific, which race
    stat_focus:    list[str] = field(default_factory=list)  # primary stats
    fixed_points_per_level: int = 3
    free_points_per_level:  int = 1
    evolution_quest_preview: str = ""  # brief preview of what evolution will require


@dataclass
class DecayStack:
    """
    A stacking stat decay applied when evolution is delayed.
    One stack per IRL day past the grace period.
    Reversed completely when player evolves all three tracks.
    """
    stat:           str
    percent_lost:   float    # total % lost so far (stacks of 1% each)
    stacks:         int      # number of stacks applied
    started_at:     float    # when grace period expired
    last_stack_at:  float    # when last stack was applied
    original_base:  float    # base stat value when decay began


@dataclass
class GodRecord:
    """
    Records a player's standing with a specific god.
    """
    god_name:      str
    is_primordial: bool  = False
    blessing_level: Optional[str] = None   # current blessing level if blessed
    is_chosen:     bool  = False
    is_heretic:    bool  = False
    heretic_since: float = 0.0
    favor:         float = 0.0    # -1000 to 1000
    interactions:  int   = 0      # times prayed/interacted


@dataclass
class ChosenRecord:
    """
    Tracks the current Chosen for a god.
    One per god. Only one True Blessing active per god at a time.
    """
    god_name:      str
    player_name:   str
    chosen_since:  float = field(default_factory=time.time)
    energy_cooldown_until: float = 0.0   # god cannot choose again until this time
    last_chosen_duration:  float = 0.0   # how long the last chosen lasted


@dataclass
class EvolutionQuestSpec:
    """
    Specification for generating an evolution quest.
    Passed to QuestSystem.generate_quest() with special flags.
    """
    track:           str    # "class" | "profession" | "race"
    current_name:    str
    current_grade:   int
    player_level:    int
    player_race:     str
    player_class:    str
    flavor_context:  str    # AI uses this for quest narrative


# ─────────────────────────────────────────────────────────────────────────────
#  EVOLUTION SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class EvolutionSystem:
    """
    Manages all evolution logic for one player.
    One EvolutionSystem per player.

    Called by game loop at:
    - Character creation (initial class selection)
    - Grade max level reached (trigger evolution quest generation)
    - `evolve class/profession/race` command
    - Level milestones (skill picks between grades)
    - Daily tick (decay check)
    """

    def __init__(self, player_name: str, quest_system=None, world_sim=None):
        self.player_name  = player_name
        self.quest_system = quest_system
        self.world_sim    = world_sim

        # Pending evolution state — set when grade cap reached
        # Each track independently tracks whether evolution is ready
        self.evolution_ready: dict[str, bool] = {
            "class": False, "profession": False, "race": False
        }

        # Pending skill picks — level → list of SkillOption
        self.pending_skill_picks: list[dict] = []

        # Pending race change offer (1% chance at race evolution)
        self.pending_race_offer: Optional[ClassOption] = None

        # Decay tracking per stat
        self.decay_stacks: list[DecayStack] = []
        self._last_decay_check: float = 0.0

        # God relationships
        self.god_records: dict[str, GodRecord] = {}

        # Skill pick history (for AI context)
        self.skill_history: list[str] = []

        # Action history (for AI context — what the player has done)
        self.action_history: list[str] = []

        # Class/profession options cache — cleared after selection
        self._pending_class_options:    list[ClassOption] = []
        self._pending_prof_options:     list[ClassOption] = []
        self._pending_race_options:     list[ClassOption] = []

        # Evolution pause flag — world sim checks this
        self.evolution_paused: bool = False

        # Perfect evolution tracking
        self.perfect_evolutions: dict[str, int] = {}   # grade → count of tracks evolved perfectly


    # ─────────────────────────────────────────────────────────────────────
    #  CHARACTER CREATION — INITIAL CLASS
    # ─────────────────────────────────────────────────────────────────────

    def get_initial_class_options(self) -> list[ClassOption]:
        """
        Return the 6 fixed starting class options for G grade.
        AI fleshes out the description and stat focus per option.
        """
        options = []
        for class_name in INITIAL_CLASSES:
            result = _call_claude_json(
                "Generate a concise description for a starting class at G grade in Kyros. "
                "Output ONLY JSON with keys: description (string, 2 sentences), "
                "stat_focus (list of 2-3 stat names from: strength/constitution/dexterity/"
                "agility/intelligence/wisdom/perception/charisma), "
                "fixed_points_per_level (int 2-5), free_points_per_level (int 1-2).",
                [{"role": "user", "content": f"Class: {class_name}"}],
                max_tokens=200,
            )
            options.append(ClassOption(
                name        = class_name,
                description = result.get("description",
                              f"A {class_name} class for beginning adventurers."),
                rarity      = "common",
                stat_focus  = result.get("stat_focus", ["strength"]),
                fixed_points_per_level = int(result.get("fixed_points_per_level", 3)),
                free_points_per_level  = int(result.get("free_points_per_level", 1)),
            ))
        return options

    def select_initial_class(
        self,
        class_option: ClassOption,
        player,             # Player instance
    ) -> list[str]:
        """Apply initial class selection to player."""
        from character import EvolutionTrack
        player.set_class(class_option.name, grade_index=0)
        player.class_track.free_points = class_option.free_points_per_level

        # Store fixed/free point rates on player for future level-ups
        player._class_fixed_per_level = class_option.fixed_points_per_level
        player._class_free_per_level  = class_option.free_points_per_level

        # Grant initial base skill for this class (inferior rarity)
        base_skill = self._generate_base_skill(class_option.name, "class")
        if base_skill:
            from character import Skill
            player.add_skill(Skill(
                name         = base_skill["name"],
                description  = base_skill["description"],
                rarity       = "inferior",
                skill_type   = base_skill.get("type", "passive"),
                source       = class_option.name,
            ))

        self.action_history.append(f"chose_class:{class_option.name}")

        return [
            f"Class selected: {class_option.name}",
            f"  {class_option.description}",
            f"  Fixed stat points per level: {class_option.fixed_points_per_level}",
            f"  Free stat points per level:  {class_option.free_points_per_level}",
        ]

    def _generate_base_skill(self, source_name: str, source_type: str) -> dict:
        """Generate an inferior-rarity base skill for a class/profession/race."""
        result = _call_claude_json(
            "Generate a base (inferior rarity) passive skill for a class in Kyros. "
            "It should be a fundamental ability that defines the class at its most basic level. "
            "Output ONLY JSON with keys: name (string), description (string, 1 sentence), "
            "type (string: active/passive/ritual).",
            [{"role": "user", "content":
              f"Source: {source_name} ({source_type})"}],
            max_tokens=150,
        )
        return result


    # ─────────────────────────────────────────────────────────────────────
    #  GRADE CAP REACHED — TRIGGER EVOLUTION
    # ─────────────────────────────────────────────────────────────────────

    def on_grade_cap_reached(
        self,
        track:   str,    # "class" | "profession" | "race"
        player,
    ) -> list[str]:
        """
        Called when a track reaches its grade max level.
        Generates an evolution quest and starts the decay grace period timer.
        Returns notifications.
        """
        self.evolution_ready[track] = True
        notifications = [
            f"[EVOLUTION READY] Your {track} has reached its grade maximum!",
            f"  Complete the evolution quest and then type 'evolve {track}' when ready.",
            f"  Warning: Waiting more than 1 day to evolve will cause stat decay.",
        ]

        # Generate evolution quest via QuestSystem
        if self.quest_system:
            quest = self._generate_evolution_quest(track, player)
            if quest:
                self.quest_system.accept_quest(quest, self.world_sim)
                notifications.append(
                    f"[EVOLUTION QUEST] {quest.title} — added to active quests."
                )

        # NOTE: Grace period timer is NOT started here.
        # It starts only when ALL required evolution quests are complete
        # and the player has not yet evolved. See on_evolution_quest_completed().

        return notifications

    def on_evolution_quest_completed(
        self,
        track:  str,
        player,
    ) -> list[str]:
        """
        Called by QuestSystem when an evolution quest is completed.
        Checks whether ALL required evolution quests are now done.
        If yes, starts the single shared grace period timer.
        A missing profession counts as complete by default.
        """
        notifications = [
            f"[EVOLUTION QUEST COMPLETE] Your {track} evolution quest is done.",
            f"  Type 'evolve {track}' whenever you are ready.",
        ]

        if self._all_evolution_quests_complete(player):
            notifications.append(
                "[WARNING] All evolution quests are complete. "
                "You have 1 day to evolve before stat decay begins."
            )
            # Start the single shared grace period timer
            if self.world_sim and not self._grace_timer_active():
                self.world_sim.add_timer(
                    timer_id  = f"decay_grace_{self.player_name}",
                    category  = "event",
                    entity_id = self.player_name,
                    duration  = DECAY_GRACE_PERIOD,
                    payload   = {
                        "event_type": "evolution_decay_start",
                        "player":     self.player_name,
                        # No single track — decay hits all ready tracks at once
                    },
                )

        return notifications

    def _all_evolution_quests_complete(self, player) -> bool:
        """
        Returns True if all required evolution quests are complete.
        Class and race are always required.
        Profession is required only if the player has a profession track.
        No profession = profession quest complete by default.
        """
        required_tracks = ["class", "race"]
        if player.profession_track:
            required_tracks.append("profession")

        for track in required_tracks:
            if not self._is_evolution_quest_complete(track):
                return False
        return True

    def _grace_timer_active(self) -> bool:
        """Check if the grace period timer is already running."""
        if not self.world_sim:
            return False
        return self.world_sim.get_timer(
            f"decay_grace_{self.player_name}"
        ) is not None

    def _generate_evolution_quest(self, track: str, player) -> object:
        """Generate an evolution quest via QuestSystem."""
        if not self.quest_system:
            return None

        track_obj = getattr(player, f"{track}_track", None)
        if not track_obj:
            return None

        spec = EvolutionQuestSpec(
            track        = track,
            current_name = track_obj.name,
            current_grade= track_obj.grade_index,
            player_level = track_obj.level,
            player_race  = player.race,
            player_class = player.class_track.name if player.class_track else "none",
            flavor_context = (
                f"Skills: {[s.name for s in player.skills[:5]]}, "
                f"Recent actions: {self.action_history[-5:]}"
            ),
        )

        quest = self.quest_system.generate_quest(
            npc_name       = f"Evolution Spirit ({track_obj.name})",
            npc_location   = "inner_realm",
            player_level   = spec.player_level,
            player_grade   = spec.current_grade,
            player_race    = spec.player_race,
            player_class   = spec.player_class,
            player_guild_rank = 0,
            world_context  = {
                "evolution_track": track,
                "current_name":    spec.current_name,
                "current_grade":   GRADE_NAMES[spec.current_grade],
                "is_evolution":    True,
                "no_failure":      True,
                "flavor":          spec.flavor_context,
            },
            source = "evolution",
        )
        if quest:
            quest.penalty.can_abandon          = False
            quest.penalty.permadeath           = False
            quest.penalty.death_penalty        = False
            quest.is_timed                     = False
            quest._is_evolution_quest          = True
            quest._evolution_track             = track
        return quest


    # ─────────────────────────────────────────────────────────────────────
    #  EVOLVE COMMAND — player types 'evolve class/profession/race'
    # ─────────────────────────────────────────────────────────────────────

    def handle_evolve_command(
        self,
        track:  str,    # "class" | "profession" | "race"
        player,
    ) -> tuple[list[str], bool]:
        """
        Handle player typing 'evolve class', 'evolve profession', or 'evolve race'.
        Returns (notifications, should_pause_world).

        Validates:
        - Evolution quest for this track is complete
        - Track is at grade max level
        Then generates options and pauses world for selection.
        """
        if track not in ("class", "profession", "race"):
            return [f"Unknown track '{track}'. Use: evolve class / evolve profession / evolve race"], False

        track_obj = getattr(player, f"{track}_track", None)
        if not track_obj:
            return [f"You have no {track} to evolve."], False

        # Check evolution quest completion
        if not self._is_evolution_quest_complete(track):
            return [
                f"[EVOLUTION] Your {track} evolution quest is not yet complete.",
                f"  Check your active quests for details.",
            ], False

        # Check grade cap
        if not track_obj.is_at_grade_max:
            return [
                f"[EVOLUTION] Your {track} has not reached the grade maximum yet.",
                f"  Current level: {track_obj.level} / {track_obj.grade_max_level}",
            ], False

        # Generate options and pause world
        self.evolution_paused = True
        notifications = [
            f"[EVOLUTION] Preparing {track} evolution...",
            f"  The world is paused while you make your choices.",
        ]

        if track == "class":
            options, notes = self._generate_class_options(player)
            self._pending_class_options = options
            notifications.extend(notes)
        elif track == "profession":
            options, notes = self._generate_profession_options(player)
            self._pending_prof_options = options
            notifications.extend(notes)
        elif track == "race":
            options, notes = self._generate_race_options(player)
            self._pending_race_options = options
            notifications.extend(notes)

        return notifications, True   # True = world should pause

    def _is_evolution_quest_complete(self, track: str) -> bool:
        """Check if the evolution quest for this track is complete."""
        if not self.quest_system:
            return True  # no quest system = no gating
        for quest in self.quest_system.completed_quests:
            if (getattr(quest, "_is_evolution_quest", False)
                    and getattr(quest, "_evolution_track", "") == track):
                return True
        return False

    def _generate_class_options(
        self,
        player,
    ) -> tuple[list[ClassOption], list[str]]:
        """
        AI-generate 3-4 evolved class options based on current class,
        skills the player has picked, and action history.
        Only shows options the player qualifies for.
        """
        track = player.class_track
        _class_ctx = json.dumps({
            "current_class":  track.name,
            "current_grade":  GRADE_NAMES[track.grade_index],
            "next_grade":     GRADE_NAMES[min(track.grade_index + 1, len(GRADE_NAMES)-1)],
            "player_race":    player.race,
            "skill_history":  self.skill_history[-10:],
            "action_history": self.action_history[-10:],
            "skills":         [s.name for s in player.skills],
            "schema": {
                "name":                    "string",
                "description":             "string (2-3 sentences; MUST state if race-specific and which race)",
                "rarity":                  "string (inferior/common/uncommon/rare/epic/legendary/mythic/divine)",
                "is_race_specific":        "bool",
                "required_race":           "string or empty",
                "stat_focus":              "list of 2-3 stat names",
                "fixed_points_per_level":  "int",
                "free_points_per_level":   "int",
                "evolution_quest_preview": "string (1 sentence hint at what evolution will require)",
            },
        })
        result = _call_claude_json(
            "Generate 3-4 evolved class options for a person in Kyros. "
            "Each option must branch logically from the current class. "
            "Skill history and action history influence which options are available — "
            "only generate options the player's history qualifies them for. "
            "If a class is race-specific, the description MUST state this clearly "
            "and list the required race. "
            "Output ONLY JSON: a list of class objects.",
            [{"role": "user", "content": _class_ctx}],
            max_tokens=1000,
        )

        options = []
        raw_options = result if isinstance(result, list) else []
        for opt in raw_options:
            co = ClassOption(
                name          = opt.get("name", "Unknown Class"),
                description   = opt.get("description", ""),
                rarity        = opt.get("rarity", "common"),
                is_race_specific = bool(opt.get("is_race_specific", False)),
                required_race = opt.get("required_race", ""),
                stat_focus    = opt.get("stat_focus", []),
                fixed_points_per_level = int(opt.get("fixed_points_per_level", 3)),
                free_points_per_level  = int(opt.get("free_points_per_level", 1)),
                evolution_quest_preview= opt.get("evolution_quest_preview", ""),
            )
            # Filter race-specific options
            if co.is_race_specific and co.required_race.lower() != player.race.lower():
                continue
            options.append(co)

        notifications = self._format_options_display("class", options)
        return options, notifications

    def _generate_profession_options(
        self,
        player,
    ) -> tuple[list[ClassOption], list[str]]:
        """Generate 3-4 evolved profession options."""
        track = player.profession_track
        if not track:
            # No profession yet — generate first profession options
            current_name = "none"
            current_grade = 0
        else:
            current_name  = track.name
            current_grade = track.grade_index

        _prof_ctx = json.dumps({
            "current_profession": current_name,
            "current_grade":      GRADE_NAMES[current_grade],
            "player_class":       player.class_track.name if player.class_track else "none",
            "player_race":        player.race,
            "skill_history":      self.skill_history[-10:],
            "action_history":     self.action_history[-10:],
            "schema": {
                "name":                    "string",
                "description":             "string",
                "rarity":                  "string",
                "is_race_specific":        "bool",
                "required_race":           "string or empty",
                "stat_focus":              "list of 2-3 stat names",
                "fixed_points_per_level":  "int",
                "free_points_per_level":   "int",
                "evolution_quest_preview": "string",
            },
        })
        result = _call_claude_json(
            "Generate 3-4 profession options for a person in Kyros. "
            "Professions are crafting/social/economic roles (blacksmith, alchemist, merchant, etc.). "
            "Base options on the player's class, skills, and action history. "
            "If a profession is race-specific, the description MUST state this clearly. "
            "Output ONLY JSON: a list of profession objects.",
            [{"role": "user", "content": _prof_ctx}],
            max_tokens=1000,
        )

        options = []
        raw = result if isinstance(result, list) else []
        for opt in raw:
            co = ClassOption(
                name          = opt.get("name", "Unknown Profession"),
                description   = opt.get("description", ""),
                rarity        = opt.get("rarity", "common"),
                is_race_specific = bool(opt.get("is_race_specific", False)),
                required_race = opt.get("required_race", ""),
                stat_focus    = opt.get("stat_focus", []),
                fixed_points_per_level = int(opt.get("fixed_points_per_level", 2)),
                free_points_per_level  = int(opt.get("free_points_per_level", 1)),
                evolution_quest_preview= opt.get("evolution_quest_preview", ""),
            )
            if co.is_race_specific and co.required_race.lower() != player.race.lower():
                continue
            options.append(co)

        notifications = self._format_options_display("profession", options)
        return options, notifications

    def _generate_race_options(
        self,
        player,
    ) -> tuple[list[ClassOption], list[str]]:
        """
        Generate race evolution option.
        99% chance: tier upgrade of current race.
        1% chance: offer one AI-generated alternative race.
        """
        track       = player.race_track
        notifications = []

        # Roll for race change
        if random.random() < RACE_CHANGE_CHANCE:
            alt_race = self._generate_alternative_race(player)
            if alt_race:
                self.pending_race_offer = alt_race
                notifications.append(
                    f"[RARE] A rare opportunity has appeared! "
                    f"You may change your race to {alt_race.name}."
                )
                notifications.append(f"  {alt_race.description}")
                notifications.append(
                    f"  Type 'evolve race accept' to change race, "
                    f"or 'evolve race skip' to evolve your current race normally."
                )
                return [alt_race], notifications

        # Normal race tier upgrade
        result = _call_claude_json(
            "Generate the next tier evolution of a race in Kyros. "
            "The evolved race is the same race at a higher tier, with greater power. "
            "Output ONLY JSON with keys: name (string), description (string, 2 sentences, "
            "must state if it is race-specific for any classes), "
            "rarity (string), stat_focus (list), "
            "fixed_points_per_level (int), free_points_per_level (int).",
            [{"role": "user", "content": json.dumps({
                "current_race":  track.name,
                "current_grade": GRADE_NAMES[track.grade_index],
                "next_grade":    GRADE_NAMES[min(track.grade_index+1, len(GRADE_NAMES)-1)],
                "player_class":  player.class_track.name if player.class_track else "none",
            })}],
            max_tokens=300,
        )

        opt = ClassOption(
            name          = result.get("name", f"{track.name} ({GRADE_NAMES[track.grade_index+1]})"),
            description   = result.get("description", f"An evolved {track.name}."),
            rarity        = result.get("rarity", "common"),
            stat_focus    = result.get("stat_focus", []),
            fixed_points_per_level = int(result.get("fixed_points_per_level", 2)),
            free_points_per_level  = int(result.get("free_points_per_level", 1)),
        )
        notifications.extend(self._format_options_display("race", [opt]))
        return [opt], notifications

    def _generate_alternative_race(self, player) -> Optional[ClassOption]:
        """Generate one AI-determined alternative race for the 1% race change offer."""
        result = _call_claude_json(
            "Generate one alternative race a person in Kyros could change to. "
            "The race must logically fit the player's history and actions. "
            "It must exist somewhere in the game world. "
            "The description MUST clearly state if this race is required for any "
            "specific classes (race-specific classes). "
            "Output ONLY JSON with keys: name, description, rarity, stat_focus (list), "
            "is_race_specific (bool), required_race (empty string), "
            "fixed_points_per_level (int), free_points_per_level (int).",
            [{"role": "user", "content": json.dumps({
                "current_race":   player.race,
                "player_class":   player.class_track.name if player.class_track else "none",
                "skill_history":  self.skill_history[-10:],
                "action_history": self.action_history[-10:],
                "blessing":       player.blessing.god_name if player.blessing else None,
            })}],
            max_tokens=400,
        )
        if not result or not isinstance(result, dict):
            return None
        return ClassOption(
            name          = result.get("name", "Unknown Race"),
            description   = result.get("description", ""),
            rarity        = result.get("rarity", "uncommon"),
            stat_focus    = result.get("stat_focus", []),
            fixed_points_per_level = int(result.get("fixed_points_per_level", 2)),
            free_points_per_level  = int(result.get("free_points_per_level", 1)),
        )

    def _format_options_display(
        self,
        track:   str,
        options: list[ClassOption],
    ) -> list[str]:
        """Format evolution options for player display."""
        lines = [f"\n=== {track.title()} Evolution Options ==="]
        for i, opt in enumerate(options, 1):
            lines.append(f"\n  [{i}] [{opt.rarity.upper()}] {opt.name}")
            lines.append(f"      {opt.description}")
            if opt.stat_focus:
                lines.append(f"      Primary stats: {', '.join(opt.stat_focus)}")
            lines.append(
                f"      Points/level: {opt.fixed_points_per_level} fixed, "
                f"{opt.free_points_per_level} free"
            )
            if opt.evolution_quest_preview:
                lines.append(f"      Next evolution: {opt.evolution_quest_preview}")
        lines.append(f"\nType 'evolve {track} <number>' to select.")
        return lines


    # ─────────────────────────────────────────────────────────────────────
    #  SELECTION — player types 'evolve class 2' etc.
    # ─────────────────────────────────────────────────────────────────────

    def select_evolution(
        self,
        track:  str,
        choice: int | str,    # 1-based index or "accept"/"skip" for race
        player,
    ) -> list[str]:
        """
        Apply a chosen evolution option to the player.
        Advances grade, grants stats, clears decay, checks perfect evolution.
        Resumes world simulation after completion.
        """
        notifications = []

        if track == "class":
            opts = self._pending_class_options
        elif track == "profession":
            opts = self._pending_prof_options
        elif track == "race":
            if choice == "accept" and self.pending_race_offer:
                return self._apply_race_change(player)
            elif choice == "skip":
                opts = self._pending_race_options
                choice = 1
            else:
                opts = self._pending_race_options
        else:
            return [f"Unknown track: {track}"]

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(opts):
                return [f"Invalid choice. Pick 1–{len(opts)}."]
            selected = opts[idx]
        except (ValueError, TypeError):
            return ["Invalid choice. Enter a number."]

        notifications.extend(
            self._apply_evolution(track, selected, player)
        )

        # Clear pending options and resume world
        self._pending_class_options = []
        self._pending_prof_options  = []
        self._pending_race_options  = []
        self.pending_race_offer     = None
        self.evolution_ready[track] = False
        self.evolution_paused       = False

        return notifications

    def _apply_evolution(
        self,
        track:    str,
        option:   ClassOption,
        player,
    ) -> list[str]:
        """Apply an evolution: advance grade, grant stat points, clear decay."""
        from character import EvolutionTrack, Skill

        track_obj = getattr(player, f"{track}_track", None)
        old_grade = track_obj.grade_index if track_obj else 0
        new_grade = old_grade + 1

        notifications = [
            f"[EVOLVED] {option.name} — {GRADE_NAMES[old_grade]} → {GRADE_NAMES[new_grade]}!"
        ]

        # Advance grade
        if track_obj:
            track_obj.name        = option.name
            track_obj.grade_index = new_grade
        elif track == "profession":
            player.set_profession(option.name, new_grade)
            track_obj = player.profession_track

        # Update per-level point rates
        attr_fixed = f"_{track}_fixed_per_level"
        attr_free  = f"_{track}_free_per_level"
        setattr(player, attr_fixed, option.fixed_points_per_level)
        setattr(player, attr_free,  option.free_points_per_level)

        # Check perfect evolution
        is_perfect = player.check_perfect_evolution()
        if is_perfect:
            bonus = player.get_perfect_evolution_bonus()
            player.free_points += bonus
            notifications.append(
                f"[PERFECT EVOLUTION!] All three tracks evolved at grade maximum!"
            )
            notifications.append(f"  + {bonus} free stat points")
            self.perfect_evolutions[GRADE_NAMES[old_grade]] = \
                self.perfect_evolutions.get(GRADE_NAMES[old_grade], 0) + 1
        else:
            # 3/4 normal stat bonus
            partial_bonus = int(player.get_perfect_evolution_bonus() * 0.75)
            if partial_bonus > 0:
                player.free_points += partial_bonus
                notifications.append(f"  + {partial_bonus} free stat points (3/4 bonus)")

        # Clear all decay stacks for this track's stats
        cleared = self._clear_decay_for_track(track, player)
        if cleared:
            notifications.append(
                f"  Stat decay cleared: {', '.join(cleared)}"
            )

        # Grant base skill for new grade
        base_skill_data = self._generate_base_skill(option.name, track)
        if base_skill_data:
            player.add_skill(Skill(
                name        = base_skill_data["name"],
                description = base_skill_data["description"],
                rarity      = "inferior",
                skill_type  = base_skill_data.get("type", "passive"),
                source      = option.name,
            ))
            notifications.append(f"  Base skill granted: {base_skill_data['name']}")

        # Record action for future AI context
        self.action_history.append(f"evolved_{track}:{option.name}:{GRADE_NAMES[new_grade]}")

        return notifications

    def _apply_race_change(self, player) -> list[str]:
        """Handle the rare 1% race change at evolution."""
        from character import EvolutionTrack

        opt       = self.pending_race_offer
        old_race  = player.race
        new_race  = opt.name

        notifications = [
            f"[RACE CHANGE] {old_race} → {new_race}!"
        ]

        # Determine if current class is race-specific and must change
        class_changes = self._check_class_race_compatibility(
            player, new_race, notifications
        )

        player.race                = new_race
        player.race_track.name     = new_race
        player.race_track.grade_index += 1

        if class_changes:
            notifications.extend(class_changes)

        # Clear race decay
        cleared = self._clear_decay_for_track("race", player)
        if cleared:
            notifications.append(f"  Stat decay cleared: {', '.join(cleared)}")

        self.pending_race_offer     = None
        self.evolution_ready["race"]= False
        self.evolution_paused       = False

        self.action_history.append(f"race_changed:{old_race}→{new_race}")
        return notifications

    def _check_class_race_compatibility(
        self,
        player,
        new_race:      str,
        notifications: list[str],
    ) -> list[str]:
        """
        If the player's current class is race-specific and incompatible
        with the new race, AI determines how the class changes.
        """
        if not player.class_track:
            return []

        result = _call_claude_json(
            "A person in Kyros is changing race. Determine if their current class "
            "is compatible with the new race, and if not, what class they transition to. "
            "Output ONLY JSON with keys: compatible (bool), "
            "new_class (string or null), reason (string).",
            [{"role": "user", "content": json.dumps({
                "current_class": player.class_track.name,
                "old_race":      player.race,
                "new_race":      new_race,
            })}],
            max_tokens=200,
        )

        if result.get("compatible", True):
            return []

        new_class = result.get("new_class")
        reason    = result.get("reason", "")
        notes     = [f"  Class changed: {player.class_track.name} → {new_class}"]
        notes.append(f"  Reason: {reason}")

        if new_class:
            player.class_track.name = new_class

        return notes


    # ─────────────────────────────────────────────────────────────────────
    #  SKILL PICKS
    # ─────────────────────────────────────────────────────────────────────

    def check_skill_pick_milestone(
        self,
        track:         str,
        current_level: int,
        grade_index:   int,
        player,
    ) -> list[str]:
        """
        Called on every level-up. Checks if this level is a skill pick milestone.
        Skill picks happen every N levels (per grade interval), NOT at grade max.
        Returns notifications if a pick is available.
        """
        interval = SKILL_PICK_INTERVAL.get(grade_index, 5)
        grade_start = 0 if grade_index == 0 else EVOLUTION_THRESHOLDS[grade_index]
        levels_into_grade = current_level - grade_start

        if levels_into_grade <= 0:
            return []
        if levels_into_grade % interval != 0:
            return []
        # Don't give a pick at grade max (that's evolution)
        if current_level >= GRADE_MAX_LEVELS[grade_index]:
            return []

        # Generate skill options
        options = self._generate_skill_options(track, grade_index, player)
        if not options:
            return []

        self.pending_skill_picks.append({
            "track":   track,
            "level":   current_level,
            "options": options,
        })

        notifications = [f"[SKILL PICK] Level {current_level} milestone!"]
        notifications.extend(self._format_skill_options(options))
        notifications.append("Type 'skill pick <number>' to choose.")
        return notifications

    def _generate_skill_options(
        self,
        track:       str,
        grade_index: int,
        player,
    ) -> list[SkillOption]:
        """
        AI-generate 3-4 skill options.
        Most will be inferior rarity, a few common, maybe 1 uncommon.
        """
        track_obj = getattr(player, f"{track}_track", None)
        source    = track_obj.name if track_obj else track

        _skill_ctx = json.dumps({
            "source":        source,
            "track":         track,
            "grade":         GRADE_NAMES[grade_index],
            "player_race":   player.race,
            "player_class":  player.class_track.name if player.class_track else "none",
            "existing_skills": [s.name for s in player.skills],
            "skill_history": self.skill_history[-5:],
            "schema": {
                "name":           "string",
                "description":    "string (1-2 sentences)",
                "rarity":         "string (inferior/common/uncommon only at this grade)",
                "skill_type":     "string (active/passive/ritual)",
                "preview_effect": "string (brief mechanical preview)",
            },
        })
        result = _call_claude_json(
            "Generate 3-4 skill options for a person in Kyros at a skill milestone. "
            "RARITY DISTRIBUTION: most skills should be 'inferior' rarity, "
            "1-2 may be 'common', at most 1 may be 'uncommon'. "
            "Higher rarity skills should be meaningfully more powerful. "
            "Output ONLY JSON: a list of skill objects.",
            [{"role": "user", "content": _skill_ctx}],
            max_tokens=700,
        )

        options = []
        raw = result if isinstance(result, list) else []
        for s in raw:
            options.append(SkillOption(
                name           = s.get("name", "Unknown Skill"),
                description    = s.get("description", ""),
                rarity         = s.get("rarity", "inferior"),
                skill_type     = s.get("skill_type", "passive"),
                source         = source,
                preview_effect = s.get("preview_effect", ""),
            ))
        return options

    def _format_skill_options(self, options: list[SkillOption]) -> list[str]:
        lines = []
        for i, opt in enumerate(options, 1):
            lines.append(f"  [{i}] [{opt.rarity.upper()}] {opt.name} ({opt.skill_type})")
            lines.append(f"      {opt.description}")
            if opt.preview_effect:
                lines.append(f"      Effect: {opt.preview_effect}")
        return lines

    def select_skill(
        self,
        choice: int,
        player,
    ) -> list[str]:
        """Apply skill pick selection."""
        from character import Skill

        if not self.pending_skill_picks:
            return ["No skill picks pending."]

        pick    = self.pending_skill_picks[0]
        options = pick["options"]

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(options):
                return [f"Invalid choice. Pick 1–{len(options)}."]
            selected = options[idx]
        except (ValueError, TypeError):
            return ["Invalid choice. Enter a number."]

        player.add_skill(Skill(
            name        = selected.name,
            description = selected.description,
            rarity      = selected.rarity,
            skill_type  = selected.skill_type,
            source      = selected.source,
        ))
        self.skill_history.append(selected.name)
        self.pending_skill_picks.pop(0)

        notifications = [f"Skill learned: [{selected.rarity.upper()}] {selected.name}"]
        notifications.append(f"  {selected.description}")

        # Remaining picks
        if self.pending_skill_picks:
            notifications.append(
                f"  {len(self.pending_skill_picks)} skill pick(s) remaining."
            )

        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  STAT DECAY
    # ─────────────────────────────────────────────────────────────────────

    def on_evolution_decay_start(self, player) -> list[str]:
        """
        Called by WorldSimulation timer when the shared grace period expires.
        Begins decay on all tracks that are evolution-ready but not yet evolved.
        A single timer covers all three tracks simultaneously.
        """
        # Determine which tracks are ready (quest complete, not yet evolved)
        ready_tracks = [
            t for t in ("class", "profession", "race")
            if self.evolution_ready.get(t)
            and self._is_evolution_quest_complete(t)
        ]
        if not ready_tracks:
            return []

        all_stats = []
        now = time.time()
        for track in ready_tracks:
            stats = self._get_primary_stats_for_track(track, player)
            for stat in stats:
                # Avoid duplicate decay stacks for the same stat
                already_tracked = any(d.stat == stat for d in self.decay_stacks)
                if already_tracked:
                    continue
                base_val = getattr(player.stats, stat, 0.0)
                self.decay_stacks.append(DecayStack(
                    stat          = stat,
                    percent_lost  = 0.0,
                    stacks        = 0,
                    started_at    = now,
                    last_stack_at = now,
                    original_base = base_val,
                ))
                all_stats.append(stat)

        if not all_stats:
            return []

        tracks_str = ", ".join(ready_tracks)
        return [
            f"[WARNING] You have delayed evolving too long! ({tracks_str})",
            f"  Stat decay has begun. Affected stats: {', '.join(all_stats)}",
            f"  Evolve all pending tracks to stop the decay.",
        ]

    def apply_daily_decay(self, player) -> list[str]:
        """
        Called once per IRL day (by WorldSimulation timer or game loop).
        Applies one additional -1% stack to each decaying stat.
        """
        notifications = []
        now = time.time()

        for decay in self.decay_stacks:
            # Only apply if at least 1 day since last stack
            if (now - decay.last_stack_at) < DECAY_TICK_INTERVAL:
                continue

            decay.stacks       += 1
            decay.percent_lost += DECAY_RATE_PER_DAY
            decay.last_stack_at = now

            # Apply to base stat
            current = getattr(player.stats, decay.stat, 0.0)
            reduction = decay.original_base * DECAY_RATE_PER_DAY
            new_val   = max(1.0, current - reduction)
            setattr(player.stats, decay.stat, new_val)

            notifications.append(
                f"[DECAY] {decay.stat.capitalize()}: -{DECAY_RATE_PER_DAY*100:.0f}% "
                f"(stack {decay.stacks}, total lost: {decay.percent_lost*100:.0f}%)"
            )

        return notifications

    def _clear_decay_for_track(self, track: str, player) -> list[str]:
        """
        Clear all decay stacks and restore stats when a track evolves.
        Returns list of restored stat names.
        """
        stats   = self._get_primary_stats_for_track(track, player)
        cleared = []

        remaining = []
        for decay in self.decay_stacks:
            if decay.stat in stats:
                # Restore the lost amount
                current = getattr(player.stats, decay.stat, 0.0)
                restored = decay.original_base * decay.percent_lost
                setattr(player.stats, decay.stat, current + restored)
                cleared.append(decay.stat)
            else:
                remaining.append(decay)

        self.decay_stacks = remaining
        return cleared

    def _get_primary_stats_for_track(self, track: str, player) -> list[str]:
        """Return the 2-3 primary stats for a given track based on class/profession/race."""
        track_obj = getattr(player, f"{track}_track", None)
        if not track_obj:
            return ["strength"]

        # Ask AI which stats are primary for this class/profession/race
        result = _call_claude_json(
            "Which 2-3 stats are most important for this class/profession/race in Kyros? "
            "Output ONLY JSON: a list of stat names from: "
            "strength/constitution/dexterity/agility/intelligence/wisdom/perception/charisma.",
            [{"role": "user", "content":
              f"{track}: {track_obj.name}"}],
            max_tokens=80,
        )
        if isinstance(result, list) and result:
            return result[:3]
        return ["strength", "constitution"]


    # ─────────────────────────────────────────────────────────────────────
    #  GODS AND BLESSINGS
    # ─────────────────────────────────────────────────────────────────────

    def get_god_record(self, god_name: str) -> GodRecord:
        if god_name not in self.god_records:
            self.god_records[god_name] = GodRecord(god_name=god_name)
        return self.god_records[god_name]

    def receive_blessing(
        self,
        god_name:      str,
        blessing_level:str,
        is_primordial: bool,
        player,
        unlocks:       list[str] = None,
        skill_data:    dict      = None,
    ) -> list[str]:
        """
        Player receives a blessing from a god.
        If they already have a blessing from a different god, they become
        a heretic toward the abandoned god.
        """
        from character import Blessing, Skill

        notifications = []

        # Handle existing blessing → heretic branding
        if player.blessing and player.blessing.god_name != god_name:
            old_god = player.blessing.god_name
            notifications.extend(self._brand_heretic(old_god, player))

        # Build blessing object
        skill = None
        if blessing_level == "true" and skill_data:
            skill = Skill(
                name        = skill_data.get("name", "Divine Gift"),
                description = skill_data.get("description", ""),
                rarity      = "divine",
                skill_type  = skill_data.get("type", "active"),
                source      = god_name,
            )
            player.add_skill(skill)

        blessing = Blessing(
            god_name   = god_name,
            level      = blessing_level,
            description= f"Blessed by {god_name}: {blessing_level} blessing.",
            unlocks    = unlocks or [],
            skill      = skill,
            is_chosen  = (blessing_level == "true"),
        )

        notes = player.receive_blessing(blessing)
        notifications.extend(notes)

        # Update god record
        rec = self.get_god_record(god_name)
        rec.blessing_level = blessing_level
        rec.is_chosen      = (blessing_level == "true")

        # Chosen: update available class/profession/race options
        if blessing_level == "true":
            notifications.append(
                f"As the Chosen of {god_name}, new class and race options "
                f"related to {god_name} will become available."
            )

        return notifications

    def _brand_heretic(self, god_name: str, player) -> list[str]:
        """Brand player as heretic toward a god."""
        rec              = self.get_god_record(god_name)
        rec.is_heretic   = True
        rec.heretic_since= time.time()
        rec.favor        = min(rec.favor, -500)

        notes = player.set_heretic(True)
        notes.insert(0, f"You have abandoned {god_name}.")
        notes.append(
            f"  {god_name} will not forget this. "
            f"Heretic status can only be cleared if {god_name} forgives you."
        )
        return notes

    def check_heretic_pardon(
        self,
        god_name: str,
        player,
        world_sim=None,
    ) -> list[str]:
        """
        AI governs the god. Only the god decides if they forgive.
        This method asks the AI whether the god forgives based on
        the player's actions since becoming a heretic.
        """
        rec = self.get_god_record(god_name)
        if not rec.is_heretic:
            return [f"You are not a heretic toward {god_name}."]

        time_since = time.time() - rec.heretic_since
        days_since = time_since / 86400

        result = _call_claude_json(
            "You are a god in Kyros deciding whether to forgive a heretic. "
            "The god has its own personality and values. "
            "Output ONLY JSON with keys: forgives (bool), "
            "reason (string, 1-2 sentences, in the god's voice).",
            [{"role": "user", "content": json.dumps({
                "god_name":       god_name,
                "days_as_heretic":round(days_since, 1),
                "player_favor":   rec.favor,
                "player_actions": self.action_history[-10:],
                "player_skills":  self.skill_history[-5:],
            })}],
            max_tokens=200,
        )

        if result.get("forgives", False):
            rec.is_heretic   = False
            rec.heretic_since= 0.0
            rec.favor        = max(0.0, rec.favor + 200)
            player.set_heretic(False)
            return [
                f"{god_name}: \"{result.get('reason', 'You are forgiven.')}\"",
                f"Your heretic status with {god_name} has been cleared.",
            ]

        return [
            f"{god_name}: \"{result.get('reason', 'You are not yet forgiven.')}\"",
        ]

    def pray_at_temple(
        self,
        god_name:   str,
        player,
        ritual_type:str = "prayer",
    ) -> list[str]:
        """
        Player prays at a temple or performs a ritual.
        AI governing the god decides response.
        God may initiate dialogue, grant favor, offer a task, or ignore.
        """
        rec = self.get_god_record(god_name)
        rec.interactions += 1
        rec.favor         = min(1000, rec.favor + 5)

        result = _call_claude_json(
            "A person is praying at your temple in Kyros. "
            "The god you are portraying has a distinct personality. "
            "Decide how to respond. The god may: respond warmly, coldly, offer a task, "
            "grant favor, initiate dialogue about Chosen status, or simply remain silent. "
            "If the player meets conditions for Chosen consideration, you may hint at it. "
            "Output ONLY JSON with keys: "
            "response_type (string: dialogue/favor/task/silence/chosen_hint), "
            "message (string: what the god says or does, 1-3 sentences), "
            "favor_change (float: -50 to 50), "
            "task (string or null: brief task description if response_type is task).",
            [{"role": "user", "content": json.dumps({
                "god_name":       god_name,
                "ritual_type":    ritual_type,
                "player_level":   player.level,
                "player_race":    player.race,
                "player_class":   player.class_track.name if player.class_track else "none",
                "player_favor":   rec.favor,
                "is_heretic":     rec.is_heretic,
                "is_chosen":      rec.is_chosen,
                "interactions":   rec.interactions,
                "player_actions": self.action_history[-5:],
                "has_blessing":   player.blessing.god_name if player.blessing else None,
            })}],
            max_tokens=300,
        )

        notifications = []
        response_type = result.get("response_type", "silence")
        message       = result.get("message", "...")
        favor_change  = float(result.get("favor_change", 0))
        task          = result.get("task")

        rec.favor = max(-1000, min(1000, rec.favor + favor_change))

        if response_type != "silence":
            notifications.append(f"{god_name}: \"{message}\"")
        else:
            notifications.append(f"Your prayers are met with silence.")

        if task:
            notifications.append(f"  Task offered: {task}")

        if response_type == "chosen_hint":
            notifications.append(
                f"  You sense that {god_name} is watching you closely..."
            )

        return notifications

    def check_chosen_eligibility(
        self,
        god_name:  str,
        player,
        chosen_registry: dict,  # god_name → ChosenRecord
    ) -> list[str]:
        """
        AI governing the god decides if this player should become the new Chosen.
        Called when: no current Chosen exists for this god AND energy cooldown has passed.
        """
        existing = chosen_registry.get(god_name)
        if existing and existing.player_name:
            return []  # already has a Chosen

        rec = self.get_god_record(god_name)

        result = _call_claude_json(
            "You are a god in Kyros deciding whether a person is worthy to become "
            "their Chosen. Being Chosen costs the god a great deal of energy — "
            "they consider it carefully. Only one True Blessing can exist per god. "
            "Output ONLY JSON with keys: chosen (bool), "
            "reason (string, in the god's voice, 1-2 sentences).",
            [{"role": "user", "content": json.dumps({
                "god_name":       god_name,
                "player_level":   player.level,
                "player_race":    player.race,
                "player_class":   player.class_track.name if player.class_track else "none",
                "player_favor":   rec.favor,
                "interactions":   rec.interactions,
                "player_actions": self.action_history[-20:],
                "player_skills":  self.skill_history[-10:],
                "blessing_level": rec.blessing_level,
            })}],
            max_tokens=200,
        )

        if not result.get("chosen", False):
            return []

        # Generate the True Blessing skill
        skill_data = _call_claude_json(
            "Generate a unique non-combat skill for a True Blessing in Kyros. "
            "It should reflect both the god's domain and the player's history. "
            "Output ONLY JSON with keys: name (string), description (string), "
            "type (string: active/passive/ritual).",
            [{"role": "user", "content": json.dumps({
                "god_name":       god_name,
                "player_actions": self.action_history[-20:],
                "player_class":   player.class_track.name if player.class_track else "none",
            })}],
            max_tokens=200,
        )

        notes = self.receive_blessing(
            god_name       = god_name,
            blessing_level = "true",
            is_primordial  = rec.is_primordial,
            player         = player,
            skill_data     = skill_data if isinstance(skill_data, dict) else {},
        )

        chosen_record = ChosenRecord(
            god_name     = god_name,
            player_name  = self.player_name,
            chosen_since = time.time(),
        )
        chosen_registry[god_name] = chosen_record

        notes.insert(0, f"{god_name}: \"{result.get('reason', 'You are my Chosen.')}\"")
        return notes

    def on_chosen_died(
        self,
        god_name:          str,
        player_name:       str,
        time_as_chosen:    float,
        chosen_registry:   dict,
    ) -> None:
        """
        Called when a Chosen player dies via permadeath.
        Sets energy cooldown for the god based on how long the Chosen lasted.
        """
        record = chosen_registry.get(god_name)
        if not record:
            return

        if time_as_chosen < DECAY_GRACE_PERIOD:
            # Died quickly — long cooldown
            cooldown = TRUE_BLESSING_QUICK_DEATH_COOLDOWN
        else:
            cooldown = TRUE_BLESSING_NORMAL_COOLDOWN

        record.player_name             = ""
        record.energy_cooldown_until   = time.time() + cooldown
        record.last_chosen_duration    = time_as_chosen


    # ─────────────────────────────────────────────────────────────────────
    #  LEVEL-UP STAT POINTS
    # ─────────────────────────────────────────────────────────────────────

    def on_level_up(
        self,
        track:   str,
        level:   int,
        player,
    ) -> list[str]:
        """
        Called on every level-up for a track.
        Grants fixed stat points (auto-applied to primary stats)
        and free stat points (added to pool).
        Also checks skill pick milestones.
        """
        notifications = []
        track_obj = getattr(player, f"{track}_track", None)
        if not track_obj:
            return notifications

        grade_index = track_obj.grade_index

        # Fixed stat points — applied automatically to primary stats
        fixed_per_level = getattr(player, f"_{track}_fixed_per_level", 3)
        if fixed_per_level > 0:
            primary = self._get_primary_stats_for_track(track, player)
            points_each = fixed_per_level // max(1, len(primary))
            remainder   = fixed_per_level % max(1, len(primary))
            for i, stat in enumerate(primary):
                pts = points_each + (1 if i < remainder else 0)
                if pts > 0 and hasattr(player.stats, stat):
                    setattr(player.stats, stat,
                            getattr(player.stats, stat) + pts)
            notifications.append(
                f"  + {fixed_per_level} fixed stat points "
                f"({', '.join(primary)})"
            )

        # Free stat points
        free_per_level = getattr(player, f"_{track}_free_per_level", 1)
        if free_per_level > 0:
            player.free_points += free_per_level
            notifications.append(f"  + {free_per_level} free stat point(s)")

        # Skill pick milestone check
        skill_notes = self.check_skill_pick_milestone(
            track, level, grade_index, player
        )
        notifications.extend(skill_notes)

        # Apply pending decay ticks
        decay_notes = self.apply_daily_decay(player)
        notifications.extend(decay_notes)

        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  RECORD ACTION (called by game loop)
    # ─────────────────────────────────────────────────────────────────────

    def record_action(self, action: str) -> None:
        """
        Record a player action for AI context.
        Used by class/skill generation to determine what options the player qualifies for.
        """
        self.action_history.append(action)
        if len(self.action_history) > 200:
            self.action_history = self.action_history[-200:]


    # ─────────────────────────────────────────────────────────────────────
    #  LAND OWNERSHIP HOOK (full system is #22)
    # ─────────────────────────────────────────────────────────────────────

    def can_build_shrine(self, player, land_manager=None) -> tuple[bool, str]:
        """
        Check if player can build a shrine at their current land.
        Requires land ownership. Full land system is #22.
        """
        if land_manager is None:
            return False, "Land ownership system not yet implemented."
        owns_land = land_manager.player_owns_land(self.player_name)
        if not owns_land:
            return False, "You must own land to build a shrine."
        return True, "You may build a shrine on your land."

    def build_shrine(
        self,
        god_name:    str,
        location:    str,
        player,
        land_manager=None,
    ) -> list[str]:
        """
        Build a shrine to a god on player-owned land.
        Hooks into land management system (#22).
        """
        can, reason = self.can_build_shrine(player, land_manager)
        if not can:
            return [reason]

        rec = self.get_god_record(god_name)
        rec.favor = min(1000, rec.favor + 50)

        return [
            f"Shrine to {god_name} built at {location}.",
            f"  {god_name}'s favor has increased.",
            f"  Worshippers may now pray here.",
        ]


    # ─────────────────────────────────────────────────────────────────────
    #  SERIALIZE / DESERIALIZE
    # ─────────────────────────────────────────────────────────────────────

    def serialize(self) -> dict:
        return {
            "player_name":      self.player_name,
            "evolution_ready":  self.evolution_ready,
            "skill_history":    self.skill_history,
            "action_history":   self.action_history[-100:],
            "decay_stacks": [
                {
                    "stat":          d.stat,
                    "percent_lost":  d.percent_lost,
                    "stacks":        d.stacks,
                    "started_at":    d.started_at,
                    "last_stack_at": d.last_stack_at,
                    "original_base": d.original_base,
                }
                for d in self.decay_stacks
            ],
            "god_records": {
                name: {
                    "god_name":      rec.god_name,
                    "is_primordial": rec.is_primordial,
                    "blessing_level":rec.blessing_level,
                    "is_chosen":     rec.is_chosen,
                    "is_heretic":    rec.is_heretic,
                    "heretic_since": rec.heretic_since,
                    "favor":         rec.favor,
                    "interactions":  rec.interactions,
                }
                for name, rec in self.god_records.items()
            },
            "pending_skill_picks": [
                {
                    "track": p["track"],
                    "level": p["level"],
                    "options": [
                        {
                            "name":           o.name,
                            "description":    o.description,
                            "rarity":         o.rarity,
                            "skill_type":     o.skill_type,
                            "source":         o.source,
                            "preview_effect": o.preview_effect,
                        }
                        for o in p["options"]
                    ],
                }
                for p in self.pending_skill_picks
            ],
            "perfect_evolutions": self.perfect_evolutions,
        }

    @classmethod
    def deserialize(cls, data: dict, quest_system=None, world_sim=None) -> "EvolutionSystem":
        es = cls(
            player_name  = data.get("player_name", ""),
            quest_system = quest_system,
            world_sim    = world_sim,
        )
        es.evolution_ready    = data.get("evolution_ready",
                                         {"class":False,"profession":False,"race":False})
        es.skill_history      = data.get("skill_history", [])
        es.action_history     = data.get("action_history", [])
        es.perfect_evolutions = data.get("perfect_evolutions", {})

        for d in data.get("decay_stacks", []):
            es.decay_stacks.append(DecayStack(
                stat          = d["stat"],
                percent_lost  = d["percent_lost"],
                stacks        = d["stacks"],
                started_at    = d["started_at"],
                last_stack_at = d["last_stack_at"],
                original_base = d["original_base"],
            ))

        for name, rec_data in data.get("god_records", {}).items():
            rec = GodRecord(
                god_name       = rec_data["god_name"],
                is_primordial  = rec_data.get("is_primordial", False),
                blessing_level = rec_data.get("blessing_level"),
                is_chosen      = rec_data.get("is_chosen", False),
                is_heretic     = rec_data.get("is_heretic", False),
                heretic_since  = rec_data.get("heretic_since", 0.0),
                favor          = rec_data.get("favor", 0.0),
                interactions   = rec_data.get("interactions", 0),
            )
            es.god_records[name] = rec

        for p in data.get("pending_skill_picks", []):
            options = [
                SkillOption(
                    name           = o["name"],
                    description    = o["description"],
                    rarity         = o["rarity"],
                    skill_type     = o["skill_type"],
                    source         = o["source"],
                    preview_effect = o.get("preview_effect", ""),
                )
                for o in p["options"]
            ]
            es.pending_skill_picks.append({
                "track":   p["track"],
                "level":   p["level"],
                "options": options,
            })

        return es