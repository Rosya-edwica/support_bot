from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram import Bot, executor, Dispatcher, types
from datetime import datetime
import keyboards as kb
import argparse
import re
import os

from db import Storage
from models import Question, Answer, Mailing
import tools
import locale

parser = argparse.ArgumentParser(
                    prog='Бот поддержки Edwica.ru',
                    description='Нужен для того, чтобы отвечать на вопросы пользователей в телеграм',
                    epilog='Text at the bottom of help')

parser.add_argument("-b", "--bot", required=True, help="Выбери название бота: edwica, openedu, profinansy")
args = parser.parse_args()
config = [cfg for cfg in tools.load_config() if cfg.BotName == args.bot][0]

locale.setlocale(locale.LC_ALL, "ru_RU") # Отображение даты на русском языке
os.makedirs("data", exist_ok=True) # Создаем папку для хранения картинок/дампов

bot = Bot(config.Token)
dp = Dispatcher(bot, storage=MemoryStorage())
mongoStorage = Storage(db_name=config.MongodbName, add_prepared_questions=True)
preparedQuestions = mongoStorage.get_questions()
UserCacheCategories = {} # Кэш для запоминания какую категорию в последний раз выбирал пользователь
UserCacheEmails = {} # Кэш для запоминания почты пользователя, чтобы в лишний раз не лезть в БД
UserTimedMessageCache = {} # Кэш для временных сообщений


class UserQuestion(StatesGroup):
    """Машина состояний для создания нового вопроса и проверки почты"""
    Email = State()
    New = State()

class AdminMailing(StatesGroup):
    """Машина состояний для создания новой рассылки"""
    New = State()
    Image = State()


@dp.message_handler(commands=["start"])
async def start_command(msg: types.Message):
    """Админу показываем одни кнопки, а пользователю другие"""
    user_text = f"""Привет, {msg.from_user.first_name}!👋\n{config.StartMessage}"""

    user_id = msg.from_user.id
    if user_id in mongoStorage.get_admins():
        await msg.answer(text="Приветственное сообщение для админа", reply_markup=kb.get_admin_menu())
    else:
        categories = mongoStorage.get_categories()
        await msg.answer(text=user_text, reply_markup=kb.get_users_menu(categories))


@dp.message_handler()
async def text_message_filter(msg: types.Message):
    """Фильтр текстовых сообщений. В зависимости от того прислал сообщение админ или пользователь, будут применяться разные фильтры"""
    if msg.from_user.id in mongoStorage.get_admins():
        await admin_message_filter(msg)
    else:
        await user_message_filter(msg)


# ------------------------------------------------------user------------------------------------------------------------------

async def user_message_filter(msg: types.Message):
    """Здесь уже фильтруем выбрал ли пользователь категорию или что-то другое написал"""
    if await check_message_is_category(msg):
        # Сценарий, когда пользователь выбрал категорию
        await show_questions_by_category(msg)
    else:
        # Сценарий, когда пользователь что-то написал (не значение какой-то кнопки)
        await detect_user_email(msg.from_user.id, msg.chat.id)

async def check_message_is_category(msg: types.Message) -> bool:
    """Проверяем, что введеное сообщение - это категория"""
    if msg.text.lower() in (i.lower() for i in mongoStorage.get_categories()):
        # Кидаем в кэш, выбранную категорию - это нам пригодится, если пользователь
        # часто будет задавать вопрос, нажимая на кнопку "задать вопрос", т.е продолжить разговор после ответа админа
        UserCacheCategories[msg.from_user.id] = msg.text.lower()
        return True
    return False

async def show_questions_by_category(msg: types.Message):
    """Показываем клавиатуру с вопросами по выбранной категории"""
    category = UserCacheCategories[msg.from_user.id]
    if category == "другое":
        await detect_user_email(msg.from_user.id, msg.chat.id)
        return

    questions = mongoStorage.get_questions_by_category(category)
    category_keyboard = kb.get_keyboard_by_category(questions)
    if not category_keyboard: # Делаем на всякий случай проверку, нашлась ли клавиатура
        return
    await msg.answer(text=category_keyboard.Text, reply_markup=category_keyboard.Keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("question_"))
async def callback_question(call: types.CallbackQuery):
    """Реакция на inline-кнопку с названием подготовленного вопроса:
    по callback_data нужный вопрос и отправим его ответ"""
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
    """Реакция на кнопки с текстом "другое" """
    await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    await detect_user_email(call.from_user.id, call.message.chat.id)

