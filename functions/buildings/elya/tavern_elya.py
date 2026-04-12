from ...utils import (
                        GamePrint,
                        GameInput
                        )
from ...tavern_elya_items import (
                                    FishAndChipsTavern,
                                    WaterTavern,
                                    BreadTavern,
                                    ButterbeerTavern,
                                    BroccoliCheddarSoupTavern,
                                    PhoenixTearsTavern,
                                    SagesSecretStewTavern
                                    )

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