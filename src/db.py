import pymongo
from models import PreparedQuestion, NewQuestion, NewAnswer, Answer, Statistic, AdminStat, CategoryStat, Mailing
import re
from collections import Counter

# MONGO_URL = "mongodb://94.250.253.88:27017/"
MONGO_URL = "mongodb://localhost:27017/"


class Storage:
    def __init__(self, connect_url: str = MONGO_URL, db_name: str = "support_bot"):
        self.client = pymongo.MongoClient(connect_url)
        self.db = self.client[db_name]
        self.admins_db = self.client["support_admins"]
        self.admins_cl = self.admins_db["admins"]
        self.prepared_questions_cl = self.db["questions"]
        self.questions_cl = self.db["requests"]
        self.mailing_cl = self.db["mailing"]

    def get_admins_id(self) -> tuple[int]:
        admins = self.admins_cl.distinct("id", {"active": True})
        return tuple(admins)
    
    def get_categories(self) -> tuple[str]:
        categories = self.prepared_questions_cl.distinct("category")
        return tuple(reversed(categories))

    def get_questions_by_category(self, category: str) -> list[PreparedQuestion]:
        pattern = re.compile(category, re.IGNORECASE)
        data = self.prepared_questions_cl.find({"category": pattern}) # поиск без привязки к регистру
        questions = [PreparedQuestion(
            Text=i["question"],
            Answer=i["answer"],
            Category=category,
            CallbackData=i["callback_data"]
        ) for i in data]
        return questions
    
    def get_questions(self) -> list[PreparedQuestion]:
        data = self.prepared_questions_cl.find() # поиск без привязки к регистру
        questions = [PreparedQuestion(
            Text=i["question"],
            Answer=i["answer"],
            Category=i["category"],
            CallbackData=i["callback_data"]
        ) for i in data]
        return questions

    
    def get_user_email(self, user_id: int) -> str | None:
        email = self.questions_cl.find_one({"user_id": user_id}, {"email": 1, "_id": 0})
        if email:
            return email["email"]
        return None
    
    def save_new_question(self, req: NewQuestion) -> int:
        """Возвращаем id, который будет являться порядковым номером в БД. Так как нам нужно именно число, а не mongo_id"""
        count = self.questions_cl.find({}, {"id": 1, "_id": 0}).sort("id", -1).limit(1)
        try:
            question_id = next(count)["id"] + 1
        except:
            question_id = 1
        doc = {
            "id": question_id,
            "admin_id": None,
            "admin_name": None,
            "user_name": req.UserName,
            "user_id": req.UserId,
            "email": req.Email,
            "category": req.Category if req.Category else "другое",
            "question": req.Question,
            "answer": None,
            "closed": False,
            "liked": None
        }
        self.questions_cl.insert_one(doc)
        return  question_id
    
    def get_question_by_id(self, id: int) -> NewQuestion:
        req = self.questions_cl.find_one({"id": id})
        return NewQuestion(
            Id=req["id"],
            UserId=req["user_id"],
            UserName=req["user_name"],
            Question=req["question"],
            Category=req["category"],
            Email=req["email"]
        )

    def save_answer(self, answer: NewAnswer):
        filter = {"id" : answer.QuestionId}
        update = {
            "$set": {
                "admin_name": answer.AdminName,
                "admin_id": answer.AdminId,
                "answer": answer.Answer,
                "closed": True
            }
        }
        self.questions_cl.update_many(filter, update)    

    
    def get_answer_by_question_id(self, id: int) -> Answer:
        req = self.questions_cl.find_one({"id": id, "closed": True})
        if not req:
            return None

        return Answer(
            Id=id,
            UserId=req["user_id"],
            UserName=req['user_name'],
            Text=req["answer"],
            Question=req["question"]
        )

    def mark_answer_as_correct(self, id: int, liked: bool = True):
        filter = {"id" : id}
        update = {
            "$set": {
                "liked": liked,
            }
        }
        self.questions_cl.update_one(filter, update)    

    def get_statistics(self) -> Statistic:
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

    def get_all_users(self) -> list[int]: 
        return self.questions_cl.distinct("user_id")
    
    def save_mailing(self, mailing: Mailing):
        doc = {
            "admin_id": mailing.AdminId,
            "admin_user": mailing.AdminUser,
            "text": mailing.Text,
            "views": mailing.Views,
            "date": mailing.Date,
            "picture": mailing.Picture
        }
        self.mailing_cl.insert_one(doc)

    def get_admin_answer(self, id: int) -> NewAnswer:
        req = self.questions_cl.find_one({"id": id, "closed": True})
        if not req:
            return None

        return NewAnswer(
            QuestionId=id,
            AdminId=req["admin_id"],
            AdminName=req['admin_name'],
            Answer=req["answer"],
            Question=req["question"]
        )
  
    def get_open_requests(self) -> list[NewQuestion]:
        data = self.questions_cl.find({"closed": False})
        items = []
        for i in data:
            items.append(NewQuestion(
                Id=i["id"],
                UserId=i["user_id"],
                UserName=i["user_name"],
                Question=i["question"],
                Category=i["category"],
                Email=i["email"],
                FirstName=""
        ))
        return items

    def check_question_is_closed(self, question_id: int) -> bool:
        item = self.questions_cl.find_one({"id": question_id}, {"_id": 0, "closed": 1})
        if item is None:
            return
        if item["closed"]:
            return True
        return False
