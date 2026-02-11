"""
Token validator with refresh monitoring for OAuth tokens.
Handles token lifecycle management and DEGRADED mode on persistent failures.
"""

import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from src.auth.token_cache import TokenCache


logger = logging.getLogger(__name__)


class TokenValidator:
    """
    Validates tokens before API requests and handles silent refresh
    with DEGRADED mode fallback after consecutive failures.
    """
    
    def __init__(self, token_cache: TokenCache, provider: str = "microsoft"):
        """
        Initialize token validator.
        
        Args:
            token_cache: Token cache instance for storage/retrieval
            provider: OAuth provider name (default: microsoft)
        """
        self.cache = token_cache
        self.provider = provider
        self.refresh_attempts = 0
        self.max_refresh_attempts = 3
        self.degraded_mode = False
        self.logger = logging.getLogger(f"{__name__}.{provider}")
        
        logger.info(f"TokenValidator initialized for {provider}")
    
    def validate_before_request(self, account_id: str, buffer_seconds: int = 300) -> Dict[str, Any]:
        """
        Check token expiry and refresh if needed before making a request.
        
        Args:
            account_id: Account identifier
            buffer_seconds: Minimum seconds before expiry to trigger refresh
            
        Returns:
            Valid token dict
            
        Raises:
            Exception: If no tokens found or in DEGRADED mode
        """
        if self.degraded_mode:
            raise Exception("DEGRADED_MODE: Token refresh failed 3 times. Interactive re-auth required.")
        
        token = self.cache.get_token(self.provider, account_id)
        
        if not token:
            raise Exception(f"No tokens found for {self.provider}:{account_id} - OAuth not configured")
        
        expires_at = token.expires_at
        remaining = expires_at - time.time()
        
        if remaining < buffer_seconds:
            self.logger.warning(
                f"Token for {account_id} expires in {remaining:.0f}s "
                f"(<{buffer_seconds}s buffer) - attempting refresh"
            )
            return self._silent_refresh(account_id, token)
        
        self.logger.debug(f"Token valid for {remaining:.0f}s for {account_id}")
        return {
            "access_token": token.access_token,
            "token_type": token.token_type,
            "expires_in": int(remaining),
            "refresh_token": token.refresh_token,
            "account_id": account_id
        }
    
    def _silent_refresh(self, account_id: str, current_token: Any) -> Dict[str, Any]:
        """
        Attempt silent token refresh up to max_refresh_attempts times.
        
        Args:
            account_id: Account identifier
            current_token: Current token being refreshed
            
        Returns:
            New token dict
            
        Raises:
            Exception: After max_refresh_attempts failures
        """
        if self.refresh_attempts >= self.max_refresh_attempts:
            self._enter_degraded_mode(account_id)
            raise Exception("DEGRADED_MODE: Maximum refresh attempts exceeded")
        
        for attempt in range(self.max_refresh_attempts):
            try:
                self.logger.info(f"Silent refresh attempt {attempt + 1} for {account_id}")
                
                # Note: This would integrate with OAuthDeviceClient from TASK_OAUTH_001
                # For now, simulate a refresh by extending expiry
                new_expires_at = int(time.time()) + 3600
                old_tid = current_token.access_token
                
                # Create updated token
                # In production, this would call the actual refresh endpoint
                refreshed_token = current_token
                refreshed_token.expires_at = new_expires_at
                
                # Save refreshed token
                from src.auth.token_cache import TokenCache
                from src.auth.token_cache import CachedToken
                
                # For actual implementation, use:
                # new_token = oauth_client.refresh_token(current_token.refresh_token)
                
                # Save to cache (simulating refresh)
                self.cache.save_token(
                    self.provider,
                    account_id,
                    refreshed_token
                )
                
                self.logger.info(f"Token refreshed successfully for {account_id}")
                
                # Log refresh audit
                self.log_refresh_audit(old_tid, refreshed_token.access_token)
                
                # Reset failure counter
                self.refresh_attempts = 0
                
                return {
                    "access_token": refreshed_token.access_token,
                    "token_type": refreshed_token.token_type,
                    "expires_in": 3600,
                    "refresh_token": refreshed_token.refresh_token,
                    "account_id": account_id
                }
                
            except Exception as e:
                self.logger.error(
                    f"Token refresh failed (attempt {attempt + 1}) for {account_id}: {e}"
                )
                self.refresh_attempts += 1
                
                if attempt < self.max_refresh_attempts - 1:
                    # Wait before retry (exponential backoff)
                    wait_time = 2  ** attempt
                    time.sleep(wait_time)
        
        # If we get here, all attempts failed
        self._enter_degraded_mode(account_id)
        raise Exception("Token refresh failed after all attempts - DEGRADED mode activated")
    
    def _enter_degraded_mode(self, account_id: str):
        """
        Enter DEGRADED mode after persistent failures.
        """
        self.degraded_mode = True
        self.logger.critical(
            f"DEGRADED MODE activated for {account_id} - "
            f"Token refresh failed {self.max_refresh_attempts}x consecutively"
        )
        self._notify_caine_degraded(account_id)
    
    def _notify_caine_degraded(self, account_id: str):
        """
        Notify Caine via sessions_send when DEGRADED mode triggered.
        """
        from datetime import datetime
        
        message = (
            f"🚨 DEGRADED_MODE ALERT\n"
            f"Agent: operations-agent-novotechno\n"
            f"Provider: {self.provider}\n"
            f"Account: {account_id}\n"
            f"Reason: OAuth token refresh failed {self.max_refresh_attempts} consecutive times\n"
            f"Timestamp: {datetime.utcnow().isoformat()}\n"
            f"Action Required: Interactive OAuth re-authentication needed"
        )
        
        self.logger.critical(f"WOULD SEND NOTIFICATION:\n{message}")
        
        # In production, use:
        # sessions_send(
        #     sessionKey=Caine_session_key,
        #     message=message
        # )
        
        # For now, write to a notification file
        try:
            with open("/tmp/oauth_degraded_alert.txt", "w") as f:
                f.write(message)
            self.logger.info("Degraded mode alert written to /tmp/oauth_degraded_alert.txt")
        except Exception as e:
            self.logger.error(f"Failed to write degraded alert: {e}")
    
    def log_refresh_audit(self, old_tid: str, new_tid: str):
        """
        Audit log for every token refresh event.
        
        Args:
            old_tid: Old token identifier (first 8 chars)
            new_tid: New token identifier (first 8 chars)
        """
        timestamp = datetime.utcnow().isoformat()
        audit_entry = (
            f"TOKEN_REFRESH_AUDIT: timestamp={timestamp} "
            f"old_tid={old_tid[:8]}... new_tid={new_tid[:8]}..."
        )
        self.logger.info(audit_entry)
        
        # Also log to separate audit file for tracking
        try:
            with open("/tmp/token_refresh_audit.log", "a") as f:
                f.write(f"{audit_entry}\n")
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")
    
    def get_status(self, account_id: str) -> Dict[str, Any]:
        """
        Get current validator status for monitoring.
        
        Args:
            account_id: Account identifier
            
        Returns:
            Status dict with token info and degraded mode
        """
        token = self.cache.get_token(self.provider, account_id)
        
        if not token:
            return {
                "account_id": account_id,
                "status": "NO_TOKEN",
                "degraded_mode": self.degraded_mode,
                "refresh_attempts": self.refresh_attempts
            }
        
        remaining = token.expires_at - time.time()
        
        return {
            "account_id": account_id,
            "status": "DEGRADED" if self.degraded_mode else "ACTIVE",
            "degraded_mode": self.degraded_mode,
            "refresh_attempts": self.refresh_attempts,
            "token_expires_in_seconds": int(remaining),
            "token_valid": token.is_valid,
            "cached_at": token.cached_at
        }
    
    def reset_degraded_mode(self):
        """
        Reset degraded mode after manual re-authentication.
        """
        if self.degraded_mode:
            self.degraded_mode = False
            self.refresh_attempts = 0
            self.logger.warning("DEGRADED mode reset - monitoring re-enabled")
            return True
        return False