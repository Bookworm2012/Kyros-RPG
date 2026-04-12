"""
kyros/npc.py
The NPC class for the Kyros system.
"""

from __future__ import annotations
import json
import math
import os
import time
import random
import urllib.request
import urllib.error
from typing import Optional
from dotenv import load_dotenv

from npc_objects import (
    Memory, GossipEntry, Emotion, CharacterTrait, Relationship,
    WealthState, Bounty, Lie, GuildMembership, Guild,
    ReputationEntry, Investment, Sentence,
    SCORE_MAX, SCORE_MIN, GOSSIP_NEW_RATE, GOSSIP_REINFORCE,
    JAIL_MIN_FAIL, JAIL_BONUS_CAP, REAL_TO_NPC_RATIO,
    EMOTION_TYPES, TRAIT_NAMES, RELATIONSHIP_TYPES, REPUTATION_TIERS,
)

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
#  CLAUDE API HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """
    Load the Anthropic API key from the environment.
    Raises RuntimeError if the key is missing so the error is explicit
    rather than silently returning empty responses.
    """
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file: ANTHROPIC_API_KEY=your_key_here"
        )
    return key


def _call_claude(system: str, messages: list, max_tokens: int = 1000) -> str:
    """
    Call the Anthropic API.
    Returns assistant text, or empty string if the response contains no text.
    Raises RuntimeError on missing API key.
    Raises urllib.error.HTTPError on bad requests (logged to stderr).
    """
    api_key = _get_api_key()

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
            "x-api-key":         api_key,
        },
        method = "POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            blocks = data.get("content", [])
            return " ".join(b["text"] for b in blocks if b.get("type") == "text")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        import sys
        print(f"[NPC API ERROR {e.code}]: {body}", file=sys.stderr)
        return ""
    except urllib.error.URLError as e:
        import sys
        print(f"[NPC API NETWORK ERROR]: {e.reason}", file=sys.stderr)
        return ""


def _call_claude_json(system: str, messages: list, max_tokens: int = 500) -> dict:
    """Call the API expecting a JSON response. Returns {} on failure."""
    raw = _call_claude(system, messages, max_tokens)
    try:
        clean = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(clean)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
#  NPC CLASS
# ─────────────────────────────────────────────────────────────────────────────

class NPC:
    """
    A fully-featured NPC in the Kyros system.

    Handles memory, gossip, emotions, relationships, character traits,
    wealth, political standing, guild membership, lying, reputation,
    and AI-driven dialogue.
    """

    def __init__(
        self,
        name:              str,
        personality:       str,
        intelligence:      str,          # "low" | "medium" | "high"
        location:          str,
        system_prompt:     str,          # base AI dialogue prompt
        wealth_value:      float = 100.0,
        schedule:          Optional[dict] = None,
    ):
        self.name              = name
        self.personality       = personality
        self.intelligence      = intelligence
        self.location          = location
        self.system_prompt     = system_prompt

        # Core state
        self.memories:          list[Memory]          = []
        self.gossip_list:       list[GossipEntry]     = []
        self.emotions:          list[Emotion]         = []
        self.relationships:     list[Relationship]    = []
        self.guilds:            list[GuildMembership] = []
        self.character_traits:  list[CharacterTrait]  = []
        self.wealth:            WealthState           = WealthState(wealth_value)
        self.political_offices: list[str]             = []
        self.reputation:        list[ReputationEntry] = []
        self.bounties_placed:   list[Bounty]          = []
        self.bounties_on_self:  list[Bounty]          = []
        self.schedule:          dict                  = schedule or {}
        self.secrets:           list[str]             = []
        self.fears:             list[str]             = []
        self.goals:             list[str]             = []
        self.magic_ability:     float                 = 0.0   # 0–100
        self.sentence:          Optional[Sentence]    = None

        # Dialogue history for current session only
        self._conversation_history: list[dict] = []

        # Last time decay_tick was called (real time)
        self._last_tick_time: float = time.time()


    # ─────────────────────────────────────────────────────────────────────
    #  AI GENERATION
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def generate(
        cls,
        name:          str,
        role:          str,
        location:      str,
        world_context: str   = "",
        wealth_value:  float = 100.0,
    ) -> "NPC":
        """
        Fully AI-generate an NPC from scratch.

        The AI decides: personality, intelligence, all character traits
        (with values, floors, ceilings), secrets, fears, long-term goals,
        daily schedule, magic ability, and system prompt for dialogue.

        Returns a fully initialized NPC instance.
        """
        system = (
            "You are generating a person who lives in the world of Kyros. "
            "Generate a complete NPC profile given their name, role, and location. "
            "Output ONLY valid JSON with these exact keys: "
            "personality (string, 2-3 sentences), "
            "intelligence (string: low medium or high), "
            "system_prompt (string: in-character dialogue instructions, 3-5 sentences), "
            "traits (list of objects each with: type, value, floor, ceiling; "
            "type must be one of the valid trait names, all values 0-100), "
            "secrets (list of 1-3 strings), "
            "fears (list of 1-3 strings), "
            "goals (list of 1-3 strings), "
            "magic_ability (float 0-100), "
            "schedule (list of objects each with: start_hour, end_hour, status; "
            "status is available sleeping working or away; hours 0-24; cover full day). "
            f"Valid trait types: {sorted(TRAIT_NAMES)}. "
            "No other text. No markdown."
        )
        prompt = (
            f"Name: {name}\n"
            f"Role: {role}\n"
            f"Location: {location}\n"
            f"World context: {world_context}"
        )
        result = _call_claude_json(system, [{"role": "user", "content": prompt}], max_tokens=1500)

        raw_traits = result.get("traits", [])
        traits = [
            CharacterTrait(
                type    = t["type"],
                value   = float(t.get("value", 50)),
                floor   = float(t.get("floor", 0)),
                ceiling = float(t.get("ceiling", 100)),
            )
            for t in raw_traits if t.get("type") in TRAIT_NAMES
        ]

        raw_schedule = result.get("schedule", [])
        schedule = {
            (float(e.get("start_hour", 0)), float(e.get("end_hour", 24))): e.get("status", "available")
            for e in raw_schedule
        }

        intelligence = result.get("intelligence", "medium")
        if intelligence not in ("low", "medium", "high"):
            intelligence = "medium"

        npc = cls(
            name          = name,
            personality   = result.get("personality", f"A {role} in {location}."),
            intelligence  = intelligence,
            location      = location,
            system_prompt = result.get("system_prompt", f"You are {name}, a {role} in {location}."),
            wealth_value  = wealth_value,
            schedule      = schedule,
        )
        npc.character_traits = traits
        npc.secrets          = result.get("secrets", [])
        npc.fears            = result.get("fears", [])
        npc.goals            = result.get("goals", [])
        npc.magic_ability    = float(result.get("magic_ability", 0.0))
        return npc

    def generate_relationships(
        self,
        other_npcs:    list,
        world_context: str = "",
    ) -> None:
        """
        AI-generate randomized starting relationships with a list of other NPCs.
        Called after all NPCs for a playthrough are created.
        Relationships are influenced by personality and traits but ultimately randomized.
        """
        if not other_npcs:
            return

        other_summaries = [f"{n.name} ({n.personality[:80]})" for n in other_npcs]

        system = (
            "You are establishing the existing relationships between people in Kyros. "
            "Given an NPC and a list of others, assign a relationship to each pair. "
            "Relationships are randomized but personality-influenced. "
            f"Valid relationship types: {sorted(RELATIONSHIP_TYPES)}. "
            "Output ONLY valid JSON: a list of objects each with: "
            "entity_b (string), type (string), intensity (float 0-100). "
            "No other text."
        )
        context = (
            f"NPC: {self.name}\n"
            f"Personality: {self.personality}\n"
            f"Traits: {self._summarise_traits()}\n"
            f"World context: {world_context}\n"
            f"Other NPCs:\n" + "\n".join(other_summaries)
        )
        result = _call_claude_json(system, [{"role": "user", "content": context}], max_tokens=800)

        raw_rels = result if isinstance(result, list) else result.get("relationships", result.get("list", []))

        for r in raw_rels:
            entity_b  = r.get("entity_b", "")
            rel_type  = r.get("type", "stranger")
            intensity = float(r.get("intensity", 50))
            if entity_b and rel_type in RELATIONSHIP_TYPES:
                self.relationships.append(Relationship(
                    entity_a  = self.name,
                    entity_b  = entity_b,
                    type      = rel_type,
                    intensity = intensity,
                    timestamp = time.time(),
                ))



    # ─────────────────────────────────────────────────────────────────────
    #  PROPERTIES
    # ─────────────────────────────────────────────────────────────────────

    @property
    def interaction_willingness(self) -> float:
        """
        0–100. Derived from emotional state.
        Deep grief or fury can reduce this to near zero.
        """
        if not self.emotions:
            return 100.0
        blocking = {"grief": 0.4, "fear": 0.5, "anger": 0.6, "despair": 0.3}
        base = 100.0
        for emotion in self.emotions:
            factor = blocking.get(emotion.type, 0.9)
            base  *= max(factor, 1.0 - (emotion.intensity / 100.0) * (1.0 - factor))
        return max(0.0, min(100.0, base))

    @property
    def gullibility(self) -> float:
        """0–100. Higher = more likely to accept claims without checking."""
        trait = self._get_trait("gullible")
        return trait.value if trait else 50.0

    @property
    def is_available(self) -> bool:
        """
        False if NPC is asleep, away, or otherwise unavailable per schedule.
        Schedule is a dict of hour_ranges -> location/status.
        """
        if self.sentence and not self.sentence.is_complete:
            return False
        if not self.schedule:
            return True
        npc_hour = (time.time() * REAL_TO_NPC_RATIO / 3600) % 24
        for time_range, status in self.schedule.items():
            start, end = time_range
            if start <= npc_hour < end:
                return status == "available"
        return True


    # ─────────────────────────────────────────────────────────────────────
    #  TRAIT HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _get_trait(self, trait_type: str) -> Optional[CharacterTrait]:
        for t in self.character_traits:
            if t.type == trait_type:
                return t
        return None

    def _get_relationship(self, entity: str) -> Optional[Relationship]:
        for r in self.relationships:
            if r.entity_b == entity or r.entity_a == entity:
                return r
        return None

    def _get_memory(self, description_key: str) -> Optional[Memory]:
        """Find a memory by partial description match."""
        desc_lower = description_key.lower()
        for m in self.memories:
            if desc_lower in m.description.lower():
                return m
        return None

    def _get_gossip(self, description_key: str) -> Optional[GossipEntry]:
        desc_lower = description_key.lower()
        for g in self.gossip_list:
            if desc_lower in g.description.lower():
                return g
        return None


    # ─────────────────────────────────────────────────────────────────────
    #  DECAY TICK
    # ─────────────────────────────────────────────────────────────────────

    def decay_tick(self) -> None:
        """
        Advance memory and emotion decay by real time elapsed since last tick.
        Deletes memories and emotions that have reached zero.
        """
        now     = time.time()
        elapsed = now - self._last_tick_time
        self._last_tick_time = now

        self.memories    = [m for m in self.memories    if not m.tick(elapsed)]
        self.gossip_list = [g for g in self.gossip_list if not g.tick(elapsed)]
        self.emotions    = [e for e in self.emotions    if not e.tick(elapsed)]


    # ─────────────────────────────────────────────────────────────────────
    #  MEMORY CREATION
    # ─────────────────────────────────────────────────────────────────────

    def create_memory(
        self,
        description: str,
        score:       float,
        source:      str,
        verified:    bool = True,
    ) -> Optional[Memory]:
        """
        Create and store a new memory. Returns None if score is 0.
        """
        if score <= 0:
            return None
        score      = min(SCORE_MAX, score)
        decay_rate = Memory.initial_decay_rate(score)
        memory     = Memory(
            description               = description,
            score                     = score,
            original_timestamp        = time.time(),
            last_reinforced_timestamp = time.time(),
            decay_rate                = decay_rate,
            source_npc                = source,
            verified                  = verified,
        )
        self.memories.append(memory)
        return memory


    # ─────────────────────────────────────────────────────────────────────
    #  MEMORY REINFORCEMENT
    # ─────────────────────────────────────────────────────────────────────

    def reinforce_memory(
        self,
        existing: Memory,
        incoming_score: float,
        source:   str,
    ) -> Memory:
        """
        Reinforce an existing memory with an incoming score (gossip or repetition).

        Old memory: continues decaying at its current accelerated rate.
        New memory: created at old_score + 20% of incoming_score,
                    inherits the old memory's decay_rate at this exact moment,
                    then accelerates from that inherited rate independently.

        Returns the new Memory object.
        """
        current_accel     = existing.current_acceleration()
        inherited_rate    = existing.decay_rate * current_accel
        new_score         = min(SCORE_MAX, existing.score + incoming_score * GOSSIP_REINFORCE)

        new_memory = Memory(
            description               = existing.description,
            score                     = new_score,
            original_timestamp        = existing.original_timestamp,
            last_reinforced_timestamp = time.time(),
            decay_rate                = inherited_rate,
            source_npc                = source,
            verified                  = existing.verified,
            passed_on                 = existing.passed_on,
        )
        self.memories.append(new_memory)
        return new_memory


    # ─────────────────────────────────────────────────────────────────────
    #  SCORE INTERACTION
    # ─────────────────────────────────────────────────────────────────────

    def score_interaction(
        self,
        interaction:  str,
        player_state: dict,
    ) -> float:
        """
        AI judges the interaction and returns a score 0–1000.
        0 means forgettable — nothing is stored.
        Called silently in the background after every player interaction.
        """
        memory_summary = self._summarise_memories()
        emotion_summary = self._summarise_emotions()
        trait_summary   = self._summarise_traits()
        relationship_summary = self._summarise_relationships(player_state.get("name", "player"))
        gossip_summary  = self._summarise_gossip()

        system = (
            "You are evaluating how memorable an event is to a person in Kyros. "
            "Given an interaction and full NPC context, output ONLY a JSON object "
            "with a single key 'score' (integer 0–1000). "
            "0 = completely forgettable. 1000 = permanently life-changing. "
            "Consider: NPC personality, existing memories of this player, "
            "repetition of similar actions, emotional state, relationship history, "
            "gossip, and the nature of the action itself. "
            "Higher gullibility means the NPC is more impressionable. "
            "Repeated actions score higher than first-time actions but with diminishing returns. "
            "Output only valid JSON, no other text."
        )

        context = (
            f"NPC: {self.name}\n"
            f"Personality: {self.personality}\n"
            f"Intelligence: {self.intelligence}\n"
            f"Gullibility: {self.gullibility:.0f}/100\n"
            f"Emotional state: {emotion_summary}\n"
            f"Character traits: {trait_summary}\n"
            f"Relationship with player: {relationship_summary}\n"
            f"Existing memories of player: {memory_summary}\n"
            f"Gossip about player: {gossip_summary}\n"
            f"Player state: {json.dumps(player_state)}\n"
            f"Interaction to score: {interaction}"
        )

        result = _call_claude_json(system, [{"role": "user", "content": context}])
        raw    = result.get("score", 0)

        try:
            score = float(raw)
        except (TypeError, ValueError):
            score = 0.0

        return max(0.0, min(SCORE_MAX, score))


    # ─────────────────────────────────────────────────────────────────────
    #  GOSSIP RECEPTION
    # ─────────────────────────────────────────────────────────────────────

    def receive_gossip(
        self,
        player_gossip_list: list[GossipEntry],
        guild_registry:     Optional[dict[str, Guild]] = None,
        npc_registry:       Optional[dict] = None,
    ) -> None:
        """
        Process all updated gossip entries from the player's gossip list.

        Rules:
        - No matching memory: create at 50% of gossip score
        - Matching memory: reinforce at 20% of gossip score
        - Two versions of same entry: NPC starts calculations from lowest score
        - Inversion applied if gossip source is a rival
        - Gullibility gates how much the NPC trusts the gossip
        - Guild instant relay triggered if applicable
        """
        # Group entries by description to handle dual-version rule
        grouped: dict[str, list[GossipEntry]] = {}
        for entry in player_gossip_list:
            key = entry.description.lower()
            grouped.setdefault(key, []).append(entry)

        for desc_key, entries in grouped.items():
            # Sort by score ascending — NPC starts from lowest per design
            entries.sort(key=lambda e: e.score)

            for entry in entries:
                adjusted_score = self._apply_gullibility(entry.score, entry.source_npc)
                adjusted_score = self._apply_relationship_inversion(
                    adjusted_score, entry.description, entry.source_npc
                )

                existing = self._get_memory(desc_key)
                if existing:
                    self.reinforce_memory(existing, adjusted_score, entry.source_npc)
                else:
                    new_score = adjusted_score * GOSSIP_NEW_RATE
                    self.create_memory(
                        description = entry.description,
                        score       = new_score,
                        source      = entry.source_npc,
                        verified    = entry.verified,
                    )

        # Relay through guild messaging system
        if guild_registry:
            self._relay_guild_gossip(player_gossip_list, guild_registry, npc_registry)

    def _apply_gullibility(self, score: float, source_npc: str) -> float:
        """
        Scale incoming gossip score by gullibility.
        High gullibility (100) accepts full score.
        Low gullibility (0) reduces score significantly.
        """
        gull_factor = self.gullibility / 100.0   # 0–1
        # Skeptical NPCs discount gossip toward 50% of face value
        adjusted = score * (0.5 + gull_factor * 0.5)
        return adjusted

    def _apply_relationship_inversion(
        self,
        score:       float,
        description: str,
        source_npc:  str,
    ) -> float:
        """
        If the source NPC is a rival/enemy, invert the emotional connotation
        and scale by relationship intensity, personality, and current emotional state.

        Nice-to-rival becomes negative. Mean-to-rival becomes positive.
        The score magnitude is preserved but its meaning is inverted via
        creating a new description with inverted framing — the actual score
        returned here is the raw value; description reframing happens in
        the memory description string when create_memory is called.
        """
        rel = self._get_relationship(source_npc)
        if not rel or not rel.is_hostile:
            return score

        # Inversion scaling: intensity of rivalry, dominant emotion, key trait
        intensity_factor = rel.intensity / 100.0
        emotion_factor   = self._dominant_emotion_factor()
        trait_factor     = self._paranoid_factor()

        inversion_strength = intensity_factor * emotion_factor * trait_factor
        return score * inversion_strength   # score retained, meaning flipped in description

    def _dominant_emotion_factor(self) -> float:
        """Returns a 0.5–1.5 multiplier from current dominant emotion."""
        if not self.emotions:
            return 1.0
        dominant = max(self.emotions, key=lambda e: e.intensity)
        amplifying = {"anger", "contempt", "envy", "vindictive"}
        dampening  = {"joy", "love", "gratitude", "relief"}
        if dominant.type in amplifying:
            return 1.0 + (dominant.intensity / 200.0)
        if dominant.type in dampening:
            return 1.0 - (dominant.intensity / 200.0)
        return 1.0

    def _paranoid_factor(self) -> float:
        """Paranoid NPCs are more suspicious and amplify rival gossip."""
        trait = self._get_trait("paranoid")
        if not trait:
            return 1.0
        return 1.0 + (trait.value / 200.0)


    # ─────────────────────────────────────────────────────────────────────
    #  GOSSIP SHARING
    # ─────────────────────────────────────────────────────────────────────

    def share_gossip(self, player_gossip_list: list[GossipEntry]) -> None:
        """
        Push all updated memory entries from this NPC into the player's gossip list.
        Marks memories as passed_on.
        """
        for memory in self.memories:
            if memory.passed_on:
                continue
            entry = GossipEntry(
                description               = memory.description,
                score                     = memory.score,
                original_timestamp        = memory.original_timestamp,
                last_reinforced_timestamp = memory.last_reinforced_timestamp,
                decay_rate                = memory.decay_rate,
                source_npc                = self.name,
                passed_on                 = False,
                verified                  = memory.verified,
                original_score            = memory.score,
                received_timestamp        = time.time(),
            )
            player_gossip_list.append(entry)
            memory.passed_on = True

    def _relay_guild_gossip(
        self,
        entries:        list[GossipEntry],
        guild_registry: dict[str, Guild],
        npc_registry:   Optional[dict] = None,
    ) -> None:
        """
        Relay gossip instantly to all active guild members through the
        guild messaging system.

        For each active guild membership:
        - Skips expelled members and dissolved guilds
        - Delivers each gossip entry to every other member NPC
        - Applies guild rank weighting to incoming score
        - Applies rival guild inversion if the guilds are rivals
        - Married/lover pairs receive gossip at full original potency
        - npc_registry maps NPC name -> NPC instance for live delivery
          If npc_registry is None, relay is skipped (deferred to simulation)
        """
        if npc_registry is None:
            return

        for membership in self.guilds:
            if membership.expelled:
                continue
            guild = guild_registry.get(membership.guild_name)
            if not guild or guild.dissolved:
                continue

            sender_rank_weight = guild.rank_weight(self.name)

            for member_name in guild.members:
                if member_name == self.name:
                    continue

                recipient = npc_registry.get(member_name)
                if not recipient:
                    continue

                relay_entries = []
                for entry in entries:
                    # Married/lover pairs get full original potency
                    rel = recipient._get_relationship(self.name)
                    if rel and rel.is_intimate:
                        effective_score = entry.original_score
                    else:
                        effective_score = entry.score * sender_rank_weight

                    relay = GossipEntry(
                        description               = entry.description,
                        score                     = effective_score,
                        original_timestamp        = entry.original_timestamp,
                        last_reinforced_timestamp = entry.last_reinforced_timestamp,
                        decay_rate                = entry.decay_rate,
                        source_npc                = self.name,
                        passed_on                 = True,
                        verified                  = entry.verified,
                        original_score            = entry.original_score,
                        received_timestamp        = time.time(),
                    )
                    relay_entries.append(relay)

                # Apply rival guild inversion if applicable
                for rival_guild_name in guild.get_rival_guilds():
                    rival_guild = guild_registry.get(rival_guild_name)
                    if rival_guild and member_name in rival_guild.members:
                        relay_entries = [
                            recipient.apply_gossip_inversion(
                                e,
                                Relationship(
                                    entity_a  = self.name,
                                    entity_b  = member_name,
                                    type      = "rival",
                                    intensity = 75.0,
                                    timestamp = time.time(),
                                )
                            )
                            for e in relay_entries
                        ]

                recipient.receive_gossip(relay_entries, guild_registry, npc_registry)


    # ─────────────────────────────────────────────────────────────────────
    #  DIALOGUE — REACT TO PLAYER
    # ─────────────────────────────────────────────────────────────────────

    def react_to_player(
        self,
        player_input: str,
        player_state: dict,
    ) -> str:
        """
        Generate an in-character AI response to the player's input.

        Pipeline:
        1. Check interaction willingness — emotional state may refuse or cut short
        2. Analyze tone of player input
        3. Build full context from all NPC attributes
        4. Call AI for dialogue response
        5. Score the interaction silently
        6. Check for lies
        """
        # 1. Willingness gate
        willingness = self.interaction_willingness
        if willingness < 10.0:
            return self._unwilling_response()

        # 2. Tone analysis (feeds into scoring pipeline)
        tone = self.analyze_tone(player_input)

        # 3. Build context
        full_context = self._build_dialogue_context(player_state, tone)

        # 4. Conversation history
        augmented_input = (
            f"[Player tone detected: {tone}]\n"
            f"[Player state: {json.dumps(player_state)}]\n"
            f"Player says: {player_input}"
        )
        self._conversation_history.append({"role": "user", "content": augmented_input})

        response = _call_claude(
            system   = full_context,
            messages = self._conversation_history,
        )
        if not response:
            response = "..."

        self._conversation_history.append({"role": "assistant", "content": response})

        # Keep history bounded to 20 turns (10 exchanges)
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]

        # 5. Score interaction silently
        interaction_description = f"Player said to {self.name}: '{player_input}' (tone: {tone})"
        score = self.score_interaction(interaction_description, player_state)
        if score > 0:
            self.create_memory(
                description = interaction_description,
                score       = score,
                source      = "player",
            )

        # 6. Lie check — if player made a factual claim
        if self._is_factual_claim(player_input):
            self.check_lie(player_input, player_state)

        # Willingness cut-short at moderate levels
        if willingness < 40.0 and len(self._conversation_history) > 4:
            return response + "\n" + self._cutshort_response()

        return response

    def _unwilling_response(self) -> str:
        """Brief response when NPC is too emotionally distressed to engage."""
        dominant = max(self.emotions, key=lambda e: e.intensity) if self.emotions else None
        if dominant and dominant.type == "grief" and not dominant.masked:
            return f"{self.name} looks away. They don't seem ready to talk."
        if dominant and dominant.type == "anger" and not dominant.masked:
            return f"{self.name} glares at you. 'Not now.'"
        return f"{self.name} doesn't respond."

    def _cutshort_response(self) -> str:
        return f"\n{self.name} seems distracted and the conversation trails off."

    def _is_factual_claim(self, text: str) -> bool:
        """
        Heuristic: does the player's input contain a factual assertion
        the NPC could verify or disbelieve?
        """
        claim_words = ["i am", "i have", "i did", "i killed", "i completed",
                       "i found", "i own", "i defeated", "i never", "i always"]
        text_lower  = text.lower()
        return any(w in text_lower for w in claim_words)

    def _build_dialogue_context(self, player_state: dict, tone: str) -> str:
        """Build the full system prompt for dialogue, including all NPC state."""
        return (
            f"{self.system_prompt}\n\n"
            f"[NPC INTERNAL STATE — never recite directly, use to inform responses]\n"
            f"Personality: {self.personality}\n"
            f"Intelligence: {self.intelligence}\n"
            f"Emotional state: {self._summarise_emotions()}\n"
            f"Character traits: {self._summarise_traits()}\n"
            f"Wealth status: {'comfortable' if self.wealth.value > 50 else 'struggling'}\n"
            f"Relationship with player: {self._summarise_relationships(player_state.get('name', 'player'))}\n"
            f"Memories of player: {self._summarise_memories()}\n"
            f"Gossip about player: {self._summarise_gossip()}\n"
            f"Player detected tone: {tone}\n"
            f"Interaction willingness: {self.interaction_willingness:.0f}/100\n"
            f"Magic ability: {self.magic_ability:.0f}/100\n"
        )


    # ─────────────────────────────────────────────────────────────────────
    #  TONE ANALYSIS
    # ─────────────────────────────────────────────────────────────────────

    def analyze_tone(self, player_input: str) -> str:
        """
        AI analyzes the player's word choice for tone.
        Returns a tone descriptor string fed into score_interaction.
        """
        system = (
            "Analyze the tone of the following dialogue spoken to a person in Kyros. "
            "Output ONLY a JSON object with key 'tone' and a short descriptor. "
            "Examples: polite, aggressive, deceptive, flattering, threatening, "
            "curious, dismissive, pleading, grateful, rude, formal, casual. "
            "No other text."
        )
        result = _call_claude_json(system, [{"role": "user", "content": player_input}])
        return result.get("tone", "neutral")


    # ─────────────────────────────────────────────────────────────────────
    #  LIE DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def check_lie(self, claim: str, world_data: dict) -> bool:
        """
        Cross-check a player's claim against world data, weighted by gullibility.

        High gullibility: skips or softens the check.
        Low gullibility: rigorous check.

        If believed: creates a false unverified memory.
        If caught: creates 'player lied to me' memory, triggers relationship hit.

        Returns True if lie was caught.
        """
        # Gullibility roll: higher gullibility = more likely to just believe it
        gull_roll = random.uniform(0, 100)
        if gull_roll < self.gullibility:
            # Believed without checking — create false memory
            score = self.score_interaction(f"Player claimed: {claim}", world_data)
            if score > 0:
                self.create_memory(
                    description = f"Player claimed: {claim}",
                    score       = score,
                    source      = "player",
                    verified    = False,
                )
            return False

        # Cross-check against world data
        system = (
            "You are evaluating a claim made to a person in Kyros. Given the claim and world data, "
            "determine if the claim is true or false. "
            "Output ONLY a JSON object with key 'is_lie' (boolean) and 'reason' (string). "
            "No other text."
        )
        context = (
            f"Player claim: {claim}\n"
            f"World data: {json.dumps(world_data)}"
        )
        result  = _call_claude_json(system, [{"role": "user", "content": context}])
        is_lie  = result.get("is_lie", False)

        if is_lie:
            # Caught — create relationship damage and 'lied to me' memory
            lie_score = self.score_interaction(
                f"Player lied to me about: {claim}", world_data
            )
            if lie_score > 0:
                self.create_memory(
                    description = f"Player lied to me about: {claim}",
                    score       = lie_score,
                    source      = "player",
                    verified    = True,
                )
            self.update_relationship("player", f"Caught lying about: {claim}", -15.0)
        else:
            # Believed after checking — verified memory
            score = self.score_interaction(f"Player claimed (verified): {claim}", world_data)
            if score > 0:
                self.create_memory(
                    description = f"Player claimed: {claim}",
                    score       = score,
                    source      = "player",
                    verified    = True,
                )

        return is_lie


    # ─────────────────────────────────────────────────────────────────────
    #  EMOTION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def update_emotion(
        self,
        emotion_type: str,
        intensity:    float,
        source:       str,
        masked:       bool = False,
    ) -> None:
        """
        Add or update an emotion in the stack.
        Triggers temporary character trait shifts.
        Masking determined by personality if not explicitly set.
        """
        if emotion_type not in EMOTION_TYPES:
            return

        # Check if this emotion type already exists — update intensity
        for emotion in self.emotions:
            if emotion.type == emotion_type:
                emotion.intensity  = min(100.0, emotion.intensity + intensity)
                emotion.source     = source
                emotion.timestamp  = time.time()
                self._apply_trait_push(emotion_type, emotion.intensity)
                return

        # Decay rate: emotions fade over real time
        # Low intensity fades fast, high intensity fades slow
        decay_rate = max(0.001, (100.0 - intensity) / 100.0 * 0.01)

        # Masking: stoic/calm personalities more likely to mask
        if not masked:
            calm_trait = self._get_trait("hotheaded")   # high value = calm
            if calm_trait and calm_trait.value > 70:
                masked = True

        new_emotion = Emotion(
            type       = emotion_type,
            intensity  = min(100.0, intensity),
            source     = source,
            timestamp  = time.time(),
            decay_rate = decay_rate,
            masked     = masked,
        )
        self.emotions.append(new_emotion)
        self._apply_trait_push(emotion_type, intensity)

    def _apply_trait_push(self, emotion_type: str, intensity: float) -> None:
        """
        Temporarily push character traits based on emotion.
        The push is proportional to intensity.
        Traits drift back as emotions decay.
        """
        push_map = {
            "anger":       [("hotheaded",  +intensity * 0.2), ("calm",      -intensity * 0.2)],
            "grief":       [("complacent", +intensity * 0.1), ("ambitious", -intensity * 0.1)],
            "fear":        [("cowardly",   +intensity * 0.2), ("brave",     -intensity * 0.2)],
            "joy":         [("generous",   +intensity * 0.1), ("greedy",    -intensity * 0.1)],
            "contempt":    [("arrogant",   +intensity * 0.15)],
            "love":        [("forgiving",  +intensity * 0.1), ("vindictive",-intensity * 0.1)],
            "envy":        [("greedy",     +intensity * 0.15)],
            "trust":       [("trusting",   +intensity * 0.1), ("paranoid",  -intensity * 0.1)],
            "anxiety":     [("paranoid",   +intensity * 0.15)],
            "gratitude":   [("generous",   +intensity * 0.1)],
        }
        pushes = push_map.get(emotion_type, [])
        for trait_name, delta in pushes:
            trait = self._get_trait(trait_name)
            if trait:
                trait.shift(delta)


    # ─────────────────────────────────────────────────────────────────────
    #  RELATIONSHIP MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def update_relationship(
        self,
        entity_b:    str,
        event:       str,
        delta:       float,
        new_type:    Optional[str] = None,
    ) -> None:
        """
        Adjust relationship with entity_b.
        Creates relationship if it doesn't exist.
        """
        rel = self._get_relationship(entity_b)
        if rel:
            rel.update(event, delta, new_type)
        else:
            self.relationships.append(Relationship(
                entity_a  = self.name,
                entity_b  = entity_b,
                type      = new_type or "acquaintance",
                intensity = max(0.0, min(100.0, 50.0 + delta)),
                timestamp = time.time(),
                history   = [{"event": event, "timestamp": time.time()}],
            ))

    def apply_gossip_inversion(
        self,
        gossip_entry: GossipEntry,
        relationship: Relationship,
    ) -> GossipEntry:
        """
        Invert gossip connotation for rival/enemy relationships.

        Nice-to-rival → 'helped my rival' (negative framing)
        Mean-to-rival → 'harmed my rival' (positive framing)

        Scaling: relationship intensity × personality × emotional state.
        Returns a modified GossipEntry with inverted description.
        """
        intensity_factor = relationship.intensity / 100.0
        emotion_factor   = self._dominant_emotion_factor()
        trait_factor     = self._vindictive_factor()
        inversion_scale  = intensity_factor * emotion_factor * trait_factor

        # Reframe the description
        original_desc    = gossip_entry.description
        inverted_desc    = self._ai_invert_description(original_desc, relationship.type)

        inverted = GossipEntry(
            description               = inverted_desc,
            score                     = gossip_entry.score * inversion_scale,
            original_timestamp        = gossip_entry.original_timestamp,
            last_reinforced_timestamp = gossip_entry.last_reinforced_timestamp,
            decay_rate                = gossip_entry.decay_rate,
            source_npc                = gossip_entry.source_npc,
            passed_on                 = gossip_entry.passed_on,
            verified                  = gossip_entry.verified,
            original_score            = gossip_entry.original_score,
            received_timestamp        = gossip_entry.received_timestamp,
        )
        return inverted

    def _ai_invert_description(self, description: str, relationship_type: str) -> str:
        """Use AI to reframe a memory description from a rival's perspective."""
        system = (
            "You are reframing a memory from the perspective of a rival. "
            "Given an event description and relationship type, rewrite it with the opposite emotional connotation. "
            "Example: 'helped a farmer' from a rival's view becomes 'helped my rival's ally'. "
            "Keep it short. Output ONLY the reframed description string, no JSON, no quotes."
        )
        content = f"Description: {description}\nRelationship: {relationship_type}"
        result  = _call_claude(system, [{"role": "user", "content": content}], max_tokens=100)
        return result.strip() if result else f"[rival framing] {description}"

    def _vindictive_factor(self) -> float:
        trait = self._get_trait("vindictive")
        if not trait:
            return 1.0
        return 1.0 + (trait.value / 200.0)


    # ─────────────────────────────────────────────────────────────────────
    #  WEALTH MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def update_wealth(self, delta: float, source: str) -> None:
        """
        Adjust wealth, log change, trigger trait drift, update credit score
        and political eligibility.
        """
        self.wealth.update(delta, source)
        self._drift_traits_from_wealth(delta)
        self._update_credit_score(delta)
        self.update_political_standing()

    def _drift_traits_from_wealth(self, delta: float) -> None:
        """Gradual trait drift from wealth changes."""
        if delta < 0:
            # Getting poorer: drift toward greedy, cowardly
            self._shift_trait("greedy",   +abs(delta) * 0.001)
            self._shift_trait("cowardly", +abs(delta) * 0.0005)
            self._shift_trait("generous", -abs(delta) * 0.001)
        else:
            # Getting richer: can drift back
            self._shift_trait("greedy",   -delta * 0.0005)
            self._shift_trait("generous", +delta * 0.0005)

    def _shift_trait(self, trait_name: str, delta: float) -> None:
        trait = self._get_trait(trait_name)
        if trait:
            trait.shift(delta)

    def _update_credit_score(self, delta: float) -> None:
        if delta >= 0:
            self.wealth.credit_score = min(1000.0, self.wealth.credit_score + delta * 0.01)
        else:
            self.wealth.credit_score = max(0.0, self.wealth.credit_score + delta * 0.02)

    def update_political_standing(self, guild_registry: Optional[dict] = None) -> list[str]:
        """
        Check wealth against political office thresholds.
        Uses AI to evaluate whether current wealth is sufficient for each
        held office, relative to regional context.

        Returns a list of offices lost due to insufficient wealth.
        Offices requiring faked wealth (ally backing) are evaluated separately.
        """
        if not self.political_offices:
            return []

        lost_offices = []

        system = (
            "You are evaluating whether a person in Kyros can retain their political offices. "
            "Given their wealth and each office, decide which offices they can still hold. "
            "Output ONLY a JSON object with key offices_retained (list of strings) "
            "and offices_lost (list of strings). No other text."
        )

        context = (
            f"NPC: {self.name}\n"
            f"Current wealth: {self.wealth.value:.0f} gold\n"
            f"Credit score: {self.wealth.credit_score:.0f}/1000\n"
            f"Political offices held: {self.political_offices}\n"
            f"Guild memberships: {[m.guild_name + ' rank ' + m.rank for m in self.guilds if not m.expelled]}\n"
            f"Relationships that might provide financial backing: "
            f"{[r.type + ' with ' + r.entity_b for r in self.relationships if r.intensity > 60]}"
        )

        result = _call_claude_json(system, [{"role": "user", "content": context}])
        if not result:
            return []

        offices_lost     = result.get("offices_lost", [])
        offices_retained = result.get("offices_retained", self.political_offices)

        for office in offices_lost:
            if office in self.political_offices:
                self.political_offices.remove(office)
                lost_offices.append(office)
                # Losing office triggers emotion
                self.update_emotion("grief", 40.0, f"lost political office: {office}")

        self.political_offices = [o for o in offices_retained if o in self.political_offices or o not in lost_offices]

        return lost_offices


    # ─────────────────────────────────────────────────────────────────────
    #  WANTED LEVEL
    # ─────────────────────────────────────────────────────────────────────

    def update_wanted_level(
        self,
        crime:        str,
        jurisdiction: str,
        reputation_list: list[ReputationEntry],
    ) -> None:
        """
        Update wanted level at the appropriate reputation tier and jurisdiction.
        Spreads through gossip and independent calculation.
        """
        tier = self._jurisdiction_to_tier(jurisdiction)
        for rep in reputation_list:
            if rep.tier == tier and rep.location == jurisdiction:
                rep.update(-50.0)    # crimes reduce reputation
                return
        reputation_list.append(ReputationEntry(
            tier      = tier,
            location  = jurisdiction,
            score     = -50.0,
            timestamp = time.time(),
        ))

    def _jurisdiction_to_tier(self, jurisdiction: str) -> str:
        mapping = {
            "local": "local", "town": "local", "village": "local",
            "regional": "regional", "province": "regional",
            "kingdom": "kingdom", "empire": "empire",
        }
        return mapping.get(jurisdiction.lower(), "local")


    # ─────────────────────────────────────────────────────────────────────
    #  JAILBREAK
    # ─────────────────────────────────────────────────────────────────────

    def attempt_jailbreak(
        self,
        method:            str,
        relationships:     list[Relationship],
        quest_bonuses:     float,
        reputation_score:  float,
    ) -> bool:
        """
        Attempt a jailbreak. Success rate is hidden from the player.

        Regular success factors: method, relationships, quests, reputation.
        Illegal extension bonus: added separately, capped at 75%.
        Minimum fail chance: always 1%.

        Returns True if successful.
        """
        if not self.sentence:
            return False

        # Regular success calculation (can reach 100% before cap)
        base_score = self._jailbreak_base_score(method, relationships, quest_bonuses, reputation_score)

        # Illegal extension bonus (separate calculation, max 75%)
        extension_bonus = self.sentence.jailbreak_bonus()

        # Combined total (before minimum fail floor)
        total = base_score + extension_bonus

        # Apply minimum fail — success can never exceed 99%
        success_chance = min(1.0 - JAIL_MIN_FAIL, total)

        roll    = random.random()
        success = roll < success_chance

        if not success:
            self.sentence.attempts += 1
            # Failed attempt increases sentence
            self.sentence.duration_real_seconds += 1800   # +30 real minutes
        else:
            self.sentence = None

        return success

    def _jailbreak_base_score(
        self,
        method:           str,
        relationships:    list[Relationship],
        quest_bonuses:    float,
        reputation_score: float,
    ) -> float:
        """
        Calculate base jailbreak success 0.0–1.0 from all regular factors.
        """
        # Relationship factor: loyal friends or guards who like you help
        rel_factor = 0.0
        for rel in relationships:
            if rel.is_hostile:
                continue
            rel_factor += (rel.intensity / 100.0) * 0.1
        rel_factor = min(0.4, rel_factor)

        # Quest factor
        quest_factor = min(0.3, quest_bonuses)

        # Reputation factor (local jurisdiction)
        rep_factor = min(0.2, max(0.0, reputation_score / 1000.0) * 0.2)

        # Method factor — rough heuristic; full AI scoring possible later
        method_map = {
            "pick_lock":    0.15,
            "bribe":        0.20,
            "distract":     0.10,
            "overpower":    0.10,
            "magic":        0.25,
            "outside_help": 0.30,
        }
        method_factor = method_map.get(method, 0.05)

        return rel_factor + quest_factor + rep_factor + method_factor


    # ─────────────────────────────────────────────────────────────────────
    #  NPC AUTONOMOUS BEHAVIOUR (SIMULATION TICKS)
    # ─────────────────────────────────────────────────────────────────────

    def pursue_goal(self, npc_registry: Optional[dict] = None, world_state: Optional[dict] = None) -> Optional[str]:
        """
        NPC acts toward their current top-priority goal during a simulation tick.

        The AI evaluates the NPC full context and decides:
        - What concrete action to take toward the goal
        - Whether the goal changes based on current circumstances
        - Whether the action affects wealth, relationships, or emotions

        Returns a plain-text description of the action taken, or None if
        the NPC is unavailable or has no goals.
        """
        if not self.goals or not self.is_available:
            return None

        goal = self.goals[0]

        system = (
            "You are a person living in the world of Kyros. "
            "Given the NPC full context and their current top goal, decide what concrete "
            "action they take this simulation tick toward that goal. "
            "Output ONLY a JSON object with these keys: "
            "action (string: what they did), "
            "wealth_delta (float: gold gained or lost, 0 if none), "
            "emotion_triggered (string or null: emotion type if any), "
            "emotion_intensity (float 0-100, 0 if none), "
            "goal_achieved (bool: true if this goal is now complete), "
            "new_goal (string or null: replacement goal if achieved). "
            "No other text."
        )

        context = (
            f"NPC: {self.name}\n"
            f"Personality: {self.personality}\n"
            f"Intelligence: {self.intelligence}\n"
            f"Current goal: {goal}\n"
            f"All goals: {self.goals}\n"
            f"Wealth: {self.wealth.value:.0f}\n"
            f"Emotional state: {self._summarise_emotions()}\n"
            f"Character traits: {self._summarise_traits()}\n"
            f"Relationships: {[r.type + ' with ' + r.entity_b for r in self.relationships]}\n"
            f"World state: {json.dumps(world_state or {})}"
        )

        result = _call_claude_json(system, [{"role": "user", "content": context}])
        if not result:
            return None

        action           = result.get("action", "")
        wealth_delta     = float(result.get("wealth_delta", 0))
        emotion_type     = result.get("emotion_triggered")
        emotion_intensity= float(result.get("emotion_intensity", 0))
        goal_achieved    = result.get("goal_achieved", False)
        new_goal         = result.get("new_goal")

        if wealth_delta != 0:
            self.update_wealth(wealth_delta, f"goal: {goal}")

        if emotion_type and emotion_intensity > 0:
            self.update_emotion(emotion_type, emotion_intensity, f"goal: {goal}")

        if goal_achieved:
            self.goals.pop(0)
            if new_goal:
                self.goals.append(new_goal)

        return f"{self.name}: {action}" if action else None

    def follow_schedule(self, current_npc_hour: float) -> str:
        """
        Advance NPC through daily routine.
        Returns current status: 'available' | 'sleeping' | 'working' | 'away'
        """
        if not self.schedule:
            return "available"
        for (start, end), status in self.schedule.items():
            if start <= current_npc_hour < end:
                return status
        return "available"


    # ─────────────────────────────────────────────────────────────────────
    #  SESSION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def reset_conversation(self) -> None:
        """Clear conversation history when player leaves the location."""
        self._conversation_history = []


    # ─────────────────────────────────────────────────────────────────────
    #  SUMMARY HELPERS (for AI context building)
    # ─────────────────────────────────────────────────────────────────────

    def _summarise_memories(self) -> str:
        if not self.memories:
            return "none"
        top = sorted(self.memories, key=lambda m: m.score, reverse=True)[:5]
        return "; ".join(
            f"'{m.description}' (score={m.score:.0f}, verified={m.verified})"
            for m in top
        )

    def _summarise_emotions(self) -> str:
        if not self.emotions:
            return "neutral"
        visible = [e for e in self.emotions if not e.masked]
        if not visible:
            return "neutral (masked)"
        return ", ".join(f"{e.type} ({e.intensity:.0f})" for e in visible)

    def _summarise_traits(self) -> str:
        if not self.character_traits:
            return "unknown"
        return ", ".join(
            f"{t.type}={t.value:.0f}" for t in self.character_traits
        )

    def _summarise_relationships(self, entity: str) -> str:
        rel = self._get_relationship(entity)
        if not rel:
            return "no prior relationship"
        return f"{rel.type} (intensity={rel.intensity:.0f})"

    def _summarise_gossip(self) -> str:
        if not self.gossip_list:
            return "none"
        top = sorted(self.gossip_list, key=lambda g: g.score, reverse=True)[:3]
        return "; ".join(
            f"'{g.description}' from {g.source_npc} (score={g.score:.0f})"
            for g in top
        )