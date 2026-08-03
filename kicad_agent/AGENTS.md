# KiCad Project Guidelines for Hermes Agents

--- 1️⃣ Prefer MCP Tools for All Circuit Operations
   *If a required MCP tool is missing* → fall back to the **generic “search‑tools”** workflow (see §6) before giving up.

--- 2️⃣ Component Availability Checks
   *If a component is not found* → try the following in order:
   1. Search the **global symbol libraries** (`mcp__kicad_general__list_symbol_libraries`).
   2. Run a **keyword search** (`mcp__kicad_general__search_symbols`).
   3. **Create a placeholder symbol** (`mcp__kicad_general__create_symbol`) and register it.
   4. **Ask the user** for an alternative part (only after the three automated attempts have failed).

--- 3️⃣ Always Run ERC After Modifications
   *If ERC returns a “missing PWR_FLAG” or any other error* → invoke the **auto‑fix loop** (see §5) before aborting.
   *If the auto‑fix loop cannot clear a violation* → move to the fallback strategy in §6 rather than stopping outright.

--- 4️⃣ Reporting & Transparency
   *When a tool call fails* → log the failure (tool name, args, error) and **continue** to the next fallback option.
   *Only after all fallback options are exhausted* → present a concise user‑facing message that explains *what* failed and *why* the agent could not recover.

--- 5️⃣ Automated “Try‑Again” Loop
   For any MCP call that returns an error:
   1. **Retry once** after a short `sleep(0.5 s)` (use `terminal` or `time.sleep` via `execute_code`).
   2. If the second attempt still fails, **switch to an alternative tool** (e.g. a higher‑level batch tool, a search‑tool, or a manual‑fallback implementation).
   3. If a fallback succeeds, **re‑run the original step** (e.g. re‑run ERC after a successful auto‑fix).
   4. Keep a **retry‑counter** in the agent’s temporary state (max 3 attempts per step) to avoid infinite loops.
   5. Log every transition (original → retry → fallback) for later debugging.

--- 6️⃣ Fallback Toolbox & Escalation Policy
   *When the primary workflow cannot proceed* → consult this toolbox in order:
   1. **Alternative MCP tools** – many actions have a batch or “*‑no‑connect*” variant that can achieve the same result with fewer calls.
   2. **Generic “search‑tools”** – call `tool_search` for a tool whose description matches the missing capability; then `tool_describe` + `tool_call`.
   3. **Shell‑level work‑arounds** – limited to safe, non‑destructive commands (e.g. `ls`, `cat`, `grep`) via `terminal` when MCP cannot be used.
   4. **User clarification** – if steps 2‑3 still fail, issue a `clarify` prompt with a concise question (e.g. “I could not find a suitable MOSFET symbol. Should I create a generic one?”). The agent only asks after exhausting the automated options.
   5. **Abort** – only after all of the above have been tried and logged.

--- 7️⃣ Preference for Explicit Arguments
   *When a tool is unavailable* → automatically **replace it with a more generic equivalent** (e.g. replace `add_schematic_component` with `batch_add_and_connect` where possible) before giving up.

These guidelines are written in a simple, machine‑readable style so that *agent* scripts can easily follow them when working with KiCad projects via the Model‑Context‑Protocol (MCP) tools.

---

## 🔁 Agentic ERC Loop
- **Goal:** Produce manufacturable KiCad designs with zero ERC violations.
- **Loop:** After every modification:
  1. Run `mcp__kicad_general__run_erc`.
  2. Categorize violations (errors, warnings, info).
  3. For each violation with confidence > 90 % (based on past patterns), apply an automated fix (e.g., `snap_to_grid`, `add_no_connect`, `delete_schematic_wire`).
  4. Re‑run ERC.
  5. Repeat up to **5 iterations** or until no violations remain.
- **Stopping criteria:**
  - No ERC violations left.
  - Reached 5 iterations.
  - Remaining violations lack a confident automated fix.

## 📚 Learning & Memory
- Store recurring ERC patterns and their successful fixes in `memory.md`.
- When a new ERC result matches a known pattern, increase confidence for the associated fix.
- Update fix strategies in memory whenever a better solution is discovered.
- Periodically prune stale entries (older than 30 days) to keep memory concise.
