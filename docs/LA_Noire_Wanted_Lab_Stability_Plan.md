# L.A. Noire Wanted Lab v2: Stability Plan and Next Steps

Companion to `LA_Noire_Wanted_System_Research.md`, `LA_Noire_No_Fail_Handoff.md` and
`LA_Noire_Weapon_Mod_Handoff.md`.

This plan comes from reviewing `C:/Tools/wanted_log.txt` (sessions 9/25 18:15 to 9/26 01:10)
alongside the research handoff and the chat history. The review was done in a session **without
Cheat Engine access**, so none of it has been tested live, and I haven't seen the current
`wanted_lab_v2.lua` source. Items marked *hypothesis* need an in-game check before anyone builds
on them. Items marked *verify* are things the current script may already do; check the source
first.

Build under review: `wanted_lab_v2 (build: gun-type check, world-ready, delayed give, spawn pin, hold)`.

---

## 0. What the log shows

### 0.1 Crash timeline (latest five `GAME GONE` entries)

| Crash | Hostile plan in use | What happened just before |
|---|---|---|
| 23:39:38 | `Police_GunCombat` (fallback since 23:38:44) | cops converting to hostile with it; crash about 4 s after the last conversion |
| 00:43:31 | `Police_GunCombat` (fallback since 00:12:36) | 15 BAR cops converted at 00:43:28–29; crash about 2 s later |
| 00:52:29 | `default_nosurrender_guncombat` | all 12 cops flipped hostile → chase within 160 ms (8 of them mid-`Actor_Shooting`); 10 showed `pin=2`; #8 lost its handle (`h=FFFF ref=-1`) 1.5 s before the crash |
| 01:01:42 | `Police_GunCombat` (fallback since 00:57:38, after a player death) | converted at 01:01:37–38; crash 4 s later, just as they started shooting |
| 01:10:45 | `Police_GunCombat` (fallback since 01:10:32) | converted at 01:10:39–41; crash 4 s later, while they were shooting |

Also relevant: the 22:06 crash came 2.5 minutes after `PLAN FIX` moved five cops onto
`Police_GunCombat` (22:04). At the time it was blamed on the bodies of dead station officers. It
may have been the plan as well.

### 0.2 What worked

- 01:05–01:07: 11 BAR cops on `default_nosurrender_guncombat` fought for 2 minutes. All died,
  cleanup ran, and nothing crashed. **The gunman plan with the BAR is stable.** Earlier notes say
  Thompson and BAR fights also ran for minutes without trouble.
- Spawning, delayed gives (`GunType … ok` every time), HOLD, the spawn pin, death cleanup, GONE
  detection, SAFE RESET on player death, and the GAME GONE auto-stop all behaved correctly.

### 0.3 Problems the log exposes

1. **Neither hostile plan stays loaded.** `default_nosurrender_guncombat` (00E7) went invalid at
   23:38:42, 00:12:36, 00:57:36 and 01:10:31. `Police_GunCombat` (00DB) went invalid at 22:45:54
   (`now UIString`). At 22:04, 00E7 had already been recycled into a `SeatInstance` while live
   cops still pointed at it.
2. **The script falls back to `Police_GunCombat` automatically**, and every fight on it has ended
   in a crash.
