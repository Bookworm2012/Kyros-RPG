import random

class Character:
    """The parent class for all living things (Players, NPCs, Enemies)"""
    def __init__(self, name, race):
        self.name = name
        self.race = race
        self.health = 10
        self.mana = 10
        self.stamina = 10
        self.gold = 10

        self.active_effects = {}
        self.active_affects = self.active_effects
        self.spells = {}

        # Roll genetics for anyone using this class
        self.genetics = {
            stat: round(random.uniform(0, 1), 2) for stat in ["STR",
        "AGI", "DEX", "VIT", "CON", "PER", "INT", "WIS", "WIL", "CHA", "LUCK"]
        }
        self.stats = self.generate_stats(self.race.stat_variation)

    def generate_stats(self, stat_variation):
        stats = {}
        for stat in stat_variation:
            stat_min, stat_max = stat_variation[stat]
            gene = self.genetics[stat]
            stats[stat] = round(stat_min + (stat_max - stat_min) * gene)
        return stats


class Player(Character):
    """The specific class for the human player"""
    def __init__(self, race):
        # Prompt for name first, then pass it up to the parent class
        player_name = input("Adventurer, what is your name? ")
        super().__init__(name=player_name, race=race)

        # Player-specific tracking
        self.expanded = {}
        self.expand_stats()

    def expand_stats(self, stat_variation=None):
        stat_variation = stat_variation or self.race.stat_variation
        for stat in stat_variation:
            stat_min, stat_max = stat_variation[stat]
            gene = self.genetics[stat]
            final_stat = self.stats[stat]
            self.expanded[stat] = f" Max: {stat_max}. Min: {stat_min}. Gene: {gene}. Final stat: {final_stat}."
        return self.expanded

    def display_status(self):
        print("=" * 20)
        print(f"Name: {self.name}\nRace: {self.race.race}\nMana: {self.mana}\nHealth: {self.health}")
        print(f"Stamina: {self.stamina}\nGold: {self.gold}")
        print("—" * 10)
        print("Stats\n" + "-" * 6)
        for key, value in self.stats.items():
            print(f"{key}: {value}")

