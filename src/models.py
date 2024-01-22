from typing import NamedTuple
from aiogram.types import InlineKeyboardButton
from dataclasses import dataclass

class PreparedQuestion(NamedTuple):
    Text: str
    Answer: str
    Category: str
    CallbackData: str


class CategoryKeyboard(NamedTuple):
    Text: str
    Keyboard: InlineKeyboardButton

class NewQuestion(NamedTuple):
    Id: int
    UserId: int
    UserName: str
    FirstName: str
    Question: str
    Category: str
    Email: str


class NewAnswer(NamedTuple):
    AdminName: str
    AdminId: int
    QuestionId: int
    Question: str
    Answer: str

class Mailing(NamedTuple):
    AdminId: int
    AdminUser: str
    Text: str
    Date: str
    Views: int


class Answer(NamedTuple):
    Id: int
    UserId: int
    UserName: str
    Text: str
    Question: str

class CategoryStat(NamedTuple):
    Category: str
    Count: int

@dataclass(slots=True)
class AdminStat:
    UserName: str
    Likes: int
    Dislikes: int
    WithoutRate: int
    
class Statistic(NamedTuple):
    UsersCount: int
    ClosedCount: int
    OpenedCount: int
    CategoryStat: list[CategoryStat]
    AdminStat: list[AdminStat]

