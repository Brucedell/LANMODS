import requests

for addr in ["005d9350", "005da750", "005db080"]:
    r = requests.get("http://127.0.0.1:8080/decompile_function", params={"address": addr})
    print(f"==================== {addr} ====================")
    print(r.text)
