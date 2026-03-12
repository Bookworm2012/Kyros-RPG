import time
from .utils import (
                    GamePrint,
                    )

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