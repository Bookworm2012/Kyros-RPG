"""
kyros/npc_objects.py
Core data objects for the Kyros NPC system.
"""

from __future__ import annotations
import time
import math
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

REAL_TO_NPC_RATIO   = 60          # 1 real second = 60 NPC seconds (1 NPC minute)
MAX_CATCH_UP_SECS   = 10 * 3600   # 10 NPC hours maximum catch-up
SEASON_REAL_DAYS    = 10          # 1 season = 10 real days
SCORE_MAX           = 1000
SCORE_MIN           = 0
JAIL_BONUS_INTERVAL = 3600        # 1 real hour before jailbreak bonus kicks in
JAIL_BONUS_PER_HR   = 0.05        # +5% per hour past minimum
JAIL_BONUS_CAP      = 0.75        # 75% cap for illegal extension bonus
JAIL_MIN_FAIL       = 0.01        # Always at least 1% fail chance
GOSSIP_NEW_RATE     = 0.50        # 50% of score for new gossip entry
GOSSIP_REINFORCE    = 0.20        # 20% added to existing gossip entry


# ─────────────────────────────────────────────────────────────────────────────
#  MEMORY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Memory:
    """
    A single memory held by an NPC about the player or a world event.

    Decay formula:
        time_to_zero = score * 30 minutes  (in real seconds: score * 1800)
        decay follows a convex curve — faster at low scores, slower at high.
        decay_rate is fixed at creation and never recalculated.
        Each tick the current score is used only to accelerate the rate,
        not to recompute it from scratch.
    """
    description:              str
    score:                    float          # 0–1000
    original_timestamp:       float          # time.time() at creation
    last_reinforced_timestamp:float          # time.time() at last reinforcement
    decay_rate:               float          # points lost per real second, fixed at creation
    source_npc:               str            # name of originating NPC or "player"
    passed_on:                bool  = False  # entered gossip chain
    verified:                 bool  = True   # False = false/unverified memory

    @staticmethod
    def initial_decay_rate(score: float) -> float:
        """
        Calculate the fixed initial decay rate (points per real second).

        For a score S, time_to_zero = S * 1800 seconds.
        Base rate = S / (S * 1800) = 1/1800 points/sec for all scores.
        We use a curve so low-score memories decay faster and high-score slower,
        while still satisfying time_to_zero = S * 1800 on average.

        Curve: decay_rate = (S / (S * 1800)) * acceleration_factor(S)
               acceleration_factor = 2 - (S / SCORE_MAX)
               At S=0   → factor=2   (fastest)
               At S=1000 → factor=1  (slowest, matches base)
        """
        if score <= 0:
            return float("inf")
        if score >= SCORE_MAX:
            return 0.0
        base          = score / (score * 1800)          # always 1/1800
        accel         = 2.0 - (score / SCORE_MAX)
        return base * accel

    def current_acceleration(self) -> float:
        """
        Acceleration multiplier based on current score.
        As score drops, decay accelerates. Rate is fixed but multiplied each tick.
        """
        if self.score <= 0:
            return float("inf")
        return 2.0 - (self.score / SCORE_MAX)

    def tick(self, elapsed_real_seconds: float) -> bool:
        """
        Advance decay by elapsed_real_seconds.
        Returns True if memory should be deleted (score reached 0).
        """
        if self.score >= SCORE_MAX:
            return False                               # permanent
        accel       = self.current_acceleration()
        points_lost = self.decay_rate * accel * elapsed_real_seconds
        self.score  = max(0.0, self.score - points_lost)
        return self.score <= 0


# ─────────────────────────────────────────────────────────────────────────────
#  GOSSIP ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GossipEntry:
    """
    A memory that has entered the gossip chain.
    Extends Memory fields with gossip-specific tracking.
    """
    description:              str
    score:                    float
    original_timestamp:       float
    last_reinforced_timestamp:float
    decay_rate:               float
    source_npc:               str
    passed_on:                bool  = False
    verified:                 bool  = True
    original_score:           float = 0.0   # score as given by originating NPC
    received_timestamp:       float = field(default_factory=time.time)

    def to_memory(self) -> Memory:
        """Convert a GossipEntry back into a Memory for storage."""
        return Memory(
            description               = self.description,
            score                     = self.score,
            original_timestamp        = self.original_timestamp,
            last_reinforced_timestamp = self.last_reinforced_timestamp,
            decay_rate                = self.decay_rate,
            source_npc                = self.source_npc,
            passed_on                 = self.passed_on,
            verified                  = self.verified,
        )

    def tick(self, elapsed_real_seconds: float) -> bool:
        """Decay same as Memory."""
        if self.score >= SCORE_MAX:
            return False
        accel       = 2.0 - (self.score / SCORE_MAX)
        points_lost = self.decay_rate * accel * elapsed_real_seconds
        self.score  = max(0.0, self.score - points_lost)
        return self.score <= 0


