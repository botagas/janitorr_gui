import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or 'dev'