from typing import NamedTuple
from aiogram.types import InlineKeyboardMarkup
from dataclasses import dataclass
from datetime import datetime


class PreparedQuestion(NamedTuple):
    """
    Это структура подготовленного ответа. Который включает в себя заранее подобранный вопрос и ответ.
    CallbackData позволяет правильно идентифицировать кнопку по нажатию.
    """

    Text: str
    Answer: str
    Category: str
    CallbackData: str

class CategoryKeyboard(NamedTuple):
    """
    Структура, которая включает в себя текст и клавиатуру, которая должна идти вместе с этим текстом
    Созданием этой структуры послужило то, что текст вопросов в inline-кнопки не помещался, поэтому пришлось пойти на такой копромисс
    """

    Text: str
    Keyboard: InlineKeyboardMarkup

class Question(NamedTuple):
    """Структура вопроса, который заполняется пользователем, если он захочет написать в поддержку.\n"""

    Id: int
    UserId: int
    UserName: str
    FirstName: str
    Question: str
    Category: str
    Email: str
    Date: datetime

class Mailing(NamedTuple):
    """Структура рассылки. Поле picture может быть опущено. """

    AdminId: int
    AdminUser: str
    Text: str
    Date: datetime
    Views: int
    Picture: str


class Answer(NamedTuple):
    """Структура ответа администратора"""

    Id: int
    UserId: int
    AdminId: int
    AdminName: str
    UserName: str
    Text: str
    Question: str

class CategoryStat(NamedTuple):
    """Структура статистики по категории"""

    Category: str
    Count: int

@dataclass(slots=True)
class AdminStat:
    """Структура статистики по админам"""

    UserName: str
    Likes: int
    Dislikes: int
    WithoutRate: int

class Statistic(NamedTuple):
    """Структура статистики по запросам"""

    UsersCount: int
    ClosedCount: int
    OpenedCount: int
    CategoryStat: list[CategoryStat]
    AdminStat: list[AdminStat]
