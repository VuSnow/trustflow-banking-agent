import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEXT2SQL_AGENT_URL = os.getenv("TEXT2SQL_AGENT_URL", "http://localhost:8001")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dungvu:dungvu@localhost:5432/banking_mcp_test")
CURRENT_BANK_CODE = os.getenv("CURRENT_BANK_CODE", "SHB")
