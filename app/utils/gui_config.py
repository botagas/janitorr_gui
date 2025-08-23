"""GUI-specific configuration management using .env file"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from flask import current_app

class GuiConfig:
    """Manages GUI-specific configuration using .env file"""
    
    def __init__(self, env_path: Optional[str] = None):
        # Use provided path or default to .env in the app root directory
        if env_path:
            self.env_path = Path(env_path)
        else:
            # Default to .env in the same directory as the main app
            app_dir = Path(__file__).parent.parent.parent
            self.env_path = app_dir / '.env'
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default GUI configuration"""
        # Read individual authentication settings
        legacy_enabled = os.getenv('GUI_LEGACY_AUTH_ENABLED', 'false').lower() == 'true'
        ldap_enabled = os.getenv('GUI_LDAP_ENABLED', 'false').lower() == 'true'
        
        # Auto-determine auth mode based on what's enabled
        # Allow manual override via GUI_AUTH_MODE if needed
        manual_auth_mode = os.getenv('GUI_AUTH_MODE', '').lower()
        
        if manual_auth_mode in ['none', 'legacy', 'ldap', 'both']:
            # Use manually specified mode
            auth_mode = manual_auth_mode
        else:
            # Auto-determine based on enabled features
            if legacy_enabled and ldap_enabled:
                auth_mode = 'both'
            elif ldap_enabled:
                auth_mode = 'ldap'
            elif legacy_enabled:
                auth_mode = 'legacy'
            else:
                auth_mode = 'none'
        
        return {
            'gui': {
                'janitorr_config_path': os.getenv('JANITORR_CONFIG_PATH', '/opt/janitorr/application.yml'),
                'janitorr_log_path': os.getenv('JANITORR_LOG_PATH', '/var/log/janitorr/janitorr.log'),
                'janitorr_working_directory': os.getenv('JANITORR_WORKING_DIR', '/opt/janitorr'),
                'auto_refresh_interval': int(os.getenv('GUI_AUTO_REFRESH', '30')),
                'theme': os.getenv('GUI_THEME', 'dark'),
                'auth_mode': auth_mode,
                'session_secret_key': os.getenv('GUI_SESSION_SECRET_KEY', 'change-this-secret-key-in-production'),
                'session_timeout': int(os.getenv('GUI_SESSION_TIMEOUT', '3600')),
                'legacy_auth': {
                    'enabled': legacy_enabled,
                    'username': os.getenv('GUI_LEGACY_AUTH_USERNAME', 'admin'),
                    'password': os.getenv('GUI_LEGACY_AUTH_PASSWORD', '')
                },
                'ldap': {
                    'enabled': ldap_enabled,
                    'server': os.getenv('GUI_LDAP_SERVER', ''),
                    'base_dn': os.getenv('GUI_LDAP_BASE_DN', ''),
                    'user_filter': os.getenv('GUI_LDAP_USER_FILTER', '(sAMAccountName={username})'),
                    'bind_dn': os.getenv('GUI_LDAP_BIND_DN', ''),
                    'bind_password': os.getenv('GUI_LDAP_BIND_PASSWORD', ''),
                    'admin_group': os.getenv('GUI_LDAP_ADMIN_GROUP', ''),
                    'use_ssl': os.getenv('GUI_LDAP_USE_SSL', 'false').lower() == 'true',
                    'verify_ssl': os.getenv('GUI_LDAP_VERIFY_SSL', 'true').lower() == 'true'
                }
            }
        }
    
    def read_env_file(self) -> Dict[str, str]:
        """Read .env file and return as dictionary"""
        env_vars = {}
        try:
            if self.env_path.exists():
                with open(self.env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            # Remove quotes if present
                            value = value.strip().strip('"').strip("'")
                            env_vars[key.strip()] = value
        except Exception as e:
            print(f"Error reading .env file: {e}")
        return env_vars
    
    def read_config(self) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Read GUI configuration from .env file and environment
        Returns: (config_dict, error_message)
        """
        try:
            # Read from .env file first
            env_vars = self.read_env_file()
            
            # Update os.environ temporarily to get values
            original_env = {}
            for key, value in env_vars.items():
                if key in os.environ:
                    original_env[key] = os.environ[key]
                os.environ[key] = value
            
            try:
                # Get config using updated environment
                config = self.get_default_config()
                config['_config_path'] = str(self.env_path)
                config['_env_vars_loaded'] = len(env_vars)
                return config, None
            finally:
                # Restore original environment
                for key in env_vars:
                    if key in original_env:
                        os.environ[key] = original_env[key]
                    else:
                        os.environ.pop(key, None)
                        
        except Exception as e:
            error_msg = f"Error reading GUI configuration: {str(e)}"
            config = self.get_default_config()
            config['_config_path'] = str(self.env_path)
            config['_env_vars_loaded'] = 0
            return config, error_msg
    
    def write_env_file(self, env_vars: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Write environment variables to .env file
        Returns: (success, error_message)
        """
        try:
            # Ensure directory exists
            self.env_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup if .env exists
            if self.env_path.exists():
                backup_path = self.env_path.with_suffix('.env.backup')
                self.env_path.rename(backup_path)
            
            # Read existing .env to preserve non-GUI settings
            existing_vars = {}
            backup_path = self.env_path.with_suffix('.env.backup')
            if backup_path.exists():
                with open(backup_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            # Don't overwrite GUI-specific vars
                            if not self._is_gui_var(key):
                                existing_vars[key] = value
            
            # Merge existing with new GUI vars
            all_vars = {**existing_vars, **env_vars}
            
            # Write .env file
            with open(self.env_path, 'w') as f:
                f.write("# Janitorr GUI Configuration\n")
                f.write("# This file contains environment variables for the GUI\n\n")
                
                # Write GUI vars in organized sections
                gui_vars = {k: v for k, v in all_vars.items() if self._is_gui_var(k)}
                if gui_vars:
                    # Basic GUI settings
                    basic_gui_vars = ['JANITORR_CONFIG_PATH', 'JANITORR_LOG_PATH', 'JANITORR_WORKING_DIR', 'GUI_AUTO_REFRESH', 'GUI_THEME']
                    f.write("# GUI Settings\n")
                    for key in basic_gui_vars:
                        if key in gui_vars:
                            f.write(f'{key}={gui_vars[key]}\n')
                    f.write('\n')
                    
                    # Authentication settings
                    auth_vars = ['GUI_SESSION_SECRET_KEY', 'GUI_SESSION_TIMEOUT', 
                                'GUI_SESSION_SECURE_COOKIES', 'GUI_SESSION_REMEMBER_ME']
                    f.write("# Authentication Settings\n")
                    f.write("# Auth mode is auto-determined based on enabled authentication methods:\n")
                    f.write("# - Both enabled = \"both\" (LDAP with legacy fallback)\n")
                    f.write("# - Only LDAP enabled = \"ldap\"\n")
                    f.write("# - Only legacy enabled = \"legacy\"\n") 
                    f.write("# - Neither enabled = \"none\"\n")
                    for key in auth_vars:
                        if key in gui_vars:
                            f.write(f'{key}={gui_vars[key]}\n')
                    f.write('\n')
                    
                    # Legacy authentication
                    legacy_vars = ['GUI_LEGACY_AUTH_ENABLED', 'GUI_LEGACY_AUTH_USERNAME', 'GUI_LEGACY_AUTH_PASSWORD']
                    f.write("# Legacy Authentication\n")
                    for key in legacy_vars:
                        if key in gui_vars:
                            f.write(f'{key}={gui_vars[key]}\n')
                    f.write('\n')
                    
                    # LDAP authentication
                    ldap_vars = ['GUI_LDAP_ENABLED', 'GUI_LDAP_SERVER', 'GUI_LDAP_PORT', 'GUI_LDAP_BASE_DN', 'GUI_LDAP_USER_FILTER', 
                                'GUI_LDAP_BIND_DN', 'GUI_LDAP_BIND_PASSWORD', 'GUI_LDAP_ADMIN_GROUP', 
                                'GUI_LDAP_USE_SSL', 'GUI_LDAP_VERIFY_SSL']
                    f.write("# LDAP Authentication\n")
                    for key in ldap_vars:
                        if key in gui_vars:
                            f.write(f'{key}={gui_vars[key]}\n')
                    f.write('\n')
                    
                    # Any remaining GUI vars
                    written_vars = set(basic_gui_vars + auth_vars + legacy_vars + ldap_vars)
                    remaining_gui_vars = {k: v for k, v in gui_vars.items() if k not in written_vars}
                    if remaining_gui_vars:
                        f.write("# Other GUI Settings\n")
                        for key, value in sorted(remaining_gui_vars.items()):
                            f.write(f'{key}={value}\n')
                        f.write('\n')
                
                # Write other vars
                other_vars = {k: v for k, v in all_vars.items() if not self._is_gui_var(k)}
                if other_vars:
                    f.write("# Other Settings\n")
                    for key, value in sorted(other_vars.items()):
                        f.write(f'{key}={value}\n')
            
            return True, None
            
        except Exception as e:
            # Restore backup if write fails
            backup_path = self.env_path.with_suffix('.env.backup')
            if backup_path.exists():
                try:
                    backup_path.rename(self.env_path)
                except Exception:
                    pass
            return False, f"Could not write .env file: {str(e)}"
    
    def _is_gui_var(self, key: str) -> bool:
        """Check if a variable is GUI-specific"""
        gui_prefixes = ['JANITORR_CONFIG_PATH', 'JANITORR_LOG_PATH', 'JANITORR_WORKING_DIR', 'GUI_']
        return any(key.startswith(prefix) for prefix in gui_prefixes)
    
    def update_setting(self, key_path: str, value: Any) -> Tuple[bool, Optional[str]]:
        """
        Update a single setting using dot notation (e.g., 'gui.janitorr_config_path')
        Returns: (success, error_message)
        """
        # Map GUI config paths to environment variable names
        env_var_map = {
            'gui.janitorr_config_path': 'JANITORR_CONFIG_PATH',
            'gui.janitorr_log_path': 'JANITORR_LOG_PATH', 
            'gui.janitorr_working_directory': 'JANITORR_WORKING_DIR',
            'gui.auto_refresh_interval': 'GUI_AUTO_REFRESH',
            'gui.theme': 'GUI_THEME',
            'gui.auth_mode': 'GUI_AUTH_MODE',
            'gui.session.secret_key': 'GUI_SESSION_SECRET_KEY',
            'gui.session.timeout_hours': 'GUI_SESSION_TIMEOUT',
            'gui.session.secure_cookies': 'GUI_SESSION_SECURE_COOKIES',
            'gui.session.remember_me': 'GUI_SESSION_REMEMBER_ME',
            'gui.legacy_auth.enabled': 'GUI_LEGACY_AUTH_ENABLED',
            'gui.legacy_auth.username': 'GUI_LEGACY_AUTH_USERNAME',
            'gui.legacy_auth.password': 'GUI_LEGACY_AUTH_PASSWORD',
            'gui.ldap.enabled': 'GUI_LDAP_ENABLED',
            'gui.ldap.server': 'GUI_LDAP_SERVER',
            'gui.ldap.port': 'GUI_LDAP_PORT',
            'gui.ldap.base_dn': 'GUI_LDAP_BASE_DN',
            'gui.ldap.user_filter': 'GUI_LDAP_USER_FILTER',
            'gui.ldap.bind_dn': 'GUI_LDAP_BIND_DN',
            'gui.ldap.bind_password': 'GUI_LDAP_BIND_PASSWORD',
            'gui.ldap.admin_group': 'GUI_LDAP_ADMIN_GROUP',
            'gui.ldap.use_ssl': 'GUI_LDAP_USE_SSL',
            'gui.ldap.verify_ssl': 'GUI_LDAP_VERIFY_SSL'
        }
        
        env_var = env_var_map.get(key_path)
        if not env_var:
            return False, f"Unknown GUI setting: {key_path}"
        
        # Handle boolean values (both actual booleans and checkbox strings from forms)
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        elif isinstance(value, str) and value.lower() in ['on', 'checked']:
            # HTML checkboxes send 'on' when checked
            value = 'true'
        elif isinstance(value, str) and value.lower() in ['off', 'unchecked', 'false']:
            value = 'false'
        
        # Read current .env vars
        current_vars = self.read_env_file()
        
        # Special handling for auth mode changes - update underlying enable/disable settings
        if key_path == 'gui.auth_mode':
            if value == 'none':
                current_vars['GUI_LEGACY_AUTH_ENABLED'] = 'false'
                current_vars['GUI_LDAP_ENABLED'] = 'false'
            elif value == 'legacy':
                current_vars['GUI_LEGACY_AUTH_ENABLED'] = 'true'
                current_vars['GUI_LDAP_ENABLED'] = 'false'
            elif value == 'ldap':
                current_vars['GUI_LEGACY_AUTH_ENABLED'] = 'false'
                current_vars['GUI_LDAP_ENABLED'] = 'true'
            elif value == 'both':
                current_vars['GUI_LEGACY_AUTH_ENABLED'] = 'true'
                current_vars['GUI_LDAP_ENABLED'] = 'true'
            # Don't store GUI_AUTH_MODE in .env since it's auto-determined
            # But we'll process it to update the enable flags above
            if env_var == 'GUI_AUTH_MODE':
                # Skip writing GUI_AUTH_MODE itself, just update the enable flags
                return self.write_env_file(current_vars)
        
        # Update the specific variable
        current_vars[env_var] = str(value)
        
        # Write back to .env file
        return self.write_env_file(current_vars)
    
    def get_setting(self, key_path: str, default: Any = None) -> Any:
        """
        Get a single setting using dot notation (e.g., 'gui.janitorr_config_path')
        """
        config, _ = self.read_config()
        
        keys = key_path.split('.')
        current = config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
