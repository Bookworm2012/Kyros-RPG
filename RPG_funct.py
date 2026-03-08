import time
import random
from dotenv import load_dotenv
import os

load_dotenv()  # reads .env file
DEV_CODE = os.getenv("KYROS_DEV_CODE")

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

def IntroText():
  print("///////////////")
  print("///////////////")
  print("///////////////")
  print("Welcome to this text RPG. You will be dropped in a town square. It is up to" +
     " you to decide what to do.")
  print("///////////////")
  print("///////////////")
  print("///////////////")
  print("///////////////")
  print("World Loading . . . ")
  print("10% . . . ")
  Pause(0.5)
  print("35% . . . ")
  Pause(0.5)
  print("50% . . . ")
  Pause(0.5)
  print("70% . . . ")
  Pause(0.5)
  print("99% . . . ")
  Pause(0.5)
  print("100% . . .")
  Pause(0.5)
  print("Loading Complete")# Lines 29 - 39 are intro text

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

def FishAndChipsTavern(Gold, AtkPwr, Defense, BuffActive, BuffEndTime, Choice, Inventory, TextMode):
  if Gold >= 10:
    Gold -= 10
    print(GamePrint(" - 10 Gold", TextMode))
    print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
    while True:
      Choice = GameInput("Would you like the Fish and Chips here or to go? h/t ", TextMode).lower()
      if Choice == "h":
        Defense += 2
        AtkPwr += 2
        print(GamePrint(" + 2 AtkPwr", TextMode))
        print(GamePrint(" + 2 Defense", TextMode))
        BuffActive = True
        BuffEndTime = time.time() + 60
        print(GamePrint("The sheer awesomeness of Fish and Chips increases your Attack and " +
              "Defense by 2 for 1 minute!", TextMode))
        print(GamePrint(f"Your AtkPwr is now {AtkPwr} for 1 minute", TextMode))
        print(GamePrint(f"Your Defense is now {Defense} for 1 minute", TextMode))
        break
      elif Choice == "t":
        Inventory.append("Fish and Chips")
        print(GamePrint("Fish and Chips has been added to your Inventory.", TextMode))
        break
      else:
        print(GamePrint("Please enter h or t.", TextMode))

  else:
    print(GamePrint(f"You have access to this restricted menu item, but not enough Gold. "
          f"Please get {10 - Gold} more Gold.", TextMode))
  return Gold, AtkPwr, Defense, BuffActive, BuffEndTime, Inventory

def WaterTavern(Gold, Health, MaxHealth, Choice, Inventory, TextMode):
  Gold -= 5
  print(GamePrint(" - 5 Gold", TextMode))
  print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
  while True:
    Choice = GameInput("Would you like the Water here or to go? h/t ", TextMode).lower()
    if Choice == "h":
      print(GamePrint("The cool water rushes through your body, revitalizing you.", TextMode))
      print(GamePrint(" + 3 Health", TextMode))
      Health += 3
      if Health >= MaxHealth:
        Health = MaxHealth
      print(GamePrint(f"Your Health is {Health}/{MaxHealth}", TextMode))
      break
    elif Choice == "t":
      Inventory.append("Water")
      print(GamePrint("Water has been added to Inventory.", TextMode))
      break
    else:
      print(GamePrint("Please enter h or t.", TextMode))
  return Gold, Health, MaxHealth, Inventory

def BreadTavern(Gold, Mana, MaxMana, Choice, Inventory, TextMode):
  Gold -= 5
  print(GamePrint(" - 5 Gold", TextMode))
  print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
  while True:
    Choice = GameInput("Would you like the Bread here or to go? h/t ", TextMode).lower()
    if Choice == "h":
      print(GamePrint("The warm bread falls to your stomach, filling you up.", TextMode))
      print(GamePrint(f" + {MaxMana - Mana} Mana", TextMode))
      Mana += 3
      if Mana >= MaxMana:
        Mana = MaxMana
      print(GamePrint(f"Your Mana is {Mana}/{MaxMana}", TextMode))
      break
    elif Choice == "t":
      Inventory.append("Bread")
      print(GamePrint("Bread has been added to your Inventory.", TextMode))
      break
    else:
      print(GamePrint("Please enter h or t.", TextMode))
  return Gold, Mana, MaxMana, Inventory

