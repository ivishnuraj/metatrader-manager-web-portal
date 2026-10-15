import MT5Manager

m = MT5Manager.ManagerAPI()
connected = m.Connect('', 0, 'dummy', 0, 120000)
print("Connect result:", connected)

if connected:
    # Try UserGet (different from UserRequest)
    user = m.UserGet(0)
    print("UserGet result type:", type(user))
    if user:
        print("UserGet - Login:", user.Login, "Name:", user.Name, "Balance:", user.Balance)
        print("Has Equity?", hasattr(user, 'Equity'))
        print("Has Margin?", hasattr(user, 'Margin'))
    else:
        print("UserGet returned None/False, error:", MT5Manager.LastError())
    
    # Try UserRequest with return value
    user2 = MT5Manager.MTUser(m)
    result = m.UserRequest(0, user2)
    print("\nUserRequest result:", result)
    print("user2.Login:", user2.Login, "Balance:", user2.Balance)
    
    m.Disconnect()
