from datetime import datetime, timedelta
import os
import MT5Manager
from flask import Flask, request, jsonify
from functools import wraps
import jwt
import configparser
from dotenv import load_dotenv
from collections import defaultdict
import json
from waitress import serve
from MT5Manager import MTConCommission
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', '9e3a6c4b2d1f8a7e0c9b3d5f1a2c4e6b')

# In-memory token storage: token -> {login, server, password}
active_tokens = {}
def tree_factory():
    return defaultdict(tree_factory)

def build_complex_tree(groups_list):
    root = tree_factory()

    for item in groups_list:
        # Split the path into parts
        parts = item['group'].split('\\')
        
        # Traverse/Create the nested structure
        current = root
        for part in parts:
            current = current[part]
        
        # At the very last node, embed the original full dictionary
        # We use '_data' to separate it from potential sub-groups
        current["_data"] = item

    return root


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token or token not in active_tokens:
            return jsonify({'message': 'Token is missing or invalid'}), 401

        return f(*args, **kwargs)
    return decorated

def get_manager_from_token(token):
    """Reconnect using stored credentials from token."""
    token_data = active_tokens.get(token)
    if not token_data:
        return None, {'message': 'Invalid token'}, 401

    login = token_data['login']
    server = token_data['server']
    password = token_data.get('password', '')
    
    if not password:
        return None, {'message': 'No password stored in token'}, 401

    manager = MT5Manager.ManagerAPI()
    # Use PUMP_MODE_ALL (0xFFFFFFFF) to sync all data including users
    PUMP_MODE_ALL = 0xFFFFFFFF
    connected = manager.Connect(server, login, password, PUMP_MODE_ALL, 120000)
    if not connected:
        error = MT5Manager.LastError()
        return None, {'message': f'MT5Manager reconnection failed: {error[2] if error else "Unknown"}'}, 500
    
    return manager, None, None

