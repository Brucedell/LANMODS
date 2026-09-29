import requests

targets = [
    0x0057f510, 0x00581e10, 0x005a5de0, 0x005a6b70, 0x005a9660
]

for t in targets:
    hex_addr = f"{t:08x}"
    r = requests.get("http://127.0.0.1:8080/decompile_function", params={"address": hex_addr})
    print(f"=== {hex_addr} ===")
    print(r.text)
