import subprocess
import pwd
import os

def validate_service_config(service_name: str, service_user: str) -> bool:
    """
    Validate the service configuration by checking:
    1. Service name is valid
    2. User exists and has appropriate permissions
    
    Args:
        service_name: Name of the systemd service
        service_user: User under which the service will run
        
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    # Validate service name
    if not service_name or not service_name.replace('-', '').isalnum():
        return False
        
    try:
        # Check if service exists
        result = subprocess.run(
            ['systemctl', 'status', service_name],
            capture_output=True,
            text=True
        )
        
        # Check if user exists
        try:
            pwd.getpwnam(service_user)
        except KeyError:
            return False
            
        return True
    except (subprocess.CalledProcessError, OSError):
        return False
