"""
kyros/combat.py

CombatSystem — all combat logic for Kyros.

Owns:
- Turn order (Agility + random roll, updates mid-combat)
- Multi-enemy targeting (player chooses, enemies can focus one target)
- Action system (attack, skill, item, defend, taunt, flee)
- Multicasting (max 2 spells: 1 mental + 1 verbal, efficiency by rarity)
- Multitasking (infinite actions, count by rarity, simultaneous)
- Status effects (time-based IRL seconds, stackable, separate timers)
- Monster AI (intelligence by tier + race type)
- Alpha monsters (reinforcement calls, only discoverable via Identify)
- Reinforcement system (delay based on caller + called, capped by area population)
- 10-minute inactivity rule (flee auto-trigger, warned at 9 minutes)
- Weather modifiers (rechecked each turn)
- Combat display (health bars, status effects, turn order)
- Death handoff to player.on_death()
- AtkPwr/Defense compatibility layer (used until full class system implemented)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Agility roll range added to base agility for turn order
AGILITY_ROLL_RANGE      = 0.20     # ±20% of agility value

# Inactivity limits
INACTIVITY_LIMIT        = 600.0    # 10 minutes in seconds
INACTIVITY_WARNING      = 540.0    # warn at 9 minutes

# Flee base success chances per grade gap
FLEE_BASE_CHANCE        = 0.75     # same grade
FLEE_GRADE_PENALTY      = 0.20     # -20% per grade above player

# Defend damage reduction
DEFEND_REDUCTION        = 0.50     # 50% damage reduction when defending

# Status effect tick interval
STATUS_TICK_INTERVAL    = 1.0      # tick every real second

# Reinforcement call delay range (real seconds)
REINFORCE_DELAY_MIN     = 5.0
REINFORCE_DELAY_MAX     = 30.0

# Multicast mana efficiency by rarity index
# 0=inferior, 1=common, 2=uncommon, 3=rare, 4=epic, 5=legendary, 6=mythic, 7=divine
MULTICAST_EFFICIENCY = {
    0: 0.60,   # inferior: each spell costs 40% more mana, does 40% less damage
    1: 0.65,
    2: 0.70,
    3: 0.75,
    4: 0.82,
    5: 0.90,
    6: 0.95,
    7: 1.00,   # divine: fully efficient
}

# Multitask action count by rarity index
MULTITASK_ACTIONS = {
    0: 2,    # inferior: 2 actions
    1: 3,
    2: 4,
    3: 5,
    4: 7,
    5: 10,
    6: 15,
    7: 999,  # divine: effectively unlimited
}

# Monster intelligence ranking by race type (lower = less intelligent)
MONSTER_INTELLIGENCE = {
    "plant":       1,
    "fungal":      1,
    "slime":       2,
    "insect":      3,
    "aquatic":     3,
    "reptile":     4,
    "beast":       5,
    "animal":      5,
    "undead":      4,
    "construct":   3,
    "elemental":   5,
    "humanoid":    8,
    "magical":     7,
    "demon":       9,
    "divine":      10,
}

# Grade multiplier for monster intelligence
GRADE_INTELLIGENCE_MULT = {
    0: 1.0,   # G
    1: 1.2,   # F
    2: 1.5,   # E
    3: 1.8,   # D
    4: 2.2,   # C
    5: 2.8,   # B
    6: 3.5,   # A
    7: 4.5,   # S
    8: 6.0,   # God
    9: 8.0,   # Godking
    10: 10.0, # Primordial
}

RARITY_TIERS = ["inferior", "common", "uncommon", "rare", "epic",
                "legendary", "mythic", "divine"]


# ─────────────────────────────────────────────────────────────────────────────
#  STATUS EFFECTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StatusEffect:
    """
    A time-based status effect. Ticks every real second.
    Total damage is fixed regardless of duration — spread across ticks.
    Multiple instances of same type stack as separate timers.
    """
    effect_id:      str
    name:           str
    effect_type:    str        # bleed / burn / poison / freeze / stun / slow /
                               # concussion / internal_bleed / psychic_shock / etc.
    source:         str        # who applied it
    applied_at:     float      = field(default_factory=time.time)
    duration:       float      = 10.0     # total real seconds
    total_damage:   float      = 0.0      # spread across ticks
    damage_per_tick:float      = 0.0      # computed: total_damage / duration
    stat_modifier:  dict       = field(default_factory=dict)  # {stat: multiplier}
    is_stun:        bool       = False    # skips target's turn
    last_tick:      float      = field(default_factory=time.time)

    def __post_init__(self):
        if self.total_damage > 0 and self.duration > 0:
            self.damage_per_tick = self.total_damage / self.duration

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.applied_at) >= self.duration

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - (time.time() - self.applied_at))

    def tick(self) -> float:
        """Returns damage dealt this tick. Called every real second."""
        now = time.time()
        if self.is_expired:
            return 0.0
        if (now - self.last_tick) < STATUS_TICK_INTERVAL:
            return 0.0
        self.last_tick = now
        return self.damage_per_tick

    def display(self) -> str:
        remaining = self.remaining
        if self.total_damage > 0:
            return f"[{self.name} {remaining:.0f}s {self.total_damage:.0f}dmg]"
        return f"[{self.name} {remaining:.0f}s]"


# ─────────────────────────────────────────────────────────────────────────────
#  COMBATANT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Combatant:
    """
    A wrapper around a player or monster for use in combat.
    Tracks combat-specific state without modifying the underlying entity.
    """
    name:           str
    entity:         object           # Player or NPC/Monster instance
    is_player:      bool   = False
    is_alpha:       bool   = False   # only discoverable via Identify
    monster_type:   str    = "beast" # for intelligence calculation
    grade_index:    int    = 0

    # Combat stats (pulled from entity, kept here for quick access)
    max_hp:         float  = 10.0
    current_hp:     float  = 10.0
    max_mana:       float  = 10.0
    current_mana:   float  = 10.0
    agility:        float  = 10.0
    attack_power:   float  = 5.0
    defense:        float  = 2.0

    # Turn state
    is_defending:   bool   = False
    is_stunned:     bool   = False
    has_taunt:      bool   = False   # taunting forces enemies to target this combatant
    turn_initiative:float  = 0.0    # agility + random roll

    # Status effects
    status_effects: list[StatusEffect] = field(default_factory=list)

    # Reinforcement state
    reinforce_call_pending: bool  = False
    reinforce_call_at:      float = 0.0
    reinforce_delay:        float = 0.0

    # Flee state
    fled:           bool   = False

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0 and not self.fled

    @property
    def is_stunned_now(self) -> bool:
        return any(e.is_stun and not e.is_expired for e in self.status_effects)

    def roll_initiative(self) -> float:
        roll = self.agility * random.uniform(
            1.0 - AGILITY_ROLL_RANGE,
            1.0 + AGILITY_ROLL_RANGE,
        )
        self.turn_initiative = roll
        return roll

    def add_status(self, effect: StatusEffect) -> None:
        """Add a status effect. Stacks as separate timer."""
        self.status_effects.append(effect)

    def tick_status_effects(self) -> tuple[float, list[str]]:
        """
        Tick all status effects. Returns (total_damage, notifications).
        Removes expired effects.
        """
        total_dmg     = 0.0
        notifications = []
        active        = []

        for effect in self.status_effects:
            if effect.is_expired:
                notifications.append(f"  {self.name}: {effect.name} wore off.")
                continue
            dmg = effect.tick()
            if dmg > 0:
                self.current_hp = max(0.0, self.current_hp - dmg)
                total_dmg      += dmg
                notifications.append(
                    f"  {self.name}: {effect.name} deals {dmg:.1f} damage "
                    f"({effect.remaining:.0f}s remaining)"
                )
            active.append(effect)

        self.status_effects = active
        return total_dmg, notifications

    def get_status_display(self) -> str:
        """Returns inline status effect string for combat display."""
        active = [e for e in self.status_effects if not e.is_expired]
        if not active:
            return ""
        return " " + " ".join(e.display() for e in active)

    def effective_defense(self) -> float:
        base = self.defense
        if self.is_defending:
            base *= (1.0 + DEFEND_REDUCTION)
        # Apply status debuffs to defense
        for effect in self.status_effects:
            mult = effect.stat_modifier.get("defense", 1.0)
            base *= mult
        return base

    def effective_attack(self) -> float:
        base = self.attack_power
        for effect in self.status_effects:
            mult = effect.stat_modifier.get("attack_power", 1.0)
            base *= mult
        return base

    def effective_agility(self) -> float:
        base = self.agility
        for effect in self.status_effects:
            mult = effect.stat_modifier.get("agility", 1.0)
            base *= mult
        return base

    def hp_bar(self, show_status: bool = True) -> str:
        """Format: Name HP/MaxHP [status effects]"""
        status = self.get_status_display() if show_status else ""
        if self.is_alpha:
            # Alpha only visible if identified
            name_display = self.name
        else:
            name_display = self.name
        return f"{name_display} {self.current_hp:.0f}/{self.max_hp:.0f}{status}"

    @property
    def intelligence_score(self) -> float:
        """Monster intelligence — drives AI behavior quality."""
        base = MONSTER_INTELLIGENCE.get(self.monster_type.lower(), 3)
        mult = GRADE_INTELLIGENCE_MULT.get(self.grade_index, 1.0)
        return base * mult


# ─────────────────────────────────────────────────────────────────────────────
#  MULTICAST / MULTITASK STATE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MulticastState:
    """Tracks the two simultaneous spell slots."""
    mental_spell:   Optional[str] = None   # spell name
    verbal_spell:   Optional[str] = None   # spell name
    rarity_index:   int           = 0      # multicast skill rarity

    @property
    def efficiency(self) -> float:
        return MULTICAST_EFFICIENCY.get(self.rarity_index, 0.60)

    @property
    def is_full(self) -> bool:
        return self.mental_spell is not None and self.verbal_spell is not None

    def add_spell(self, spell_name: str, slot: str) -> bool:
        """slot: 'mental' or 'verbal'"""
        if slot == "mental" and self.mental_spell is None:
            self.mental_spell = spell_name
            return True
        if slot == "verbal" and self.verbal_spell is None:
            self.verbal_spell = spell_name
            return True
        return False

    def clear(self) -> None:
        self.mental_spell = None
        self.verbal_spell = None


@dataclass
class MultitaskState:
    """Tracks simultaneous non-spell actions."""
    actions:        list[str] = field(default_factory=list)
    rarity_index:   int       = 0

    @property
    def max_actions(self) -> int:
        return MULTITASK_ACTIONS.get(self.rarity_index, 2)

    @property
    def can_add(self) -> bool:
        return len(self.actions) < self.max_actions

    def add(self, action: str) -> bool:
        if self.can_add:
            self.actions.append(action)
            return True
        return False

    def clear(self) -> None:
        self.actions.clear()


# ─────────────────────────────────────────────────────────────────────────────
#  COMBAT TURN
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CombatTurn:
    """
    One entity's turn declaration.
    Player can declare multiple actions (multitask) + up to 2 spells (multicast).
    All execute simultaneously.
    """
    combatant:      Combatant
    actions:        list[str]          = field(default_factory=list)
    # action format: "attack:<target>" | "skill:<name>:<target>" |
    #                "item:<name>" | "defend" | "taunt" | "flee"
    multicast:      Optional[MulticastState] = None
    multitask:      Optional[MultitaskState] = None
    declared_at:    float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  COMBAT SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class CombatSystem:
    """
    Manages a single combat encounter.
    One instance per fight. Discarded after combat ends.

    Usage:
        combat = CombatSystem(player_combatant, enemy_combatants, world_sim)
        result = combat.run()   # returns CombatResult
    """

    def __init__(
        self,
        player:         Combatant,
        enemies:        list[Combatant],
        world_sim=None,
        region:         str = "elya",
    ):
        self.player         = player
        self.enemies:       list[Combatant] = list(enemies)
        self.world_sim      = world_sim
        self.region         = region

        # All combatants in initiative order
        self.all_combatants: list[Combatant] = []

        # Turn tracking
        self.turn_number:   int   = 0
        self.combat_log:    list[str] = []

        # Inactivity tracking
        self.last_input_at: float = time.time()
        self.warned_inactivity: bool = False

        # Pending reinforcements
        self.pending_reinforcements: list[dict] = []

        # Weather modifier (rechecked each turn)
        self._weather_mod:  float = 1.0

        # Combat state
        self.is_over:       bool  = False
        self.result:        Optional[str] = None   # "victory" | "defeat" | "fled"

        # Multicast/multitask state for player
        self.player_multicast = None
        self.player_multitask = None
        self._init_player_combat_skills()


    # ─────────────────────────────────────────────────────────────────────
    #  INITIALIZATION
    # ─────────────────────────────────────────────────────────────────────

    def _init_player_combat_skills(self) -> None:
        """Check if player has multicast/multitask skills and initialize state."""
        entity = self.player.entity
        if not hasattr(entity, "magic_system"):
            return

        multicast_skill = None
        multitask_skill = None
        for skill in entity.magic_system.skills:
            if "multicast" in skill.name.lower():
                multicast_skill = skill
            if "multitask" in skill.name.lower():
                multitask_skill = skill

        if multicast_skill:
            rarity_idx = RARITY_TIERS.index(multicast_skill.rarity) \
                         if multicast_skill.rarity in RARITY_TIERS else 0
            self.player_multicast = MulticastState(rarity_index=rarity_idx)

        if multitask_skill:
            rarity_idx = RARITY_TIERS.index(multitask_skill.rarity) \
                         if multitask_skill.rarity in RARITY_TIERS else 0
            self.player_multitask = MultitaskState(rarity_index=rarity_idx)

    def _get_weather_mod(self) -> float:
        """Pull current weather modifier from WorldSimulation."""
        if not self.world_sim:
            return 1.0
        weather = self.world_sim.get_weather(self.region)
        return weather.combat_modifiers.get("atk_mod", 0.0) + 1.0

    def _roll_initiative(self) -> None:
        """Roll initiative for all combatants. Sort by roll descending."""
        all_c = [self.player] + self.enemies
        for c in all_c:
            c.roll_initiative()
        self.all_combatants = sorted(
            all_c, key=lambda c: c.turn_initiative, reverse=True
        )

    def _reroll_initiative(self) -> None:
        """
        Reroll initiative mid-combat (after speed buff/debuff).
        Preserves current HP and status effects.
        """
        self._roll_initiative()
        self.combat_log.append("  [Turn order updated!]")


    # ─────────────────────────────────────────────────────────────────────
    #  COMBAT DISPLAY
    # ─────────────────────────────────────────────────────────────────────

    def display_state(self) -> str:
        """
        Full combat display for this turn.
        Shows: turn order, enemy health bars, player health/mana, status effects.
        """
        lines = []

        # Turn order
        order_str = " → ".join(
            c.name for c in self.all_combatants if c.is_alive
        )
        lines.append(f"Turn {self.turn_number} | Order: {order_str}")
        lines.append("")

        # Enemies
        lines.append("Enemies:")
        for enemy in self.enemies:
            if enemy.is_alive:
                lines.append(f"  {enemy.hp_bar(show_status=False)}")
        lines.append("")

        # Player
        p = self.player
        lines.append(
            f"You: {p.current_hp:.0f}/{p.max_hp:.0f} HP  "
            f"{p.current_mana:.0f}/{p.max_mana:.0f} Mana"
        )

        # Player status effects (listed separately)
        player_statuses = [e for e in p.status_effects if not e.is_expired]
        if player_statuses:
            lines.append("  Status effects:")
            for effect in player_statuses:
                lines.append(f"    {effect.display()}")

        lines.append("")

        # Available actions
        lines.append("Actions: attack | skill <name> | item <name> | "
                     "defend | taunt | flee")
        if self.player_multicast:
            lines.append(
                f"  Multicast available "
                f"(efficiency: {self.player_multicast.efficiency*100:.0f}%): "
                f"cast mental <spell> | cast verbal <spell>"
            )
        if self.player_multitask:
            lines.append(
                f"  Multitask available "
                f"({len(self.player_multitask.actions)}/{self.player_multitask.max_actions} "
                f"actions queued): add <action>"
            )

        # Weather
        if self._weather_mod != 1.0:
            mod_pct = (self._weather_mod - 1.0) * 100
            sign    = "+" if mod_pct > 0 else ""
            lines.append(f"  Weather: {sign}{mod_pct:.0f}% attack modifier")

        return "\n".join(lines)

    def display_turn_result(self, results: list[str]) -> str:
        return "\n".join(results)


    # ─────────────────────────────────────────────────────────────────────
    #  MAIN COMBAT LOOP
    # ─────────────────────────────────────────────────────────────────────

    def run(self, input_fn=None) -> "CombatResult":
        """
        Main combat loop.
        input_fn: callable that takes a prompt string and returns player input.
        If None, uses input() directly.
        """
        if input_fn is None:
            input_fn = input

        self._roll_initiative()
        self._weather_mod = self._get_weather_mod()

        print(f"\n{'='*50}")
        print(f"COMBAT BEGINS!")
        print(f"{'='*50}")

        while not self.is_over:
            self.turn_number += 1
            self._weather_mod = self._get_weather_mod()

            # Tick status effects for all combatants
            self._tick_all_statuses()

            # Check for deaths after status ticks
            self._check_deaths()
            if self.is_over:
                break

            # Process pending reinforcements
            self._process_reinforcements()

            # Display state
            print("\n" + self.display_state())

            # Process turn for each combatant in initiative order
            for combatant in list(self.all_combatants):
                if not combatant.is_alive:
                    continue
                if self.is_over:
                    break

                if combatant.is_player:
                    results = self._player_turn(combatant, input_fn)
                else:
                    results = self._monster_turn(combatant)

                if results:
                    print(self.display_turn_result(results))
                    self.combat_log.extend(results)

                # Reroll initiative if agility changed
                self._check_initiative_update()

                # Check deaths after each action
                self._check_deaths()

            # Reset defending state
            self.player.is_defending = False

        return CombatResult(
            result          = self.result,
            turns           = self.turn_number,
            log             = self.combat_log,
            enemies_defeated= [e for e in self.enemies if not e.is_alive],
            player_fled     = self.result == "fled",
        )


    # ─────────────────────────────────────────────────────────────────────
    #  PLAYER TURN
    # ─────────────────────────────────────────────────────────────────────

    def _player_turn(
        self,
        combatant: Combatant,
        input_fn,
    ) -> list[str]:
        """Handle player's turn. Supports multitask/multicast."""
        if combatant.is_stunned_now:
            return [f"  {combatant.name} is stunned and cannot act!"]

        # Reset multicast/multitask queues
        if self.player_multicast:
            self.player_multicast.clear()
        if self.player_multitask:
            self.player_multitask.clear()

        # Collect actions
        actions = self._collect_player_actions(combatant, input_fn)
        if not actions:
            return []

        # Execute all actions simultaneously
        results = []
        for action in actions:
            result = self._execute_player_action(combatant, action)
            results.extend(result)

        # Execute multicast spells simultaneously
        if self.player_multicast:
            results.extend(
                self._execute_multicast(combatant)
            )

        self.last_input_at  = time.time()
        self.warned_inactivity = False
        return results

    def _collect_player_actions(
        self,
        combatant: Combatant,
        input_fn,
    ) -> list[str]:
        """
        Collect player action input with inactivity detection.
        Returns list of action strings.
        """
        actions = []

        while True:
            # Check inactivity
            elapsed = time.time() - self.last_input_at
            if elapsed >= INACTIVITY_LIMIT:
                print("\n[INACTIVITY] No input for 10 minutes. Fleeing automatically.")
                self._execute_flee(combatant)
                return []
            if elapsed >= INACTIVITY_WARNING and not self.warned_inactivity:
                print("\n[WARNING] You have 1 minute to act or you will flee automatically.")
                self.warned_inactivity = True

            # Determine how many actions expected
            max_actions = 1
            if self.player_multitask:
                max_actions = self.player_multitask.max_actions

            prompt = f"\nYour action ({len(actions)+1}"
            if max_actions > 1:
                prompt += f"/{max_actions}, or 'done' to execute"
            prompt += "): "

            try:
                raw = input_fn(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return actions or ["flee"]

            if not raw:
                continue

            # Status check intercept
            if raw in ("status", "save"):
                if hasattr(combatant.entity, "intercept_status"):
                    combatant.entity.intercept_status(raw)
                continue

            if raw == "done" and actions:
                break

            # Parse multicast
            if raw.startswith("cast mental ") or raw.startswith("cast verbal "):
                if self.player_multicast:
                    parts = raw.split(" ", 2)
                    slot  = parts[1]
                    spell = parts[2] if len(parts) > 2 else ""
                    if self.player_multicast.add_spell(spell, slot):
                        print(f"  {slot.capitalize()} spell queued: {spell}")
                    else:
                        print(f"  {slot.capitalize()} slot already filled.")
                else:
                    print("  You don't have the Multicast skill.")
                continue

            # Add action
            actions.append(raw)
            self.last_input_at = time.time()

            # If only 1 action allowed, execute immediately
            if max_actions == 1:
                break

            # If multitask max reached
            if len(actions) >= max_actions:
                print(f"  Maximum actions reached ({max_actions}). Executing.")
                break

        return actions

    def _execute_player_action(
        self,
        combatant: Combatant,
        action:    str,
    ) -> list[str]:
        """Execute a single player action. Returns result strings."""
        parts = action.split()
        verb  = parts[0] if parts else ""

        if verb == "attack":
            target = self._get_target(parts[1] if len(parts) > 1 else "")
            if not target:
                return ["  No valid target."]
            return self._execute_attack(combatant, target)

        elif verb == "skill":
            skill_name = " ".join(parts[1:-1]) if len(parts) > 2 else " ".join(parts[1:])
            target_name= parts[-1] if len(parts) > 2 else ""
            target     = self._get_target(target_name)
            return self._execute_skill(combatant, skill_name, target)

        elif verb == "item":
            item_name = " ".join(parts[1:])
            return self._execute_item(combatant, item_name)

        elif verb == "defend":
            combatant.is_defending = True
            return [f"  {combatant.name} takes a defensive stance. "
                    f"(Damage reduced by {DEFEND_REDUCTION*100:.0f}%)"]

        elif verb == "taunt":
            return self._execute_taunt(combatant)

        elif verb == "flee":
            return self._execute_flee(combatant)

        return [f"  Unknown action: {action}"]

    def _execute_attack(
        self,
        attacker: Combatant,
        target:   Combatant,
    ) -> list[str]:
        """Basic attack using AtkPwr/Defense compatibility layer."""
        raw_dmg  = max(1.0, attacker.effective_attack() * self._weather_mod)
        defense  = target.effective_defense()
        damage   = max(1.0, raw_dmg - defense)

        # Crit roll (Dexterity-based if available)
        dex = getattr(
            getattr(attacker.entity, "stats", None), "dexterity", 10.0
        )
        crit_chance = dex * 0.003
        is_crit     = random.random() < crit_chance
        if is_crit:
            damage *= 1.5

        # Dodge roll
        target_agi   = target.effective_agility()
        attacker_agi = attacker.effective_agility()
        dodge_chance = max(0.0, target_agi * 0.002 - attacker_agi * 0.001)
        if random.random() < dodge_chance:
            return [f"  {target.name} dodged {attacker.name}'s attack!"]

        target.current_hp = max(0.0, target.current_hp - damage)
        crit_str = " [CRITICAL!]" if is_crit else ""
        return [
            f"  {attacker.name} attacks {target.name} "
            f"for {damage:.1f} damage{crit_str}. "
            f"({target.current_hp:.0f}/{target.max_hp:.0f} HP)"
        ]

    def _execute_skill(
        self,
        user:       Combatant,
        skill_name: str,
        target:     Optional[Combatant],
    ) -> list[str]:
        """Execute a skill. Routes through MagicSystem if available."""
        entity = user.entity
        if not hasattr(entity, "magic_system"):
            return [f"  {user.name} has no skill system."]

        ms      = entity.magic_system
        skill   = ms.get_skill(skill_name)
        if not skill:
            return [f"  Unknown skill: {skill_name}"]

        # Check outlawed
        if ms._is_outlawed(skill, self.region):
            # still allowed but flagged
            pass

        notes, success = ms.use_skill(
            skill_name  = skill_name,
            player      = entity,
            target      = target.entity if target else None,
            region      = self.region,
            weather_mod = self._weather_mod,
        )

        if not success:
            return notes

        # Apply damage to target
        if target and skill.effects:
            damage = skill.get_damage(entity.stats, self._weather_mod)
            if skill.effects[0].area:
                # Area — hit all enemies
                results = list(notes)
                for enemy in self.enemies:
                    if enemy.is_alive:
                        enemy.current_hp = max(0.0, enemy.current_hp - damage)
                        results.append(
                            f"  {enemy.name} takes {damage:.1f} damage. "
                            f"({enemy.current_hp:.0f}/{enemy.max_hp:.0f} HP)"
                        )
                return results
            else:
                target.current_hp = max(0.0, target.current_hp - damage)
                notes.append(
                    f"  {target.name} takes {damage:.1f} damage. "
                    f"({target.current_hp:.0f}/{target.max_hp:.0f} HP)"
                )

        # Apply status effects from skill
        for effect_data in skill.effects:
            if effect_data.effect_type in ("bleed", "burn", "poison", "stun",
                                            "slow", "freeze", "concussion",
                                            "internal_bleed", "psychic_shock"):
                if target:
                    status = StatusEffect(
                        effect_id    = f"status_{int(time.time())}_{random.randint(100,999)}",
                        name         = effect_data.effect_type.replace("_", " ").title(),
                        effect_type  = effect_data.effect_type,
                        source       = user.name,
                        duration     = effect_data.duration or 10.0,
                        total_damage = effect_data.base_value,
                        is_stun      = effect_data.effect_type == "stun",
                    )
                    target.add_status(status)
                    notes.append(
                        f"  {target.name} is afflicted with "
                        f"{status.name}! ({status.duration:.0f}s)"
                    )

        # Reroll initiative if agility modified
        if any(sb.stat == "agility" for sb in skill.stat_bonuses):
            self._reroll_initiative()

        return notes

    def _execute_multicast(self, combatant: Combatant) -> list[str]:
        """Execute both queued multicast spells simultaneously."""
        if not self.player_multicast:
            return []
        results = []
        efficiency = self.player_multicast.efficiency

        for slot in ("mental", "verbal"):
            spell_name = getattr(self.player_multicast, f"{slot}_spell")
            if not spell_name:
                continue
            target = self._get_best_target()
            if not target:
                continue
            entity = combatant.entity
            if not hasattr(entity, "magic_system"):
                continue
            skill = entity.magic_system.get_skill(spell_name)
            if not skill:
                results.append(f"  [{slot}] Unknown spell: {spell_name}")
                continue

            # Apply efficiency penalty to mana cost and damage
            original_mana   = skill.mana_cost
            skill.mana_cost = skill.mana_cost / efficiency  # costs more
            notes, success  = entity.magic_system.use_skill(
                spell_name, entity, target.entity, self.region, self._weather_mod
            )
            skill.mana_cost = original_mana  # restore

            if success and skill.effects:
                damage = skill.get_damage(entity.stats, self._weather_mod) * efficiency
                target.current_hp = max(0.0, target.current_hp - damage)
                results.append(
                    f"  [MULTICAST/{slot}] {spell_name}: "
                    f"{damage:.1f} damage on {target.name} "
                    f"({efficiency*100:.0f}% efficiency)"
                )
            else:
                results.extend(notes)

        return results

    def _execute_item(
        self,
        combatant: Combatant,
        item_name: str,
    ) -> list[str]:
        """Use an item from inventory."""
        entity = combatant.entity
        if not hasattr(entity, "use_item"):
            return [f"  Cannot use items."]
        result = entity.use_item(item_name)
        return [f"  {result}"] if isinstance(result, str) else result or []

    def _execute_taunt(self, combatant: Combatant) -> list[str]:
        """Check for taunt skill and apply."""
        entity = combatant.entity
        has_taunt_skill = False
        if hasattr(entity, "magic_system"):
            for skill in entity.magic_system.skills:
                if "taunt" in skill.name.lower():
                    has_taunt_skill = True
                    break
        if not has_taunt_skill:
            return ["  You don't have a Taunt skill."]
        combatant.has_taunt = True
        for enemy in self.enemies:
            if enemy.is_alive:
                enemy._forced_target = combatant
        return [f"  {combatant.name} taunts all enemies! They must target you."]

    def _execute_flee(self, combatant: Combatant) -> list[str]:
        """
        Attempt to flee. Agility-based.
        Grade gap reduces chance significantly.
        Some fights inescapable (boss/story quest flag on enemy).
        """
        # Check inescapable
        for enemy in self.enemies:
            if getattr(enemy.entity, "is_inescapable", False):
                return ["  You cannot flee from this fight!"]

        # Find highest grade enemy
        max_enemy_grade = max(
            (e.grade_index for e in self.enemies if e.is_alive),
            default=0,
        )
        grade_gap = max(0, max_enemy_grade - combatant.grade_index)
        chance    = max(0.05, FLEE_BASE_CHANCE - grade_gap * FLEE_GRADE_PENALTY)

        # Agility bonus
        player_agi = combatant.effective_agility()
        avg_enemy_agi = sum(
            e.effective_agility() for e in self.enemies if e.is_alive
        ) / max(1, sum(1 for e in self.enemies if e.is_alive))
        agi_mod = min(0.20, max(-0.20, (player_agi - avg_enemy_agi) / 100.0))
        chance  = min(0.95, chance + agi_mod)

        if random.random() < chance:
            combatant.fled = True
            self.result    = "fled"
            self.is_over   = True
            return [
                f"  {combatant.name} successfully fled!",
                f"  (Success chance was {chance*100:.0f}%)"
            ]

        return [
            f"  {combatant.name} failed to flee! "
            f"(Success chance was {chance*100:.0f}%)"
        ]


    # ─────────────────────────────────────────────────────────────────────
    #  MONSTER TURN
    # ─────────────────────────────────────────────────────────────────────

    def _monster_turn(self, combatant: Combatant) -> list[str]:
        """
        Monster AI turn. Intelligence determines behavior quality.
        Higher intelligence = smarter targeting, skill use, fleeing.
        """
        if combatant.is_stunned_now:
            return [f"  {combatant.name} is stunned!"]

        intel = combatant.intelligence_score
        results = []

        # Check reinforcement call (alpha only)
        if combatant.is_alpha and not combatant.reinforce_call_pending:
            call_results = self._check_alpha_reinforcement_call(combatant, intel)
            results.extend(call_results)

        # Determine target
        target = self._monster_choose_target(combatant, intel)
        if not target or not target.is_alive:
            return results

        # Choose action based on intelligence
        action = self._monster_choose_action(combatant, target, intel)

        if action == "skill":
            skill_results = self._monster_use_skill(combatant, target, intel)
            results.extend(skill_results)
        elif action == "flee":
            results.extend(self._execute_flee(combatant))
        else:
            results.extend(self._execute_attack(combatant, target))

        # Reset defending
        combatant.is_defending = False
        return results

    def _monster_choose_target(
        self,
        monster: Combatant,
        intel:   float,
    ) -> Optional[Combatant]:
        """
        Choose a target. Enemies can focus one player target.
        If player has taunt active, must target taunting combatant.
        Intelligence affects targeting strategy.
        """
        # Check forced target (taunt)
        forced = getattr(monster, "_forced_target", None)
        if forced and forced.is_alive:
            return forced

        # Only player in single-player, but structured for multi-target future
        if self.player.is_alive:
            return self.player
        return None

    def _monster_choose_action(
        self,
        monster: Combatant,
        target:  Combatant,
        intel:   float,
    ) -> str:
        """
        Choose action based on intelligence score.
        Low intel = random. High intel = strategic.
        """
        entity = monster.entity
        has_skills = (
            hasattr(entity, "magic_system") and
            len(entity.magic_system.skills) > 0
        )

        # Low intelligence — mostly random
        if intel < 3:
            if has_skills and random.random() < 0.2:
                return "skill"
            return "attack"

        # Medium intelligence — considers HP
        if intel < 6:
            hp_pct = monster.current_hp / monster.max_hp
            if hp_pct < 0.2 and random.random() < 0.3:
                return "flee"
            if has_skills and random.random() < 0.4:
                return "skill"
            return "attack"

        # High intelligence — strategic
        hp_pct = monster.current_hp / monster.max_hp
        target_hp_pct = target.current_hp / target.max_hp

        # Flee if badly hurt and can
        if hp_pct < 0.15 and random.random() < 0.5:
            return "flee"

        # Use skills when available and beneficial
        if has_skills:
            # Use debuff skills when target is healthy
            if target_hp_pct > 0.7 and random.random() < 0.5:
                return "skill"
            # Use damage skills when target is low
            if target_hp_pct < 0.3 and random.random() < 0.7:
                return "skill"

        return "attack"

    def _monster_use_skill(
        self,
        monster: Combatant,
        target:  Combatant,
        intel:   float,
    ) -> list[str]:
        """Monster uses a skill. Intelligence affects skill selection."""
        entity = monster.entity
        if not hasattr(entity, "magic_system"):
            return self._execute_attack(monster, target)

        skills = [s for s in entity.magic_system.skills
                  if s.skill_category == "active" and s.can_use]
        if not skills:
            return self._execute_attack(monster, target)

        # Low intel: random skill
        # High intel: pick best skill for situation
        if intel < 5:
            skill = random.choice(skills)
        else:
            # Prefer debuffs when target is healthy, damage when low
            target_hp_pct = target.current_hp / target.max_hp
            debuff_skills = [s for s in skills
                            if any(e.effect_type in ("slow","stun","poison","bleed")
                                   for e in s.effects)]
            damage_skills = [s for s in skills
                            if any(e.effect_type == "damage" for e in s.effects)]
            if target_hp_pct > 0.6 and debuff_skills:
                skill = random.choice(debuff_skills)
            elif damage_skills:
                skill = random.choice(damage_skills)
            else:
                skill = random.choice(skills)

        return self._execute_skill(monster, skill.name, target)

    def _check_alpha_reinforcement_call(
        self,
        alpha: Combatant,
        intel: float,
    ) -> list[str]:
        """
        Alpha monsters can call reinforcements as a skill.
        Only calls if intelligent enough to do so strategically.
        Delay based on alpha's intelligence and responders' proximity.
        """
        # Must have reinforcement skill
        entity = alpha.entity
        has_call_skill = False
        if hasattr(entity, "magic_system"):
            for skill in entity.magic_system.skills:
                if "call" in skill.name.lower() or "reinforce" in skill.name.lower():
                    has_call_skill = True
                    break
        if not has_call_skill:
            return []

        # Intelligence gates strategic use
        hp_pct = alpha.current_hp / alpha.max_hp
        should_call = False

        if intel >= 8:
            # Very smart: call early when advantageous
            should_call = hp_pct < 0.6 or len([e for e in self.enemies if e.is_alive]) < 2
        elif intel >= 5:
            # Medium: call when hurt
            should_call = hp_pct < 0.4
        else:
            # Low: call when desperate
            should_call = hp_pct < 0.2

        if not should_call:
            return []

        # Schedule reinforcements
        delay = random.uniform(REINFORCE_DELAY_MIN, REINFORCE_DELAY_MAX)
        # Smarter alpha = faster call
        delay *= max(0.3, 1.0 - (intel / 20.0))

        alpha.reinforce_call_pending = True
        alpha.reinforce_call_at      = time.time()
        alpha.reinforce_delay        = delay

        self.pending_reinforcements.append({
            "caller":    alpha.name,
            "arrives_at":time.time() + delay,
            "count":     random.randint(1, 3),
        })

        return [
            f"  {alpha.name} lets out a commanding call!",
            f"  Reinforcements may be on their way... ({delay:.0f}s)",
        ]

    def _process_reinforcements(self) -> None:
        """Check if any pending reinforcements have arrived."""
        now     = time.time()
        arrived = []
        pending = []

        for reinf in self.pending_reinforcements:
            if now >= reinf["arrives_at"]:
                arrived.append(reinf)
            else:
                pending.append(reinf)

        self.pending_reinforcements = pending

        for reinf in arrived:
            count = reinf["count"]
            print(f"\n  [REINFORCEMENTS] {count} allies of {reinf['caller']} arrive!")
            # In full implementation: generate new Combatant objects from
            # nearby monster population. For now, notify only.
            # Full monster spawning wired in when region system (#5) is built.


    # ─────────────────────────────────────────────────────────────────────
    #  STATUS TICKING
    # ─────────────────────────────────────────────────────────────────────

    def _tick_all_statuses(self) -> None:
        """Tick status effects for all combatants."""
        for combatant in self.all_combatants:
            if not combatant.is_alive:
                continue
            dmg, notes = combatant.tick_status_effects()
            if notes:
                for note in notes:
                    print(note)


    # ─────────────────────────────────────────────────────────────────────
    #  UTILITY
    # ─────────────────────────────────────────────────────────────────────

    def _check_deaths(self) -> None:
        """Check for dead combatants. Handle player death and victory."""
        # Check player death
        if not self.player.is_alive and not self.player.fled:
            self.result  = "defeat"
            self.is_over = True
            print(f"\n  {self.player.name} has fallen!")

            # Drop items (2 random items)
            entity = self.player.entity
            if hasattr(entity, "on_death"):
                death_notes = entity.on_death()
                for note in death_notes:
                    print(note)

            # Intelligent enemies loot immediately
            for enemy in self.enemies:
                if enemy.is_alive and enemy.intelligence_score >= 6:
                    print(f"  {enemy.name} searches the body...")
                    # Full looting wired in when inventory system (#11) is built
            return

        # Check if all enemies defeated
        if all(not e.is_alive for e in self.enemies):
            self.result  = "victory"
            self.is_over = True
            print(f"\n  Victory! All enemies defeated!")

    def _check_initiative_update(self) -> None:
        """Reroll initiative if any combatant's agility changed this turn."""
        for combatant in self.all_combatants:
            entity = combatant.entity
            if hasattr(entity, "stats"):
                current_agi = getattr(entity.stats, "agility", combatant.agility)
                if abs(current_agi - combatant.agility) > 0.5:
                    combatant.agility = current_agi
                    self._reroll_initiative()
                    break

    def _get_target(self, name: str) -> Optional[Combatant]:
        """Find a target by name fragment."""
        if not name:
            return self._get_best_target()
        for enemy in self.enemies:
            if enemy.is_alive and name.lower() in enemy.name.lower():
                return enemy
        return self._get_best_target()

    def _get_best_target(self) -> Optional[Combatant]:
        """Default target: lowest HP living enemy."""
        alive = [e for e in self.enemies if e.is_alive]
        if not alive:
            return None
        return min(alive, key=lambda e: e.current_hp)


# ─────────────────────────────────────────────────────────────────────────────
#  COMBAT RESULT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CombatResult:
    result:           str              # "victory" | "defeat" | "fled"
    turns:            int
    log:              list[str]
    enemies_defeated: list[Combatant]
    player_fled:      bool = False

    @property
    def won(self) -> bool:
        return self.result == "victory"

    @property
    def lost(self) -> bool:
        return self.result == "defeat"


# ─────────────────────────────────────────────────────────────────────────────
#  COMBATANT FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def make_combatant_from_player(player) -> Combatant:
    """Build a Combatant from a Player instance."""
    stats = getattr(player, "stats", None)
    return Combatant(
        name         = getattr(player, "name", "Player"),
        entity       = player,
        is_player    = True,
        grade_index  = getattr(player.race_track, "grade_index", 0)
                       if hasattr(player, "race_track") else 0,
        max_hp       = getattr(player, "max_health", 100.0),
        current_hp   = getattr(player, "health", 100.0),
        max_mana     = getattr(player, "max_mana", 50.0),
        current_mana = getattr(player, "mana", 50.0),
        agility      = getattr(stats, "agility", 10.0) if stats else 10.0,
        attack_power = getattr(player, "AtkPwr", 5.0),   # AtkPwr compat layer
        defense      = getattr(player, "Defense", 2.0),  # Defense compat layer
    )


def make_combatant_from_npc(npc, is_alpha: bool = False) -> Combatant:
    """Build a Combatant from an NPC/Monster instance."""
    stats = getattr(npc, "stats", None)

    # Determine monster type from race
    race         = getattr(npc, "race", "beast").lower()
    monster_type = "beast"
    for mtype in MONSTER_INTELLIGENCE.keys():
        if mtype in race:
            monster_type = mtype
            break

    return Combatant(
        name         = getattr(npc, "name", "Monster"),
        entity       = npc,
        is_player    = False,
        is_alpha     = is_alpha,
        monster_type = monster_type,
        grade_index  = getattr(npc.race_track, "grade_index", 0)
                       if hasattr(npc, "race_track") else 0,
        max_hp       = getattr(npc, "max_health", 20.0),
        current_hp   = getattr(npc, "health", 20.0),
        max_mana     = getattr(npc, "max_mana", 20.0),
        current_mana = getattr(npc, "mana", 20.0),
        agility      = getattr(stats, "agility", 8.0) if stats else 8.0,
        attack_power = getattr(npc, "AtkPwr",
                       getattr(stats, "strength", 5.0) * 1.1 if stats else 5.0),
        defense      = getattr(npc, "Defense",
                       getattr(stats, "constitution", 3.0) * 0.6 if stats else 2.0),
    )