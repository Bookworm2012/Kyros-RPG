"""
kyros/quest.py

QuestSystem — all quest logic for Kyros.

Owns:
- Quest objects (objectives, rewards, penalties, chains, branches)
- Quest generation (AI, per NPC offer)
- Quest tracking (active, completed, failed)
- Event hooks (on_kill, on_item_obtained, on_location_visited, etc.)
- Status display (full details, search, completed log)
- Repeating quest cooldowns and reputation diminishing returns
- Adventurers guild rank gating
- Permadeath quest consequences

Timers live in WorldSimulation. QuestSystem registers them there.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Callable

from dotenv import load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

REPEAT_COOLDOWN          = 60 * 60 * 24        # 1 real day in seconds
REPEAT_DISAPPEAR_COUNT   = 10                   # quest disappears after this many completions
REPEAT_DISAPPEAR_COOLDOWN= 60 * 60 * 24 * 7    # 1 real week
COMPLETED_DISPLAY_COUNT  = 10                   # show most recent N in log
REPUTATION_DIMINISH_RATE = 0.85                 # rep gain multiplied per repeat completion

# Adventurers guild rank ladder (index = rank level)
ADVENTURERS_RANKS = ["Copper", "Bronze", "Silver", "Gold", "Platinum", "Diamond"]

# Objective types
OBJECTIVE_TYPES = [
    "kill",          # kill X of monster type (killing blow required)
    "deliver",       # deliver item to NPC
    "escort",        # escort NPC to location (NPC death = auto fail)
    "find_location", # travel to location and bring back map
    "talk",          # speak with NPC
    "craft",         # craft item yourself (profession check)
    "collect",       # obtain items (any method)
]

# Completion styles that affect branching
COMPLETION_STYLES = [
    "killed",        # objective completed by killing
    "spared",        # objective completed by sparing
    "stealthy",      # completed without being detected
    "diplomatic",    # completed through dialogue
    "destructive",   # completed by destroying something
    "merciful",      # completed without unnecessary harm
]


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude_json(
    system:     str,
    messages:   list,
    max_tokens: int = 800,
) -> dict | list:
    """Call Claude API and return parsed JSON."""
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


def _npc_hour_to_display(npc_seconds: float) -> str:
    """Convert real seconds remaining to NPC time display string."""
    npc_minutes = npc_seconds * 60
    if npc_minutes < 60:
        return f"{int(npc_minutes)} NPC minutes"
    npc_hours = npc_minutes / 60
    if npc_hours < 24:
        return f"{npc_hours:.1f} NPC hours"
    return f"{npc_hours/24:.1f} NPC days"


# ─────────────────────────────────────────────────────────────────────────────
#  OBJECTIVE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Objective:
    """A single quest objective."""
    obj_id:         str
    obj_type:       str                  # from OBJECTIVE_TYPES
    description:    str
    target:         str                  # monster name, NPC name, location, item name
    required_count: int   = 1
    current_count:  int   = 0
    completed:      bool  = False
    failed:         bool  = False

    # Escort-specific
    escort_npc:     Optional[str] = None
    escort_dest:    Optional[str] = None

    # Craft-specific
    requires_profession: Optional[str] = None
    requires_profession_grade: int = 0  # minimum grade index

    # Location-specific
    requires_map_note: bool = False      # find_location requires map materialization

    # Tracking: how the objective was completed (affects branching)
    completion_style: Optional[str] = None

    @property
    def progress_str(self) -> str:
        if self.required_count <= 1:
            return "✓" if self.completed else "○"
        return f"{self.current_count}/{self.required_count}"

    @property
    def is_done(self) -> bool:
        return self.completed or self.current_count >= self.required_count

    def advance(self, amount: int = 1, style: str = None) -> bool:
        """Advance progress. Returns True if just completed."""
        if self.completed or self.failed:
            return False
        self.current_count = min(self.required_count, self.current_count + amount)
        if self.current_count >= self.required_count:
            self.completed        = True
            self.completion_style = style
            return True
        return False

    def fail(self) -> None:
        self.failed = True


# ─────────────────────────────────────────────────────────────────────────────
#  REWARD
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QuestReward:
    """Rewards for completing a quest."""
    gold:               float = 0.0
    xp:                 float = 0.0
    items:              list[dict] = field(default_factory=list)   # [{name, rarity, quantity}]
    reputation_gains:   list[dict] = field(default_factory=list)   # [{tier, location, amount}]
    relationship_gains: list[dict] = field(default_factory=list)   # [{npc_name, amount}]
    skill_unlock:       Optional[str] = None
    title:              Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
#  PENALTY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QuestPenalty:
    """Penalties applied on quest failure or abandonment."""
    gold_loss:          float = 0.0
    xp_loss:            float = 0.0
    reputation_losses:  list[dict] = field(default_factory=list)   # [{tier, location, amount}]
    relationship_damage:list[dict] = field(default_factory=list)   # [{npc_name, amount}]
    wanted_increase:    float = 0.0
    jail_time:          float = 0.0   # NPC seconds
    permadeath:         bool  = False  # save deleted entirely
    death_penalty:      bool  = False  # die with full death penalty, respawn at start
    can_abandon:        bool  = True
    abandon_is_permadeath: bool = False
    abandon_is_death:   bool  = False


# ─────────────────────────────────────────────────────────────────────────────
#  CHAIN BRANCH
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChainBranch:
    """
    A branch in a quest chain.
    Triggered by the completion_style of the previous quest's key objective.
    The player does not know branches exist — they are a hidden consequence.
    """
    trigger_style:  str        # completion_style that triggers this branch
    next_quest_id:  str        # quest ID to generate/load
    branch_hint:    str = ""   # internal note for AI generation


# ─────────────────────────────────────────────────────────────────────────────
#  QUEST
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Quest:
    """
    A single quest. May have multiple related objectives.
    May chain to another quest on completion.
    May branch based on how objectives were completed.
    """
    quest_id:       str
    title:          str
    description:    str
    giver_npc:      str                   # NPC who gave the quest
    giver_location: str
    objectives:     list[Objective]       = field(default_factory=list)
    reward:         QuestReward           = field(default_factory=QuestReward)
    penalty:        QuestPenalty          = field(default_factory=QuestPenalty)

    # Timing
    is_timed:       bool  = False
    time_limit:     float = 0.0           # real seconds
    accepted_at:    float = 0.0           # set when accepted
    timer_id:       str   = ""            # WorldSimulation timer ID

    # Chain/branch
    is_chain:       bool  = False
    chain_position: int   = 1             # position in chain
    chain_total:    int   = 1
    chain_id:       str   = ""
    branches:       list[ChainBranch] = field(default_factory=list)
    next_quest_id:  Optional[str]     = None   # default next (no branch)

    # Repeating
    is_repeating:   bool  = False
    repeat_key:     str   = ""            # unique key for cooldown tracking

    # Guild gating
    requires_guild_rank: int = 0          # index into ADVENTURERS_RANKS (0 = Copper)
    requires_guild:      bool = False

    # State
    status:         str   = "offered"     # offered | active | completed | failed | abandoned
    completed_at:   float = 0.0
    failed_at:      float = 0.0
    completion_style: Optional[str] = None   # how the key objective was completed

    # Source
    source:         str   = "npc"         # npc | board | guild

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status in ("failed", "abandoned")

    @property
    def all_objectives_done(self) -> bool:
        return all(o.is_done for o in self.objectives)

    @property
    def any_objective_failed(self) -> bool:
        return any(o.failed for o in self.objectives)

    @property
    def time_remaining(self) -> float:
        """Real seconds remaining. 0 if not timed or expired."""
        if not self.is_timed or not self.accepted_at:
            return 0.0
        elapsed = time.time() - self.accepted_at
        return max(0.0, self.time_limit - elapsed)

    @property
    def key_objective(self) -> Optional[Objective]:
        """The first non-deliver objective — used for branch detection."""
        for o in self.objectives:
            if o.obj_type != "deliver":
                return o
        return self.objectives[0] if self.objectives else None

    def display(self, verbose: bool = True) -> str:
        """Format quest for status menu display."""
        lines = [f"[{self.status.upper()}] {self.title}"]
        if self.is_chain:
            lines.append(f"  Chain: Part {self.chain_position} of {self.chain_total}")
        lines.append(f"  From: {self.giver_npc} ({self.giver_location})")
        if verbose:
            lines.append(f"  {self.description}")
        lines.append("  Objectives:")
        for obj in self.objectives:
            status = "✓" if obj.completed else ("✗" if obj.failed else obj.progress_str)
            lines.append(f"    [{status}] {obj.description}")
        if self.is_timed and self.is_active:
            remaining = self.time_remaining
            lines.append(f"  Time remaining: {_npc_hour_to_display(remaining)}")
        if verbose:
            lines.append(f"  Reward: {self.reward.gold:.0f}g, {self.reward.xp:.0f}xp"
                         + (f", {', '.join(i['name'] for i in self.reward.items)}"
                            if self.reward.items else ""))
            if self.penalty.can_abandon:
                abandon_warn = ""
                if self.penalty.abandon_is_permadeath:
                    abandon_warn = " [PERMADEATH — save will be deleted]"
                elif self.penalty.abandon_is_death:
                    abandon_warn = " [DEATH PENALTY on abandon]"
                lines.append(f"  Abandonable: Yes{abandon_warn}")
            else:
                lines.append("  Abandonable: No")
            if self.penalty.permadeath:
                lines.append("  ⚠ FAILURE = PERMADEATH")
            elif self.penalty.death_penalty:
                lines.append("  ⚠ FAILURE = DEATH PENALTY")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  QUEST SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class QuestSystem:
    """
    Manages all quests for a player.
    One QuestSystem instance per player.
    """

    def __init__(self, player_name: str, world_simulation=None):
        self.player_name         = player_name
        self.world_sim           = world_simulation   # WorldSimulation reference

        self.active_quests:      list[Quest]  = []
        self.completed_quests:   list[Quest]  = []
        self.failed_quests:      list[Quest]  = []

        # Repeating quest tracking
        # repeat_key → {count, last_completed, disappeared_until}
        self.repeat_tracker:     dict[str, dict] = {}

        # Reputation diminishing returns per (quest_id, location)
        self.rep_diminish:       dict[str, float] = {}

        # Quest generation counter for unique IDs
        self._quest_counter:     int = 0

        # Event listeners — game loop calls these
        # Registered externally if needed
        self._listeners:         list[Callable] = []

    # ─────────────────────────────────────────────────────────────────────
    #  QUEST GENERATION
    # ─────────────────────────────────────────────────────────────────────

    def generate_quest(
        self,
        npc_name:      str,
        npc_location:  str,
        player_level:  int,
        player_grade:  int,        # grade index (0=G, 1=F, etc.)
        player_race:   str,
        player_class:  str,
        player_guild_rank: int,    # adventurers guild rank index
        world_context: dict = None,
        chain_context: dict = None,  # if this is a chained quest
        is_repeating:  bool = False,
        source:        str  = "npc",
    ) -> Optional[Quest]:
        """
        AI-generate a quest at the moment an NPC offers it.
        Scales difficulty to player level and grade.
        Returns None if generation fails.
        """
        world_ctx = world_context or {}
        chain_ctx = chain_context or {}

        system_prompt = (
            "You are a quest giver in the world of Kyros. "
            "Generate a quest that fits the player's level and is narratively interesting. "
            "Objectives should be thematically related (e.g. kill monster, then deliver its core). "
            "Output ONLY valid JSON with no preamble or markdown."
        )

        user_content = json.dumps({
            "npc_name":        npc_name,
            "npc_location":    npc_location,
            "player_level":    player_level,
            "player_grade":    ["G","F","E","D","C","B","A","S","God","Godking","Primordial"][player_grade],
            "player_race":     player_race,
            "player_class":    player_class,
            "player_guild_rank": ADVENTURERS_RANKS[min(player_guild_rank, 5)],
            "is_repeating":    is_repeating,
            "is_chain":        bool(chain_ctx),
            "chain_context":   chain_ctx,
            "world_context":   world_ctx,
            "schema": {
                "title":       "string",
                "description": "string (2-3 sentences, narrative flavor)",
                "objectives": [
                    {
                        "obj_type":       "one of: kill/deliver/escort/find_location/talk/craft/collect",
                        "description":    "string",
                        "target":         "string (monster name, NPC name, item name, location name)",
                        "required_count": "int",
                        "escort_npc":     "string or null",
                        "escort_dest":    "string or null",
                        "requires_profession": "string or null",
                        "requires_profession_grade": "int 0-10",
                        "requires_map_note": "bool (only for find_location)",
                    }
                ],
                "reward": {
                    "gold":               "float",
                    "xp":                 "float",
                    "items":              [{"name":"string","rarity":"string","quantity":"int"}],
                    "reputation_gains":   [{"tier":"string","location":"string","amount":"float"}],
                    "relationship_gains": [{"npc_name":"string","amount":"float"}],
                    "skill_unlock":       "string or null",
                    "title":              "string or null",
                },
                "penalty": {
                    "gold_loss":           "float",
                    "xp_loss":             "float",
                    "reputation_losses":   [{"tier":"string","location":"string","amount":"float"}],
                    "relationship_damage": [{"npc_name":"string","amount":"float"}],
                    "wanted_increase":     "float",
                    "jail_time":           "float (NPC seconds, 0 if none)",
                    "permadeath":          "bool (save deleted — use rarely for serious quests)",
                    "death_penalty":       "bool (die and respawn at start — use for serious quests)",
                    "can_abandon":         "bool",
                    "abandon_is_permadeath": "bool",
                    "abandon_is_death":    "bool",
                },
                "is_timed":       "bool",
                "time_limit":     "float (real seconds, 0 if not timed)",
                "is_chain":       "bool",
                "chain_total":    "int (how many quests in this chain, 1 if not chain)",
                "branches": [
                    {
                        "trigger_style": "one of: killed/spared/stealthy/diplomatic/destructive/merciful",
                        "next_quest_id": "string (descriptive ID for next quest)",
                        "branch_hint":   "string (brief internal note for what that branch leads to)",
                    }
                ],
                "requires_guild_rank": "int 0-5 (0=Copper, 5=Diamond)",
                "requires_guild":      "bool",
                "guild_rank_name":     "string (rank name if requires_guild, else null)",
            }
        })

        result = _call_claude_json(
            system_prompt,
            [{"role": "user", "content": user_content}],
            max_tokens = 1200,
        )

        if not result or not isinstance(result, dict):
            return None

        return self._build_quest_from_ai(
            result, npc_name, npc_location, source, is_repeating, chain_ctx
        )

    def _build_quest_from_ai(
        self,
        data:          dict,
        npc_name:      str,
        npc_location:  str,
        source:        str,
        is_repeating:  bool,
        chain_ctx:     dict,
    ) -> Quest:
        """Construct a Quest object from AI-generated data."""
        self._quest_counter += 1
        quest_id = f"quest_{self._quest_counter}_{int(time.time())}"

        # Objectives
        objectives = []
        for i, obj_data in enumerate(data.get("objectives", [])):
            objectives.append(Objective(
                obj_id          = f"{quest_id}_obj_{i}",
                obj_type        = obj_data.get("obj_type", "kill"),
                description     = obj_data.get("description", ""),
                target          = obj_data.get("target", ""),
                required_count  = int(obj_data.get("required_count", 1)),
                escort_npc      = obj_data.get("escort_npc"),
                escort_dest     = obj_data.get("escort_dest"),
                requires_profession = obj_data.get("requires_profession"),
                requires_profession_grade = int(obj_data.get("requires_profession_grade", 0)),
                requires_map_note = bool(obj_data.get("requires_map_note", False)),
            ))

        # Reward
        r_data = data.get("reward", {})
        reward = QuestReward(
            gold               = float(r_data.get("gold", 0)),
            xp                 = float(r_data.get("xp", 0)),
            items              = r_data.get("items", []),
            reputation_gains   = r_data.get("reputation_gains", []),
            relationship_gains = r_data.get("relationship_gains", []),
            skill_unlock       = r_data.get("skill_unlock"),
            title              = r_data.get("title"),
        )

        # Penalty
        p_data = data.get("penalty", {})
        penalty = QuestPenalty(
            gold_loss           = float(p_data.get("gold_loss", 0)),
            xp_loss             = float(p_data.get("xp_loss", 0)),
            reputation_losses   = p_data.get("reputation_losses", []),
            relationship_damage = p_data.get("relationship_damage", []),
            wanted_increase     = float(p_data.get("wanted_increase", 0)),
            jail_time           = float(p_data.get("jail_time", 0)),
            permadeath          = bool(p_data.get("permadeath", False)),
            death_penalty       = bool(p_data.get("death_penalty", False)),
            can_abandon         = bool(p_data.get("can_abandon", True)),
            abandon_is_permadeath = bool(p_data.get("abandon_is_permadeath", False)),
            abandon_is_death    = bool(p_data.get("abandon_is_death", False)),
        )

        # Branches
        branches = []
        for b in data.get("branches", []):
            branches.append(ChainBranch(
                trigger_style = b.get("trigger_style", "killed"),
                next_quest_id = b.get("next_quest_id", ""),
                branch_hint   = b.get("branch_hint", ""),
            ))

        # Chain context
        chain_position = chain_ctx.get("position", 1)
        chain_total    = int(data.get("chain_total", 1))
        chain_id       = chain_ctx.get("chain_id", quest_id if data.get("is_chain") else "")

        repeat_key = f"{npc_name}_{npc_location}_{data.get('title','')}" if is_repeating else ""

        return Quest(
            quest_id             = quest_id,
            title                = data.get("title", "Unnamed Quest"),
            description          = data.get("description", ""),
            giver_npc            = npc_name,
            giver_location       = npc_location,
            objectives           = objectives,
            reward               = reward,
            penalty              = penalty,
            is_timed             = bool(data.get("is_timed", False)),
            time_limit           = float(data.get("time_limit", 0)),
            is_chain             = bool(data.get("is_chain", False)),
            chain_position       = chain_position,
            chain_total          = chain_total,
            chain_id             = chain_id,
            branches             = branches,
            is_repeating         = is_repeating,
            repeat_key           = repeat_key,
            requires_guild_rank  = int(data.get("requires_guild_rank", 0)),
            requires_guild       = bool(data.get("requires_guild", False)),
            source               = source,
            status               = "offered",
        )


    # ─────────────────────────────────────────────────────────────────────
    #  RANK GATING
    # ─────────────────────────────────────────────────────────────────────

    def can_accept(
        self,
        quest:             Quest,
        player_guild_rank: int,
        has_guild:         bool,
    ) -> tuple[bool, str]:
        """
        Check if player can accept this quest.
        Returns (can_accept, reason_if_not).
        Player can see all quests but cannot accept above their rank.
        """
        if quest.requires_guild and not has_guild:
            return False, "You must be a member of the Adventurers Guild."
        if quest.requires_guild and player_guild_rank < quest.requires_guild_rank:
            required = ADVENTURERS_RANKS[min(quest.requires_guild_rank, 5)]
            current  = ADVENTURERS_RANKS[min(player_guild_rank, 5)]
            return False, (
                f"This quest requires {required} rank. "
                f"Your current rank is {current}."
            )
        if quest.is_repeating:
            tracker = self.repeat_tracker.get(quest.repeat_key, {})
            disappeared_until = tracker.get("disappeared_until", 0)
            if time.time() < disappeared_until:
                remaining = disappeared_until - time.time()
                days = remaining / 86400
                return False, f"This quest is unavailable for {days:.1f} more days."
            last_completed = tracker.get("last_completed", 0)
            if (time.time() - last_completed) < REPEAT_COOLDOWN:
                hours = (REPEAT_COOLDOWN - (time.time() - last_completed)) / 3600
                return False, f"You can repeat this quest in {hours:.1f} hours."
        return True, ""


    # ─────────────────────────────────────────────────────────────────────
    #  ACCEPT / ABANDON / FAIL
    # ─────────────────────────────────────────────────────────────────────

    def accept_quest(
        self,
        quest:      Quest,
        world_sim=None,
    ) -> list[str]:
        """
        Accept a quest. Starts timer if timed.
        Returns notification strings.
        """
        quest.status      = "active"
        quest.accepted_at = time.time()
        self.active_quests.append(quest)

        notifications = [f"Quest accepted: {quest.title}"]

        if quest.is_timed and quest.time_limit > 0:
            ws = world_sim or self.world_sim
            if ws:
                timer_id = ws.add_timer(
                    timer_id  = f"quest_{quest.quest_id}",
                    category  = "quest",
                    entity_id = self.player_name,
                    duration  = quest.time_limit,
                    payload   = {
                        "quest_id":    quest.quest_id,
                        "quest_name":  quest.title,
                        "penalties":   {
                            "gold_loss":        quest.penalty.gold_loss,
                            "reputation_loss":  bool(quest.penalty.reputation_losses),
                            "relationship_damage": bool(quest.penalty.relationship_damage),
                            "npc_name":         quest.giver_npc,
                            "permadeath":       quest.penalty.permadeath,
                            "death_penalty":    quest.penalty.death_penalty,
                        },
                    },
                )
                quest.timer_id = timer_id.timer_id if hasattr(timer_id, "timer_id") else str(timer_id)
            notifications.append(
                f"  Time limit: {_npc_hour_to_display(quest.time_limit)}"
            )

        if quest.penalty.permadeath:
            notifications.append("  ⚠ WARNING: Failure will permanently delete your save.")
        elif quest.penalty.death_penalty:
            notifications.append("  ⚠ WARNING: Failure will kill your character.")
        if quest.penalty.can_abandon:
            if quest.penalty.abandon_is_permadeath:
                notifications.append("  ⚠ ABANDON WARNING: Abandoning will delete your save.")
            elif quest.penalty.abandon_is_death:
                notifications.append("  ⚠ ABANDON WARNING: Abandoning will kill your character.")
        else:
            notifications.append("  This quest cannot be abandoned.")

        return notifications

    def abandon_quest(
        self,
        quest_id: str,
        world_sim=None,
    ) -> tuple[list[str], str]:
        """
        Attempt to abandon a quest.
        Returns (notifications, consequence_type).
        consequence_type: "ok" | "death" | "permadeath" | "blocked"
        """
        quest = self._get_active(quest_id)
        if not quest:
            return [f"No active quest with ID {quest_id}."], "ok"

        if not quest.penalty.can_abandon:
            return ["This quest cannot be abandoned."], "blocked"

        notifications = [f"Quest abandoned: {quest.title}"]
        consequence   = "ok"

        if quest.penalty.abandon_is_permadeath:
            notifications.append("Your save is being deleted.")
            consequence = "permadeath"
        elif quest.penalty.abandon_is_death:
            notifications.append("You pay the ultimate price for abandoning your duty.")
            consequence = "death"
        else:
            # Apply normal failure penalties
            notifications.extend(self._describe_penalties(quest.penalty))

        quest.status    = "abandoned"
        quest.failed_at = time.time()
        self._move_to_failed(quest)
        self._cancel_timer(quest, world_sim)

        return notifications, consequence

    def _force_fail_quest(
        self,
        quest:    Quest,
        reason:   str,
        world_sim=None,
    ) -> tuple[list[str], str]:
        """
        Force-fail a quest (timer expired, escort NPC died, etc.).
        Returns (notifications, consequence_type).
        """
        notifications = [f"Quest failed: {quest.title}", f"  Reason: {reason}"]
        consequence   = "ok"

        if quest.penalty.permadeath:
            notifications.append("Your save is being deleted.")
            consequence = "permadeath"
        elif quest.penalty.death_penalty:
            notifications.append("You pay with your life.")
            consequence = "death"
        else:
            notifications.extend(self._describe_penalties(quest.penalty))

        quest.status    = "failed"
        quest.failed_at = time.time()
        self._move_to_failed(quest)
        self._cancel_timer(quest, world_sim)

        return notifications, consequence

    def _describe_penalties(self, penalty: QuestPenalty) -> list[str]:
        lines = []
        if penalty.gold_loss > 0:
            lines.append(f"  Lost {penalty.gold_loss:.0f} Gold.")
        if penalty.xp_loss > 0:
            lines.append(f"  Lost {penalty.xp_loss:.0f} XP.")
        if penalty.reputation_losses:
            lines.append("  Reputation decreased.")
        if penalty.relationship_damage:
            lines.append("  Relationships damaged.")
        if penalty.wanted_increase > 0:
            lines.append("  Wanted level increased.")
        if penalty.jail_time > 0:
            npc_minutes = penalty.jail_time / 60
            lines.append(f"  Sentenced to {npc_minutes:.0f} NPC minutes in jail.")
        return lines


    # ─────────────────────────────────────────────────────────────────────
    #  EVENT HOOKS — called by game loop
    # ─────────────────────────────────────────────────────────────────────

    def on_kill(
        self,
        monster_name:  str,
        style:         str = "killed",   # from COMPLETION_STYLES
        world_sim=None,
    ) -> list[str]:
        """
        Call when player lands killing blow.
        Advances kill objectives. Returns notifications.
        """
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if obj.obj_type == "kill" and obj.target.lower() == monster_name.lower():
                    just_completed = obj.advance(1, style)
                    notifications.append(
                        f"[{quest.title}] {obj.description}: {obj.progress_str}"
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_item_obtained(
        self,
        item_name: str,
        world_sim=None,
    ) -> list[str]:
        """Call when player obtains an item (collect objectives)."""
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if obj.obj_type == "collect" and obj.target.lower() == item_name.lower():
                    just_completed = obj.advance(1)
                    notifications.append(
                        f"[{quest.title}] {obj.description}: {obj.progress_str}"
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_item_delivered(
        self,
        item_name: str,
        npc_name:  str,
        world_sim=None,
    ) -> list[str]:
        """Call when player delivers an item to an NPC."""
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if (obj.obj_type == "deliver"
                        and obj.target.lower() == item_name.lower()
                        and quest.giver_npc.lower() == npc_name.lower()):
                    just_completed = obj.advance(1, "delivered")
                    notifications.append(
                        f"[{quest.title}] {obj.description}: {obj.progress_str}"
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_location_visited(
        self,
        location:  str,
        has_map_note: bool = False,
        world_sim=None,
    ) -> list[str]:
        """
        Call when player enters a location.
        Advances find_location objectives if map note exists.
        """
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if obj.obj_type == "find_location" and obj.target.lower() == location.lower():
                    if obj.requires_map_note and not has_map_note:
                        notifications.append(
                            f"[{quest.title}] You must record a map note here "
                            f"before this counts as found."
                        )
                        continue
                    just_completed = obj.advance(1, "explored")
                    notifications.append(
                        f"[{quest.title}] {obj.description}: {obj.progress_str}"
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_map_materialized(
        self,
        location:  str,
        npc_name:  str,
        world_sim=None,
    ) -> list[str]:
        """
        Call when player hands a materialized map to the quest giver.
        Completes find_location objectives.
        """
        notifications = []
        for quest in self.active_quests:
            if quest.giver_npc.lower() != npc_name.lower():
                continue
            for obj in quest.objectives:
                if (obj.obj_type == "find_location"
                        and obj.requires_map_note
                        and obj.target.lower() == location.lower()
                        and not obj.completed):
                    just_completed = obj.advance(1, "mapped")
                    notifications.append(
                        f"[{quest.title}] Map of {location} delivered to {npc_name}."
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_npc_talked(
        self,
        npc_name:  str,
        world_sim=None,
    ) -> list[str]:
        """Call when player speaks with an NPC."""
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if obj.obj_type == "talk" and obj.target.lower() == npc_name.lower():
                    just_completed = obj.advance(1, "diplomatic")
                    notifications.append(
                        f"[{quest.title}] {obj.description}: ✓"
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_item_crafted(
        self,
        item_name:        str,
        profession:       str,
        profession_grade: int,
        world_sim=None,
    ) -> list[str]:
        """Call when player crafts an item themselves."""
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if obj.obj_type != "craft":
                    continue
                if obj.target.lower() != item_name.lower():
                    continue
                # Check profession requirement
                if obj.requires_profession:
                    if profession.lower() != obj.requires_profession.lower():
                        notifications.append(
                            f"[{quest.title}] Requires {obj.requires_profession} "
                            f"to craft this item."
                        )
                        continue
                    if profession_grade < obj.requires_profession_grade:
                        notifications.append(
                            f"[{quest.title}] Requires {obj.requires_profession} "
                            f"grade {obj.requires_profession_grade} or higher."
                        )
                        continue
                just_completed = obj.advance(1, "crafted")
                notifications.append(
                    f"[{quest.title}] {obj.description}: ✓"
                )
                if just_completed:
                    notifications.extend(
                        self._check_quest_completion(quest, world_sim)
                    )
        return notifications

    def on_escort_npc_died(
        self,
        npc_name:  str,
        world_sim=None,
    ) -> list[str]:
        """Call when an escorted NPC dies. Auto-fails the quest."""
        notifications = []
        for quest in list(self.active_quests):
            for obj in quest.objectives:
                if obj.obj_type == "escort" and obj.escort_npc == npc_name:
                    obj.fail()
                    notes, _ = self._force_fail_quest(
                        quest, f"{npc_name} died.", world_sim
                    )
                    notifications.extend(notes)
        return notifications

    def on_escort_arrived(
        self,
        npc_name:  str,
        location:  str,
        world_sim=None,
    ) -> list[str]:
        """Call when escorted NPC reaches destination."""
        notifications = []
        for quest in self.active_quests:
            for obj in quest.objectives:
                if (obj.obj_type == "escort"
                        and obj.escort_npc == npc_name
                        and obj.escort_dest
                        and obj.escort_dest.lower() == location.lower()):
                    just_completed = obj.advance(1, "escorted")
                    notifications.append(
                        f"[{quest.title}] {npc_name} safely arrived at {location}."
                    )
                    if just_completed:
                        notifications.extend(
                            self._check_quest_completion(quest, world_sim)
                        )
        return notifications

    def on_quest_timer_expired(
        self,
        quest_id:  str,
        world_sim=None,
    ) -> tuple[list[str], str]:
        """
        Called by WorldSimulation when a quest timer fires.
        Returns (notifications, consequence_type).
        """
        quest = self._get_active(quest_id)
        if not quest:
            return [], "ok"
        return self._force_fail_quest(quest, "Time limit expired.", world_sim)


    # ─────────────────────────────────────────────────────────────────────
    #  COMPLETION
    # ─────────────────────────────────────────────────────────────────────

    def _check_quest_completion(
        self,
        quest:     Quest,
        world_sim=None,
    ) -> list[str]:
        """
        Check if all objectives are done. If so, complete the quest.
        Returns notifications.
        """
        if quest.any_objective_failed:
            notes, _ = self._force_fail_quest(quest, "An objective failed.", world_sim)
            return notes

        if not quest.all_objectives_done:
            return []

        return self._complete_quest(quest, world_sim)

    def _complete_quest(
        self,
        quest:     Quest,
        world_sim=None,
    ) -> list[str]:
        """Mark quest complete, grant rewards, handle chain/branch."""
        quest.status       = "completed"
        quest.completed_at = time.time()

        # Determine completion style from key objective
        key_obj = quest.key_objective
        if key_obj:
            quest.completion_style = key_obj.completion_style

        notifications = [f"Quest complete: {quest.title}! 🎉"]

        # Rewards
        notifications.extend(self._grant_rewards(quest.reward, quest))

        # Repeating tracker
        if quest.is_repeating and quest.repeat_key:
            self._update_repeat_tracker(quest)

        # Cancel timer
        self._cancel_timer(quest, world_sim)

        # Move to completed
        self._move_to_completed(quest)

        # Chain / branch — trigger next quest
        next_quest_data = self._resolve_chain(quest)
        if next_quest_data:
            notifications.append(
                f"A new quest has appeared: return to {quest.giver_npc}."
            )
            # Store pending chain quest for QuestSystem to offer on next NPC visit
            self._pending_chain = next_quest_data

        return notifications

    def _resolve_chain(self, quest: Quest) -> Optional[dict]:
        """
        Determine next quest in chain based on completion style.
        Returns dict with chain context, or None.
        Player never sees branch detection — it's hidden.
        """
        if not quest.is_chain and not quest.branches and not quest.next_quest_id:
            return None

        # Branch resolution — check completion style against branches
        if quest.branches and quest.completion_style:
            for branch in quest.branches:
                if branch.trigger_style == quest.completion_style:
                    return {
                        "chain_id":    quest.chain_id,
                        "position":    quest.chain_position + 1,
                        "branch_hint": branch.branch_hint,
                        "next_id":     branch.next_quest_id,
                        "giver_npc":   quest.giver_npc,
                        "giver_loc":   quest.giver_location,
                    }

        # Default chain (no branch matched or no branches)
        if quest.next_quest_id or (quest.is_chain and quest.chain_position < quest.chain_total):
            return {
                "chain_id":    quest.chain_id,
                "position":    quest.chain_position + 1,
                "branch_hint": "",
                "next_id":     quest.next_quest_id or "",
                "giver_npc":   quest.giver_npc,
                "giver_loc":   quest.giver_location,
            }
        return None

    def _grant_rewards(self, reward: QuestReward, quest: Quest) -> list[str]:
        """Return reward notification strings. Actual application done by game loop."""
        lines = []
        if reward.gold > 0:
            lines.append(f"  + {reward.gold:.0f} Gold")
        if reward.xp > 0:
            lines.append(f"  + {reward.xp:.0f} XP")
        for item in reward.items:
            lines.append(f"  + {item['name']} [{item.get('rarity','common')}]")
        for rep in reward.reputation_gains:
            # Apply diminishing returns for repeating quests
            amount = rep.get("amount", 0)
            if quest.is_repeating:
                key = f"{quest.repeat_key}_{rep.get('location','')}"
                mult = self.rep_diminish.get(key, 1.0)
                amount = amount * mult
                self.rep_diminish[key] = max(0.1, mult * REPUTATION_DIMINISH_RATE)
            lines.append(
                f"  + Reputation in {rep.get('location','')} "
                f"({rep.get('tier','')}: +{amount:.1f})"
            )
        for rel in reward.relationship_gains:
            lines.append(
                f"  + Relationship with {rel.get('npc_name','')}: "
                f"+{rel.get('amount',0):.0f}"
            )
        if reward.skill_unlock:
            lines.append(f"  + Skill unlocked: {reward.skill_unlock}")
        if reward.title:
            lines.append(f"  + Title earned: [{reward.title}]")
        return lines

    def _update_repeat_tracker(self, quest: Quest) -> None:
        key     = quest.repeat_key
        tracker = self.repeat_tracker.get(key, {"count": 0})
        tracker["count"]          = tracker.get("count", 0) + 1
        tracker["last_completed"] = time.time()
        if tracker["count"] >= REPEAT_DISAPPEAR_COUNT:
            tracker["disappeared_until"] = time.time() + REPEAT_DISAPPEAR_COOLDOWN
            tracker["count"]             = 0
        self.repeat_tracker[key] = tracker


    # ─────────────────────────────────────────────────────────────────────
    #  STATUS DISPLAY
    # ─────────────────────────────────────────────────────────────────────

    def show_active_quests(self) -> str:
        """Display all active quests with full details."""
        if not self.active_quests:
            return "No active quests."
        lines = ["=== Active Quests ==="]
        for quest in self.active_quests:
            lines.append(quest.display(verbose=True))
            lines.append("")
        return "\n".join(lines)

    def show_completed_log(self, search: str = None) -> str:
        """
        Show completed and failed quests log.
        Displays most recent 10. Supports search by name, giver,
        objective type, region, or source.
        """
        all_done = sorted(
            self.completed_quests + self.failed_quests,
            key     = lambda q: q.completed_at or q.failed_at or 0,
            reverse = True,
        )

        if search:
            search_lower = search.lower()
            all_done = [
                q for q in all_done if (
                    search_lower in q.title.lower()
                    or search_lower in q.giver_npc.lower()
                    or search_lower in q.giver_location.lower()
                    or search_lower in q.source.lower()
                    or any(search_lower in o.obj_type for o in q.objectives)
                    or any(search_lower in o.target.lower() for o in q.objectives)
                )
            ]

        display = all_done[:COMPLETED_DISPLAY_COUNT]

        if not display:
            return "No completed quests found." if not search else f"No quests matching '{search}'."

        lines = [f"=== Quest Log (showing {len(display)}) ==="]
        if search:
            lines[0] += f" — search: '{search}'"
        for quest in display:
            tag = "[FAILED]" if quest.status in ("failed","abandoned") else "[DONE]"
            ts  = time.strftime(
                "%Y-%m-%d",
                time.localtime(quest.completed_at or quest.failed_at or 0)
            )
            lines.append(f"{tag} {quest.title} ({ts})")
            lines.append(f"  From: {quest.giver_npc} — {quest.giver_location}")
            if quest.status in ("failed","abandoned"):
                lines.append(f"  Failed: {quest.status}")
            lines.append("")
        return "\n".join(lines)

    def show_quest_details(self, quest_id: str) -> str:
        """Show full details for a specific quest (active, completed, or failed)."""
        all_quests = (
            self.active_quests +
            self.completed_quests +
            self.failed_quests
        )
        for quest in all_quests:
            if quest.quest_id == quest_id:
                return quest.display(verbose=True)
        return f"Quest {quest_id} not found."


    # ─────────────────────────────────────────────────────────────────────
    #  UTILITY
    # ─────────────────────────────────────────────────────────────────────

    def _get_active(self, quest_id: str) -> Optional[Quest]:
        for q in self.active_quests:
            if q.quest_id == quest_id:
                return q
        return None

    def _move_to_completed(self, quest: Quest) -> None:
        if quest in self.active_quests:
            self.active_quests.remove(quest)
        self.completed_quests.append(quest)

    def _move_to_failed(self, quest: Quest) -> None:
        if quest in self.active_quests:
            self.active_quests.remove(quest)
        self.failed_quests.append(quest)

    def _cancel_timer(self, quest: Quest, world_sim=None) -> None:
        ws = world_sim or self.world_sim
        if ws and quest.timer_id:
            ws.remove_timer(quest.timer_id)
            quest.timer_id = ""

    def get_pending_chain(self) -> Optional[dict]:
        """
        Retrieve and clear a pending chained quest context.
        Called by NPC interaction system when player returns to quest giver.
        """
        chain = getattr(self, "_pending_chain", None)
        self._pending_chain = None
        return chain

    def serialize(self) -> dict:
        """Serialize quest system state for save/load."""
        def _quest_to_dict(q: Quest) -> dict:
            return {
                "quest_id":        q.quest_id,
                "title":           q.title,
                "description":     q.description,
                "giver_npc":       q.giver_npc,
                "giver_location":  q.giver_location,
                "status":          q.status,
                "is_timed":        q.is_timed,
                "time_limit":      q.time_limit,
                "accepted_at":     q.accepted_at,
                "completed_at":    q.completed_at,
                "failed_at":       q.failed_at,
                "is_chain":        q.is_chain,
                "chain_position":  q.chain_position,
                "chain_total":     q.chain_total,
                "chain_id":        q.chain_id,
                "is_repeating":    q.is_repeating,
                "repeat_key":      q.repeat_key,
                "requires_guild_rank": q.requires_guild_rank,
                "source":          q.source,
                "completion_style":q.completion_style,
                "objectives": [
                    {
                        "obj_id":        o.obj_id,
                        "obj_type":      o.obj_type,
                        "description":   o.description,
                        "target":        o.target,
                        "required_count":o.required_count,
                        "current_count": o.current_count,
                        "completed":     o.completed,
                        "failed":        o.failed,
                        "completion_style": o.completion_style,
                    }
                    for o in q.objectives
                ],
                "reward": {
                    "gold":               q.reward.gold,
                    "xp":                 q.reward.xp,
                    "items":              q.reward.items,
                    "reputation_gains":   q.reward.reputation_gains,
                    "relationship_gains": q.reward.relationship_gains,
                    "skill_unlock":       q.reward.skill_unlock,
                    "title":              q.reward.title,
                },
                "penalty": {
                    "gold_loss":            q.penalty.gold_loss,
                    "xp_loss":              q.penalty.xp_loss,
                    "reputation_losses":    q.penalty.reputation_losses,
                    "relationship_damage":  q.penalty.relationship_damage,
                    "wanted_increase":      q.penalty.wanted_increase,
                    "jail_time":            q.penalty.jail_time,
                    "permadeath":           q.penalty.permadeath,
                    "death_penalty":        q.penalty.death_penalty,
                    "can_abandon":          q.penalty.can_abandon,
                    "abandon_is_permadeath":q.penalty.abandon_is_permadeath,
                    "abandon_is_death":     q.penalty.abandon_is_death,
                },
            }

        return {
            "player_name":      self.player_name,
            "active_quests":    [_quest_to_dict(q) for q in self.active_quests],
            "completed_quests": [_quest_to_dict(q) for q in self.completed_quests],
            "failed_quests":    [_quest_to_dict(q) for q in self.failed_quests],
            "repeat_tracker":   self.repeat_tracker,
            "rep_diminish":     self.rep_diminish,
        }

    @classmethod
    def deserialize(cls, data: dict, world_sim=None) -> "QuestSystem":
        """Reconstruct QuestSystem from serialized data."""
        qs = cls(
            player_name      = data.get("player_name", ""),
            world_simulation = world_sim,
        )
        qs.repeat_tracker = data.get("repeat_tracker", {})
        qs.rep_diminish   = data.get("rep_diminish", {})

        def _dict_to_quest(d: dict) -> Quest:
            objectives = [
                Objective(
                    obj_id          = o["obj_id"],
                    obj_type        = o["obj_type"],
                    description     = o["description"],
                    target          = o["target"],
                    required_count  = o["required_count"],
                    current_count   = o["current_count"],
                    completed       = o["completed"],
                    failed          = o["failed"],
                    completion_style= o.get("completion_style"),
                )
                for o in d.get("objectives", [])
            ]
            r = d.get("reward", {})
            reward = QuestReward(
                gold               = r.get("gold", 0),
                xp                 = r.get("xp", 0),
                items              = r.get("items", []),
                reputation_gains   = r.get("reputation_gains", []),
                relationship_gains = r.get("relationship_gains", []),
                skill_unlock       = r.get("skill_unlock"),
                title              = r.get("title"),
            )
            p = d.get("penalty", {})
            penalty = QuestPenalty(
                gold_loss            = p.get("gold_loss", 0),
                xp_loss              = p.get("xp_loss", 0),
                reputation_losses    = p.get("reputation_losses", []),
                relationship_damage  = p.get("relationship_damage", []),
                wanted_increase      = p.get("wanted_increase", 0),
                jail_time            = p.get("jail_time", 0),
                permadeath           = p.get("permadeath", False),
                death_penalty        = p.get("death_penalty", False),
                can_abandon          = p.get("can_abandon", True),
                abandon_is_permadeath= p.get("abandon_is_permadeath", False),
                abandon_is_death     = p.get("abandon_is_death", False),
            )
            return Quest(
                quest_id        = d["quest_id"],
                title           = d["title"],
                description     = d["description"],
                giver_npc       = d["giver_npc"],
                giver_location  = d["giver_location"],
                objectives      = objectives,
                reward          = reward,
                penalty         = penalty,
                status          = d["status"],
                is_timed        = d.get("is_timed", False),
                time_limit      = d.get("time_limit", 0),
                accepted_at     = d.get("accepted_at", 0),
                completed_at    = d.get("completed_at", 0),
                failed_at       = d.get("failed_at", 0),
                is_chain        = d.get("is_chain", False),
                chain_position  = d.get("chain_position", 1),
                chain_total     = d.get("chain_total", 1),
                chain_id        = d.get("chain_id", ""),
                is_repeating    = d.get("is_repeating", False),
                repeat_key      = d.get("repeat_key", ""),
                requires_guild_rank = d.get("requires_guild_rank", 0),
                source          = d.get("source", "npc"),
                completion_style= d.get("completion_style"),
            )

        qs.active_quests    = [_dict_to_quest(d) for d in data.get("active_quests", [])]
        qs.completed_quests = [_dict_to_quest(d) for d in data.get("completed_quests", [])]
        qs.failed_quests    = [_dict_to_quest(d) for d in data.get("failed_quests", [])]
        return qs