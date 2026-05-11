# Spec: tracking-heatmap

Combined full spec for two new capabilities: `person-tracking` and `heatmap-visualization`. No existing specs for either domain.

---

## 1. Functional Requirements

### FR-001: ByteTrack Multi-Person Tracking

The system MUST replace single-frame YOLO detection (`model(frame, ...)`) with persistent tracking (`model.track(frame, persist=True, tracker="bytetrack.yaml", ...)`) so that each detected person receives a stable track ID that persists across frames.

**Tracker configuration**: ByteTrack parameters SHALL use `track_buffer=45` and `match_thresh=0.8`.

#### Scenario: Stable ID across consecutive frames
- GIVEN a video with a person walking through the frame
- WHEN the system processes frame N and frame N+1
- THEN the same person bears the same track ID in both frames

#### Scenario: Person re-enters within track_buffer
- GIVEN a person exits the frame and re-enters within 45 frames
- WHEN the system detects them again
- THEN ByteTrack SHOULD assign the same track ID

#### Scenario: First frame — no prior tracks
- GIVEN the system starts processing a video
- WHEN frame 0 is processed with `model.track`
- THEN all detections receive new track IDs starting from 1

### FR-002: Track ID Display on Bounding Boxes

Every bounding box label MUST include the track ID in format `ID:{n} {conf}%` (e.g. `ID:3 85%`). The label replaces the current `Persona {conf:.0%}` format.

#### Scenario: Multiple persons with IDs
- GIVEN a frame with 3 detected persons
- WHEN bounding boxes render
- THEN labels read `ID:1 92%`, `ID:2 87%`, `ID:3 95%`

### FR-003: Heatmap Accumulation and Rendering

The system MUST accumulate a float32 heatmap over the full video duration. On each frame, for every detected person, the system SHALL add a Gaussian or circular brush (radius ~40px) centered at the bbox bottom-center to the accumulator. At render time, the accumulator SHALL be normalized to [0,1], color-mapped via `cv2.COLORMAP_JET`, and composited over the frame with `cv2.addWeighted` (`alpha=0.4` for the heatmap layer).

#### Scenario: Accumulation over time
- GIVEN a 300-frame video where a person walks along a path
- WHEN all frames are processed
- THEN the heatmap shows higher intensity along that path

#### Scenario: No persons in frame
- GIVEN a frame with zero detections
- WHEN the system renders
- THEN the heatmap accumulator remains unchanged and the overlay stays static from the previous frame

### FR-004: Heatmap Toggle (Show/Hide)

The system MUST support toggling heatmap visibility at runtime via a frontend control. The toggle MUST take effect on the next rendered frame (no stream restart required). Default state SHALL be `on` (heatmap visible).

#### Scenario: Toggle mid-video
- GIVEN the video is processing with heatmap visible
- WHEN the user unchecks "Mostrar mapa de calor"
- THEN the overlay disappears within 1 frame
- AND the accumulator continues building (invisible)
- WHEN the user re-checks
- THEN the overlay reappears showing all accumulated activity

### FR-005: "Personas Únicas" Stat

The system MUST maintain a count of unique track IDs seen across the entire video. This count SHALL be exposed via `/stats` and displayed as a stat card in the frontend.

#### Scenario: Unique count increments correctly
- GIVEN 5 persons have been tracked so far
- WHEN a 6th person enters the frame
- THEN the "Personas únicas" value updates from 5 to 6
- AND it never decrements

### FR-006: State Fields for Tracking and Heatmap

The system MUST add these fields to `_state`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `unique_ids_count` | `int` | `0` | Exposed count of unique track IDs |
| `heatmap_enabled` | `bool` | `True` | Whether heatmap overlay renders on current frame |

The internal unique-ID set SHALL be held OUTSIDE `_state` (not JSON-serializable), guarded by `_state_lock`, and only its length published to state.

---

## 2. Non-functional Requirements

### NFR-001: Performance — Tracking Overhead

Tracking enabled + heatmap OFF MUST cause less than 5% FPS drop relative to the current baseline (`model(frame, ...)` with annotations).

### NFR-002: Performance — Heatmap Overhead

Tracking + heatmap ON MUST cause less than 15% FPS drop relative to baseline.

### NFR-003: Memory — Heatmap Accumulator

The float32 heatmap array MUST NOT exceed 10 MB. At `MAX_FRAME_SIZE=1920` (max width, proportional height) a 1920×1080 float32 accumulator occupies ~8.3 MB — within budget. If input resolution exceeds this, frames SHALL be resized before accumulation.

---

## 3. Edge Case Scenarios