async def detect_user_email(user_id: int, chat_id: int):
    """Если пользователь хочет написать хоть что-то, что не является категорий подготовленных вопросов,
    то мы должны проверить вводил ли он свою почту раньше. Если нет, то просим ввести. Почта должна пройти валидацию регуляркой
    Если пользователь уже вводил почту, то включаем режим прослушивания вопроса"""

    if not mongoStorage.get_user_email(user_id):
        await bot.send_message(chat_id=chat_id, text="Для быстрой помощи, напишите, пожалуйста, почту, использованную при регистрации 📧👍")
        await UserQuestion.Email.set()
    else:
        await bot.send_message(chat_id=chat_id, text="Опишите вашу проблему:")
        await UserQuestion.New.set()

@dp.message_handler(state=UserQuestion.New)
async def process_new_user_question(msg: types.Message, state: FSMContext):
    """Здесь мы обрабатываем вопрос пользователя, которого нет среди подготовленных"""
    await state.finish()

    # Если пользователь ввел категорию, то выключаем машину состояний и показываем ему вопросы по категории
    if await check_message_is_category(msg):
        await show_questions_by_category(msg)
        return

    # Проверяем все ли хорошо с почтой
    user_id = msg.from_user.id
    if user_id in UserCacheEmails:
        email = UserCacheEmails[user_id]
    else:
        email = mongoStorage.get_user_email(user_id)
        if not email:
            await detect_user_email(user_id, msg.chat.id)
            return

    question = Question(
        Id=0,
        FirstName=msg.from_user.first_name,
        UserId=user_id,
        UserName=msg.from_user.username,
        Question=msg.text,
        Category=UserCacheCategories[user_id] if user_id in UserCacheCategories else "другое",
        Email=email,
        Date=datetime.now()

    )
    question_id = mongoStorage.save_new_question(question)
    # timed_message - нужен для того, чтобы удалить сообщение после ответа администратора.
    timed_message = await msg.answer("Ваш запрос отправлен администратору и будет рассмотрен в ближайшее время. Ответ придет в чат. Спасибо за обращение!")
    UserTimedMessageCache[msg.from_user.id] = timed_message.message_id

    # Отправляем всем админам оповещение о новом вопросе
    await send_new_question_to_admins(question_id, question)

@dp.message_handler(state=UserQuestion.Email)
async def get_new_email_from_user(msg: types.Message, state: FSMContext):
    """Если пользователь ввел неправильную почту, то программа попросит ввести почту заново.
    И НЕ ОСТАНОВИТСЯ ПОКА НЕ ПОЛУЧИТ НОРМ ПОЧТУ"""
    if not tools.validate_email(msg.text):
        await bot.send_message(chat_id=msg.chat.id, text=f"Почта [{msg.text}] не прошла валидацию. Попробуйте снова внимательно ввести вашу почту без ничего лишнего")
        await UserQuestion.Email.set()
        return

    UserCacheEmails[msg.from_user.id] = msg.text
    await bot.send_message(chat_id=msg.chat.id, text="Опишите вашу проблему:")
    # Теперь, после того, как мы получили сообщение, можно узнать о проблеме пользователя
    await UserQuestion.New.set()

async def send_answer_to_user(question_id: int):
    """Отправляем ответ пользователю"""

    # Проверяем, что вопрос закрыт
    answer = mongoStorage.get_answer(question_id)
    if not answer:
        return

    # Если мы ранее сохраняли в кэш сообщение типа: "админ скоро вам ответит", то удаляем его из чата
    if answer.UserId in UserTimedMessageCache:
        await bot.delete_message(chat_id=answer.UserId, message_id=UserTimedMessageCache[answer.UserId])
        del UserTimedMessageCache[answer.UserId] # В кэше сообщение нам тоже больше не нужно

    msg = f"{answer.UserName}, мы обработали ваш запрос: {answer.Question}\nГотовы предоставить ответ: {answer.Text}."
    await bot.send_message(chat_id=answer.UserId, text=msg, reply_markup=kb.get_rate_answer_keyboard(question_id))


@dp.callback_query_handler(lambda c: "like" in c.data)
async def rate_answer(call: types.CallbackQuery):
    """Решаем че нам делать с оценкой пользователя. Если она хорошая, то ставим лайк админу,
    если плохая, то спрашиваем че случилось и ставим админу дизлайк"""
    rate, question_id = call.data.split("_") # делим по символу '_' тк нам придет такая строка 'dislike_1' или 'like_1214'
    if rate == "like":
        mongoStorage.mark_answer_as_correct(int(question_id))
        await bot.send_message(chat_id=call.message.chat.id, text="Ваша поддержка мотивирует нас становиться лучше! Спасибо! 🎉")
    else:
        mongoStorage.mark_answer_as_correct(int(question_id), liked=False)
        await bot.send_message(chat_id=call.message.chat.id, text="Нам жаль, что вы не довольны. Можете ли вы задать свой вопрос еще раз или уточнить, что именно вам не понравилось? 😓")
        await UserQuestion.New.set() # Слушаем че не так

    # Удаляем клавиатуру с оценкой
    await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)


