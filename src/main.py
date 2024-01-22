from aiogram import Bot, executor, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import keyboards as kb
import tools
import re
from models import NewQuestion, NewAnswer, Mailing
from db import Storage
from datetime import datetime
import argparse

parser = argparse.ArgumentParser(
                    prog='Бот поддержки Edwica.ru',
                    description='Нужен для того, чтобы отвечать на вопросы пользователей в телеграм',
                    epilog='Text at the bottom of help')

parser.add_argument("-b", "--bot", required=True, help="Выбери название бота: edwica, openedu, profinansy")
args = parser.parse_args()

config = [cfg for cfg in tools.load_config() if cfg.BotName == args.bot][0]


bot = Bot(config.Token)
dp = Dispatcher(bot, storage=MemoryStorage())
mongoStorage = Storage(db_name=config.MongodbName)
preparedQuestions = mongoStorage.get_questions()
UserCacheCategories = {}
UserCacheEmails = {}
UserTimedMessageCache = {}

class UserQuestion(StatesGroup):
    Email = State()
    New = State()

class AdminMailing(StatesGroup):
    New = State()
    Image = State()


@dp.message_handler(commands=["start"])
async def start_command(msg: types.Message):
    """Админу показываем одни кнопки, а пользователю другие"""

    user_id = msg.from_user.id
    if user_id in tools.ADMINS:
        await msg.answer(text="Приветственное сообщение для админа", reply_markup=kb.get_admin_menu())
    else:
        categories = mongoStorage.get_categories()
        await msg.answer(text="Приветственное сообщение для пользователя", reply_markup=kb.get_users_menu(categories))


@dp.message_handler()
async def text_message_filter(msg: types.Message):
    if msg.from_user.id in config.Admins:
        await admin_message_filter(msg)
    else:
        await user_message_filter(msg)


# ------------------------------------------------------user------------------------------------------------------------------

async def user_message_filter(msg: types.Message):
    if await check_message_is_category(msg):
        # Сценарий, когда пользователь выбрал категорию
        await show_questions_by_category(msg)
    else: 
        # Сценарий, когда пользователь что-то написал (не значение какой-то кнопки)
        await detect_user_email(msg.from_user.id, msg.chat.id)

async def check_message_is_category(msg: types.Message) -> bool:
    """
    Проверяем, что введеное сообщение - это категория
    """
    categories = mongoStorage.get_categories()
    if msg.text.lower() in (i.lower() for i in categories):
        UserCacheCategories[msg.from_user.id] = msg.text.lower()
        return True
    
async def show_questions_by_category(msg: types.Message):
    category = UserCacheCategories[msg.from_user.id]
    if category == "другое":
        await detect_user_email(msg.from_user.id, msg.chat.id)
    
    else:
        questions = mongoStorage.get_questions_by_category(category)
        category_keyboard = kb.get_keyboard_by_category(questions)
        await msg.answer(text=category_keyboard.Text, reply_markup=category_keyboard.Keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("question_"))
async def callback_question(call: types.CallbackQuery):
    """
    Здесь мы показываем зараннее подобранные ответы на вопросы
    """
    if call.message.text.lower() == "другое":
        await detect_user_email(call.from_user.id, call.message.chat.id)
        return
    
    for qst in preparedQuestions:
        if qst.CallbackData == call.data:
            await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
            await bot.send_message(chat_id=call.message.chat.id, text=qst.Answer)
            break

@dp.callback_query_handler(lambda c: c.data.startswith("other_"))
async def callback_other(call: types.CallbackQuery):
    """
    Здесь мы обрабатываем сообщение пользователя, когда он хочет написать свой вопрос
    """
    await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    await detect_user_email(call.from_user.id, call.message.chat.id)

async def detect_user_email(user_id: int, chat_id: int):
    if not mongoStorage.get_user_email(user_id):
        await bot.send_message(chat_id=chat_id, text="Для быстрой помощи, напишите, пожалуйста, почту, использованную при регистрации 📧👍")
        await UserQuestion.Email.set()
    else:
        await bot.send_message(chat_id=chat_id, text="Опишите вашу проблему:")
        await UserQuestion.New.set()

