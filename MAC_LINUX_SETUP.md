# Mac / Linux Setup

這份文件是給你把目前 `voice_pick` repo 搬到 macOS 或 Linux 上繼續處理用的。

## 1. Clone Repo

```bash
git clone https://github.com/bubbleee030/VLAtest.git
cd VLAtest
```

## 2. Create Python Environment

### macOS / Linux with `venv`

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux with Conda

```bash
conda create -n voice_pick python=3.10 -y
conda activate voice_pick
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Dependency Notes

`requirements.txt` 已經做了平台分流：

- Linux: 會安裝 `pyrealsense2`
- macOS: 會安裝 `pyrealsense2-mac`

如果安裝 RealSense 套件失敗，先不要卡太久，可以先把相機模組關掉驗證其他功能：

- `config/demo_config.yaml`
- `modules.cam1.enabled: false`
- `modules.cam2.enabled: false`

## 4. Start the Demo Backend

目前主入口仍然是：

```bash
python tools/voice_pick_demo.py
```

啟動後預設 dashboard：

- `http://127.0.0.1:8090`

## 5. Important Configs to Check First

主要要改的是 [config/demo_config.yaml](/d:/Codes/voice_pick/config/demo_config.yaml)。

### Arm IP

現在 repo 內預設是 Windows 現場 switch 直連：

```yaml
arm:
  connections:
    - host: "192.168.1.232"
      port: 502
    - host: "192.168.1.233"
      port: 502
```

如果你在 Mac / Linux 上的網段不同，要改成你當下能直通的 arm IP。

### Gripper / Tactile API

目前預設：

```yaml
gripper.agx_ip: "192.168.1.100"
sensor_api.base_url: "http://192.168.1.100:5001"
```

如果 AGX 的 IP 改了，這兩個都要一起改。

### Claw Camera Source

現在 repo 內：

```yaml
cameras:
  claw:
    source: 4
```

這是 Windows 上當時探測到的 UVC index。換到 Mac / Linux 幾乎一定要重查。

先跑：

```bash
python tools/probe_cameras.py --max-index 10
```

再把 `cameras.claw.source` 改成正確 index。

### RealSense Camera Serials

目前設定：

```yaml
cameras:
  cam1:
    serial: "908212071386"
  cam2:
    serial: "943222070989"
```

如果你換了機器、線材或設備，請確認這兩顆 serial 還在。

### Default Teach Replay Mode

目前預設：

```yaml
teach:
  default_replay_mode: "phase_axis_split"
```

這是現在比較穩定的模式，會先走 `XY/姿態`，再單獨走 `Z`。

### Digital Twin

目前虛擬環境 API：

```yaml
virtual_env:
  base_url: "http://140.127.205.127:8765"
```

如果在 Mac / Linux 上連不到，先把：

```yaml
modules:
  virtual_env:
    enabled: false
    show_in_ui: false
  virtual_env_data:
    enabled: false
    show_in_ui: false
```

## 6. Legacy Modbus Config Note

[config/modbus_config.yaml](/d:/Codes/voice_pick/config/modbus_config.yaml) 目前還保留 legacy relay/tunnel 預設：

```yaml
connection:
  host: "127.0.0.1"
  port: 1502
```

但現在 demo 執行時，主要是先看 `demo_config.yaml` 裡的 `arm.connections`。

也就是說：

- 日常 demo 先改 `demo_config.yaml`
- `modbus_config.yaml` 比較偏 controller / register / motion tuning

## 7. Models Are Not In Git

以下資料夾沒有推上 GitHub：

- `data/models/`
- `data/panel_recordings/`
- `data/recordings/`
- `data/validation_sessions/`

所以換到新機器後，如果要跑：

- YOLO
- ASR
- 其他本地模型

你需要自己把模型檔補回去，或重新下載到 `data/models/...`。

## 8. Recommended Bring-Up Order

建議不要一開始就全部開。

1. 先確認 Python 環境能啟動後端。
2. 關閉 arm / gripper / tactile / virtual env，只測 UI。
3. 測 RealSense 兩顆相機。
4. 測 claw cam index。
5. 測 AGX API：gripper / tactile。
6. 最後再接 arm 做 replay。

## 9. Quick Safe Disable Set

如果你只想先在 Mac / Linux 上把 UI 跑起來，可先這樣改：

```yaml
modules:
  cam1: { enabled: false, show_in_ui: false }
  cam2: { enabled: false, show_in_ui: false }
  claw_cam: { enabled: false, show_in_ui: false }
  sensor_chart: { enabled: false, show_in_ui: false }
  gripper: { enabled: false, show_in_ui: false }
  virtual_env: { enabled: false, show_in_ui: false }
  virtual_env_data: { enabled: false, show_in_ui: false }
```

這樣可以先確認：

- Flask / Socket.IO
- dashboard layout
- voice / teach / config reload

## 10. Config Reload vs Restart

目前：

- 大部分 YAML 變更可以用 dashboard 的 `Reload Config`
- 但這幾類通常還是建議重開後端：
  - 相機 source / serial
  - 某些低階 Modbus 參數
  - 裝置重新插拔後的初始化

## 11. Useful Commands

### Probe cameras

```bash
python tools/probe_cameras.py --max-index 10
```

### Syntax check

```bash
python -m py_compile tools/voice_pick_demo.py src/controller.py
```

### Start backend

```bash
python tools/voice_pick_demo.py
```

## 12. If Something Feels Wrong

優先檢查：

- IP 網段是不是對的
- claw camera index 是不是變了
- RealSense serial 是不是還對
- AGX API 是不是還在 `192.168.1.100`
- 模型檔是不是其實沒在新機器上

如果只是要先在 Mac / Linux 上整理 phase YAML、teach recordings、NLU 或 UI，建議先把硬體模組都關掉再做。
