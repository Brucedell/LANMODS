# L.A. Noire WantedCars: Review of the Spawn Scripts and a Plan for Navigation

Reviewed: `wc_spawn_cave.lua`, `wc_reinstall.lua`, `SESSION_HANDOFF_2026-09-29.txt` (the other
agent's handoff), `Goal.txt`, and the chat log "LA Phase 1 project status check" (9/27–9/29).

This review was done **without Cheat Engine or Ghidra access**, so nothing in it has been tested
in-game. **Verify** marks something to check before building on it. **Idea** marks an untested
proposal. Addresses are research addresses (base `0x4A0000`); convert them with `R()` as usual.

---

## TL;DR

1. `wc_spawn_cave.lua` has bugs that will show up on the next test:
   - It saves the wrong value as the car pointer.
   - It hardcodes a heap pointer for the police VehicleType, and that pointer won't survive a
     relaunch.
   - Its Lua trigger stops working after the first failure.

   Fixes are in §2.
2. `wc_reinstall.lua` and `wc_spawn_cave.lua` conflict: running reinstall after spawn_cave silently
   disables spawning. Retire reinstall (§3).
3. The new cave uses the least reliable method: a random spawn point plus the game's own crew
   request (AFC860). It dropped what the one successful end-to-end run used: picking a spawn point
   that faces the player, and seating our own cops with 005DD110 in seats 1 and 3. The helpers
   that ran that flow exist only in CE's Lua memory. If that CE window is still open, save their
   source now (§4).
4. Navigation: nothing tells the car where to go. It follows traffic and turns at random at
   junctions. The options, ranked, are in §5:
   - find the rule that recycles cars,
   - check AF6050's other parameters,
   - drive the car with the chase path planner,
   - bias the junction choice,
   - spawn on the player's own road.
5. Test the drift on ambient cars that drive past you, so it no longer waits on navigation (§6).

---

## 1. Where things stand

| Piece | Status | Source |
|---|---|---|
| Spawn a car on a road out of sight (AF6050 → AFBA80) | works | chat 9/27, 9/29 |
| Game's own crew (`AFC860(car,1)`) | unreliable: only works when a patrolman model is streamed in; 0 of 5 in one area | chat 9/29 12:47 |
| Own cops via `SPAWNCOP("policeman_driver")`, seated with 005DD110 | works in seats 1 and 3; seat 0 releases the AIVehicle | chat 12:58 |
| Spawn point facing the player (E9C050 sampler, row 2 = forward) | works | chat 13:02 |
| Brake (AIVehicle→+0x0C→+0x32 = 1) + exit (Actor_Vehicle +0x40 = 0) | works, parked or moving | chat 9/27 |
| End to end: spawn → drive in → brake → exit | worked once (13:07); the game added a third cop in seat 0, and he wasn't ejected | chat 13:08 |
| Speed boost (SplineDPF+0x10) | works | chat 16:13 |
| Reaching the player | often fails because of random turns | chat 16:13 |
| Physics switch + drift | never reached | chat 16:13 |
| Empty "probe" cars | recycled after about 5 s | chat 16:18 |

---

## 2. Bugs in `wc_spawn_cave.lua`

### 2.1 The stored "car" is AFC860's return value (definite)

```
test eax, eax
jz _fail
or byte ptr [eax+19C6], 4
push 1
push eax
call AFC860               ; overwrites eax
mov [wc4_data+4], eax     ; <- AFC860's return value, not the car
```

EAX is the return register, so after `call AFC860` it holds whatever AFC860 returns. Unless AFC860
happens to return its first argument, `WC.lastCar` and the "Spawn SUCCESS! Car VehicleInstance = …"
line are wrong. Anything built on `WC.lastCar` then reads or writes the wrong memory, including
distance tracking, brake, seating and exit. The fix is to store the car before the call (§2.5).

### 2.2 The police VehicleType is a hardcoded heap address (high risk)

`mov eax, 168A80B0` is the default, and `WC.spawnPoliceCar()` always writes 0 to `wc4_data+8`, so
the default is used every time. `0x168A80B0` is a heap object read during one launch. `R()` fixes
module addresses, but heap addresses change between launches, especially with ASLR (the module base
has already moved from `0x4A0000` to `0x90000`). On a new launch AFBA80 gets a random pointer as its
type and will most likely crash.

The fix is to resolve the type once per launch in Lua, pass it in `wc4_data+8`, and have the cave
fail cleanly if it's 0. There are two known ways to resolve it:

- The partner code reads the police type from `PoliceManagerSettings+0x34`, a handle that resolves
  to `ford_4dr_1947_police_vehicle`.
- The 9/27 session listed all 122 VehicleTypes by name. Rebuilding that name lookup also gives you
  the "spawn any car" utility (`WC.spawnCar(name)`).

**Verify** on every launch, before the first spawn, that the pointer's vtable is inside
LANoire.exe and that the type's name is the one you expect.

### 2.3 The spawn record isn't zeroed before AF6050 (likely)

The 16-byte record at `[esp+10]` is uninitialised stack. The success check reads `record+8`
(`cmp dword ptr [esp+18], 0`). If AF6050 fails without writing that field, the check can pass on
leftover stack data and AFBA80 gets a garbage road pointer. That's the same kind of crash as the 9/27
"record 4 bytes off" one. Zero the record first. Once you've confirmed what AF6050 returns, check its
return value as well.

### 2.4 Lua side

- **The trigger stops working after one failure (definite).** `WC.spawnPoliceCar()` refuses to run
  unless the flag is 0. On failure the cave leaves it at `0xFF`, so every later call prints "Busy or
  pending flag: 255" and does nothing until someone writes 0 by hand. Treat `0xFF` (and any error
  code) as idle.
