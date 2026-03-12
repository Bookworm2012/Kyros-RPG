"""
kyros/world_simulation.py

WorldSimulation — the master clock and world state manager for Kyros.

Owns:
- Master NPC time clock (1 real second = 1 NPC minute)
- All timers (quest, jail, buff, caravan, event, weather, shop queue)
- NPC simulation ticks (goals, schedules, gossip propagation)
- Weather (real Brevard NC forecast via OpenWeatherMap)
- Economy (supply/demand, shop stock, caravan trade routes)
- Caravans (travel, attacks, loot drops)
- News system (notice board + NPC dialogue delivery)
- Guild bankruptcy / regional economic crisis
- Player absence tracking → NPC gossip
- Multiplayer server tick (TCP socket, separate process)
- Shop transaction queue (per-shop, sequential)

WorldSimulation runs as a separate process via run_server().
Player game loops connect to it via TCP socket on port 7890.
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
import socket
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

REAL_TO_NPC_RATIO        = 60          # 1 real second = 60 NPC seconds (1 NPC minute)
NPC_SECONDS_PER_REAL_SEC = 60
NPC_MINUTE               = 1           # 1 real second
NPC_HOUR                 = 60          # real seconds
NPC_DAY                  = 1440        # real seconds  (24 * 60)
NPC_SEASON               = 864_000     # real seconds  (10 real days)
MAX_CATCHUP_NPC_HOURS    = 10 * NPC_HOUR   # 10 NPC hours = 600 real seconds

WEATHER_FETCH_INTERVAL   = NPC_DAY     # fetch new forecast once per NPC day
CARAVAN_TICK_INTERVAL    = NPC_HOUR    # caravans advance every NPC hour
ECONOMY_TICK_INTERVAL    = NPC_HOUR    # economy updates every NPC hour
NPC_TICK_INTERVAL        = 30          # NPC goals/schedule tick every 30 real seconds
NEWS_EXPIRY              = NPC_DAY * 7 # news items expire after 7 NPC days
NOTICE_BOARD_EXPIRY      = 60 * 60 * 24 * 14  # 2 real weeks

SERVER_HOST              = "0.0.0.0"
SERVER_PORT              = 7890
MAX_CLIENTS              = 32

BANDIT_ATTACK_CHANCE     = 0.08        # 8% per caravan tick
MONSTER_ATTACK_CHANCE    = 0.05        # 5% per caravan tick
CARAVAN_BASE_TRAVEL_TIME = NPC_HOUR * 6  # 6 NPC hours base travel time

# Weather mapping: OpenWeatherMap condition → Kyros weather type
WEATHER_MAP = {
    "thunderstorm": "storm",
    "drizzle":      "rain",
    "rain":         "rain",
    "snow":         "blizzard",
    "mist":         "fog",
    "smoke":        "fog",
    "haze":         "fog",
    "dust":         "dust_storm",
    "fog":          "fog",
    "sand":         "dust_storm",
    "ash":          "ash_fall",
    "squall":       "storm",
    "tornado":      "tornado",
    "clear":        "clear",
    "clouds":       "cloudy",
}

# Weather mood modifiers for NPC emotion ticks
WEATHER_MOOD = {
    "clear":       ("joy",       10),
    "cloudy":      ("anxiety",    5),
    "rain":        ("grief",      8),
    "storm":       ("fear",      20),
    "blizzard":    ("fear",      30),
    "fog":         ("anxiety",   12),
    "dust_storm":  ("anxiety",   15),
    "ash_fall":    ("fear",      25),
    "tornado":     ("fear",      50),
    "magical_storm":("fear",     35),
    "arcane_fog":  ("anxiety",   20),
}

# Weather combat modifiers
WEATHER_COMBAT = {
    "clear":        {"visibility": 1.0,  "dodge_mod": 0.0,  "atk_mod": 0.0},
    "cloudy":       {"visibility": 0.9,  "dodge_mod": 0.0,  "atk_mod": 0.0},
    "rain":         {"visibility": 0.7,  "dodge_mod":-0.05, "atk_mod":-0.05},
    "storm":        {"visibility": 0.4,  "dodge_mod":-0.15, "atk_mod":-0.10},
    "blizzard":     {"visibility": 0.2,  "dodge_mod":-0.25, "atk_mod":-0.20},
    "fog":          {"visibility": 0.3,  "dodge_mod": 0.10, "atk_mod":-0.10},
    "dust_storm":   {"visibility": 0.3,  "dodge_mod":-0.10, "atk_mod":-0.05},
    "magical_storm":{"visibility": 0.5,  "dodge_mod":-0.10, "atk_mod": 0.10},
    "arcane_fog":   {"visibility": 0.4,  "dodge_mod": 0.15, "atk_mod":-0.05},
}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _call_claude_json(system: str, messages: list, max_tokens: int = 500) -> dict:
    """Minimal Claude API call returning parsed JSON dict."""
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            data   = json.loads(resp.read().decode())
            blocks = data.get("content", [])
            text   = " ".join(b["text"] for b in blocks if b.get("type") == "text")
            clean  = text.strip().lstrip("```json").rstrip("```").strip()
            return json.loads(clean)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeatherState:
    """Current weather in a region."""
    region:       str
    kyros_type:   str   = "clear"
    raw_condition:str   = "clear"
    temperature:  float = 65.0      # Fahrenheit
    fetched_at:   float = field(default_factory=time.time)
    # Fantasy overrides (magical events, player/NPC triggered)
    fantasy_override: Optional[str] = None
    override_until:   float         = 0.0

    @property
    def active_type(self) -> str:
        if self.fantasy_override and time.time() < self.override_until:
            return self.fantasy_override
        return self.kyros_type

    @property
    def combat_modifiers(self) -> dict:
        return WEATHER_COMBAT.get(self.active_type, WEATHER_COMBAT["clear"])

    @property
    def mood_effect(self) -> tuple[str, int]:
        return WEATHER_MOOD.get(self.active_type, ("anxiety", 0))


@dataclass
class CaravanGoods:
    """A single good carried by a caravan."""
    item_name: str
    quantity:  int
    region_of_origin: str


@dataclass
class GossipPayload:
    """Gossip being transported by a caravan."""
    description: str
    score:       float
    source_npc:  str
    origin:      str


@dataclass
class Caravan:
    """
    A caravan travelling between regions.
    Carries goods and gossip. Can be attacked by monsters or bandits.
    """
    caravan_id:    str
    origin:        str
    destination:   str
    goods:         list[CaravanGoods]   = field(default_factory=list)
    gossip:        list[GossipPayload]  = field(default_factory=list)
    departed_at:   float                = field(default_factory=time.time)
    travel_time:   float                = CARAVAN_BASE_TRAVEL_TIME
    arrived:       bool                 = False
    destroyed:     bool                 = False
    delayed_until: float                = 0.0
    attack_site:   Optional[str]        = None   # location name if attacked
    loot_dropped:  list[CaravanGoods]   = field(default_factory=list)
    bandits_took:  list[CaravanGoods]   = field(default_factory=list)

    @property
    def progress(self) -> float:
        """0.0 – 1.0 travel progress."""
        effective_time = time.time() - self.departed_at
        return min(1.0, effective_time / self.travel_time)

    @property
    def is_delayed(self) -> bool:
        return time.time() < self.delayed_until

    @property
    def eta(self) -> float:
        """Real seconds until arrival."""
        return max(0.0, self.departed_at + self.travel_time - time.time())


@dataclass
class NewsItem:
    """A piece of world news. Delivered via notice board and NPC dialogue."""
    news_id:     str
    headline:    str
    body:        str
    region:      str    # "local" | "regional" | "kingdom" | "empire" | "world"
    source:      str    # what caused this news
    created_at:  float  = field(default_factory=time.time)
    read_by:     list[str] = field(default_factory=list)   # player names who read it

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) >= NEWS_EXPIRY


@dataclass
class NoticeBoardPost:
    """A player-posted notice. Costs gold, expires after 2 real weeks."""
    post_id:    str
    author:     str        # player name or alias
    content:    str
    location:   str
    posted_at:  float = field(default_factory=time.time)
    is_anonymous: bool = False
    cost:       float = 10.0   # gold cost to post

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.posted_at) >= NOTICE_BOARD_EXPIRY


@dataclass
class ShopTransaction:
    """A queued shop transaction."""
    player_name: str
    shop_name:   str
    action:      str   # "buy" | "sell"
    item_name:   str
    quantity:    int
    submitted_at:float = field(default_factory=time.time)


@dataclass
class Timer:
    """A generic simulation timer."""
    timer_id:   str
    category:   str      # "quest" | "jail" | "buff" | "caravan" | "event" | "notice"
    entity_id:  str      # player name, quest id, etc.
    expires_at: float
    payload:    dict = field(default_factory=dict)
    fired:      bool = False

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at and not self.fired


@dataclass
class RegionalEconomy:
    """Supply/demand and price state for a region."""
    region:      str
    shop_stock:  dict[str, int]   = field(default_factory=dict)
    base_prices: dict[str, float] = field(default_factory=dict)
    supply:      dict[str, float] = field(default_factory=dict)   # 0–2.0, 1.0 = normal
    demand:      dict[str, float] = field(default_factory=dict)   # 0–2.0, 1.0 = normal
    crisis:      bool             = False
    crisis_since:float            = 0.0
    closed_shops:list[str]        = field(default_factory=list)

    def effective_price(self, item: str) -> float:
        base   = self.base_prices.get(item, 10.0)
        supply = self.supply.get(item, 1.0)
        demand = self.demand.get(item, 1.0)
        crisis = 1.5 if self.crisis else 1.0
        # Low supply + high demand = high price
        factor = max(0.5, min(3.0, (demand / max(0.1, supply)) * crisis))
        return round(base * factor, 1)

    def record_sale(self, item: str, qty: int) -> None:
        self.shop_stock[item]  = max(0, self.shop_stock.get(item, 0) - qty)
        self.demand[item]      = min(2.0, self.demand.get(item, 1.0) + qty * 0.01)

    def record_restock(self, item: str, qty: int) -> None:
        self.shop_stock[item]  = self.shop_stock.get(item, 0) + qty
        self.supply[item]      = min(2.0, self.supply.get(item, 1.0) + qty * 0.01)

    def apply_crisis(self) -> None:
        self.crisis       = True
        self.crisis_since = time.time()

    def resolve_crisis(self) -> None:
        self.crisis = False


@dataclass
class ConnectedPlayer:
    """A player currently connected to the multiplayer world."""
    name:         str
    location:     str
    connected_at: float = field(default_factory=time.time)
    socket:       object = None    # client socket reference
    last_ping:    float  = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  WORLD SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

class WorldSimulation:
    """
    The master world simulation for Kyros.

    Owns the master clock, all timers, NPC ticks, weather,
    economy, caravans, news, and multiplayer server.

    In multiplayer: runs as a separate process via run_server().
    In single player: instantiated and driven by the game loop.
    """

    def __init__(
        self,
        world_name:    str  = "Kyros",
        is_multiplayer:bool = False,
    ):
        self.world_name    = world_name
        self.is_multiplayer= is_multiplayer

        # ── Master clock ─────────────────────────────────────────────────
        self.start_time:     float = time.time()
        self.last_tick_time: float = time.time()
        self.npc_time:       float = 0.0     # total NPC seconds elapsed
        self.season_index:   int   = 0       # 0 = spring, 1 = summer, 2 = autumn, 3 = winter
        self.day_number:     int   = 0

        # ── Registries ───────────────────────────────────────────────────
        # Populated externally by game loader
        self.npc_registry:   dict  = {}      # name → NPC instance
        self.guild_registry: dict  = {}      # name → Guild instance
        self.region_list:    list  = ["elya"]

        # ── Timers ───────────────────────────────────────────────────────
        self.timers:         list[Timer] = []
        self._timer_lock     = threading.Lock()

        # ── Weather ──────────────────────────────────────────────────────
        self.weather:        dict[str, WeatherState] = {
            "elya": WeatherState(region="elya")
        }
        self._last_weather_fetch: float = 0.0

        # ── Economy ──────────────────────────────────────────────────────
        self.economies:      dict[str, RegionalEconomy] = {
            "elya": RegionalEconomy(region="elya")
        }
        self._last_economy_tick: float = time.time()

        # ── Caravans ─────────────────────────────────────────────────────
        self.caravans:       list[Caravan] = []
        self._last_caravan_tick: float = time.time()
        self._caravan_counter: int = 0

        # ── News ─────────────────────────────────────────────────────────
        self.news_feed:      list[NewsItem] = []
        self.notice_boards:  dict[str, list[NoticeBoardPost]] = {
            "elya": []
        }

        # ── Shop queues ──────────────────────────────────────────────────
        # Each shop has its own queue; transactions process one at a time
        self.shop_queues:    dict[str, queue.Queue] = {}
        self.shop_locks:     dict[str, threading.Lock] = {}

        # ── Player tracking ──────────────────────────────────────────────
        self.connected_players: dict[str, ConnectedPlayer] = {}
        self.player_last_seen:  dict[str, float] = {}
        self.player_locations:  dict[str, str]   = {}

        # ── NPC tick ─────────────────────────────────────────────────────
        self._last_npc_tick: float = time.time()

        # ── Server (multiplayer) ─────────────────────────────────────────
        self._server_socket:   Optional[socket.socket] = None
        self._server_thread:   Optional[threading.Thread] = None
        self._client_threads:  list[threading.Thread] = []
        self._running:         bool = False

        # ── Notifications queue (player name → list of messages) ─────────
        self._notifications:   dict[str, list[str]] = {}
        self._notif_lock       = threading.Lock()


    # ─────────────────────────────────────────────────────────────────────
    #  MASTER CLOCK
    # ─────────────────────────────────────────────────────────────────────

    @property
    def npc_hour(self) -> float:
        """Current hour of NPC day (0–24)."""
        return (self.npc_time / NPC_HOUR) % 24

    @property
    def npc_day_number(self) -> int:
        return int(self.npc_time / NPC_DAY)

    @property
    def season_name(self) -> str:
        return ["Spring", "Summer", "Autumn", "Winter"][self.season_index % 4]

    def tick(self) -> list[str]:
        """
        Advance simulation by real time elapsed since last tick.
        Called by game loop or server thread.
        Returns list of world-level notification strings.
        """
        now     = time.time()
        elapsed = min(now - self.last_tick_time, MAX_CATCHUP_NPC_HOURS)
        self.last_tick_time = now
        self.npc_time      += elapsed * REAL_TO_NPC_RATIO

        notifications = []

        # Season advancement
        new_season = int(self.npc_time / NPC_SEASON) % 4
        if new_season != self.season_index:
            self.season_index = new_season
            notifications.append(
                f"The season has changed to {self.season_name}."
            )
            self._on_season_change(notifications)

        # Weather fetch (once per NPC day)
        if (now - self._last_weather_fetch) >= WEATHER_FETCH_INTERVAL:
            self._fetch_weather()
            self._last_weather_fetch = now

        # NPC ticks
        if (now - self._last_npc_tick) >= NPC_TICK_INTERVAL:
            self._tick_npcs(notifications)
            self._last_npc_tick = now

        # Caravan ticks
        if (now - self._last_caravan_tick) >= CARAVAN_TICK_INTERVAL:
            self._tick_caravans(notifications)
            self._last_caravan_tick = now

        # Economy ticks
        if (now - self._last_economy_tick) >= ECONOMY_TICK_INTERVAL:
            self._tick_economy(notifications)
            self._last_economy_tick = now

        # Timer checks
        self._check_timers(notifications)

        # Clean expired news
        self.news_feed = [n for n in self.news_feed if not n.is_expired]

        return notifications


    # ─────────────────────────────────────────────────────────────────────
    #  TIMERS
    # ─────────────────────────────────────────────────────────────────────

    def add_timer(
        self,
        timer_id:   str,
        category:   str,
        entity_id:  str,
        duration:   float,
        payload:    dict = None,
    ) -> Timer:
        """Add a timer. duration in real seconds."""
        timer = Timer(
            timer_id   = timer_id,
            category   = category,
            entity_id  = entity_id,
            expires_at = time.time() + duration,
            payload    = payload or {},
        )
        with self._timer_lock:
            self.timers.append(timer)
        return timer

    def remove_timer(self, timer_id: str) -> None:
        with self._timer_lock:
            self.timers = [t for t in self.timers if t.timer_id != timer_id]

    def get_timer(self, timer_id: str) -> Optional[Timer]:
        for t in self.timers:
            if t.timer_id == timer_id:
                return t
        return None

    def _check_timers(self, notifications: list[str]) -> None:
        """Fire all expired timers."""
        with self._timer_lock:
            expired = [t for t in self.timers if t.is_expired]

        for timer in expired:
            timer.fired = True
            self._fire_timer(timer, notifications)

        with self._timer_lock:
            self.timers = [t for t in self.timers if not t.fired]

    def _fire_timer(self, timer: Timer, notifications: list[str]) -> None:
        """Handle a fired timer based on its category."""
        if timer.category == "quest":
            self._on_quest_timer_expired(timer, notifications)
        elif timer.category == "jail":
            self._on_jail_timer_expired(timer, notifications)
        elif timer.category == "event":
            self._on_event_timer_expired(timer, notifications)
        elif timer.category == "notice":
            self._on_notice_expired(timer, notifications)
        elif timer.category == "weather_override":
            region = timer.payload.get("region", "elya")
            if region in self.weather:
                self.weather[region].fantasy_override = None

    def _on_quest_timer_expired(self, timer: Timer, notifications: list[str]) -> None:
        """Quest timed out — apply failure penalties immediately."""
        player_name = timer.entity_id
        quest_id    = timer.payload.get("quest_id", "")
        penalties   = timer.payload.get("penalties", {})
        quest_name  = timer.payload.get("quest_name", "A quest")

        msg = f"[QUEST FAILED] {quest_name} has expired."
        if penalties.get("gold_loss"):
            msg += f" Lost {penalties['gold_loss']} Gold."
        if penalties.get("reputation_loss"):
            msg += f" Reputation decreased."
        if penalties.get("relationship_damage"):
            msg += f" Your standing with {penalties.get('npc_name','')} has suffered."

        self._notify_player(player_name, msg)
        notifications.append(f"Quest '{quest_name}' failed for {player_name}.")

    def _on_jail_timer_expired(self, timer: Timer, notifications: list[str]) -> None:
        """Jail sentence completed."""
        player_name = timer.entity_id
        self._notify_player(player_name, "Your sentence is complete. You are free to go.")

    def _on_event_timer_expired(self, timer: Timer, notifications: list[str]) -> None:
        """A scheduled world event fires."""
        event_type  = timer.payload.get("event_type", "")
        region      = timer.payload.get("region", "elya")
        player_name = timer.payload.get("player", "")

        if event_type == "evolution_decay_start":
            # Notify the player's EvolutionSystem via the notification queue.
            # The game loop must call player.evolution_system.on_evolution_decay_start(player)
            # when it receives this notification tag.
            self._notify_player(
                player_name,
                f"__evolution_decay_start__",
            )
            notifications.append(
                f"Evolution decay timer fired for {player_name}."
            )
            return

        self._trigger_world_event(event_type, region, notifications)

    def _on_notice_expired(self, timer: Timer, notifications: list[str]) -> None:
        """Notice board post expired — remove it."""
        post_id  = timer.payload.get("post_id", "")
        location = timer.payload.get("location", "elya")
        board    = self.notice_boards.get(location, [])
        self.notice_boards[location] = [p for p in board if p.post_id != post_id]


    # ─────────────────────────────────────────────────────────────────────
    #  WEATHER
    # ─────────────────────────────────────────────────────────────────────

    def _fetch_weather(self) -> None:
        """
        Fetch real weather for Brevard NC from OpenWeatherMap.
        Maps to Kyros weather type. Applies to all regions with
        slight randomized variation per region.
        """
        if not OPENWEATHER_API_KEY:
            return

        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q=Brevard,NC,US&appid={OPENWEATHER_API_KEY}&units=imperial"
        )
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            return

        condition_id  = data.get("weather", [{}])[0].get("main", "Clear").lower()
        temperature   = data.get("main", {}).get("temp", 65.0)
        kyros_type    = WEATHER_MAP.get(condition_id, "clear")

        for region, weather in self.weather.items():
            # Small regional variation
            if random.random() < 0.15:
                # 15% chance a region gets adjacent weather type
                variations = {
                    "clear":   ["cloudy"],
                    "cloudy":  ["clear", "rain"],
                    "rain":    ["cloudy", "storm"],
                    "storm":   ["rain"],
                    "blizzard":["storm"],
                    "fog":     ["cloudy", "rain"],
                }
                alts = variations.get(kyros_type, [kyros_type])
                regional_type = random.choice(alts)
            else:
                regional_type = kyros_type

            weather.kyros_type    = regional_type
            weather.raw_condition = condition_id
            weather.temperature   = temperature
            weather.fetched_at    = time.time()

            # Apply mood effect to NPCs in this region
            emotion_type, intensity = weather.mood_effect
            if intensity > 0:
                self._apply_weather_mood_to_region(region, emotion_type, intensity)

    def _apply_weather_mood_to_region(
        self,
        region:       str,
        emotion_type: str,
        intensity:    int,
    ) -> None:
        """Apply weather-driven emotion to all NPCs in a region."""
        for npc in self.npc_registry.values():
            if getattr(npc, "location", None) == region:
                npc.update_emotion(
                    emotion_type,
                    float(intensity),
                    f"weather: {self.weather[region].active_type}",
                    masked = True,   # weather moods are masked
                )

    def trigger_fantasy_weather(
        self,
        region:    str,
        weather_type: str,
        duration:  float,
        source:    str = "unknown",
    ) -> list[str]:
        """
        Trigger a fantasy weather event (magical storm, arcane fog, etc.)
        independent of real-world weather. Duration in real seconds.
        """
        if region not in self.weather:
            self.weather[region] = WeatherState(region=region)
        self.weather[region].fantasy_override = weather_type
        self.weather[region].override_until   = time.time() + duration

        self.add_timer(
            timer_id  = f"weather_override_{region}_{int(time.time())}",
            category  = "weather_override",
            entity_id = region,
            duration  = duration,
            payload   = {"region": region},
        )

        news = self._generate_weather_news(region, weather_type, source)
        self._add_news(news)
        return [f"Magical weather event in {region}: {weather_type}"]

    def _generate_weather_news(
        self,
        region: str,
        weather_type: str,
        source: str,
    ) -> NewsItem:
        result = _call_claude_json(
            "Generate a news headline and body for a weather event in the world of Kyros. "
            "Output ONLY JSON with keys: headline (string), body (string, 1-2 sentences).",
            [{"role": "user", "content":
              f"Region: {region}, Weather: {weather_type}, Caused by: {source}"}],
        )
        return NewsItem(
            news_id  = f"news_{int(time.time())}_{random.randint(1000,9999)}",
            headline = result.get("headline", f"{weather_type.title()} strikes {region}!"),
            body     = result.get("body", f"A {weather_type} has descended upon {region}."),
            region   = "regional",
            source   = source,
        )

    def get_weather(self, region: str) -> WeatherState:
        return self.weather.get(region, WeatherState(region=region))


    # ─────────────────────────────────────────────────────────────────────
    #  NPC TICKS
    # ─────────────────────────────────────────────────────────────────────

    def _tick_npcs(self, notifications: list[str]) -> None:
        """
        Advance all NPCs: decay ticks, goal pursuit, schedule following,
        gossip propagation, player absence reactions.
        """
        npc_hour = self.npc_hour
        world_state = {
            "npc_hour":   npc_hour,
            "season":     self.season_name,
            "day_number": self.npc_day_number,
            "weather":    {r: w.active_type for r, w in self.weather.items()},
        }

        for name, npc in self.npc_registry.items():
            # Decay tick
            npc.decay_tick()

            # Schedule
            npc.follow_schedule(npc_hour)

            # Goal pursuit
            if npc.is_available:
                result = npc.pursue_goal(
                    npc_registry = self.npc_registry,
                    world_state  = world_state,
                )
                if result:
                    notifications.append(result)

        # Player absence gossip
        self._propagate_absence_gossip(notifications)

    def _propagate_absence_gossip(self, notifications: list[str]) -> None:
        """
        If a player has been absent for at least 1 NPC hour,
        inject absence gossip into NPCs who know them.
        """
        now = time.time()
        for player_name, last_seen in self.player_last_seen.items():
            if player_name in self.connected_players:
                continue  # player is online
            absence_npc_minutes = (now - last_seen) * REAL_TO_NPC_RATIO / 60
            if absence_npc_minutes < 60:
                continue  # less than 1 NPC hour, not notable yet

            description = (
                f"{player_name} has been absent from {self.player_locations.get(player_name,'town')} "
                f"for {int(absence_npc_minutes // 60)} NPC hours."
            )
            for npc in self.npc_registry.values():
                # Only NPCs who have a memory of the player spread this
                player_memory = npc._get_memory(player_name)
                if player_memory and player_memory.score > 200:
                    npc.create_memory(
                        description = description,
                        score       = min(300, player_memory.score * 0.3),
                        source      = "observation",
                        verified    = True,
                    )


    # ─────────────────────────────────────────────────────────────────────
    #  CARAVANS
    # ─────────────────────────────────────────────────────────────────────

    def spawn_caravan(
        self,
        origin:      str,
        destination: str,
        goods:       list[CaravanGoods]  = None,
        gossip:      list[GossipPayload] = None,
    ) -> Caravan:
        """Spawn a new caravan between two regions."""
        self._caravan_counter += 1
        caravan = Caravan(
            caravan_id  = f"caravan_{self._caravan_counter}",
            origin      = origin,
            destination = destination,
            goods       = goods or self._generate_caravan_goods(origin),
            gossip      = gossip or [],
            travel_time = CARAVAN_BASE_TRAVEL_TIME * random.uniform(0.8, 1.3),
        )
        self.caravans.append(caravan)
        return caravan

    def _generate_caravan_goods(self, origin: str) -> list[CaravanGoods]:
        """AI-generate a realistic goods manifest for a caravan."""
        result = _call_claude_json(
            "Generate a caravan goods manifest for a trading caravan in Kyros. "
            "Output ONLY JSON: a list of objects each with item_name (string) "
            "and quantity (int 1-50). Include 3-6 items typical for a trading caravan.",
            [{"role": "user", "content": f"Origin region: {origin}"}],
            max_tokens=300,
        )
        goods = []
        if isinstance(result, list):
            for g in result:
                goods.append(CaravanGoods(
                    item_name        = g.get("item_name", "Trade Goods"),
                    quantity         = int(g.get("quantity", 10)),
                    region_of_origin = origin,
                ))
        return goods or [CaravanGoods("Trade Goods", 20, origin)]

    def _tick_caravans(self, notifications: list[str]) -> None:
        """Advance all caravans. Roll for attacks. Deliver arrived caravans."""
        still_traveling = []
        for caravan in self.caravans:
            if caravan.arrived or caravan.destroyed:
                continue
            if caravan.is_delayed:
                still_traveling.append(caravan)
                continue

            # Check for attack
            attacked = self._roll_caravan_attack(caravan, notifications)
            if not attacked and caravan.progress >= 1.0:
                self._deliver_caravan(caravan, notifications)
                caravan.arrived = True
            else:
                still_traveling.append(caravan)

        self.caravans = [c for c in self.caravans
                         if not c.arrived and not c.destroyed] + []
        # Keep all for history; filter active only for ticking
        self.caravans = still_traveling + [
            c for c in self.caravans if c.arrived or c.destroyed
        ]

    def _roll_caravan_attack(
        self,
        caravan: Caravan,
        notifications: list[str],
    ) -> bool:
        """
        Roll for bandit or monster attack.
        Bandits may take goods. Monsters stay at scene.
        Returns True if attacked.
        """
        attack_type = None
        if random.random() < BANDIT_ATTACK_CHANCE:
            attack_type = "bandit"
        elif random.random() < MONSTER_ATTACK_CHANCE:
            attack_type = "monster"

        if not attack_type:
            return False

        # Generate attack site name
        attack_site = self._generate_attack_site(caravan.origin, caravan.destination)
        caravan.attack_site = attack_site

        if attack_type == "bandit":
            # Bandits take 30–80% of goods to their camp
            stolen_count = int(len(caravan.goods) * random.uniform(0.3, 0.8))
            stolen       = random.sample(caravan.goods, min(stolen_count, len(caravan.goods)))
            caravan.bandits_took.extend(stolen)
            caravan.goods = [g for g in caravan.goods if g not in stolen]
            # Delay caravan significantly
            caravan.delayed_until = time.time() + NPC_HOUR * random.randint(2, 6)
            headline = f"Caravan from {caravan.origin} attacked by bandits near {attack_site}!"
            body     = (
                f"A caravan traveling from {caravan.origin} to {caravan.destination} "
                f"was attacked by bandits near {attack_site}. "
                f"Goods were stolen. The caravan has been delayed."
            )
        else:
            # Monster attack — goods drop at scene, caravan destroyed
            caravan.loot_dropped.extend(caravan.goods)
            caravan.goods    = []
            caravan.destroyed = True
            headline = f"Caravan from {caravan.origin} destroyed by monsters near {attack_site}!"
            body     = (
                f"A caravan traveling from {caravan.origin} to {caravan.destination} "
                f"was destroyed by monsters near {attack_site}. "
                f"The goods remain scattered at the scene."
            )

        # Add news
        news = NewsItem(
            news_id  = f"news_{int(time.time())}_{random.randint(1000,9999)}",
            headline = headline,
            body     = body,
            region   = "regional",
            source   = "caravan_attack",
        )
        self._add_news(news)
        notifications.append(headline)

        # Inject gossip into NPCs at origin and destination
        gossip_desc = f"A caravan from {caravan.origin} was attacked by {attack_type}s near {attack_site}."
        self._inject_regional_gossip(caravan.destination, gossip_desc, 400)
        self._inject_regional_gossip(caravan.origin,      gossip_desc, 350)

        return True

    def _generate_attack_site(self, origin: str, destination: str) -> str:
        """Generate a discoverable location name for the attack site."""
        result = _call_claude_json(
            "Generate a short evocative fantasy location name for a road between two towns. "
            "Output ONLY JSON with key: name (string, 2-4 words).",
            [{"role": "user", "content": f"Between {origin} and {destination}"}],
            max_tokens=50,
        )
        return result.get("name", f"the road between {origin} and {destination}")

    def _deliver_caravan(
        self,
        caravan: Caravan,
        notifications: list[str],
    ) -> None:
        """Deliver caravan goods and gossip to destination region."""
        dest_economy = self.economies.get(caravan.destination)
        if dest_economy:
            for good in caravan.goods:
                dest_economy.record_restock(good.item_name, good.quantity)

        # Deliver gossip to all NPCs in destination region
        for gossip_payload in caravan.gossip:
            self._inject_regional_gossip(
                caravan.destination,
                gossip_payload.description,
                gossip_payload.score,
            )

        notifications.append(
            f"Caravan from {caravan.origin} arrived in {caravan.destination}."
        )


    # ─────────────────────────────────────────────────────────────────────
    #  ECONOMY
    # ─────────────────────────────────────────────────────────────────────

    def _tick_economy(self, notifications: list[str]) -> None:
        """
        Update regional economies. Supply/demand drift toward equilibrium.
        Check for guild bankruptcies.
        """
        for region, economy in self.economies.items():
            # Natural demand/supply drift toward 1.0
            for item in list(economy.demand.keys()):
                economy.demand[item]  = economy.demand[item]  * 0.99 + 0.01
            for item in list(economy.supply.keys()):
                economy.supply[item]  = economy.supply[item]  * 0.99 + 0.01

            # Occasional random demand spike (news event, festival, etc.)
            if random.random() < 0.02:  # 2% per tick
                self._generate_demand_event(region, economy, notifications)

            # Crisis recovery — crises last 1–3 NPC days then resolve
            if economy.crisis:
                crisis_duration = NPC_DAY * random.uniform(1, 3)
                if (time.time() - economy.crisis_since) >= crisis_duration:
                    economy.resolve_crisis()
                    self._add_news(NewsItem(
                        news_id  = f"news_{int(time.time())}",
                        headline = f"Economy in {region} stabilizes.",
                        body     = f"The economic crisis in {region} has begun to ease.",
                        region   = "regional",
                        source   = "economy",
                    ))
                    notifications.append(f"Economic crisis in {region} is easing.")

    def _generate_demand_event(
        self,
        region:  str,
        economy: RegionalEconomy,
        notifications: list[str],
    ) -> None:
        """AI-generate a random demand spike event."""
        if not economy.shop_stock:
            return
        item = random.choice(list(economy.shop_stock.keys()))
        economy.demand[item] = min(2.0, economy.demand.get(item, 1.0) + random.uniform(0.1, 0.4))
        result = _call_claude_json(
            "Generate a one-sentence reason why demand for an item has increased in Kyros. "
            "Output ONLY JSON with key: reason (string).",
            [{"role": "user", "content": f"Region: {region}, Item: {item}"}],
            max_tokens=100,
        )
        reason = result.get("reason", f"Demand for {item} has increased in {region}.")
        self._add_news(NewsItem(
            news_id  = f"news_{int(time.time())}",
            headline = f"Demand for {item} rises in {region}.",
            body     = reason,
            region   = "local",
            source   = "economy",
        ))

    def trigger_guild_bankruptcy(
        self,
        guild_name: str,
        region:     str,
        notifications: list[str],
    ) -> None:
        """
        Handle guild bankruptcy. Causes regional economic crisis:
        - Prices increase across region
        - Some shops may close
        - NPCs may lose jobs, become frugal
        - Unemployment gossip spreads
        """
        economy = self.economies.get(region)
        if economy:
            economy.apply_crisis()
            # Close 1-3 shops owned by the guild
            result = _call_claude_json(
                "List 1-3 shop names that would be associated with this guild in Kyros. "
                "Output ONLY JSON: a list of strings.",
                [{"role": "user", "content": f"Guild: {guild_name}, Region: {region}"}],
                max_tokens=100,
            )
            shops = result if isinstance(result, list) else []
            for shop in shops:
                economy.closed_shops.append(shop)

        # NPCs react — become frugal, lose jobs
        for npc in self.npc_registry.values():
            if getattr(npc, "location", None) == region:
                npc.update_emotion("anxiety", 40.0, f"{guild_name} bankruptcy")
                npc.update_emotion("grief",   20.0, f"{guild_name} bankruptcy")

        # Spread unemployment gossip
        desc = (
            f"The {guild_name} has gone bankrupt! "
            f"The economy of {region} is in crisis. "
            f"Shops are closing and people are losing work."
        )
        self._inject_regional_gossip(region, desc, 600)

        headline = f"{guild_name} declares bankruptcy — {region} in economic crisis!"
        body     = (
            f"The collapse of {guild_name} has sent shockwaves through {region}. "
            f"Prices are rising, shops are closing, and workers face unemployment."
        )
        self._add_news(NewsItem(
            news_id  = f"news_{int(time.time())}",
            headline = headline,
            body     = body,
            region   = "regional",
            source   = f"{guild_name}_bankruptcy",
        ))
        notifications.append(headline)

    def queue_shop_transaction(
        self,
        player_name: str,
        shop_name:   str,
        action:      str,
        item_name:   str,
        quantity:    int,
    ) -> str:
        """
        Queue a shop transaction. Returns a transaction ID.
        Players queue for the same shop; different shops process independently.
        """
        if shop_name not in self.shop_queues:
            self.shop_queues[shop_name] = queue.Queue()
            self.shop_locks[shop_name]  = threading.Lock()

        transaction = ShopTransaction(
            player_name = player_name,
            shop_name   = shop_name,
            action      = action,
            item_name   = item_name,
            quantity     = quantity,
        )
        tx_id = f"tx_{shop_name}_{int(time.time())}_{random.randint(1000,9999)}"
        self.shop_queues[shop_name].put((tx_id, transaction))

        # Notify player they are queued
        position = self.shop_queues[shop_name].qsize()
        if position > 1:
            self._notify_player(
                player_name,
                f"The shop is busy. You are #{position} in queue. Please wait."
            )
        return tx_id

    def process_shop_queue(
        self,
        shop_name: str,
        processor_fn,
    ) -> None:
        """
        Process all queued transactions for a shop sequentially.
        processor_fn(transaction) → list[str] of result messages.
        """
        if shop_name not in self.shop_queues:
            return
        lock = self.shop_locks[shop_name]
        q    = self.shop_queues[shop_name]

        def _process():
            with lock:
                while not q.empty():
                    tx_id, transaction = q.get()
                    results = processor_fn(transaction)
                    self._notify_player(transaction.player_name, "\n".join(results))
                    q.task_done()

        thread = threading.Thread(target=_process, daemon=True)
        thread.start()


    # ─────────────────────────────────────────────────────────────────────
    #  NEWS AND NOTICE BOARD
    # ─────────────────────────────────────────────────────────────────────

    def _add_news(self, news: NewsItem) -> None:
        self.news_feed.append(news)

    def get_notice_board(
        self,
        location: str,
        player_name: str = None,
    ) -> str:
        """
        Return formatted notice board contents for a location.
        Sections: World News | Regional News | Local News | Player Notices
        """
        board  = self.notice_boards.get(location, [])
        active = [p for p in board if not p.is_expired]

        # Auto-expire posts
        self.notice_boards[location] = active

        region_news = [
            n for n in self.news_feed
            if n.region in ("world", "empire", "kingdom")
        ]
        regional_news = [
            n for n in self.news_feed if n.region == "regional"
        ]
        local_news = [
            n for n in self.news_feed if n.region == "local"
        ]

        lines = [f"=== Notice Board — {location.title()} ==="]

        if region_news:
            lines.append("\n── World News ─────────────────────────")
            for n in region_news[-5:]:
                lines.append(f"  {n.headline}")
                lines.append(f"    {n.body}")

        if regional_news:
            lines.append("\n── Regional News ───────────────────────")
            for n in regional_news[-5:]:
                lines.append(f"  {n.headline}")
                lines.append(f"    {n.body}")

        if local_news:
            lines.append("\n── Local News ──────────────────────────")
            for n in local_news[-5:]:
                lines.append(f"  {n.headline}")
                lines.append(f"    {n.body}")

        if active:
            lines.append("\n── Player Notices ──────────────────────")
            for post in active:
                author = "Anonymous" if post.is_anonymous else post.author
                lines.append(f"  [{author}] {post.content}")

        if player_name:
            # Mark all news as read for this player
            for n in self.news_feed:
                if player_name not in n.read_by:
                    n.read_by.append(player_name)

        lines.append("=" * 42)
        return "\n".join(lines)

    def post_notice(
        self,
        player_name: str,
        location:    str,
        content:     str,
        gold_cost:   float = 10.0,
        anonymous:   bool  = False,
    ) -> tuple[bool, str]:
        """
        Post a notice to the board. Costs gold. Returns (success, message).
        """
        if location not in self.notice_boards:
            self.notice_boards[location] = []

        post_id = f"post_{int(time.time())}_{random.randint(1000,9999)}"
        post    = NoticeBoardPost(
            post_id      = post_id,
            author       = player_name,
            content      = content,
            location     = location,
            is_anonymous = anonymous,
            cost         = gold_cost,
        )
        self.notice_boards[location].append(post)

        # Set expiry timer
        self.add_timer(
            timer_id  = f"notice_{post_id}",
            category  = "notice",
            entity_id = player_name,
            duration  = NOTICE_BOARD_EXPIRY,
            payload   = {"post_id": post_id, "location": location},
        )
        return True, f"Notice posted at {location}. Expires in 2 weeks."


    # ─────────────────────────────────────────────────────────────────────
    #  GOSSIP PROPAGATION
    # ─────────────────────────────────────────────────────────────────────

    def _inject_regional_gossip(
        self,
        region:      str,
        description: str,
        score:       float,
    ) -> None:
        """Inject a gossip entry into all NPCs in a region."""
        from npc_objects import GossipEntry, Memory
        decay_rate = Memory.initial_decay_rate(score)
        entry = GossipEntry(
            description               = description,
            score                     = score,
            original_timestamp        = time.time(),
            last_reinforced_timestamp = time.time(),
            decay_rate                = decay_rate,
            source_npc                = "world_event",
            original_score            = score,
        )
        for npc in self.npc_registry.values():
            if getattr(npc, "location", None) == region:
                npc.receive_gossip([entry], self.guild_registry, self.npc_registry)


    # ─────────────────────────────────────────────────────────────────────
    #  WORLD EVENTS
    # ─────────────────────────────────────────────────────────────────────

    def _trigger_world_event(
        self,
        event_type: str,
        region:     str,
        notifications: list[str],
    ) -> None:
        """AI-generated world event. Fires based on timer or player/NPC trigger."""
        result = _call_claude_json(
            "Generate a world event occurring in Kyros. "
            "Output ONLY JSON with keys: "
            "headline (string), body (string, 2 sentences), "
            "scope (string: local/regional/kingdom/empire), "
            "economic_impact (float: -1.0 to 1.0, negative = bad), "
            "npc_emotion (string: emotion type), "
            "npc_emotion_intensity (int: 0-100).",
            [{"role": "user", "content":
              f"Event type: {event_type}\nRegion: {region}\n"
              f"Season: {self.season_name}\n"
              f"Weather: {self.weather.get(region, WeatherState(region)).active_type}"}],
            max_tokens=400,
        )

        headline  = result.get("headline", f"A {event_type} occurs in {region}!")
        body      = result.get("body", "")
        scope     = result.get("scope", "regional")
        econ      = float(result.get("economic_impact", 0.0))
        emotion   = result.get("npc_emotion", "anxiety")
        intensity = float(result.get("npc_emotion_intensity", 20))

        # Add news
        self._add_news(NewsItem(
            news_id  = f"news_{int(time.time())}_{random.randint(1000,9999)}",
            headline = headline,
            body     = body,
            region   = scope,
            source   = event_type,
        ))

        # Economy impact
        if econ != 0.0:
            economy = self.economies.get(region)
            if economy and econ < -0.3:
                economy.apply_crisis()
            elif economy and econ > 0.3:
                # Positive — boost supply
                for item in list(economy.supply.keys()):
                    economy.supply[item] = min(2.0, economy.supply[item] + 0.1)

        # NPC emotion
        if intensity > 0:
            self._apply_weather_mood_to_region(region, emotion, int(intensity))

        # Gossip
        self._inject_regional_gossip(region, headline, 500)
        notifications.append(headline)

    def schedule_world_event(
        self,
        event_type: str,
        region:     str,
        delay:      float,
    ) -> str:
        """Schedule a world event to fire after delay real seconds."""
        timer_id = f"event_{event_type}_{region}_{int(time.time())}"
        self.add_timer(
            timer_id  = timer_id,
            category  = "event",
            entity_id = region,
            duration  = delay,
            payload   = {"event_type": event_type, "region": region},
        )
        return timer_id

    def _on_season_change(self, notifications: list[str]) -> None:
        """
        Seasonal changes: NPC schedules shift, shop stock changes,
        AI-generated seasonal event injected.
        """
        season = self.season_name
        for region in self.region_list:
            economy = self.economies.get(region)
            if economy:
                # Seasonal supply shifts
                if season == "Winter":
                    for item in list(economy.supply.keys()):
                        if "food" in item.lower() or "herb" in item.lower():
                            economy.supply[item] *= 0.7
                elif season == "Summer":
                    for item in list(economy.supply.keys()):
                        if "food" in item.lower():
                            economy.supply[item] *= 1.3

        # Schedule a seasonal event
        self.schedule_world_event(
            event_type = f"seasonal_{season.lower()}_festival",
            region     = "elya",
            delay      = NPC_HOUR * random.randint(2, 12),
        )
        notifications.append(f"Season changed to {season}.")

    def trigger_npc_death(
        self,
        npc_name:   str,
        cause:      str,
        notifications: list[str],
    ) -> None:
        """
        Handle NPC death ripple. AI generates impact based on
        political standing, guild rank, relationship web, prominence.
        """
        npc = self.npc_registry.get(npc_name)
        if not npc:
            return

        result = _call_claude_json(
            "A person has died in Kyros. Generate the world impact. "
            "Output ONLY JSON with keys: "
            "headline (string), body (string), "
            "scope (string: local/regional/kingdom/empire), "
            "economic_impact (float -1 to 1), "
            "political_impact (string: brief description or null), "
            "grief_intensity (int 0-100 for people who knew them).",
            [{"role": "user", "content":
              f"NPC: {npc_name}\n"
              f"Cause of death: {cause}\n"
              f"Political offices: {getattr(npc, 'political_offices', [])}\n"
              f"Guilds: {[m.guild_name for m in getattr(npc, 'guilds', [])]}\n"
              f"Location: {getattr(npc, 'location', 'unknown')}"}],
            max_tokens=400,
        )

        headline      = result.get("headline", f"{npc_name} has died.")
        body          = result.get("body", "")
        scope         = result.get("scope", "local")
        grief         = float(result.get("grief_intensity", 30))

        self._add_news(NewsItem(
            news_id  = f"news_{int(time.time())}",
            headline = headline,
            body     = body,
            region   = scope,
            source   = f"death_{npc_name}",
        ))

        # Grief ripple to related NPCs
        for other_npc in self.npc_registry.values():
            rel = other_npc._get_relationship(npc_name)
            if rel and rel.intensity > 30:
                intensity = grief * (rel.intensity / 100.0)
                other_npc.update_emotion("grief", intensity, f"death of {npc_name}")

        # Gossip
        self._inject_regional_gossip(
            getattr(npc, "location", "elya"),
            f"{npc_name} has died. {cause}",
            500,
        )
        notifications.append(headline)


    # ─────────────────────────────────────────────────────────────────────
    #  PLAYER TRACKING
    # ─────────────────────────────────────────────────────────────────────

    def player_connected(self, player_name: str, location: str) -> None:
        self.connected_players[player_name] = ConnectedPlayer(
            name=player_name, location=location
        )
        self.player_locations[player_name] = location

    def player_disconnected(self, player_name: str) -> None:
        self.player_last_seen[player_name]  = time.time()
        self.player_locations[player_name]  = self.connected_players.get(
            player_name, ConnectedPlayer("", "")
        ).location
        self.connected_players.pop(player_name, None)

    def update_player_location(self, player_name: str, location: str) -> None:
        if player_name in self.connected_players:
            self.connected_players[player_name].location = location
        self.player_locations[player_name] = location

    def get_player_count(self) -> int:
        return len(self.connected_players)

    def is_world_active(self) -> bool:
        """World simulation runs if at least one player is connected."""
        return len(self.connected_players) > 0


    # ─────────────────────────────────────────────────────────────────────
    #  NOTIFICATIONS
    # ─────────────────────────────────────────────────────────────────────

    def _notify_player(self, player_name: str, message: str) -> None:
        """Queue a notification for a specific player."""
        with self._notif_lock:
            if player_name not in self._notifications:
                self._notifications[player_name] = []
            self._notifications[player_name].append(message)

    def poll_notifications(self, player_name: str) -> list[str]:
        """Drain and return all pending notifications for a player."""
        with self._notif_lock:
            msgs = self._notifications.pop(player_name, [])
        return msgs

    def notify_all(self, message: str) -> None:
        for name in self.connected_players:
            self._notify_player(name, message)


    # ─────────────────────────────────────────────────────────────────────
    #  MULTIPLAYER SERVER
    # ─────────────────────────────────────────────────────────────────────

    def run_server(self) -> None:
        """
        Start the multiplayer server.
        Binds to 0.0.0.0:7890.
        Runs simulation tick in background thread.
        Accepts client connections in main thread.
        """
        self._running = True

        # Simulation tick thread
        tick_thread = threading.Thread(
            target = self._simulation_loop,
            daemon = True,
            name   = "SimulationLoop",
        )
        tick_thread.start()

        # TCP server
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((SERVER_HOST, SERVER_PORT))
        self._server_socket.listen(MAX_CLIENTS)
        print(f"[Kyros Server] Listening on {SERVER_HOST}:{SERVER_PORT}")

        try:
            while self._running:
                try:
                    client_sock, addr = self._server_socket.accept()
                    client_thread = threading.Thread(
                        target = self._handle_client,
                        args   = (client_sock, addr),
                        daemon = True,
                    )
                    client_thread.start()
                    self._client_threads.append(client_thread)
                except OSError:
                    break
        finally:
            self._server_socket.close()

    def stop_server(self) -> None:
        self._running = False
        if self._server_socket:
            self._server_socket.close()

    def _simulation_loop(self) -> None:
        """Background thread: runs tick every second if world is active."""
        while self._running:
            if self.is_world_active():
                notifications = self.tick()
                for msg in notifications:
                    self.notify_all(msg)
            time.sleep(1.0)

    def _handle_client(self, client_sock: socket.socket, addr: tuple) -> None:
        """
        Handle a connected player client.

        Protocol: newline-delimited JSON messages.
        Each message: {"action": "...", "payload": {...}}
        Response:     {"ok": true/false, "data": {...}, "notifications": [...]}
        """
        player_name = None
        try:
            client_sock.settimeout(60.0)
            buf = ""
            while self._running:
                try:
                    chunk = client_sock.recv(4096).decode("utf-8")
                    if not chunk:
                        break
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        response, player_name = self._handle_message(
                            msg, player_name, client_sock
                        )
                        client_sock.sendall(
                            (json.dumps(response) + "\n").encode("utf-8")
                        )
                except socket.timeout:
                    # Send ping; check if player still connected
                    try:
                        ping = json.dumps({"action": "ping"}) + "\n"
                        client_sock.sendall(ping.encode("utf-8"))
                    except OSError:
                        break
        finally:
            if player_name:
                self.player_disconnected(player_name)
                print(f"[Kyros Server] {player_name} disconnected from {addr}")
            client_sock.close()

    def _handle_message(
        self,
        msg:         dict,
        player_name: Optional[str],
        client_sock: socket.socket,
    ) -> tuple[dict, Optional[str]]:
        """
        Process a client message. Returns (response_dict, updated_player_name).

        Actions:
        - connect:            player joins world
        - disconnect:         player leaves world
        - update_location:    player moved
        - poll:               get pending notifications
        - shop_transaction:   queue a shop transaction
        - post_notice:        post to notice board
        - get_notice_board:   read the notice board
        - tick_request:       single player requests a manual tick
        """
        action  = msg.get("action", "")
        payload = msg.get("payload", {})
        notifs  = []

        if action == "connect":
            player_name = payload.get("player_name", "Unknown")
            location    = payload.get("location", "elya")
            self.player_connected(player_name, location)
            # Deliver any pending notifications from while they were offline
            notifs = self.poll_notifications(player_name)
            print(f"[Kyros Server] {player_name} connected from {client_sock.getpeername()}")
            return {"ok": True, "data": {"welcome": True}, "notifications": notifs}, player_name

        if action == "disconnect":
            if player_name:
                self.player_disconnected(player_name)
            return {"ok": True, "data": {}, "notifications": []}, None

        if action == "update_location":
            if player_name:
                self.update_player_location(player_name, payload.get("location", ""))
            return {"ok": True, "data": {}, "notifications": []}, player_name

        if action == "poll":
            if player_name:
                notifs = self.poll_notifications(player_name)
            return {"ok": True, "data": {}, "notifications": notifs}, player_name

        if action == "shop_transaction":
            tx_id = self.queue_shop_transaction(
                player_name = player_name or "unknown",
                shop_name   = payload.get("shop_name", ""),
                action      = payload.get("tx_action", "buy"),
                item_name   = payload.get("item_name", ""),
                quantity    = int(payload.get("quantity", 1)),
            )
            return {"ok": True, "data": {"tx_id": tx_id}, "notifications": []}, player_name

        if action == "post_notice":
            success, msg_text = self.post_notice(
                player_name = player_name or "unknown",
                location    = payload.get("location", "elya"),
                content     = payload.get("content", ""),
                gold_cost   = float(payload.get("gold_cost", 10.0)),
                anonymous   = bool(payload.get("anonymous", False)),
            )
            return {"ok": success, "data": {"message": msg_text}, "notifications": []}, player_name

        if action == "get_notice_board":
            board = self.get_notice_board(
                location    = payload.get("location", "elya"),
                player_name = player_name,
            )
            return {"ok": True, "data": {"board": board}, "notifications": []}, player_name

        if action == "trigger_fantasy_weather":
            notifs = self.trigger_fantasy_weather(
                region       = payload.get("region", "elya"),
                weather_type = payload.get("weather_type", "magical_storm"),
                duration     = float(payload.get("duration", NPC_HOUR)),
                source       = payload.get("source", player_name or "unknown"),
            )
            return {"ok": True, "data": {}, "notifications": notifs}, player_name

        if action == "tick_request":
            # Single player manual tick
            notifs = self.tick()
            return {"ok": True, "data": {}, "notifications": notifs}, player_name

        if action == "get_weather":
            region  = payload.get("region", "elya")
            weather = self.get_weather(region)
            return {"ok": True, "data": {
                "type":        weather.active_type,
                "temperature": weather.temperature,
                "combat_mods": weather.combat_modifiers,
            }, "notifications": []}, player_name

        if action == "ping":
            if player_name:
                cp = self.connected_players.get(player_name)
                if cp:
                    cp.last_ping = time.time()
            return {"ok": True, "data": {"pong": True}, "notifications": []}, player_name

        return {"ok": False, "data": {"error": f"Unknown action: {action}"},
                "notifications": []}, player_name


# ─────────────────────────────────────────────────────────────────────────────
#  SERVER CLIENT HELPER (used by game loop to talk to the server)
# ─────────────────────────────────────────────────────────────────────────────

class WorldClient:
    """
    Thin client for the game loop to communicate with WorldSimulation server.
    Used in multiplayer. In single player, game loop calls WorldSimulation directly.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = SERVER_PORT):
        self.host   = host
        self.port   = port
        self._sock  = None
        self._buf   = ""
        self._lock  = threading.Lock()

    def connect(self, player_name: str, location: str) -> dict:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self.host, self.port))
        return self._send({"action": "connect", "payload": {
            "player_name": player_name, "location": location
        }})

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._send({"action": "disconnect", "payload": {}})
            except Exception:
                pass
            self._sock.close()
            self._sock = None

    def poll(self) -> list[str]:
        resp = self._send({"action": "poll", "payload": {}})
        return resp.get("notifications", [])

    def update_location(self, location: str) -> None:
        self._send({"action": "update_location", "payload": {"location": location}})

    def get_weather(self, region: str = "elya") -> dict:
        resp = self._send({"action": "get_weather", "payload": {"region": region}})
        return resp.get("data", {})

    def get_notice_board(self, location: str) -> str:
        resp = self._send({"action": "get_notice_board",
                           "payload": {"location": location}})
        return resp.get("data", {}).get("board", "")

    def post_notice(
        self,
        location:  str,
        content:   str,
        gold_cost: float = 10.0,
        anonymous: bool  = False,
    ) -> tuple[bool, str]:
        resp = self._send({"action": "post_notice", "payload": {
            "location": location, "content": content,
            "gold_cost": gold_cost, "anonymous": anonymous,
        }})
        return resp.get("ok", False), resp.get("data", {}).get("message", "")

    def shop_transaction(
        self,
        shop_name: str,
        action:    str,
        item_name: str,
        quantity:  int = 1,
    ) -> str:
        resp = self._send({"action": "shop_transaction", "payload": {
            "shop_name": shop_name, "tx_action": action,
            "item_name": item_name, "quantity": quantity,
        }})
        return resp.get("data", {}).get("tx_id", "")

    def trigger_fantasy_weather(
        self,
        region:       str,
        weather_type: str,
        duration:     float,
        source:       str = "player",
    ) -> list[str]:
        resp = self._send({"action": "trigger_fantasy_weather", "payload": {
            "region": region, "weather_type": weather_type,
            "duration": duration, "source": source,
        }})
        return resp.get("notifications", [])

    def tick(self) -> list[str]:
        """Single player tick request."""
        resp = self._send({"action": "tick_request", "payload": {}})
        return resp.get("notifications", [])

    def _send(self, msg: dict) -> dict:
        with self._lock:
            if not self._sock:
                return {}
            try:
                self._sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
                self._sock.settimeout(10.0)
                while "\n" not in self._buf:
                    chunk = self._sock.recv(4096).decode("utf-8")
                    if not chunk:
                        return {}
                    self._buf += chunk
                line, self._buf = self._buf.split("\n", 1)
                return json.loads(line.strip())
            except Exception:
                return {}


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT (run as server process)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kyros World Simulation Server")
    parser.add_argument("--world",  default="Kyros",   help="World name")
    parser.add_argument("--host",   default="0.0.0.0", help="Bind host")
    parser.add_argument("--port",   default=7890, type=int, help="Bind port")
    args = parser.parse_args()

    SERVER_HOST = args.host
    SERVER_PORT = args.port

    sim = WorldSimulation(world_name=args.world, is_multiplayer=True)
    print(f"[Kyros Server] Starting world '{args.world}'")
    try:
        sim.run_server()
    except KeyboardInterrupt:
        print("\n[Kyros Server] Shutting down.")
        sim.stop_server()