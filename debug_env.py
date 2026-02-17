# debug_env.py
from dotenv import load_dotenv
import os

load_dotenv()

print("APP_ID:", os.getenv("GITHUB_APP_ID"))
print("WEBHOOK_SECRET:", os.getenv("GITHUB_WEBHOOK_SECRET"))