@dp.callback_query_handler(lambda c: c.data == "continue_chating")
async def continue_chating(call: types.CallbackQuery):
    """Продолжение чаттинга, если ответ не понравился"""

    # Удаляем клавиатуру с оценкой
    await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    await bot.send_message(chat_id=call.message.chat.id, text="Опишите вашу проблему:")
    await UserQuestion.New.set()

# ------------------------------------------------------admin------------------------------------------------------------------

async def admin_message_filter(msg: types.Message):
    """фильтр текстовых сообщений для админа"""
    if msg.reply_to_message:
        await admin_reply_message(msg)
    else:
        await check_message_is_admin_actions(msg)

async def send_new_question_to_admins(question_id: int, question: Question):
    """Отправляем новое сообщение от пользователя всем админам"""
    message = "\n".join((
        f"⚠️ Новый вопрос от: @{question.UserName}",
        f"id: {question_id}",
        f"👤 Имя пользователя: {question.FirstName}",
        f"💌 Почта: {question.Email}",
        f"Категория: {question.Category}",
        f"❓Вопрос: {question.Question}",
    ))
    for admin in mongoStorage.get_admins():
        await bot.send_message(chat_id=admin, text=message)


async def admin_reply_message(msg: types.Message):
    """Когда админ тегает сообщение бота, нужно получить id из этого сообщения и ответить на него"""
    question_text = msg.reply_to_message.text
    try:
        question_id = int(re.findall(r"id: \d+", question_text)[0].replace("id: ", ""))
    except:
        return

    closed = mongoStorage.check_question_is_closed(question_id)
    if closed is None:
        # Проверяем был ли такой вопрос в БД
        await msg.answer("Вопрос был удален из БД")
        return

    if closed:
        # Проверяем отвечали ли раньше админы на это сообщение
        answer = mongoStorage.get_answer(question_id)
        if answer:
            await msg.answer(f"На это сообщение уже ответил: @{answer.AdminName}\nВот ответ:{answer.Text}")
        return

    # Отправляем наш ответ
    mongoStorage.save_answer(Answer(
        Id=question_id,
        Text=msg.text,
        AdminId=msg.from_user.id,
        AdminName=msg.from_user.username,
        Question=question_text,
        UserId=0,
        UserName=""
    ))
    await msg.answer("Готово!")
    await send_answer_to_user(question_id)
    await send_notification_to_admins(question_id, ignore_id=msg.from_user.id)


async def send_notification_to_admins(question_id: int, ignore_id: int = 0):
    """Пишем всем админам, что другой админ ответил на какое-то сообщение
    ignore_id = это id того админа, который и придумал ответ. Ему уведомление отправлять смысла нет"""

    answer = mongoStorage.get_answer(question_id)
    if not answer:
        return

    message = "\n".join((
        f"👤 Админ @{answer.AdminName} ответил на вопрос № {question_id}",
        f"❔ Вопрос: {answer.Question}",
        f"📝 Ответ: {answer.Text}"
    ))
    for admin in mongoStorage.get_admins():
        if admin == ignore_id: continue
        await bot.send_message(chat_id=admin, text=message)


async def check_message_is_admin_actions(msg: types.Message):
    """Фильтр кнопок админа"""
    action = msg.text.lower()
    match action:
        case "статистика":
            await show_statistic(msg)
        case "непрочитанные сообщения":
            await send_open_question_to_admin(msg.chat.id)
        case "сделать рассылку":
            await msg.answer("Напишите текст рассылки:")
            await AdminMailing.New.set()
        case "рассылка с картинкой":
            await msg.answer("Отправь картинку сразу вместе с текстом")
            await AdminMailing.Image.set()



async def show_statistic(msg: types.Message):
    """Отправляем админу запрошенную статистику"""

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

