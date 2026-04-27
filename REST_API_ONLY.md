# T9 REST API Only（0422 / External Integration）

這份文件只保留給外部系統、VLA、Agent、後端服務使用的 REST API。

刻意不包含：
- `/ui`
- `/webrtc`
- `/display/*`
- `/stream/*`
- VNC / WebRTC / 人工操作說明

如果需要展示層、監看頁或部署細節，請看 [REST_API_GUIDE.md](/home/leon/isaac_ros2_nav2/python_file/0422/REST_API_GUIDE.md)。

## Base URL

```text
http://<HOST>:8765
```

## Supported Targets

目前支援：
- `chopsticks`
- `forcept`
- `shears`
- `knife1`
- `bigspoon`
- `board`
- `butterknife`
- `hook1`
- `spoon`
- `unnamed1_red`

模式限制：
- `suction`: `chopsticks`, `forcept`, `shears`, `knife1`, `bigspoon`, `board`, `butterknife`, `hook1`, `spoon`
- `grasp`: `unnamed1_red`

## General Behavior

- 大多數成功回應都會包含 `ok: true`
- 失敗時通常會包含 `ok: false` 與 `message` 或 `error`
- 任務執行中再次送新任務，若未指定搶占，通常會回 `409`
- `0422` 是單一 Isaac instance 架構，不會因 `task`、`object_pose`、`monitor_target` 之類操作去重開一個新的 Isaac

## Response Conventions

常見欄位：
- `ok`: 是否成功
- `message`: 人類可讀訊息
- `result`: 該 API 的主結果
- `status`: 當下 runtime snapshot

## 1. Health / Runtime Status

### GET `/health`

確認 API 是否存活。

```bash
curl -s http://127.0.0.1:8765/health
```

### GET `/status`

讀取目前 runtime 狀態。

常用欄位：
- `current_kind`: `monitor` / `task` / `idle`
- `current_running`: 目前是否有流程在跑
- `current_task`: 目前任務內容
- `last_result`: 上一個 task 的結果
- `motion_profile`: 目前手臂速度設定
- `ee_move_limits`: `0422` 允許的末端安全工作區
- `delta_pose_calibration`: 目前 `Delta 六軸 -> 0422` 的粗轉換參數
- `object_physics_mode`: 物體預設 physics 模式，`dynamic` 代表平常保持物理行為，`kinematic` 代表 monitor 會鎖住物體
- `object_pose_overrides`: 目前場景中被覆寫的位置
- `web_display_meta`: 目前 monitor/task 顯示狀態摘要

```bash
curl -s http://127.0.0.1:8765/status
```

### GET `/last_result`

讀取上一個任務結果。

```bash
curl -s http://127.0.0.1:8765/last_result
```

## 2. Motion Profile

### GET `/motion_profile`

讀取目前速度設定。

```bash
curl -s http://127.0.0.1:8765/motion_profile
```

### POST `/motion_profile`

直接設定五個速度參數。

可用欄位：
- `coarse_move_max_step_xy_m`
- `coarse_move_max_step_z_m`
- `task_max_step_xy_m`
- `task_max_step_z_m`
- `task_max_step_rise_m`

Request example:

```json
{
  "coarse_move_max_step_xy_m": 0.05,
  "coarse_move_max_step_z_m": 0.03,
  "task_max_step_xy_m": 0.03,
  "task_max_step_z_m": 0.018,
  "task_max_step_rise_m": 0.03
}
```

```bash
curl -s -X POST http://127.0.0.1:8765/motion_profile \
  -H "Content-Type: application/json" \
  -d '{
    "coarse_move_max_step_xy_m": 0.05,
    "coarse_move_max_step_z_m": 0.03,
    "task_max_step_xy_m": 0.03,
    "task_max_step_z_m": 0.018,
    "task_max_step_rise_m": 0.03
  }'
```

注意：
- 若 task 正在執行，這個 API 會拒絕更新
- 後端有最小值保護，不會讓速度降到 0

### GET `/motion_profile_percent`

讀取 `0~100%` 百分比速度模式與目前 profile。

```bash
curl -s http://127.0.0.1:8765/motion_profile_percent
```

### POST `/motion_profile_percent`

直接用百分比設定速度。

Request example:

```json
{
  "speed_percent": 60
}
```

也接受：
- `percent`

