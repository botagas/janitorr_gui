from dataclasses import dataclass
from typing import Optional
import requests
import subprocess
from pathlib import Path
from app.utils.config_parser import ConfigParser

@dataclass
class SystemStatus:
    config_available: bool
    config_error: Optional[str]
    logs_available: bool
    logs_error: Optional[str]
    jellyfin_available: bool
    jellyfin_error: Optional[str]
    service_running: bool
    service_error: Optional[str]

class StatusChecker:
    def __init__(self, config_path: Optional[str], log_path: Optional[str], jellyfin_url: Optional[str]):
        self.config_path = Path(config_path) if config_path else None
        self.log_path = Path(log_path) if log_path else None
        self.jellyfin_url = jellyfin_url

    def check_all(self) -> SystemStatus:
        """Check availability of all required components"""
        config_status, config_error = self._check_config()
        logs_status, logs_error = self._check_logs()
        jellyfin_status, jellyfin_error = self._check_jellyfin()
        service_status, service_error = self._check_service()

        return SystemStatus(
            config_available=config_status,
            config_error=config_error,
            logs_available=logs_status,
            logs_error=logs_error,
            jellyfin_available=jellyfin_status,
            jellyfin_error=jellyfin_error,
            service_running=service_status,
            service_error=service_error
        )

    def _check_config(self) -> tuple[bool, Optional[str]]:
        """Check if configuration file is accessible"""
        if not self.config_path:
            return False, "Configuration path not set"
        
        try:
            return self.config_path.exists(), None if self.config_path.exists() else "Configuration file not found"
        except Exception as e:
            return False, f"Error checking configuration: {str(e)}"

    def _check_logs(self) -> tuple[bool, Optional[str]]:
        """Check if log file is accessible"""
        if not self.log_path:
            return False, "Log path not set"
        
        try:
            return self.log_path.exists(), None if self.log_path.exists() else "Log file not found"
        except Exception as e:
            return False, f"Error checking logs: {str(e)}"

    def _check_jellyfin(self) -> tuple[bool, Optional[str]]:
        """Check if Jellyfin is accessible and properly configured"""
        # First check if we have config
        if not self.config_path:
            return False, "Configuration not available"
            
        try:
            config_parser = ConfigParser(str(self.config_path))
            config = config_parser.read_config()[0]  # Using [0] since read_config returns tuple(config, error)
            
            if not config or 'clients' not in config or 'jellyfin' not in config['clients']:
                return False, "Jellyfin configuration not found"
                
            jellyfin_config = config['clients']['jellyfin']
            if not jellyfin_config.get('enabled'):
                return False, "Jellyfin is disabled in configuration"
                
            if not jellyfin_config.get('url') or not jellyfin_config.get('api-key'):
                return False, "Jellyfin URL or API key not configured"
            
            # Then check connectivity
            try:
                response = requests.get(
                    f"{jellyfin_config['url'].rstrip('/')}/System/Info/Public",
                    headers={'X-MediaBrowser-Token': jellyfin_config['api-key']},
                    timeout=5
                )
                return response.ok, None if response.ok else f"Jellyfin returned status {response.status_code}"
            except requests.RequestException as e:
                return False, f"Could not connect to Jellyfin: {str(e)}"
                
        except Exception as e:
            return False, f"Error checking Jellyfin configuration: {str(e)}"

    def _check_service(self) -> tuple[bool, Optional[str]]:
        """Check if Janitorr is properly configured and running"""
        try:
            # First check if we have the basic configuration paths
            if not self.config_path or not self.log_path:
                return False, "Configuration required in GUI settings"
            
            # Check if the config file exists
            if not self.config_path.exists():
                return False, f"Janitorr config file not found: {self.config_path}"
            
            # Try to load the configuration to verify it's valid
            config_parser = ConfigParser(str(self.config_path))
            config, config_error = config_parser.read_config()
            
            if not config:
                return False, f"Could not load Janitorr configuration: {config_error or 'Unknown error'}"
            
            # At this point, Janitorr is "configured" - now check if it's running
            # Try common service names for Janitorr
            service_names = ['janitorr', 'janitorr.service']
            
            for service_name in service_names:
                try:
                    result = subprocess.run(
                        ['systemctl', 'is-active', service_name],
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0 and result.stdout.strip() == 'active':
                        return True, None  # Service is running
                        
                except subprocess.CalledProcessError:
                    continue  # Try next service name
            
            # Service is configured but not running
            return False, "Configured, not running"
            
        except Exception as e:
            return False, f"Error checking service: {str(e)}"
