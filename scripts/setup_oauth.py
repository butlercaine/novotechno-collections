#!/usr/bin/env python3
"""
Interactive OAuth setup script for Microsoft Graph API email integration.
Guides user through device code flow and saves tokens to macOS Keychain.
"""

import sys
import os
import argparse
import logging
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.auth.device_code_flow import DeviceCodeFlow
from src.auth.token_cache import TokenCache, CachedToken
from src.auth.token_validator import TokenValidator
from src.auth.rate_limiter import TokenBucketRateLimiter
from src.collections.email_sender import GraphEmailSender


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_oauth(
    client_id: str,
    tenant_id: str = "common",
    scopes: str = "Mail.Send User.Read offline_access",
    account_id: str = "default",
    test_email: Optional[str] = None
) -> bool:
    """
    Interactive OAuth setup for Microsoft Graph API.
    
    Args:
        client_id: Azure AD application client ID
        tenant_id: Azure AD tenant ID (default: common)
        scopes: OAuth scopes (space-separated)
        account_id: Account identifier for token storage
        test_email: Optional test email address
        
    Returns:
        True if setup successful
    """
    print("\n" + "="*60)
    print(" NovotEcho Collections - OAuth Setup")
    print("="*60 + "\n")
    
    # Step 1: Initialize authentication
    print("🔐 Initializing OAuth flow...")
    
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scope_list = scopes.split()
    
    try:
        flow = DeviceCodeFlow(
            client_id=client_id,
            authority=authority,
            scopes=scope_list
        )
    except Exception as e:
        logger.error(f"Failed to initialize device flow: {e}")
        print(f"❌ Error: {e}")
        return False
    
    # Step 2: Get device code
    print("\n📱 Requesting device code...")
    
    try:
        device_flow = flow.initiate_flow()
        user_code = flow.get_user_code()
        verification_uri = flow.get_authorization_url()
        
        print(f"\n✅ Device code received!")
        print(f"\n{'='*60}")
        print(" AUTHENTICATION REQUIRED")
        print("="*60)
        print(f"\n1. Open this URL in your browser:")
        print(f"   {verification_uri}")
        print(f"\n2. Enter this code:")
        print(f"   {user_code}")
        print(f"\n3. Complete the authentication")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Failed to initiate device flow: {e}")
        print(f"\n❌ Error getting device code: {e}")
        return False
    
    # Step 3: Poll for token
    print("\n⏳ Waiting for authentication... (check your browser)")
    print("(You have 15 minutes to complete authentication)\n")
    
    try:
        token_response = flow.poll_for_token(device_flow, timeout=900)
        
        if not token_response or "access_token" not in token_response:
            print("❌ Authentication failed or timed out")
            return False
        
        print("\n✅ Authentication successful!")
        print(f"   Token type: {token_response.get('token_type', 'Bearer')}")
        print(f"   Expires in: {token_response.get('expires_in', 0)} seconds")
        
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        print(f"\n❌ Authentication error: {e}")
        return False
    
    # Step 4: Cache tokens securely
    print("\n🔒 Caching tokens in macOS Keychain...")
    
    try:
        cache = TokenCache(app_name="novotechno-collections")
        
        # Create cached token
        from src.auth.token_cache import CachedToken
        import time
        
        cached_token = CachedToken(
            access_token=token_response["access_token"],
            token_type=token_response.get("token_type", "Bearer"),
            expires_at=int(time.time()) + token_response.get("expires_in", 3600),
            refresh_token=token_response.get("refresh_token"),
            scope=token_response.get("scope"),
            account_id=account_id
        )
        
        # Save to keychain
        success = cache.save_token(self.provider, account_id, cached_token)
        
        if not success:
            print("❌ Failed to save tokens to Keychain")
            return False
        
        print("✅ Tokens saved securely to macOS Keychain")
        
    except Exception as e:
        logger.error(f"Failed to cache tokens: {e}")
        print(f"❌ Error caching tokens: {e}")
        return False
    
    # Step 5: Test the setup
    if test_email:
        print("\n📧 Testing email sending...")
        
        try:
            # Initialize validator and rate limiter
            validator = TokenValidator(cache, provider=self.provider)
            rate_limiter = TokenBucketRateLimiter()
            
            # Initialize email sender
            sender = GraphEmailSender(
                token_validator=validator,
                rate_limiter=rate_limiter,
                account_id=account_id
            )
            
            # Send test email
            result = sender.send_email(
                to_address=test_email,
                subject="NovotEcho Collections - OAuth Setup Success",
                body_html=f"""
                <html>
                <body>
                    <h2>✅ OAuth Setup Successful</h2>
                    <p>Your NovotEcho Collections email integration is now configured and working!</p>
                    <p><strong>Account:</strong> {account_id}</p>
                    <p><strong>Setup Time:</strong> {datetime.now().isoformat()}</p>
                    <p>You can now send collection reminder emails via Microsoft Graph API.</p>
                </body>
                </html>
                """
            )
            
            print(f"✅ Test email sent successfully!")
            print(f"   Message ID: {result.get('message_id', 'N/A')}")
            print(f"   Recipient: {test_email}")
            
        except Exception as e:
            logger.error(f"Test email failed: {e}")
            print(f"\n⚠️  Test email failed: {e}")
            print("   (OAuth is configured, but email sending had an issue)")
    
    # Summary
    print("\n" + "="*60)
    print(" SETUP COMPLETE")
    print("="*60)
    print(f"\n✅ OAuth configured successfully!")
    print(f"   Client ID: {client_id}")
    print(f"   Tenant ID: {tenant_id}")
    print(f"   Account: {account_id}")
    print(f"   Scopes: {scopes}")
    print(f"\n🔒 Tokens stored securely in macOS Keychain")
    
    if test_email:
        print(f"📧 Test email sent to: {test_email}")
    
    print("\nYou can now use the email sender in your application.")
    print("="*60 + "\n")
    
    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive OAuth setup for NovotEcho Collections email"
    )
    
    parser.add_argument(
        "--client-id",
        required=True,
        help="Azure AD application client ID"
    )
    
    parser.add_argument(
        "--tenant-id",
        default="common",
        help="Azure AD tenant ID (default: common)"
    )
    
    parser.add_argument(
        "--scopes",
        default="Mail.Send User.Read offline_access",
        help="OAuth scopes (space-separated, default: Mail.Send User.Read offline_access)"
    )
    
    parser.add_argument(
        "--account-id",
        default="default",
        help="Account identifier for token storage (default: default)"
    )
    
    parser.add_argument(
        "--test-email",
        help="Send test email to this address after setup"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run setup
    success = setup_oauth(
        client_id=args.client_id,
        tenant_id=args.tenant_id,
        scopes=args.scopes,
        account_id=args.account_id,
        test_email=args.test_email
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()