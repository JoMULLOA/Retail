# Proposal: tracking-heatmap

## Intent

Add multi-person tracking (ByteTrack) + heatmap visualization to RetailVision to understand person movement patterns and dwell zones in retail spaces. Tracking enables counting unique visitors; heatmap reveals high-traffic areas.

## Scope

### In Scope
- ByteTrack multi-person tracking integrated into video processing pipeline
- Heatmap accumulator: float32 overlay rendered via cv2.applyColorMap(JET)
- Heatmap toggle from frontend (checkbox)
- Unique visitor count stat card ("Personas únicas")
- Track ID labels on bounding boxes (e.g. "ID:3 85%")
- Thread-safe state updates for tracking + heatmap state

### Out of Scope
- Video download/export
- Multi-video queuing or simultaneous processing
- Heatmap download as image
- Persistent track history across uploads
- Heatmap decay/aging over time
- Track re-identification across occlusions (ByteTrack handles internally, no need for overrides)

## Capabilities

### New Capabilities
- `person-tracking`: multi-person tracking with persistent IDs across frames, unique visitor count
- `heatmap-visualization`: accumulative heatmap overlay with show/hide toggle from frontend

### Modified Capabilities
- None

## Approach

Replace `model(frame, ...)` with `model.track(frame, persist=True, tracker="bytetrack.yaml", ...)` for tracking. Accumulate person positions (circle at bbox center) into float32 numpy array. Render via cv2.applyColorMap(JET) + addWeighted overlay. Track IDs from `boxes.id.int().cpu().tolist()`. Frontend polls `/stats` for unique count; sends toggle query param on `/video_feed`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app.py` | Modified | +~80 lines: ByteTrack pipeline, heatmap accumulator, new state keys, toggle param |
| `templates/index.html` | Modified | +new stat card, heatmap checkbox, JS toggle logic |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Track ID instability at low FPS | Low | tune ByteTrack params (track_buffer=45, match_thresh=0.8) |
| Heatmap memory at 4K resolution | Low | resize frames before accumulation; cap at 1920px wide |
| Heatmap overlay hides detections | Low | use addWeighted alpha=0.4; toggle off by default |

## Rollback Plan

Revert `model.track` → `model(frame, ...)`, remove heatmap state + rendering, revert template changes. Single commit per deliverable.

## Dependencies

None. ByteTrack is bundled with Ultralytics YOLO v8.3.61 (already installed).

## Success Criteria

- [ ] Each detected person has a stable track ID across frames
- [ ] Heatmap overlay renders and toggles via frontend checkbox
- [ ] Unique visitor count displayed and updated in real-time
- [ ] No measurable FPS drop (>5%) from tracking overhead alone
