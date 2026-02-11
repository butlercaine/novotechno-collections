"""
Device code flow implementation using MSAL for Python.
Supports device authorization grant without browser requirement.
"""

import time
import logging
from typing import Dict, Optional, Callable
from msal import PublicClientApplication


logger = logging.getLogger(__name__)


class DeviceCodeFlow:
    """MSAL-based device code flow for headless authentication."""
    
    def __init__(self, client_id: str, authority: str, scopes: list, **kwargs):
        """
        Initialize device code flow client.
        
        Args:
            client_id: Azure AD application client ID
            authority: Authority URL (e.g., https://login.microsoftonline.com/common)
            scopes: List of scopes to request
            **kwargs: Additional MSAL parameters
        """
        self.client_id = client_id
        self.authority = authority
        self.scopes = scopes
        self.app = PublicClientApplication(
            client_id=client_id,
            authority=authority,
            **kwargs
        )
        self._last_device_flow = None
        
    def initiate_flow(self) -> Dict:
        """
        Initiate device code flow and return device authorization response.
        
        Returns:
            Dict containing device_code, user_code, verification_uri, etc.
        """
        logger.info("Initiating device code flow")
        
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        
        if "user_code" not in flow:
            raise ValueError(
                f"Failed to create device flow. Err: {flow.get('error')}, "
                f"Description: {flow.get('error_description')}"
            )
        
        self._last_device_flow = flow
        
        logger.info(f"Device flow initiated. User code: {flow['user_code']}")
        return flow
    
    def get_authorization_url(self) -> str:
        """Get the verification URI for user authorization."""
        if not self._last_device_flow:
            raise RuntimeError("No active device flow. Call initiate_flow() first.")
        return self._last_device_flow["verification_uri"]
    
    def get_user_code(self) -> str:
        """Get the user code for authorization."""
        if not self._last_device_flow:
            raise RuntimeError("No active device flow. Call initiate_flow() first.")
        return self._last_device_flow["user_code"]
    
    def poll_for_token(
        self, 
        flow: Optional[Dict] = None,
        interval: int = 5,
        timeout: int = 1800
    ) -> Optional[Dict]:
        """
        Poll for token after user authorization.
        
        Args:
            flow: Device flow dict (uses last flow if None)
            interval: Polling interval in seconds
            timeout: Maximum time to poll in seconds
            
        Returns:
            Token response dict or None if timeout
        """
        if flow is None:
            flow = self._last_device_flow
            
        if flow is None:
            raise RuntimeError("No device flow provided or previously initiated.")
        
        logger.info("Starting token polling")
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                logger.warning("Device code flow timed out")
                return None
            
            try:
                result = self.app.acquire_token_by_device_flow(flow)
                
                if "access_token" in result:
                    logger.info("Token acquired successfully")
                    return result
                
                error = result.get("error", "")
                
                if error == "authorization_pending":
                    logger.debug("Authorization pending, waiting...")
                    time.sleep(interval)
                    continue
                elif error == "slow_down":
                    logger.debug("Server requested slow down")
                    time.sleep(interval + 5)
                    continue
                elif error == "expired_token":
                    logger.error("Device code expired")
                    raise Exception("Device code expired")
                elif error == "access_denied":
                    logger.error("User denied authorization")
                    raise Exception("User denied authorization")
                else:
                    logger.error(f"Unexpected error: {error}")
                    raise Exception(f"Authentication failed: {error}")
                    
            except Exception as e:
                logger.error(f"Error during token polling: {e}")
                raise
    
    def authenticate(
        self,
        prompt_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict:
        """
        Complete authentication flow.
        
        Args:
            prompt_callback: Callback to display user code and URI
            
        Returns:
            Token response with access_token, refresh_token, etc.
        """
        flow = self.initiate_flow()
        
        user_code = flow["user_code"]
        auth_url = flow["verification_uri"]
        
        if prompt_callback:
            prompt_callback(user_code, auth_url)
        else:
            print(f"\nTo sign in, use a web browser to open the page {auth_url}")
            print(f"and enter the code {user_code} to authenticate.\n")
        
        return self.poll_for_token(flow)
    
    def get_token_silent(self) -> Optional[Dict]:
        """
        Try to get token silently from cache (no user interaction).
        
        Returns:
            Token response or None if no cached token
        """
        accounts = self.app.get_accounts()
        
        if not accounts:
            logger.debug("No cached accounts found")
            return None
        
        # Use first account
        account = accounts[0]
        logger.info(f"Attempting silent auth for account: {account.get('username')}")
        
        result = self.app.acquire_token_silent(
            scopes=self.scopes,
            account=account
        )
        
        if "access_token" in result:
            logger.info("Silent authentication successful")
            return result
        
        return None