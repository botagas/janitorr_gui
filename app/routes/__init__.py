"""Routes package for janitorr GUI"""

# Import blueprints and initialization functions
from .main import main_bp, init_login_manager

__all__ = ['main_bp', 'init_login_manager']