@dp.message_handler(state=UserQuestion.Email)
async def get_new_email_from_user(msg: types.Message, state: FSMContext):
    # Если пользователь ввел неправильную почту, то программа попросит ввести почту заново. И НЕ ОСТАНОВИТСЯ ПОКА НЕ ПОЛУЧИТ НОРМ ПОЧТУ
    if not tools.validate_email(msg.text):
        await bot.send_message(chat_id=msg.chat.id, text=f"Почта [{msg.text}] не прошла валидацию. Попробуйте снова внимательно ввести вашу почту без ничего лишнего")
        await UserQuestion.Email.set()
        return

    UserCacheEmails[msg.from_user.id] = msg.text
    await bot.send_message(chat_id=msg.chat.id, text="Опишите вашу проблему:")
    await UserQuestion.New.set()

@dp.message_handler(state=UserQuestion.New)
async def process_new_user_question(msg: types.Message, state: FSMContext):
    # Сохраняем любое сообщение 
    user_id = msg.from_user.id
    question = NewQuestion(
        Id=0,
        FirstName=msg.from_user.first_name,
        UserId=user_id,
        UserName=msg.from_user.username,
        Question=msg.text,
        Category=UserCacheCategories[user_id] if user_id in UserCacheCategories else "другое",
        Email=UserCacheEmails[msg.from_user.id] if user_id in UserCacheEmails else mongoStorage.get_user_email(user_id)

    )
    question_id = mongoStorage.save_new_question(question)
    timed_message = await msg.answer("Ваш запрос отправлен администратору и будет рассмотрен в ближайшее время. Ответ придет в чат. Спасибо за обращение!")
    UserTimedMessageCache[msg.from_user.id] = timed_message.message_id
    await send_new_question_to_admins(question_id, question)
    await state.finish()


async def send_answer_to_user(question_id: int):
    answer = mongoStorage.get_answer_by_question_id(question_id)
    if not answer:
        return
    if answer.UserId in UserTimedMessageCache:
        await bot.delete_message(chat_id=answer.UserId, message_id=UserTimedMessageCache[answer.UserId])
        del UserTimedMessageCache[answer.UserId]

    msg = f"{answer.UserName}, мы обработали ваш запрос: {answer.Question}\nГотовы предоставить ответ: {answer.Text}."
    keyboard = kb.get_rate_answer_keyboard(question_id)
    await bot.send_message(chat_id=answer.UserId, text=msg, reply_markup=keyboard)


@dp.callback_query_handler(lambda c: "like" in c.data)
async def rate_answer(call: types.CallbackQuery):
    rate, question_id = call.data.split("_") # делим по символу '_' тк нам придет такая строка 'dislike_1' или 'like_1214'
    if rate == "like":
        mongoStorage.mark_answer_as_correct(int(question_id))
        print("Ответ понравился")
        await bot.send_message(chat_id=call.message.chat.id, text="Ваша поддержка мотивирует нас становиться лучше! Спасибо! 🎉")
    else:
        print("Ответ не понравился")
        mongoStorage.mark_answer_as_correct(int(question_id), liked=False)
        await bot.send_message(chat_id=call.message.chat.id, text="Нам жаль, что вы не довольны. Можете ли вы задать свой вопрос еще раз или уточнить, что именно вам не понравилось? 😓")
        await UserQuestion.New.set()

    await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)


@dp.callback_query_handler(lambda c: c.data == "continue_chating")
async def continue_chating(call: types.CallbackQuery):
    await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    await bot.send_message(chat_id=call.message.chat.id, text="Опишите вашу проблему")
    await UserQuestion.New.set()

# ------------------------------------------------------admin------------------------------------------------------------------

async def send_new_question_to_admins(question_id: int, question: NewQuestion = None):
    if not question:
        question = mongoStorage.get_question_by_id(question_id)
    
    message = "\n".join((
        f"⚠️ Новый вопрос от: @{question.UserName}",
        f"id: {question_id}",
        f"👤 Имя пользователя: {question.FirstName}",
        f"💌 Почта: {question.Email}",
        f"Категория: {question.Category}",
        f"❓Вопрос: {question.Question}",
    ))

    for admin in config.Admins:
        await bot.send_message(chat_id=admin, text=message)


async def admin_message_filter(msg: types.Message):
    if msg.reply_to_message:
        await admin_reply_message(msg)
        return
    else:
        await check_message_is_admin_actions(msg)


