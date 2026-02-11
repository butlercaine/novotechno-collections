### [2026-02-11] - OAuth Security Architecture

**Decision:** Use MSAL device code flow with macOS Keychain storage

**Rationale:**
- Device code flow: No browser required in agent context
- Keychain: Secure storage with OS-level encryption
- MSAL: Official Microsoft library, actively maintained

**Alternatives Considered:**
- Interactive browser flow: Rejected (requires browser in agent)
- File-based token storage: Rejected (less secure than Keychain)
- Custom OAuth implementation: Rejected (security risk)

**Consequences:**
- Tokens survive agent restart
- Tokens never in plaintext
- Silent refresh prevents auth interruption

**References:**
- MSAL Python: https://github.com/AzureAD/microsoft-authentication-library-for-python
- Azure AD App Registration: docs.microsoft.com/azure/active-directory/develop/
