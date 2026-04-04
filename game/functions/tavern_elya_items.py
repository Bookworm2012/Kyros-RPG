import time
from .utils import (
                    GamePrint,
                    GameInput
                    )

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