def BroccoliCheddarSoupTavern(Gold, HealthRegenMultiplier, Choice, Inventory, TextMode):
  Gold -= 15
  print(GamePrint(" - 15 Gold", TextMode))
  print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
  while True:
    Choice = GameInput("Would you like the Broccoli Cheddar Soup here or to go? h/t ", TextMode).lower()
    if Choice == "h":
      HealthRegenMultiplier += 0.1
      print(GamePrint(" + 10% Health Regen", TextMode))
      print(GamePrint("The hot soup revitalizes your body and soul, increasing your healing rate.", TextMode))
      break
    elif Choice == "t":
      Inventory.append("Broccoli Cheddar Soup")
      print(GamePrint("Broccoli Cheddar Soup has been added to your Inventory", TextMode))
      break
    else:
      print(GamePrint("Please enter h or t.", TextMode))
  return Gold, HealthRegenMultiplier, Inventory

def ButterbeerTavern(Gold, ManaRegenMultiplier, Choice, Inventory, TextMode):
  Gold -= 15
  print(GamePrint(" - 15 Gold", TextMode))
  print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
  while True:
    Choice = GameInput("Would you like the Butterbeer here or to go? h/t ", TextMode).lower()
    if Choice == "h":
      ManaRegenMultiplier += 0.1
      print(GamePrint(" + 10% Mana Regen", TextMode))
      print(GamePrint("The sweet drink, soaked in magic from the far land of Hogwarts, increases" +
        " your mana regeneration rate", TextMode))
      break
    elif Choice == "t":
      Inventory.append("Butterbeer")
      print(GamePrint("Butterbeer has been added to your Inventory", TextMode))
      break
    else:
      print(GamePrint("Please enter h or t.", TextMode))
  return Gold, ManaRegenMultiplier, Inventory

def PhoenixTearsTavern(Gold, Health, MaxHealth, Choice, Inventory, PhoenixPrice, TextMode):
  Gold -= PhoenixPrice
  print(GamePrint(f" - {PhoenixPrice} Gold", TextMode))
  print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
  while True:
    Choice = GameInput("Would you like the Phoenix tears here or to go? h/t ", TextMode).lower()
    if Choice == "h":
      print(GamePrint(f" + {MaxHealth - Health} Health", TextMode))
      Health = MaxHealth
      print(GamePrint("You have been healed to your max Health", TextMode))
      print(GamePrint(f"Your Health is now {Health}/{MaxHealth}", TextMode))
      break
    elif Choice == "t":
      Inventory.append("Phoenix Tears")
      print(GamePrint("You can use them whenever, but cannot purchase more if you still " +
            "have them.", TextMode))
      print(GamePrint("Phoenix Tears have been added to your Inventory", TextMode))
      break
    else:
      print(GamePrint("Please answer h or t.", TextMode))
  return Gold, Health, MaxHealth, Inventory

def SagesSecretStewTavern(Gold, Mana, MaxMana, Choice, Inventory, SagePrice, TextMode):
  Gold -= SagePrice
  print(GamePrint(f" - {SagePrice} Gold", TextMode))
  print(GamePrint(f"Your new balance is {Gold} Gold.",  TextMode))
  while True:
    Choice = GameInput("Would you like the Sage's Secret Stew here or to go? " +
    "h/t ", TextMode).lower()
    if Choice == "h":
      print(GamePrint(f" + {MaxMana - Mana} Mana", TextMode))
      Mana = MaxMana
      print(GamePrint("You have been filled to your max Mana", TextMode))
      print(GamePrint(f"Your Mana is now {Mana}/{MaxMana}", TextMode))
      break
    elif Choice == "t":
      Inventory.append("Sage's Secret Stew")
      print(GamePrint("You can use them whenever, but cannot purchase more if you still " +
            "have them.", TextMode))
      print(GamePrint("Sage's Secret Stew has been added to your Inventory", TextMode))
      break
    else:
      print(GamePrint("Please answer h or t.", TextMode))
  return Gold, Mana, MaxMana, Inventory

