# Session Handoff

## Goal

Current workflow target:

- use `tools/voice_pick_demo.py` as the main validation / teach UI
- no realtime camera requirement
- record arm teach trajectories
- merge claw CSV recorded from another machine
- replay arm + claw together for validation

## What Was Implemented

### Validation / Teach UI

Files updated:

- `tools/voice_pick_demo.py`
- `tools/static/index.html`
- `tools/static/app.js`
- `tools/static/style.css`

Features already in place:

- arm monitor
- 3D trajectory plot
- speech / NLU display
- validation session recording
- teach mode
- gripper / tactile panel
- no-camera mode still works

### Validation Session Recording

Each validation attempt is saved under:

```text
data/validation_sessions/<timestamp>_<object_key>/
```

Includes at least:

- `session.json`
- `arm_trajectory.csv`
- `arm_logs.jsonl`
- `speech_events.jsonl`

### Teach Recording Stores Gripper State

Files updated:

- `tools/voice_pick_demo.py`
- `tools/teach_recorder.py`

Teach waypoints now store:

- `gripper_pos`
- `tactile_data`
- `gripper_server_time_unix`

This avoids relying only on symbolic `open/close` commands.

### Gripper Absolute Position API

File updated:

- `gripper_record_CSV_API.py`

Added endpoint:

```text
POST /set_position
```

Payload:

```json
{"positions":[p1,p2,p3]}
```

### Replay Behavior

Replay now prefers, in order:

1. `wp["gripper_pos"]`
2. `wp["matched_external"]["row"].pos1/pos2/pos3`
3. fallback symbolic `gripper` command

Files updated:

- `tools/voice_pick_demo.py`
- `tools/teach_recorder.py`

### Full External Timeline Replay

If merged teach JSON contains:

```json
"external_timeline": [...]
```

Replay streams `set_position` over time using that timeline.

## Merge Tool

### `tools/genlock_merge.py`

Extended to support:

- `--episode-dir`
- `--teach-json`

Teach merge outputs:

- `*.genlock_merged.csv`
- `*.genlock_report.json`
- `*.merged.json`

Merged teach JSON may contain:

- `matched_external`
- `matched_gripper`
- `timestamp_unix`
- `external_timeline`

## Merge Policy

User asked to use:

- absolute time merge
- `timestamp_unix`
- tolerate about `1s`

So merges were rerun with:

- `max_delta = 1.0`
- no relative-time anchoring unless the CSV itself only had relative timestamps

## Current Merge Status

Detailed status is in:

- `data/teach_recordings/MERGE_STATUS.md`

### Valid Replay Targets

Currently usable:

- `spoon_pick_v2.merged`
- `trapedzoid_v4.merged`

### Trapezoid Latest Good Version

Best current trapezoid replay target:

- `data/teach_recordings/trapedzoid_v4.merged.json`

Created from:

- teach: `data/teach_recordings/trapedzoid_v4.json`
- claw: `data/claw/tactile_data_1776914592.csv`

Result:

- `matched_external_rows = 7`
- `external_timeline_samples = 1779`

Also generated:

- `data/teach_recordings/trapedzoid_v4.genlock_merged.csv`
- `data/teach_recordings/trapedzoid_v4.genlock_report.json`

### Older / Non-Preferred Trapezoid

`trapedzoid_v3.merged` also exists and is usable, but:

- it used a CSV with relative `timestamp`
- absolute time had to be inferred from the filename

Prefer:

- `trapedzoid_v4.merged`

### Invalid / Mismatched Merges

These were rerun and shown to be invalid under absolute time:

- `spoon_pick_v1.merged`
- `trapezoid_pick_v1.merged`

They now contain no usable external timeline.

## Default Replay Selection

Updated files:

- `config/objects.yaml`
- `tools/voice_pick_demo.py`
- `tools/static/app.js`

For object `trapezoid`, config now includes:

```yaml
default_teach_recording: "trapedzoid_v4.merged"
```

Frontend and backend now prefer that explicitly, instead of guessing older recordings.

## Network / Relay Notes

### Current Windows Direct-Switch Setup

This handoff originally described an older Mac + Linux-relay topology.
That is no longer the main assumption.

Current Windows host observed on `2026-04-23`:

- `Ethernet`: `192.168.1.51/24`
- `Wi-Fi`: `172.20.10.5`

The repo config now prefers:

- arm: `192.168.1.232:502`, then `192.168.1.233:502`
- gripper: `192.168.1.100:5002` on AGX, then older direct-switch guesses as fallback

Legacy relay paths are kept only as fallback:

- arm relay fallback: `10.42.0.1:1502`
- gripper relay fallback: `10.42.0.1:5002`

Important:

- do not assume arm and gripper share the same endpoint
- AGX startup log showed gripper API on `0.0.0.0:5002`, reachable as `192.168.1.100:5002`
- `tools/voice_pick_demo.py` and `tools/teach_recorder.py` now try multiple gripper endpoints automatically
- exact live device IP still needs to be confirmed on the switch if neither `.232` nor `.233` responds

## Important Bug Found

### Symptom

Replay log showed:

```text
Replay failed: file descriptor cannot be a negative integer (-1)
```

### Diagnosis

This was most likely caused by concurrent access to the same Modbus client:

- background pose polling thread
- replay thread calling `move_to()` and `read_current_pose()`

### Fix Applied

File updated:

- `src/controller.py`

Added:

- `threading.RLock()`

Wrapped Modbus I/O in the lock for:

- `reset_alarms`
- `servo_on`
- `servo_off`
- `read_current_pose`
- `write_target_pose`
- `move_to`
- `disconnect`

This fix is now present in the repo, but still needs a fresh replay re-test on Windows.

## Separate Gripper Failure

Old replay logs also showed:

```text
Gripper set_position failed: HTTPConnectionPool(host='10.42.0.1', port=5002) ...
ConnectTimeoutError ...
```

At that time it meant:

- arm replay was running
- claw replay was not, because gripper API timed out

So there were two distinct issues:

1. arm Modbus race condition
2. gripper API timeout during replay

## Latest Replay Log Conclusion

The merged recording itself was not the main problem.

Observed behavior:

- arm replay started and moved through multiple waypoints
- live arm pose values changed normally
- claw `set_position` timed out repeatedly
- replay then failed with the Modbus fd error

So:

- merged file was valid
- arm replay issue was likely Modbus client concurrency
- claw replay issue was API reachability / timeout

## Most Relevant Files

- `config/objects.yaml`
- `config/demo_config.yaml`
- `src/controller.py`
- `tools/voice_pick_demo.py`
- `tools/teach_recorder.py`
- `tools/genlock_merge.py`
- `gripper_record_CSV_API.py`
- `tools/static/index.html`
- `tools/static/app.js`
- `tools/static/style.css`
- `data/teach_recordings/MERGE_STATUS.md`

## Recommended Next Step

Open the next session with:

> Continue debugging replay for `trapedzoid_v4.merged`. `src/controller.py` now has an `RLock` added to serialize Modbus I/O, but replay has not yet been re-tested after that change on Windows. Need to verify whether `file descriptor cannot be a negative integer (-1)` is fixed, and separately which direct gripper endpoint is actually reachable during replay on the switch network.
