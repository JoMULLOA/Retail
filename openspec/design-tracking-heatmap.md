# Design: ByteTrack Tracking + Heatmap Visualization

## Technical Approach

Replace the single-frame `model(frame, ...)` inference with `model.track(frame, persist=True, tracker="bytetrack.yaml")` inside the existing MJPEG generator loop. A float32 heatmap accumulator is lazily initialized on the first frame, populated with circular brushes at each person's bbox bottom-center every frame, and composited over the annotated frame via `cv2.addWeighted` with `COLORMAP_JET`. A `set[int]` outside `_state` tracks unique IDs; its length is published to `_state["unique_ids_count"]` for the `/stats` endpoint. Heatmap toggle is a `POST /toggle_heatmap` route that flips `_state["heatmap_enabled"]`.

---

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|----------|---------|--------|-----------|
| Toggle mechanism | A: POST endpoint, B: query param on `/video_feed`, C: WebSocket | **A: POST `/toggle_heatmap`** | Changing query param on `/video_feed` would force browser reconnect (stream restart). WebSocket is overkill for a single binary state. POST is idempotent, fits existing REST pattern, and takes effect on next frame render. |
| Heatmap storage | float32, uint8, list of coords | **float32 ndarray** | Pixel-level accumulator enables smooth JET colormap. uint8 loses precision for long videos. Coord list would require re-rendering every frame. |
| Heatmap decay | None, multiply 0.999, max cap | **No decay (cap at max)** | Spec EC-001 accepts saturation as v1 behavior. Decay adds complexity with minimal benefit for retail traffic analysis. |
| Unique ID storage | `set[int]` in `_state`, `list[int]` in `_state`, separate module var | **`set[int]` outside `_state`** | `set` is not JSON-serializable. `list[int]` would require dedup on every append. Module-level `set` guarded by `_state_lock` is cleanest — only `len()` is published to state. |
| ByteTrack config | Default Ultralytics, custom yaml | **Custom `bytetrack.yaml`** | Defaults favor general MOT; retail needs higher `track_buffer` (45), lower `match_thresh` (0.8) to handle occlusion in crowded aisles. |
| Tracker reinit on new upload | Manual reset, auto-detect | **Manual reset in `reset_state()`** | New upload calls `reset_state()` which clears `_state`. Adding a `reset_tracker()` call there ensures clean tracker state without model reload. |

---

## Data Flow

```
Upload ──→ reset_state() ──→ /video_feed ──→ generate_frames()
                                                  │
                    ┌─────────────────────────────┘
                    ▼
        model.track(persist=True) ──→ boxes + track IDs
                    │
         ┌──────────┼──────────────┐
         ▼          ▼              ▼
   unique_ids     heatmap_acc    annotate frame
   set.add(id)    draw circle     label "ID:{n}"
         │        at bbox         with bbox + conf
         ▼        bottom-center
   _state         normalize [0,1]
   [unique_        → COLORMAP_JET
    ids_count]    → addWeighted
                    alpha=0.4
                      │
                      ▼
         if _state["heatmap_enabled"]:
              composite overlay
                      │
                      ▼
                  encode JPEG
                  → yield MJPEG
```

**Toggle path** (separate thread):

```
Frontend checkbox
  → fetch POST /toggle_heatmap {enabled: bool}
    → set_state(heatmap_enabled=bool)
      → next frame in generate_frames reads new value
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app.py` | Modify | Add `_unique_ids`, `_heatmap_acc`, `_heatmap_lock`, `_tracker_active`. Change inference to `model.track()`. Add `HeatmapAccumulator` logic inline. Add `reset_tracker()` function. Add `POST /toggle_heatmap` route. Modify label format to `ID:{n} {conf}%`. |
| `templates/index.html` | Modify | Add "Personas únicas" stat card after "Máximo concurrente". Add heatmap toggle checkbox in panel header. Add JS: `fetch('/toggle_heatmap')` on toggle change. Poll `s.unique_ids_count` from `/stats`. Reset on `resetUpload()`. |

---

## Interfaces / Contracts

