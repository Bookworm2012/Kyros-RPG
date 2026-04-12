from ...utils import (
                        GamePrint,
                        GameInput
                    )
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




