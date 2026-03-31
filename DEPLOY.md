# Gmail Enhanced MCP — Deployment Guide

## Target: Mac Mini with Claude Desktop + Cloudflare Tunnel

### Prerequisites

- Python 3.11+
- pip
- git
- cloudflared (Cloudflare Tunnel client)

### 1. Clone and Install

```bash
git clone https://github.com/jonpastore/gmail-enhanced-mcp.git
cd gmail-enhanced-mcp
pip install -r requirements.txt
```

### 2. Authenticate Accounts

#### Gmail (jpastore79@gmail.com)

1. Place `client_secret.json` in `credentials/` (download from Google Cloud Console > project gmail-enhanced-mcp)
2. Run:
   ```bash
   python -m gmail_mcp auth --provider gmail
   ```
3. Sign in with jpastore79@gmail.com in the browser
4. Token saved to `credentials/jpastore79@gmail.com/token.json`

#### Outlook (jon@degenito.ai)

1. Register an app in Azure AD (Entra ID) for the degenito.ai tenant:
   - Go to https://entra.microsoft.com > App registrations > New registration
   - Name: "Gmail Enhanced MCP"
   - Supported account types: Single tenant
   - Redirect URI: http://localhost (Mobile and desktop applications)
   - Add API permissions: Microsoft Graph > Delegated > Mail.ReadWrite, Mail.Send, User.Read
   - Grant admin consent
2. Copy the Application (client) ID and Directory (tenant) ID
3. Add to accounts.json under the outlook account's "azure" section
4. Run:
   ```bash
   python -m gmail_mcp auth --provider outlook
   ```
5. Sign in with jon@degenito.ai in the browser

### 3. Configure accounts.json

Edit `accounts.json`:
```json
{
  "default": "jpastore79@gmail.com",
  "accounts": [
    {
      "email": "jpastore79@gmail.com",
      "provider": "gmail"
    },
    {
      "email": "jon@degenito.ai",
      "provider": "outlook",
      "azure": {
        "client_id": "YOUR_CLIENT_ID",
        "tenant_id": "YOUR_TENANT_ID"
      }
    }
  ]
}
```

### 4. Set Environment

Create `.env`:
```
MCP_AUTH_TOKEN=<generate a random token: python -c "import secrets; print(secrets.token_urlsafe(32))">
LOG_LEVEL=INFO
LOG_FILE=mcp_server.log
HTTP_PORT=8420
```

### 5. Claude Desktop Integration

Add to Claude Desktop's MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "gmail-enhanced": {
      "url": "http://localhost:8420/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_AUTH_TOKEN"
      }
    }
  }
}
```

### 6. Auto-Start with launchd

Create `~/Library/LaunchAgents/com.gmail-enhanced-mcp.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gmail-enhanced-mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>gmail_mcp</string>
        <string>serve</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/gmail-enhanced-mcp</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/gmail-mcp-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/gmail-mcp-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>MCP_AUTH_TOKEN</key>
        <string>YOUR_TOKEN</string>
    </dict>
</dict>
</plist>
```

Load:
```bash
launchctl load ~/Library/LaunchAgents/com.gmail-enhanced-mcp.plist
```

### 7. Network Access (Tailscale)

All devices (laptop, Mac Mini, phone) are on the Tailscale VPN. No tunnels or public DNS needed.

Tailscale hostnames:
- Dev (laptop): `morpheus-ai` / `100.109.84.99`
- Prod (Mac Mini): `jons-mac-mini` / `100.96.244.44`
- Phone: `oneplus-11-5g`

The MCP server is accessible at `http://<tailscale-hostname>:8420/mcp/` from any device on the tailnet.

### 8. Mobile Setup (Claude App)

In Claude mobile app settings > MCP Servers > Add:
- URL: `http://jons-mac-mini:8420/mcp/`
- Auth: `Bearer YOUR_MCP_AUTH_TOKEN`

Ensure Tailscale is running on your phone before connecting.

### 9. Verify

```bash
curl http://localhost:8420/health
# {"status":"ok","version":"2.0.0"}

curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8420/mcp -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}'
```

### Troubleshooting

- Token expired: Re-run `python -m gmail_mcp auth --provider gmail|outlook`
- Port in use: Change HTTP_PORT in .env
- Tailscale not connecting: Run `tailscale status` to verify devices are online
- Claude Desktop not connecting: Verify URL in claude_desktop_config.json matches Tailscale hostname and port
