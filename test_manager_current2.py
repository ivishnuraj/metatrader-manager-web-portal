import MT5Manager

m = MT5Manager.ManagerAPI()
connected = m.Connect('', 0, 'dummy', 0, 120000)
print("Connect result:", connected)

if connected:
    # Try ManagerCurrent
    try:
        current = m.ManagerCurrent()
        print("ManagerCurrent result type:", type(current))
        if current:
            print("ManagerCurrent attributes:", [x for x in dir(current) if not x.startswith('_') and x[0].isupper()][:20])
            for attr in ['Login', 'Name', 'LastName', 'Balance', 'Credit', 'Levearge']:
                if hasattr(current, attr):
                    print(f"  {attr}: {getattr(current, attr)}")
        else:
            print("ManagerCurrent returned None/False")
    except Exception as e:
        print(f"ManagerCurrent error: {e}")
    m.Disconnect()