# ─────────────────────────────────────────────────────────────────────────────
#  EMOTION
# ─────────────────────────────────────────────────────────────────────────────

EMOTION_TYPES = {
    "anger", "joy", "grief", "fear", "love", "contempt",
    "surprise", "disgust", "anticipation", "trust",
    "shame", "guilt", "envy", "pride", "anxiety",
    "relief", "loneliness", "hope", "despair", "gratitude",
}

@dataclass
class Emotion:
    """
    A single emotion in an NPC's emotional stack.
    Emotions decay over real time and can temporarily push character traits.
    """
    type:       str           # must be in EMOTION_TYPES
    intensity:  float         # 0–100
    source:     str           # what caused it
    timestamp:  float         # time.time() at creation
    decay_rate: float         # intensity points lost per real second
    masked:     bool = False  # hidden from player, detectable via text clues only

    def tick(self, elapsed_real_seconds: float) -> bool:
        """Returns True if emotion has faded completely."""
        self.intensity = max(0.0, self.intensity - self.decay_rate * elapsed_real_seconds)
        return self.intensity <= 0


# ─────────────────────────────────────────────────────────────────────────────
#  CHARACTER TRAIT
# ─────────────────────────────────────────────────────────────────────────────

TRAIT_PAIRS = [
    ("greedy",     "generous"),
    ("cowardly",   "brave"),
    ("hotheaded",  "calm"),
    ("honest",     "deceitful"),
    ("loyal",      "treacherous"),
    ("compassionate", "cruel"),
    ("ambitious",  "complacent"),
    ("humble",     "arrogant"),
    ("paranoid",   "trusting"),
    ("impulsive",  "deliberate"),
    ("vindictive", "forgiving"),
    ("gullible",   "skeptical"),
]

TRAIT_NAMES = {name for pair in TRAIT_PAIRS for name in pair}

@dataclass
class CharacterTrait:
    """
    A single character trait on a 0–100 spectrum between two poles.
    Floor and ceiling are AI-set at generation and never crossed.
    """
    type:    str    # must be in TRAIT_NAMES
    value:   float  # 0 = left pole fully, 100 = right pole fully
    floor:   float  # minimum value ever, AI set at generation
    ceiling: float  # maximum value ever, AI set at generation

    def shift(self, delta: float) -> None:
        """Shift trait value, respecting floor and ceiling."""
        self.value = max(self.floor, min(self.ceiling, self.value + delta))


# ─────────────────────────────────────────────────────────────────────────────
#  RELATIONSHIP
# ─────────────────────────────────────────────────────────────────────────────

RELATIONSHIP_TYPES = {
    "stranger", "acquaintance", "friend", "close_friend", "best_friend",
    "rival", "enemy", "lover", "married", "ex_lover", "ex_married",
    "mentor", "student", "colleague", "employer", "employee",
    "parent", "child", "sibling", "extended_family",
    "admirer", "nemesis", "ally", "neutral",
}

@dataclass
class Relationship:
    """
    A relationship between two entities (NPC-NPC or NPC-Player).
    Intensity 0–100. History logs shaping events.
    """
    entity_a:  str            # NPC name or "player"
    entity_b:  str
    type:      str            # from RELATIONSHIP_TYPES
    intensity: float          # 0–100
    timestamp: float          # time.time() when formed
    history:   list  = field(default_factory=list)

    def update(self, event: str, delta_intensity: float, new_type: Optional[str] = None) -> None:
        self.history.append({"event": event, "timestamp": time.time()})
        self.intensity = max(0.0, min(100.0, self.intensity + delta_intensity))
        if new_type and new_type in RELATIONSHIP_TYPES:
            self.type = new_type

    @property
    def is_hostile(self) -> bool:
        return self.type in {"rival", "enemy", "nemesis"}

    @property
    def is_intimate(self) -> bool:
        return self.type in {"lover", "married"}


