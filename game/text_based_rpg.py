import RPG_funct as funct
import random # Lets me generate random numbers
import time # Lets me check time
from dotenv import load_dotenv
import os


load_dotenv()
DEV_CODE = os.getenv("KYROS_DEV_CODE")
TextMode = None
Text = None
Random = ""
BlacksmithUnlocked = False # Checks if you can get to blacksmith without code
DisplayedMessage = False
RegisteredAdventurer = False
ForestDiscovered = False
FoundBones = 0
MaxHealth = 10 # Maximum health of the player
Health = 10 # Current health of the player
HealthRegen =  int(MaxHealth * 0.1)  # Rate at which the player heals
HealthAdded = 0
HealthRegenMultiplier = 1
MonsterHealth = 0 # The current monster health
MaxMana = 10 # Maximum mana of the player
Mana = 10 # Current mana of the player
ManaRegen =  int(MaxMana * 0.1) # Rate at which the player regenerates mana
ManaRegenMultiplier = 1
ManaAdded = 0
LastRegenTime = time.time()
BuffActive = False
BuffEndTime = 0
Consumables = {"Elya": ["Basic Health Potion", "Fish and Chips", "Phoenix Tears",
                        "Sage's Secret Stew", "Butterbeer", "Broccoli Cheddar Soup",
                        "Bread", "Water", "Mysterious Letter",
                        "Tattered Map"]
              }# Has all consumable items in the game
UnlockorCraft = {"Elya": ["Slime Core", "Vial of Slime", "Wolf Fang", "Mysterious Letter", "Tattered Map"]
                }
item = None
Inventory = [] # Contain items
Equipped = [] #  Contains equipped items
CodeInput = None # The code that you give the Blacksmith
SecretCode = None # Correct Blacksmith Code
PhoenixPrice = (MaxHealth * 5) + 10 # Price of Phoenix Tears
SagePrice = (MaxMana * 5) + 10 # Price of Sage's Secret
MonstersKilled = 0 # Tracks Monsters killed for missions.
Rank = "" # Rank in the Adventurers guild
TakenStarterQuest = False
QuestsActive = []
QuestsCompleted = 0 # Missions completed.
Gold = 0 # Used to purchase stuff
Race = "human" # Added this for later functionality of race changes
Magic = [] # Set of avalible spells
AtkPwr = 5 # Base attack power if enemy has 0 defense
Defense = 2 # Damaged blocked from incoming attacks
SlimeStats = {"SlimeAtkPwr": random.randint(4, 7),
              "SlimeDefense": 0,
              "SlimeHealth": random.randint(12, 16)
            }
# SlimeLoot key: Item, quantity, 1 in x chance
SlimeLoot = [("Slime Core", 2, 2), ("Vial of Slime", 1, 5), ("Mysterious Letter", 1, 10)]
MonsterAtkPwr = 0 # Attack power of a monster
MonsterDefense = 0 # Defense of a monster
Name = "" # What the player will be called
Location = "" # Where the player chooses to go
Choice = "" # able to view inventory or attack, other functionalities added later
Idx = 0
Items = ["Slime Core", "Vial of Slime", "Wolf Fang", "Tattered Map", "Dev Sword",
        "Basic Armor", "Regular Armor", "Basic Dagger", "Regular Dagger"]
ShopStock = {
              "Slime Core": random.randint(0, 15,),
              "Vial of Slime":random.randint(0, 10),
              "Wolf Fang": random.randint(0, 10),
              "Tattered Map": random.randint(0, 10),
              "Dev Sword": random.randint(0, 10),
              "Basic Armor": random.randint(0, 10),
              "Regular Armor": random.randint(0, 5),
              "Basic Dagger": random.randint(0, 10),
              "Regular Dagger": random.randint(0, 5)
}
BasePrice = {
            "Slime Core": 10,
            "Vial of Slime": 25,
            "Wolf Fang": 15,
            "Tattered Map": 50,
            "Dev Sword": 1000,
            "Basic Armor": 30,
            "Regular Armor": 50,
            "Basic Dagger": 20,
            "Regular Dagger": 40
            }

Banned = ["monty", "cj"]






funct.IntroText()
Name = funct.AskName(Name, TextMode)
TextMode = (Name.lower() in Banned)
if Name in Banned:
    print("YoU BRouGht ThiS UpoN YouRseLF.")
