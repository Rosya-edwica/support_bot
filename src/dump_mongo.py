import subprocess
from datetime import datetime
from db import Storage
from tools import load_config
import requests
import shutil
import os

date = datetime.now().strftime("%d_%m_%Y__%H_%M_%S")
archive_path = f"dumps/mongodump_{date}.zip"
storage = Storage(db_name="support_admins")
token = [i.Token for i in load_config()][0]

def backup_mongo():
    os.makedirs("dumps", exist_ok=True)
    dbs = ("support_edwica", "support_admins", "support_profinansy", "support_openedu")
    folders = " ".join(dbs)
    backup_path = "."

    [subprocess.run(f"mongodump --db {db} --out {backup_path}", shell=True)  for db in dbs] 
    subprocess.run(f"tar -cvzf {archive_path} {folders}", shell=True)
    [shutil.rmtree(folder) for folder in dbs]
    

def send_backup_to_admins():
    for admin in storage.get_admins_id():
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(archive_path, 'rb') as file:
            files = {
                'document': file
            }
            data = {
                'chat_id': admin,
                "caption": f"Дапм данных от: {datetime.now()}"
            }
            response = requests.post(url, files=files, data=data)
            return response.json()


if __name__ == "__main__":
    backup_mongo()
    send_backup_to_admins()