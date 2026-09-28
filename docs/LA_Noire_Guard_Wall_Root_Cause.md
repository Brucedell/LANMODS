# L.A. Noire Wanted System: Why the "Guard Wall" Keeps Growing

Analysis of the crash dumps `LANoire.exe.8408.dmp` and `LANoire.exe(1).33320.dmp`, compared with
`wanted_lab_v2.lua` and `LA_Noire_Wanted_System_Changes_Handoff.md`. The dumps were decoded with
Python `minidump` and `capstone`. It was done without Cheat Engine access, so the fix below has not
been tested in-game.

## TL;DR

Guards 1–19 are all symptoms of **one** bug: **handle (weak-ref) lifetimes are broken for the cops
we manage.** The game frees a cop's handle while its squad, awareness, event and relationship systems
still hold it. Each guard patches one of the places that later reads the freed handle. There are
dozens of such readers, which is why every round finds a new one. Deaths in a cluster make it happen
more often (many handles freed in the same second), but deaths are not the cause.

## Evidence 1: dump 8408 was a freed handle, not a dead cop

Crash at `00790F6A` (the loop that Guard 19 now covers):

```
00790F40  mov eax,[ebx+0C] / mov ecx,[eax+08] / movzx eax,word [ecx+edi*2]   ; squad member handle
00790F54  mov ecx,[015C64D4] / mov edx,[ecx+08]                                 ; WeakRefManager entry array
00790F60  mov ecx,[edx+eax*8+4]                                                 ; entry.object
00790F68  mov eax,[ecx]            ; "vtable"
00790F6A  mov edx,[eax+24]         ; <- AV reading 0x24 (eax = 0)
```

Registers at the fault: `edx` (entry array) = `110ECAE0` and `ecx` ("object") = `110FFE98`.

`110FFE98 - 110ECAE0 = 0x133B8 = 0x2677 * 8`, exactly aligned to an entry. So the "object pointer"
points **into the WeakRefManager's own entry array**, at another entry. Per the research doc, free
entries are linked through `entry+4`. So this handle's entry was **on the free list**: `entry+4` held
the next-free pointer, and the "vtable = 0" was the refcount word of the next free entry. The cop's
body was not the problem. The squad still listed a handle that had already been released and put back
on the free list.

