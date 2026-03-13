"""
kyros/magic.py

MagicSystem — all skill, spell, bloodline, transcendant, and world rule logic for Kyros.

Skills in Kyros ARE spells (and vice versa). Every active skill costs mana.
Passive skills provide always-on bonuses. Ritual skills require materials/time/location.
Transcendant skills arise spontaneously from profound realizations.
Bloodlines are inherited traits — one per entity, permanent, ranging from cosmetic to
devastating. All NPCs can have bloodlines, transcendants, classes, professions, levels.

World Rules (enforced by cosmic forces):
  1. Karmic plagues must be quarantined — gods physically intervene.
  2. Bloodlines cannot be abused — instant death, no respawn, save deleted.
  3. Mortals are submissive to immortals (not enforced for player specifically).

Identify skill upgrades based on player class/profession choices.
Outlawed skills tracked per region by AI, player notified on entry.
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

# Rarity tiers — transcendant is NOT on this list, it is above all
RARITY_TIERS = ["inferior", "common", "uncommon", "rare", "epic",
                "legendary", "mythic", "divine"]

# Transcendant is unique and above divine — stored separately
TRANSCENDANT_RARITY = "transcendant"

# Stat bonus percentages by keyword
STAT_BONUS_TIERS = {
    "miniscule": 0.01,   # 1%
    "minor":     0.02,   # 2%
    "lesser":    0.05,   # 5%
    "major":     0.10,   # 10%
}

# Skill categories
SKILL_CATEGORIES = [
    "active",        # costs mana, triggered by player
    "passive",       # always-on stat/effect bonus
    "ritual",        # requires materials, time, or location
    "transcendant",  # unique profound realization, above mythic
    "bloodline",     # inherited trait, one per entity, permanent
]

# Identify tier unlock thresholds (rarity index)
IDENTIFY_BASE_RARITY       = 0   # inferior — name, race, level (with hiding rules)
IDENTIFY_STAT_RARITY       = 1   # common   — basic stats
IDENTIFY_DETAIL_RARITY     = 3   # rare     — loosens the 50% race level hide
IDENTIFY_SPEC_RARITY       = 5   # legendary — class/profession specialization

# Identify race level hiding
IDENTIFY_HIDE_TIER_GAP     = 1   # hide if target is this many tiers above viewer
IDENTIFY_HIDE_LEVEL_PCT    = 0.50  # hide if target race level > 50% of viewer's

# Bloodline replacement weights
BLOODLINE_REPLACE_NEUTRAL  = 0.75
BLOODLINE_REPLACE_BENEFICIAL = 0.25

# Transcendant check: summarize after this many recent actions
TRANSCENDANT_SUMMARY_WINDOW = 10

# Karmic plague spread: interaction window (real seconds)
KARMIC_SPREAD_WINDOW       = 60 * 60 * 24 * 7   # 7 real days

# World rule: bloodline abuse categories
BLOODLINE_ABUSE_ACTS = [
    "harvesting_bloodlines",      # using bloodline to get more bloodlines
    "enslaving_bloodlines",       # enslaving entities because of bloodline
    "killing_for_bloodline",      # killing without reason to take bloodline
]


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude_json(
    system:     str,
    messages:   list,
    max_tokens: int = 600,
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
#  SKILL DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SkillEffect:
    """
    A single effect a skill produces when used.
    Damage, healing, stat buffs, debuffs, utility.
    """
    effect_type:  str     # damage / heal / buff / debuff / utility / disease / disaster
    damage_type:  str     = "magic"   # physical/fire/ice/lightning/poison/magic/holy/dark
    base_value:   float   = 0.0       # base number; actual = base * stat_scaling
    stat_scaling: str     = "intelligence"  # which stat scales this effect
    scaling_hint: str     = ""        # e.g. "scales with Intelligence"
    duration:     float   = 0.0       # seconds (0 = instant)
    area:         bool    = False     # hits all enemies in range
    description:  str     = ""        # human-readable effect description


@dataclass
class SkillStatBonus:
    """
    A stat bonus granted while a skill is active.
    """
    stat:       str
    tier:       str    # miniscule / minor / lesser / major
    percent:    float  # resolved from STAT_BONUS_TIERS

    @classmethod
    def from_tier(cls, stat: str, tier: str) -> "SkillStatBonus":
        pct = STAT_BONUS_TIERS.get(tier.lower(), 0.01)
        return cls(stat=stat, tier=tier, percent=pct)

    def apply(self, base_stat: float) -> float:
        """Return the bonus amount for a given base stat value."""
        return base_stat * self.percent


@dataclass
class Skill:
    """
    A skill in Kyros. Spells are skills. All active skills cost mana.

    rarity: inferior → common → uncommon → rare → epic → legendary → mythic → divine
            transcendant skills are NOT on this scale — they are unique and above all.

    skill_category: active / passive / ritual / transcendant / bloodline
    """
    skill_id:       str
    name:           str
    description:    str            # always mentions: damage/mana cost/stat bonuses/scaling hint
    rarity:         str            # from RARITY_TIERS or TRANSCENDANT_RARITY
    skill_category: str            # from SKILL_CATEGORIES
    source:         str            # class/profession/race/god/transcendant/bloodline/world
    skill_type:     str            = "active"  # legacy compat alias for skill_category

    # Costs
    mana_cost:      float          = 0.0       # 0 for passive/bloodline
    other_cost:     str            = ""        # e.g. "10 HP", "1 soul essence"

    # Effects
    effects:        list[SkillEffect]    = field(default_factory=list)
    stat_bonuses:   list[SkillStatBonus] = field(default_factory=list)

    # Progression
    level:          int    = 1
    comprehension:  float  = 0.0   # 0–100*level; auto-upgrades at threshold
    is_active:      bool   = True
    cooldown:       float  = 0.0   # real seconds
    last_used:      float  = 0.0

    # Outlawed tracking
    is_outlawed_in: list[str] = field(default_factory=list)  # region names

    # Transcendant-specific
    transcendant_cost_current: float = 0.0   # current use cost (diminishes with use)
    transcendant_cost_original:float = 0.0   # original cost at discovery
    transcendant_uses:         int   = 0     # times used
    transcendant_recovery:     str   = ""    # how to recover from cost

    @property
    def is_transcendant(self) -> bool:
        return self.rarity == TRANSCENDANT_RARITY

    @property
    def can_use(self) -> bool:
        if not self.is_active:
            return False
        if self.skill_category == "passive":
            return False
        return (time.time() - self.last_used) >= self.cooldown

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self.cooldown - (time.time() - self.last_used))

    def can_upgrade(self) -> bool:
        return self.comprehension >= 100.0 * self.level

    def upgrade(self) -> bool:
        if self.can_upgrade():
            self.level += 1
            return True
        return False

    def get_mana_cost(self, player_stats: object) -> float:
        """
        Actual mana cost. Transcendant cost diminishes with use.
        Transcendant cost can be non-mana (stated in other_cost).
        """
        if self.is_transcendant:
            return self.transcendant_cost_current
        return self.mana_cost

    def get_damage(self, player_stats: object, weather_mod: float = 1.0) -> float:
        """
        Calculate skill damage based on player stats and weather modifiers.
        Player never sees this formula — they observe it empirically.
        The description gives hints: "scales with Intelligence."
        """
        total = 0.0
        for effect in self.effects:
            if effect.effect_type not in ("damage", "heal"):
                continue
            base      = effect.base_value
            stat_val  = getattr(player_stats, effect.stat_scaling, 0.0)
            # Non-linear scaling: accelerates with investment
            scaling   = stat_val * (1.0 + (stat_val ** 1.1) * 0.0005)
            total    += (base + scaling) * self.level * weather_mod
        return max(1.0, total)

    def get_active_stat_bonuses(self, base_stats: object) -> dict[str, float]:
        """Return {stat: bonus_amount} for all active stat bonuses."""
        bonuses = {}
        for sb in self.stat_bonuses:
            base = getattr(base_stats, sb.stat, 0.0)
            bonuses[sb.stat] = bonuses.get(sb.stat, 0.0) + sb.apply(base)
        return bonuses


# ─────────────────────────────────────────────────────────────────────────────
#  BLOODLINE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Bloodline:
    """
    An inherited trait. One per entity, permanent.
    Cannot be chosen — assigned at creation or acquired through special means.
    Ranges from cosmetic to profound to devastating.

    Bloodlines have NO rarity tier — each is unique.
    Abuse = instant death (no respawn, save deleted).
    Replacing a harmful bloodline requires completing an evolution-style quest.
    """
    bloodline_id:   str
    name:           str
    description:    str
    alignment:      str    # "beneficial" / "neutral" / "harmful"

    # Effects (always-on, cannot be toggled)
    stat_modifiers: dict[str, float] = field(default_factory=dict)  # stat → multiplier
    passive_effects:list[str]        = field(default_factory=list)   # text descriptions
    special_ability:Optional[str]    = None    # e.g. "sphere_of_perception"
    special_params: dict             = field(default_factory=dict)   # ability parameters

    # Sphere of perception specific
    perception_radius: float = 0.0   # current radius in meters (grows per tier)

    # Harmful bloodline quest
    replacement_quest_id:   str  = ""
    replacement_quest_done: bool = False
    replacement_bloodline:  Optional["Bloodline"] = None

    # Abuse detection
    abuse_acts_committed:   list[str] = field(default_factory=list)

    # Rare bloodline flag
    is_rare_start: bool = False   # True for the 0.0001% chance bloodline

    def is_abuse(self, act: str) -> bool:
        return act in BLOODLINE_ABUSE_ACTS

    def on_tier_up(self) -> list[str]:
        """Called when owner's race tier increases. Grows sphere, upgrades effects."""
        notifications = []
        if self.special_ability == "sphere_of_perception":
            growth = self.special_params.get("growth_per_tier", 5.0)
            self.perception_radius += growth
            notifications.append(
                f"[BLOODLINE] Sphere of Perception expanded to "
                f"{self.perception_radius:.0f} meters."
            )
        return notifications


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSCENDANT SKILL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TranscendantRecord:
    """
    Records the context of a Transcendant skill's discovery.
    Each is unique — no two Transcendant skills are alike.
    """
    skill_id:      str
    discovery_context: str   # what the player was doing when it manifested
    discovered_at: float = field(default_factory=time.time)
    uses:          int   = 0


