import re
import bisect
import requests

# Load all functions from the saved file
functions = []
with open(r"C:\Users\Living room desk\.gemini\antigravity-ide\brain\fcd5fcf7-f173-464c-b37c-d74ea0c7fa07\.system_generated\steps\7362\output.txt", "r") as f:
    for line in f:
        # Format: "123: FUN_004a1000 at 004a1000"
        m = re.search(r"(\S+)\s+at\s+([0-9a-fA-F]+)", line)
        if m:
            name = m.group(1)
            addr = int(m.group(2), 16)
            functions.append((addr, name))

functions.sort(key=lambda x: x[0])
func_addrs = [f[0] for f in functions]

def find_enclosing_function(target_addr):
    idx = bisect.bisect_right(func_addrs, target_addr) - 1
    if idx >= 0:
        return functions[idx]
    return (0, "Unknown")

hits = [
    0x004A4085, 0x004A79D2, 0x004A90EC, 0x004A9780, 0x004AB116, 0x004AE873, 0x004AE9AF,
    0x004B6277, 0x004B6376, 0x004B6509, 0x004B6759, 0x004C0508, 0x004C266D, 0x004C27D6,
    0x004C28DB, 0x004C2B8B, 0x004C2F83, 0x004C309D, 0x004C35B1, 0x004C36AC, 0x004C3810,
    0x004C3DC5, 0x004C42A8, 0x004C484F, 0x004C663E, 0x004C669A, 0x004C66D0, 0x004C696F,
    0x004C6A6A, 0x004C7976, 0x004C7AB5, 0x004C876C, 0x004CF626, 0x004CF93C, 0x004D67F8,
    0x004D6AA2, 0x004D6D6B, 0x004D6E5E, 0x004D7852, 0x004D79BB, 0x004D955B, 0x004D9FB2,
    0x004DA483, 0x004DB725, 0x004E4E83, 0x004E4F0A, 0x004E5336, 0x004E5C38, 0x004E97B5,
    0x004EA166, 0x004EEE69, 0x004F0567, 0x004F4161, 0x004F8A4E, 0x004F9465, 0x004F951A,
    0x004F9DC9, 0x0050BC0D, 0x0050BC74, 0x00518D5E, 0x0051CDA4, 0x0051D157, 0x0051E37F,
    0x0051E3B5, 0x0051E5D8, 0x0051E60E, 0x0052564B, 0x0052CE08, 0x005318CA, 0x00539EB4,
    0x0053B7DB, 0x0053B8F3, 0x00548929, 0x00555B10, 0x00557580, 0x005576FB, 0x00557734,
    0x0055F649, 0x0056C0CD, 0x00571FAB, 0x00573738, 0x005792A8, 0x00579304, 0x0057F53B,
    0x00581665, 0x005817C7, 0x00581E2A, 0x0058AEEE, 0x0058D17E, 0x0058E46D, 0x0059105D,
    0x0059DAC7, 0x005A152B, 0x005A5E20, 0x005A6B3B, 0x005A6B8B, 0x005A6FEC, 0x005A96B5,
    0x005AA746, 0x005ACAF8
]

seen_funcs = {}
for h in hits:
    f_addr, f_name = find_enclosing_function(h)
    seen_funcs.setdefault((f_addr, f_name), []).append(h)

print(f"Total unique enclosing functions found: {len(seen_funcs)}")
for (f_addr, f_name), h_list in sorted(seen_funcs.items()):
    h_str = ", ".join(f"0x{x:08X}" for x in h_list)
    print(f"Function {f_name} (0x{f_addr:08X}) contains {len(h_list)} hits: {h_str}")