def InventoryMenu(Idx, Choice, Inventory, Equipped, Mana, MaxMana,
ManaRegenMultiplier, Health, MaxHealth, HealthRegenMultiplier, AtkPwr, Defense,
BuffActive, BuffEndTime, Consumables, UnlockorCraft, TextMode, SecretCode, RegisteredAdventurer):
  while True:
    print(GamePrint("  INVENTORY MENU", TextMode))
    print(GamePrint("=", TextMode) * 20)
    print(GamePrint("1. Equip/Use", TextMode))
    print(GamePrint("2. Unequip", TextMode))
    print(GamePrint("3. Exit to previous menu", TextMode))
    Choice = GameInput("Choose an action. ", TextMode)
    if Choice == "1":
      if not Inventory:
        print(GamePrint("You have nothing to Equip or use.", TextMode))
      else:
        print(GamePrint("----INVENTORY----", TextMode))
        for i, item in enumerate(Inventory):
          print(GamePrint(f"{i + 1}. {item}", TextMode))
        print(GamePrint(f"{len(Inventory) + 1}. Exit to previous menu", TextMode))
        Choice = GameInput("Please select a number. ", TextMode)
        if Choice.isdigit():
          Idx = int(Choice) - 1
          if 0 <= Idx < len(Inventory):
            ItemName = Inventory[Idx]
            MaxMana, Mana, ManaRegenMultiplier, Health, MaxHealth,
            HealthRegenMultiplier, AtkPwr, Defense, BuffActive, BuffEndTime,
            Equipped, Inventory = EquipItem(ItemName, Mana, MaxMana,
                            ManaRegenMultiplier, Health, MaxHealth,
                            HealthRegenMultiplier, Equipped, Inventory,
                            Consumables, UnlockorCraft, AtkPwr,
                            Defense, BuffActive, BuffEndTime, TextMode,
                            SecretCode, RegisteredAdventurer
                            )
        else:
            print(GamePrint("Please enter a number.", TextMode))
    elif Choice == "2":
      if not Equipped:
        print(GamePrint("You have nothing to Unequip.", TextMode))
      else:
        print(GamePrint("----EQUIPPED----", TextMode))
        for i, item in enumerate(Equipped):
          print(GamePrint(f"{i + 1}. {item}", TextMode))
          print(GamePrint(f"{len(Equipped) + 1}. Exit to previous menu", TextMode))
        Choice = GameInput("Please select a number. ", TextMode)
        if Choice.isdigit():
          Idx = int(Choice) - 1
          if 0 <= Idx < len(Equipped):
            ItemName = Equipped[Idx]
            AtkPwr, Defense, Equipped, Inventory = UnequipItem(ItemName, AtkPwr,
                                                    Defense, Equipped, Inventory, TextMode)
        else:
          print(GamePrint("Please enter a number.", TextMode))
    elif Choice == "3":
      print(GamePrint("You have exited the Inventory Menu.", TextMode))
      break
    else:
      print(GamePrint("Please enter an option above.", TextMode))
  return (Inventory, Equipped, AtkPwr, Defense, MaxMana, Mana,
  ManaRegenMultiplier, Health, MaxHealth, HealthRegenMultiplier, BuffActive,
  BuffEndTime)

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

def BasicHealthPotion(Health, MaxHealth, Inventory, TextMode):
  print(GamePrint("You drink the potion. Gulp . . . ", TextMode))
  Health += 5
  if Health >= MaxHealth:
    Health = MaxHealth
  print(GamePrint(f"You regained 5 Health!", TextMode))
  print(GamePrint(f"{Health}/{MaxHealth}", TextMode))
  Inventory.remove("Basic Health Potion")
  return Health, MaxHealth, Inventory

def FishAndChipsInventory(AtkPwr, Defense, BuffActive, BuffEndTime, Inventory, TextMode):
  print(GamePrint("You quickly eat the fish, the cod settling in your stomach.", TextMode))
  Defense += 2
  AtkPwr += 2
  print(GamePrint(" + 2 AtkPwr", TextMode))
  print(GamePrint(" + 2 Defense", TextMode))
  BuffActive = True
  BuffEndTime = time.time() + 60
  print(GamePrint(f"Your AtkPwr is now {AtkPwr} for 1 minute", TextMode))
  print(GamePrint(f"Your Defense is now {Defense} for 1 minute", TextMode))
  Inventory.remove("Fish and Chips")
  return AtkPwr, Defense, BuffActive, BuffEndTime, Inventory

def PhoenixTearsInventory(Health, MaxHealth, Inventory, TextMode):
  print(GamePrint("You drink the tears. Gulp . . . ", TextMode))
  print(GamePrint(f" + {MaxHealth - Health} Health", TextMode))
  Health = MaxHealth
  print(GamePrint("You have been healed to full health!", TextMode))
  print(GamePrint(f"{Health}/{MaxHealth}", TextMode))
  Inventory.remove("Phoenix Tears")
  return Health, MaxHealth, Inventory

