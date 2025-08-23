import requests
from flask import current_app

import urllib.parse

class JellyfinClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-MediaBrowser-Token': api_key,
            'Content-Type': 'application/json'
        }
    
    def search_item(self, title):
        """Search for an item by title"""
        if not title:
            current_app.logger.warning("Empty title provided to search")
            return None
            
        encoded_title = urllib.parse.quote(title)
        # Build query with more specific parameters
        url = (f"{self.base_url}/Items?"
               f"SearchTerm={encoded_title}"
               "&Recursive=true"
               "&IncludeItemTypes=Movie,Series"
               "&Fields=Path,Name,Id,Type,ImageTags"
               "&Limit=10")  # Get more results to find better matches
        
        try:
            current_app.logger.debug(f"Searching Jellyfin for title: {title}")
            current_app.logger.debug(f"Search URL: {url}")
            
            response = requests.get(url, headers=self.headers)
            if not response.ok:
                current_app.logger.error(f"Jellyfin search failed for '{title}': {response.status_code} {response.text}")
                return None
            
            data = response.json()
            items = data.get('Items', [])
            
            if not items:
                current_app.logger.warning(f"No items found for title: '{title}'")
                return None
                
            # Log what we found to help debug
            current_app.logger.debug(f"Found {len(items)} potential matches for '{title}':")
            for idx, item in enumerate(items):
                current_app.logger.debug(
                    f"  {idx + 1}. Name='{item.get('Name')}' "
                    f"ID={item.get('Id')} "
                    f"Type={item.get('Type')}"
                )
                
            # First try to find an exact match (case insensitive)
            for item in items:
                item_name = item.get('Name', '')
                item_id = item.get('Id', '')
                current_app.logger.debug(f"Checking item: '{item_name}' with ID: '{item_id}' (length: {len(item_id)})")
                if item_name.lower() == title.lower():
                    current_app.logger.info(f"Found exact match for '{title}': '{item_name}' (ID: {item_id})")
                    return item
                    
            # If no exact match, try to find the best partial match
            # Prefer items that start with the search term
            for item in items:
                item_name = item.get('Name', '')
                item_id = item.get('Id', '')
                if item_name.lower().startswith(title.lower()):
                    current_app.logger.info(f"Found prefix match for '{title}': '{item_name}' (ID: {item_id}, length: {len(item_id)})")
                    return item
                    
            # No good match found, take the first result but log a warning
            best_match = items[0]
            best_match_id = best_match.get('Id', '')
            current_app.logger.warning(
                f"No exact or prefix match found for '{title}', using first result: "
                f"'{best_match.get('Name')}' (ID={best_match_id}, length: {len(best_match_id)})"
            )
            return best_match
            
        except Exception as e:
            current_app.logger.error(f"Error during Jellyfin search for '{title}': {str(e)}")
            return None
    
    def get_item_by_id(self, item_id):
        """Get item information directly by ID"""
        if not item_id:
            current_app.logger.warning("Attempted to get item with empty ID")
            return None
        
        url = f"{self.base_url}/Items/{item_id}"
        try:
            response = requests.get(url, headers=self.headers)
            if not response.ok:
                current_app.logger.error(f"Jellyfin get_item_by_id failed for '{item_id}': {response.status_code} {response.text}")
                return None
            return response.json()
        except Exception as e:
            current_app.logger.error(f"Error getting Jellyfin item '{item_id}': {str(e)}")
            return None

    def get_item_info(self, title):
        """Get information about a media item by its title"""
        if not title:
            return None

        # Search by title since that's what we get from logs
        return self.search_item(title)
    
    def get_item_image(self, item_info, image_type="Primary"):
        """Get the image data for an item"""
        if not item_info or not item_info.get('ImageTags', {}).get(image_type):
            return None
            
        item_id = item_info['Id']
        url = f"{self.base_url}/Items/{item_id}/Images/{image_type}"
        
        try:
            response = requests.get(url, headers=self.headers)
            if response.ok:
                return response.content
        except Exception:
            return None
        
        return None
    
    def get_libraries(self):
        """Get all media libraries"""
        url = f"{self.base_url}/Library/MediaFolders"
        response = requests.get(url, headers=self.headers)
        return response.json()['Items'] if response.ok else []
