from dotenv import load_dotenv
import os
from ...utils import (
                        GamePrint,
                        GameInput,
                        Pause,
                        SellItem
                        )

current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, 'functions', 'buildings', '.env')

load_dotenv(dotenv_path)
DEV_CODE = os.getenv("KYROS_DEV_CODE")


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