def SagesSecretStewInventory(Mana, MaxMana, Inventory, TextMode):
  print(GamePrint("You eat the stew. Yum . . . ", TextMode))
  print(GamePrint(f" + {MaxMana - Mana} Mana", TextMode))
  Mana = MaxMana
  print(GamePrint("You have been filled to full Mana!", TextMode))
  print(GamePrint(f"{Mana}/{MaxMana}", TextMode))
  Inventory.remove("Sage's Secret Stew")
  return Mana, MaxMana, Inventory

def BroccoliCheddarSoupInventory(HealthRegenMultiplier, Inventory, TextMode):
  print(GamePrint("The cheesy goodness flows down your throat. Soon, you have finished the " +
  "bowl.", TextMode))
  HealthRegenMultiplier += 0.1
  print(GamePrint(" + 10% Health Regeneration rate.", TextMode))
  Inventory.remove("Broccoli Cheddar Soup")
  return HealthRegenMultiplier, Inventory

def ButterbeerInventory(ManaRegenMultiplier, Inventory, TextMode):
  print(GamePrint("The foamy drink is cool and refreshing. Gulp . . . ", TextMode))
  ManaRegenMultiplier += 0.1
  print(GamePrint(" + 10% Mana Regeneration rate", TextMode))
  Inventory.remove("Butterbeer")
  return ManaRegenMultiplier, Inventory

def WaterInventory(Health, MaxHealth, Inventory, TextMode):
  print(GamePrint("The cool liquid slides down your throat, rejuvenating you", TextMode))
  Health += 3
  if Health >= MaxHealth:
      Health = MaxHealth
  print(GamePrint(f" + 3 Health", TextMode))
  print(GamePrint(f"{Health}/{MaxHealth}", TextMode))
  Inventory.remove("Water")
  return Health, Inventory

def BreadInventory(Mana, MaxMana, Inventory, TextMode):
  print(GamePrint("The warm bread enters your mouth, slightly filling your Mana pool.", TextMode))
  Mana += 3
  if Mana >= MaxMana:
      Mana = MaxMana
  print(GamePrint(" + 3 Mana", TextMode))
  print(GamePrint(f"{Mana}/{MaxMana}", TextMode))
  Inventory.remove("Bread")
  return Mana, Inventory

def MysteriousLetter(SecretCode, TextMode):
  print(GamePrint(f"You read the letter: It says, Dear Residents of Elya. You must " +
          f"tell me the code to talk to me so that only people I trust " +
                f"can buy my wares. The code is {SecretCode}.", TextMode))

def TatteredMap(RegisteredAdventurer, TextMode):
  if RegisteredAdventurer == True:
    print(GamePrint("You look at the map, but cannot understand a word. You realize you need to see a professional Identifier.", TextMode))
  if RegisteredAdventurer == False:
    print(GamePrint("You look at the map, but cannot understand a word. You keep it in your Inventory for later use.", TextMode))

def DevSword(AtkPwr, Defense, TextMode):
  AtkPwr += 50
  Defense += 50
  print(GamePrint(" + 50 AtkPwr", TextMode))
  print(GamePrint(" + 50 Defense", TextMode))
  print(GamePrint("Your AtkPwr has gone up 50! You deal more damage!", TextMode))
  print(GamePrint("Your Defense has gone up 50! You take less damage!", TextMode))
  print(GamePrint(f"Your AtkPwr is now {AtkPwr}", TextMode))
  print(GamePrint(f"Your Defense is now {Defense}", TextMode))
  return AtkPwr, Defense

def BasicArmor(Defense, TextMode):
  Defense += 1
  print(GamePrint(" + 1 Defense", TextMode))
  print(GamePrint("Your Defense has gone up 1! You take less damage!", TextMode))
  print(GamePrint(f"Your Defense is now {Defense}", TextMode))
  return Defense

def SmallDagger(AtkPwr, TextMode):
  print(GamePrint(" + 1 AtkPwr", TextMode))
  print(GamePrint("Your AtkPwr has gone up 1! You deal more damage!", TextMode))
  print(GamePrint(f"Your AtkPwr is now {AtkPwr}", TextMode))
  return AtkPwr

def RegularArmor(Defense, TextMode):
  Defense += 3
  print(GamePrint(" + 3 Defense", TextMode))
  print(GamePrint("Your Defense has gone up 3! You take less damage!", TextMode))
  print(GamePrint(f"Your Defense is now {Defense}", TextMode))
  return Defense

