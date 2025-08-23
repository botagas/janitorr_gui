import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

class ConfigParserError(Exception):
    """Base exception for config parser errors"""
    pass

class ConfigParser:
    def __init__(self, config_path):
        self.config_path = Path(config_path) if config_path else None
        self._config_cache = None
        self._config_error = None
    
    def read_config(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Read and parse Janitorr's configuration file
        Returns: (config_dict, error_message)
        """
        if not self.config_path:
            return None, "No configuration path provided"
            
        try:
            if not self.config_path.exists():
                return None, f"Configuration file not found: {self.config_path}"
                
            with open(self.config_path, 'r') as f:
                self._config_cache = yaml.safe_load(f)
                self._config_error = None
                return self._config_cache, None
        except yaml.YAMLError as e:
            error_msg = f"Invalid YAML in configuration: {str(e)}"
            self._config_error = error_msg
            return None, error_msg
        except Exception as e:
            error_msg = f"Error reading configuration: {str(e)}"
            self._config_error = error_msg
            return None, error_msg
    
    def write_config(self, config_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Write configuration back to file
        Returns: (success, error_message)
        """
        if not self.config_path:
            return False, "No configuration path provided"
            
        # Create backup of existing config
        if self.config_path.exists():
            backup_path = self.config_path.with_suffix('.yml.backup')
            try:
                self.config_path.rename(backup_path)
            except Exception as e:
                return False, f"Could not create backup: {str(e)}"
            
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(config_data, f, default_flow_style=False)
            return True, None
        except Exception as e:
            # Restore backup if write fails
            if backup_path.exists():
                try:
                    backup_path.rename(self.config_path)
                except Exception:
                    return False, f"Write failed and could not restore backup: {str(e)}"
            return False, f"Could not write configuration: {str(e)}"
    
    def get_jellyfin_config(self) -> Dict[str, Any]:
        """Get Jellyfin-specific configuration"""
        config, error = self.read_config()
        if error or not config:
            return {}
        return config.get('clients', {}).get('jellyfin', {})
    
    def get_deletion_rules(self) -> Dict[str, Any]:
        """Get media deletion rules"""
        config, error = self.read_config()
        if error or not config:
            return {
                'media_deletion': {},
                'tag_based_deletion': {},
                'episode_deletion': {}
            }
        return {
            'media_deletion': config.get('application', {}).get('media-deletion', {}),
            'tag_based_deletion': config.get('application', {}).get('tag-based-deletion', {}),
            'episode_deletion': config.get('application', {}).get('episode-deletion', {})
        }
    
    def update_deletion_rules(self, rules: Dict[str, Any]):
        """Update media deletion rules"""
        config = self.read_config()
        
        if 'application' not in config:
            config['application'] = {}
            
        for rule_type, rule_config in rules.items():
            config['application'][rule_type.replace('_', '-')] = rule_config
            
        self.write_config(config)
