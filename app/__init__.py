from flask import Flask
from flask_login import LoginManager
from app.config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Import and register blueprints
    from app.routes import main_bp, init_login_manager
    
    # Set up login manager
    init_login_manager(app)
    
    # Register blueprints
    app.register_blueprint(main_bp)
    
    return app
