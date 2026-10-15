# MT5 Manager REST API

Flask-based REST API for MetaTrader 5 Manager operations using the `mt5manager` Python package.

## Features

- **JWT Authentication** - Manager login returns bearer token
- **User Info** - Get manager/trader account details
- **Positions** - List all open positions on the server
- **Trade Execution** - Place buy/sell orders for trader accounts
- **Plugin Management** - List and get plugin details
- **Group Management** - List groups, get group details, update commissions config
- **MT5Manager Only** - No local MT5 terminal required (connects directly to server)

## Prerequisites

1. **Python 3.9+** installed
2. **MT5Manager** package (included in requirements)
3. **Manager/Administrator credentials** on the MT5 server with API access
4. IP address whitelisted for the manager account (if server restricts IPs)

## Installation

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# or source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Set environment variables (or pass in login request):

```env
MT5_SERVER=your.mt5.server:443
SECRET_KEY=your-secret-key-for-jwt
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

## Running the API

```bash
python main.py
```

The API runs on `http://localhost:5000`

---

## API Reference

### POST `/auth/login`

Authenticates with MT5 Manager server and returns a JWT token.

**Headers:** None

**Body:**
```json
{
  "login": 0,
  "password": "manager_password",
  "server": "MetaTrader5-ServerName"
}
```

- `login` — Manager account number (often 0 or a specific admin login)
- `password` — Manager password
- `server` — MT5 server address/name (e.g., `"MetaQuotes-Demo"` or `"192.168.1.100:443"`)

**Success Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user_info": {
    "login": 0,
    "name": "Administrator",
    "group": "managers\\admin",
    "balance": 0.0,
    "credit": 0.0,
    "leverage": 0
  }
}
```

**Error Response (401):**
```json
{
  "message": "MT5Manager connection failed: IP address unallowed for manager"
}
```
*Add your IP to manager's allowed list in MT5 Manager → Rights.*

---

### GET `/auth/me`

Get current authenticated manager's info. **Prints full MTUser object to console for debugging**.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "login": 0,
  "name": "Administrator",
  "group": "managers\\admin",
  "balance": 0.0,
  "credit": 0.0,
  "leverage": 0
}
```

**Console Debug Output:**
When this endpoint is called, the server console prints:
```
============================================================
DEBUG: Full MTUser object details
============================================================
Type: <class 'MT5Manager.MTUser'>
Dir (all attributes): ['Account', 'Balance', 'Clear', 'Country', 'Credit', ...]
--- Capitalized/Public Properties ---
  Balance: 0.0 (type: float)
  Clear: <built-in method Clear ...> (type: builtin_function_or_method)
  Country: "US" (type: str)
  Credit: 0.0 (type: float)
  Group: "managers\\admin" (type: str)
  ...
============================================================
```

---

### GET `/positions`

List all open positions on the server (requires manager rights).

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
[
  {
    "ticket": 13111682,
    "symbol": "EURUSD",
    "type": 0,
    "volume": 0.0019,
    "price_open": 1.06567,
    "price_current": 1.06600,
    "profit": 0.45
  }
]
```
- `type`: `0` = BUY, `1` = SELL
- `ticket`: Position identifier (`Position` in MT5Manager)

---

### POST `/trade`

Place a trade for a specific trader account.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Body:**
```json
{
  "symbol": "EURUSD",
  "volume": 0.1,
  "user_login": 123456,
  "type": "BUY",
  "price": 1.08500,
  "sl": 1.08000,
  "tp": 1.09000,
  "comment": "Manual trade"
}
```
- `user_login` — Target trader account number

**Success Response (200):**
```json
{
  "order": 987654321,
  "deal": 987654322,
  "result": "success"
}
```

**Error Response (400):**
```json
{
  "message": "Trade failed",
  "retcode": 10019,
  "comment": "Not enough money"
}
```

---

### GET `/account`

Get account details for the authenticated manager.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "login": 0,
  "name": "Administrator",
  "group": "managers\\admin",
  "balance": 0.0,
  "credit": 0.0,
  "leverage": 0
}
```

---

### GET `/health`

Health check (no auth).

**Response (200):**
```json
{
  "status": "healthy",
  "service": "mt5-api"
}
```

---

## Plugin Endpoints

### GET `/v1/plugins`

