import requests

# Let's search via CE memory read
# We can read memory or use CE aob_scan or CE pattern search
# E8 xx xx xx xx -> target = EIP + 5 + rel32
# If target == 0x004B62B0:
# rel32 = 0x004B62B0 - (call_addr + 5)