@app.route('/auth/login', methods=['POST'])
def login():
    """Login to MetaTrader 5 Manager and return JWT token."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), 400

        login_val = data.get('login')
        password = data.get('password')
        server = data.get('server') or os.getenv('MT5_SERVER', '')

        if not login_val or not password:
            return jsonify({'message': 'Login and password required'}), 400

        login_int = int(login_val)
        manager = MT5Manager.ManagerAPI()
        # Use PUMP_MODE_ALL to sync user data
        PUMP_MODE_ALL = 0xFFFFFFFF
        connected = manager.Connect(server, login_int, password, PUMP_MODE_ALL, 120000)
        if not connected:
            error = MT5Manager.LastError()
            return jsonify({'message': f'MT5Manager connection failed: {error[2] if error else "Unknown error"}'}), 401

        try:
            # Get user info using UserGet (returns MTUser object directly)
            user = manager.UserGet(login_int)
            if not user:
                return jsonify({'message': 'Failed to retrieve user info'}), 500

            # Build user_info from available MTUser fields
            user_info = {
                'login': user.Login,
                'name': f"{user.Name} {user.LastName}".strip(),
                'group': user.Group,
                'balance': user.Balance,
                'credit': user.Credit,
                'leverage': user.Leverage
            }
            # Add optional fields if present
            if hasattr(user, 'Company'):
                user_info['company'] = user.Company
            if hasattr(user, 'Country'):
                user_info['country'] = user.Country
            if hasattr(user, 'EMail'):
                user_info['email'] = user.EMail
            if hasattr(user, 'Currency'):
                user_info['currency'] = user.Currency

            # Create JWT token
            token_data = {
                'sub': str(login_int),
                'login': login_int,
                'server': server,
                'password': password,  # store for reconnection
                'exp': datetime.utcnow() + timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60')))
            }
            token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')

            active_tokens[token] = token_data

            return jsonify({
                'access_token': token,
                'token_type': 'bearer',
                'expires_in': int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60')) * 60,
                'user_info': user_info
            })
        finally:
            manager.Disconnect()

    except ValueError:
        return jsonify({'message': 'Invalid login format'}), 400
    except Exception as e:
        return jsonify({'message': f'Login failed: {str(e)}'}), 500

@app.route('/auth/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current authenticated user info."""
    token = request.headers.get('Authorization').split(' ')[1]
    manager, error_resp, status = get_manager_from_token(token)
    if error_resp:
        return jsonify(error_resp), status

    try:
        user = manager.UserGet(active_tokens[token]['login'])
        if not user:
            return jsonify({'message': 'Account not found'}), 404

        # ============ DEBUG: Print full user object info to console ============
        print("\n" + "="*60)
        print("DEBUG: Full MTUser object details")
        print("="*60)
        print(f"Type: {type(user)}")
        print(f"User object id: {id(user)}")
        # Try __dict__ if available
        try:
            print(f"__dict__: {user.__dict__}")
        except Exception as e:
            print(f"__dict__ not available: {e}")
        
        all_attrs = [x for x in dir(user) if not x.startswith('_')]
        print(f"Total attributes ({len(all_attrs)}): {all_attrs}")
        print("\n--- Capitalized/Public Properties ---")
        for attr in sorted([x for x in dir(user) if x[0].isupper() and not x.startswith('_')]):
            try:
                val = getattr(user, attr)
                if callable(val):
                    print(f"  {attr}: <method> (type: {type(val).__name__})")
                else:
                    # Show full value for non-string types, truncate strings
                    if isinstance(val, str) and len(val) > 100:
                        display = val[:100] + "..."
                    else:
                        display = val
                    print(f"  {attr}: {display} (type: {type(val).__name__})")
            except Exception as e:
                print(f"  {attr}: <error accessing: {e}>")
        print("="*60 + "\n")

        user_info = {
            'login': user.Login,
            'name': f"{user.Name} {user.LastName}".strip(),
            'group': user.Group,
            'balance': user.Balance,
            'credit': user.Credit,
            'leverage': user.Leverage
        }
        # Add optional fields if present
        if hasattr(user, 'Company'):
            user_info['company'] = user.Company
        if hasattr(user, 'Country'):
            user_info['country'] = user.Country
        if hasattr(user, 'EMail'):
            user_info['email'] = user.EMail
        if hasattr(user, 'Currency'):
            user_info['currency'] = user.Currency

        return jsonify(user_info)
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        manager.Disconnect()

@app.route('/positions', methods=['GET'])
@token_required
def get_positions():
    """Get all open positions."""
    token = request.headers.get('Authorization').split(' ')[1]
    manager, error_resp, status = get_manager_from_token(token)
    if error_resp:
        return jsonify(error_resp), status

    try:
        positions = manager.PositionGet()
        if positions is None or positions is False:
            error = MT5Manager.LastError()
            return jsonify({'message': f'Failed to get positions: {error[2] if error else "Unknown error"}'}), 500

        result = []
        # positions can be a list or a single object
        if isinstance(positions, list):
            for pos in positions:
                result.append({
                    'ticket': pos.Position,
                    'symbol': pos.Symbol,
                    'type': pos.Action,
                    'volume': pos.Volume,
                    'price_open': pos.PriceOpen,
                    'price_current': pos.PriceCurrent,
                    'profit': pos.Profit
                })
        else:
            result.append({
                'ticket': positions.Position,
                'symbol': positions.Symbol,
                'type': positions.Action,
                'volume': positions.Volume,
                'price_open': positions.PriceOpen,
                'price_current': positions.PriceCurrent,
                'profit': positions.Profit
            })

        return jsonify(result)
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        manager.Disconnect()

