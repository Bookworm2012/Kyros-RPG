import time
import random
import inspect
import sys

def CalcSellPrice(item, BasePrice, ShopStock):
  Base = BasePrice[item]
  Stock = ShopStock[item]
  StockFactor = max(0.5, min(1.5, 1.0 - (Stock - 5) * 0.1))
  FinalPrice = int(Base * StockFactor)
  return FinalPrice

def SellItem(item, ShopStock, Gold, BasePrice, Inventory, TextMode):
    if item not in Inventory:
      print(GamePrint("You don't have that item.", TextMode))
      return
    Price = CalcSellPrice(item, BasePrice, ShopStock)
    while True:
        Choice = GameInput(f"The shop offers {Price} Gold for your {item}. Sell it? y/n ", TextMode)
        if Choice == "y":
            Inventory.remove(item)
            Gold += Price
            ShopStock[item] += 1
            print(GamePrint(f"You sold {item} for {Price} Gold.", TextMode))
            print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
            break
        elif Choice == "n":
            print(GamePrint("You keep the item.", TextMode))
            break
        else:
            print(GamePrint("Please enter y/n.", TextMode))
    return ShopStock, Inventory, Gold

def Pause(seconds):
  time.sleep(seconds)

def AskName(Name, TextMode):
  Name = input("Traveler, what would you like to be called in this new world? ")
# Line 40 is asking what the player wants to be called
  return Name

def PerformAttack(attacker_atk, defender_def, defender_hp):
    damage = attacker_atk - defender_def
    if damage < 0:
        damage = 0
    defender_hp -= damage
    if defender_hp < 0:
        defender_hp = 0
    return damage, defender_hp

def LootEnemy(loot_table, Inventory, Gold):
    for item, max_qty, chance in loot_table:
        roll = random.randint(1, chance)
        if roll == 1:
            qty = random.randint(1, max_qty)
            for _ in range(qty):
                Inventory.append(item)
            print(f"You obtained {item} x{qty}.")

    return Inventory, Gold

def RegenerationCode(LastRegenTime, MaxHealth, Health, HealthRegenMultiplier,
                    MaxMana, Mana, ManaRegenMultiplier, TextMode):
  if time.time() - LastRegenTime >= 60:
    HealthRegen = int(MaxHealth * 0.1)
    ManaRegen = int(MaxMana * 0.1)
    MinutesPassed = int((time.time()-LastRegenTime)/60)
    if Health < MaxHealth:
      HealthAdded = int(HealthRegen * MinutesPassed * HealthRegenMultiplier)
      Health += HealthAdded
      if Health > MaxHealth:
        Health = MaxHealth
      print(GamePrint(f"Time has passed . . . You regenerated {HealthAdded} " +
    f"health.", TextMode))
    if Mana < MaxMana:
      ManaAdded = int(ManaRegen * MinutesPassed * ManaRegenMultiplier)
      Mana += ManaAdded
      if Mana > MaxMana:
        Mana = MaxMana
      print(GamePrint(f"Time has passed . . . You regenerated {ManaAdded} " +
    f"mana.", TextMode))
    LastRegenTime = time.time()
  return LastRegenTime, Health, Mana
