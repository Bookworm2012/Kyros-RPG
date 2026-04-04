from .utils import (
                    GamePrint,
                    GameInput,
                    EquipItem,
                    UnequipItem,
                    )

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