```bash
curl -s -X POST http://127.0.0.1:8765/motion_profile_percent \
  -H "Content-Type: application/json" \
  -d '{"speed_percent": 60}'
```

## 3. End-Effector Pose / Move

### GET `/delta_pose_calibration`

讀取目前 `Delta 六軸 -> 0422` 的粗轉換參數。

```bash
curl -s http://127.0.0.1:8765/delta_pose_calibration
```

### GET `/ee_pose`

讀取當前手臂末端位置。

Query parameters:
- `blocking=true|false`
- `timeout_s=<seconds>`

預設：
- `blocking=true`
- `timeout_s=8`

```bash
curl -s "http://127.0.0.1:8765/ee_pose?blocking=true&timeout_s=8"
```

回傳中常見欄位：
- `result.ee_xyz_m`
- `result.ee_quat_wxyz`
- `result.ee_yaw_deg`
- `result.tool_xyz_m`
- `result.tool_quat_wxyz`
- `result.tool_yaw_deg`
- `result.arm_joint_names`
- `result.arm_joint_positions_rad`
- `result.arm_joint_positions_deg`

### POST `/ee_move`

直接控制手臂末端目標位置，剩下交給運動學 / 控制器。

Request body:

```json
{
  "position": [-0.90, -1.60, 1.29],
  "yaw_deg": 0.0,
  "blocking": true,
  "timeout_s": 35.0
}
```

也接受：
- `xyz` 取代 `position`

欄位說明：
- `position` / `xyz`: `[x, y, z]`
- `yaw_deg`: 末端 yaw，預設 `0.0`
- `blocking`: 是否等待完成，預設 `true`
- `timeout_s`: 等待秒數，預設 `35`

```bash
curl -s -X POST http://127.0.0.1:8765/ee_move \
  -H "Content-Type: application/json" \
  -d '{
    "position": [-0.90, -1.60, 1.29],
    "yaw_deg": 0.0,
    "blocking": true,
    "timeout_s": 35.0
  }'
```

注意：
- 座標必須是 `0422` 場景中的世界座標，單位是公尺
- 不要直接送台達 joint counts、mm 或未轉換的實機數值
- 若超出 `status.ee_move_limits`，後端會直接拒絕並回 `400`

### POST `/delta_pose_convert`

把台達 6 軸座標轉成 `0422` 虛擬世界座標，但不真的移動手臂。

Request example:

```json
{
  "delta_pose": [490.127, 0.000, 425.027, 179.999, 0.000, 0.000],
  "units": "mm_deg"
}
```

也接受：
- `delta_pose_raw`
- 或直接送 `x,y,z,rx,ry,rz`

回傳重點：
- `result.sim_ee_position_m`
- `result.sim_yaw_deg`
- `result.semantic_conveyor_coords_m`
- `result.calibration_flags`

```bash
curl -s -X POST http://127.0.0.1:8765/delta_pose_convert \
  -H "Content-Type: application/json" \
  -d '{
    "delta_pose": [490.127, 0.000, 425.027, 179.999, 0.000, 0.000],
    "units": "mm_deg"
  }'
```

### POST `/ee_move_delta_raw`

直接接收台達 6 軸座標，先轉成 `0422` 虛擬 EE 目標，再送進 `/ee_move` 控制鏈。

目前姿態行為：
- 位置：用粗標定的 `Delta -> 0422` 轉換
- 姿態：固定 `tool-down`
- yaw：用 `ready_yaw + (rz - ready_rz)` 近似
- `rx` / `ry` 不會驅動到 IK

Request example:

```json
{
  "delta_pose_raw": [490127, 0, 425027, 179999, 0, 0],
  "units": "raw_counts",
  "blocking": true,
  "timeout_s": 35.0,
  "include_ee_pose": true
}
```

如果 `blocking=true` 且 `include_ee_pose=true`，回傳中會多帶：
- `ee_pose_after_move`

```bash
curl -s -X POST http://127.0.0.1:8765/ee_move_delta_raw \
  -H "Content-Type: application/json" \
  -d '{
    "delta_pose_raw": [490127, 0, 425027, 179999, 0, 0],
    "units": "raw_counts",
    "blocking": true,
    "timeout_s": 35.0,
    "include_ee_pose": true
  }'
```

### Delta API Validation Status

2026-04-23 已做兩輪測試。