print(funct.GamePrint(f"Welcome, {Name}, to the world of Kyros and to the town of Elya!", TextMode))
print("You open your eyes and look around. ")
while True:
  LastRegenTime, Health, Mana = funct.RegenerationCode(LastRegenTime,
    MaxHealth, Health, HealthRegenMultiplier,
    Mana, MaxMana, ManaRegenMultiplier, TextMode)
  if BuffActive == True and time.time() > BuffEndTime:
    print("The effect of the fish and chips has worn off! Stats return to normal.")
    print(" - 2 AtkPwr")
    AtkPwr -= 2
    print(" - 2 Defense")
    Defense -= 2
    print(f"Your current AtkPwr is {AtkPwr}")
    print(f"Your current Defense is {Defense}")
    BuffActive = False
  # Makes this loop run forever, or until exit is typed, so the player goes back to
  # lines 47 - 49
  print("You see a field (f), a shop (s), a blacksmith (b) " +
", a tavern (t), and an adventurers guild branch (a). ")
  if Inventory != [] or Equipped != []:
    print("You can also see the items in your Inventory (i), ")
  if Magic != []:
    print("You can also see your known spells (s).")
  print("You may also exit (exit).")
  print(f"Health: {Health}/{MaxHealth} | Gold: {Gold}")
  Location = input("Where would you like to go? Just input the letter " +
  "").lower()
  if Location == "money":
    if DEV_CODE is not None:
        if Name == "Jacob":
            Code = input("Enter the dev code. ").strip()
            if not Code:  # catches empty input or just spaces/enter
                print("No code entered. Access denied.")
                print("YoU BRouGht ThiS UpoN YouRseLF.")
                TextMode = True
                funct.Pause(3)
            elif Code == DEV_CODE:
                Gold += 1000
                print(" + 1000 gold!")
                print(f"Your current balance is {Gold} gold.")
            else:
                print("You are not a dev.")
                print("YoU BRouGht ThiS UpoN YouRseLF.")
                TextMode = True
                funct.Pause(3)
        else:
            print("You are not a dev.")
            print("YoU BRouGht ThiS UpoN YouRseLF.")
            TextMode = True
            funct.Pause(3)
    else:
        print("You are not a dev.")
        print("YoU BRouGht ThiS UpoN YouRseLF.")
        TextMode = True
        funct.Pause(3)
  elif Location == "f": # Code for the field
    Random = random.randint(1, 100)
    if Random <= 15  and "Tattered Map" not in Inventory and ForestDiscovered == False and FoundBones < 5:
      # make 0% = <= 15.
      print("While exploring, you come across a pile of bones. You open the satchel on the bones, and find " +
            "a Tattered Map, 2 Slime Cores, and 50 Gold.")
      print("Tattered Map added to your Inventory. Slime Core x 2 added to Your Inventory.")
      print(" + 50 Gold")
      Inventory.append("Tattered Map")
      for i in range(2):
        Inventory.append("Slime Core")
      Gold += 50
      print(f"Your new balance is {Gold} Gold.")
      FoundBones +=  1
      continue
    SlimeStats["SlimeHealth"] = random.randint(12, 16)
    SlimeStats["SlimeAtkPwr"] = random.randint(4, 7)
    SlimeStats["SlimeDefense"] = 0
    print("You have chosen to go to the field. Good luck!")
    print("You hear a rustling in the grass. A slime appears.")
    while SlimeStats["SlimeHealth"] > 0 and Health > 0:

      print(f"Slime Health: {SlimeStats['SlimeHealth']} | Your Health: {Health}")
      Choice = input("Do you attack (a), use an item (i), or retreat (r)? ").lower()
    # Asking if you want to begin fighting the slime, or use an item or retreat
      if  Choice == "a":
        YourTotalDmgDealt, SlimeStats["SlimeHealth"] = funct.PerformAttack(
                                                        AtkPwr,
                                                        SlimeStats["SlimeDefense"],
                                                        SlimeStats["SlimeHealth"]
)
        print(f"You have dealt {YourTotalDmgDealt} damage to Slime. ")