def RegularDagger(AtkPwr, TextMode):
  AtkPwr += 3
  print(GamePrint(" + 3 AtkPwr", TextMode))
  print(GamePrint("Your AtkPwr has gone up 3! You deal more damage!", TextMode))
  print(GamePrint(f"Your AtkPwr is now {AtkPwr}", TextMode))
  return AtkPwr

def SlimeCore(TextMode):
  print(GamePrint("This is a crafting item, for heavens' sake!", TextMode))

def VialOfSlime(TextMode):
  print(GamePrint("This is a crafting item, for heavens' sake!", TextMode))

def WolfFang(TextMode):
  print(GamePrint("This is a crafting item, for heavens' sake!", TextMode))





def BlacksmithShopElya(Gold, Inventory, Choice, TextMode):
    while True:
            print(GamePrint(f"You have {Gold} Gold.", TextMode))
            if len(Inventory) == 0:
              print(GamePrint("Your Inventory is empty", TextMode))
            else:
              print(GamePrint(f"You have {len(Inventory)} items in your Inventory.", TextMode))
              print(GamePrint(f"Your inventory contains: " + ", ".join(Inventory), TextMode))
            print(GamePrint("----BLACKSMITH WARES----", TextMode))
            print(GamePrint("1. Upgrade-Armor: Defense + 2 - 40 Gold, 2x Slime core, Basic " +
                  "Armor", TextMode))
            print(GamePrint("2. Upgrade-Dagger: AtkPwr +2 - 40 Gold + 1x Wolf fang, Small " +
                  "Dagger", TextMode))
            print(GamePrint("3. Exit", TextMode))
            Choice = GameInput("What would you like to buy? Please put the number. ", TextMode)
            if Choice == "1":
              if "Basic Armor" not in Inventory and Gold < 40 and Inventory.count("Slime Core") < 2:
                print(GamePrint(f"Please get Basic Armor, {40 - Gold} more Gold and " +
                f"{2 - Inventory.count("Slime Core")} more Slime Cores.", TextMode))
              elif "Basic Armor" not in Inventory:
                print(GamePrint("Please come back when you have Basic Armor. I cannot " +
                      "upgrade without it.", TextMode))
              elif Gold < 40:
                print(GamePrint(f"Sorry, you don't have enough for that right now. Please get " +
                f"{40 - Gold} more Gold.", TextMode))
              elif Inventory.count("Slime Core") < 2:
                print(GamePrint(f"Sorry, you don't have enough for that right now. Please get " +
                f"{2 - Inventory.count("Slime Core")} more Slime Core(s).", TextMode))
              else:
                Inventory.append("Regular Armor")
                Inventory.remove("Basic Armor")
                for i in range(2):
                  Inventory.remove("Slime Core")
                print(GamePrint("You have acquired an armor upgrade for your Basic Armor. " +
                    "It has been upgraded to Regular Armor for 40 Gold and 2 " +
                    "Slime Cores.", TextMode))
                Gold -= 40
                print(GamePrint("Basic Armor has been removed from your Inventory.", TextMode))
                print(GamePrint("Regular Armor has been added to your Inventory.", TextMode))
                print(GamePrint("2x Slime cores have been removed from your Inventory.", TextMode))
                print(GamePrint(" - 40 Gold", TextMode))
                print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
            elif Choice == "2":
              if "Small Dagger" not in Inventory and Gold < 40 and Inventory.count("Wolf Fang") < 1:
                print(GamePrint(f"Please get Small Dagger, {40 - Gold} more Gold and " +
                      f"{1 - Inventory.count("Wolf Fang")} more Wolf Fangs.", TextMode))
              elif "Small Dagger" not in Inventory:
                print(GamePrint("Please come back when you have a Small Dagger. I cannot " +
                                "upgrade without it.", TextMode))
              elif Gold < 40:
                print(GamePrint(f"Sorry, you don't have enough for that right now. Please get " +
                f"{40 - Gold} more Gold.", TextMode))
              elif Inventory.count("Wolf Fang") < 1:
                print(GamePrint(f"Sorry, you don't have enough for that right now. Please get " +
                f"{1 - Inventory.count("Wolf fang")} more Wolf Fang(s).", TextMode))
              else:
                Inventory.append("Regular Dagger")
                Inventory.remove("Small Dagger")
                Inventory.remove("Wolf Fang")
                print(GamePrint("You have acquired an armor upgrade for your Small Dagger. " +
                    "It has been upgraded to Regular Dagger for 40 Gold and 1 " +
                    "Wolf Fang.", TextMode))
                Gold -= 40
                print(GamePrint("Small Dagger has been removed from your Inventory.", TextMode))
                print(GamePrint("Regular Dagger has been added to your Inventory.", TextMode))
                print(GamePrint("1x Wolf Fang has been removed from your Inventory.", TextMode))
                print(GamePrint(" - 40 Gold", TextMode))
                print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))

            elif Choice == "3":
              print(GamePrint("You have left the Blacksmith. You no longer need a code to " +
              "enter.", TextMode))
              break
    return Gold, Inventory, TextMode

