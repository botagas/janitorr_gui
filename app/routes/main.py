"""Main routes for janitorr GUI"""

from datetime import datetime
import yaml
import difflib
import requests
from flask import Blueprint, render_template, current_app, jsonify, request, abort, flash, redirect, url_for, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from functools import wraps
from io import BytesIO

from app.jellyfin_client import JellyfinClient
from app.utils.config_parser import ConfigParser
from app.utils.gui_config import GuiConfig
from app.utils.log_parser import LogParser
from app.utils.ldap_auth import LdapAuthenticator, User
from app.utils.status_checker import StatusChecker

main_bp = Blueprint('main', __name__)
login_manager = LoginManager()
ldap_auth = LdapAuthenticator()

def init_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

@login_manager.user_loader
def load_user(user_id):
    # Get admin status from session
    from flask import session
    is_admin = session.get('is_admin', False)
    user = User(user_id, is_admin)
    return user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Administrator access required')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def get_jellyfin_client():
    """Get configured Jellyfin client from Janitorr config"""
    try:
        # Get configuration path from GUI config only
        gui_config = GuiConfig()
        gui_config_data, _ = gui_config.read_config()
        
        janitorr_config_path = gui_config_data['gui']['janitorr_config_path']
        
        config_parser = ConfigParser(janitorr_config_path)
        jellyfin_config = config_parser.get_jellyfin_config()
        
        if not jellyfin_config or not jellyfin_config.get('enabled'):
            return None
            
        # Make sure we have required configuration
        if 'url' not in jellyfin_config or 'api-key' not in jellyfin_config:
            current_app.logger.warning("Jellyfin configuration incomplete: missing url or api-key")
            return None
            
        return JellyfinClient(
            jellyfin_config['url'],
            jellyfin_config['api-key']
        )
    except Exception as e:
        current_app.logger.error(f"Error creating Jellyfin client: {str(e)}")
        return None

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Get authentication configuration
    gui_config = GuiConfig()
    config_data, _ = gui_config.read_config()
    auth_mode = config_data.get('gui', {}).get('auth_mode', 'none')
    
    current_app.logger.info(f"Authentication mode: {auth_mode}")
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        current_app.logger.info(f"Login attempt for user: {username}")
        
        user = None
        
        if auth_mode == 'none':
            # No authentication required - create admin user
            current_app.logger.info("No authentication required")
            user = User(username or 'admin', is_admin=True)
        elif auth_mode == 'legacy':
            # Legacy username/password authentication
            current_app.logger.info("Using legacy authentication")
            user = authenticate_legacy(username, password, config_data)
        elif auth_mode == 'ldap':
            # LDAP only
            current_app.logger.info("Using LDAP authentication")
            user = ldap_auth.authenticate(username, password)
            if not user:
                # LDAP failed and no fallback available
                flash('LDAP authentication failed. Please check your credentials or contact administrator.', 'error')
        elif auth_mode == 'both':
            # Try LDAP first, fallback to legacy
            current_app.logger.info("Using LDAP with legacy fallback")
            user = ldap_auth.authenticate(username, password)
            if not user:
                current_app.logger.info("LDAP failed, trying legacy authentication")
                # Show message about LDAP failure and suggest legacy
                flash('LDAP server unavailable. Try using your local admin credentials instead.', 'info')
                user = authenticate_legacy(username, password, config_data)
        
        if user:
            # Check if remember me was checked
            remember_me = request.form.get('remember') == '1'
            login_user(user, remember=remember_me)
            # Store admin status in session for load_user function
            from flask import session
            session['is_admin'] = user.is_admin
            return redirect(url_for('main.index'))
        flash('Invalid credentials')
    
    return render_template('login.html', auth_mode=auth_mode)

def authenticate_legacy(username, password, config_data):
    """Authenticate using legacy username/password"""
    legacy_config = config_data.get('gui', {}).get('legacy_auth', {})
    
    if not legacy_config.get('enabled', True):
        return None
    
    expected_username = legacy_config.get('username', 'admin')
    expected_password = legacy_config.get('password', '')
    
    if username == expected_username and password == expected_password:
        return User(username, is_admin=True)
    
    return None

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    # Clear admin status from session
    from flask import session
    session.pop('is_admin', None)
    
    # Clear any existing flash messages to prevent them from showing after logout
    session.pop('_flashes', None)
    
    return redirect(url_for('main.login'))