# ─────────────────────────────────────────────────────────────────────────────
#  POLITICAL ALLIANCE
# ─────────────────────────────────────────────────────────────────────────────

ALLIANCE_TYPES = {
    "alliance", "cooperation", "non_aggression", "trade_agreement",
    "military_pact", "vassalage", "rivalry", "war", "neutral",
}

@dataclass
class PoliticalAlliance:
    """
    A political relationship between two guilds.
    Separate from personal NPC relationships.
    Overrides gossip inversion between allied guilds.
    """
    guild_a:   str
    guild_b:   str
    type:      str    # from ALLIANCE_TYPES
    intensity: float  # 0–100
    timestamp: float
    history:   list = field(default_factory=list)

    def update(self, event: str, delta: float, new_type: Optional[str] = None) -> None:
        self.history.append({"event": event, "timestamp": time.time()})
        self.intensity = max(0.0, min(100.0, self.intensity + delta))
        if new_type and new_type in ALLIANCE_TYPES:
            self.type = new_type

    @property
    def is_allied(self) -> bool:
        return self.type in {"alliance", "cooperation", "military_pact", "trade_agreement"}

    @property
    def is_hostile(self) -> bool:
        return self.type in {"rivalry", "war"}


# ─────────────────────────────────────────────────────────────────────────────
#  WEALTH STATE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WealthState:
    """
    Tracks an entity's wealth, credit score, and tax record.
    Wealth changes drift character traits gradually.
    """
    value:         float
    credit_score:  float        = 500.0   # 0–1000, higher = more creditworthy
    tax_record:    list         = field(default_factory=list)
    history:       list         = field(default_factory=list)
    visible_clues: list[str]    = field(default_factory=list)

    def update(self, delta: float, source: str) -> None:
        self.value += delta
        self.history.append({
            "delta":     delta,
            "source":    source,
            "timestamp": time.time(),
            "balance":   self.value,
        })

    def log_tax(self, amount: float, period: str) -> None:
        self.tax_record.append({
            "amount":    amount,
            "period":    period,
            "timestamp": time.time(),
            "paid":      True,
        })

    def evade_tax(self, amount: float, period: str) -> None:
        self.tax_record.append({
            "amount":    amount,
            "period":    period,
            "timestamp": time.time(),
            "paid":      False,
        })

    @property
    def is_broke(self) -> bool:
        return self.value <= 0

    @property
    def evasion_history(self) -> list:
        return [r for r in self.tax_record if not r["paid"]]


# ─────────────────────────────────────────────────────────────────────────────
#  BOUNTY
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Bounty:
    """
    A bounty placed on a target by a contractor.
    Completion or refusal affects reputation with both parties.
    """
    target:                  str
    contractor:              str
    reward:                  float
    conditions:              str
    status:                  str   = "active"   # active | completed | failed | expired
    timestamp:               float = field(default_factory=time.time)
    reputation_on_complete:  dict  = field(default_factory=dict)
    reputation_on_refuse:    dict  = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
#  LIE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Lie:
    """
    A lie told by the player to an NPC.
    Believed lies create false memories. Caught lies create relationship damage.
    """
    description: str
    timestamp:   float
    target_npc:  str
    believed:    bool  = False
    spread:      bool  = False


# ─────────────────────────────────────────────────────────────────────────────
#  SENTENCE (JAIL STATE)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Sentence:
    """
    Active jail sentence for the player or an NPC.
    Tracks time served, illegal extension, and jailbreak attempts.
    """
    duration_real_seconds:   float          # total sentence in real seconds
    start_time:              float          # time.time() when jailed
    jurisdiction:            str
    crime:                   str
    attempts:                int   = 0      # failed jailbreak attempts
    illegally_extended:      bool  = False

    @property
    def time_served(self) -> float:
        return time.time() - self.start_time

    @property
    def time_remaining(self) -> float:
        return max(0.0, self.duration_real_seconds - self.time_served)

    @property
    def is_complete(self) -> bool:
        return self.time_served >= self.duration_real_seconds

    @property
    def extension_hours(self) -> float:
        """Hours past the 1-hour minimum threshold."""
        base_threshold = JAIL_BONUS_INTERVAL
        overtime       = max(0.0, self.time_served - base_threshold)
        return overtime / 3600.0

    def jailbreak_bonus(self) -> float:
        """
        Extra success chance from illegal extension past minimum.
        Caps at JAIL_BONUS_CAP (75%).
        Only applies if sentence was illegally extended.
        """
        if not self.illegally_extended:
            return 0.0
        bonus = self.extension_hours * JAIL_BONUS_PER_HR
        return min(JAIL_BONUS_CAP, bonus)


