---
name: mail
description: List all available Gmail Enhanced MCP email commands
---

# Gmail Enhanced MCP — Available Commands

## Quick Actions
- `/mail:qrcode` — Show QR code to open the Hygiene UI on your phone
- `/mail:hud-refresh` — Refresh HUD with mail/calendar status (coming soon)
- `/mail:calendar-reminders` — Ensure upcoming events have reminders (coming soon)

## MCP Tools by Category

### Search & Read (4 tools)
| Tool | Description |
|------|-------------|
| `gmail_get_profile` | Get authenticated user's profile info |
| `gmail_search_messages` | Search messages using Gmail query syntax |
| `gmail_read_message` | Read a specific message by ID |
| `gmail_read_thread` | Read all messages in a thread |

### Drafts & Send (5 tools)
| Tool | Description |
|------|-------------|
| `gmail_create_draft` | Create a new draft message |
| `gmail_update_draft` | Update an existing draft |
| `gmail_list_drafts` | List all drafts |
| `gmail_send_draft` | Send a draft (requires approval) |
| `gmail_send_email` | Send email directly (requires approval) |

### Labels & Organization (3 tools)
| Tool | Description |
|------|-------------|
| `gmail_list_labels` | List all Gmail labels |
| `gmail_modify_thread_labels` | Add/remove labels from a thread |
| `gmail_create_label` | Create a new label |

### Attachments & Templates (3 tools)
| Tool | Description |
|------|-------------|
| `gmail_download_attachment` | Download an attachment to local path |
| `gmail_save_template` | Save an email template for reuse |
| `gmail_use_template` | Create draft from template with variables |

### Triage & Scoring (2 tools)
| Tool | Description |
|------|-------------|
| `gmail_triage_inbox` | Score and categorize inbox messages |
| `gmail_reset_triage_cache` | Reset the triage cache |

### Priority Senders (3 tools)
| Tool | Description |
|------|-------------|
| `gmail_add_priority_sender` | Add email/domain to priority list |
| `gmail_list_priority_senders` | List all priority senders by tier |
| `gmail_remove_priority_sender` | Remove a priority sender |

### Follow-up Tracking (2 tools)
| Tool | Description |
|------|-------------|
| `gmail_track_followup` | Track a sent message for replies |
| `gmail_check_followups` | Check overdue/approaching follow-ups |

### Email Hygiene (6 tools)
| Tool | Description |
|------|-------------|
| `gmail_trash_messages` | Bulk trash by IDs or search query |
| `gmail_block_sender` | Create auto-delete filter + trash existing |
| `gmail_report_spam` | Report messages as spam |
| `gmail_list_contacts` | List Google contacts with emails |
| `gmail_import_contacts_as_priority` | Import contacts as priority senders |
| `gmail_get_unsubscribe_link` | Extract unsubscribe link from message |

### Contact Management (2 tools)
| Tool | Description |
|------|-------------|
| `gmail_dismiss_contact` | Dismiss contact from future resync |
| `gmail_list_dismissed_contacts` | List dismissed contacts |

### Account Management (1 tool)
| Tool | Description |
|------|-------------|
| `gmail_list_accounts` | List all registered email accounts |

**Total: 31 tools across 2 accounts (jpastore79@gmail.com, jon@degenito.ai)**

## Hygiene UI
Access at: `https://morpheus-ai.tail42929e.ts.net:8420/ui/`
Run `/mail:qrcode` for a scannable link.
