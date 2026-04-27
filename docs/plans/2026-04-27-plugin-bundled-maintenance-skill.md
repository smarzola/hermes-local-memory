# Plugin-Bundled Maintenance Skill Implementation Plan

> **For Hermes:** Implement directly with strict TDD. This plan is intentionally scoped to Phase 1: no new provider maintenance-status/runbook tools.

**Goal:** Make the Local Memory maintenance skill available as a Hermes plugin-bundled, namespaced skill so ordinary users can load current package-versioned guidance without syncing a copied global skill.

**Architecture:** Reuse the existing maintenance skill content as the canonical runbook, but expose it through the installed Hermes plugin shim via `ctx.register_skill("maintenance", path)`. Keep the current `sync-skills` command as a compatibility path for now, while docs and cron examples prefer the plugin skill name `local_memory:maintenance` once the plugin is installed/enabled. No new provider tools are needed in Phase 1; the skill remains the agent-facing policy/runbook layer.

**Tech Stack:** Python stdlib, Hermes plugin `ctx.register_skill`, existing shim generator, pytest, hatch packaging.

---

## Decision: no new tool for Phase 1

`memory_maintenance_status` is useful later, but not required for this step. Phase 1 can avoid new tools because:

1. Plugin-bundled skills already solve the largest drift source: copied `~/.hermes/skills` content going stale relative to the package.
2. The existing provider tools already expose every maintenance primitive needed by the skill.
3. User flexibility remains best expressed through prompt policy: recipe/phases/apply/reporting.
4. Adding a new status tool now would increase scope before validating whether namespaced plugin skill loading is enough.

A later Phase 2 can add a status/capabilities tool if real cron runs still need machine-readable migration state, last-run state, or capability discovery.

---

## Task 1: Add failing test for shim skill registration

**Objective:** Prove the generated Hermes plugin shim registers the maintenance skill with Hermes via `ctx.register_skill`.

**Files:**
- Modify: `tests/test_hermes_plugin.py`

**Step 1: Extend the test collector**

Add skill capture support:

```python
class Collector:
    def __init__(self) -> None:
        self.provider = None
        self.skills = {}

    def register_memory_provider(self, provider) -> None:  # noqa: ANN001
        self.provider = provider

    def register_skill(self, name: str, path) -> None:  # noqa: ANN001
        self.skills[name] = Path(path)
```

**Step 2: Add failing assertions to the existing shim registration test**

In `test_write_plugin_shim_creates_hermes_discoverable_register_function`, after `module.register(collector)`, assert:

```python
assert collector.skills["maintenance"].name == "SKILL.md"
assert collector.skills["maintenance"].is_file()
assert "name: local-memory-maintenance" in collector.skills["maintenance"].read_text(
    encoding="utf-8"
)
```

**Step 3: Add rendered-shim source assertion**

In `test_plugin_shim_contains_absolute_package_path_for_external_hermes_loading`, assert:

```python
assert "register_skill" in content
assert "local-memory-maintenance" in content
```

**Step 4: Run the targeted failing test**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_hermes_plugin.py
```

Expected: FAIL because the shim currently only calls `register_memory_provider`.

---

## Task 2: Implement skill registration in the shim generator

**Objective:** Make the shim register the package's maintenance skill as plugin skill `maintenance`.

**Files:**
- Modify: `src/hermes_local_memory/hermes_plugin.py`

**Step 1: Add skill path resolution to shim template**

Update the generated shim to compute candidate skill paths for both development checkouts and installed wheels:

```python
PACKAGE_ROOT = Path(...)
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from hermes_local_memory import LocalMemoryProvider  # noqa: E402


def _maintenance_skill_path() -> Path:
    candidates = [
        PACKAGE_ROOT.parent / "skills" / "local-memory-maintenance" / "SKILL.md",
        PACKAGE_ROOT / "skills" / "local-memory-maintenance" / "SKILL.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def register(ctx):
    ctx.register_memory_provider(LocalMemoryProvider())
    if hasattr(ctx, "register_skill"):
        ctx.register_skill("maintenance", _maintenance_skill_path())
```

Note: use `hasattr` so the shim remains compatible with older/smaller Hermes contexts or tests that only support memory-provider registration.

**Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_hermes_plugin.py
```

Expected: PASS.

---

## Task 3: Add packaging tests for plugin-bundled skill availability

**Objective:** Ensure release artifacts continue to include the skill path used by the plugin shim.

**Files:**
- Modify: `tests/test_package_artifacts.py`

**Step 1: Rename/clarify existing config test**

Keep the existing assertion that `/skills` is included in hatch build config.

**Step 2: Add assertion that wheel/sdist skill path is the one shim expects**

Existing artifact test already checks `skills/local-memory-maintenance/SKILL.md`. Add a comment or assertion helper that this is the plugin skill source as well:

```python
skill_path = "skills/local-memory-maintenance/SKILL.md"
```

No behavior change may be necessary beyond keeping the test green; the important new regression is the shim test.

---

## Task 4: Update docs from synced skill to plugin skill as primary path

**Objective:** Make docs recommend `local_memory:maintenance` as the primary maintenance skill while keeping `sync-skills` as compatibility/legacy.

**Files:**
- Modify: `docs/setup.md`
- Modify: `docs/cli.md`
- Modify: `README.md`
- Modify: `AGENTS.md` if scheduled maintenance guidance mentions copied skill
- Modify: `skills/local-memory-maintenance/SKILL.md` cron skeleton if needed

**Step 1: Update setup docs**

Add after shim installation:

```markdown
The shim also registers the package-versioned maintenance skill as the plugin skill `local_memory:maintenance`. Prefer loading that namespaced plugin skill in scheduled jobs instead of copying a global skill into `~/.hermes/skills`.
```

**Step 2: Update cron prompt skeleton**

Prefer:

```text
Load and follow the plugin-provided `local_memory:maintenance` skill.

Policy:
- recipe/phases: ...
- apply: ...
- reporting: ...
```

Keep mention that `sync-skills` remains available for older Hermes installations that cannot load plugin-provided skills.

**Step 3: Update CLI docs**

Clarify `sync-skills` as compatibility rather than primary path.

---

## Task 5: Run full verification

**Objective:** Verify tests, lint, compile, and build artifacts.

Run:

```bash
PYTHONPATH=src pytest -q
ruff check .
PYTHONPATH=src python -m compileall -q src tests
uv build
```

Expected: all pass. Artifact test should pass after `uv build` includes `skills/local-memory-maintenance/SKILL.md`.

---

## Task 6: Commit implementation branch

**Objective:** Commit branch work without releasing yet.

Run:

```bash
git status --short
git add src/hermes_local_memory/hermes_plugin.py tests/test_hermes_plugin.py tests/test_package_artifacts.py docs/setup.md docs/cli.md README.md AGENTS.md skills/local-memory-maintenance/SKILL.md docs/plans/2026-04-27-plugin-bundled-maintenance-skill.md
git commit -m "feat: bundle maintenance skill through plugin shim"
```

Expected: one commit on `feat/plugin-bundled-maintenance-skill`.

---

## Open follow-ups deliberately out of scope

- No `memory_maintenance_status` tool in Phase 1.
- No stateful maintenance protocol/runbook tool in Phase 1.
- No automatic cron installer changes in Phase 1.
- No removal of `sync-skills`; keep it for compatibility until plugin-bundled skills are proven in real use.
