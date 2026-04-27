# Windows Demo Steps

## Goal

On Windows, run one UI that shows:

- local dual-camera feeds
- arm monitor
- gripper / tactile data
- 3D trajectory
- browser ASR transcript
- embedded virtual-environment monitor from `http://140.127.205.127:8765`

And replay the existing teach recordings:

- `chopsticks_pick_v4`
- `spoon_pick_v2.merged`
- `trapedzoid_v4.merged`

## 1. Network Topology

Windows must use two networks at the same time:

- `Ethernet` -> switch -> arm computer / gripper network
- `Wi-Fi` -> internet / campus network -> virtual environment server

## 2. Windows Network Setup

### Ethernet

Current Windows machine is already on:

- IP: `192.168.1.51`
- Subnet mask: `255.255.255.0`
- Gateway: `192.168.1.1`

This means the old `10.42.0.x` Linux-relay assumption is no longer the default path.
The repo is now configured to try direct switch endpoints first:

- arm: `192.168.1.232:502`, then `192.168.1.233:502`
- gripper: `192.168.1.232:5002`, then `192.168.1.233:5002`
- old relay paths remain only as fallbacks

If Ethernet IP changes on another machine, use:

```powershell
ipconfig
```

and make sure the robot-side devices are on the same subnet.

### Wi-Fi

Connect normally to the internet-facing network.

Do not disable Wi-Fi.

## 3. Basic Connectivity Checks

Open PowerShell on Windows and verify:

```powershell
ipconfig
Test-NetConnection 192.168.1.232 -Port 502
Test-NetConnection 192.168.1.233 -Port 502
Test-NetConnection 192.168.1.232 -Port 5002
Test-NetConnection 192.168.1.233 -Port 5002
Invoke-RestMethod http://140.127.205.127:8765/health
```

Expected:

- at least one direct arm endpoint responds on `:502`
- at least one direct gripper endpoint responds on `:5002`
- `140.127.205.127:8765/health` returns `{ ok: true, ... }`

If `140.127.205.127` fails but Ethernet works, the issue is Wi-Fi / routing, not the robot side.

If both direct robot endpoints fail but Wi-Fi works, the issue is Ethernet / switch / robot-side addressing.

## 4. Copy Project to Windows

Copy the whole repo directory to Windows, for example:

```text
C:\voice_pick
```

Keep these files and folders:

- `tools/`
- `src/`
- `config/`
- `data/teach_recordings/`
- `data/claw/`

## 5. Create Python Environment

If you already have a working Windows env, use it. Otherwise:

```powershell
conda create -n voice_pick python=3.10 -y
conda activate voice_pick
pip install -r requirements.txt
```

If `pyrealsense2` is missing or broken on Windows:

```powershell
conda install -n voice_pick -c conda-forge pyrealsense2 librealsense -y
```

## 6. Connect USB Devices

Plug into Windows:

- RealSense camera 1
- RealSense camera 2 if available
- microphone if needed

The arm and gripper are not USB here; they come through Ethernet.

## 7. Start the Demo Server

From the repo root on Windows:

```powershell
conda activate voice_pick
python tools/voice_pick_demo.py --host 0.0.0.0 --port 8090
```

Then open on the same Windows machine:

```text
http://127.0.0.1:8090
```

Use `127.0.0.1`, not LAN IP, for browser microphone permission.

## 8. First UI Checks

After the page loads, confirm all of these:

### Cameras

- `Cam1 RGB` is live
- `Cam1 Depth` is live
- `Cam2 RGB` is live if second camera is attached
- `Cam2 Depth` is live if second camera is attached

### Arm

- click `Connect Arm`
- `Arm Monitor` starts updating
- trajectory plot starts moving when arm pose updates

### Gripper

- `Gripper / Tactile` panel shows current positions
- no persistent gripper API error

### Virtual Environment

- `Virtual Environment` panel shows `Connected`
- iframe loads remote `8765` UI
- remote four-view monitor appears

### ASR

- use Chrome or Edge
- click mic button
- transcript appears in `Voice Input`

## 9. Replay the Existing Recordings

Use Teach Replay in this order:

### Chopsticks

- replay: `chopsticks_pick_v4`
- note: this one has no claw data by design

### Spoon

Prefer:

- `spoon_pick_v2.merged`

### Trapezoid

Current replayable version:

- `trapedzoid_v4.merged`

## 10. Validation Mode

For replay-based validation:

1. choose object in `Validation`
2. set `Mode = teach`
3. click `Start Validation`
4. after the motion really completes, click:
   - `Mark Success`
   - or `Mark Fail`

Teach-mode recording resolution now prefers:

- highest available `.merged`
- otherwise highest available raw `vN`

So:

- `chopsticks` will resolve to `chopsticks_pick_v4`
- `spoon` will resolve to the latest merged spoon recording

## 11. If Something Fails

### No mic permission

Use:

```text
http://127.0.0.1:8090
```

Do not use `http://<LAN-IP>:8090` for ASR testing.

### Virtual environment panel empty

Check:

```powershell
Invoke-RestMethod http://140.127.205.127:8765/health
```

If health is okay, click:

- `Open Console`
- or `Open WebRTC`

from the `Virtual Environment` panel.

### Arm not connecting

Check:

```powershell
Test-NetConnection 192.168.1.232 -Port 502
Test-NetConnection 192.168.1.233 -Port 502
```

If that fails, fix Ethernet / switch first.

### Gripper panel shows error

Check:

```powershell
Test-NetConnection 192.168.1.232 -Port 5002
Test-NetConnection 192.168.1.233 -Port 5002
```

If that fails, fix gripper API reachability on the direct switch network first.

### Cameras not visible

Check that Windows sees the USB cameras, then restart:

```powershell
python tools/voice_pick_demo.py --host 0.0.0.0 --port 8090
```

## 12. Demo-Minimum Pass Criteria

Before the actual demo, confirm this exact set:

- local page opens on Windows
- two local camera panels are visible
- arm monitor updates after `Connect Arm`
- gripper / tactile panel has live values
- trajectory plot updates
- browser ASR transcript appears
- virtual environment panel shows remote monitor
- `chopsticks_pick_v4` replays
- one spoon merged replay works