@main_bp.route('/')
@login_required
def index():
    """Main dashboard showing scheduled deletions"""
    # Get configuration paths from GUI config only
    gui_config = GuiConfig()
    gui_config_data, gui_error = gui_config.read_config()
    
    if gui_error:
        flash(f'GUI configuration error: {gui_error}', 'error')
    
    # Use GUI config paths directly
    janitorr_config_path = gui_config_data['gui']['janitorr_config_path']
    janitorr_log_path = gui_config_data['gui']['janitorr_log_path']
    
    # Check system status
    config_parser = ConfigParser(janitorr_config_path)
    config, config_error = config_parser.read_config()
    
    # Get Jellyfin URL from config if available
    jellyfin_url = None
    if config and 'clients' in config and 'jellyfin' in config['clients']:
        jellyfin_url = config['clients']['jellyfin'].get('url')
    
    status_checker = StatusChecker(
        janitorr_config_path,
        janitorr_log_path,
        jellyfin_url
    )
    system_status = status_checker.check_all()
    
    # Get scheduled deletions if logs are available
    log_parser = LogParser(janitorr_log_path)
    
    # Get deletion configuration for days until deletion calculation
    deletion_config = None
    if config:
        deletion_config = config_parser.get_deletion_rules()
    
    scheduled_deletions, log_error = log_parser.get_scheduled_deletions(deletion_config)
    recent_logs = log_parser.tail_log(100) if system_status.logs_available else []
    
    # Get media info if Jellyfin is available
    media_info = {}
    if system_status.jellyfin_available and config:
        jellyfin = get_jellyfin_client()
        if jellyfin:
            for date, items in scheduled_deletions.items():
                for item in items:
                    current_app.logger.debug(f"Searching for title: {item['title']}")
                    info = jellyfin.get_item_info(item['title'])
                    if info and 'Id' in info:  # Only add if we have valid info with an ID
                        current_app.logger.debug(f"Found Jellyfin item: ID={info['Id']}, Name={info.get('Name')}, Type={info.get('Type')}")
                        media_info[item['title']] = {
                            'info': info,
                            'image_path': f"/jellyfin/Items/{info['Id']}/Images/Primary" if info.get('ImageTags', {}).get('Primary') else None
                        }
                    else:
                        current_app.logger.warning(f"No Jellyfin match found for: {item['title']}")
    
    # Check if Jellyfin is configured and available
    jellyfin_enabled = False
    if config and 'clients' in config and 'jellyfin' in config['clients']:
        jellyfin_config = config['clients']['jellyfin']
        jellyfin_enabled = jellyfin_config.get('enabled', False) and jellyfin_config.get('url') and jellyfin_config.get('api-key')

    return render_template('index.html', 
                         deletions=scheduled_deletions,
                         media_info=media_info,
                         recent_logs=recent_logs,
                         system_status=system_status,
                         jellyfin_enabled=jellyfin_enabled,
                         deletion_config=deletion_config,
                         jellyfin_available=system_status.jellyfin_available)