def EquipItem(ItemName, Mana, MaxMana, ManaRegenMultiplier, Health, MaxHealth,
HealthRegenMultiplier, Equipped, Inventory, Consumables, UnlockorCraft, AtkPwr,
Defense, BuffActive, BuffEndTime, TextMode, SecretCode, RegisteredAdventurer):
  print(GamePrint(f"---- {ItemName} ----", TextMode))
  if ItemName == "Basic Health Potion":
    print(GamePrint("Description: A red liquid in a dented metal flask.", TextMode))
    print(GamePrint("Stats: + 5 Health", TextMode))
  elif ItemName == "Fish and Chips":
    print(GamePrint("Description: Salty, greasy, and included by request.", TextMode))
    print(GamePrint("Stats: + 2 AtkPwr, + 2 Defense", TextMode))
  elif ItemName == "Phoenix Tears":
    print(GamePrint("Description: Clear liquid in a small glass vial.", TextMode))
    print(GamePrint(f"Stats: + {MaxHealth - Health} Health", TextMode))
  elif ItemName == "Sage's Secret Stew":
    print(GamePrint("Description: A hearty stew that is the owner's secret recipe", TextMode))
    print(GamePrint(f"Stats: + {MaxMana - Mana} Mana", TextMode))
  elif ItemName == "Broccoli Cheddar Soup":
    print(GamePrint("Description: The favorite soup of the dev, included because it is so good.", TextMode))
    print(GamePrint("Stats: + 10% Health Regeneration", TextMode))
  elif ItemName == "Butterbeer":
    print(GamePrint("Description: A sweet drink infused with magic, from the lands of Hogwarts.", TextMode))
    print(GamePrint("Stats: + 10% Mana Regeneration", TextMode))
  elif ItemName == "Water":
    print(GamePrint("Description: Cool water.", TextMode))
    print(GamePrint("Stats: + 3 Health", TextMode))
  elif ItemName == "Bread":
    print(GamePrint("Description: Simple bread.", TextMode))
    print(GamePrint("Stats: + 3 Mana", TextMode))
  elif ItemName == "Dev Sword":
    print(GamePrint("Description: A tool of the devs, used to explore different " +
          "branches of code.", TextMode))
    print(GamePrint("Stats: + 50 AtkPwr, + 50 Defense", TextMode))
  elif ItemName == "Basic Armor":
    print(GamePrint("Description: Dented starter armor.", TextMode))
    print(GamePrint("Stats: + 1 Defense", TextMode))
  elif ItemName == "Regular Armor":
    print(GamePrint("Description: Undented starter armor.", TextMode))
    print(GamePrint("Stats: + 3 Defense", TextMode))
  elif ItemName == "Small Dagger":
     print(GamePrint("Description: Twisted starter dagger.", TextMode))
     print(GamePrint("Stats: + 1 AtkPwr", TextMode))
  elif ItemName == "Regular Dagger":
    print(GamePrint("Description: Straight starter dagger.", TextMode))
    print(GamePrint("Stats: + 3 AtkPwr", TextMode))
  elif ItemName == "Mysterious Letter":
    print(GamePrint("Description: A letter from the Blacksmith to the reidents of " +
          "Elya.", TextMode))
    print(GamePrint("Stats: Unlocks secret code to Blacksmith", TextMode))
  elif ItemName == "Tattered Map":
    print(GamePrint("Description: A ripped map with symbols on it.", TextMode))
    print(GamePrint("Stats: ???????", TextMode))
  print(GamePrint("1. Use/Equip", TextMode))
  print(GamePrint("2. Back to Inventory", TextMode))
  Choice = GameInput("What do you choose to do? ", TextMode)
  if Choice == "1":
     # Call the existing functions based on the item name
        if ItemName not in Consumables["Elya"]:

          Equipped.append(ItemName)
          Inventory.remove(ItemName)
        if ItemName == "Basic Health Potion":
            Health, MaxHealth, Inventory = BasicHealthPotion(Health, MaxHealth,
                                                                Inventory, TextMode)
        elif ItemName == "Fish and Chips":
            AtkPwr, Defense, BuffActive, BuffEndTime, Inventory = FishAndChipsInventory(
                AtkPwr, Defense, BuffActive, BuffEndTime, Inventory, TextMode)
        elif ItemName == "Sage's Secret Stew":
            Mana, MaxMana, Inventory = SagesSecretStewInventory(Mana, MaxMana,
            Inventory, TextMode)
        elif ItemName == "Phoenix Tears":
            Health, MaxHealth, Inventory, = PhoenixTearsInventory(Health,
            MaxHealth, Inventory, TextMode)
        elif ItemName == "Broccoli Cheddar Soup":
            HealthRegenMultiplier, Inventory = BroccoliCheddarSoupInventory(HealthRegenMultiplier,
            Inventory, TextMode)
        elif ItemName == "Butterbeer":
            ManaRegenMultiplier, Inventory = ButterbeerInventory(ManaRegenMultiplier,
            Inventory, TextMode)
        elif ItemName == "Bread":
            Health, Inventory = BreadInventory(Health, MaxHealth, Inventory, TextMode)
        elif ItemName == "Water":
            Mana, MaxMana, Inventory = WaterInventory(Mana, MaxMana, Inventory, TextMode)
        elif ItemName == "Dev Sword":
            AtkPwr, Defense = DevSword(AtkPwr, Defense, TextMode)
        elif ItemName == "Small Dagger":
            AtkPwr = SmallDagger(AtkPwr, TextMode)
        elif ItemName == "Basic Armor":
            Defense = BasicArmor(Defense, TextMode)
        elif ItemName == "Regular Armor":
            Defense = RegularArmor(Defense, TextMode)
        elif ItemName == "Regular Dagger":
            AtkPwr = RegularDagger(AtkPwr, TextMode)
        elif ItemName == "Mysterious Letter":
            MysteriousLetter(SecretCode, TextMode)
        elif ItemName == "Slime Core":
            SlimeCore(TextMode)
        elif ItemName == "Vial of Slime":
            VialOfSlime(TextMode)
        elif ItemName == "Wolf Fang":
            WolfFang(TextMode)
        elif ItemName == "Tattered Map":
            TatteredMap(RegisteredAdventurer, TextMode)
        if ItemName not in UnlockorCraft:
          print(GamePrint(f"Successfully used/equipped {ItemName}!", TextMode))
  return (MaxMana, Mana, ManaRegenMultiplier, Health, MaxHealth,
  HealthRegenMultiplier, AtkPwr, Defense, BuffActive, BuffEndTime,
  Equipped, Inventory)