### EC-001: Very long video — heatmap saturation
- GIVEN a video longer than 10 minutes with constant person activity
- WHEN the accumulator values saturate near 1.0 across most pixels
- THEN the heatmap renders as mostly red (JET max) 
- AND this is ACCEPTABLE behavior (no decay in scope v1)

### EC-002: No persons in any frame
- GIVEN a video with zero persons detected
- WHEN the pipeline ends
- THEN `unique_ids_count` stays 0
- AND the heatmap is all-black (zero accumulator)

### EC-003: Toggle heatmap with zero accumulator
- GIVEN heatmap is OFF since upload
- WHEN user enables it mid-video with no persons yet detected
- THEN the overlay renders as fully transparent (all-zero accumulator → normalized to 0 → black JET → transparent on addWeighted)

### EC-004: Uploaded video ends while heatmap on
- GIVEN heatmap is ON when video finishes
- WHEN `set_state(processing=False, progress=1.0)` fires
- THEN the last frame displayed includes the final accumulated heatmap overlay

---

## 4. UI Specification

### 4.1 New Stat Card

Positioned between "Máximo concurrente" and "Detecciones totales" in the stats panel.

```html
<div class="stat-card">
    <div class="label">👤 Personas únicas</div>
    <div class="value green" id="statUnique">0</div>
    <div class="sub">visitantes distintos en el video</div>
</div>
```

Behavior: increments only when a new track ID appears; never decrements. Value resets to `0` on new upload via `resetUpload()`.

### 4.2 Toggle Element

A checkbox/switch placed inside the video panel header, before the stream label:

```html
<label class="toggle-label">
    <input type="checkbox" id="heatmapToggle" checked />
    <span class="toggle-track"></span>
    <span>Mapa de calor</span>
</label>
```

**CSS**: dark-theme toggle switch (slider style) using `--accent-green` for active state.

**Default**: checked (`heatmap_enabled = True`).

**Visual feedback**: immediate check/uncheck on click + polling confirms via `/stats` response.

### 4.3 Frontend Logic

- On toggle change → `fetch('/toggle_heatmap', { method: 'POST' })`
- JS polls `/stats` → reads `s.unique_ids_count` → updates `DOM.statUnique.textContent`
- Existing `resetUpload()` resets the unique counter to 0

---

## 5. State Specification

### New Fields in `_state`

```python
_state = {
    # ... existing fields unchanged ...
    "unique_ids_count": 0,      # int — snapshot of len(unique_ids_set)
    "heatmap_enabled": True,    # bool — frontend toggle
}
```

### Module-level (outside `_state`)

```python
_unique_ids: set[int] = set()   # Raw set of seen track IDs
_heatmap_acc: Optional[np.ndarray] = None  # float32 accumulator, shape (H, W)
```

Both guarded by `_state_lock` for write access. `_heatmap_acc` is lazily initialized on first frame with the frame's spatial dimensions. Reads during frame rendering happen in the same thread (`generate_frames`) so no additional lock needed.

### Thread Safety

- `generate_frames` (single thread): reads `_state["heatmap_enabled"]` and `_heatmap_acc`, writes to `_unique_ids` and `_heatmap_acc` — all behind `_state_lock` for the shared state portion
- `/toggle_heatmap` (fastAPI thread): writes `_state["heatmap_enabled"]` via `set_state()`
- `/stats` (fastAPI thread): reads `_state["unique_ids_count"]` via `get_state()` — already thread-safe
- `_unique_ids` set: mutations inside `generate_frames` only (single producer). No concurrent consumer because count is published to `_state`.

---

## 6. Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| AC-1 | Upload video → tracks persist across frames | Observe same person keeps same ID from entry to exit |
| AC-2 | Toggle heatmap → overlay appears/disappears within 1 frame | Check/uncheck checkbox mid-stream, observe immediate visual change |
| AC-3 | "Personas únicas" increments only for new IDs | Upload video with staged entries — count matches distinct entrants, not total detections |
| AC-4 | Heatmap shows accumulated activity by end of video | After full video, heatmap overlay shows higher intensity in high-traffic areas |
| AC-5 | Fresh upload resets both unique count and heatmap | Upload second video without refresh — both values start from zero |

---

## Key Technical Decisions (Pre-Design)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Toggle mechanism | POST `/toggle_heatmap` endpoint updates `_state` | Avoids stream restart (changing query param on `/video_feed` src would reconnect) |
| Heatmap storage | float32 accumulator, lazily allocated per-frame dimensions | Matches input resolution; resize first to stay ≤10 MB |
| ID persistence | ByteTrack internally re-identifies within `track_buffer` frames | Bundled in Ultralytics YOLO 8.3.61 — no external dependency |
| Unique ID counting | `set[int]` outside `_state`, publish `len()` to `_state` | `set` is not JSON-serializable; `/stats` returns int |