async def admin_reply_message(msg: types.Message):
    question_text = msg.reply_to_message.text
    try:
        question_id = int(re.findall(r"id: \d+", question_text)[0].replace("id: ", ""))
    except:
        return
    
    closed = mongoStorage.check_question_is_closed(question_id)
    if closed is None:
        await msg.answer("Вопрос был удален из БД")
        return 
    
    if closed:
        answer = mongoStorage.get_admin_answer(question_id)
        await msg.answer(f"На это сообщение уже ответил: @{answer.AdminName}\nВот ответ:{answer.Answer}")
        return



    mongoStorage.save_answer(NewAnswer(
        QuestionId=question_id,
        Answer=msg.text,
        AdminId=msg.from_user.id,
        AdminName=msg.from_user.username,
        Question=question_text
    ))
    await msg.answer("Готово!")
    await send_answer_to_user(question_id)
    await send_notification_to_admins(question_id, ignore_id=msg.from_user.id)


async def send_notification_to_admins(question_id: int, ignore_id: int = 0):
    answer = mongoStorage.get_admin_answer(question_id)
    message = "\n".join((
        f"👤 Админ @{answer.AdminName} ответил на вопрос № {question_id}",
        f"❔ Вопрос: {answer.Question}",
        f"📝 Ответ: {answer.Answer}"
    ))
    for admin in config.Admins:
        if admin == ignore_id: continue
        await bot.send_message(chat_id=admin, text=message)


async def check_message_is_admin_actions(msg: types.Message):
    action = msg.text.lower()
    if action == "статистика":
        stat = mongoStorage.get_statistics()
        categories_stat = "\n".join((f"{i.Category}: {i.Count}" for i in stat.CategoryStat))
        admins_stat = "\n\n".join((f"Админ: {i.UserName}\nЛайков: {i.Likes}\nДизлайков: {i.Dislikes}\nБез оценки: {i.WithoutRate}" for i in stat.AdminStat))

        message = "\n".join((
            f"Количество пользователей: {stat.UsersCount}",
            f"Закрытых ответов: {stat.ClosedCount}",
            f"Открытых ответов: {stat.OpenedCount}",
            f"\nОбращения по категориям:\n{categories_stat}",
            f"\nСтатистика админов:\n{admins_stat}"

        ))
        await msg.answer(message)
    elif action == "сделать рассылку":
        await msg.answer("Напишите текст рассылки:")
        await AdminMailing.New.set()

    elif action == "непрочитанные сообщения":
        await send_open_question_to_admin(msg.chat.id)


async def send_open_question_to_admin(chat_id: int):
    questions = mongoStorage.get_open_requests()
    if not questions:
        await bot.send_message(chat_id=chat_id, text="Нет непрочитанных сообщений")
        return
    for qst in questions:
        text = "\n".join((
                f"id: {qst.Id}",
                f"👤 Имя пользователя: {qst.FirstName}",
                f"💌 Почта: {qst.Email}",
                f"Категория: {qst.Category}",
                f"❓Вопрос: {qst.Question}",
            ))
        await bot.send_message(chat_id, text)



@dp.message_handler(state=AdminMailing.New)
async def new_mailing(msg: types.Message, state: FSMContext):
    await msg.answer(text=msg.text, reply_markup=kb.get_mailing_keyboard())
    await bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
    await state.finish()

@dp.callback_query_handler(lambda c: "mailing" in c.data)
async def process_mailing(call: types.CallbackQuery):
    if call.data == "edit_mailing":
        await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        await AdminMailing.New.set()
    
    elif call.data == "send_mailing":
        users = mongoStorage.get_all_users()
        for user in users:
            await bot.send_message(chat_id=user, text=call.message.text)
        
        await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        await bot.send_message(chat_id=call.from_user.id, text="Отправлено!")
        mongoStorage.save_mailing(Mailing(
            AdminId=call.from_user.id,
            AdminUser=call.from_user.username,
            Text=call.message.text,
            Date=datetime.now(),
            Views=len(mongoStorage.get_all_users())
        ))
    else:
        await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        await bot.send_message(chat_id=call.from_user.id, text="Рассылки не будет")



if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)