介面層煙測：
- [api_delta_smoke_8786_20260423.json](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/api_delta_smoke_8786_20260423.json)
- 驗證通過：
  - `GET /delta_pose_calibration`
  - `GET /status`
  - `POST /delta_pose_convert` with:
    - `ready_raw`
    - `ready_mm`
    - `contact_scalars`
    - `left22_mm`
    - `near_edge_mm`
    - `far_edge_mm`
    - `rz_plus_15`
- 錯誤路徑：
  - `delta_pose` 長度錯誤 -> `400`
  - `units=banana` -> `400`
  - `POST /ee_move_delta_raw` 在沒有 monitor 時 -> `409 monitor is not running`

正式 live 服務驗證：
- [api_delta_live_8765_20260423.json](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/api_delta_live_8765_20260423.json)
- 已確認：
  - `GET /delta_pose_calibration` -> `200`
  - `GET /ee_pose?blocking=true&timeout_s=8` -> `200`
    - 回傳包含 `arm_joint_names`、`arm_joint_positions_rad`、`arm_joint_positions_deg`
  - `POST /ee_move_delta_raw` with `ready_raw` -> `200`, `reached=true`
  - `POST /ee_move_delta_raw` with `left22_mm` -> 多次 `409`, `reached=false`
  - 從 `left22_mm` 狀態回 `ready_raw`：
    - 有成功案例
    - 也有 `409 / reached=false` 案例

目前結論：
- `delta_pose_convert` 可用於 dry-run 與轉換檢查
- `ee_move_delta_raw` 對 ready anchor 可用
- `ee_move_delta_raw` 對大 lateral offset 仍不穩
- 這套 `Delta -> 0422` 目前是 `coarse_xy + ready_anchor`，不能當精標定結果

影像證據：
- [after_left22_debug.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_left22_debug.jpg)
- [after_ready_debug.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_ready_debug.jpg)

### GET `/ready_pose`

讀取內建的 conveyor ready pose。

這組 pose 目前對應：
- 使用者提供的台達 ready joint：`490127,0,425027,179999,0,0`
- `0422` 內已驗證的 EE ready 座標
- 夾爪朝正下方

回傳中常見欄位：
- `ready_pose.ee_position_m`
- `ready_pose.reference_tool_xyz_m`
- `ready_pose.yaw_deg`
- `ready_pose.tool_direction`
- `ready_pose.source_delta_joint_counts`

```bash
curl -s http://127.0.0.1:8765/ready_pose
```

### POST `/ready_pose`

讓夾爪回到已驗證的 ready pose。

後端會直接復用 `/ee_move` 的 tool-down 姿態解算，所以夾爪會朝正下方，不是只移到某個 XY 上方。

Request body:

```json
{
  "blocking": true,
  "timeout_s": 20.0
}
```

欄位說明：
- `blocking`: 是否等待完成，預設 `true`
- `timeout_s`: 等待秒數，預設 `20`

```bash
curl -s -X POST http://127.0.0.1:8765/ready_pose \
  -H "Content-Type: application/json" \
  -d '{
    "blocking": true,
    "timeout_s": 20.0
  }'
```

## 4. Scene Object Poses

### GET `/scene_object_poses`

讀取場景中物體目前的幾何位置。

Query parameters:
- `target=<target>`：只查單一物體
- `blocking=true|false`
- `timeout_s=<seconds>`

預設：
- `blocking=true`
- `timeout_s=10`

全部物體：

```bash
curl -s "http://127.0.0.1:8765/scene_object_poses"
```

單一物體：

```bash
curl -s "http://127.0.0.1:8765/scene_object_poses?target=board"
```

回傳中每個物體常見欄位：
- `bbox_center_xyz_m`
- `bbox_min_xyz_m`
- `bbox_max_xyz_m`
- `support_z_m`
- `body_xyz_m`
- `body_quat_wxyz`
- `yaw_deg`
- `kinematic_enabled`
- `physics_mode`

### GET `/object_poses`

讀取目前 API 記住的物體覆寫資料，不是場景即時計算 bbox。

```bash
curl -s http://127.0.0.1:8765/object_poses
```

這個端點回的是：
- `object_pose_overrides`

如果你要看場景裡物體現在實際在哪裡，優先用 `/scene_object_poses`。

## 5. Update Object Pose

### POST `/object_pose`

更新單一物體的位置 / 姿態。

必要欄位：
- `target`
- `position` 或 `xyz`

`position[2]` 的語義是：
- 物體底部要放到的 `support_z`
- 不是 rigid body root 的 z

