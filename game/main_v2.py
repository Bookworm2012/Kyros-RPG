import random

class Spell:
    
    def __init__(self, caster, target, ability_name, thing_affected, how_much_affected, caster_affected, caster_change):
        self.caster = caster
        self.target = target
        self.ability_name = ability_name
        self.affects = thing_affected
        self.change = how_much_affected
        self.caster_affected = caster_affected
        self.caster_change = caster_change

    def use_ability(self):
        if self.caster == Character.name:
            print(f"You cast {self.ability_name} at {self.target} for {self.change} points " +
            f"to {self.target}'s {self.affects} pool. ")
            # Subtract self.caster change from self.caster_affeted pool 
            #subrtact self.change from self.affects


class StatusEffect(Spell):

    def __init__(self, caster, target, ability_name, thing_affected, how_much_affected, duration):

        super().__init__(caster, target, ability_name, thing_affected, how_much_affected)

        self.duration = duration

    def apply_effect(self):
        if self.change < 0:
            print(f"{self.caster} hits your {self.affects} pool for {self.change} points. " +
            f"Debuff has {self.duration}turns remaining.")
            self.duration -= 1
            # Subtract points from respective pools

        elif self.change > 0:
            print(f"{self.caster} hits your {self.affects} pool for {self.change} points. " +
            f"Buff has {self.duration} turns remaining.")

        else:
            print("This effect does nothing.")
            self.duration -= 1





class Race:

    def __init__(self, race, stat_variation, abilities):
        self.race = race
        self.stat_variation = stat_variation
        self.racial_abilities = abilities

human = Race("human", {
        "STR": [3, 7],
        "AGI": [5, 10],
        "DEX": [2, 3],
        "CON": [4, 6],
        "PER": [1, 7],
        "INT": [6, 9],
        "WIS": [5, 9],
        "WIL": [5, 7],
        "CHA": [2, 8],
        "LUCK": [3, 6]
    }, ["Fast learning"]
    )
class Character:



    def __init__(self, username, race):
        #self.name = input("Name? ")
        self.health = 10
        self.mana = 10
        self.gold = 10
        self.stats = {}
        self.expanded = {}
        self.active_affects = {}
        self.spells = {}
        self.race = race
        self.genetics = {
            #STR determines physical attack
            "STR": round(random.uniform(0, 1), 2),
            #AGI determines sneak and move speed
            "AGI": round(random.uniform(0, 1), 2),
            #DEX determines dodge chance
            "DEX": round(random.uniform(0, 1), 2),
            #CON determines max HP, resistance
            "CON": round(random.uniform(0, 1), 2),
            #PER determines accuracy, chance of spotting things
            "PER": round(random.uniform(0, 1), 2),
            #INT determines spell damage
            "INT": round(random.uniform(0, 1), 2),
            #WIS determines size of mana pool
            "WIS": round(random.uniform(0, 1), 2),
            #WIL determines mental resistances
            "WIL": round(random.uniform(0, 1), 2),
            #CHA determines how much people like you, how much they listen
            "CHA": round(random.uniform(0, 1), 2),
            #LUCK determines random chance
            "LUCK": round(random.uniform(0, 1), 2)
            }
        self.stats = self.generate_stats(self.race.stat_variation)

    def generate_stats(self, stat_variation):
        for stat in self.race.stat_variation:
            stat_max = stat_variation[stat][1]
            stat_min = stat_variation[stat][0]
            gene = self.genetics[stat]
            final_stat = round(stat_min + (stat_max - stat_min) * gene)
            self.stats[stat] = final_stat
        return self.stats

    def expand_stats(self, stat_variation):
        for stat in self.race.stat_variation:
            stat_max = stat_variation[stat][1]
            stat_min = stat_variation[stat][0]
            gene = self.genetics[stat]
            final_stat = round(stat_min + (stat_max - stat_min) * gene)
            expanded_str = f" Max: {stat_max}. Min: {stat_min}. Gene: {gene}. Final stat: {final_stat}."
            self.expanded[stat] = expanded_str
        return self.expanded

    def show_attributes(self):
        print(f"Race: {self.race.race} \n HP: {self.health} \n MP: {self.mana} \n Gold: {self.gold}")

    def apply_status_effect(self):
        for effect in self.status_effcts:
            pass


"""
    def change_gold_total(self, amount):
        self.gold = self.gold + amount
        if amount < 0:
            print(f"You lost {abs(amount)} gold.")
        else:
            print(f"You gained {amount} gold!")


"""
player1 = Character("player", human)
for stat, value in player1.stats.items():
    print(f"{stat}: {value}")

print("Expand stats? Y/N")
while True:
    expand = input(">>> ")
    expand = expand.lower()
    if expand == "n":
        print("Continuing . . . ")
        break
    elif expand == "y":
        print(player1.expand_stats())
        break
    else:
        print("Please enter Y/N")

print("Would you like to see the other attributes? Y/N")
while True:
    attributes = input(">>> ")
    if attributes.lower() == "n":
        break
    elif attributes.lower() == "y":
        player1.show_attributes()
        break


    else:
        print("Please enter Y/N")

test_spell = Spell("You", "Thunderbird", "test_spell", "Health", -5, "Mana", 10)
test_status_effect = StatusEffect("You", "Thunderbird", "test_status_effct", "Health", -5, "Mana", 10, 3)
print(test_spell.ability_name)
print(test_spell.caster)
print(test_spell.target)
print(test_spell.affects)
print(test_spell.change)
print(test_spell.caster_affected)
print(test_spell.caster_change)

test_spell.use_ability()

print(test_status_effect.ability_name)
print(test_status_effect.caster)
print(test_status_effect.target)
print(test_status_effect.affects)
print(test_status_effect.change)
print(test_status_effect.caster_affected)
print(test_status_effect.caster_change)
print(test_status_effect.duration)

test_status_effect.apply_effect()
"""
#player1.amount_gold_changed = 5
#print(player1)
#print(player1.name)
#print(type(player1))
print(type(player1.gold))
player1.change_gold_total(0)
"""