List all installed plugins on the MT5 server.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "plugins": [
    {
      "name": "FeedRedundancy",
      "module": "feed_redundancy",
      "status": 1,
      "version": "5.0.38",
      "type": 1,
      "company": "MetaQuotes",
      "build": 3035,
      "flags": 0,
      "description": "Redundant feed handler"
    }
  ],
  "total": 1
}
```

**Fields:**
- `name` — Plugin name
- `module` — Module filename/path
- `status` — 0=stopped, 1=running
- `version` — Plugin version
- `type` — Plugin type (1=feed, 2=web, etc.)
- `company` — Vendor/company
- `build` — Build number
- `flags` — Plugin flags bitmask
- `description` — Plugin description

---

### GET `/v1/plugins/{plugin_name}`

Get details of a specific plugin by name (case-insensitive).

**Headers:**
```
Authorization: Bearer <access_token>
```

**URL Parameters:**
- `plugin_name` — Plugin name

**Success Response (200):**
```json
{
  "name": "FeedRedundancy",
  "module": "feed_redundancy",
  "status": 1,
  "version": "5.0.38",
  "type": 1,
  "company": "MetaQuotes",
  "build": 3035
}
```

**Error Response (404):**
```json
{
  "message": "Plugin not found"
}
```

---

## Group Endpoints

### GET `/v1/groups`

List all groups on the MT5 server with commissions config status.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "groups": {
    "managers": {
      "_data": {
        "group": "managers",
        "company": "MetaQuotes",
        "currency": "USD",
        "leverage": 0,
        "has_config": false
      },
      "admin": {
        "_data": {
          "group": "managers\\admin",
          "company": "MetaQuotes",
          "currency": "USD",
          "leverage": 0,
          "has_config": true,
          "split": "70/20/10",
          "type": "percentage"
        }
      }
    }
  },
  "total": 2
}
```
- Groups are returned in a nested tree structure based on backslash separators.
- `has_config` indicates if commissions config exists in the ini file.
- `split` and `type` are included if config exists.

---

### GET `/v1/group`

Get details of a specific group by name.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `name` — Group name (case-insensitive)

**Example:**
```
GET /v1/group?name=managers%5Cadmin
```

**Success Response (200):**
```json
{
  "group": "managers\\admin",
  "company": "MetaQuotes",
  "currency": "USD",
  "leverage": 0,
  "has_config": true,
  "split": "70/20/10",
  "type": "percentage",
  "commissions": [
    {
      "name": "MAIN",
      "has_config": true,
      "split": "80/10/10",
      "type": "percentage",
      ...
    }
  ]
}
```

Each commission object now also carries its own `has_config`/`split`/`type` when a `[group|commission]` section exists in the ini.

**Error Response (404):**
```json
{
  "message": "Group not found"
}
```

---

### PUT `/v1/group`

Update commissions config for a specific group (or a specific commission inside the group).

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `name` — Group name (case-insensitive)
- `commission` (optional) — Commission name; if provided, stores under section `name|commission` instead of just the group. This allows per-commission split/type overrides.

**Body:**
```json
{
  "split": "70/20/10",
  "type": "percentage"
}
```
- `type`: `"percentage"` or `"amount"`
- `split`: Delimited by `/`
  - Percentage: `"70/20/10"` (must sum to 100)
  - Amount: `"$70/$10"` (must sum to group's total commission per lot)

**Validation:**
- Group must exist
- For percentage: split parts must be numbers summing to 100
- For amount: split parts must start with `$`, numbers summing to group's `CommissionLot`
- Split must have at least 1 part

**Success Response (200):**
```json
{
  "message": "Commissions config updated successfully"
}
```

**Error Response (422):**
```json
{
  "message": "Validation failed",
  "errors": [
    "Percentage split must sum to 100, got 90"
  ]
}
```

---

## Notes

- **Manager vs Trader**: This API uses MT5Manager to connect as a **manager/administrator**. It cannot log in with regular trader accounts.
- **IP Whitelisting**: Manager accounts often have IP restrictions. Add your server's IP to the manager's allowed IPs in MT5 Manager → Users → Managers → [manager] → Rights.
- **Token Storage**: Tokens and passwords are stored in-memory. Restarting the API invalidates all tokens.
- **Production**: Use a proper WSGI server (Gunicorn/uWSGI), persistent token store (Redis/DB), and HTTPS.

## Troubleshooting

### "MT5Manager connection failed: IP address unallowed for manager"
Your manager account is restricted to specific IPs. Add the current IP to the allowed list via MT5 Manager or connect from an allowed IP.

### "Failed to retrieve user info"
Ensure the manager login is correct and the account exists on the server.

### Position/trade errors
Manager must have appropriate rights to view positions and place trades. Ensure rights are set in MT5 Manager.
