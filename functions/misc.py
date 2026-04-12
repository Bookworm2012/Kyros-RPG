from .utils import (
                    Pause
                    )

from dotenv import load_dotenv
import os

load_dotenv()  # reads .env file
DEV_CODE = os.getenv("KYROS_DEV_CODE")


def IntroText():
  print("///////////////")
  print("///////////////")
  print("///////////////")
  print("Welcome to this text RPG. You will be dropped in a town square. It is up to" +
     " you to decide what to do.")
  print("///////////////")
  print("///////////////")
  print("///////////////")
  print("///////////////")
  print("World Loading . . . ")
  print("10% . . . ")
  Pause(0.5)
  print("35% . . . ")
  Pause(0.5)
  print("50% . . . ")
  Pause(0.5)
  print("70% . . . ")
  Pause(0.5)
  print("99% . . . ")
  Pause(0.5)
  print("100% . . .")
  Pause(0.5)
  print("Loading Complete")# Lines 29 - 39 are intro text



















