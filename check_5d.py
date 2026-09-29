from map_funcs import find_enclosing_function

addrs = [0x005D9953, 0x005DA98F, 0x005DB919, 0x005D9900, 0x005DA900, 0x005DB900]
for a in addrs:
    f_addr, f_name = find_enclosing_function(a)
    print(f"0x{a:08X} -> {f_name} (0x{f_addr:08X})")