# ─────────────────────────────────────────────────────────────────────────────
#  DISEASE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Disease:
    """
    A disease in Kyros. Can be natural or cast via skill.
    Spreads through karmic connections (anyone who has interacted with infected).
    Karmic plagues specifically spread through karmic links — gods quarantine them.
    Deliberately spreading disease is a crime.
    """
    disease_id:      str
    name:            str
    description:     str
    is_karmic:       bool   = False    # if True, gods physically intervene to quarantine
    is_deliberate:   bool   = False    # if True, casting it is a crime everywhere
    spread_window:   float  = KARMIC_SPREAD_WINDOW

    # Debuff effects
    stat_reductions: dict[str, float] = field(default_factory=dict)  # stat → % reduction
    duration:        float = 0.0      # real seconds (0 = permanent until cured)
    cure_items:      list[str] = field(default_factory=list)

    # Infected tracking
    infected:        list[str] = field(default_factory=list)   # entity names
    quarantined:     bool      = False
    quarantined_at:  float     = 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  OUTLAWED SKILL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RegionOutlawRecord:
    """
    Tracks which skills and their variants are outlawed in a region.
    AI-generated per region. Player notified on entry.
    """
    region:         str
    outlawed_skills:list[str]  = field(default_factory=list)   # skill names
    outlawed_types: list[str]  = field(default_factory=list)   # skill categories
    outlawed_variants: list[str] = field(default_factory=list) # variant descriptors
    authority:      str        = "local_lord"   # who enforces the ban
    last_updated:   float      = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  IDENTIFY SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IdentifySpec:
    """
    Tracks the player's Identify skill specialization.
    Upgrades based on class/profession choices — adds detail, not replaces base.
    """
    rarity_index:    int   = 0     # current rarity index of the Identify skill
    specializations: list[str] = field(default_factory=list)
    # e.g. ["potion_details", "ingredient_quality"] for an alchemist
    # e.g. ["attack_breakdown", "weapon_analysis"] for a warrior