- **The 1 s busy-wait blocks CE's main thread.** The CE timers (monitors, exit guard) don't run
  while it spins. The 9/29 session hit the same thing ("my checks were pausing CE's timers"). Poll
  with a timer instead (§2.5).
- **Remove the `debug.setupvalue(WC.go / WC.seat / WC.evalSpawn, n, data)` lines.** They overwrite
  upvalue #2 or #4 without checking what it is. Upvalue numbering follows the order in which names
  first appear in each function, and nobody knows what #2 is in those functions. If it isn't the
  data address, they replace a helper or an offset with a number and break in odd ways. There's a
  bigger problem too: those helpers use the old cave's commands (seat, sample, spawn from record),
  and the new cave doesn't implement any of them.
- **Verify AFC860's calling convention.** `ret 8` shows that the callee pops two stack arguments, but
  a `__thiscall` with two arguments does the same. AFC860 sits among the TrafficManager functions, so
  it may well read ECX as `this`. If it does, the cave currently passes whatever AFBA80 left in ECX.
  Check its first instructions for a read of ECX before any write to it. Setting `ecx = [TM_PTR]`
  before the call is harmless either way, so the fixed cave does that.
- **Verify that 19C6 bit 4 really stops recycling** (§5.1). The handoff calls it the anti-culling
  flag, but the chat only ever said "probably".

### 2.5 Fixed installer core (untested)

Keep the rest of the installer (prologue restore, symbol cleanup, hook write, verification). This
replaces the `aaScript` and `WC.spawnPoliceCar`. It passes the addresses in with `define()` so the
Auto Assembler text needs no `%08X` positional arguments.

```lua
local aaScript = string.format([[
define(RSPM_PTR,%08X)
define(TM_PTR,%08X)
define(F_AF6050,%08X)
define(F_AFBA80,%08X)
define(F_AFC860,%08X)
define(TM_RET,%08X)

alloc(wc4_cave, 2048)
alloc(wc4_data, 1024)
registersymbol(wc4_cave)
registersymbol(wc4_data)

label(_ok)
label(_fail_type)
label(_fail_point)
label(_fail_spawn)
label(_done)
label(_ret_to_game)

wc4_cave:
    // stolen 6-byte prologue
    push ebp
    mov ebp, esp
    and esp, -10

    cmp dword ptr [wc4_data], 1
    jne _ret_to_game
    mov dword ptr [wc4_data], 2

    pushad
    sub esp, 40

    // a VehicleType must come from Lua; no hardcoded default
    cmp dword ptr [wc4_data+8], 0
    je _fail_type

    // zero the 16-byte spawn record at esp+10
    xor eax, eax
    mov [esp+10], eax
    mov [esp+14], eax
    mov [esp+18], eax
    mov [esp+1C], eax

    // AF6050(ecx = RSPM, edx = &record, 5.5f, 0, 0), callee pops 0xC
    mov ecx, [RSPM_PTR]
    test ecx, ecx
    jz _fail_point
    lea edx, [esp+10]
    push 0
    push 0
    push 40B00000
    call F_AF6050
    cmp dword ptr [esp+18], 0      // record+8 = road segment
    je _fail_point

    // AFBA80(ecx = TrafficManager, eax = type, [esp] = &record), callee pops 4
    mov ecx, [TM_PTR]
    test ecx, ecx
    jz _fail_point
    mov eax, [wc4_data+8]
    lea edx, [esp+10]
    push edx
    call F_AFBA80
    test eax, eax
    jz _fail_spawn

    mov [wc4_data+4], eax          // save the car BEFORE any other call
    or byte ptr [eax+19C6], 4

    // optional: wc4_data+C = 1 asks the game for its own crew
    cmp dword ptr [wc4_data+C], 0
    je _ok
    mov ecx, [TM_PTR]              // harmless if AFC860 is stdcall
    push 1
    push eax
    call F_AFC860                  // callee pops 8

_ok:
    mov dword ptr [wc4_data], 0
    jmp _done

_fail_type:
    mov dword ptr [wc4_data], FE
    jmp _done

_fail_spawn:
    mov dword ptr [wc4_data+4], 0
    mov dword ptr [wc4_data], FD
    jmp _done

_fail_point:
    mov dword ptr [wc4_data+4], 0
    mov dword ptr [wc4_data], FF

_done:
    add esp, 40
    popad

_ret_to_game:
    jmp TM_RET
]], RSPM_PTR, TM_PTR, AF6050, AFBA80, AFC860, TM_RET)
```

