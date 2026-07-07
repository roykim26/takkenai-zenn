import os
from dotenv import load_dotenv

load_dotenv()

print("LLM_API_KEY =", repr(os.getenv("LLM_API_KEY")))
print("LLM_BASE_URL =", repr(os.getenv("LLM_BASE_URL")))
print("LLM_MODEL =", repr(os.getenv("LLM_MODEL")))