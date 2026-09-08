
class Race:

    def __init__(self, race, stat_variation, abilities):
        self.race = race
        self.stat_variation = stat_variation
        self.racia_abilities = abilities

human = Race("human",
    {
        "STR": [2, 5],
        "AGI": [2, 5],
        "DEX": [2, 5],
        "CON": [2, 5],
        "PER": [2, 5],
        "INT": [2, 5],
        "WIS": [2, 5],
        "WIL": [2, 5],
        "CHA": [3, 6],
        "LUCK": [5, 8]
    },
    ["Fast learning"]
    )

elf = Race("elf",
    {
        "STR": [1, 4],
        "AGI": [5, 8],
        "DEX": [4, 7],
        "VIT": [1, 4],
        "CON": [0, 3],
        "PER": [3, 6],
        "INT": [4, 7],
        "WIS": [3, 6],
        "WIL": [2, 5],
        "CHA": [6, 9],
        "LUCK": [2, 5]
    },
    ["Dark vision"]
    )

dwarf = Race("dwarf",
    {
        "": [4, 7],
        "AGI": [0, 3],
        "DEX": [1, 4],
        "VIT": [4, 7],
        "CON": [5, 8],
        "PER": [2, 5],
        "INT": [1, 4],
        "WIS": [2, 5],
        "WIL": [3, 6],
        "CHA": [1, 4],
        "LUCK": [2, 5],
    },
    ["Crafting intuition"]
    )

orc = Race("orc",
    {
        "STR": [5, 8],
        "AGI": [1, 4],
        "DEX": [1, 4],
        "VIT": [4, 7],
        "CON": [4, 7],
        "PER": [0, 3],
        "INT": [0, 3],
        "WIS": [0, 3],
        "WIL": [2, 5],
        "CHA": [0, 3],
        "LUCK": [1, 4],
    },
    ["Berserk strength"]
    )

twiceborn = Race("twiceborn",
    {
        "STR": [3, 6],
        "AGI": [1, 4],
        "DEX": [2, 5],
        "VIT": [4, 7],
        "CON": [3, 6],
        "PER": [2, 5],
        "INT": [2, 5],
        "WIS": [1, 4],
        "WIL": [5, 8],
        "CHA": [0, 2],
        "LUCK": [0, 3],
    },
    ["Blight"]
    )

reptilian = Race("reptilian",
    {
        "STR": [4, 7],
        "AGI": [2, 5],
        "DEX": [3, 6],
        "VIT": [4, 7],
        "CON": [5, 8],
        "PER": [3, 6],
        "INT": [1, 4],
        "WIS": [2, 5],
        "WIL": [3, 6],
        "CHA": [1, 4],
        "LUCK": [2, 5],
    },
    [""]
    )

lupine = Race("lupine",
    {
        "STR": [3, 6],
        "AGI": [5, 8],
        "DEX": [4, 7],
        "VIT": [3, 6],
        "CON": [2, 5],
        "PER": [5, 8],
        "INT": [2, 5],
        "WIS": [2, 5],
        "WIL": [1, 4],
        "CHA": [3, 6],
        "LUCK": [2, 5],
    },
    [""]
    )

avian = Race("avian",
    {
        "STR": [1, 4],
        "AGI": [4, 7],
        "DEX": [5, 8],
        "VIT": [2, 5],
        "CON": [1, 4],
        "PER": [5, 8],
        "INT": [2, 5],
        "WIS": [4, 7],
        "WIL": [2, 5],
        "CHA": [3, 6],
        "LUCK": [2, 5],
    },
    [""]
    )

draconian = Race("draconian",
    {
        "STR": [5, 8],
        "AGI": [2, 5],
        "DEX": [2, 5],
        "VIT": [4, 7],
        "CON": [5, 8],
        "PER": [3, 6],
        "INT": [3, 6],
        "WIS": [2, 5],
        "WIL": [4, 7],
        "CHA": [3, 6],
        "LUCK": [2, 5]
    },
    [""]
    )

dragon = Race("dragon",
    {
        "STR": [6, 9],
        "AGI": [3, 6],
        "DEX": [1, 4],
        "VIT": [5, 8],
        "CON": [6, 9],
        "PER": [4, 7],
        "INT": [5, 8],
        "WIS": [4, 7],
        "WIL": [5, 8],
        "CHA": [2, 5],
        "LUCK": [1, 4]
    },
    [""]
    )
