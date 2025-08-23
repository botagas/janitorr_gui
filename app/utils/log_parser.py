import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

class LogParser:
    def __init__(self, log_path):
        self.log_path = Path(log_path)
        # Updated pattern to match Janitorr's log format, capturing the age in days
        self.deletion_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})T.*?\[.*?\] .*?SonarrRestService\s*: Deleting (.*?) \[(\d+)}]')
    
    def _parse_duration_to_days(self, duration_str):
        """
        Parse duration string like '120d', '4w', '2m' to days
        Returns number of days or None if invalid
        """
        if not duration_str or not isinstance(duration_str, str):
            return None
            
        duration_str = str(duration_str).strip().lower()
        if not duration_str:
            return None
            
        # Extract number and unit
        import re
        match = re.match(r'^(\d+)([dwmy]?)$', duration_str)
        if not match:
            return None
            
        number = int(match.group(1))
        unit = match.group(2) or 'd'  # default to days
        
        # Convert to days
        if unit == 'd':
            return number
        elif unit == 'w':
            return number * 7
        elif unit == 'm':
            return number * 30  # approximate
        elif unit == 'y':
            return number * 365  # approximate
        
        return None
    
    def get_scheduled_deletions(self, deletion_config=None):
        """
        Parse log file and return media scheduled for deletion from the last scan
        Args:
            deletion_config: Dictionary containing media-deletion settings from config
        Returns: (deletions_dict, error_message)
        """
        if not self.log_path:
            return {}, "No log file path provided"
            
        if not self.log_path.exists():
            return {}, f"Log file not found: {self.log_path}"
        
        try:
            # Get default deletion time from config
            default_deletion_days = None
            if deletion_config:
                # Handle both key formats: media_deletion and media-deletion
                media_deletion = deletion_config.get('media_deletion') or deletion_config.get('media-deletion')
                if media_deletion and isinstance(media_deletion, dict):
                    # Check for different expiration types (movie, season, or generic time)
                    if 'movie-expiration' in media_deletion:
                        # Get the largest expiration time for movies
                        movie_exp = media_deletion['movie-expiration']
                        if isinstance(movie_exp, dict):
                            # Get all expiration values and find the maximum
                            expiration_values = []
                            for percent, duration in movie_exp.items():
                                days = self._parse_duration_to_days(duration)
                                if days is not None:
                                    expiration_values.append(days)
                            if expiration_values:
                                default_deletion_days = max(expiration_values)
                    elif 'season-expiration' in media_deletion:
                        # Get the largest expiration time for seasons
                        season_exp = media_deletion['season-expiration']
                        if isinstance(season_exp, dict):
                            expiration_values = []
                            for percent, duration in season_exp.items():
                                days = self._parse_duration_to_days(duration)
                                if days is not None:
                                    expiration_values.append(days)
                            if expiration_values:
                                default_deletion_days = max(expiration_values)
                    elif 'time' in media_deletion:
                        # Generic time field
                        default_deletion_days = self._parse_duration_to_days(media_deletion['time'])
                elif isinstance(media_deletion, str):
                    # Direct string value
                    default_deletion_days = self._parse_duration_to_days(media_deletion)
                    
            # Read all lines first
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
            
            # Find the last scan by looking for the last batch of deletions
            deletions = defaultdict(list)
            last_scan_date = None
            seen_titles = set()  # To prevent duplicates within the same scan
            
            # Process lines in reverse to find the last scan
            for line in reversed(lines):
                match = self.deletion_pattern.search(line)
                if match:
                    log_date_str = match.group(1)
                    title = match.group(2)
                    age_days = int(match.group(3))
                    
                    # Parse the log date
                    log_date = datetime.strptime(log_date_str, '%Y-%m-%d').date()
                    
                    # If this is our first match, set it as the last scan date
                    if last_scan_date is None:
                        last_scan_date = log_date
                    # If we've moved to a different date, we've found all entries from the last scan
                    elif log_date != last_scan_date:
                        break
                    
                    # Skip if we've already seen this title in this scan
                    if title in seen_titles:
                        continue
                        
                    seen_titles.add(title)
                    
                    # Calculate when the media was added based on its age
                    added_date = log_date - timedelta(days=age_days)
                    
                    # Calculate days until deletion
                    days_until_deletion = None
                    deletion_date = None
                    if default_deletion_days:
                        days_until_deletion = default_deletion_days - age_days
                        deletion_date = added_date + timedelta(days=default_deletion_days)
                    
                    deletions[log_date].append({
                        'title': title,
                        'age_days': age_days,
                        'added_date': added_date.isoformat(),
                        'days_until_deletion': days_until_deletion,
                        'deletion_date': deletion_date.isoformat() if deletion_date else None
                    })
            
            return dict(deletions), None
        except Exception as e:
            return {}, f"Error reading log file: {str(e)}"
    
    def tail_log(self, num_lines=100):
        """Get the last N lines of the log file"""
        if not self.log_path.exists():
            return []
            
        with open(self.log_path, 'r') as f:
            lines = f.readlines()
            return lines[-num_lines:]