def ShopElya(Gold, Inventory, Choice, Idx, Name, ShopStock, BasePrice, item, TextMode, Items):
  while True:
    print(GamePrint("----SHOP INVENTORY----", TextMode))
    print(GamePrint(f"You have {Gold} Gold.", TextMode))
    if len(Inventory) == 0 and Gold < 20:
      print(GamePrint("Your Inventory is empty", TextMode))
      break
    else:
      print(GamePrint(f"You have {len(Inventory)} items in your Inventory.", TextMode))
      if len(Inventory) == 0:
        print(GamePrint("Your Inventory is empty.", TextMode))
      else:
        print(GamePrint(f"Your inventory contains: " + ", ".join(Inventory), TextMode))
      print(GamePrint("1. Basic Health Potion: + 10 Health - 20 Gold", TextMode))
      print(GamePrint("2. Basic Armor: Defense + 1 - 50 Gold", TextMode))
      print(GamePrint("3. Small Dagger: AtkPwr + 1 - 50 Gold", TextMode))
      print(GamePrint("4. Dev Sword: + 50 AtkPwr, + 50 Defense - 1000 Gold", TextMode))
      print(GamePrint("5. Sell an item", TextMode))
      print(GamePrint("6. Exit", TextMode))
      Choice = GameInput("What would you like to get? Please choose a number. ", TextMode)
      if Choice == "1":
        if Gold < 20:
          print(GamePrint(f"To buy this, you need {20 - Gold} more Gold.", TextMode))
        else:
          print(GamePrint(" Congratulations on your puchase. No refunds allowed.", TextMode))
          print(GamePrint("You have acquired Basic Health Potion for 20 Gold", TextMode))
          Inventory.append("Basic Health Potion")
          Gold -= 20
          print(GamePrint(" - 20 Gold", TextMode))
          print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
      elif Choice == "2":
        if Gold < 50:
          print(GamePrint(f"Sorry, you don't have enough for that right now. Please get " +
              f"{50 - Gold} Gold.", TextMode))
        else:
          Inventory.append("Basic Armor")
          print(GamePrint("You have acquired Basic Armor for 50 Gold.", TextMode))
          print(GamePrint("Basic Armor has been added to your Inventory.", TextMode))
          Gold -= 50
          print(GamePrint(" - 50 Gold", TextMode))
          print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
      elif Choice == "3":
        if Gold < 50:
          print(GamePrint(f"Sorry, you don't have enough for that right now. Please get " +
              f"{50 - Gold} Gold.", TextMode))
        else:
          Inventory.append("Small Dagger")
          print(GamePrint("You have acquired Small Dagger for 50 Gold.", TextMode))
          print(GamePrint("Small Dagger has been added to your Inventory.", TextMode))
          Gold -= 50
          print(GamePrint(" - 50 Gold", TextMode))
          print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))

      elif Choice == "4":
        if DEV_CODE is not None:
            if Name != "Jacob":
                print("You are not a dev.")
                print("YoU BRouGht ThiS UpoN YouRseLF.")
                Pause(3)
                TextMode = True
            else:
                Code = GameInput("Please enter the dev code. ", TextMode).strip()
                if not Code:  # catches empty input or just spaces/enter
                    print("No code entered. Access denied.")
                    print("YoU BRouGht ThiS UpoN YouRseLF.")
                    TextMode = True
                    Pause(3)
                elif Code == DEV_CODE:
                    if Gold < 1000:
                        print(GamePrint(f"To buy this, you need {1000 - Gold} more Gold."))
                    else:
                        print(GamePrint("Congratulations on your puchase. No refunds allowed.", TextMode))
                        print(GamePrint("You have acquired Dev Sword for 1000 Gold", TextMode))
                        Inventory.append("Dev Sword")
                        Gold -= 1000
                        print(GamePrint(" - 1000 Gold", TextMode))
                        print(GamePrint(f"Your new balance is {Gold} Gold.", TextMode))
                else:
                    print("You are not a dev.")
                    print("YoU BRouGht ThiS UpoN YouRseLF.")
                    TextMode = True
                    Pause(3)
        else:
            print("You are not a dev.")
            print("YoU BRouGht ThiS UpoN YouRseLF.")
            TextMode = True
            Pause(3)
      elif Choice == "5":
        while True:
          print(GamePrint("----INVENTORY----", TextMode))
          for i, item in enumerate(Inventory):
            print(GamePrint(f"{i + 1}. {item}", TextMode))
          print(GamePrint(f"{len(Inventory) + 1}. Exit.", TextMode))
          try:
            Idx = int(GameInput("Which item do you want to sell? Please choose a number. ", TextMode)) - 1
          except ValueError:
            print(GamePrint("Please enter a  number on the screen.", TextMode))
          if Idx == len(Inventory):
            print(GamePrint("you have exited the sell menu.", TextMode))
            break
          elif 0 <= Idx < len(Inventory):
            item = Inventory[Idx]
            Inventory, ShopStock, Gold = SellItem(item, ShopStock, Gold, BasePrice, Inventory, TextMode)
            break
          else:
            print(GamePrint("Invalid Input.", TextMode))
      elif Choice    == "6":
        print(GamePrint("You have exited the shop.", TextMode))
        break
      else:
        print(GamePrint("Please put a number.", TextMode))
  return Gold, Inventory, ShopStock, TextMode

