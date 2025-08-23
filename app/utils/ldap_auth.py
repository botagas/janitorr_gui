import ldap
import os
from flask_login import UserMixin
from flask import current_app

class User(UserMixin):
    def __init__(self, username, is_admin=False):
        self.id = username
        self.is_admin = is_admin

class LdapAuthenticator:
    def __init__(self):
        # Read LDAP configuration from environment variables
        self.ldap_server = os.getenv('GUI_LDAP_SERVER', 'localhost')
        self.ldap_port = int(os.getenv('GUI_LDAP_PORT', '389'))
        self.use_ssl = os.getenv('GUI_LDAP_USE_SSL', 'false').lower() == 'true'
        self.verify_ssl = os.getenv('GUI_LDAP_VERIFY_SSL', 'true').lower() == 'true'
        
        # Build LDAP URI
        protocol = 'ldaps' if self.use_ssl else 'ldap'
        self.ldap_uri = f"{protocol}://{self.ldap_server}:{self.ldap_port}"
        
        # LDAP structure configuration
        self.base_dn = os.getenv('GUI_LDAP_BASE_DN', 'dc=yunohost,dc=org')
        self.user_filter = os.getenv('GUI_LDAP_USER_FILTER', 'uid={}')
        self.bind_dn = os.getenv('GUI_LDAP_BIND_DN', '')
        self.bind_password = os.getenv('GUI_LDAP_BIND_PASSWORD', '')
        self.admin_group = os.getenv('GUI_LDAP_ADMIN_GROUP', 'cn=admins,ou=groups,dc=yunohost,dc=org')
        
        # Group membership detection strategy (optional optimization)
        self.group_strategy = os.getenv('GUI_LDAP_GROUP_STRATEGY', 'auto')  # auto, posix, groupOfNames, groupOfUniqueNames
        
        # Derive user DN pattern from base DN and user filter
        if '{}' in self.user_filter:
            # For YunoHost: uid={} should become uid=username,ou=users,dc=yunohost,dc=org
            if self.user_filter == 'uid={}':
                self.user_dn_pattern = f"uid={{}},ou=users,{self.base_dn}"
            else:
                # For other filters, use as-is with base DN
                self.user_dn_pattern = f"{self.user_filter},{self.base_dn}"
        else:
            self.user_dn_pattern = f"uid={{}},ou=users,{self.base_dn}"

    def _check_admin(self, conn, user_dn, username):
        """Check if user is in admin group"""
        try:
            if not self.admin_group:
                # No admin group configured, no admin privileges
                return False
            
            # Use specific strategy if configured, otherwise try all patterns
            if self.group_strategy == 'posix':
                return self._check_posix_group(conn, username)
            elif self.group_strategy == 'groupOfNames':
                return self._check_group_of_names(conn, user_dn)
            elif self.group_strategy == 'groupOfUniqueNames':
                return self._check_group_of_unique_names(conn, user_dn)
            else:
                # Auto-detection: try all patterns
                return (self._check_posix_group(conn, username) or
                       self._check_group_of_names(conn, user_dn) or
                       self._check_group_of_unique_names(conn, user_dn))
                
        except ldap.LDAPError as e:
            current_app.logger.error(f"Error checking admin status: {str(e)}")
            return False

    def _check_posix_group(self, conn, username):
        """Check POSIX group membership (YunoHost style)"""
        try:
            result = conn.search_s(
                self.admin_group,
                ldap.SCOPE_BASE,
                f"(&(objectClass=posixGroup)(memberUid={username}))"
            )
            return bool(result)
        except ldap.LDAPError:
            return False

    def _check_group_of_names(self, conn, user_dn):
        """Check groupOfNames membership (Standard LDAP)"""
        try:
            result = conn.search_s(
                self.admin_group,
                ldap.SCOPE_BASE,
                f"(&(objectClass=groupOfNames)(member={user_dn}))"
            )
            return bool(result)
        except ldap.LDAPError:
            return False

    def _check_group_of_unique_names(self, conn, user_dn):
        """Check groupOfUniqueNames membership (OpenLDAP)"""
        try:
            result = conn.search_s(
                self.admin_group,
                ldap.SCOPE_BASE,
                f"(&(objectClass=groupOfUniqueNames)(uniqueMember={user_dn}))"
            )
            return bool(result)
        except ldap.LDAPError:
            return False

    def authenticate(self, username, password):
        current_app.logger.info(f"Starting LDAP authentication for user: {username}")
        current_app.logger.debug(f"LDAP URI: {self.ldap_uri}")
        current_app.logger.debug(f"Base DN: {self.base_dn}")
        current_app.logger.debug(f"User filter: {self.user_filter}")
        
        try:
            # Initialize connection
            conn = ldap.initialize(self.ldap_uri)
            conn.protocol_version = ldap.VERSION3
            
            # Set SSL/TLS options if needed
            if self.use_ssl and not self.verify_ssl:
                ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
            
            # Determine user DN
            user_dn = self.user_dn_pattern.format(username)
            current_app.logger.debug(f"Constructed user DN: {user_dn}")
            
            # If bind DN is provided, use it for initial connection
            if self.bind_dn and self.bind_password:
                current_app.logger.debug("Using bind DN for initial connection")
                try:
                    conn.simple_bind_s(self.bind_dn, self.bind_password)
                    
                    # Search for user to validate existence
                    search_filter = f"(uid={username})"
                    current_app.logger.debug(f"Searching for user with filter: {search_filter}")
                    result = conn.search_s(
                        self.base_dn,
                        ldap.SCOPE_SUBTREE,
                        search_filter
                    )
                    
                    if not result:
                        current_app.logger.warning(f"User {username} not found in LDAP")
                        return None
                    
                    # Get the actual user DN from search result
                    user_dn = result[0][0]
                    current_app.logger.debug(f"Found user DN: {user_dn}")
                    
                except ldap.LDAPError as e:
                    current_app.logger.error(f"LDAP bind with service account failed: {e}")
                    return None
            else:
                current_app.logger.debug("No bind DN configured, using direct user authentication")
            
            # Now try to bind as the user to verify password
            current_app.logger.debug(f"Attempting to authenticate user: {user_dn}")
            try:
                user_conn = ldap.initialize(self.ldap_uri)
                user_conn.protocol_version = ldap.VERSION3
                if self.use_ssl and not self.verify_ssl:
                    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                user_conn.simple_bind_s(user_dn, password)
                user_conn.unbind_s()
                current_app.logger.info(f"Password authentication successful for {username}")
            except ldap.INVALID_CREDENTIALS:
                current_app.logger.warning(f"Invalid credentials for user {username}")
                return None
            except ldap.LDAPError as e:
                current_app.logger.error(f"LDAP authentication error for {username}: {e}")
                return None

            # Check if user is in admin group
            is_admin = self._check_admin(conn, user_dn, username)
            current_app.logger.info(f"User {username} authenticated successfully, admin status: {is_admin}")
            
            return User(username, is_admin)
            
        except ldap.LDAPError as e:
            current_app.logger.error(f"LDAP error: {e}")
            return None
        finally:
            if 'conn' in locals():
                try:
                    conn.unbind_s()
                except:
                    pass
