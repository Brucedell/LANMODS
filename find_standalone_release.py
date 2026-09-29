import requests

with open("map_funcs.py") as f:
    pass

from map_funcs import seen_funcs

print(f"Checking {len(seen_funcs)} functions...")
standalone = []

for (f_addr, f_name), h_list in sorted(seen_funcs.items()):
    hex_addr = f"{f_addr:08x}"
    r = requests.get("http://127.0.0.1:8080/decompile_function", params={"address": hex_addr})
    code = r.text
    # Check if this function takes a handle or WeakRefManager as param
    # or how large it is
    lines = [l for l in code.splitlines() if l.strip() and not l.strip().startswith("/*")]
    # If the function is relatively short or clearly a Release function
    print(f"Function {f_name} at {hex_addr}: {len(lines)} lines")
    if len(lines) < 40:
        standalone.append((hex_addr, f_name, code))

print(f"\nFound {len(standalone)} short functions:")
for h, name, c in standalone:
    print(f"\n--- {name} ({h}) ---")
    print(c[:500])