def TavernElya(Gold, Choice, Inventory, MaxHealth, Health, HealthRegenMultiplier,
MaxMana, Mana, ManaRegenMultiplier, AtkPwr, Defense, BuffActive, BuffEndTime, TextMode):
  while True:
    Choice = GameInput("Welcome to the tavern. Would you like to see our menu? "
    "y/n ", TextMode).lower()
    if Choice == "n":
      print(GamePrint("You have left the tavern.", TextMode))
      break
    elif Choice == "y":
      if Gold < 5:
        print(GamePrint("You don't have enough to buy anything.", TextMode))
        print(GamePrint(f"Please come back when you get {5 - Gold} Gold.", TextMode))
        break
      else:
        while True:
          print(GamePrint(f"You have {Gold} Gold.", TextMode))
          PhoenixPrice = (MaxHealth * 5) + 10
          SagePrice = (MaxMana * 5) + 10
          print(GamePrint(f"Your current balance is {Gold} Gold.", TextMode))
          print(GamePrint("----MENU----", TextMode))
          print(GamePrint("1. Water: + 3 Health - 5 Gold", TextMode))
          print(GamePrint("2. Bread: + 3 Mana - 5 Gold", TextMode))
          print(GamePrint("3. Broccoli Cheddar Soup: + 10% Health Regen Rate - 15 Gold", TextMode))
          print(GamePrint("4. Butterbeer: + 10% Mana Regen Rate - 15 Gold", TextMode))
          print(GamePrint(f"5. Phoenix Tears: Heals you to your Max Health - {PhoenixPrice} " +
                f"Gold", TextMode))
          print(GamePrint(f"6. Sage's Secret Stew: Fills you to your Max Mana - {SagePrice} " +
          f"Gold", TextMode))
          print(GamePrint("7. Back to entrance", TextMode))
          Choice = input(GamePrint("What do you choose? Please put the number. ", TextMode)).lower()
          if Choice == "fish and chips":
            Gold, AtkPwr, Defense, BuffActive, BuffEndTime, Inventory = FishAndChipsTavern(Gold,
            AtkPwr, Defense, BuffActive, BuffEndTime,
            Choice, Inventory, TextMode)
          elif Choice == "1":
            if Gold < 5:
              print(GamePrint(f"Please get {5 - Gold} to get this item.", TextMode))
            else:
              Gold, Health, MaxHealth, Inventory = WaterTavern(Gold, Health,
              MaxHealth, Choice, Inventory, TextMode)
          elif Choice == "2":
            if Gold < 5:
              print(GamePrint(f"Please get {5 - Gold} to get this item.", TextMode))
            else:
              Gold, Mana, MaxMana, Inventory = BreadTavern(Gold, Mana, MaxMana,
              Choice, Inventory, TextMode)
          elif Choice == "3":
            if Gold < 15:
              print(GamePrint(f"Please get {15 - Gold} to get this item.", TextMode))
            else:
              Gold, HealthRegenMultiplier, Inventory = BroccoliCheddarSoupTavern(Gold,
              HealthRegenMultiplier, Choice, Inventory, TextMode)
          elif Choice == "4":
            if Gold < 15:
              print(GamePrint(f"Please get {15 - Gold} to get this item.", TextMode))
            else:
              Gold, ManaRegenMultiplier, Inventory = ButterbeerTavern(Gold,
              ManaRegenMultiplier, Choice, Inventory, TextMode)
          elif Choice == "5":
            if "Phoenix Tears" in Inventory:
              print(GamePrint("You still have the Phoenix Tears you bought. Please use it " +
                    " before you can buy another.", TextMode))
            elif Gold < PhoenixPrice:
              print(GamePrint(f"Please get {PhoenixPrice - Gold} to get this item.", TextMode))
            else:
              Gold, Health, MaxHealth, Inventory = PhoenixTearsTavern(Gold,
              Health, MaxHealth, Choice, Inventory, PhoenixPrice, TextMode)
          elif Choice == "6":
            if "Sage's Secret Stew" in Inventory:
              print(GamePrint("You still have the Sage's Secret Stew you bought. Please use " +
              "it before you can buy another.", TextMode))
            elif Gold < SagePrice:
              print(GamePrint(f"Please get {SagePrice  - Gold} to get this item.", TextMode))
            else:
              Gold, Mana, MaxMana, Inventory = SagesSecretStewTavern(Gold, Mana,
              MaxMana, Choice, Inventory, SagePrice, TextMode)
          elif Choice == "7":
            print(GamePrint("You have decided to go back to the front door of the tavern.", TextMode))
            break
    else:
      print(GamePrint("Please input y/n.", TextMode))
      continue
  return (Gold, AtkPwr, Defense, BuffActive, BuffEndTime, Health,
  MaxHealth, HealthRegenMultiplier, Mana, MaxMana, ManaRegenMultiplier,
  Inventory)