async def send_open_question_to_admin(chat_id: int):
    """Отправляем непрочитанные сообщения для админа, который попросил список этих сообщений"""

    questions = mongoStorage.get_open_requests()
    if not questions:
        await bot.send_message(chat_id=chat_id, text="Нет непрочитанных сообщений")
        return

    for qst in questions:
        text = "\n".join((
                f"#️⃣ id: {qst.Id}",
                f"👤 Имя пользователя: {qst.FirstName if qst.FirstName else qst.UserName}",
                f"💌 Почта: {qst.Email}",
                f"🏷️ Категория: {qst.Category}",
                f"❓ Вопрос: {qst.Question}\n",
                f"📅 Дата: {qst.Date.strftime('%d %B, %Y г. %H:%M')}"
            ))
        await bot.send_message(chat_id, text)

@dp.message_handler(state=AdminMailing.New)
async def new_mailing(msg: types.Message, state: FSMContext):
    """Создаем новую текстовую рассылку"""
    timed_message = await msg.answer(text=msg.text, reply_markup=kb.get_mailing_keyboard())
    UserTimedMessageCache[msg.from_user.id] = timed_message.message_id # Удалим потом это сообщение из чата
    await state.finish()

@dp.callback_query_handler(lambda c: "mailing" in c.data)
async def process_mailing(call: types.CallbackQuery):
    """Реакция на кнопки под рассылкой"""
    if call.data == "send_mailing":
        for user in mongoStorage.get_all_users():
            await bot.send_message(chat_id=user, text=call.message.text)

        # Удаляем клавиатуру у админа
        await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        await bot.send_message(chat_id=call.from_user.id, text="Отправлено!")
        mongoStorage.save_mailing(Mailing(
            AdminId=call.from_user.id,
            AdminUser=call.from_user.username,
            Text=call.message.text,
            Date=datetime.now(),
            Views=len(mongoStorage.get_all_users()),
            Picture=""
        ))

    # Реакция на кнопку отмены
    else:
        await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        await bot.send_message(chat_id=call.from_user.id, text="Рассылки не будет")

@dp.edited_message_handler(lambda msg: True)
async def edit_mailing(msg: types.Message):
    """Реакция на редактирование сообщения без картинки (будет активироваться рассылка)"""
    try:
        await bot.delete_message(chat_id=msg.chat.id, message_id=UserTimedMessageCache[msg.from_user.id])
        del UserTimedMessageCache[msg.from_user.id]
    except BaseException as err:
        # Хз че делать
        print(err)
        return

    timed_message = await msg.answer(text=msg.text, reply_markup=kb.get_mailing_keyboard())
    UserTimedMessageCache[msg.from_user.id] = timed_message.message_id


@dp.message_handler(state=AdminMailing.Image, content_types=["photo"])
async def img_mailing(msg: types.Message, state: FSMContext):
    """Создание рассылки с картинкой"""
    timed_message = await msg.reply_photo(photo=msg.photo[-1].file_id, caption=msg.caption, reply_markup=kb.get_mailing_img_keyboard())
    UserTimedMessageCache[msg.from_user.id] = timed_message.message_id
    await state.finish()

@dp.callback_query_handler(lambda c: "img" in c.data)
async def process_img_mailing(call: types.CallbackQuery):
    """Реакция на кнопки под рассылкой с картинкой"""
    if call.data == "send_img":
        # Сохраняем переданную фотку
        os.makedirs("data/imgs", exist_ok=True)
        img_path = f"data/imgs/{datetime.now()}.jpg"
        await call.message.photo[-1].download(destination_file=img_path)

        for user in mongoStorage.get_all_users():
            await bot.send_photo(chat_id=user, photo=call.message.photo[-1].file_id,  caption=call.message.caption)

        # Удаляем клавиатуру под рассылкой
        await bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
        await bot.send_message(chat_id=call.from_user.id, text="Отправлено!")
        mongoStorage.save_mailing(Mailing(
            AdminId=call.from_user.id,
            AdminUser=call.from_user.username,
            Text=call.message.caption,
            Date=datetime.now(),
            Views=len(mongoStorage.get_all_users()),
            Picture=img_path
        ))
    # Реакция на отмену
    else:
        await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        await bot.send_message(chat_id=call.from_user.id, text="Рассылки не будет")

@dp.edited_message_handler(lambda msg: True, content_types=["photo"])
async def edit_img_mailing(msg: types.Message):
    """Реакция на редактирование сообщения c картинкой (будет активироваться рассылка)"""
    try:
        await bot.delete_message(chat_id=msg.chat.id, message_id=UserTimedMessageCache[msg.from_user.id])
        del UserTimedMessageCache[msg.from_user.id]
    except BaseException as err:
        print(err)
        return

    timed_message = await msg.answer_photo(photo=msg.photo[-1].file_id, caption=msg.caption, reply_markup=kb.get_mailing_img_keyboard())
    UserTimedMessageCache[msg.from_user.id] = timed_message.message_id


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