# ─────────────────────────────────────────────────────────────────────────────
#  GUILD
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GuildMembership:
    guild_name: str
    rank:       str
    joined:     float = field(default_factory=time.time)
    expelled:   bool  = False


@dataclass
class Guild:
    """
    A guild with members, ranks, alliances, and rivalries.
    Internal messaging system relays gossip instantly to all active members.
    """
    name:             str
    purpose:          str
    ranks:            list[str]                    # ordered lowest to highest
    members:          dict[str, str]               # entity_name -> rank
    alliances:        list[PoliticalAlliance]      = field(default_factory=list)
    neutral:          bool                         = False
    wealth:           WealthState                  = field(default_factory=lambda: WealthState(0))
    political_offices:list[str]                    = field(default_factory=list)
    credit_score:     float                        = 500.0
    tax_record:       list                         = field(default_factory=list)
    dissolved:        bool                         = False

    def add_member(self, name: str, rank: str) -> None:
        if rank not in self.ranks:
            raise ValueError(f"Rank '{rank}' not in guild ranks {self.ranks}")
        self.members[name] = rank

    def expel_member(self, name: str) -> None:
        self.members.pop(name, None)

    def get_rival_guilds(self) -> list[str]:
        return [
            a.guild_b if a.guild_a == self.name else a.guild_a
            for a in self.alliances if a.is_hostile
        ]

    def get_allied_guilds(self) -> list[str]:
        return [
            a.guild_b if a.guild_a == self.name else a.guild_a
            for a in self.alliances if a.is_allied
        ]

    def rank_weight(self, member_name: str) -> float:
        """
        Returns a 0–1 trust weight based on guild rank.
        Higher rank = more trusted gossip within guild.
        """
        if member_name not in self.members:
            return 0.0
        rank  = self.members[member_name]
        idx   = self.ranks.index(rank) if rank in self.ranks else 0
        return (idx + 1) / len(self.ranks)


# ─────────────────────────────────────────────────────────────────────────────
#  REPUTATION
# ─────────────────────────────────────────────────────────────────────────────

REPUTATION_TIERS = [
    "local",
    "regional",
    "kingdom",
    "empire",
    "planetary",   # reserved for space expansion
    "system",      # reserved for space expansion
    "galaxy",      # reserved for space expansion
]

@dataclass
class ReputationEntry:
    """
    Reputation at a specific tier and location.
    Derived from gossip spread and independent calculation.
    """
    tier:      str    # from REPUTATION_TIERS
    location:  str    # town, region, kingdom name etc.
    score:     float  # -1000 to 1000
    timestamp: float  = field(default_factory=time.time)

    def update(self, delta: float) -> None:
        self.score     = max(-1000.0, min(1000.0, self.score + delta))
        self.timestamp = time.time()


# ─────────────────────────────────────────────────────────────────────────────
#  INVESTMENT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Investment:
    """
    A financial investment by the player or NPC into a guild or entity.
    Returns scale with guild wealth, political standing, and trade performance.
    """
    investor:    str
    target:      str          # guild or entity name
    amount:      float
    timestamp:   float        = field(default_factory=time.time)
    silent:      bool         = False   # silent investor, not publicly known
    returns:     list         = field(default_factory=list)
    active:      bool         = True

    def log_return(self, amount: float, reason: str) -> None:
        self.returns.append({
            "amount":    amount,
            "reason":    reason,
            "timestamp": time.time(),
        })

    @property
    def total_returned(self) -> float:
        return sum(r["amount"] for r in self.returns)

    @property
    def net_gain(self) -> float:
        return self.total_returned - self.amount