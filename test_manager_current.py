import MT5Manager

m = MT5Manager.ManagerAPI()
# Don't need to connect to test ManagerCurrent? maybe it's static?
try:
    result = MT5Manager.ManagerCurrent(m)
    print("ManagerCurrent result:", type(result))
    if result:
        print("Attrs:", [x for x in dir(result) if x[0].isupper()][:15])
except Exception as e:
    print("Error calling ManagerCurrent:", e)

# Check if it's a method on instance
print("Has ManagerCurrent on instance:", hasattr(m, 'ManagerCurrent'))
print("Type of m.ManagerCurrent:", type(m.ManagerCurrent) if hasattr(m, 'ManagerCurrent') else None)
