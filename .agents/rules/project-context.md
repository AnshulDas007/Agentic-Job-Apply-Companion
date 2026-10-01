---
trigger: always_on
---

# Agentic-JobApply-Companion — Persistent Context

- Whenever you produce an implementation plan or update project 
  status, write it to IMPLEMENTATION_PLAN.md and TASK_STATUS.md 
  in the repo root as real files — not only as an in-chat artifact. 
  Keep these files updated as tasks complete.
- Before starting any task, check for IMPLEMENTATION_PLAN.md and 
  TASK_STATUS.md in the repo root. If they exist, treat them as 
  ground truth — do not regenerate the implementation plan or 
  re-derive architecture decisions already documented there.
- Only re-analyze files you are about to directly modify. Do not 
  re-scan the full codebase to "catch up" — the plan and status 
  files are the source of remain for progress.
- CandidateProfile schema: Experience and Project fields are 
  strictly separate types — never populate one from the other.
- Never auto-accept legal consent checkboxes or e-signature 
  toggles. Typed-name-only signature fields may be auto-filled.
- API keys live only in .env, never hardcoded.