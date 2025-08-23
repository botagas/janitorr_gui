import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the project root for Flask-specific settings only
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or 'dev'
    # Janitorr paths are now handled exclusively by GuiConfig