@app.route('/trade', methods=['POST'])
@token_required
def place_trade():
    """Place a new trade order using MT5Manager."""
    token = request.headers.get('Authorization').split(' ')[1]
    manager, error_resp, status = get_manager_from_token(token)
    if error_resp:
        return jsonify(error_resp), status

    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), 400

        symbol = data.get('symbol')
        volume = float(data.get('volume', 0))
        user_login = data.get('user_login')  # target trader account
        trade_type = data.get('type', '').upper()
        price = data.get('price')
        sl = data.get('sl')
        tp = data.get('tp')
        comment = data.get('comment', '')

        if not symbol or not user_login or volume <= 0 or trade_type not in ['BUY', 'SELL']:
            return jsonify({'message': 'Invalid trade parameters. Requires symbol, user_login, volume, type'}), 400

        # Create trade request using MTRequest
        trade_req = MT5Manager.MTRequest(manager)
        trade_req.Action = 0  # TRADE_ACTION_DEAL
        trade_req.Symbol = symbol
        trade_req.Volume = volume
        trade_req.Login = int(user_login)  # target trader account
        trade_req.Type = 0 if trade_type == 'BUY' else 1

        if price:
            trade_req.PriceOrder = float(price)
        if sl:
            trade_req.PriceSL = float(sl)
        if tp:
            trade_req.PriceTP = float(tp)
        if comment:
            trade_req.Comment = comment

        trade_req.PriceDeviation = 20

        # Send order via manager
        result = manager.OrderSend(trade_req)

        if result.RetCode != 0:
            error = MT5Manager.LastError()
            return jsonify({
                'message': 'Trade failed',
                'retcode': result.RetCode,
                'comment': result.Comment or (error[2] if error else 'Unknown error')
            }), 400

            return jsonify({
                'order': result.Order,
                'deal': result.Deal,
                'result': 'success'
            })
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        manager.Disconnect()

@app.route('/account', methods=['GET'])
@token_required
def get_account_info():
    """Get detailed account information (uses MTUser fields)."""
    token = request.headers.get('Authorization').split(' ')[1]
    manager, error_resp, status = get_manager_from_token(token)
    if error_resp:
        return jsonify(error_resp), status

    try:
        user = manager.UserGet(active_tokens[token]['login'])
        if not user:
            return jsonify({'message': 'Account not found'}), 404

        account_info = {
            'login': user.Login,
            'name': f"{user.Name} {user.LastName}".strip(),
            'group': user.Group,
            'balance': user.Balance,
            'credit': user.Credit,
            'leverage': user.Leverage
        }
        # Add optional fields if present
        if hasattr(user, 'Company'):
            account_info['company'] = user.Company
        if hasattr(user, 'Country'):
            account_info['country'] = user.Country
        if hasattr(user, 'Currency'):
            account_info['currency'] = user.Currency
        
        return jsonify(account_info)
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        manager.Disconnect()

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path=None):
    return '', 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'mt5-api'})

@app.route('/v1/plugins', methods=['GET'])
@token_required
def list_plugins():
    """List all installed plugins on the MT5 server."""
    token = request.headers.get('Authorization').split(' ')[1]
    manager, error_resp, status = get_manager_from_token(token)
    token_data = active_tokens.get(token)

    if error_resp:
        return jsonify(error_resp), status
    login = token_data['login']
    server = token_data['server']
    password = token_data.get('password', '')
    if not password:
        return jsonify({'message': 'No password stored in token'}), 401

    admin = MT5Manager.AdminAPI()
    connected = admin.Connect(server, login, password, 0xFFFFFFFF, 120000)
    if not connected:
        error = MT5Manager.LastError()
        return jsonify({'message': f'AdminAPI connection failed: {error[2] if error else "Unknown"}'}), 500

    try:
        # Get total number of plugins
        total = admin.PluginTotal()
        if total == 0:
            return jsonify({'plugins': [], 'total': 0})
        
        plugins = []
        # Get first plugin
        for i in range(total):
            plugin = admin.PluginNext(i)
            plugins.append(extract_plugin_info(plugin))
        return jsonify({'plugins': plugins, 'total': total})
    
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        manager.Disconnect()