def AdventurersGuild(RegisteredAdventurer, Rank, QuestsCompleted, MonstersKilled,
                    TakenStarterQuest, Magic, Gold, Choice, Inventory, AtkPwr, Defense,
                    QuestsActive, TextMode):
  print(GamePrint("----AVALABLE QUESTS----", TextMode))
  if TakenStarterQuest == False:
    GamePrint("1. Deliver 2 Slime Cores to Adventurers Guild - Required Rank 1, Reward: 20 Gold.", TextMode)
    while True:
      Choice = GameInput("Would you like to accept the starter quest of deliver 2 Slime " +
                   "cores to the Adventurers Guild? Reward: 20 Gold. y/n ", TextMode).lower()
      if Choice == "y":
        print(GamePrint("You have accepted the starter quest of deliver 2 Slime " +
                     "cores to the Adventurers Guild for 20 Gold.", TextMode))
        QuestsActive.append("Deliver Slime cores (2) to Adventurers Guild.")
        TakenStarterQuest = True
        break
      elif Choice == "n":
        print(GamePrint("You must accept the starter quest before accepting any others.", TextMode))
        continue
      else:
        print(GamePrint("Please input yes or no.", TextMode))
  else:
    while True:
      print(GamePrint("1. Deliver 1 Vial of Slime to Adventurers Guild - Required Rank 1, Reward: 50 Gold.", TextMode))
      print(GamePrint("2. Deliver 5 Slime cores to Adventurers Guild - Required Rank 1, Reward: 50 Gold.", TextMode))
      print(GamePrint("3. Deliver 3 Wolf Fangs to Adventurers Guild -  Required Rank 2 - 3, Reward: 45 Gold.", TextMode))
      print(GamePrint("4. Exit Quest Hall", TextMode))
      Choice = GameInput("What would you like to accept? please put the number. ", TextMode)
      if Choice == "1":
        print(GamePrint("Menu under construction", TextMode))
      elif Choice == "2":
        print(GamePrint("Menu under construction", TextMode))
      elif Choice == "3":
        print(GamePrint("Menu under construction", TextMode))
      if Choice == "4":
        print(GamePrint("You have exited the Quest Hall.", TextMode))
        break
  return QuestsActive, QuestsCompleted, TakenStarterQuest

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