@main_bp.route('/api/media/<item_id>/info')
@login_required
def media_info(item_id):
    """Get media information from Jellyfin"""
    if not item_id or item_id == 'undefined':
        return jsonify({'error': 'Invalid media ID'}), 400
        
    jellyfin = get_jellyfin_client()
    if not jellyfin:
        return jsonify({'error': 'Jellyfin not configured'}), 503
        
    try:
        info = jellyfin.get_item_by_id(item_id)
        if not info:
            return jsonify({'error': 'Item not found'}), 404
        return jsonify(info)
    except Exception as e:
        current_app.logger.error(f"Error fetching media info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/jellyfin/Items/<item_id>/Images/<image_type>')
@login_required
def media_image(item_id, image_type="Primary"):
    """Proxy Jellyfin image requests with proper authentication"""
    current_app.logger.debug(f"Requested image for item_id: '{item_id}' (length: {len(item_id) if item_id else 0}), type: {image_type}")
    
    jellyfin = get_jellyfin_client()
    if not jellyfin:
        return 'Jellyfin not configured', 503
    
    try:
        # Jellyfin IDs can be various formats:
        # - MD5 hashes (32 hex chars): e.g., "a1b2c3d4e5f6789012345678901234ab"
        # - GUIDs (36 chars with dashes): e.g., "1a2b3c4d-5e6f-7g8h-9i0j-k1l2m3n4o5p6"
        # - Other formats that Jellyfin might use
        if not item_id or len(item_id) < 16:  # More lenient validation
            current_app.logger.error(f"Invalid Jellyfin ID format: '{item_id}' (length: {len(item_id) if item_id else 0})")
            return 'Invalid ID format', 400
            
        url = f"{jellyfin.base_url}/Items/{item_id}/Images/{image_type}"
        current_app.logger.debug(f"Fetching image from: {url}")
        response = requests.get(url, headers=jellyfin.headers)
        
        if not response.ok:
            current_app.logger.error(f"Failed to fetch image for item {item_id}: {response.status_code} {response.text}")
            return 'Image not found', 404
            
        return send_file(
            BytesIO(response.content),
            mimetype=response.headers.get('Content-Type', 'image/jpeg')
        )
    except Exception as e:
        current_app.logger.error(f"Error fetching image: {str(e)}")
        return 'Error fetching image', 500

@main_bp.route('/api/logs/recent')
@login_required
def recent_logs():
    """Get recent log entries"""
    # Get log path from GUI config only
    gui_config = GuiConfig()
    gui_config_data, _ = gui_config.read_config()
    
    janitorr_log_path = gui_config_data['gui']['janitorr_log_path']
    
    log_parser = LogParser(janitorr_log_path)
    lines = log_parser.tail_log(100)  # Get last 100 lines
    return jsonify({'logs': lines})

@main_bp.route('/config', methods=['GET', 'POST'])
@login_required
@admin_required
def config():
    """Configuration management page with tabs"""
    # Get configuration path from GUI config only
    gui_config = GuiConfig()
    gui_config_data, gui_config_error = gui_config.read_config()
    
    janitorr_config_path = gui_config_data['gui']['janitorr_config_path']
    
    config_parser = ConfigParser(janitorr_config_path)
    
    if request.method == 'POST':
        try:
            # Handle YAML text area submission
            if 'config' in request.form:
                config_text = request.form.get('config')
                config_data = yaml.safe_load(config_text)
                config_parser.write_config(config_data)
                flash('Configuration saved successfully!', 'success')
                return redirect(url_for('main.config'))
        except Exception as e:
            flash(f'Error saving configuration: {str(e)}', 'error')
    
    # Read Janitorr configuration
    config_data, config_error = config_parser.read_config()
    
    # Format config as YAML for display
    config_yaml = ''
    if config_data:
        config_yaml = yaml.dump(config_data, default_flow_style=False, sort_keys=False, indent=2)
    
    return render_template('config_tabs.html', 
                         config=config_data,
                         gui_config=gui_config_data,
                         config_yaml=config_yaml,
                         config_error=config_error,
                         gui_config_error=gui_config_error,
                         config_path=janitorr_config_path)

@main_bp.route('/config/update-section', methods=['POST'])
@login_required
@admin_required
def update_config_section():
    """Update a specific section of the configuration"""
    # Get configuration path from GUI config only
    gui_config = GuiConfig()
    gui_config_data, _ = gui_config.read_config()
    
    janitorr_config_path = gui_config_data['gui']['janitorr_config_path']
    
    config_parser = ConfigParser(janitorr_config_path)
    section = request.form.get('section')
    
    try:
        # Handle GUI-specific settings separately
        if section == 'gui-service':
            # GUI config was already read above with error handling
            
            # Define all checkbox fields that need special handling
            checkbox_fields = {
                'gui.legacy_auth.enabled',
                'gui.ldap.enabled',
                'gui.ldap.use_ssl',
                'gui.ldap.verify_ssl',
                'gui.session.secure_cookies',
                'gui.session.remember_me'
            }
            
            # Update GUI settings
            for key, value in request.form.items():
                if key in ['section']:  # Skip non-config fields
                    continue
                if key.startswith('gui.'):
                    gui_config.update_setting(key, value)
            
            # Handle unchecked checkboxes (they don't appear in form data)
            for checkbox_field in checkbox_fields:
                if checkbox_field not in request.form:
                    gui_config.update_setting(checkbox_field, False)
            
            flash('GUI settings updated successfully!', 'success')
            return redirect(url_for('main.config'))
        
        # Handle Janitorr configuration settings
        config, config_error = config_parser.read_config()
        if not config:
            config = {}
        
        # Update config based on form data
        for key, value in request.form.items():
            if key in ['section']:  # Skip non-config fields
                continue
                
            # Special handling for media deletion expiration fields
            if key.endswith('.movie-expiration.default') or key.endswith('.season-expiration.default'):
                # Handle the special case of media deletion maps
                if 'application' not in config:
                    config['application'] = {}
                if 'media-deletion' not in config['application']:
                    config['application']['media-deletion'] = {}
                
                if 'movie-expiration.default' in key:
                    if 'movie-expiration' not in config['application']['media-deletion']:
                        config['application']['media-deletion']['movie-expiration'] = {}
                    # Update all percentage levels with the new default value
                    for percentage in [5, 10, 15, 20]:
                        config['application']['media-deletion']['movie-expiration'][percentage] = value
                elif 'season-expiration.default' in key:
                    if 'season-expiration' not in config['application']['media-deletion']:
                        config['application']['media-deletion']['season-expiration'] = {}
                    # Update all percentage levels with the new default value
                    for percentage in [5, 10, 15, 20]:
                        config['application']['media-deletion']['season-expiration'][percentage] = value
                continue
            
            # Skip GUI-specific settings for Janitorr config
            if key.startswith('gui.'):
                continue
                
            # Handle nested keys but be smart about certain keys that should remain as single keys
            if key == 'logging.level.com.github.schaka':
                # Special case: this should be treated as a path but 'com.github.schaka' is a single key
                if 'logging' not in config:
                    config['logging'] = {}
                if 'level' not in config['logging']:
                    config['logging']['level'] = {}
                config['logging']['level']['com.github.schaka'] = value
                continue
            elif key == 'logging.threshold.file':
                # Special case: logging threshold file setting
                if 'logging' not in config:
                    config['logging'] = {}
                if 'threshold' not in config['logging']:
                    config['logging']['threshold'] = {}
                config['logging']['threshold']['file'] = value
                continue
                
            # Handle other nested keys like 'clients.jellyfin.url'
            keys = key.split('.')
            current = config
            
            # Navigate/create nested structure
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            # Handle checkbox and boolean string values robustly
            if str(value).lower() == 'on' or str(value).lower() == 'true':
                current[keys[-1]] = True
            elif str(value).lower() == 'false':
                current[keys[-1]] = False
            elif key in request.form and value == '':
                # Don't update empty values unless explicitly set
                continue
            else:
                current[keys[-1]] = value
        
        config_parser.write_config(config)
        flash(f'{section.title()} configuration updated successfully!', 'success')
        
    except Exception as e:
        flash(f'Error updating {section} configuration: {str(e)}', 'error')
    
    return redirect(url_for('main.config'))

@main_bp.route('/config/preview', methods=['POST'])
@login_required
@admin_required
def preview_config_changes():
    """Preview configuration changes without saving them"""
    # Get configuration path from GUI config only
    gui_config = GuiConfig()
    gui_config_data, _ = gui_config.read_config()
    
    janitorr_config_path = gui_config_data['gui']['janitorr_config_path']
    
    config_parser = ConfigParser(janitorr_config_path)
    section = request.form.get('section')
    
    try:
        # --- Unified preview logic: handle YAML textarea or section form ---
        if 'config' in request.form:
            # YAML textarea diff preview
            config_text = request.form.get('config', '')
            # Get current config as Python object
            config, config_error = config_parser.read_config()
            if not config:
                config = {}
            # Normalize both current and new configs by loading and dumping
            try:
                new_config_obj = yaml.safe_load(config_text) if config_text.strip() else {}
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'YAML parse error in new config: {str(e)}'
                }), 400
            # Dump both as pretty YAML for diffing
            current_yaml = yaml.dump(config, default_flow_style=False, sort_keys=False, indent=2)
            new_yaml = yaml.dump(new_config_obj, default_flow_style=False, sort_keys=False, indent=2)
            # Generate diff
            diff = list(difflib.unified_diff(
                current_yaml.splitlines(),
                new_yaml.splitlines(),
                fromfile='Current',
                tofile='New',
                lineterm=''
            ))
            return jsonify({
                'success': True,
                'current_yaml': current_yaml,
                'new_yaml': new_yaml,
                'diff': diff
            })
        # --- Section form preview logic (as before) ---
        # Handle GUI-specific settings preview
        if section == 'gui-service':
            # GUI config was already read above
            # Create a copy for modifications
            import copy
            new_gui_config = copy.deepcopy(gui_config_data)
            # Apply GUI setting changes
            for key, value in request.form.items():
                if key in ['section']:  # Skip non-config fields
                    continue
                if key.startswith('gui.'):
                    keys = key.split('.')
                    current = new_gui_config
                    # Navigate/create nested structure
                    for k in keys[:-1]:
                        if k not in current:
                            current[k] = {}
                        current = current[k]
                    current[keys[-1]] = value
            # Convert to JSON for comparison
            import json
            new_json = json.dumps(new_gui_config, indent=2, sort_keys=True)
            return jsonify({
                'success': True,
                'new_yaml': f"# GUI Configuration (stored as JSON)\n{new_json}"
            })
        # Handle Janitorr configuration preview
        # Read current config
        config, config_error = config_parser.read_config()
        if not config:
            config = {}
        # Create a copy for modifications
        import copy
        new_config = copy.deepcopy(config)
        # Apply the same logic as update_config_section but don't save
        for key, value in request.form.items():
            if key in ['section']:  # Skip non-config fields
                continue
            # Special handling for media deletion expiration fields
            if key.endswith('.movie-expiration.default') or key.endswith('.season-expiration.default'):
                # Handle the special case of media deletion maps
                if 'application' not in new_config:
                    new_config['application'] = {}
                if 'media-deletion' not in new_config['application']:
                    new_config['application']['media-deletion'] = {}
                if 'movie-expiration.default' in key:
                    if 'movie-expiration' not in new_config['application']['media-deletion']:
                        new_config['application']['media-deletion']['movie-expiration'] = {}
                    # Update all percentage levels with the new default value
                    for percentage in [5, 10, 15, 20]:
                        new_config['application']['media-deletion']['movie-expiration'][percentage] = value
                elif 'season-expiration.default' in key:
                    if 'season-expiration' not in new_config['application']['media-deletion']:
                        new_config['application']['media-deletion']['season-expiration'] = {}
                    # Update all percentage levels with the new default value
                    for percentage in [5, 10, 15, 20]:
                        new_config['application']['media-deletion']['season-expiration'][percentage] = value
                continue
            # Skip GUI-specific settings for Janitorr config preview
            if key.startswith('gui.'):
                continue
            # Handle nested keys but be smart about certain keys that should remain as single keys
            if key == 'logging.level.com.github.schaka':
                # Special case: this should be treated as a path but 'com.github.schaka' is a single key
                if 'logging' not in new_config:
                    new_config['logging'] = {}
                if 'level' not in new_config['logging']:
                    new_config['logging']['level'] = {}
                new_config['logging']['level']['com.github.schaka'] = value
                continue
            elif key == 'logging.threshold.file':
                # Special case: logging threshold file setting
                if 'logging' not in new_config:
                    new_config['logging'] = {}
                if 'threshold' not in new_config['logging']:
                    new_config['logging']['threshold'] = {}
                new_config['logging']['threshold']['file'] = value
                continue
            # Handle other nested keys like 'clients.jellyfin.url'
            keys = key.split('.')
            current = new_config
            # Navigate/create nested structure
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            # Handle checkbox values
            if str(value).lower() == 'on' or str(value).lower() == 'true':
                current[keys[-1]] = True
            elif str(value).lower() == 'false':
                current[keys[-1]] = False
            elif key in request.form and value == '':
                # Don't update empty values unless explicitly set
                continue
            else:
                current[keys[-1]] = value
        # Convert both configs to YAML for comparison
        new_yaml = yaml.dump(new_config, default_flow_style=False, sort_keys=False, indent=2)
        return jsonify({
            'success': True,
            'new_yaml': new_yaml
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
