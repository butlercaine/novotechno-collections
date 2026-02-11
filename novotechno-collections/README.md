# NovotEcho Collections

Automated invoice collections system for NovotEcho SAS.

## Features

- ✅ Automated PDF invoice parsing with confidence scoring
- ✅ Multi-language Spanish email templates (Colombia, Mexico, Spain)
- ✅ Microsoft Graph API integration for email sending
- ✅ Real-time payment detection via filesystem monitoring
- ✅ Confidence-based routing (auto/review/manual)
- ✅ Agent health monitoring and coordination
- ✅ Rate limit compliance (100/day tenant limit)

## Requirements

- Python 3.9+
- macOS (for Keychain token storage)
- Microsoft Graph API access

## Installation

```bash
git clone https://github.com/butlercaine/novotechno-collections.git
cd novotechno-collections
pip install -e .
```

## Quick Start

1. **OAuth Setup:**
   ```bash
   python scripts/setup_oauth.py
   ```
   Follow prompts to authenticate with Microsoft.

2. **Run Agents:**
   ```bash
   # Terminal 1: Email agent
   collections-emailer --watch ~/Documents/Invoices/
   
   # Terminal 2: Payment watcher
   payment-watcher --watch ~/Downloads/
   
   # Terminal 3: Supervisor (hourly checks)
   collections-supervisor --dashboard
   ```

3. **Access Dashboard:**
   ```bash
   open ~/.local/share/novotechno-collections/state/dashboard.html
   ```

## Configuration

See `docs/oauth-setup.md` for detailed OAuth configuration.

## Documentation

- [OAuth Setup Guide](docs/oauth-setup.md)
- [Architecture Overview](docs/architecture/overview.md)
- [API Reference](docs/api/README.md)

## License

MIT