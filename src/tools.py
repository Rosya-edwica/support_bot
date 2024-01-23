import re
import json

from typing import NamedTuple


NUMBERS_EMOGIES = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}

class Config(NamedTuple):
    BotName: str
    Token: str
    MongodbName: str
    StartMessage: str


def load_config() -> list[Config]:
    with open("config.json", encoding="utf-8", mode="r") as f:
        data = json.load(f)
    res = []
    for i in data["bots"]:
        res.append(Config(
            BotName=i["name"],
            Token=i["token"],
            MongodbName=i["mongodb_name"],
            StartMessage=i["start_message"],
        ))
    return res



def validate_email(email: str):
    pattern = "^((?!\.)[\w\-_.]*[^.])(@\w+)(\.\w+(\.\w+)?[^.\W])$"
    if re.findall(pattern, email):
        return True
    else:
        return False