Status codes in `wc4_data`: `0` idle/done, `1` requested, `2` running, `FF` no spawn point or null
manager, `FE` no VehicleType given, `FD` AFBA80 returned 0.

```lua
-- typePtr: a VehicleType* resolved THIS launch. wantCrew: true = also call AFC860(car,1).
-- cb(car) runs when the game thread answers.
WC.spawnCar = function(typePtr, wantCrew, cb)
  local st = readInteger(data)
  if st == 1 or st == 2 then print("[WCS] busy, flag=" .. st) return false end
  if not typePtr or typePtr == 0 then print("[WCS] no VehicleType") return false end
  writeInteger(data + 4, 0)
  writeInteger(data + 8, typePtr)
  writeInteger(data + 0xC, wantCrew and 1 or 0)
  writeInteger(data, 1)

  local t, t0 = createTimer(nil, false), getTickCount()
  t.Interval = 50
  t.OnTimer = function(sender)
    local s = readInteger(data)
    if s == 0 then
      sender.destroy()
      WC.lastCar = readInteger(data + 4)
      print(string.format("[WCS] spawned car %08X", WC.lastCar))
      if cb then cb(WC.lastCar) end
    elseif s and s >= 0xFD then
      sender.destroy()
      print(string.format("[WCS] spawn failed, code %X", s))
    elseif getTickCount() - t0 > 2000 then
      sender.destroy()
      if s == 1 then writeInteger(data, 0) end   -- cancel: traffic isn't updating
      print("[WCS] no answer from the game thread, flag=" .. tostring(s))
    end
  end
  t.Enabled = true
  return true
end
```

---

## 3. `wc_reinstall.lua` conflicts with `wc_spawn_cave.lua`

- **Its cave has no spawn code.** It holds only the stolen prologue and a jump back, with no trigger
  check. After running it, `WC.spawnPoliceCar()` sets the flag and nothing ever answers.
- **It breaks an existing spawn cave.** If `wc4_cave` exists (from `wc_spawn_cave.lua`), reinstall
  reuses it and writes 11 bytes over its start. The jump back lands on top of
  `cmp [wc4_data],1`, so all the spawn code after it becomes dead code. Reinstall also zeroes
  `wc4_data`.
- **Stale symbols can point into game memory.** CE keeps registered symbols when the game restarts,
  so after a relaunch `wc4_cave` still resolves to the old process's address. The "readable" check
  only proves that something is mapped there in the new process, and in a 32-bit game that's often
  heap. The script would then write code into game memory and point TrafficManager::Update at it.
  This might be what the handoff calls "page protection dropouts".

**Recommendation:** delete `wc_reinstall.lua` and make `wc_spawn_cave.lua` the only installer. It
already restores the prologue, drops the old symbols and allocates fresh memory. If you keep any
reuse logic, save the PID at install time (`getOpenedProcessID()`) and treat the symbols as stale
whenever it has changed.

---

## 4. Recover the helpers that worked, before CE closes

The only end-to-end success (13:07) ran on four helpers, `WC.launchMark`, `WC.findNewCops`,
`WC.ejectAll` and `WC.stopAndExit`, plus the old cave (spawn from record, E9C050 placement sampling,
005DD110 seating). The 9/29 session never saved any of it to a file: "These helpers only exist in CE's
current Lua state." Also, once `wc_spawn_cave.lua` has run, the helpers still write to the old
`wc4_data`, which nothing reads any more. Even if they're still loaded, they silently do nothing.
That may explain part of today's trouble.