@app.route('/v1/plugins/<plugin_name>', methods=['GET'])
@token_required
def get_plugin(plugin_name):
    """Get details of a specific plugin by name."""
    token = request.headers.get('Authorization').split(' ')[1]
    manager, error_resp, status = get_manager_from_token(token)
    if error_resp:
        return jsonify(error_resp), status

    try:
        # Iterate through all plugins to find the one with matching name
        total = manager.PluginTotal()
        if total == 0:
            return jsonify({'message': 'Plugin not found'}), 404

        plugin = manager.PluginGet()
        if plugin:
            if match_plugin_name(plugin, plugin_name):
                return jsonify(extract_plugin_info(plugin))
            
            # Check remaining plugins
            while True:
                next_plugin = manager.PluginNext()
                if not next_plugin:
                    break
                if match_plugin_name(next_plugin, plugin_name):
                    return jsonify(extract_plugin_info(next_plugin))

        return jsonify({'message': 'Plugin not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        manager.Disconnect()

@app.route('/v1/groups', methods=['GET'])
@token_required
def list_groups():
    """List all groups from MT5 Admin API with commissions config."""
    token = request.headers.get('Authorization').split(' ')[1]
    token_data = active_tokens.get(token)
    if not token_data:
        return jsonify({'message': 'Invalid token'}), 401

    login = token_data['login']
    server = token_data['server']
    password = token_data.get('password', '')
    if not password:
        return jsonify({'message': 'No password stored in token'}), 401

    admin = MT5Manager.AdminAPI()
    connected = admin.Connect(server, login, password, 0xFFFFFFFF, 120000)
    if not connected:
        error = MT5Manager.LastError()
        return jsonify({'message': f'AdminAPI connection failed: {error[2] if error else "Unknown"}'}), 500

    try:
        # Load commissions config
        config = configparser.ConfigParser()
        config.read('C:\\MetaTrader 5 Platform\\TradeMain\\plugins\\commissions.ini')

        # Get total number of groups
        total = admin.GroupTotal()
        if total == 0:
            return jsonify({'groups': [], 'total': total})
        groups = []
        for i in range(total):
            group = admin.GroupNext(i)
            groups.append(extract_group_info(group, config, False))
        group_tree = build_complex_tree(groups)
        return jsonify({'groups': group_tree, 'total': total})
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        admin.Disconnect()

@app.route('/v1/group', methods=['GET'])
@token_required
def get_group():
    """Get details of a specific group from MT5 Admin API with commissions config."""
    group_name = request.args.get('name')
    if not group_name:
        return jsonify({'message': 'Group name required'}), 400

    token = request.headers.get('Authorization').split(' ')[1]
    token_data = active_tokens.get(token)
    if not token_data:
        return jsonify({'message': 'Invalid token'}), 401

    login = token_data['login']
    server = token_data['server']
    password = token_data.get('password', '')
    if not password:
        return jsonify({'message': 'No password stored in token'}), 401

    admin = MT5Manager.AdminAPI()
    connected = admin.Connect(server, login, password, 0xFFFFFFFF, 120000)
    if not connected:
        error = MT5Manager.LastError()
        return jsonify({'message': f'AdminAPI connection failed: {error[2] if error else "Unknown"}'}), 500

    try:
        # Load commissions config
        config = configparser.ConfigParser()
        config.read('C:\\MetaTrader 5 Platform\\TradeMain\\plugins\\commissions.ini')

        # Iterate through all groups to find the one with matching name
        total = admin.GroupTotal()
        if total == 0:
            return jsonify({'message': 'Group not found'}), 404

        group = admin.GroupGet(group_name)
        while group:
            if getattr(group, 'Group', '').lower() == group_name.lower():
                return jsonify(extract_group_info(group, config))
            group = admin.GroupNext()

        return jsonify({'message': 'Group not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        admin.Disconnect()

@app.route('/v1/group', methods=['PUT'])
@token_required
def update_group_config():
    """Update commissions config for a specific group or a specific commission inside it.
    Use ?commission=NAME to target a commission-specific section "group|NAME"."""
    group_name = request.args.get('name')
    commission_name = request.args.get('commission')
    if not group_name:
        return jsonify({'message': 'Group name required'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400

    # Validate type
    if 'type' not in data or data['type'] not in ['amount', 'percentage']:
        return jsonify({'message': 'Invalid type, must be "amount" or "percentage"'}), 422

    if 'split' not in data:
        return jsonify({'message': 'Split required'}), 422

    split_str = data['split']
    if not isinstance(split_str, str):
        return jsonify({'message': 'Split must be a string'}), 422

    parts = split_str.split('/')
    if len(parts) < 1:
        return jsonify({'message': 'Invalid split format'}), 422

    # Determine target section key
    target_section = f"{group_name}|{commission_name}" if commission_name else group_name

    # Get group to validate existence and get commission tiers
    token = request.headers.get('Authorization').split(' ')[1]
    token_data = active_tokens.get(token)
    if not token_data:
        return jsonify({'message': 'Invalid token'}), 401

    login = token_data['login']
    server = token_data['server']
    password = token_data.get('password', '')
    if not password:
        return jsonify({'message': 'No password stored in token'}), 401

    admin = MT5Manager.AdminAPI()
    connected = admin.Connect(server, login, password, 0xFFFFFFFF, 120000)
    if not connected:
        error = MT5Manager.LastError()
        return jsonify({'message': f'AdminAPI connection failed: {error[2] if error else "Unknown"}'}), 500

    group = None
    try:
        total = admin.GroupTotal()
        if total == 0:
            return jsonify({'message': 'Group does not exist'}), 422

        group = admin.GroupGet(group_name)
        while group:
            if getattr(group, 'Group', '').lower() == group_name.lower():
                break
            group = admin.GroupNext()

        if not group:
            return jsonify({'message': 'Group does not exist'}), 422

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        admin.Disconnect()

    # Validate split
    errors = []
    if data['type'] == 'percentage':
        try:
            values = [float(p) for p in parts]
            if sum(values) != 100.0:
                errors.append(f'Percentage split must sum to 100, got {sum(values)}')
        except ValueError as e:
            errors.append(f'Invalid percentage values: {str(e)}')
    elif data['type'] == 'amount':
        if not all(p.startswith('$') for p in parts):
            errors.append('Amount split parts must start with $')
        else:
            try:
                values = [float(p[1:]) for p in parts]
                total_split = sum(values)
                commissions = group_commissions_info(group)
                if commission_name:
                    commissions = [c for c in commissions if str(c.get('name', '')).lower() == str(commission_name).lower()]
                    if not commissions:
                        errors.append(f"Specified commission '{commission_name}' not found in the group")
                for commission in commissions:
                    matched = any(total_split == tier.get('value') for tier in commission.get('tiers', []))
                    if not matched:
                        errors.append(f'Amount split sum {total_split} does not match any tier value for commission {commission.get("name")}')
            except ValueError as e:
                errors.append(f'Invalid amount values: {str(e)}')

    if errors:
        return jsonify({'message': 'Validation failed', 'errors': errors}), 422

    try:
        # Load commissions config
        config = configparser.ConfigParser()
        config.read('C:\\MetaTrader 5 Platform\\TradeMain\\plugins\\commissions.ini')

        # Add section if it doesn't exist
        if not config.has_section(target_section):
            config.add_section(target_section)

        # Update values
        config.set(target_section, 'split', split_str)
        config.set(target_section, 'type', data['type'])

        # Write back to file
        with open('C:\\MetaTrader 5 Platform\\TradeMain\\plugins\\commissions.ini', 'w') as configfile:
            config.write(configfile)

        return jsonify({'message': 'Commissions config updated successfully'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500

def extract_plugin_info(plugin):
    """Extract plugin information into a dict."""
    # all params 
    allParamsCounter = plugin.ParameterTotal()
    params = []
    for i in range(allParamsCounter):
       parma = plugin.ParameterNext(i)
       params.append(
           {
               "name":getattr(parma, 'Name', ''),
               "value":getattr(parma, 'Value', ''),
           }
       )

    info = {
        'name': getattr(plugin, 'Name', ''),
        'module': getattr(plugin, 'Module', ''),
        'status': getattr(plugin, 'Status', 0),
        'version': getattr(plugin, 'Version', ''),
        'type': getattr(plugin, 'Type', 0),
        'flags': getattr(plugin, 'Flags', 0),
        'build': getattr(plugin, 'Build', 0),
        'company': getattr(plugin, 'Company', ''),
        'copyright': getattr(plugin, 'Copyright', ''),
        'description': getattr(plugin, 'Description', ''),
        'params' : params
    }

    
    print(params)
    # Filter out None values
    return {k: v for k, v in info.items() if v not in ('', None, 0) or k in ('name', 'module')}

def match_plugin_name(plugin, name):
    """Check if plugin name matches (case-insensitive)."""
    plugin_name = getattr(plugin, 'Name', '')
    return plugin_name.lower() == name.lower()

def group_commissions_info(group) :
    """ Extract Info about commissions"""
    commissionsTotal = group.CommissionTotal()
    commissions = []
    for i in range(commissionsTotal):
       commission = group.CommissionNext(i)
       tiersTotal = commission.TierTotal()
       tiers = []

       for j in range(tiersTotal):
            tier = commission.TierNext(j)
            tiers.append({
                "name": getattr(tier, 'Name', ''),
                "mode": getattr(tier, 'Mode', ''),
                "type": getattr(tier, 'Type', ''),
                "value": getattr(tier, 'Value', 0.0),
                "minimal": getattr(tier, 'Minimal', 0.0),
                "maximal": getattr(tier, 'Maximal', 0.0),
                "range_from": getattr(tier, 'RangeFrom', 0.0),
                "range_to": getattr(tier, 'RangeTo', 0.0),
                "currency": getattr(tier, 'Currency', '')
            })

       commissions.append(
           {
               "name":getattr(commission, 'Name', ''),
               "description":getattr(commission, 'Description', ''),
               "mode":getattr(commission, 'Mode', ''),
               "range":getattr(commission, 'RangeMode', ''),
               "range":getattr(commission, 'RangeMode', ''),
               "profit_mode":getattr(commission, 'ProfitMode', ''),
               "total_tiers" : tiersTotal,
               "tiers" : tiers
           }
       )
    return commissions


def extract_group_info(group, config, loadExtra = True):
    """Extract group information into a dict and merge commissions config."""
    info = {
        'group': getattr(group, 'Group', ''),
        'company': getattr(group, 'Company', ''),
        'currency': getattr(group, 'Currency', ''),
        'leverage': getattr(group, 'Leverage', 0),
        'margin_call': getattr(group, 'MarginCall', 0.0),
        'margin_stopout': getattr(group, 'MarginStopOut', 0.0),
        "commissions": [],
        # Add other fields as available
    }
    if loadExtra :
        commissions = group_commissions_info(group)
        # Filter to only show Agent Commission where EnCommMode is agent
        if commissions:
            commissions = [
                c for c in commissions
                if c.get('mode', '') == MTConCommission.EnCommMode.COMM_AGENT
            ]
            # commissions = [c for c in commissions if str(c.get('mode', '')).lower() == 'COMM_AGENT']
        info['commissions'] = commissions

    # Add commissions config if present (group level)
    section = info['group']
    info['has_config'] = config.has_section(section)
    if config.has_section(section):
        info['split'] = config.get(section, 'split', fallback=None)
        info['type'] = config.get(section, 'type', fallback=None)

    # Per-commission configs using "group|commission_name" sections
    if loadExtra and info.get('commissions'):
        gname = info['group']
        for comm in info['commissions']:
            cname = comm.get('name')
            if not cname:
                continue
            csection = f"{gname}|{cname}"
            comm['has_config'] = config.has_section(csection)
            if config.has_section(csection):
                comm['split'] = config.get(csection, 'split', fallback=None)
                comm['type'] = config.get(csection, 'type', fallback=None)
    # Filter out None, empty strings, and zero values for optional fields
    filtered = {}
    for k, v in info.items():
        if v is not None and (v != '' or k in ('group', 'has_config')) and (v != 0 or k in ('group', 'leverage', 'has_config')):
            filtered[k] = v
    return filtered

if __name__ == '__main__':
    port = int(os.getenv("API_PORT", "14315"))
    print(f"MT5 API running on port {port}")
    serve(app, host='0.0.0.0', port=port)