# ─────────────────────────────────────────────────────────────────────────────
#  MAGIC SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class MagicSystem:
    """
    Manages all skill, spell, bloodline, transcendant, disease,
    outlawed skill, and Identify logic for one player (or NPC).

    One MagicSystem instance per entity (player or NPC).
    World-level systems (disease spread, karmic plague quarantine,
    outlawed skill registries) are owned by MagicSystem but reference
    WorldSimulation for timers and notifications.
    """

    def __init__(
        self,
        entity_name:  str,
        is_player:    bool = False,
        world_sim=None,
        quest_system=None,
    ):
        self.entity_name  = entity_name
        self.is_player    = is_player
        self.world_sim    = world_sim
        self.quest_system = quest_system

        # Skills (includes spells, passives, rituals, transcendants)
        self.skills:            list[Skill]            = []
        self.transcendant_log:  list[TranscendantRecord] = []

        # Bloodline (one per entity, permanent)
        self.bloodline:         Optional[Bloodline]    = None

        # Disease infections
        self.active_diseases:   list[Disease]          = []
        self.disease_contacts:  list[str]              = []  # entities interacted with recently

        # Identify specialization
        self.identify_spec:     IdentifySpec           = IdentifySpec()

        # Interaction log for karmic spread tracking
        self.recent_interactions: list[dict]           = []  # {entity, timestamp}

        # Skill counter
        self._skill_counter:    int = 0

        # Action summary for transcendant check
        self._action_summary:   str = ""
        self._recent_actions:   list[str] = []

        # Outlawed skill awareness (populated on region entry)
        self._known_outlawed:   dict[str, RegionOutlawRecord] = {}


    # ─────────────────────────────────────────────────────────────────────
    #  SKILL CREATION
    # ─────────────────────────────────────────────────────────────────────

    def create_skill(
        self,
        name:           str,
        description:    str,
        rarity:         str,
        skill_category: str,
        source:         str,
        mana_cost:      float       = 0.0,
        other_cost:     str         = "",
        effects:        list[dict]  = None,
        stat_bonuses:   list[dict]  = None,
        cooldown:       float       = 0.0,
    ) -> Skill:
        """Build a Skill object. stat_bonuses are [{stat, tier}] dicts."""
        self._skill_counter += 1
        skill_id = f"skill_{self.entity_name}_{self._skill_counter}_{int(time.time())}"

        # Parse effects
        parsed_effects = []
        for e in (effects or []):
            parsed_effects.append(SkillEffect(
                effect_type  = e.get("effect_type", "damage"),
                damage_type  = e.get("damage_type", "magic"),
                base_value   = float(e.get("base_value", 0)),
                stat_scaling = e.get("stat_scaling", "intelligence"),
                scaling_hint = e.get("scaling_hint", ""),
                duration     = float(e.get("duration", 0)),
                area         = bool(e.get("area", False)),
                description  = e.get("description", ""),
            ))

        # Parse stat bonuses
        parsed_bonuses = []
        for sb in (stat_bonuses or []):
            parsed_bonuses.append(SkillStatBonus.from_tier(
                stat = sb.get("stat", "strength"),
                tier = sb.get("tier", "minor"),
            ))

        skill = Skill(
            skill_id       = skill_id,
            name           = name,
            description    = description,
            rarity         = rarity,
            skill_category = skill_category,
            skill_type     = skill_category,
            source         = source,
            mana_cost      = mana_cost,
            other_cost     = other_cost,
            effects        = parsed_effects,
            stat_bonuses   = parsed_bonuses,
            cooldown       = cooldown,
        )
        return skill

    def add_skill(self, skill: Skill) -> list[str]:
        """Add a skill. Returns notifications."""
        self.skills.append(skill)
        notifications = [f"Skill acquired: [{skill.rarity.upper()}] {skill.name}"]
        if skill.mana_cost > 0:
            notifications.append(f"  Mana cost: {skill.mana_cost:.0f}")
        if skill.other_cost:
            notifications.append(f"  Other cost: {skill.other_cost}")
        for sb in skill.stat_bonuses:
            notifications.append(
                f"  While active: {sb.tier} {sb.stat} bonus (+{sb.percent*100:.0f}%)"
            )
        return notifications

    def get_skill(self, name: str) -> Optional[Skill]:
        for s in self.skills:
            if s.name.lower() == name.lower():
                return s
        return None


    # ─────────────────────────────────────────────────────────────────────
    #  SKILL USE
    # ─────────────────────────────────────────────────────────────────────

    def use_skill(
        self,
        skill_name:  str,
        player,                  # Player/NPC instance with .mana and .stats
        target=None,
        region:      str = "",
        weather_mod: float = 1.0,
    ) -> tuple[list[str], bool]:
        """
        Attempt to use a skill.
        Returns (notifications, success).
        Checks: cooldown, mana, outlawed status, ritual requirements.
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return [f"Unknown skill: {skill_name}"], False
        if not skill.can_use:
            if skill.skill_category == "passive":
                return [f"{skill.name} is a passive skill."], False
            remaining = skill.cooldown_remaining
            return [f"{skill.name} is on cooldown ({remaining:.0f}s)."], False

        # Check if outlawed in current region
        if region and self._is_outlawed(skill, region):
            notifications = [
                f"[WARNING] {skill.name} is outlawed in {region}.",
                f"  Using it here will increase your wanted level.",
            ]
            # Still allow use — player's choice
            # Wanted level increase handled after use

        notifications = []

        # Mana cost
        cost = skill.get_mana_cost(player.stats)
        if cost > 0 and hasattr(player, "mana"):
            if player.mana < cost:
                return [f"Not enough mana. ({player.mana:.0f}/{cost:.0f})"], False
            player.mana -= cost

        # Apply stat bonuses (while-active duration)
        active_bonuses = skill.get_active_stat_bonuses(player.stats)
        if active_bonuses and skill.skill_category == "active":
            for stat, bonus in active_bonuses.items():
                from character import Buff
                player.add_buff(Buff(
                    name     = f"{skill.name}_bonus_{stat}",
                    stat     = stat,
                    modifier = bonus,
                    is_pct   = False,
                    duration = max(skill.cooldown, 5.0),
                    source   = skill.name,
                ))
                notifications.append(
                    f"  {skill.name}: {stat} +{bonus:.1f} (active)"
                )

        # Compute damage / healing
        damage = skill.get_damage(player.stats, weather_mod)

        # Skill description hints (player can observe to deduce formula)
        for effect in skill.effects:
            if effect.scaling_hint:
                # Only show hint first time skill is used
                if skill.uses if hasattr(skill, "uses") else 0 == 0:
                    notifications.append(f"  [{skill.name}] {effect.scaling_hint}")

        # Transcendant cost diminishment
        if skill.is_transcendant:
            skill.transcendant_uses += 1
            # Cost reduces by 5% per use, minimum 10% of original
            reduction = skill.transcendant_cost_original * 0.05
            skill.transcendant_cost_current = max(
                skill.transcendant_cost_original * 0.10,
                skill.transcendant_cost_current - reduction,
            )
            notifications.append(
                f"  [TRANSCENDANT] Use cost reduced to "
                f"{skill.transcendant_cost_current:.1f} "
                f"({skill.transcendant_recovery})"
            )

        # Mark cooldown
        skill.last_used = time.time()

        # Outlawed consequence
        if region and self._is_outlawed(skill, region):
            notifications.append(
                f"[WITNESSED] Using {skill.name} in {region} — wanted level increased."
            )
            # Actual wanted level update handled by law system via return value

        notifications.insert(0, f"Used {skill.name}: {damage:.0f} {skill.effects[0].damage_type if skill.effects else 'effect'}")
        return notifications, True

    def _is_outlawed(self, skill: Skill, region: str) -> bool:
        """Check if a skill is outlawed in the given region."""
        record = self._known_outlawed.get(region)
        if not record:
            return False
        if skill.name in record.outlawed_skills:
            return True
        if skill.skill_category in record.outlawed_types:
            return True
        for variant in record.outlawed_variants:
            if variant.lower() in skill.name.lower():
                return True
        return False


    # ─────────────────────────────────────────────────────────────────────
    #  OUTLAWED SKILL REGISTRY
    # ─────────────────────────────────────────────────────────────────────

    def on_region_entry(
        self,
        region:    str,
        world_sim=None,
    ) -> list[str]:
        """
        Called when entity enters a region.
        Fetches outlawed skills for that region via AI (if not cached).
        Returns notifications for the player.
        """
        if region in self._known_outlawed:
            record = self._known_outlawed[region]
        else:
            record = self._generate_outlawed_skills(region)
            self._known_outlawed[region] = record

        if not record.outlawed_skills and not record.outlawed_types:
            return []

        notifications = [f"[{region.upper()}] Outlawed skills in this region:"]
        for skill_name in record.outlawed_skills:
            notifications.append(f"  — {skill_name} (and variants)")
        for stype in record.outlawed_types:
            notifications.append(f"  — All {stype} skills")
        if record.authority:
            notifications.append(f"  Enforced by: {record.authority}")
        return notifications

    def _generate_outlawed_skills(self, region: str) -> RegionOutlawRecord:
        """AI generates which skills are outlawed in a region."""
        result = _call_claude_json(
            "You are determining which skills are outlawed in a region of Kyros. "
            "Some regions ban certain types of magic or combat techniques. "
            "Plague/disease skills and karmic skills are almost always banned everywhere. "
            "Output ONLY JSON with keys: "
            "outlawed_skills (list of skill name strings), "
            "outlawed_types (list from: active/passive/ritual/transcendant), "
            "outlawed_variants (list of variant descriptors e.g. 'fire', 'necro', 'plague'), "
            "authority (string: who enforces this).",
            [{"role": "user", "content": f"Region: {region}"}],
            max_tokens=300,
        )
        return RegionOutlawRecord(
            region           = region,
            outlawed_skills  = result.get("outlawed_skills", []),
            outlawed_types   = result.get("outlawed_types", []),
            outlawed_variants= result.get("outlawed_variants", []),
            authority        = result.get("authority", "local_lord"),
        )


    # ─────────────────────────────────────────────────────────────────────
    #  TRANSCENDANT SKILLS
    # ─────────────────────────────────────────────────────────────────────

    def check_transcendant(
        self,
        action:       str,
        player,
        world_sim=None,
    ) -> list[str]:
        """
        Called after every significant action.
        AI decides if the action — in context of full history — warrants
        a Transcendant skill.
        Uses most recent N actions + a running summary to limit API cost.
        """
        # Update action log and summary
        self._recent_actions.append(action)
        if len(self._recent_actions) > TRANSCENDANT_SUMMARY_WINDOW:
            # Summarize oldest actions and compress
            oldest = self._recent_actions[:-TRANSCENDANT_SUMMARY_WINDOW]
            self._action_summary = self._compress_action_summary(
                self._action_summary, oldest
            )
            self._recent_actions = self._recent_actions[-TRANSCENDANT_SUMMARY_WINDOW:]

        result = _call_claude_json(
            "You are the world of Kyros evaluating whether a person has had a "
            "profound enough realization to earn a Transcendant skill. "
            "Transcendant skills arise spontaneously — they are above mythic, "
            "completely unique, and represent a deep truth the person has grasped. "
            "Most actions will NOT earn one. They are extremely rare. "
            "If yes, generate the skill. If no, respond with earned: false. "
            "Output ONLY JSON with keys: "
            "earned (bool), "
            "name (string, unique evocative name), "
            "description (string: what it does, mentions mana/stat cost, "
            "recovery method, scaling hints), "
            "skill_category (always 'transcendant'), "
            "mana_cost (float, or 0 if non-mana cost), "
            "other_cost (string: stat loss/level loss description or empty), "
            "recovery (string: how the cost is recovered), "
            "effects (list of effect objects), "
            "cooldown (float: real seconds between uses, likely very long).",
            [{"role": "user", "content": json.dumps({
                "entity":          self.entity_name,
                "race":            getattr(player, "race", "unknown"),
                "class":           getattr(player.class_track, "name", "none")
                                   if hasattr(player, "class_track") and player.class_track
                                   else "none",
                "level":           getattr(player, "level", 0),
                "action_summary":  self._action_summary,
                "recent_actions":  self._recent_actions,
                "existing_transcendants": [
                    s.name for s in self.skills if s.is_transcendant
                ],
                "blessing":        getattr(player.blessing, "god_name", None)
                                   if hasattr(player, "blessing") and player.blessing
                                   else None,
            })}],
            max_tokens=600,
        )

        if not result.get("earned", False):
            return []

        # Build transcendant skill
        skill = self.create_skill(
            name           = result.get("name", "Unnamed Transcendant"),
            description    = result.get("description", ""),
            rarity         = TRANSCENDANT_RARITY,
            skill_category = "transcendant",
            source         = "transcendant",
            mana_cost      = float(result.get("mana_cost", 0)),
            other_cost     = result.get("other_cost", ""),
            effects        = result.get("effects", []),
            cooldown       = float(result.get("cooldown", 3600)),
        )
        skill.transcendant_cost_original = skill.mana_cost
        skill.transcendant_cost_current  = skill.mana_cost
        skill.transcendant_recovery      = result.get("recovery", "")

        notes = self.add_skill(skill)
        notes.insert(0,
            f"[TRANSCENDANT REALIZATION] A profound truth has manifested as a skill!"
        )

        record = TranscendantRecord(
            skill_id          = skill.skill_id,
            discovery_context = action,
        )
        self.transcendant_log.append(record)

        return notes

    def _compress_action_summary(
        self,
        existing_summary: str,
        new_actions: list[str],
    ) -> str:
        """Compress old actions into a running summary string."""
        actions_text = "; ".join(new_actions)
        result = _call_claude_json(
            "Compress these actions into a brief summary of a person's life story in Kyros. "
            "Keep it under 3 sentences. Output ONLY JSON with key: summary (string).",
            [{"role": "user", "content":
              f"Existing: {existing_summary}\nNew actions: {actions_text}"}],
            max_tokens=150,
        )
        return result.get("summary", existing_summary + " " + actions_text)


    # ─────────────────────────────────────────────────────────────────────
    #  BLOODLINES
    # ─────────────────────────────────────────────────────────────────────

    def assign_bloodline_at_creation(
        self,
        player,
        force_rare: bool = False,
    ) -> list[str]:
        """
        Assign a bloodline at character creation.
        0.0001% chance of rare sphere-of-perception bloodline.
        Some players get no bloodline.
        """
        # Roll for rare bloodline
        if force_rare or random.random() < 0.000001:
            self.bloodline = self._generate_rare_bloodline()
            notes = [
                f"[BLOODLINE] A rare bloodline has manifested: {self.bloodline.name}",
                f"  {self.bloodline.description}",
            ]
            return notes

        # 95% chance of no bloodline — bloodlines are extremely rare
        if random.random() < 0.95:
            return []

        # Generate a bloodline via AI
        bloodline = self._generate_bloodline(player)
        if bloodline:
            self.bloodline = bloodline
            return [
                f"[BLOODLINE] {bloodline.name} ({bloodline.alignment})",
                f"  {bloodline.description}",
            ]
        return []

    def _generate_rare_bloodline(self) -> Bloodline:
        """Generate the rare 0.0001% sphere of perception bloodline."""
        return Bloodline(
            bloodline_id       = "rare_sphere_perception",
            name               = "Sphere of Perception",
            description        = (
                "An impossibly rare bloodline. You perceive all things within a sphere "
                "around you. The sphere grows larger with each tier of race evolution. "
                "Nothing within the sphere can be hidden from you — movement, intent, "
                "the unseen. Abuse of this bloodline means instant death."
            ),
            alignment          = "beneficial",
            special_ability    = "sphere_of_perception",
            special_params     = {"growth_per_tier": 10.0, "base_radius": 5.0},
            perception_radius  = 5.0,
            is_rare_start      = True,
        )

    def _generate_bloodline(self, entity) -> Optional[Bloodline]:
        """AI-generate a bloodline appropriate for this entity."""
        result = _call_claude_json(
            "You are assigning a bloodline to a person in Kyros. "
            "Bloodlines are unique inherited traits — one per person, permanent. "
            "They range from cosmetic (hair color) to neutral to profound to devastating. "
            "There is no rarity system for bloodlines — each is unique. "
            "Bloodlines cannot be abused (harvesting, enslaving, or killing for them "
            "results in instant death). "
            "Output ONLY JSON with keys: "
            "name (string), "
            "description (string, 2 sentences), "
            "alignment (string: beneficial/neutral/harmful), "
            "stat_modifiers (dict: stat → multiplier, e.g. {strength: 1.1}), "
            "passive_effects (list of strings describing effects), "
            "special_ability (string or null).",
            [{"role": "user", "content": json.dumps({
                "race":  getattr(entity, "race", "human"),
                "class": getattr(entity.class_track, "name", "none")
                         if hasattr(entity, "class_track") and entity.class_track
                         else "none",
            })}],
            max_tokens=300,
        )
        if not result or not isinstance(result, dict):
            return None

        return Bloodline(
            bloodline_id    = f"bloodline_{self.entity_name}_{int(time.time())}",
            name            = result.get("name", "Unknown Bloodline"),
            description     = result.get("description", ""),
            alignment       = result.get("alignment", "neutral"),
            stat_modifiers  = result.get("stat_modifiers", {}),
            passive_effects = result.get("passive_effects", []),
            special_ability = result.get("special_ability"),
        )

    def check_bloodline_abuse(
        self,
        act:    str,
        player,
    ) -> tuple[bool, list[str]]:
        """
        Check if an action constitutes bloodline abuse.
        If yes: instant death, save deleted, no respawn.
        Returns (is_abuse, notifications).
        """
        if not self.bloodline:
            return False, []
        if not self.bloodline.is_abuse(act):
            return False, []

        self.bloodline.abuse_acts_committed.append(act)
        notifications = [
            f"[BLOODLINE ABUSE] You have abused your bloodline.",
            f"  The world itself strikes you down.",
            f"  There is no escape. There is no respawn.",
            f"  Your save will be deleted.",
        ]
        return True, notifications

    def start_bloodline_replacement_quest(
        self,
        player,
    ) -> list[str]:
        """
        When a player wants to replace a harmful bloodline.
        Generates an evolution-style quest (no failure, just completion).
        On completion, bloodline is replaced with AI-chosen neutral/beneficial one.
        """
        if not self.bloodline:
            return ["You have no bloodline."]
        if self.bloodline.alignment not in ("harmful",):
            return ["Your bloodline does not need to be replaced."]
        if self.bloodline.replacement_quest_id:
            return ["You are already on a bloodline replacement quest."]

        if not self.quest_system:
            return ["Quest system not available."]

        quest = self.quest_system.generate_quest(
            npc_name       = "Bloodline Sage",
            npc_location   = "inner_realm",
            player_level   = getattr(player, "level", 1),
            player_grade   = getattr(player.race_track, "grade_index", 0)
                             if hasattr(player, "race_track") else 0,
            player_race    = getattr(player, "race", "human"),
            player_class   = getattr(player.class_track, "name", "none")
                             if hasattr(player, "class_track") and player.class_track
                             else "none",
            player_guild_rank = 0,
            world_context  = {
                "is_bloodline_quest": True,
                "bloodline_name":     self.bloodline.name,
                "bloodline_effects":  self.bloodline.passive_effects,
                "no_failure":         True,
            },
            source = "bloodline",
        )
        if quest:
            quest.penalty.can_abandon          = False
            quest.penalty.permadeath           = False
            quest._is_bloodline_quest          = True
            self.bloodline.replacement_quest_id = quest.quest_id
            self.quest_system.accept_quest(quest)
            return [
                f"Bloodline replacement quest accepted: {quest.title}",
                f"  Complete it to replace your bloodline.",
            ]
        return ["Could not generate bloodline replacement quest."]

    def complete_bloodline_replacement(self, player) -> list[str]:
        """
        Called when bloodline replacement quest completes.
        AI chooses replacement: 75% neutral, 25% beneficial.
        """
        if not self.bloodline:
            return []

        # Determine alignment
        alignment = "neutral" if random.random() < BLOODLINE_REPLACE_NEUTRAL else "beneficial"

        result = _call_claude_json(
            "Generate a replacement bloodline for a person in Kyros who has overcome "
            "a harmful bloodline. The replacement should reflect their journey. "
            "Output ONLY JSON with keys: "
            "name, description, alignment, stat_modifiers (dict), "
            "passive_effects (list), special_ability (string or null).",
            [{"role": "user", "content": json.dumps({
                "old_bloodline":    self.bloodline.name,
                "old_effects":      self.bloodline.passive_effects,
                "target_alignment": alignment,
                "entity_actions":   self._recent_actions[-10:],
                "entity_race":      getattr(player, "race", "human"),
                "entity_class":     getattr(player.class_track, "name", "none")
                                    if hasattr(player, "class_track") and player.class_track
                                    else "none",
            })}],
            max_tokens=300,
        )

        new_bloodline = Bloodline(
            bloodline_id    = f"bloodline_{self.entity_name}_replacement_{int(time.time())}",
            name            = result.get("name", "Reborn Bloodline"),
            description     = result.get("description", ""),
            alignment       = alignment,
            stat_modifiers  = result.get("stat_modifiers", {}),
            passive_effects = result.get("passive_effects", []),
            special_ability = result.get("special_ability"),
        )

        old_name       = self.bloodline.name
        self.bloodline = new_bloodline

        return [
            f"[BLOODLINE] {old_name} has been replaced with {new_bloodline.name}.",
            f"  {new_bloodline.description}",
            f"  Alignment: {alignment}",
        ]

    def apply_bloodline_stats(self, player) -> None:
        """Apply bloodline stat modifiers to player stats. Called on load and tier up."""
        if not self.bloodline:
            return
        for stat, multiplier in self.bloodline.stat_modifiers.items():
            if hasattr(player.stats, stat):
                current = getattr(player.stats, stat)
                setattr(player.stats, stat, current * multiplier)

    def on_tier_up(self, player) -> list[str]:
        """Called when entity's race tier increases. Grows bloodline if applicable."""
        if not self.bloodline:
            return []
        return self.bloodline.on_tier_up()


    # ─────────────────────────────────────────────────────────────────────
    #  DISEASES
    # ─────────────────────────────────────────────────────────────────────

    def infect(
        self,
        disease:      Disease,
        source:       str,
        is_deliberate:bool = False,
    ) -> list[str]:
        """Infect this entity with a disease."""
        disease.infected.append(self.entity_name)
        disease.is_deliberate = is_deliberate
        self.active_diseases.append(disease)

        notifications = [
            f"[DISEASE] Infected with {disease.name}.",
            f"  {disease.description}",
        ]
        if disease.is_karmic:
            notifications.append(
                f"  [KARMIC PLAGUE] This plague spreads through karmic connections. "
                f"  The gods will intervene to quarantine it."
            )
        if is_deliberate:
            notifications.append(
                f"  [CRIME] Deliberately spreading disease is a crime in Kyros."
            )
        return notifications

    def record_interaction(self, entity_name: str) -> None:
        """Record an interaction for karmic plague spread tracking."""
        self.recent_interactions.append({
            "entity":    entity_name,
            "timestamp": time.time(),
        })
        # Prune old interactions
        cutoff = time.time() - KARMIC_SPREAD_WINDOW
        self.recent_interactions = [
            i for i in self.recent_interactions
            if i["timestamp"] > cutoff
        ]
        if entity_name not in self.disease_contacts:
            self.disease_contacts.append(entity_name)

    def spread_karmic_plague(
        self,
        disease:     Disease,
        world_sim=None,
    ) -> list[str]:
        """
        Spread a karmic plague to all entities this entity has interacted with.
        Triggers god quarantine.
        """
        notifications = []
        cutoff   = time.time() - disease.spread_window
        contacts = [
            i["entity"] for i in self.recent_interactions
            if i["timestamp"] > cutoff
        ]

        notifications.append(
            f"[KARMIC PLAGUE] {disease.name} spreading through karmic connections: "
            f"{len(contacts)} entities at risk."
        )

        # Quarantine trigger
        disease.quarantined   = True
        disease.quarantined_at= time.time()
        notifications.append(
            f"  The gods are intervening to contain {disease.name}."
        )

        # WorldSimulation creates a world event for the quarantine
        if world_sim:
            world_sim.schedule_world_event(
                event_type = f"karmic_plague_quarantine_{disease.disease_id}",
                region     = "all",
                delay      = 60.0,   # gods respond within 1 NPC minute
            )

        return notifications, contacts

    def generate_plague_skill(
        self,
        player,
        plague_type: str = "karmic",
    ) -> Optional[Skill]:
        """
        Generate a plague/disease skill. These are almost always banned everywhere.
        Deliberate use is a crime in Kyros.
        """
        result = _call_claude_json(
            "Generate a plague skill for a person in Kyros. "
            "This type of skill is banned almost everywhere and using it deliberately "
            "is considered a serious crime. It should feel dark and dangerous. "
            "Output ONLY JSON with keys: "
            "name, description (mentions it is banned, crime to use deliberately, "
            "scaling hints, mana cost), mana_cost (float), cooldown (float), "
            "effects (list), stat_bonuses (list).",
            [{"role": "user", "content": json.dumps({
                "plague_type":  plague_type,
                "entity_class": getattr(player.class_track, "name", "none")
                                if hasattr(player, "class_track") and player.class_track
                                else "none",
                "entity_level": getattr(player, "level", 1),
            })}],
            max_tokens=400,
        )
        if not result:
            return None

        skill = self.create_skill(
            name           = result.get("name", "Plague"),
            description    = result.get("description", ""),
            rarity         = "rare",
            skill_category = "active",
            source         = "forbidden",
            mana_cost      = float(result.get("mana_cost", 50)),
            effects        = result.get("effects", []),
            cooldown       = float(result.get("cooldown", 3600)),
        )
        return skill


    # ─────────────────────────────────────────────────────────────────────
    #  IDENTIFY SYSTEM
    # ─────────────────────────────────────────────────────────────────────

    def upgrade_identify(
        self,
        new_rarity_index: int,
        player,
    ) -> list[str]:
        """
        Upgrade Identify skill based on class/profession choices.
        Higher rarity adds specialization — never replaces base info.
        """
        self.identify_spec.rarity_index = new_rarity_index

        if new_rarity_index >= IDENTIFY_SPEC_RARITY:
            # Generate specializations based on class/profession
            specs = self._generate_identify_specializations(player)
            self.identify_spec.specializations.extend(specs)
            return [
                f"[IDENTIFY] Upgraded to {RARITY_TIERS[new_rarity_index]}.",
                f"  Specializations unlocked: {', '.join(specs)}",
            ]

        return [f"[IDENTIFY] Upgraded to {RARITY_TIERS[new_rarity_index]}."]

    def _generate_identify_specializations(self, player) -> list[str]:
        """AI generates Identify specializations based on class/profession."""
        result = _call_claude_json(
            "Generate 2-3 Identify skill specializations for a person in Kyros "
            "based on their class and profession. "
            "These add extra detail to what Identify shows, on top of the base info. "
            "Examples: an alchemist might see potion ingredient quality, "
            "a warrior might see detailed attack power breakdown. "
            "Output ONLY JSON: a list of specialization strings (short names).",
            [{"role": "user", "content": json.dumps({
                "class":      getattr(player.class_track, "name", "none")
                              if hasattr(player, "class_track") and player.class_track
                              else "none",
                "profession": getattr(player.profession_track, "name", "none")
                              if hasattr(player, "profession_track") and player.profession_track
                              else "none",
            })}],
            max_tokens=150,
        )
        if isinstance(result, list):
            return result[:3]
        return []

    def identify_target(
        self,
        target,           # Player or NPC instance
        viewer_race_level: int,
        viewer_race_grade: int,
    ) -> str:
        """
        Use Identify on a target. What is shown depends on Identify rarity.
        Base: name, race, level (with hiding rules).
        Higher rarity: more stats, then specialization details.
        """
        rarity_idx = self.identify_spec.rarity_index
        lines      = []

        # Base info (all levels)
        target_race  = getattr(target, "race", "Unknown")
        target_name  = getattr(target, "name", "Unknown")
        target_level = getattr(target.race_track, "level", 0) \
                       if hasattr(target, "race_track") else getattr(target, "level", 0)
        target_grade = getattr(target.race_track, "grade_index", 0) \
                       if hasattr(target, "race_track") else 0

        lines.append(f"Name: {target_name}")
        lines.append(f"Race: {target_race}")

        # Race level hiding rules
        level_display = self._get_level_display(
            target_level, target_grade,
            viewer_race_level, viewer_race_grade,
            rarity_idx,
        )
        lines.append(f"Race Level: {level_display}")

        # Common+: basic stats
        if rarity_idx >= IDENTIFY_STAT_RARITY:
            t_stats = getattr(target, "stats", None)
            if t_stats:
                for stat in ["strength","constitution","dexterity","agility",
                             "intelligence","wisdom","perception","charisma"]:
                    val = t_stats.effective(stat) if hasattr(t_stats, "effective") \
                          else getattr(t_stats, stat, 0)
                    lines.append(f"  {stat.capitalize()}: {val:.0f}")

        # Rare+: looser hiding, titles
        if rarity_idx >= IDENTIFY_DETAIL_RARITY:
            titles = getattr(target, "titles", [])
            if titles:
                lines.append(f"Titles: {', '.join(t.name for t in titles[:3])}")

        # Legendary+: specialization details
        if rarity_idx >= IDENTIFY_SPEC_RARITY:
            for spec in self.identify_spec.specializations:
                detail = self._get_specialization_detail(target, spec)
                if detail:
                    lines.append(f"[{spec}] {detail}")

        return "\n".join(lines)

    def _get_level_display(
        self,
        target_level:  int,
        target_grade:  int,
        viewer_level:  int,
        viewer_grade:  int,
        rarity_idx:    int,
    ) -> str:
        """
        Apply hiding rules to race level display.
        Hidden if: target is 1+ tier above viewer, OR target level > threshold%.
        At rare+ rarity, the level-% threshold loosens.
        Number of ? = number of characters in the actual level string.
        """
        # Tier gap hiding
        if (target_grade - viewer_grade) >= IDENTIFY_HIDE_TIER_GAP:
            level_str = str(target_level)
            return "?" * len(level_str)

        # Level percentage hiding
        pct_threshold = IDENTIFY_HIDE_LEVEL_PCT
        if rarity_idx >= IDENTIFY_DETAIL_RARITY:
            pct_threshold = 0.75   # rare loosens to 75%
        if rarity_idx >= IDENTIFY_SPEC_RARITY:
            pct_threshold = 1.00   # legendary shows all

        if viewer_level > 0 and (target_level / max(1, viewer_level)) > pct_threshold:
            level_str = str(target_level)
            return "?" * len(level_str)

        return str(target_level)

    def _get_specialization_detail(self, target, spec: str) -> str:
        """Return specialization-specific detail about a target."""
        # Warrior specializations
        if "attack" in spec.lower():
            ap = getattr(target, "attack_power", None)
            if callable(ap):
                ap = ap()
            if ap is not None:
                return f"Attack Power: {ap:.1f}"

        # Alchemist specializations
        if "potion" in spec.lower() or "ingredient" in spec.lower():
            inv = getattr(target, "inventory", [])
            potions = [i.name for i in inv
                       if hasattr(i, "item_type") and i.item_type == "consumable"]
            if potions:
                return f"Potions: {', '.join(potions[:3])}"

        return ""


    # ─────────────────────────────────────────────────────────────────────
    #  WORLD RULES
    # ─────────────────────────────────────────────────────────────────────

    def check_world_rules(
        self,
        act:    str,
        player,
        world_sim=None,
    ) -> tuple[str, list[str]]:
        """
        Check if an action violates a world rule.
        Returns (consequence_type, notifications).
        consequence_type: "ok" | "instant_death" | "quarantine"

        World Rules:
        1. Bloodline abuse → instant death (gods kill, no respawn, save deleted)
        2. Karmic plague → gods quarantine
        3. Mortal submissiveness → not enforced for player
        """
        # Rule 1: Bloodline abuse
        is_abuse, notes = self.check_bloodline_abuse(act, player)
        if is_abuse:
            return "instant_death", notes

        # Rule 2: Karmic plague detection
        for disease in self.active_diseases:
            if disease.is_karmic and not disease.quarantined:
                spread_notes, contacts = self.spread_karmic_plague(disease, world_sim)
                return "quarantine", spread_notes

        return "ok", []


    # ─────────────────────────────────────────────────────────────────────
    #  SERIALIZE / DESERIALIZE
    # ─────────────────────────────────────────────────────────────────────

    def serialize(self) -> dict:
        def _skill_to_dict(s: Skill) -> dict:
            return {
                "skill_id":       s.skill_id,
                "name":           s.name,
                "description":    s.description,
                "rarity":         s.rarity,
                "skill_category": s.skill_category,
                "source":         s.source,
                "mana_cost":      s.mana_cost,
                "other_cost":     s.other_cost,
                "cooldown":       s.cooldown,
                "level":          s.level,
                "comprehension":  s.comprehension,
                "transcendant_cost_current":  s.transcendant_cost_current,
                "transcendant_cost_original": s.transcendant_cost_original,
                "transcendant_uses":          s.transcendant_uses,
                "transcendant_recovery":      s.transcendant_recovery,
                "is_outlawed_in": s.is_outlawed_in,
                "effects": [
                    {
                        "effect_type":  e.effect_type,
                        "damage_type":  e.damage_type,
                        "base_value":   e.base_value,
                        "stat_scaling": e.stat_scaling,
                        "scaling_hint": e.scaling_hint,
                        "duration":     e.duration,
                        "area":         e.area,
                        "description":  e.description,
                    }
                    for e in s.effects
                ],
                "stat_bonuses": [
                    {"stat": sb.stat, "tier": sb.tier, "percent": sb.percent}
                    for sb in s.stat_bonuses
                ],
            }

        def _bloodline_to_dict(b: Bloodline) -> dict:
            return {
                "bloodline_id":         b.bloodline_id,
                "name":                 b.name,
                "description":          b.description,
                "alignment":            b.alignment,
                "stat_modifiers":       b.stat_modifiers,
                "passive_effects":      b.passive_effects,
                "special_ability":      b.special_ability,
                "special_params":       b.special_params,
                "perception_radius":    b.perception_radius,
                "replacement_quest_id": b.replacement_quest_id,
                "is_rare_start":        b.is_rare_start,
            }

        return {
            "entity_name":        self.entity_name,
            "is_player":          self.is_player,
            "skills":             [_skill_to_dict(s) for s in self.skills],
            "bloodline":          _bloodline_to_dict(self.bloodline) if self.bloodline else None,
            "identify_spec": {
                "rarity_index":    self.identify_spec.rarity_index,
                "specializations": self.identify_spec.specializations,
            },
            "action_summary":     self._action_summary,
            "recent_actions":     self._recent_actions,
            "transcendant_log": [
                {
                    "skill_id":          r.skill_id,
                    "discovery_context": r.discovery_context,
                    "discovered_at":     r.discovered_at,
                    "uses":              r.uses,
                }
                for r in self.transcendant_log
            ],
            "disease_contacts":   self.disease_contacts,
            "active_diseases": [
                {
                    "disease_id":     d.disease_id,
                    "name":           d.name,
                    "description":    d.description,
                    "is_karmic":      d.is_karmic,
                    "is_deliberate":  d.is_deliberate,
                    "quarantined":    d.quarantined,
                }
                for d in self.active_diseases
            ],
        }

    @classmethod
    def deserialize(
        cls,
        data:        dict,
        world_sim=None,
        quest_system=None,
    ) -> "MagicSystem":
        ms = cls(
            entity_name  = data.get("entity_name", ""),
            is_player    = data.get("is_player", False),
            world_sim    = world_sim,
            quest_system = quest_system,
        )
        ms._action_summary = data.get("action_summary", "")
        ms._recent_actions = data.get("recent_actions", [])
        ms.disease_contacts= data.get("disease_contacts", [])

        # Skills
        for sd in data.get("skills", []):
            skill = Skill(
                skill_id       = sd["skill_id"],
                name           = sd["name"],
                description    = sd["description"],
                rarity         = sd["rarity"],
                skill_category = sd["skill_category"],
                skill_type     = sd["skill_category"],
                source         = sd["source"],
                mana_cost      = sd.get("mana_cost", 0),
                other_cost     = sd.get("other_cost", ""),
                cooldown       = sd.get("cooldown", 0),
                level          = sd.get("level", 1),
                comprehension  = sd.get("comprehension", 0),
                transcendant_cost_current  = sd.get("transcendant_cost_current", 0),
                transcendant_cost_original = sd.get("transcendant_cost_original", 0),
                transcendant_uses          = sd.get("transcendant_uses", 0),
                transcendant_recovery      = sd.get("transcendant_recovery", ""),
                is_outlawed_in = sd.get("is_outlawed_in", []),
                effects        = [
                    SkillEffect(
                        effect_type  = e["effect_type"],
                        damage_type  = e.get("damage_type", "magic"),
                        base_value   = e.get("base_value", 0),
                        stat_scaling = e.get("stat_scaling", "intelligence"),
                        scaling_hint = e.get("scaling_hint", ""),
                        duration     = e.get("duration", 0),
                        area         = e.get("area", False),
                        description  = e.get("description", ""),
                    )
                    for e in sd.get("effects", [])
                ],
                stat_bonuses   = [
                    SkillStatBonus(
                        stat    = sb["stat"],
                        tier    = sb["tier"],
                        percent = sb["percent"],
                    )
                    for sb in sd.get("stat_bonuses", [])
                ],
            )
            ms.skills.append(skill)

        # Bloodline
        bd = data.get("bloodline")
        if bd:
            ms.bloodline = Bloodline(
                bloodline_id      = bd["bloodline_id"],
                name              = bd["name"],
                description       = bd["description"],
                alignment         = bd["alignment"],
                stat_modifiers    = bd.get("stat_modifiers", {}),
                passive_effects   = bd.get("passive_effects", []),
                special_ability   = bd.get("special_ability"),
                special_params    = bd.get("special_params", {}),
                perception_radius = bd.get("perception_radius", 0),
                replacement_quest_id = bd.get("replacement_quest_id", ""),
                is_rare_start     = bd.get("is_rare_start", False),
            )

        # Identify spec
        ispec = data.get("identify_spec", {})
        ms.identify_spec = IdentifySpec(
            rarity_index    = ispec.get("rarity_index", 0),
            specializations = ispec.get("specializations", []),
        )

        # Transcendant log
        for rd in data.get("transcendant_log", []):
            ms.transcendant_log.append(TranscendantRecord(
                skill_id          = rd["skill_id"],
                discovery_context = rd["discovery_context"],
                discovered_at     = rd.get("discovered_at", time.time()),
                uses              = rd.get("uses", 0),
            ))

        # Active diseases
        for dd in data.get("active_diseases", []):
            ms.active_diseases.append(Disease(
                disease_id    = dd["disease_id"],
                name          = dd["name"],
                description   = dd["description"],
                is_karmic     = dd.get("is_karmic", False),
                is_deliberate = dd.get("is_deliberate", False),
                quarantined   = dd.get("quarantined", False),
            ))

        return ms