A game restart is fine, and only a CE restart loses them. If the same CE window is still open, this
saves the source of every chunk that defined a `WC.*` function:

```lua
local path = [[C:\Tools\wc_recovered.lua]]
local f = assert(io.open(path, "w"))
local ids, n = {}, 0
for name, fn in pairs(WC or {}) do
  if type(fn) == "function" then
    local info = debug.getinfo(fn, "S")
    local src = info.source or ""
    if not ids[src] then
      n = n + 1; ids[src] = n
      f:write("--================ CHUNK #", n, " ================\n", src, "\n\n")
    end
    f:write(("-- WC.%s = chunk #%d, lines %d-%d\n\n"):format(
      name, ids[src], info.linedefined, info.lastlinedefined))
  end
end
f:close()
print("[WC] wrote " .. n .. " chunks to " .. path)
```

When a chunk is loaded from a string without a name, Lua keeps the whole string as its `source`. So
this usually recovers the full code, including the old cave's Auto Assembler text if it was in the
same chunk. If a chunk shows only a short name like `=mcp` or `@file`, the bridge named its chunks
and this method can't get the text back. As a last resort, `string.dump(fn)` saves the bytecode
without upvalues.

Then build **one** cave with the old command set plus the §2 fixes:

- sample a spawn point,
- spawn from a given record,
- seat an actor in seat N,
- request the game's crew,
- later on, the navigation and drift calls.

Use one flag word per command (or a small command ring), and keep the rule "queue from Lua, run on
TrafficManager::Update".

**Seat conflict.** AFC860 reserves the crew seats. The 12:40 log shows both seats flagged "occupant
requested" (0x46/0x16), most likely seats 0 and 1. If you seat your own cop in seat 1 after calling
AFC860, he can collide with a pending patrolman. When you seat your own cops, either skip AFC860 or
use seats 2 and 3 (**verify** that seat 2 exists on the Ford).

---

## 5. Navigation: getting the car to the player

What we know:

- AFBA80 gives the car a normal traffic route: B92060 attaches a path follower from the
  AIVehicleManager pool.
- TrafficDPP picks the next road at random at each junction.
- The partner's return car isn't given a destination either: 0075F3C0 sets none. The 9/29 reading
  was that AF6050 picks points on roads whose traffic flows toward the camera. The partner then rides
  along until the car is close.

So choosing a spawn point that faces the player only fixes the first road. Here are the options,
starting with the cheapest and most useful.

### 5.1 Find the recycle rule (read-only; unlocks several things)

Empty cars are released after about 5 s, and cars that pop in within view after about 1 s. Find the
TrafficManager pass that releases a car back to the pool, where the handle becomes FFFF. It's the
counterpart of BFB3E0. Then read which fields exempt a car:

- 19C6 bit 4,
- the claim handle at +0x124A that 0075F3C0 checks,
- occupants,
- distance or visibility.

If a flag or a claim keeps an empty car alive:

- the probe strategy works again: spawn 3–4 probes, keep the one that closes in, and seat the crew
  in it;
- you can seat the cops after the car has shown it's heading your way;
- the "spawn any car in front of me" utility becomes possible.

### 5.2 Check AF6050's other parameters (read-only, minutes)

The cave passes (5.5f, 0, 0). Decompile AF6050 and look at exactly how 0075F3C0 calls it. If
parameter 4 or 5 is a target position, a direction bias or a distance band, making the same call as
the partner may already give points that lead to the player.

### 5.3 Drive with the chase planner (best native option)

The driving controller already has a Chase mode (ChaseDPP pursues a target over the road network),
as well as Pathed and Stop modes. ChaseBehavior's driving branch (00734A80) puts the car's AI on a
chase route with B91C40, B91E80 and B924D0. B924D0 also shows up around the spawner. Decompile all
three:

- If one takes (AIVehicle, target) or a position, call it from the cave on the spawned car with the
  player as the target, and re-issue it about once a second. That needs no ChaseBehavior, ChaseGroup
  or plan change. The car keeps its AIVehicle because seat 0 stays empty or holds the game's driver.
- If they need a ChaseGroup or formation pointer, check what PoliceManager's IncidentalChase
  "pursuers" group holds, and whether you can borrow it, before building anything.