3. **The second `ALLHOSTILE(150)` at 01:10:26 re-added 9 dead bodies** (#12–#15, #17, #20, #26,
   #28, #29, all `state=Actor_Dead`) and pinned them. When the first of those bodies was freed
   (01:10:31), 00E7 went invalid **on the same tick**. *Hypothesis:* the plan was unloaded once
   its last users (the bodies from wave 1) were torn down.
4. **The pin byte is shared with the game.** Cops in chase mode read `pin=2`, then drop to
   `pin=0` when they switch back to hostile, and `PIN LOST … (restored)` has to repair it (#11,
   #9, #2, #8 at 01:06).
5. **Mode switches come in bursts and happen mid-action.** At 00:52:25, 12 re-plans fired in
   160 ms, 8 of them while the cop was in `Actor_Shooting`.
6. **The timestamps are unreliable.** The millisecond field isn't tied to the seconds field, so
   lines appear out of order (`01:05:54.006` printed after `01:05:54.945`). There's also one
   garbled stamp: `00:00:53:44.345`.

---

## 1. Priority 0: do these first

### 1.1 Remove the `Police_GunCombat` fallback
- **Change:** never switch the hostile plan to `Police_GunCombat` automatically. If the
  preferred hostile plan is missing or invalid, **don't convert anyone to hostile**. Leave cops
  pending, in HOLD, or in chase, then log and print `HOSTILE PLAN MISSING - conversions paused`.
- Put `Police_GunCombat` on a blocklist until an isolated test (test B, §5.3) shows it's safe.
- *Hypothesis for why it crashes:* the police combat plan probably expects squad or cover-volume
  data (`Squad` slot `Actor+0x288`, `GunCombatSquad`) that a spawned patroller doesn't have. A
  crash dump (§5.1) would confirm or rule this out.
- **Verify:** reproduce a plan unload (kill a wave, wait for the bodies to clear, or die) and
  confirm the manager pauses conversions instead of crashing.

### 1.2 Validate the plan every tick, on the cops as well as in the cache
- The cached-ID check exists (`PLAN … no longer valid`). Add a check on each managed cop: resolve
  `Actor+0x1E8` through the WeakRefManager and require class `BehaviorPlan` with the expected
  name.
- If a **live** cop points at an invalid or recycled plan (the 22:04 `SeatInstance` case), fix it
  right away on the game thread. Write a known-resident plan (`Policeman` 00B5 or whatever the
  census in 1.4 finds) and queue a re-plan. If no valid plan exists, unmanage the cop and stop
  touching him.
- Validate the stored **original plan** (`SimplePolicePlan`, `generic_policeman`,
  `policeman_work`) before writing it back on stand-down. It can be unloaded too.
- Run this check first in every tick, before any conversion or mode switch.

### 1.3 Never add dead or dying actors
- `ALLHOSTILE` and auto-recruit should skip `Actor_Dead`, and probably `Actor_Falling` and downed
  states too.
- Keep a dead registry for the session, keyed by `Actor` pointer plus handle (heap addresses get
  recycled, so the address alone isn't enough). Clear an entry when the game frees that object.
  Log `SKIP dead #n` so the filter's effect is visible.
- Evidence: 01:10:28, where 9 bodies were re-added and pinned.

### 1.4 Find a hostile plan that stays loaded, or keep ours loaded (research)
1. **Plan residency census:** every 5 s, log every `BehaviorPlan` in the WeakRefManager (name,
   handle, `entry+0` refcount). Cover these situations: police station, open street, after
   driving far away, after death and reload, and after bodies are cleared. Some plans should
   never unload. Those are the only safe hostile plans.
2. **Keep-alive experiment:** take our own +1 weak ref on the plan's WeakRefManager entry, on the
   game thread, the same way actor handles are acquired. Then kill every user of the plan and see
   whether the plan object survives. Caution: the pool force-clears actor entries regardless of
   refcount (research §9.2). Plans could also belong to a streamed resource (street-crime data),
   in which case a refcount won't hold them. So treat this strictly as an experiment, and release
   the reference on unload.
3. **Candidate plans to soak-test** with armed spawned cops: `Default_GunCombat` (used by
   case-switched cops, though it includes Surrender) and `violent_criminal`. Only test plans that
   step 1 shows are resident.
4. Also find **what loads** `default_nosurrender_guncombat`. It belongs to the rooftop street
   crime. If a loader function can be called on the game thread, the plan could be loaded on
   demand.

---

## 2. Priority 1: handle, pin and pair bookkeeping

### 2.1 The pin byte is shared with the game
- Research §9.2 says the cull loop (`0090A420`) skips an actor if `Actor+0x1C4 != 0` **or**
  `Actor+0x1C5 != 0`. The log shows the game writing `2` to `+0x1C4` during chase and `0` on the
  way out. Our code writes absolute `1`/`0`, so the two fight each other.
- **Research:** put a one-shot, auto-continue write watch on `+0x1C4` of one managed cop through
  hostile → chase → hostile. Find out who writes `2` and `0`, whether they are inc/dec or absolute
  writes, and whether the write is a byte or a dword. A dword write of 0 would also clear `+0x1C5`.
- **Fix options:**
  - If the field is a counter: pin with +1 and unpin with −1, both on the game thread, and never
    write an absolute value.
  - If the game treats it as its own flag: move our pin to `+0x1C5`, which the cull loop also
    checks. Look for other readers and writers of `+0x1C5` first.
- Unpinning with an absolute `0` can also strip a pin the game set for its own reasons.

### 2.2 A managed cop loses his handle
- At 00:52:27.937, #8 read `h=FFFF ref=-1` while in chase with `pin=1`, and the crash followed
  1.5 s later.
- **Handling:** when detected, stop every write keyed on the old handle and remove our pairs that
  reference it (on the game thread). Log `HANDLE LOST #n`. Re-acquire only once the cop is
  `Actor_OnFoot` and settled. If in doubt, unmanage him.
- **Research:** watch `Actor+6` on a cop in chase mode. All the 00:52 cops were on the
  `Policeman` plan, so the chase behaviour may release references when it ends.

### 2.3 Pair table safety (*verify*: possible heap corruption)
Research §5.1 says pairs are appended by hand at `end` (with about 236 spare entries). Check the
current script for:
- **A capacity check before each append** (`end + 12 <= capacity`). Writing past capacity
  corrupts the heap, which would cause delayed, seemingly random crashes.
- **Growth over a long fight.** A hostile ↔ chase switch should update our two entries in place,
  not append new ones. Add the total vector size to the `STATE` line and check that each managed
  cop owns exactly 2 entries.
- **A thread race.** If the CE timer writes the vector while the game thread reallocates it (a
  mission trigger or a `00A47E10` push), our write lands in freed memory. **Fix:** add and remove
  pairs on the game thread. Ideally call the game's own `00A47E10`, which removes any existing
  entry and reallocates as needed, but confirm its calling convention first with an entry-only
  logger. The `006253B0` `ret 1C` crash is the reason for that step.
- **Stale handles.** A culled or freed cop's handle entry is force-cleared and then reused by some
  other object. After that, our leftover `handle ↔ 0004 = 2` pair makes a random object hostile,
  or points at nothing. On `GONE` (and `WARNING vanished while hostile`), remove pairs for that
  handle immediately. Once per tick, sweep: every pair we own must map to a live managed cop.

### 2.4 Teardown hook (the long-term fix for bodies)
- The research names this as the right fix. Add an **entry-only** hook on `006262B0` (return to
  pool), and on the work-actor teardown once that's found. On the game thread, inside the hook,
  remove our pairs for that actor and drop our bookkeeping **before** the handle is force-cleared
  (`00626240`) and reused.
- This removes the "release at death crashes / never release crashes" dilemma for bodies.

---

## 3. Priority 1: every write goes through the game thread

*Verify* how the current script does it. According to the chat, the 0.5 s CE timer writes the
plan ID, pin and pairs directly, and only acquire, release and re-plan are queued to the game
thread.

- **Proposal:** one command queue in the `005CB280` cave, as a ring buffer of `{actor, op, arg}`.
  When the hook runs for an actor (`esi = Actor`), it applies that actor's ops in a fixed order:
  `RELEASE → ACQUIRE → REMOVE_PAIRS/ADD_PAIRS → SET_PLAN → PIN/UNPIN → REPLAN`. That's the exact
  moment the AI reads the plan, so plan and re-plan become atomic.
- The CE timer then only **reads** memory and **enqueues**.
- **Gun Anywhere:** its Give and Equip calls still run on a CE thread (`executeCode`). Route them
  through the population-hook queue that the cop weapon gives already use. That fixes the known
  crash from activating Gun Anywhere while cops were being spawned or armed (23:1x).

---

## 4. Priority 1: throttle mode switches

Evidence: the 00:52 burst (12 re-plans in 160 ms, mostly mid-shooting).

- **Per-cop cooldown:** at least 4 s between mode changes (`WS.MODE_COOLDOWN`).
- **Wider or time-based hysteresis:** cops flipped at d = 45.0–47.8, right on the threshold.
  Either widen it (chase above 50, hostile below 38) or require the distance to stay past the
  threshold for 2 s.
- **Only switch in `Actor_OnFoot`.** Defer while `Actor_Shooting`, `Actor_Cover`,
  `Actor_Falling` or reloading. The safety rules say "only re-plan while OnFoot", but the log
  shows `CONVERT … st=Actor_Shooting`. Research §9.4 allowed Shooting for the single-cop
  prototype, and that should be revisited now that there are 10+ cops.
- **Global budget:** at most 2 re-plans per manager tick, with the rest queued. This also covers
  the burst that fires on unpause after conversions were queued while paused.

---

## 5. Priority 2: diagnostics and testing

### 5.1 Capture the actual crash address (biggest single win)
All we get today is `GAME GONE`. Windows can write a minidump for every crash:

```
HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\LANoire.exe
    DumpFolder  REG_EXPAND_SZ  C:\Tools\dumps
    DumpType    REG_DWORD      1        (minidump)
    DumpCount   REG_DWORD      10
```

This is a one-time setup and needs admin. Open a dump in WinDbg (`!analyze -v`), or just read the
faulting EIP and map it to known functions:
- `0071DB90`/`007251A0` means the plan walk (a plan problem)
- `00A47C40` means a pair lookup
- `005CC7C0`/`00626240` means teardown
- `005A1C40` means the awareness sweep

Caveats: the game or an overlay may have its own crash handler, and a CE debugger attached to the
game takes the exception first. This turns guesses into facts.

### 5.2 Log fixes
- **Timestamps:** use one clock. At load, record `t0 = os.time()` and `c0 = getTickCount()`.
  Then stamp `os.date('%H:%M:%S', t0 + (now-c0)//1000)` plus `(now-c0)%1000` as the milliseconds.
- **Add to `STATE`:** pair-table size, the cop's plan name resolved fresh, raw `+0x1C4` and
  `+0x1C5`, and the hook queue depth.
- **Log a reason for every mode switch:** the distance, the state at switch time, and which rule
  fired.
- **Print the config at load** (every tunable plus the build marker), so each log session records
  its settings.

### 5.3 Controlled soak tests (change one thing at a time)

| Test | Setup | Pass criteria |
|---|---|---|
| A. Baseline | `default_nosurrender_guncombat`, 5 BAR cops, fight to the end, wait 60 s for bodies, 3 waves without dying | no crash (matches 01:05) |
| B. Police plan | same as A with `Police_GunCombat` forced deliberately, WER dumps on | confirms or clears it; the dump names the function |
| C. Plan unload | after A, watch whether 00E7 goes invalid when the last body is freed (compare `PLAN invalid` and `GONE` times) | confirms hypothesis 0.3-3 |
| D. Mode flapping | 8 cops, player runs back and forth across 45 units | no crash with the cooldown; compare with it off |
| E. Dead re-add | second `ALLHOSTILE` while bodies are present, with the filter from 1.3 | `SKIP dead` lines, no pins on bodies |
| F. Death/reload | die mid-fight, reload, `ALLHOSTILE` after world-ready | plan, gun types and template all re-resolved; no stale writes |
| G. Weapons | one type at a time: `m1_garand`, shotguns (Thompson and BAR are known good) | a list of NPC-safe weapons |

---

## 6. Priority 2: lifecycle hardening
- After `SAFE RESET`, invalidate **everything** cached (plan IDs, gun types, spawn template
  `1646975C`, PoliceManager pointer) and re-resolve at world-ready. Gun types are already
  re-checked. *Verify* the rest.
- `WL2_UNLOAD` while the game is alive should unpin managed cops and remove our pairs on the game
  thread before the hook is removed. When the game is gone, it should skip all of that and only
  clear state.
- **Cap total pinned actors** (e.g. 12). Pinned actors can't be culled, so the population system
  culls others instead, and the generic pool grows (`006247C0`). At 01:10:28, 22 actors were
  pinned at once, including the corpses.
- Order of operations on shutdown: untick or unload Gun Anywhere and the wanted lab before closing
  CE. Stale hooks and timers across restarts caused several earlier crashes.

---

## 7. Other ideas (features)

1. **Wanted trigger from the no-fail patch.** The cave at `009EAA70` already intercepts
   reason 1 (Citizen Injured) and 11 (Officer Down). Add a counter write there (for example
   `inc [WANTED_EVENTS]` plus the last reason ID) and have the wanted manager read it every tick
   to raise the wanted level, with Officer Down worth more. That makes it the natural "crime
   committed" signal (research §7). Validate the process ID before trusting the symbol, because
   registered symbols survive restarts.
2. **Waves with a cap:** at most 5 active hostile cops, and reinforcements only while under the
   cap. The trickle of one spawn per population update is already a good pacing mechanism.
3. **Spawn out of sight:** place spawns behind the camera (using the camera forward vector), more
   than 60 units away, on a pedestrian navmesh. Chases stall without navmesh (the underpass note).
   The cops then walk or run in rather than popping in.
4. **Reinforcement cars** through the partner-return system (from the research design notes).
5. **Heat decay using existing data:** the awareness entry's `unseen` time (`+0x8`, research
   §5.3) can lower the wanted level after N seconds with no cop seeing the player.
6. **A "Busted" ending:** at low wanted levels, if the player holsters (Gun Anywhere stance
   `+0DD4` = 0 or 2) and stands still near cops, stand everyone down. It gives the player an
   alternative to dying.
7. **Corpse cleanup:** return bodies to the pool via `006262B0` on the game thread after N seconds
   out of view. Only do this once the teardown hook (2.4) is understood.
8. **On-screen wanted notice** using the UI text path found during the no-fail work
   (`SetTextHash` at `00D0FAA0`). This needs research.
9. **A single core loader** (`lanmods_core.lua`) providing shared death and reload detection, the
   process guard, the game-thread command queue and logging, with Gun Anywhere and the wanted lab
   as modules. It prevents two scripts from hooking independently, and prevents the
   table-vs-Lua mismatches (like the no-fail patch missing from a saved `.ct`).

---

## 8. Suggested order for the CE session

1. The user sets up WER local dumps (5.1).
2. Remove the `Police_GunCombat` fallback (1.1), add per-tick plan validation (1.2) and the dead
   filter (1.3). Then run tests A and E.
3. Pin watch and pin fix (2.1).
4. Pair-table audit: capacity, count per cop, which thread writes it (2.3).
5. Game-thread command queue (3), including Gun Anywhere's weapon calls.
6. Mode-switch throttle (4), then test D.
7. Plan residency census and keep-alive experiment (1.4), then tests B and C.
8. Features (7).