#lines 70 and 72 say how much damage you did to the slime and how much hp it has left
        funct.Pause(0.5)
        print(f"Slime health: {SlimeStats['SlimeHealth']}")
        print("---------------")
        if SlimeStats["SlimeHealth"] <= 0: # Victory condition
          print("Victory! You have defeated the Slime!")
          print("---------------")
          Gold += 10 # Gives you 10 gold
          print(" + 10 gold!")
          print(f"Your current balance is {Gold} gold.")
          print(f"Your current health is {Health} health.")
          funct.Pause(0.5)
          Inventory, Gold = funct.LootEnemy(
                                        SlimeLoot,
                                        Inventory,
                                        Gold
                                        )
          Random = random.randint(1,10)
          if "Mysterious Letter" in Inventory and BlacksmithUnlocked == False and DisplayedMessage == False:
            DisplayedMessage = True
            SecretCode = random.randint(1000,9999)
            print("You have obtained a Mysterious Letter")
            print(f"You read the letter: It says, Dear Residents of Elya. You must ")
            funct.Pause(0.5)
            print(f"tell me the code to talk to me so that only people I trust ")
            funct.Pause(0.5)
            print(f"can buy my wares. The code is {SecretCode}.")
          if Health < MaxHealth:
            print("Visit the tavern to regain health before heading out again.")
          break
        (MonsterTotalDmgDealt, Health) = funct.PerformAttack(
                                                        SlimeStats["SlimeAtkPwr"],
                                                        Defense,
                                                        Health
                                                        )
        print(f"Slime hits you with Slime Shot for {MonsterTotalDmgDealt} damage. ")
        funct.Pause(0.5)
        print(f" Your health: {Health}")
        print("---------------")
        if Health <= 0:
          print("You Died.")
          print("---------------")
          Inventory = [] # Lose all items in inventory
          Equipped = []
          print("Emptying Inventory . . .  Inventory Emptied")
          print("Unequipping Items . . . Items Unequipped")
          print(f" - {round(Gold * 0.5)} gold.")
          Gold = round(Gold * 0.5) # Lose half your gold
          print(f"Your current balance is {Gold} Gold.")
          Health = MaxHealth # Fully heals the player
          Mana = MaxMana
          break
      elif Choice == "i":
        (Inventory, Equipped, AtkPwr, Defense, MaxMana, Mana,
  ManaRegenMultiplier, Health, MaxHealth, HealthRegenMultiplier, BuffActive,
  BuffEndTime) = funct.InventoryMenu(Idx, Choice, Inventory,
                                Equipped, Mana, MaxMana,
                                ManaRegenMultiplier, Health, MaxHealth,
                                HealthRegenMultiplier, AtkPwr, Defense,
                                BuffActive, BuffEndTime, Consumables,
                                UnlockorCraft, TextMode, SecretCode,
                                RegisteredAdventurer
                                )
      elif Choice == "r":
          print("You feel that the slime is too strong for you. You retreat back to " +
              "town.")
          break




  elif Location == "s":
    if len(Inventory) != 0:
      print("Come in, Come in! Here are our fine wares:")
      Gold, Inventory, ShopStock, TextMode = funct.ShopElya(Gold, Inventory, Choice, Idx,
      Name, ShopStock, BasePrice, item, TextMode, Items)
    elif Gold < 20:
      print(f"You don't have even enough for the least expensive "
        f"thing here! Come back when you get {20 - Gold} more gold.")
    elif Gold >= 20:
      print("Come in, Come in! Here are our fine wares:")
      Gold, Inventory, ShopStock, TextMode = funct.ShopElya(Gold, Inventory, Choice, Idx,
      Name, ShopStock, BasePrice, item, TextMode, Items)

  elif Location == "b":
    if BlacksmithUnlocked == True:
            Gold, Inventory, TextMode = funct.BlacksmithShopElya(Gold, Inventory, Choice, TextMode)

    if BlacksmithUnlocked == False and "Mysterious Letter" not in Inventory:
      Random = random.randint(1,3)
      if (Random == 2 or Random == 3) and "Mysterious Letter" not in Inventory:
        print("Go away. I want to be left alone.")
      elif Random == 1 and "Mysterious Letter" not in Inventory:
        print("Do you have the code? If not, then go away.")
    if "Mysterious Letter" in Inventory:
      CodeInput = input("Please input the code on the Mysterious Letter. ")
      if str(SecretCode) == CodeInput:
        print("You have the code, so you are able to buy my wares." +
        " You are also now a trusted friend.")
        print("Take a look around.")
        BlacksmithUnlocked = True
        Inventory.remove("Mysterious Letter")
        Gold, Inventory = funct.BlacksmithShopElya(Gold, Inventory, Choice)

  elif Location == "t":
    (Gold, AtkPwr, Defense, BuffActive, BuffEndTime, Health,
    MaxHealth, HealthRegenMultiplier, Mana, MaxMana, ManaRegenMultiplier,
    Inventory) = funct.TavernElya(Gold, Choice, Inventory, MaxHealth, Health,
    HealthRegenMultiplier, MaxMana, Mana, ManaRegenMultiplier, AtkPwr, Defense,
    BuffActive, BuffEndTime, TextMode)

  elif Location == "a":
    if RegisteredAdventurer == True:
      print("You walk into the building and immediatly head to the quests room.")
      QuestsActive, QuestsCompleted, TakenStarterQuest = funct.AdventurersGuild(RegisteredAdventurer,
      Rank, QuestsCompleted, MonstersKilled, TakenStarterQuest, Magic, Gold,
      Choice, Inventory, AtkPwr, Defense, QuestsActive, TextMode)
    else:
      while True:
        Choice = input("Hello! Would you like to register with the guild? y/n ").lower()
        if Choice == "y":
          Choice = input("Are you sure? There is a one time fee of 50 Gold. y/n ").lower()
          if Choice == "y":
            if Gold < 50:
              print(f"Come back when you get {50 - Gold } more Gold.")
              break
            else:
              print("Please give me the Gold . . . ")
              Gold -= 50
              print(" - 50 Gold")
              print(f"Your new balance is {Gold} Gold.")
              print("Great! Let me just get you this card here . . . ")
              print("You will be Rank 1 to start, but you can upgrade that by " +
                    "completing missions and proving you have the required Attack " +
                    "and Defense. ")
              Rank = 1
              RegisteredAdventurer = True
              print("Rank upgraded to 1!")
              print("Please go down that hall and someone will teach you a spell.")
              print("Hi, you need to be taught Insect? Yes? ")
              print("Well, you just have to concentrate. No, not enough, CONCENTRATE. CONCENTRATE!!!!")
              Magic.append("Inspect")
              print("Inspect added to your magic!")
              print("Ah, now that you know inspect, you should accept a quest. The " +
              "Quest Hall is just across the, well, hall.")
              print("You walk across the hall and into a room full of paper. " +
                    "'10 slime cores needed!' . . . 'Personal quest: '" +
                    "Deliver 1 wolf fang to Guild: 10 Gold' until you see a " +
                    "piece of paper with all available quests on it.")
              QuestsActive, QuestsCompleted, TakenStarterQuest = funct.AdventurersGuild(RegisteredAdventurer,
              Rank, QuestsCompleted, MonstersKilled, TakenStarterQuest, Magic, Gold,
              Choice, Inventory, AtkPwr, Defense, QuestsActive, TextMode)
              break


          elif Choice == "n":
            print("Alrighty, but you can come back any time.")
            break
          else:
            print("Please enter yes or no.")
        elif Choice == "n":
          print("Alrighty, but you can come back any time.")
          break
        else:
          print("Please enter yes or no.")
  elif Location == "i":
    (Inventory, Equipped, AtkPwr, Defense, MaxMana, Mana,
  ManaRegenMultiplier, Health, MaxHealth, HealthRegenMultiplier, BuffActive,
  BuffEndTime) = funct.InventoryMenu(Idx, Choice, Inventory, Equipped,
                            Mana, MaxMana, ManaRegenMultiplier, Health,
                            MaxHealth, HealthRegenMultiplier, AtkPwr, Defense,
                            BuffActive, BuffEndTime, Consumables, UnlockorCraft,
                            TextMode, SecretCode, RegisteredAdventurer
                            )



  elif Location == "exit":
    print("You have exited Kyros. The items in your inventory will be scattered " +
         "across the earth, and your gold will be given to the people.")
    break
  else:
    print("Invalid location: Please try again.")






