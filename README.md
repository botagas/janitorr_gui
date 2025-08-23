# Janitorr GUI

A simple Flask-based GUI for Janitorr that shows scheduled media deletions and allows configuration management.

## System Requirements

- Python 3.8 or newer
- Janitorr installed and running
- Access to Janitorr's configuration and log files
- Jellyfin server (optional, for media thumbnails)

## Features

- View media scheduled for deletion with thumbnails from Jellyfin
- Modify Janitorr configuration through a web interface
- Monitor Janitorr logs in real-time
- Integration with Jellyfin API for media information and thumbnails

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create configuration file:
```bash
# Copy the example configuration
cp .env.example .env

# Edit the configuration file
nano .env  # or use your preferred editor
```

Your `.env` file should contain:
```env
# GUI Settings
GUI_AUTO_REFRESH=60
GUI_THEME=dark
JANITORR_CONFIG_PATH=/path/to/janitorr/application.yml
JANITORR_LOG_PATH=/path/to/janitorr/janitorr.log
JANITORR_WORKING_DIR=/path/to/janitorr

# Authentication (see dev/LDAP_CONFIGURATION_EXAMPLES.md for LDAP setup)
GUI_AUTH_MODE=none
GUI_SESSION_SECRET_KEY=change-this-secret-key-in-production

# For production, use GUI_AUTH_MODE=ldap or legacy
```

## Authentication

The GUI features intelligent authentication that automatically determines the mode based on which methods you enable:

- **Enable Legacy Auth only** → Legacy Authentication  
- **Enable LDAP only** → LDAP Authentication
- **Enable both** → LDAP with Legacy Fallback
- **Enable neither** → No Authentication (development only)

### Configuration
```env
# Simply enable the authentication methods you want:
GUI_LEGACY_AUTH_ENABLED=true  # Enable username/password auth
GUI_LDAP_ENABLED=true         # Enable LDAP auth

# The system automatically uses "LDAP with Legacy Fallback" when both are enabled
# No need to manually set GUI_AUTH_MODE unless you want to override the auto-detection
```

For detailed LDAP configuration examples, see `dev/LDAP_CONFIGURATION_EXAMPLES.md`.

## Development

### Configuration
All configuration is done via environment variables in the `.env` file. See `.env.example` for all available options.

### Development Files
The `dev/` directory contains:
- LDAP configuration examples
- Authentication documentation  
- Testing scripts for LDAP connectivity

### LDAP Testing
To test LDAP connectivity:
```bash
python dev/ldap_test.py
python dev/ldap_test.py <username> <password>  # Test specific user
```

4. Run the development server:
```bash
flask run
```

The application will be available at `http://localhost:5000`

## Production Deployment

For production deployment, we recommend using gunicorn with a reverse proxy (like nginx). Follow these steps:

1. Clone the repository:
```bash
sudo mkdir -p /var/www/janitorr-gui
sudo git clone https://github.com/Schaka/janitorr_gui.git /var/www/janitorr-gui
```

2. Create a dedicated user:
```bash
sudo useradd -r -s /bin/false janitorr
sudo chown -R janitorr:janitorr /var/www/janitorr-gui
```

3. Set up the Python virtual environment:
```bash
cd /var/www/janitorr-gui
python3 -m venv venv
# Make sure venv belongs to janitorr user
sudo chown -R janitorr:janitorr venv/
# Activate venv and install dependencies
sudo -u janitorr bash -c 'source venv/bin/activate && pip install -r requirements.txt'
```

4. Generate a secret key and install the systemd service:
```bash
# Generate a secret key
sudo -u janitorr bash -c 'source venv/bin/activate && python scripts/generate_key.py' > secret_key.txt
```bash
# Copy the service file
sudo cp contrib/janitorr-gui.service /etc/systemd/system/

# Create log directory
sudo mkdir -p /var/log/janitorr-gui
sudo chown janitorr:janitorr /var/log/janitorr-gui

# Edit the service file to set your configuration
sudo nano /etc/systemd/system/janitorr-gui.service

# Reload systemd and start the service
sudo systemctl daemon-reload
sudo systemctl enable janitorr-gui
sudo systemctl start janitorr-gui
```

5. Set up nginx as a reverse proxy (recommended):
```nginx
server {
    listen 80;
    server_name janitorr-gui.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8977;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The service will run on port 8977 by default. You can change this in the systemd service file.

## Configuration

The Janitorr GUI uses two separate configuration systems:

### 1. Application Configuration (Required)

These settings are required for the GUI to function and are configured via environment variables or a `.env` file:

```env
# Required: Flask application secret key for session security
SECRET_KEY=your-generated-secret-key

# Required: Path to Janitorr's configuration file
JANITORR_CONFIG_PATH=/opt/janitorr/application.yml

# Required: Path to Janitorr's log file
JANITORR_LOG_PATH=/var/log/janitorr/janitorr.log

# Optional: Janitorr working directory (default: /opt/janitorr)
JANITORR_WORKING_DIR=/opt/janitorr

# Optional: GUI auto-refresh interval in seconds (default: 30)
GUI_AUTO_REFRESH=30

# Optional: GUI theme (default: dark)
GUI_THEME=dark
```

### 2. GUI Settings

GUI-specific settings are managed separately from Janitorr's configuration and stored in `.env` file. These settings control:

- Auto-refresh intervals for the dashboard
- Theme preferences (dark/light)
- GUI-specific paths and directories

You can modify these settings through the Configuration tab in the web interface, or by editing the `.env` file directly.

### Environment Variables Priority

The configuration system follows this priority order:
1. Environment variables set in the system
2. Variables defined in the `.env` file
3. Default values

For production deployments using systemd, set the environment variables in the service file rather than using a `.env` file.

### Janitorr Configuration Integration

The GUI provides a web interface to modify Janitorr's configuration file directly. This includes:

- Service settings (Jellyfin, Sonarr, Radarr, etc.)
- Media retention policies
- Logging configuration
- Cleanup schedules

**Important**: Changes to Janitorr's configuration through the GUI require a restart of the Janitorr service to take effect.

## Development

The project structure:

```
janitorr_gui/
├── app/
│   ├── __init__.py
│   ├── routes.py
│   ├── config.py
│   ├── jellyfin_client.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   └── config.html
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── main.js
│   └── utils/
│       ├── config_parser.py
│       └── log_parser.py
├── requirements.txt
└── run.py
```
