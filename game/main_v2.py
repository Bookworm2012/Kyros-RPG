from races import (
    Race,
    human,
    elf,
    dwarf,
    orc,
    twiceborn,
    reptilian,
    lupine,
    avian,
    draconian,
    dragon
    )
from entity import (
    Character,
    Player
    )
player1 = Player(human)

print("Display status? Y/N")
while True:
    display = input(">>> ")
    display = display.lower()
    if display == "y":
        Player.display_status(player1)
        break
    elif display == "n":
        print("Continuing . . . ")
        break
    else:
        print("You didn't type Y/N.")