### New State Fields

```python
_state = {
    # ... existing fields unchanged ...
    "unique_ids_count": 0,   # int — published len of _unique_ids
    "heatmap_enabled": True, # bool — toggle state
}
```

### Module-level Globals

```python
_unique_ids: set[int] = set()
_heatmap_acc: Optional[np.ndarray] = None  # float32 (H, W)
_tracker_active: bool = False              # False after reset
# All guarded by existing _state_lock
```

### New Route

```python
@app.post("/toggle_heatmap")
async def toggle_heatmap(body: dict):
    enabled = body.get("enabled", True)
    set_state(heatmap_enabled=enabled)
    return {"heatmap_enabled": enabled}
```

### ByteTrack Config (`bytetrack.yaml`)

Embedded as a Python string written to a tempfile, or as a module-level dict converted to YAML. Content:

```yaml
# bytetrack.yaml — tuned for retail person tracking
track_buffer: 45        # frames to keep lost tracks (occlusion tolerance)
match_thresh: 0.8       # IoU threshold for data association
fuse_score: True        # fuse detection confidence into tracking score
min_box_area: 100       # min pixels to consider a valid track
```

Rationale:
- `track_buffer: 45` — at ~15 FPS, ~3 seconds of occlusion tolerance when a person passes behind a shelf
- `match_thresh: 0.8` — slightly lower than default (0.9) to handle partial occlusion at aisle edges
- `fuse_score: True` — standard, improves ID stability
- `min_box_area: 100` — filters tiny false positives from distant detections

### Heatmap Brush

```python
# Per person per frame
cx, cy = int((x1 + x2) / 2), int(y2)  # bbox bottom-center
cv2.circle(_heatmap_acc, (cx, cy), radius=40, color=1.0, thickness=-1)

# Before compositing
norm = cv2.normalize(_heatmap_acc, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
heatmap_color = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
overlay = cv2.addWeighted(frame, 1.0, heatmap_color, 0.4, 0)
```

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Heatmap init on first frame | Mock a 100x100 frame, verify `_heatmap_acc.shape == (100, 100)` |
| Unit | Unique ID set growth | Feed 5 IDs, verify count = 5; feed same ID again, count stays 5 |
| Unit | Toggle endpoint | `POST /toggle_heatmap {"enabled": False}` → GET `/stats` → `heatmap_enabled == False` |
| Integration | End-to-end tracking with synthetic video | Upload a clip with 1 walking person, verify ID stays constant across frames via `/stats` |
| Integration | Heatmap toggle mid-stream | Upload 2s clip, toggle off at 1s mark via POST, verify JPEG frame differs |

---

## Migration / Rollout

No migration required. Implementation order:

1. **Phase A — Tracking only**: Replace `model(frame)` with `model.track()`, update label format to `ID:{n} {conf}%`. Verify IDs persist across frames. No heatmap yet.
2. **Phase B — Heatmap accumulator**: Add `_heatmap_acc`, brush logic, `COLORMAP_JET` compositing. Verify overlay renders.
3. **Phase C — Frontend**: Add toggle checkbox, stats card, unique ID polling. Verify end-to-end.
4. **Phase D — Polish**: Edge cases (no persons, reset on new upload, saturation). Verify AC-1 through AC-5.

Each phase is a deliverable commit. Rollback = revert the commit for that phase.

---

## Open Questions

- **Q1**: Should `bytetrack.yaml` be a physical file in the repo or embedded as a Python string + `tempfile.NamedTemporaryFile`? Embedded avoids file clutter but adds complexity. **Preference**: physical file at `config/bytetrack.yaml` — cleaner for parameter tuning without code changes.
- **Q2**: Frame resize happens before tracking — should heatmap accumulator use pre-resize or post-resize dimensions? **Answer**: post-resize (what the user sees). The accumulator matches the annotated frame size.
- **Q3**: What radius for the heatmap brush? 40px feels right for 1920-wide frames but may need scaling for smaller resolutions. **Decision**: fixed 40px for v1; proportional scaling if feedback shows issues.
