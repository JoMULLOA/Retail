# Tasks: ByteTrack Tracking + Heatmap Visualization

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80 (40 app.py + 25 index.html + 5 bytetrack.yaml + 10 wiring) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

---

## Phase 1: Foundation — Config & State

- [x] 1.1 **Create `config/bytetrack.yaml`** — track_buffer=45, match_thresh=0.8, fuse_score=True, new_track_thresh=0.4 (+5 lines, no deps)
- [x] 1.2 **Add tracking globals to `app.py`** — `_seen_ids: set[int]`, `_heatmap_acc: np.ndarray | None` guarded by single-thread access (+3 lines, no deps)
- [x] 1.3 **Add new `_state` fields** — `unique_persons: 0`, `heatmap_enabled: True` to state dict + init in `/upload` (+3 lines, depends on 1.2)

## Phase 2: Core — ByteTrack Pipeline

- [x] 2.1 **Replace `model(frame)` with `model.track()`** — Use `persist=True, tracker="config/bytetrack.yaml"`, extract `boxes.id.int().cpu().tolist()` (+10 lines, depends on 1.1, 1.2)
- [x] 2.2 **Update labels to `ID:{n} {conf}%`** — Change `f"Persona {conf:.0%}"` → `f"ID:{tid} {conf:.0%}"` (+2 lines, depends on 2.1)
- [x] 2.3 **Publish unique ID count** — `_seen_ids.add(tid)` per detection, set `unique_persons=len(_seen_ids)` in frame state (+3 lines, depends on 1.2, 2.1)

## Phase 3: Backend — Heatmap

- [x] 3.1 **Lazy-init heatmap accumulator** — `np.zeros((H, W), dtype=np.float32)` on first frame if `_heatmap_acc is None` (+3 lines, depends on 1.2)
- [x] 3.2 **Draw brush per detection** — `cv2.circle(_heatmap_acc, (cx, cy), 40, 1.0, -1)` at bbox centroid (+3 lines, depends on 3.1)
- [x] 3.3 **COLORMAP_JET compositing** — Normalize → applyColorMap → addWeighted(frame, heatmap, 0.6, 0.4, 0), gated on `_state["heatmap_enabled"]` (+6 lines, depends on 3.2, 1.3)

## Phase 4: Toggle Endpoint + Frontend

- [x] 4.1 **Add `POST /toggle_heatmap`** — Toggle `heatmap_enabled`, return state (no body needed) (+5 lines, depends on 1.3)
- [ ] 4.2 **Add "Personas únicas" stat card** — `<div class="stat-card">` between "Máximo concurrente" and "Detecciones totales" in `index.html` (+7 lines, depends on 2.3)
- [ ] 4.3 **Add heatmap toggle checkbox** — `<input type="checkbox" id="heatmapToggle" checked>` in video panel header with dark toggle CSS (+8 lines, depends on 4.1)
- [ ] 4.4 **JS: toggle fetch + unique ID polling** — `heatmapToggle.onchange → fetch('/toggle_heatmap')`, poll `s.unique_ids_count` in `pollStats()`, reset in `resetUpload()` (+8 lines, depends on 4.2, 4.3)

## Phase 5: Reset & Polish

- [ ] 5.1 **Reset on new upload** — Clear `_unique_ids`, set `_heatmap_acc = None`, signal `_tracker_active` reinit in `reset_state()` flow (+4 lines, depends on all above)

---

## Task Dependency Graph

```
1.1 (bytetrack.yaml) ──┐
                        ├──→ 2.1 ──→ 2.2 ──→ 2.3 ──→ 4.2 ──→ 4.4
1.2 (module globals) ───┤         │                       ↑
                        │         └──→ 2.3                │
                        │                                 4.3 ───↑
1.3 (state fields) ─────┼─────────────→ 4.1 ──→ 4.3 ─────┘
                        │
3.1 (lazy heatmap) ─────┘──→ 3.2 ──→ 3.3

5.1 (reset) depends on: all nodes above.
```

## Implementation Order

```
1.1 → 1.2 → 1.3 → 2.1 → 2.2 → 2.3 → 3.1 → 3.2 → 3.3 → 4.1 → 4.2 → 4.3 → 4.4 → 5.1
```

Strict sequential within phases; phase 1–2 form the critical path since tracking must work before heatmap or frontend can be verified.

## Batch Grouping (for sdd-apply)

| Batch | Tasks | Scope | Est. Lines | Status |
|-------|-------|-------|-----------|--------|
| A: Backend | 1.1 → 1.2 → 1.3 → 2.1 → 2.2 → 2.3 → 3.1 → 3.2 → 3.3 → 4.1 | `app.py` + `config/bytetrack.yaml` | ~45 | ✅ Complete |
| B: Frontend | 4.2 → 4.3 → 4.4 | `templates/index.html` | ~23 | ⬜ Pending |
| C: Polish | 5.1 | `app.py` | ~4 | ⬜ Pending |

**Batch A must complete first** (backend provides the data frontend displays). Batch B and C are independent of each other after A.

## Verification (Manual — No Test Suite)

| Task | How to Verify |
|------|-------------|
| 1.1 | File `config/bytetrack.yaml` exists with valid YAML keys |
| 1.2 | `app.py` starts without ImportError for `Optional` |
| 1.3 | `GET /stats` returns `"unique_ids_count": 0` and `"heatmap_enabled": true` |
| 2.1 | Upload video → bounding boxes show stable track IDs per person across frames |
| 2.2 | Labels show `ID:3 85%` format (not `Persona 85%`) |
| 2.3 | `/stats` `unique_ids_count` increments when new person enters, never decrements |
| 3.1 | First frame creates accumulator — verify via memory or debug log |
| 3.2 | Heatmap accumulator values change at person positions (visible via overlay) |
| 3.3 | Heatmap overlay visible on stream when enabled, hidden when disabled |
| 4.1 | `curl -X POST -d '{"enabled":false}' localhost:8000/toggle_heatmap` → `/stats` shows `heatmap_enabled: false` |
| 4.2 | Stat card visible between "Máximo concurrente" and "Detecciones totales" |
| 4.3 | Toggle checkbox visible in video panel header, toggles heatmap on/off |
| 4.4 | Checkbox sends POST, unique count updates in poll, both reset on new upload |
| 5.1 | Upload video → let it finish → upload another → unique count + heatmap start fresh |

## Risks

| Risk | Level | Mitigation |
|------|-------|-----------|
| `model.track()` API differs from `model()` in return shape | Medium | Test with a short video first; fallback: keep `model()` as try/except |
| Heatmap alpha=0.4 obscures detections | Low | Toggle off by default; adjustable constant in future |
| Track IDs reset mid-video (ByteTrack instability) | Medium | Increase `track_buffer` if needed; verify with occlusion-heavy footage |