This is also the route to real pursuits later (the Phase 2 item "Police cars arriving and
pursuing"). Decode it fully before calling anything. A wrong call here is the same kind of crash as
005AE4F3.

### 5.4 Bias the junction choice (fallback)

Find the TrafficDPP method that picks the next road: it writes route +0x68 and calls the RNG. Hook it
so that, for cars on our list, it picks the connected road whose far end is closest to the player
instead of a random one. A greedy choice works well on a street grid like 1947 LA. Add a no-U-turn
rule, and fall back to random when every option takes the car further away. The rest of the traffic
driving stays as it is.

Overwriting +0x68 from Lua after the choice is tempting but risky, because the transition spline may
already have been built.

### 5.5 Spawn on the player's own road (no new reverse engineering)

The 9/27 session could index streamed road segments (95 were found) and had the E9C050 "where would
it spawn" sampler. Build spawn records on the segment nearest the player, or on the one that feeds
into it:

- Sweep the position field (+0) through the sampler until the transform lands 80–150 units away.
- Keep only points outside the camera view.
- Require row 2 (forward) to point at the player.

The game computes the position itself, so this avoids the earlier mistakes in converting positions.
The car then passes the player before its first junction choice.

### 5.6 Arrival logic (applies to every option)

- Stop at the closest approach, not at a fixed radius: stop when the distance is under about 60 and
  has grown for 2 samples, or when it's under about 20.
- Braking distance grows with the boost, so start braking earlier at 30 u/s.
- Eject using the car's occupant list (VehicleInstance+0x11DE; count via 00BE5E80), skipping the
  player and partner. Keep re-checking for about 5 s after the stop, so a game driver who loads late
  also gets out.

---

## 6. The drift stop: test it without navigation

The drift never ran only because the car never got close. Build it as `WC.driftStop(car)` and test
it on ambient police cars driving past you, the same way `WC.stopAndExit()` was tested:

1. Read the speed (SplineDPF+0x10) and the forward vector (row 2).
2. Switch the car to physics with the game's own mode switch (00BE6560), run on the game thread. Don't
   use the route stop flag for this. **Verify** which field holds the drive mode: the chat mentions
   both +0x10DC (set to 2 by AFBA80) and +0x10DE (2 = spline, 0 = physics).
3. Right after the switch, set the rigid body's linear velocity to speed × forward. Otherwise the car
   may stop dead instead of sliding.
4. For the slide, use the game's own handbrake rather than a yaw kick: set handbrake = 1, full steer
   and throttle 0 for about 0.5–1 s. That needs the control inputs (below).
5. When the speed drops below about 1 u/s, eject everyone (§5.6).

**Finding the control inputs.** The user can do this alone in CE:

1. Drive any car, hold the handbrake and scan for the float 1.0.
2. Release it and scan for 0.0.
3. Repeat until only a few results remain.
4. Do the same for steering (−1/+1) and throttle.
5. See where the address sits relative to the player's VehicleInstance or its physics DPF.

An AI car in physics mode has its inputs rewritten every frame by its PhysicsDPF. Either write them
from the game-thread hook after the DPF has run, or test on a car with no AIVehicle. A car with an
actor seated in seat 0 has no AIVehicle, so nothing else writes its inputs.

---

## 7. Smaller leads

- **A visible driver.** 00680040 releases the AIVehicle (B93D30) when seat 0 is filled. Yet the
  game's own streamed patrolmen sit in seat 0 and the car keeps its AI (the 12:35 and 13:07 runs), so
  the release must be conditional. Decompile the branch around the B93D30 call and see which flag or
  path skips it. Seating a `SPAWNCOP` policeman_driver in seat 0 that way would give the car a real
  driver.
- **Spawn any car.** Once §5.1 is known, spawn through traffic out of sight and keep the car alive.
  Alternatively, look in the RTTI class list for a parked-car manager. Street-parked cars that you
  can commandeer aren't traffic, so they may not be culled the same way.
- **Standing rule from the 9/29 crash:** never change a seated cop's plan (null behaviour data at
  005AE4F3).

---

## 8. Suggested order for the next session

1. If that CE session is still alive, recover the `WC.*` sources (§4).
2. Apply the §2 fixes, delete `wc_reinstall.lua`, and resolve the VehicleType on every launch.
3. Read-only work: §5.2 (AF6050's parameters), §5.1 (the recycle rule) and §5.3
   (B91C40/B91E80/B924D0).
4. Live: one spawn with the fixed cave, passengers seated in seats 1 and 3, no AFC860. This confirms
   the car-pointer and type fixes.
5. Live: `WC.driftStop` on an ambient car.
6. Live: whichever of §5.3, §5.4 or §5.5 the read-only work supports.
