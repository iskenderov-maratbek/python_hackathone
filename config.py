
import os
from urllib.parse import quote_plus

# Получаем значения из окружения
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost:27017")
MONGO_DB   = os.getenv("MONGO_DB", "mcp_demo_db")

if not MONGO_USER or not MONGO_PASS:
    raise RuntimeError("Missing MongoDB credentials in environment variables")

# Экранируем пароль для URI
mongo_pass_escaped = quote_plus(MONGO_PASS)
print(f"mongo_pass_escaped: {mongo_pass_escaped}")
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{mongo_pass_escaped}@{MONGO_HOST}/{MONGO_DB}?retryWrites=true&w=majority"

from pymongo import MongoClient
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

employees_collection = db["employees"]
expenses_collection = db["expenses"]
contracts_collection = db["contracts"]
tasks_collection = db["tasks"]
schema_registry_collection = db["db_schema_registry"]
