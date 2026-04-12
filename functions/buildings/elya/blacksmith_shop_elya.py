from ...utils import (
                        GamePrint,
                        GameInput
                        )

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