The Changes handoff describes this case as "dead cop object had zeroed vtable". That reading is
mistaken, and the same misreading probably applies to Guards 9, 10, 14, 17 and 19. Guard 13 ("handle
reused by an animation node") is the same bug one step later: the freed entry was handed out again.

## Evidence 2: dump 33320 is a guard crash

The fault is at `01C40636`, inside `guard12_cave` (allocated memory, not `LANoire.exe`), with
`mov al,[eax+0C29]` and `eax = 00010000` read from `[esp+1C]`. The range check passed, and the
"pointer" was garbage from a stale object. Raising the threshold to `0x20000` only moves the crash,
because a range check can't tell a live object from freed or reused memory.

(The second 33320 file, `EXCEPTION_UNKNOWN` with parameter `0x15`, is a secondary record from the
same crash.)

## Why handles get freed while still in use

1. **Ambient cops aren't built to be combat actors.** A normal pool cop has handle `FFFF` and no
   squad. We give him a handle, and in combat the game hangs dozens of references on it (squad
   tables, awareness entries, interesting events, relationship pairs; refcount 57 has been observed).
   Some holders, such as awareness entries, store the number **without counting a reference**.
2. **The pool teardown force-clears the handle regardless of refcount** (`006262B0` → `00626240`,
   research §9.2). When a body or culled cop goes back to the pool, the handle is freed while all
   those holders still point at it. Vanilla never hits this, because pool actors never collect
   combat references.
3. **Our own +1 references make it worse.** `mw_cave`'s `a_addref` path does `inc dword ptr [eax]` on
   entries the **game** owns, and nothing ever releases it (`RELEASE_REFS = false`). The research doc
   §2.4 warns against exactly this: "Never bump refcounts on references the game owns." Once the entry
   has been force-cleared or reused, every later game release decrements an entry that belongs to
   something else. That produces early frees of unrelated objects and double insertions into the free
   list, so two objects end up sharing a handle.
4. **The guards hide the corruption instead of stopping it.** Skipping a squad member or an event
   leaves game state inconsistent, and the next reader crashes somewhere else. Guards have also caused
   crashes themselves: Guard 3 (missing `mov edi,eax`), Guard 11 (NOP padding), Guard 14 (wrong
   address, corrupted the bullet-hit dispatcher), and Guard 12 (this dump).

## The fix: control the lifetime instead of adding guards

### A. Stop bumping game-owned refcounts
Remove the `a_addref` path. Only take a reference when the cop has none (`FFFF`), and record that the
reference is ours. The reason `a_addref` was added (dump 31360: pairs left stale when the game dropped
the last reference) is already handled by the teardown pair purge and the handle-loss purge.

### B. Corpse queue: don't let a managed cop reach the pool while he's still referenced
1. At death, keep the body **pinned**, remove our pairs (on the game thread), and put the cop in a
   corpse queue.
2. Wait until the game has let go: the state has been `Actor_Dead` for about 5–10 s (the awareness
   sweep `005A1C40` drops dead entries, squads drop dead members), **and** the entry's refcount equals
   our own count (1 if we acquired the handle, 0 extra if the game owns it).
3. Then release our reference through the **normal** path (refcount − 1 → 0 → `Actor+6 = FFFF`, entry
   onto the free list). This is the same code the game uses, and it runs while the body still exists.
4. Only then unpin, and let the cull loop return the body to the pool.
5. Throttle it to one body per second. That spreads out the deaths-in-a-cluster spike.

Apply the same rule to escaped and stood-down cops: don't unpin until only our reference remains.

### C. Belt and braces in the teardown hook
`tp_cave` already runs on every pool return. Also make it check the actor's entry: if
`Actor+6 != FFFF` and the refcount is higher than ours, log `TEARDOWN WITH LIVE REFS h=… rc=…` (write
it to a counter the Lua side prints). If that line ever appears, it names the exact hole in the
lifetime handling. A more aggressive option is to refuse the pool return for such actors and re-pin
them, but test the logging version first.

### D. Integrity checker (diagnostics)
Once per tick, from Lua:
- walk the WeakRefManager free list (it must have no cycles and no entry twice)
- for each managed cop, check that `entry.object` is his `Actor` and that `[Actor]` is a valid vtable
- log the **first** tick any check fails, together with the recent actions

That tells you which event corrupts the table, instead of where the corruption crashes later.

### E. Guards after that
Keep them loaded and **watch the hit counters**. When A and B are right, the counters should stay near
0. The last 12-cop test logged 66 guard hits, which means the table was being corrupted dozens of
times per fight. Then remove the guards one at a time. Each guard is a patch into game code that can
crash on its own.

## Other notes
- **Full dumps for the next crash.** The current minidumps don't include the heap, so the
  WeakRefManager entries and objects can't be read. For one or two crashes, set `DumpType = 2` (full
  dump, 1–2 GB) under `LocalDumps\LANoire.exe`. Then the refcount and free-list state at the moment of
  the crash can be inspected directly.
- **The attached `wanted_lab_v2.lua` has only Guards 1–5** (the `CRASH IMMUNITY GUARDS (1-5)`
  section), while the handoff describes 19. Check which copy is actually loaded, using the build
  marker in `wanted_log.txt`. Stale copies have been loaded by mistake before.
- **Any crash from the period when awareness stamping wrote `+0x80`** (an out-of-bounds heap write
  past the 48-byte entry) should be treated as possibly caused by that, and not guarded.
- Going from 20 cops down to 12 lowers the rate but can't fix the bug. After A and B, test by scaling
  back up: 12, then 16, then 20.
