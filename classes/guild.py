"""
kyros/guild.py

GuildSystem — all guild logic for Kyros.

Owns:
- Guild creation (grade/gold/item requirements, bureaucratic registration)
- Guild ranks (custom names, contribution thresholds, manual + auto promotion)
- Guild membership (multiple guilds per entity, NPC and player)
- Guild quests (contribution points, shared tracking)
- Guild wars (bounties, economic sabotage, NPC mercenaries, win conditions)
- Guild alliances (declared by leader)
- Guild halls (physical locations, protected by convention)
- Guild messaging (NPC dialogue system, rank-gated broadcasts)
- Guild bankruptcy (triggers world_simulation economic crisis)
- Guild dissolution (assets seized, members freed, name can be reinstated)
- Contribution points (used to purchase guild resources, affect rank)
- Bureaucracy (AI-generated per region/government, 3-10+ steps)

World rules:
- Guild halls are not destroyed by respectable kingdoms (reputation penalty if found out)
- Other guilds react to hall destruction based on their relationship with the kingdom
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Minimum grade index to found any guild (grade D = index 3)
GUILD_FOUND_MIN_GRADE    = 3

# Default bureaucracy step range
BUREAUCRACY_MIN_STEPS    = 3
BUREAUCRACY_MAX_STEPS    = 10

# Guild war: minimum duration before surrender allowed (real seconds)
GUILD_WAR_MIN_DURATION   = 60 * 60 * 24   # 1 IRL day

# Hall destruction reputation penalty
HALL_DESTRUCTION_REP_HIT = -500.0

# Contribution point costs for resources
RESOURCE_COST_BASE       = 100   # base cost for common guild resources

# Message delivery delay (NPC processes message within this window)
NPC_MESSAGE_RESPONSE_WINDOW = 60 * 60   # 1 IRL hour

# Inactivity threshold for demotion consideration (real seconds)
# Contribution points don't decay — but leader can manually demote inactive members


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GuildRank:
    """A single rank tier within a guild."""
    rank_index:          int
    name:                str
    contribution_required: int    # points needed to reach this rank
    permissions:         list[str] = field(default_factory=list)
    # permissions: "promote", "demote", "declare_war", "declare_alliance",
    #              "manage_hall", "issue_quest", "broadcast_message",
    #              "manage_resources", "dissolve_guild"


@dataclass
class GuildMember:
    """A member of a guild — player or NPC."""
    entity_name:         str
    is_player:           bool
    rank_index:          int       = 0
    contribution_points: int       = 0
    joined_at:           float     = field(default_factory=time.time)
    last_active:         float     = field(default_factory=time.time)
    is_founder:          bool      = False
    criminal_record:     list[str] = field(default_factory=list)
    # criminal_record: list of convictions relevant to guild standing


@dataclass
class BureaucracyStep:
    """A single step in the guild registration bureaucracy."""
    step_index:    int
    description:   str
    step_type:     str    # "fetch_item" | "pay_gold" | "wait" | "bribe" | "talk_npc"
    target:        str    # item name, NPC name, location, etc.
    cost:          float  = 0.0    # gold cost if applicable
    wait_duration: float  = 0.0    # NPC seconds to wait
    completed:     bool   = False
    can_bypass:    bool   = False   # can be skipped with gold/reputation
    bypass_cost:   float  = 0.0


@dataclass
class GuildRegistration:
    """
    Tracks a guild's registration process through government bureaucracy.
    AI-generated per region/government type.
    Steps can be bypassed with gold or reputation.
    Application can be rejected and reapplied.
    """
    guild_name:      str
    region:          str
    steps:           list[BureaucracyStep] = field(default_factory=list)
    current_step:    int   = 0
    rejected:        bool  = False
    rejection_reason:str   = ""
    approved:        bool  = False
    applied_at:      float = field(default_factory=time.time)
    approved_at:     float = 0.0
    attempts:        int   = 1

    @property
    def is_complete(self) -> bool:
        return all(s.completed for s in self.steps)

    @property
    def current_step_obj(self) -> Optional[BureaucracyStep]:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self) -> bool:
        """Mark current step complete and advance. Returns True if all done."""
        if self.current_step < len(self.steps):
            self.steps[self.current_step].completed = True
            self.current_step += 1
        return self.is_complete


@dataclass
class GuildQuest:
    """
    A quest issued by a guild. Uses the normal quest system but tracks
    contribution points separately.
    """
    quest_id:            str
    guild_id:            str
    title:               str
    description:         str
    issued_by:           str      # member name who issued it
    assigned_to:         str      = ""   # member name, or "" for open
    contribution_reward: int      = 50
    is_bounty:           bool     = False
    bounty_target:       str      = ""   # NPC or player name
    bounty_amount:       float    = 0.0  # gold reward for completion
    completed:           bool     = False
    completed_by:        str      = ""
    completed_at:        float    = 0.0


@dataclass
class GuildWar:
    """
    A war between two guilds.
    No PvP — conducted via bounties, economic sabotage, NPC mercenaries.
    Third guilds can join either side or both sides.
    """
    war_id:          str
    aggressor:       str     # guild name
    defender:        str     # guild name
    declared_at:     float   = field(default_factory=time.time)
    ended_at:        float   = 0.0
    is_active:       bool    = True
    winner:          str     = ""
    end_reason:      str     = ""   # "surrender" | "bankruptcy" | "dissolution"

    # Allied guilds per side
    aggressor_allies: list[str] = field(default_factory=list)
    defender_allies:  list[str] = field(default_factory=list)

    # War actions log
    actions:         list[dict] = field(default_factory=list)

    # Surrender / dissolution
    loser_dissolved: bool  = False

    @property
    def can_surrender(self) -> bool:
        return (time.time() - self.declared_at) >= GUILD_WAR_MIN_DURATION

    def add_action(self, actor: str, action_type: str, target: str, details: str) -> None:
        self.actions.append({
            "actor":       actor,
            "action_type": action_type,
            "target":      target,
            "details":     details,
            "timestamp":   time.time(),
        })


@dataclass
class GuildAlliance:
    """A formal alliance between two guilds."""
    alliance_id:   str
    guild_a:       str
    guild_b:       str
    formed_at:     float = field(default_factory=time.time)
    formed_by_a:   str   = ""   # leader who declared
    formed_by_b:   str   = ""   # leader who accepted
    is_active:     bool  = True
    dissolved_at:  float = 0.0


@dataclass
class GuildHall:
    """
    A physical guild hall location.
    Protected by convention — respectable kingdoms don't destroy them.
    People inside are safe. Enemies can camp outside.
    Rival guild members can enter only if invited.
    """
    hall_id:         str
    guild_id:        str
    location:        str
    region:          str
    established_at:  float = field(default_factory=time.time)
    is_primary:      bool  = True    # primary hall vs branch hall
    is_destroyed:    bool  = False
    destroyed_by:    str   = ""
    destroyed_at:    float = 0.0

    # Access control
    invited_guilds:  list[str] = field(default_factory=list)
    invited_members: list[str] = field(default_factory=list)

    # Upgrades (managed via land ownership system #22)
    upgrade_level:   int   = 1

    def can_enter(self, entity_name: str, guild_id: str, member_guilds: list[str]) -> bool:
        """Check if an entity can enter this hall."""
        if guild_id == self.guild_id:
            return True
        if entity_name in self.invited_members:
            return True
        if any(g in self.invited_guilds for g in member_guilds):
            return True
        return False


@dataclass
class GuildMessage:
    """A message sent within guild communication system."""
    message_id:   str
    sender:       str
    recipient:    str     # member name or "broadcast"
    content:      str
    sent_at:      float   = field(default_factory=time.time)
    read:         bool    = False
    is_broadcast: bool    = False
    min_rank:     int     = 0     # minimum rank to receive broadcast


@dataclass
class GuildResource:
    """A resource available for purchase with contribution points."""
    resource_id:   str
    name:          str
    description:   str
    cost:          int     # contribution points
    quantity:      int     = 1
    is_exclusive:  bool    = False   # only available through guild


@dataclass
class Guild:
    """
    A guild in Kyros. Can be founded by players or NPCs.
    Has custom ranks, messaging, wars, alliances, halls, and quests.
    """
    guild_id:        str
    name:            str
    description:     str
    guild_type:      str    # "adventurers" | "merchant" | "magic" | "craft" | "criminal" | etc.
    founder:         str
    founded_at:      float  = field(default_factory=time.time)
    region:          str    = "elya"

    # Ranks (custom names, set by founder or AI)
    ranks:           list[GuildRank]   = field(default_factory=list)

    # Members
    members:         list[GuildMember] = field(default_factory=list)

    # Halls
    halls:           list[GuildHall]   = field(default_factory=list)

    # Quests
    quests:          list[GuildQuest]  = field(default_factory=list)

    # Wars and alliances
    active_wars:     list[str]         = field(default_factory=list)   # war IDs
    alliances:       list[str]         = field(default_factory=list)   # alliance IDs

    # Resources available for contribution points
    resources:       list[GuildResource] = field(default_factory=list)

    # Finances
    treasury:        float = 0.0
    tax_rate:        float = 0.05    # 5% of member earnings by default

    # Registration
    is_registered:   bool  = False
    registration:    Optional[GuildRegistration] = None
    is_dissolved:    bool  = False
    dissolved_at:    float = 0.0
    dissolution_reason: str = ""
    name_blacklisted:bool  = False   # set if dissolved disgracefully

    # Messages
    messages:        list[GuildMessage] = field(default_factory=list)

    @property
    def leader(self) -> Optional[GuildMember]:
        """Highest rank member."""
        if not self.members:
            return None
        return max(self.members, key=lambda m: m.rank_index)

    @property
    def member_count(self) -> int:
        return len(self.members)

    def get_member(self, name: str) -> Optional[GuildMember]:
        for m in self.members:
            if m.entity_name.lower() == name.lower():
                return m
        return None

    def get_rank(self, rank_index: int) -> Optional[GuildRank]:
        for r in self.ranks:
            if r.rank_index == rank_index:
                return r
        return None

    def has_permission(self, member_name: str, permission: str) -> bool:
        member = self.get_member(member_name)
        if not member:
            return False
        rank = self.get_rank(member.rank_index)
        if not rank:
            return False
        return permission in rank.permissions

    def top_rank_index(self) -> int:
        if not self.ranks:
            return 0
        return max(r.rank_index for r in self.ranks)


# ─────────────────────────────────────────────────────────────────────────────
#  GUILD SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class GuildSystem:
    """
    Manages all guilds in the world.
    One GuildSystem per world (owned by WorldSimulation).

    Handles:
    - Guild founding and registration
    - Membership management
    - Rank promotion/demotion
    - Wars, alliances, bounties
    - Guild halls
    - Messaging
    - Contribution points and resources
    - Bankruptcy and dissolution
    - Hall destruction reputation tracking
    """

    def __init__(self, world_sim=None, quest_system_factory=None):
        self.world_sim              = world_sim
        self.quest_system_factory   = quest_system_factory

        # All guilds in the world
        self.guilds:       dict[str, Guild]      = {}   # guild_id → Guild
        self.guild_names:  dict[str, str]        = {}   # name → guild_id
        self.blacklisted_names: set[str]         = set()

        # All wars
        self.wars:         dict[str, GuildWar]   = {}

        # All alliances
        self.alliances:    dict[str, GuildAlliance] = {}

        # Hall destruction tracking
        self.hall_destructions: list[dict]       = []

        # Counter for unique IDs
        self._id_counter:  int = 0

    def _new_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}_{self._id_counter}_{int(time.time())}"


    # ─────────────────────────────────────────────────────────────────────
    #  GUILD FOUNDING
    # ─────────────────────────────────────────────────────────────────────

    def check_founding_requirements(
        self,
        founder_name:    str,
        founders:        list[dict],   # [{name, grade_index, is_player}]
        guild_name:      str,
        gold_offered:    float,
        items_offered:   list[str],
        region:          str,
    ) -> tuple[bool, str]:
        """
        Check if founding requirements are met.
        All founding members must meet grade requirement.
        Returns (can_found, reason).
        """
        # Name uniqueness
        if guild_name.lower() in {n.lower() for n in self.guild_names}:
            return False, f"A guild named '{guild_name}' already exists."
        if guild_name.lower() in self.blacklisted_names:
            return False, f"'{guild_name}' is a blacklisted guild name."

        # Grade check — all founding members
        below_grade = [
            f["name"] for f in founders
            if f.get("grade_index", 0) < GUILD_FOUND_MIN_GRADE
        ]
        if below_grade:
            from evolution import GRADE_NAMES
            required = GRADE_NAMES[GUILD_FOUND_MIN_GRADE]
            return False, (
                f"The following founding members do not meet the minimum "
                f"grade requirement ({required}): {', '.join(below_grade)}"
            )

        # Gold check (AI-decided minimum, rough baseline)
        min_gold = 500.0
        if gold_offered < min_gold:
            return False, f"Insufficient gold. Need at least {min_gold:.0f}g to found a guild."

        # Items check — at least a charter item (parchment, seal, etc.)
        charter_items = ["charter", "parchment", "seal", "founding document"]
        has_charter = any(
            any(ci in item.lower() for ci in charter_items)
            for item in items_offered
        )
        if not has_charter:
            return False, "A founding charter (parchment or seal) is required."

        return True, ""

    def begin_founding(
        self,
        founder_name:  str,
        founders:      list[dict],
        guild_name:    str,
        guild_type:    str,
        gold_cost:     float,
        region:        str,
        rank_names:    list[str] = None,    # player-defined rank names
        is_player_founded: bool  = True,
    ) -> tuple[Optional[Guild], list[str]]:
        """
        Begin the guild founding process.
        Creates the guild object and starts bureaucracy registration.
        Returns (guild, notifications).
        """
        can, reason = self.check_founding_requirements(
            founder_name, founders, guild_name, gold_cost, [], region
        )
        if not can:
            return None, [reason]

        guild_id = self._new_id("guild")

        # Generate ranks
        if rank_names and is_player_founded:
            ranks = self._build_ranks_from_names(rank_names)
        else:
            ranks = self._generate_ranks_ai(guild_name, guild_type)

        # Build guild
        guild = Guild(
            guild_id    = guild_id,
            name        = guild_name,
            description = self._generate_guild_description(guild_name, guild_type),
            guild_type  = guild_type,
            founder     = founder_name,
            region      = region,
            ranks       = ranks,
            treasury    = gold_cost,
        )

        # Add founding members
        top_rank = guild.top_rank_index()
        for i, f in enumerate(founders):
            rank = top_rank if f["name"] == founder_name else 0
            member = GuildMember(
                entity_name = f["name"],
                is_player   = f.get("is_player", False),
                rank_index  = rank,
                is_founder  = True,
            )
            guild.members.append(member)

        # Generate resources
        guild.resources = self._generate_guild_resources(guild_type)

        # Start bureaucracy
        registration = self._generate_bureaucracy(guild_name, region)
        guild.registration = registration

        # Register
        self.guilds[guild_id]           = guild
        self.guild_names[guild_name]    = guild_id

        notifications = [
            f"Guild '{guild_name}' founding begun!",
            f"  Type: {guild_type}",
            f"  Ranks: {' → '.join(r.name for r in ranks)}",
            f"  Treasury: {gold_cost:.0f}g",
            f"",
            f"  You must now complete the registration bureaucracy.",
            f"  Steps required: {len(registration.steps)}",
        ]

        return guild, notifications

    def _build_ranks_from_names(self, names: list[str]) -> list[GuildRank]:
        """Build rank objects from player-provided names."""
        ranks = []
        n     = len(names)
        for i, name in enumerate(names):
            # Contribution thresholds scale with rank
            contribution = i * 500
            # Higher ranks get more permissions
            permissions  = ["view_quests"]
            if i >= n // 2:
                permissions += ["issue_quest", "manage_resources"]
            if i >= n - 2:
                permissions += ["promote", "demote", "broadcast_message"]
            if i == n - 1:
                permissions += ["declare_war", "declare_alliance",
                                "manage_hall", "dissolve_guild"]
            ranks.append(GuildRank(
                rank_index            = i,
                name                  = name,
                contribution_required = contribution,
                permissions           = permissions,
            ))
        return ranks

    def _generate_ranks_ai(
        self,
        guild_name: str,
        guild_type: str,
    ) -> list[GuildRank]:
        """AI generates rank names for NPC-founded guilds."""
        from magic import _call_claude_json
        result = _call_claude_json(
            "You are creating rank names for a guild in the world of Kyros. "
            "Generate 4-6 thematic rank names from lowest to highest. "
            "Output ONLY JSON: a list of rank name strings.",
            [{"role": "user", "content":
              f"Guild: {guild_name}, Type: {guild_type}"}],
            max_tokens=150,
        )
        names = result if isinstance(result, list) else [
            "Initiate", "Member", "Veteran", "Officer", "Commander", "Grandmaster"
        ]
        return self._build_ranks_from_names(names)

    def _generate_guild_description(self, name: str, guild_type: str) -> str:
        """AI generates a guild description."""
        from magic import _call_claude_json
        result = _call_claude_json(
            "Write a 2-sentence description for a guild in the world of Kyros. "
            "Output ONLY JSON with key: description (string).",
            [{"role": "user", "content": f"Guild: {name}, Type: {guild_type}"}],
            max_tokens=150,
        )
        return result.get("description", f"The {name} guild of Kyros.")

    def _generate_guild_resources(self, guild_type: str) -> list[GuildResource]:
        """AI generates purchasable guild resources."""
        from magic import _call_claude_json
        result = _call_claude_json(
            "Generate 4-6 resources a guild in Kyros offers to its members "
            "in exchange for contribution points. Some should be exclusive to "
            "the guild, others available elsewhere but cheaper here. "
            "Output ONLY JSON: a list of resource objects.",
            [{"role": "user", "content": json.dumps({
                "guild_type": guild_type,
                "schema": {
                    "name":        "string",
                    "description": "string",
                    "cost":        "int (contribution points)",
                    "quantity":    "int",
                    "is_exclusive":"bool",
                }
            })}],
            max_tokens=400,
        )
        resources = []
        raw = result if isinstance(result, list) else []
        for r in raw:
            resources.append(GuildResource(
                resource_id  = self._new_id("res"),
                name         = r.get("name", "Guild Resource"),
                description  = r.get("description", ""),
                cost         = int(r.get("cost", RESOURCE_COST_BASE)),
                quantity     = int(r.get("quantity", 1)),
                is_exclusive = bool(r.get("is_exclusive", False)),
            ))
        return resources


    # ─────────────────────────────────────────────────────────────────────
    #  BUREAUCRACY
    # ─────────────────────────────────────────────────────────────────────

    def _generate_bureaucracy(
        self,
        guild_name: str,
        region:     str,
    ) -> GuildRegistration:
        """AI generates registration steps based on region/government type."""
        from magic import _call_claude_json
        result = _call_claude_json(
            "Generate the bureaucratic registration steps required to officially "
            "found a guild in a region of Kyros. The bureaucracy should feel "
            "tedious, frustrating, and occasionally corrupt. "
            "Include 3-10 steps. Some steps can be bypassed with gold or reputation. "
            "Output ONLY JSON: a list of step objects.",
            [{"role": "user", "content": json.dumps({
                "guild_name": guild_name,
                "region":     region,
                "schema": {
                    "description":  "string (what the player must do)",
                    "step_type":    "string (fetch_item/pay_gold/wait/bribe/talk_npc)",
                    "target":       "string (item/NPC/location name)",
                    "cost":         "float (gold cost, 0 if not applicable)",
                    "wait_duration":"float (NPC seconds, 0 if not applicable)",
                    "can_bypass":   "bool",
                    "bypass_cost":  "float (gold to skip this step)",
                }
            })}],
            max_tokens=600,
        )
        steps = []
        raw   = result if isinstance(result, list) else []
        for i, s in enumerate(raw):
            steps.append(BureaucracyStep(
                step_index    = i,
                description   = s.get("description", f"Step {i+1}"),
                step_type     = s.get("step_type", "talk_npc"),
                target        = s.get("target", "City Clerk"),
                cost          = float(s.get("cost", 0)),
                wait_duration = float(s.get("wait_duration", 0)),
                can_bypass    = bool(s.get("can_bypass", False)),
                bypass_cost   = float(s.get("bypass_cost", 0)),
            ))

        return GuildRegistration(
            guild_name = guild_name,
            region     = region,
            steps      = steps,
        )

    def advance_bureaucracy(
        self,
        guild_id:   str,
        bypass:     bool  = False,
        gold_paid:  float = 0.0,
    ) -> list[str]:
        """
        Advance one step in registration bureaucracy.
        Returns notifications.
        """
        guild = self.guilds.get(guild_id)
        if not guild or not guild.registration:
            return ["No active registration found."]

        reg  = guild.registration
        step = reg.current_step_obj
        if not step:
            return ["Registration already complete."]

        # Bypass check
        if bypass:
            if not step.can_bypass:
                return [f"Step '{step.description}' cannot be bypassed."]
            if gold_paid < step.bypass_cost:
                return [
                    f"Bypassing this step costs {step.bypass_cost:.0f}g. "
                    f"You paid {gold_paid:.0f}g."
                ]
            reg.advance()
            notifications = [f"  Step bypassed: {step.description}"]
        else:
            reg.advance()
            notifications = [f"  Step completed: {step.description}"]

        if reg.is_complete:
            # Roll for rejection (rare, based on AI or bad luck)
            if random.random() < 0.05 and reg.attempts == 1:
                reg.rejected       = True
                reg.rejection_reason = self._generate_rejection_reason()
                notifications.append(
                    f"[REJECTED] Your application was rejected: {reg.rejection_reason}"
                )
                notifications.append("  You may reapply.")
            else:
                reg.approved    = True
                reg.approved_at = time.time()
                guild.is_registered = True
                notifications.append(
                    f"[APPROVED] '{guild.name}' is now officially registered!"
                )
        else:
            remaining = len(reg.steps) - reg.current_step
            notifications.append(
                f"  {remaining} step(s) remaining."
            )

        return notifications

    def reapply_bureaucracy(self, guild_id: str) -> list[str]:
        """Reapply after rejection."""
        guild = self.guilds.get(guild_id)
        if not guild or not guild.registration:
            return ["No registration found."]
        if not guild.registration.rejected:
            return ["Application has not been rejected."]

        new_reg = self._generate_bureaucracy(guild.name, guild.region)
        new_reg.attempts = guild.registration.attempts + 1
        guild.registration = new_reg
        return [
            f"Reapplying for registration of '{guild.name}'.",
            f"  New steps generated ({len(new_reg.steps)} steps).",
        ]

    def _generate_rejection_reason(self) -> str:
        """AI generates a bureaucratic rejection reason."""
        from magic import _call_claude_json
        result = _call_claude_json(
            "Generate a short, absurd bureaucratic reason for rejecting a "
            "guild registration application in Kyros. "
            "Output ONLY JSON with key: reason (string, 1 sentence).",
            [{"role": "user", "content": "Generate a rejection reason."}],
            max_tokens=80,
        )
        return result.get("reason",
            "The application form was submitted on the wrong shade of parchment.")


    # ─────────────────────────────────────────────────────────────────────
    #  MEMBERSHIP
    # ─────────────────────────────────────────────────────────────────────

    def join_guild(
        self,
        guild_id:    str,
        entity_name: str,
        is_player:   bool,
        invited_by:  str = "",
    ) -> list[str]:
        """Entity joins a guild at rank 0."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if guild.is_dissolved:
            return ["That guild has been dissolved."]
        if guild.get_member(entity_name):
            return [f"{entity_name} is already a member of {guild.name}."]

        member = GuildMember(
            entity_name = entity_name,
            is_player   = is_player,
            rank_index  = 0,
        )
        guild.members.append(member)
        return [
            f"{entity_name} has joined {guild.name}.",
            f"  Starting rank: {guild.get_rank(0).name if guild.get_rank(0) else 'Initiate'}",
        ]

    def leave_guild(
        self,
        guild_id:    str,
        entity_name: str,
    ) -> list[str]:
        """Entity leaves a guild."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        member = guild.get_member(entity_name)
        if not member:
            return [f"{entity_name} is not a member of {guild.name}."]
        guild.members.remove(member)
        return [f"{entity_name} has left {guild.name}."]

    def promote_member(
        self,
        guild_id:     str,
        promoter:     str,
        target:       str,
        new_rank_idx: int = -1,   # -1 = next rank up
    ) -> list[str]:
        """Promote a member. Requires 'promote' permission."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if not guild.has_permission(promoter, "promote"):
            return [f"{promoter} does not have promotion rights."]
        member = guild.get_member(target)
        if not member:
            return [f"{target} is not a member."]

        if new_rank_idx == -1:
            new_rank_idx = member.rank_index + 1

        new_rank = guild.get_rank(new_rank_idx)
        if not new_rank:
            return [f"Rank {new_rank_idx} does not exist."]

        # Check contribution threshold
        if member.contribution_points < new_rank.contribution_required:
            return [
                f"{target} does not have enough contribution points. "
                f"({member.contribution_points}/{new_rank.contribution_required})"
            ]

        old_rank = guild.get_rank(member.rank_index)
        member.rank_index = new_rank_idx
        return [
            f"{target} promoted: "
            f"{old_rank.name if old_rank else '?'} → {new_rank.name}",
        ]

    def demote_member(
        self,
        guild_id:     str,
        demoter:      str,
        target:       str,
        reason:       str = "",
    ) -> list[str]:
        """Demote a member. Requires 'demote' permission."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if not guild.has_permission(demoter, "demote"):
            return [f"{demoter} does not have demotion rights."]
        member = guild.get_member(target)
        if not member:
            return [f"{target} is not a member."]
        if member.rank_index == 0:
            return [f"{target} is already at the lowest rank."]

        old_rank     = guild.get_rank(member.rank_index)
        member.rank_index -= 1
        new_rank     = guild.get_rank(member.rank_index)
        if reason:
            member.criminal_record.append(reason)
        return [
            f"{target} demoted: "
            f"{old_rank.name if old_rank else '?'} → {new_rank.name if new_rank else '?'}",
            f"  Reason: {reason}" if reason else "",
        ]

    def check_auto_promotion(self, guild_id: str) -> list[str]:
        """
        Check all members for auto-promotion based on contribution thresholds.
        Called periodically by world simulation tick.
        """
        guild = self.guilds.get(guild_id)
        if not guild:
            return []
        notifications = []
        for member in guild.members:
            next_rank_idx = member.rank_index + 1
            next_rank     = guild.get_rank(next_rank_idx)
            if not next_rank:
                continue
            if member.contribution_points >= next_rank.contribution_required:
                old_rank = guild.get_rank(member.rank_index)
                member.rank_index = next_rank_idx
                notifications.append(
                    f"[{guild.name}] {member.entity_name} auto-promoted to "
                    f"{next_rank.name}!"
                )
        return notifications

    def add_contribution(
        self,
        guild_id:    str,
        member_name: str,
        points:      int,
        reason:      str = "",
    ) -> list[str]:
        """Add contribution points to a member."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return []
        member = guild.get_member(member_name)
        if not member:
            return []
        member.contribution_points += points
        member.last_active          = time.time()
        return [
            f"[{guild.name}] +{points} contribution points "
            f"({reason or 'earned'}). "
            f"Total: {member.contribution_points}"
        ]

    def purchase_resource(
        self,
        guild_id:    str,
        member_name: str,
        resource_id: str,
    ) -> tuple[Optional[GuildResource], list[str]]:
        """Purchase a guild resource with contribution points."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return None, ["Guild not found."]
        member = guild.get_member(member_name)
        if not member:
            return None, ["Not a member."]

        resource = next((r for r in guild.resources if r.resource_id == resource_id), None)
        if not resource:
            return None, ["Resource not found."]
        if resource.quantity <= 0:
            return None, [f"{resource.name} is out of stock."]
        if member.contribution_points < resource.cost:
            return None, [
                f"Not enough contribution points. "
                f"({member.contribution_points}/{resource.cost})"
            ]

        member.contribution_points -= resource.cost
        resource.quantity          -= 1
        return resource, [
            f"Purchased {resource.name} for {resource.cost} contribution points.",
            f"  Remaining points: {member.contribution_points}",
        ]


    # ─────────────────────────────────────────────────────────────────────
    #  GUILD QUESTS AND BOUNTIES
    # ─────────────────────────────────────────────────────────────────────

    def issue_quest(
        self,
        guild_id:            str,
        issuer:              str,
        title:               str,
        description:         str,
        contribution_reward: int  = 50,
        assigned_to:         str  = "",
    ) -> list[str]:
        """Issue a guild quest. Requires 'issue_quest' permission."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if not guild.has_permission(issuer, "issue_quest"):
            return [f"{issuer} cannot issue quests."]

        quest = GuildQuest(
            quest_id             = self._new_id("gquest"),
            guild_id             = guild_id,
            title                = title,
            description          = description,
            issued_by            = issuer,
            assigned_to          = assigned_to,
            contribution_reward  = contribution_reward,
        )
        guild.quests.append(quest)
        return [
            f"[{guild.name}] Quest issued: {title}",
            f"  Contribution reward: {contribution_reward} pts",
            f"  Assigned to: {assigned_to or 'Open'}",
        ]

    def issue_bounty(
        self,
        guild_id:      str,
        issuer:        str,
        target_name:   str,
        gold_reward:   float,
        reason:        str = "",
    ) -> list[str]:
        """Issue a bounty on an NPC. Requires 'issue_quest' permission."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if not guild.has_permission(issuer, "issue_quest"):
            return [f"{issuer} cannot issue bounties."]

        quest = GuildQuest(
            quest_id       = self._new_id("bounty"),
            guild_id       = guild_id,
            title          = f"Bounty: {target_name}",
            description    = reason or f"Bring proof of {target_name}'s elimination.",
            issued_by      = issuer,
            is_bounty      = True,
            bounty_target  = target_name,
            bounty_amount  = gold_reward,
            contribution_reward = 100,
        )
        guild.quests.append(quest)
        guild.treasury -= gold_reward

        return [
            f"[{guild.name}] Bounty issued on {target_name}.",
            f"  Reward: {gold_reward:.0f}g + 100 contribution pts",
            f"  Reason: {reason or 'Undisclosed'}",
        ]

    def complete_guild_quest(
        self,
        guild_id:    str,
        quest_id:    str,
        member_name: str,
    ) -> list[str]:
        """Mark a guild quest complete and award contribution points."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        quest = next((q for q in guild.quests if q.quest_id == quest_id), None)
        if not quest:
            return ["Quest not found."]
        if quest.completed:
            return ["Quest already completed."]

        quest.completed    = True
        quest.completed_by = member_name
        quest.completed_at = time.time()

        notes = self.add_contribution(
            guild_id, member_name, quest.contribution_reward,
            f"completed quest: {quest.title}"
        )

        if quest.is_bounty:
            notes.append(
                f"  Bounty reward: {quest.bounty_amount:.0f}g "
                f"(collected from guild treasury)"
            )
            guild.treasury += 0   # gold given to member externally

        return [f"[{guild.name}] Quest complete: {quest.title}"] + notes


    # ─────────────────────────────────────────────────────────────────────
    #  WARS AND ALLIANCES
    # ─────────────────────────────────────────────────────────────────────

    def declare_war(
        self,
        aggressor_id: str,
        defender_id:  str,
        declarer:     str,
    ) -> list[str]:
        """Declare guild war. Requires 'declare_war' permission."""
        aggressor = self.guilds.get(aggressor_id)
        defender  = self.guilds.get(defender_id)
        if not aggressor or not defender:
            return ["One or both guilds not found."]
        if not aggressor.has_permission(declarer, "declare_war"):
            return [f"{declarer} cannot declare war."]

        war_id = self._new_id("war")
        war    = GuildWar(
            war_id     = war_id,
            aggressor  = aggressor.name,
            defender   = defender.name,
        )
        self.wars[war_id] = war
        aggressor.active_wars.append(war_id)
        defender.active_wars.append(war_id)

        notifications = [
            f"[WAR DECLARED] {aggressor.name} has declared war on {defender.name}!",
            f"  Surrender possible after {GUILD_WAR_MIN_DURATION//3600:.0f} hours.",
        ]

        # Notify world simulation
        if self.world_sim:
            self.world_sim._add_news(
                type("NewsItem", (), {
                    "news_id":   f"news_{int(time.time())}",
                    "headline":  f"{aggressor.name} declares war on {defender.name}!",
                    "body":      f"The guilds of {aggressor.name} and {defender.name} "
                                 f"are now at war.",
                    "region":    "regional",
                    "source":    "guild_war",
                    "created_at":time.time(),
                    "read_by":   [],
                    "is_expired":False,
                })()
            )

        return notifications

    def join_war(
        self,
        war_id:    str,
        guild_id:  str,
        side:      str,   # "aggressor" | "defender" | "both"
        declarer:  str,
    ) -> list[str]:
        """A third guild joins an existing war."""
        war   = self.wars.get(war_id)
        guild = self.guilds.get(guild_id)
        if not war or not guild:
            return ["War or guild not found."]
        if not guild.has_permission(declarer, "declare_war"):
            return [f"{declarer} cannot declare war."]
        if not war.is_active:
            return ["That war has ended."]

        if side in ("aggressor", "both"):
            war.aggressor_allies.append(guild.name)
        if side in ("defender", "both"):
            war.defender_allies.append(guild.name)
        guild.active_wars.append(war_id)

        return [
            f"{guild.name} has joined the war between "
            f"{war.aggressor} and {war.defender}! (Side: {side})"
        ]

    def war_action(
        self,
        war_id:      str,
        actor_guild: str,
        action_type: str,    # "bounty" | "sabotage" | "mercenary" | "economic"
        target:      str,
        details:     str,
        gold_cost:   float = 0.0,
    ) -> list[str]:
        """
        Perform a war action.
        Types: bounty on member, economic sabotage, hire NPC mercenaries.
        """
        war = self.wars.get(war_id)
        if not war or not war.is_active:
            return ["War not found or ended."]

        war.add_action(actor_guild, action_type, target, details)

        notifications = [f"[WAR] {actor_guild}: {action_type} against {target}"]
        if details:
            notifications.append(f"  {details}")

        # Economic sabotage triggers world simulation
        if action_type == "economic" and self.world_sim:
            target_guild = self.guilds.get(
                self.guild_names.get(target, ""), None
            )
            if target_guild:
                self.world_sim.trigger_guild_bankruptcy(
                    guild_name    = target,
                    region        = target_guild.region,
                    notifications = [],
                )

        return notifications

    def surrender_war(
        self,
        war_id:    str,
        guild_id:  str,
        declarer:  str,
        dissolve:  bool = False,
    ) -> list[str]:
        """
        Surrender in a guild war.
        Losing guild may be dissolved. Assets seized by winner.
        """
        war   = self.wars.get(war_id)
        guild = self.guilds.get(guild_id)
        if not war or not guild:
            return ["War or guild not found."]
        if not war.can_surrender:
            remaining = GUILD_WAR_MIN_DURATION - (time.time() - war.declared_at)
            return [f"Cannot surrender yet. Wait {remaining/3600:.1f} more hours."]

        # Determine winner
        loser  = guild.name
        winner = war.defender if loser == war.aggressor else war.aggressor

        war.is_active  = False
        war.ended_at   = time.time()
        war.winner     = winner
        war.end_reason = "surrender"

        # Remove war from guilds
        for g in self.guilds.values():
            if war_id in g.active_wars:
                g.active_wars.remove(war_id)

        notifications = [
            f"[WAR ENDED] {loser} surrenders to {winner}.",
        ]

        if dissolve:
            war.loser_dissolved = True
            notes = self.dissolve_guild(guild_id, f"Lost war against {winner}")
            notifications.extend(notes)

        return notifications

    def declare_alliance(
        self,
        guild_a_id: str,
        guild_b_id: str,
        declarer:   str,
    ) -> list[str]:
        """Declare a formal alliance between two guilds."""
        guild_a = self.guilds.get(guild_a_id)
        guild_b = self.guilds.get(guild_b_id)
        if not guild_a or not guild_b:
            return ["One or both guilds not found."]
        if not guild_a.has_permission(declarer, "declare_alliance"):
            return [f"{declarer} cannot declare alliances."]

        alliance_id = self._new_id("alliance")
        alliance    = GuildAlliance(
            alliance_id = alliance_id,
            guild_a     = guild_a.name,
            guild_b     = guild_b.name,
            formed_by_a = declarer,
        )
        self.alliances[alliance_id] = alliance
        guild_a.alliances.append(alliance_id)
        guild_b.alliances.append(alliance_id)

        return [
            f"[ALLIANCE] {guild_a.name} and {guild_b.name} are now allied.",
        ]


    # ─────────────────────────────────────────────────────────────────────
    #  GUILD HALLS
    # ─────────────────────────────────────────────────────────────────────

    def establish_hall(
        self,
        guild_id:   str,
        location:   str,
        region:     str,
        establisher:str,
        is_primary: bool = False,
    ) -> list[str]:
        """Establish a guild hall at a location."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if not guild.has_permission(establisher, "manage_hall"):
            return [f"{establisher} cannot manage halls."]

        hall = GuildHall(
            hall_id    = self._new_id("hall"),
            guild_id   = guild_id,
            location   = location,
            region     = region,
            is_primary = is_primary or len(guild.halls) == 0,
        )
        guild.halls.append(hall)
        return [
            f"[{guild.name}] Guild hall established at {location}!",
            f"  People inside are protected by convention.",
        ]

    def destroy_hall(
        self,
        hall_id:     str,
        destroyer:   str,
        is_kingdom:  bool = False,
        kingdom_name:str  = "",
    ) -> list[str]:
        """
        Destroy a guild hall. Tracks reputation penalty if done by a kingdom.
        Information may be suppressed — dead people can't talk.
        """
        # Find hall
        hall = None
        guild= None
        for g in self.guilds.values():
            for h in g.halls:
                if h.hall_id == hall_id:
                    hall  = h
                    guild = g
                    break

        if not hall:
            return ["Hall not found."]

        hall.is_destroyed = True
        hall.destroyed_by = destroyer
        hall.destroyed_at = time.time()

        notifications = [
            f"[HALL DESTROYED] {guild.name}'s hall at {hall.location} "
            f"was destroyed by {destroyer}!",
        ]

        # Track destruction event
        event = {
            "hall_id":     hall_id,
            "guild":       guild.name,
            "location":    hall.location,
            "destroyer":   destroyer,
            "is_kingdom":  is_kingdom,
            "kingdom":     kingdom_name,
            "timestamp":   time.time(),
            "known":       not is_kingdom,  # kingdoms can suppress it
        }
        self.hall_destructions.append(event)

        # Kingdom reputation penalty if it gets out
        if is_kingdom and kingdom_name:
            notifications.append(
                f"  {kingdom_name} has violated the convention protecting guild halls."
            )
            notifications.append(
                f"  If this becomes known, their reputation will suffer greatly."
            )

            # Other guilds react based on their relationship with the kingdom
            self._trigger_guild_hall_reactions(kingdom_name, guild.name, notifications)

        return notifications

    def _trigger_guild_hall_reactions(
        self,
        kingdom:      str,
        victim_guild: str,
        notifications: list[str],
    ) -> None:
        """Other guilds react to hall destruction based on kingdom relationship."""
        from magic import _call_claude_json
        for guild in self.guilds.values():
            if guild.name == victim_guild or guild.is_dissolved:
                continue
            result = _call_claude_json(
                "A kingdom has destroyed a guild hall in Kyros, violating the "
                "convention that protects guild halls. Decide how this guild reacts. "
                "Output ONLY JSON with keys: "
                "reaction (string: ignore/condemn/withdraw_services/declare_war), "
                "reason (string, 1 sentence).",
                [{"role": "user", "content": json.dumps({
                    "reacting_guild": guild.name,
                    "guild_type":     guild.guild_type,
                    "kingdom":        kingdom,
                    "victim_guild":   victim_guild,
                })}],
                max_tokens=150,
            )
            reaction = result.get("reaction", "ignore")
            reason   = result.get("reason", "")
            if reaction != "ignore":
                notifications.append(
                    f"  {guild.name} reacts to {kingdom}'s actions: "
                    f"{reaction}. {reason}"
                )


    # ─────────────────────────────────────────────────────────────────────
    #  MESSAGING
    # ─────────────────────────────────────────────────────────────────────

    def send_message(
        self,
        guild_id:    str,
        sender:      str,
        recipient:   str,
        content:     str,
        is_broadcast:bool  = False,
        min_rank:    int   = 0,
    ) -> list[str]:
        """
        Send a message to a guild member or broadcast.
        Messages to NPCs go through NPC dialogue system.
        NPC messages arrive as notifications.
        """
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]

        # Broadcast rank check
        if is_broadcast and not guild.has_permission(sender, "broadcast_message"):
            return [f"{sender} cannot broadcast messages."]

        msg = GuildMessage(
            message_id   = self._new_id("msg"),
            sender       = sender,
            recipient    = recipient if not is_broadcast else "broadcast",
            content      = content,
            is_broadcast = is_broadcast,
            min_rank     = min_rank,
        )
        guild.messages.append(msg)

        notifications = []
        if is_broadcast:
            # Notify all members of sufficient rank via world sim
            for member in guild.members:
                rank = guild.get_rank(member.rank_index)
                if rank and member.rank_index >= min_rank:
                    if self.world_sim:
                        self.world_sim._notify_player(
                            member.entity_name,
                            f"[{guild.name}] Broadcast from {sender}: {content}"
                        )
            notifications.append(f"Broadcast sent to all members (rank {min_rank}+).")
        else:
            # Direct message — NPC goes through dialogue
            target_member = guild.get_member(recipient)
            if target_member and not target_member.is_player:
                notifications.append(
                    f"Message sent to {recipient}. "
                    f"They will respond when available."
                )
            elif target_member and target_member.is_player:
                if self.world_sim:
                    self.world_sim._notify_player(
                        recipient,
                        f"[{guild.name}] Message from {sender}: {content}"
                    )
                notifications.append(f"Message delivered to {recipient}.")
            else:
                notifications.append(f"{recipient} is not in this guild.")

        return notifications

    def get_messages(
        self,
        guild_id:    str,
        member_name: str,
        unread_only: bool = False,
    ) -> list[GuildMessage]:
        """Get messages for a member."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return []
        member = guild.get_member(member_name)
        if not member:
            return []

        messages = [
            m for m in guild.messages
            if (m.recipient == member_name or
                (m.is_broadcast and member.rank_index >= m.min_rank))
        ]
        if unread_only:
            messages = [m for m in messages if not m.read]
        # Mark as read
        for m in messages:
            m.read = True
        return messages

    def npc_respond_to_message(
        self,
        guild_id:    str,
        npc_name:    str,
        message_id:  str,
        npc_entity=None,
    ) -> list[str]:
        """
        NPC responds to a message through their dialogue system.
        AI-decided based on relationship and mood.
        NPC can ignore or refuse.
        """
        guild = self.guilds.get(guild_id)
        if not guild:
            return []
        msg = next((m for m in guild.messages if m.message_id == message_id), None)
        if not msg:
            return []

        from magic import _call_claude_json
        result = _call_claude_json(
            "An NPC in Kyros has received a guild message. "
            "Decide if they respond and what they say. "
            "They may ignore it based on mood or relationship. "
            "Output ONLY JSON with keys: "
            "responds (bool), response (string, in character, 1-3 sentences).",
            [{"role": "user", "content": json.dumps({
                "npc_name":    npc_name,
                "sender":      msg.sender,
                "message":     msg.content,
                "guild":       guild.name,
                "npc_mood":    getattr(npc_entity, "_dominant_emotion", "neutral")
                               if npc_entity else "neutral",
                "relationship":getattr(npc_entity, "_get_relationship",
                               lambda x: None)(msg.sender) if npc_entity else None,
            })}],
            max_tokens=200,
        )

        if not result.get("responds", True):
            return [f"{npc_name} did not respond to your message."]

        response = result.get("response", "...")
        # Send response back via guild message
        self.send_message(
            guild_id  = guild_id,
            sender    = npc_name,
            recipient = msg.sender,
            content   = response,
        )
        return [f"{npc_name}: \"{response}\""]


    # ─────────────────────────────────────────────────────────────────────
    #  BANKRUPTCY AND DISSOLUTION
    # ─────────────────────────────────────────────────────────────────────

    def trigger_bankruptcy(
        self,
        guild_id:   str,
        reason:     str = "insolvency",
    ) -> list[str]:
        """
        Guild goes bankrupt. Triggers world simulation economic crisis.
        Members may face legal consequences if fraud was involved.
        """
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]

        guild.treasury = 0.0
        notifications  = [
            f"[BANKRUPTCY] {guild.name} has gone bankrupt!",
            f"  Reason: {reason}",
        ]

        # Trigger economic crisis in world simulation
        if self.world_sim:
            self.world_sim.trigger_guild_bankruptcy(
                guild_name    = guild.name,
                region        = guild.region,
                notifications = notifications,
            )

        # Check for fraud implications
        if "fraud" in reason.lower() or "tax" in reason.lower():
            for member in guild.members:
                rank = guild.get_rank(member.rank_index)
                if not rank:
                    continue
                # High-ranking members implicated
                if member.rank_index >= guild.top_rank_index() - 1:
                    member.criminal_record.append(f"guild_tax_fraud:{guild.name}")
                    notifications.append(
                        f"  {member.entity_name} ({rank.name}) has been implicated "
                        f"in guild tax fraud. Authorities have been notified."
                    )
                    # Law system handles actual consequences
                    if self.world_sim:
                        self.world_sim._notify_player(
                            member.entity_name,
                            f"[WANTED] You have been implicated in guild tax fraud. "
                            f"The authorities are looking for you."
                        )

        return notifications

    def dissolve_guild(
        self,
        guild_id: str,
        reason:   str = "voluntary",
    ) -> list[str]:
        """
        Dissolve a guild. Assets seized if by war loss.
        Name can be reinstated later (not blacklisted).
        Members freed to join other guilds.
        """
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]

        guild.is_dissolved       = True
        guild.dissolved_at       = time.time()
        guild.dissolution_reason = reason

        notifications = [
            f"[DISSOLVED] {guild.name} has been dissolved.",
            f"  Reason: {reason}",
            f"  {guild.member_count} members are now free to join other guilds.",
        ]

        # Seize assets if war dissolution
        if "war" in reason.lower():
            winner_name = reason.split("against ")[-1] if "against " in reason else ""
            winner_id   = self.guild_names.get(winner_name, "")
            winner      = self.guilds.get(winner_id)
            if winner:
                winner.treasury += guild.treasury
                notifications.append(
                    f"  {guild.name}'s treasury ({guild.treasury:.0f}g) "
                    f"seized by {winner_name}."
                )
                # Transfer halls
                for hall in guild.halls:
                    if not hall.is_destroyed:
                        hall.guild_id = winner_id
                        winner.halls.append(hall)
                        notifications.append(
                            f"  Hall at {hall.location} transferred to {winner_name}."
                        )

        guild.treasury = 0.0

        # Name NOT blacklisted — can be reinstated
        notifications.append(
            f"  Note: '{guild.name}' may be reinstated in the future."
        )

        return notifications

    def reinstate_guild(
        self,
        guild_id:    str,
        reinstater:  str,
        new_founder: str,
    ) -> list[str]:
        """Reinstate a dissolved guild under new or original leadership."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return ["Guild not found."]
        if not guild.is_dissolved:
            return [f"{guild.name} is not dissolved."]

        guild.is_dissolved       = False
        guild.dissolved_at       = 0.0
        guild.dissolution_reason = ""
        guild.founder            = new_founder
        guild.treasury           = 0.0
        # Clear members — must be re-recruited
        guild.members            = [GuildMember(
            entity_name = new_founder,
            is_player   = True,
            rank_index  = guild.top_rank_index(),
            is_founder  = True,
        )]

        return [
            f"[REINSTATED] {guild.name} has been reinstated under {new_founder}.",
            f"  The guild must rebuild its membership and treasury.",
        ]


    # ─────────────────────────────────────────────────────────────────────
    #  WORLD TICK
    # ─────────────────────────────────────────────────────────────────────

    def tick(self) -> list[str]:
        """
        Called by WorldSimulation each tick.
        Checks auto-promotions, war resolutions, bankruptcy checks.
        """
        notifications = []
        for guild_id, guild in self.guilds.items():
            if guild.is_dissolved:
                continue
            # Auto-promotion checks
            promo_notes = self.check_auto_promotion(guild_id)
            notifications.extend(promo_notes)
            # Bankruptcy check — AI decides if treasury triggers it
            if guild.treasury < 0:
                notes = self.trigger_bankruptcy(guild_id, "treasury deficit")
                notifications.extend(notes)
        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  DISPLAY
    # ─────────────────────────────────────────────────────────────────────

    def display_guild(self, guild_id: str, viewer_name: str = "") -> str:
        """Format guild info for display."""
        guild = self.guilds.get(guild_id)
        if not guild:
            return "Guild not found."

        lines = [
            f"=== {guild.name} ===",
            f"  Type:     {guild.guild_type}",
            f"  Founded:  by {guild.founder}",
            f"  Region:   {guild.region}",
            f"  Members:  {guild.member_count}",
            f"  Treasury: {guild.treasury:.0f}g",
            f"  Status:   {'DISSOLVED' if guild.is_dissolved else 'Active'}",
            f"  Registered: {'Yes' if guild.is_registered else 'Pending'}",
            "",
            f"  Ranks:",
        ]
        for rank in sorted(guild.ranks, key=lambda r: r.rank_index):
            lines.append(
                f"    {rank.rank_index}. {rank.name} "
                f"({rank.contribution_required} pts required)"
            )

        if guild.halls:
            lines.append(f"\n  Halls:")
            for hall in guild.halls:
                status = "[DESTROYED]" if hall.is_destroyed else ""
                lines.append(f"    {hall.location} ({hall.region}) {status}")

        if viewer_name:
            member = guild.get_member(viewer_name)
            if member:
                rank = guild.get_rank(member.rank_index)
                lines.append(f"\n  Your rank: {rank.name if rank else '?'}")
                lines.append(f"  Your contribution: {member.contribution_points} pts")

        return "\n".join(lines)


    # ─────────────────────────────────────────────────────────────────────
    #  SERIALIZE / DESERIALIZE
    # ─────────────────────────────────────────────────────────────────────

    def serialize(self) -> dict:
        def _guild_to_dict(g: Guild) -> dict:
            return {
                "guild_id":    g.guild_id,
                "name":        g.name,
                "description": g.description,
                "guild_type":  g.guild_type,
                "founder":     g.founder,
                "founded_at":  g.founded_at,
                "region":      g.region,
                "treasury":    g.treasury,
                "tax_rate":    g.tax_rate,
                "is_registered":g.is_registered,
                "is_dissolved":g.is_dissolved,
                "dissolved_at":g.dissolved_at,
                "dissolution_reason": g.dissolution_reason,
                "active_wars": g.active_wars,
                "alliances":   g.alliances,
                "ranks": [
                    {"rank_index":r.rank_index,"name":r.name,
                     "contribution_required":r.contribution_required,
                     "permissions":r.permissions}
                    for r in g.ranks
                ],
                "members": [
                    {"entity_name":m.entity_name,"is_player":m.is_player,
                     "rank_index":m.rank_index,"contribution_points":m.contribution_points,
                     "joined_at":m.joined_at,"is_founder":m.is_founder,
                     "criminal_record":m.criminal_record}
                    for m in g.members
                ],
                "halls": [
                    {"hall_id":h.hall_id,"location":h.location,"region":h.region,
                     "is_primary":h.is_primary,"is_destroyed":h.is_destroyed,
                     "invited_guilds":h.invited_guilds,"invited_members":h.invited_members}
                    for h in g.halls
                ],
                "quests": [
                    {"quest_id":q.quest_id,"title":q.title,"description":q.description,
                     "issued_by":q.issued_by,"assigned_to":q.assigned_to,
                     "contribution_reward":q.contribution_reward,"completed":q.completed,
                     "is_bounty":q.is_bounty,"bounty_target":q.bounty_target,
                     "bounty_amount":q.bounty_amount}
                    for q in g.quests
                ],
            }

        return {
            "guilds":            {gid: _guild_to_dict(g) for gid, g in self.guilds.items()},
            "guild_names":       self.guild_names,
            "blacklisted_names": list(self.blacklisted_names),
            "wars": {
                wid: {
                    "war_id":w.war_id,"aggressor":w.aggressor,"defender":w.defender,
                    "declared_at":w.declared_at,"ended_at":w.ended_at,
                    "is_active":w.is_active,"winner":w.winner,"end_reason":w.end_reason,
                    "aggressor_allies":w.aggressor_allies,"defender_allies":w.defender_allies,
                    "loser_dissolved":w.loser_dissolved,
                }
                for wid, w in self.wars.items()
            },
            "alliances": {
                aid: {
                    "alliance_id":a.alliance_id,"guild_a":a.guild_a,"guild_b":a.guild_b,
                    "formed_at":a.formed_at,"is_active":a.is_active,
                }
                for aid, a in self.alliances.items()
            },
        }

    @classmethod
    def deserialize(cls, data: dict, world_sim=None) -> "GuildSystem":
        gs = cls(world_sim=world_sim)
        gs.guild_names       = data.get("guild_names", {})
        gs.blacklisted_names = set(data.get("blacklisted_names", []))

        for gid, gd in data.get("guilds", {}).items():
            ranks = [
                GuildRank(
                    rank_index            = r["rank_index"],
                    name                  = r["name"],
                    contribution_required = r["contribution_required"],
                    permissions           = r.get("permissions", []),
                )
                for r in gd.get("ranks", [])
            ]
            members = [
                GuildMember(
                    entity_name        = m["entity_name"],
                    is_player          = m["is_player"],
                    rank_index         = m["rank_index"],
                    contribution_points= m["contribution_points"],
                    joined_at          = m.get("joined_at", time.time()),
                    is_founder         = m.get("is_founder", False),
                    criminal_record    = m.get("criminal_record", []),
                )
                for m in gd.get("members", [])
            ]
            halls = [
                GuildHall(
                    hall_id         = h["hall_id"],
                    guild_id        = gid,
                    location        = h["location"],
                    region          = h["region"],
                    is_primary      = h.get("is_primary", False),
                    is_destroyed    = h.get("is_destroyed", False),
                    invited_guilds  = h.get("invited_guilds", []),
                    invited_members = h.get("invited_members", []),
                )
                for h in gd.get("halls", [])
            ]
            quests = [
                GuildQuest(
                    quest_id            = q["quest_id"],
                    guild_id            = gid,
                    title               = q["title"],
                    description         = q["description"],
                    issued_by           = q["issued_by"],
                    assigned_to         = q.get("assigned_to", ""),
                    contribution_reward = q.get("contribution_reward", 50),
                    completed           = q.get("completed", False),
                    is_bounty           = q.get("is_bounty", False),
                    bounty_target       = q.get("bounty_target", ""),
                    bounty_amount       = q.get("bounty_amount", 0),
                )
                for q in gd.get("quests", [])
            ]
            guild = Guild(
                guild_id            = gid,
                name                = gd["name"],
                description         = gd.get("description", ""),
                guild_type          = gd["guild_type"],
                founder             = gd["founder"],
                founded_at          = gd.get("founded_at", time.time()),
                region              = gd.get("region", "elya"),
                ranks               = ranks,
                members             = members,
                halls               = halls,
                quests              = quests,
                treasury            = gd.get("treasury", 0),
                tax_rate            = gd.get("tax_rate", 0.05),
                is_registered       = gd.get("is_registered", False),
                is_dissolved        = gd.get("is_dissolved", False),
                dissolved_at        = gd.get("dissolved_at", 0),
                dissolution_reason  = gd.get("dissolution_reason", ""),
                active_wars         = gd.get("active_wars", []),
                alliances           = gd.get("alliances", []),
            )
            gs.guilds[gid] = guild

        for wid, wd in data.get("wars", {}).items():
            gs.wars[wid] = GuildWar(
                war_id           = wd["war_id"],
                aggressor        = wd["aggressor"],
                defender         = wd["defender"],
                declared_at      = wd.get("declared_at", time.time()),
                ended_at         = wd.get("ended_at", 0),
                is_active        = wd.get("is_active", True),
                winner           = wd.get("winner", ""),
                end_reason       = wd.get("end_reason", ""),
                aggressor_allies = wd.get("aggressor_allies", []),
                defender_allies  = wd.get("defender_allies", []),
                loser_dissolved  = wd.get("loser_dissolved", False),
            )

        for aid, ad in data.get("alliances", {}).items():
            gs.alliances[aid] = GuildAlliance(
                alliance_id = ad["alliance_id"],
                guild_a     = ad["guild_a"],
                guild_b     = ad["guild_b"],
                formed_at   = ad.get("formed_at", time.time()),
                is_active   = ad.get("is_active", True),
            )

        return gs