def UnequipItem(ItemName, AtkPwr, Defense, Equipped, Inventory, TextMode):
  if ItemName in Equipped:
    if ItemName == "Dev Sword":
      AtkPwr -= 50
      Defense -= 50
      print(GamePrint(f"Your AtkPwr is now {AtkPwr}.", TextMode))
      print(GamePrint(f"Your Defense is now {Defense}.", TextMode))
    elif ItemName == "Small Dagger":
      AtkPwr -= 1
      print(GamePrint(f"Your AtkPwr is now {AtkPwr}.", TextMode))
    elif ItemName == "Regular Dagger":
      AtkPwr -= 3
      print(GamePrint(f"Your AtkPwr is now {AtkPwr}.", TextMode))
    elif ItemName == "Basic Armor":
      Defense -= 1
      print(GamePrint(f"Your Defense is now {Defense}.", TextMode))
    elif ItemName == "Regular Armor":
      Defense -= 3
      print(GamePrint(f"Your Defense is now {Defense}", TextMode))

    Equipped.remove(ItemName)
    Inventory.append(ItemName)
    print(GamePrint(f"You unequipped {ItemName}. Your stats have been lowered.", TextMode))
  else:
    print(GamePrint("That item is not equipped.", TextMode))
  return AtkPwr, Defense, Equipped, Inventory
def TextToBF(Text):
    result = ""
    current_value = 0
    for char in Text:
        target = ord(char)
        diff = target - current_value
        if diff > 0:
            result += "+" * diff
        else:
            result += "-" * (-diff)
        result += "."
        current_value = target
    return result

def GamePrint(Text, TextMode):
    if TextMode:
        return TextToBF(Text)
    else:
        return Text

def GameInput(prompt, TextMode):
    if TextMode:
        print(TextToBF(prompt))
        return input(TextToBF("> "))
    else:
        return input(prompt)


def get_my_definitions():
    # Gets all functions AND classes in the current module, excluding imports
    return [
        obj for name, obj in inspect.getmembers(sys.modules[__name__])
        if (inspect.isfunction(obj) or inspect.isclass(obj))
        and obj.__module__ == __name__
    ]

# Example usage
all_definitions = get_my_definitions()