Request examples:

只改位置：

```json
{
  "target": "board",
  "position": [-0.88, -1.92, 1.019]
}
```

位置 + yaw：

```json
{
  "target": "board",
  "position": [-0.88, -1.92, 1.019],
  "yaw_deg": 90
}
```

位置 + 完整 quaternion：

```json
{
  "target": "board",
  "position": [-0.88, -1.92, 1.019],
  "quat_wxyz": [1, 0, 0, 0]
}
```

旋轉欄位優先順序：
1. `quat_wxyz`
2. `rpy_deg`
3. `yaw_deg`

```bash
curl -s -X POST http://127.0.0.1:8765/object_pose \
  -H "Content-Type: application/json" \
  -d '{
    "target": "board",
    "position": [-0.88, -1.92, 1.019],
    "yaw_deg": 90
  }'
```

## 6. Clear Object Pose Overrides

### POST `/clear_object_poses`

清除物體位置覆寫。

清除全部：

```bash
curl -s -X POST http://127.0.0.1:8765/clear_object_poses \
  -H "Content-Type: application/json" \
  -d '{}'
```

只清單一物體：

```bash
curl -s -X POST http://127.0.0.1:8765/clear_object_poses \
  -H "Content-Type: application/json" \
  -d '{"target":"board"}'
```

## 7. Submit Task

### POST `/task`

下發抓取任務。

Request body:

```json
{
  "mode": "suction",
  "target": "board",
  "record": false,
  "place_xyz": [-0.74, -1.84, 1.019],
  "force_interrupt": false
}
```

欄位說明：
- `mode`: 目前請用 `suction`
- `target`: `board / chopsticks / forcept / shears / knife1 / bigspoon / butterknife / hook1 / spoon`
- `record`: 是否錄影
- `place_xyz`: 可選，指定放置位置 `[x,y,z]`
- `force_interrupt`: 若已有 task 在跑，是否直接搶占

```bash
curl -s -X POST http://127.0.0.1:8765/task \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "suction",
    "target": "board",
    "record": false,
    "force_interrupt": false
  }'
```

### Task Concurrency

如果 task 正在執行：
- `force_interrupt=false`：通常回 `409`
- `force_interrupt=true`：會搶占現有 task

建議外部系統採用：
1. 先查 `/status`
2. 確認 `current_kind != "task"`
3. 再送新的 `/task`

## 8. Abort Task

### POST `/abort_task`

只中止目前 task，不會把整個 API / monitor 關掉。

```bash
curl -s -X POST http://127.0.0.1:8765/abort_task \
  -H "Content-Type: application/json" \
  -d '{}'
```

中止後建議再查一次：

```bash
curl -s http://127.0.0.1:8765/status
curl -s http://127.0.0.1:8765/last_result
```

## 9. Typical Control Loop

外部系統常見流程：

1. `GET /health`
2. `GET /status`
3. `GET /scene_object_poses`
4. 必要時 `POST /object_pose`
5. 必要時 `POST /ee_move`
6. `POST /task`
7. 輪詢 `GET /status`
8. 完成後讀 `GET /last_result`

## 10. Minimal Examples

### Read current board pose

```bash
curl -s "http://127.0.0.1:8765/scene_object_poses?target=board"
```

### Move board by +3 cm in Y

```bash
curl -s -X POST http://127.0.0.1:8765/object_pose \
  -H "Content-Type: application/json" \
  -d '{
    "target": "board",
    "position": [-0.887, -1.919, 1.019]
  }'
```

### Restore board

```bash
curl -s -X POST http://127.0.0.1:8765/clear_object_poses \
  -H "Content-Type: application/json" \
  -d '{"target":"board"}'
```

### Start a suction task

```bash
curl -s -X POST http://127.0.0.1:8765/task \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "suction",
    "target": "board",
    "record": false
  }'
```

### Abort current task

```bash
curl -s -X POST http://127.0.0.1:8765/abort_task \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 11. Deliberately Omitted

以下端點不是這份外部整合文件的範圍：
- `/ui`
- `/webrtc`
- `/display/*`
- `/stream/*`
- `/monitor_target`
- `/monitor_detection`
- `/monitor_focus_highlight`
- `/start_monitor`
- `/stop_monitor`
- `/stop`

這些屬於展示層、監看層或運維控制，不建議直接交給 VLA 或外部業務邏輯作為主控制接口。
