# Dashboard clarity audit — Phase 17

Date: August 21, 2026

## Evidence captured

- `01-current-dashboard.png` shows search and the event timeline competing in the same
  continuous page as setup and operations.
- `02-dashboard-entry.png` shows regression-gate controls appearing in the main path.
- `03-first-screen.png` shows a narrow first-time experience dominated by manual scene
  geometry and edge infrastructure before the user can describe a camera job.
- `04-guided-dashboard-complete.jpg` shows the redesigned first screen with one clear
  camera-instruction task and advanced tools removed from the primary path.
- `05-plan-simulation.jpg` shows the passed replay gate, no-side-effect simulation
  confirmation, explicit deploy button, stopped usage state, and simplified alerts.

## Main findings

1. The basic product loop was distributed across many equally prominent panels.
2. First-time users encountered internal terms such as edge devices, normalized
   coordinates, MediaMTX, and regression gates before completing a useful task.
3. Camera selection, instruction entry, rule review, testing, deployment, and analysis
   control did not read as one sequence.
4. The long single page made it hard to know what was required and what was optional.
5. Infrastructure and investigation tools had the same visual priority as the core job.

## Implemented response

The default `Automations` view is now a guided camera-to-alert flow with one prominent
plain-language instruction box. It reveals review, plan, simulation, replay gate,
deployment, analysis control, and recent alerts in order. Existing camera setup,
geometry, edge fleet, evaluation laboratory, alert routing, evidence search, event
timeline, and audit log remain intact under `Advanced tools`.
