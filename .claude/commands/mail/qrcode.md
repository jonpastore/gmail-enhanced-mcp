---
name: qrcode
description: Generate QR code to access the Email Hygiene UI from your phone
---

Generate and display an ASCII QR code linking to the Gmail Enhanced Hygiene UI.

Steps:
1. Read the MCP_AUTH_TOKEN from the .env file at /home/jon/projects/gmail-enhanced-mcp/.env, or from the MCP_AUTH_TOKEN environment variable
2. Construct the URL: `https://morpheus-ai.tail42929e.ts.net:8420/ui/?token=TOKEN`
3. Generate an ASCII QR code using Python:

```bash
python -c "
import qrcode, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('/home/jon/projects/gmail-enhanced-mcp/.env'))
token = os.getenv('MCP_AUTH_TOKEN', '')
if not token:
    print('ERROR: MCP_AUTH_TOKEN not found in .env or environment')
else:
    url = f'https://morpheus-ai.tail42929e.ts.net:8420/ui/?token={token}'
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print()
    print(f'URL: {url}')
    print()
    print('Requirements: Tailscale running on phone, MCP server running (python -m gmail_mcp serve)')
"
```

4. Display the QR code output and the URL to the user
5. Remind them: Tailscale must be running on phone, and MCP server must be running
