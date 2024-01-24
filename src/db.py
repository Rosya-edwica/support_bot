import pymongo
from collections import Counter
import json
import re
from models import PreparedQuestion, Question, Answer, Statistic, AdminStat, CategoryStat, Mailing

DEFAULT_PATH_FOR_PREPARED_QUESTIONS = "data/questions.json"

class Storage:
    """
    Класс для работы с БД. В данном случае - mongoDB.\n
    Здесь реализована работа с разными бд в рамках одного mongoDB.\n
    С помощью этого класса можно получить список подготовленных вопросов, создать новый вопрос, отправить ответ на вопрос,
    создать рассылку и еще многое другое.
    """
    def __init__(self, connect_url: str = "mongodb://localhost:27017/", db_name: str = "support_bot", add_prepared_questions: bool = False):
        self.client = pymongo.MongoClient(connect_url)
        self.db = self.client[db_name]
        self.admins_db = self.client["support_admins"] # Общая БД, к которой должны иметь доступ все другие бд
        self.admins_cl = self.admins_db["admins"] # Коллекция, в которой хранится список администраторов
        self.prepared_questions_cl = self.db["questions"] # Коллекция, в которой лежат подготовленые вопросы вместе с ответами
        self.questions_cl = self.db["requests"] # Коллекция, в которой будут лежат вопросы от пользователя
        self.mailing_cl = self.db["mailing"] # Коллекция, в которой будет храниться история рассылок

        # При первом запуске mongoDB, важно проверить есть ли подготовленные вопросы в выбранной db_name
        if add_prepared_questions:
            self.add_questions()

    def add_questions(self):
        """
        Метод, который будет переносить подготовленные вопросы с ответами в коллекцию questions
        Метод сработает только в том случае, если в коллекции questions ничего нет, чтобы избежать дублирования.
        """

        with open(DEFAULT_PATH_FOR_PREPARED_QUESTIONS, mode="r", encoding="utf-8") as f:
            data = json.load(f)

        if not self.prepared_questions_cl.find_one():
            self.prepared_questions_cl.insert_many(data)

    def get_questions(self) -> list[PreparedQuestion]:
        """Метод, который вернет список всех вопросов"""

        data = self.prepared_questions_cl.find()
        questions = [PreparedQuestion(
            Text=i["question"],
            Answer=i["answer"],
            Category=i["category"],
            CallbackData=i["callback_data"]
        ) for i in data]
        if not questions:
            self.add_questions()
            return self.get_questions()
        return questions

    def save_new_question(self, req: Question) -> int:
        """Сохраняем новый запрос от пользователя и возвращаем импровизированный id AUTOINCREMENT"""

        # выбираем максимальное значение id
        max_qst_id = self.questions_cl.find({}, {"id": 1, "_id": 0}).sort("id", -1).limit(1)
        try:
            question_id = next(max_qst_id)["id"] + 1
        except:
            question_id = 1
        doc = {
            "id": question_id,
            "admin_id": None,
            "admin_name": None,
            "user_name": req.UserName,
            "first_name": req.FirstName,
            "user_id": req.UserId,
            "email": req.Email,
            "category": req.Category if req.Category else "другое",
            "question": req.Question,
            "answer": None,
            "closed": False,
            "liked": None,
            "date": req.Date
        }
        self.questions_cl.insert_one(doc)
        return  question_id

    def get_question_by_id(self, id: int) -> Question:
        """"Возвращаем вопрос по id"""

        req = self.questions_cl.find_one({"id": id})
        return Question(
            Id=req["id"],
            UserId=req["user_id"],
            UserName=req["user_name"],
            Question=req["question"],
            Category=req["category"],
            Email=req["email"],
            FirstName=req["first_name"],
            Date=req["date"]
        )

    def get_open_requests(self) -> list[Question]:
        """Получаем список неотвеченных сообщений"""

        data = self.questions_cl.find({"closed": False})
        items = []
        for i in data:
            items.append(Question(
                Id=i["id"],
                UserId=i["user_id"],
                UserName=i["user_name"],
                Question=i["question"],
                Category=i["category"],
                Email=i["email"],
                FirstName="",
                Date=i["date"]
        ))
        return items

    def check_question_is_closed(self, question_id: int) -> bool | None:
        """Проверяем закрыт ли вопрос"""
        item = self.questions_cl.find_one({"id": question_id}, {"_id": 0, "closed": 1})
        if item is None:
            return
        if item["closed"]:
            return True
        return False

    def get_questions_by_category(self, category: str) -> list[PreparedQuestion]:
        """Метод, который вернет все вопросы, принадлежащие категории {category}"""

        ignore_case_ptn = re.compile(category, re.IGNORECASE)
        data = self.prepared_questions_cl.find({"category": ignore_case_ptn}) # поиск без привязки к регистру
        questions = [PreparedQuestion(
            Text=i["question"],
            Answer=i["answer"],
            Category=category,
            CallbackData=i["callback_data"]
        ) for i in data]
        return questions

    def get_categories(self) -> list[str]:
        """Метод, который возвращает уникальный список категорий"""

        categories = self.prepared_questions_cl.distinct("category")
        categories.reverse()
        return categories

    def save_answer(self, answer: Answer) -> None:
        """"сохраняем ответ админа к конкретному вопросу"""
        filter = {"id" : answer.Id}
        update = {
            "$set": {
                "admin_name": answer.AdminName,
                "admin_id": answer.AdminId,
                "answer": answer.Text,
                "closed": True
            }
        }
        self.questions_cl.update_many(filter, update)

    def mark_answer_as_correct(self, id: int, liked: bool = True):
        """
        Если liked = False, то ставим дизлайк ответу админа\n
        Если liked = True, то ставим лайк ответу админа
        """
        filter = {"id" : id}
        update = {
            "$set": {
                "liked": liked,
            }
        }
        self.questions_cl.update_one(filter, update)

    def get_answer(self, id: int) -> Answer | None:
        """Получаем ответ админа по id"""
        req = self.questions_cl.find_one({"id": id, "closed": True})
        if not req:
            return None

        return Answer(
            Id=id,
            AdminId=req["admin_id"],
            AdminName=req['admin_name'],
            UserId=req["user_id"],
            UserName=req["user_name"],
            Text=req["answer"],
            Question=req["question"]
        )

    def get_admins_id(self) -> list[int]:
        """Метод, который возвращает уникальный список администраторов"""

        admins: list[int] = self.admins_cl.distinct("id", {"active": True})
        return admins

    def get_user_email(self, user_id: int) -> str | None:
        """Метод найдет почту пользователя по его id"""

        email = self.questions_cl.find_one({"user_id": user_id}, {"email": 1, "_id": 0})
        if email:
            return email["email"]
        return None

    def get_all_users(self) -> list[int]:
        """Получить список уникальных пользователей"""
        return self.questions_cl.distinct("user_id")

    def get_statistics(self) -> Statistic:
        """Возвращаем статистику для админов"""

        count_users = len(self.questions_cl.distinct("user_id"))
        count_closed = len([0 for _ in self.questions_cl.find({"closed": True})])
        count_open = len([0 for _ in self.questions_cl.find({"closed": False})])
        categories = [i["category"].lower() for i in self.questions_cl.find({}, {"category": 1, "_id": 0})]
        categories_count = [CategoryStat(*i) for i in Counter(categories).items()]
        admins = self.count_admins_stat()
        return Statistic(
            UsersCount=count_users,
            ClosedCount=count_closed,
            OpenedCount=count_open,
            CategoryStat=categories_count,
            AdminStat=admins
        )

    def count_admins_stat(self) -> list[AdminStat]:
        """Считаем статистику по каждому админу"""

        data = self.questions_cl.find({"admin_id": {"$ne": None}}, {"liked": 1, "admin_id": 1, "admin_name": 1, "_id": 0})
        admins = {}
        for item in data:
            if item["admin_id"] not in admins:
                admins[item["admin_id"]] = AdminStat(UserName=item["admin_name"], Likes=0, Dislikes=0, WithoutRate=0)

            match item["liked"]:
                case True:
                    admins[item["admin_id"]].Likes += 1
                case False:
                    admins[item["admin_id"]].Dislikes += 1
                case None:
                    admins[item["admin_id"]].WithoutRate += 1
        return list(admins.values())

    def save_mailing(self, mailing: Mailing) -> None:
        """Сохранить информацию о рассылке"""

        doc = {
            "admin_id": mailing.AdminId,
            "admin_user": mailing.AdminUser,
            "text": mailing.Text,
            "views": mailing.Views,
            "date": mailing.Date,
            "picture": mailing.Picture
        }
        self.mailing_cl.insert_one(doc)
