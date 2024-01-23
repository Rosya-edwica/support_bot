from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from tools import  NUMBERS_EMOGIES
from models import PreparedQuestion, CategoryKeyboard


def get_users_menu(categories: list[str]) -> ReplyKeyboardMarkup:
    menu = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    for i in categories:
        btn = KeyboardButton(text=i)
        menu.add(btn)
    return menu


def get_admin_menu() -> ReplyKeyboardMarkup:
    menu = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    text_list = (
        "Сделать рассылку",
        "Рассылка с картинкой",
        "Статистика",
        "Непрочитанные сообщения"
    )
    for i in text_list:
        btn = KeyboardButton(text=i)
        menu.add(btn)
    return menu
 

def get_keyboard_by_category(questions: list[PreparedQuestion]) -> CategoryKeyboard:
    if questions[0].Category == "другое":
        return []

    questions_text = []
    menu = InlineKeyboardMarkup(row_width=3)
    for i, qst in enumerate(questions, start=1):
        btn = InlineKeyboardButton(text=NUMBERS_EMOGIES[i], callback_data=qst.CallbackData)
        questions_text.append(f"{NUMBERS_EMOGIES[i]} {qst.Text}")
        menu.insert(btn)

    return CategoryKeyboard(
        Text="\n".join(questions_text),
        Keyboard=menu
    )


def get_rate_answer_keyboard(question_id: int) -> InlineKeyboardMarkup:
    menu = InlineKeyboardMarkup(row_width=2)
    like = InlineKeyboardButton(text="👍", callback_data=f"like_{question_id}")
    dislike = InlineKeyboardButton(text="👎", callback_data=f"dislike_{question_id}")
    continue_btn = InlineKeyboardButton(text="Задать вопрос 🗣️", callback_data="continue_chating")
    menu.insert(like)
    menu.insert(dislike)
    menu.insert(continue_btn)
    return menu


def get_mailing_keyboard() -> InlineKeyboardMarkup:
    menu = InlineKeyboardMarkup(row_width=2)
    cancel = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mailing")
    send = InlineKeyboardButton(text="✅ Разослать", callback_data="send_mailing")
    menu.insert(cancel)
    menu.insert(send)
    return menu

def get_mailing_img_keyboard() -> InlineKeyboardMarkup:
    menu = InlineKeyboardMarkup(row_width=2)
    cancel = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_img")
    send = InlineKeyboardButton(text="✅ Разослать", callback_data="send_img")
    menu.insert(cancel)
    menu.insert(send)
    return menu


def get_next_open_question(id: int = 0) -> InlineKeyboardMarkup:
    menu = InlineKeyboardMarkup(row_width=2)
    next_qst = InlineKeyboardButton(text="Следующий вопрос", callback_data=f"next_question_{id}")

    menu.insert(next_qst)
    return menu 