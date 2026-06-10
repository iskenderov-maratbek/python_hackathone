from pymongo import MongoClient

# MongoDB Atlas Cloud Connection String
MONGO_URI = "mongodb+srv://iskenderovmaratbek_db_user:EZ9zdsfWLXjyU9DF@rapid-agent-cluster.2vat2ai.mongodb.net/agrum_platform?retryWrites=true&w=majority"

client = MongoClient(MONGO_URI)
db = client["agrum_platform"]

# Exporting collections for the Municipal Enterprise platform
employees_collection = db["employees"]
expenses_collection = db["expenses"]
contracts_collection = db["contracts"]
tasks_collection = db["tasks"]

# Registry for AI schema discovery (The "Knowledge Base" for the agent)
schema_registry_collection = db["db_schema_registry"]