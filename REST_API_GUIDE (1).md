# T9 0422 Full REST API Guide

這份文件對應：
- [t9_persistent_api.py](/home/leon/isaac_ros2_nav2/python_file/0422/t9_persistent_api.py)
- [main_t9_demo.py](/home/leon/isaac_ros2_nav2/python_file/0422/main_t9_demo.py)
- [build_lab9_wrapper_scene.py](/home/leon/isaac_ros2_nav2/python_file/0422/build_lab9_wrapper_scene.py)

這是 `0422` 的完整 API 說明，包含：
- 控制 API
- 監看 / display API
- MJPEG stream API
- WebRTC proxy API
- monitor 運維 API

如果你只要外部系統 / VLA 最小接口，請看 [REST_API_ONLY.md](/home/leon/isaac_ros2_nav2/python_file/0422/REST_API_ONLY.md)。

## 1. Service Layout

正式對外建議只暴露 `8765`：

- 主 API / UI / WebRTC proxy：`http://<HOST>:8765`
- WebRTC companion 內部埠：`8771`

瀏覽器與外部程式通常應該連：
- `http://<HOST>:8765/ui`
- `http://<HOST>:8765/webrtc/`
- `http://<HOST>:8765/...`

不建議外部直接依賴 `8771`。

## 2. Real-to-Sim Calibration

如果你需要把現實機械手臂 / 現實物體座標轉成 `0422` 虛擬場景世界座標，請看：

- [REAL_SIM_CALIBRATION.md](/home/leon/isaac_ros2_nav2/python_file/0422/REAL_SIM_CALIBRATION.md)
- [print_lab9_track_reference_points.py](/home/leon/isaac_ros2_nav2/python_file/0422/print_lab9_track_reference_points.py)
- [compute_real_to_sim_transform.py](/home/leon/isaac_ros2_nav2/python_file/0422/compute_real_to_sim_transform.py)
- [calibration_points_template_0422.json](/home/leon/isaac_ros2_nav2/python_file/0422/calibration_points_template_0422.json)

建議流程：

1. 從 `0422` 的 `track` 印出虛擬參考點
2. 用現實 TCP 去 touch 對應幾何點
3. 用 3 點或 4 點擬合 `real -> sim` 平面剛體變換
4. 再把轉換後的座標送進 `/object_pose` 或 `/ee_move`

## 3. Startup

Docker 內啟動：

```bash
docker exec -it isaac-workspace bash -lc '
start-xvfb-vnc
cd /home/ros2-essentials/python_file/0422
python3 build_lab9_wrapper_scene.py
python3 t9_persistent_api.py \
  --host 0.0.0.0 \
  --port 8765 \
  --webrtc-port 8771 \
  --runtime-root /home/ros2-essentials/python_file/0422/demo_runtime/live_main
'
```

背景啟動：

```bash
cd /home/ros2-essentials/python_file/0422
mkdir -p demo_runtime/live_main/persistent_api
nohup python3 t9_persistent_api.py \
  --host 0.0.0.0 \
  --port 8765 \
  --webrtc-port 8771 \
  --runtime-root /home/ros2-essentials/python_file/0422/demo_runtime/live_main \
  > demo_runtime/live_main/persistent_api/manual_api_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

長時間常駐保護：
- `T9_MONITOR_STEP_RESET_INTERVAL`：monitor step 計數器達到指定值後歸零，預設 `1000000`
- `T9_RUNTIME_LOG_ROTATE_MAX_BYTES`：目前執行中的 log 超過此大小時原地截斷，預設 `67108864`（64 MiB）
- `T9_RUNTIME_LOG_ROTATE_CHECK_INTERVAL_S`：log 大小檢查週期，預設 `15`

## 4. Supported Targets

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

### GET `/supported_classes`

查詢目前支援的類別清單，以及每個類別支援的模式與 metadata。

相容 alias：
- `GET /supported_targets`

回傳欄位：
- `supported_classes`
- `supported_targets`
- `target_supported_modes`
- `target_metadata`

其中：
- `supported_classes` 和 `supported_targets` 內容相同
- `target_supported_modes` 會列出每個類別支援 `suction` 或 `grasp`
- `target_metadata` 會帶各類別目前的 source / destination / support z 等資訊

```bash
curl -s http://127.0.0.1:8765/supported_classes
```

## 5. Response Pattern

常見成功格式：

```json
{
  "ok": true
}
```

常見失敗格式：

```json
{
  "ok": false,
  "message": "...",
  "error": "..."
}
```

常見 HTTP code：
- `200`：成功
- `400`：請求格式錯誤 / 參數錯誤
- `404`：端點或資源不存在
- `409`：狀態衝突，例如 task 已在執行
- `500`：未處理例外
- `502`：WebRTC proxy 後端失敗

## 5. Endpoint Overview

### General / Status
- `GET /health`
- `GET /status`
- `GET /supported_classes`
- `GET /last_result`

### UI / WebRTC
- `GET /`
- `GET /ui`
- `GET /webrtc/`
- `GET /webrtc/health`
- `POST /webrtc/offer`

### Display / Image
- `GET /display/meta`
- `GET /display/composite.jpg`
- `GET /display/d435_left.jpg`
- `GET /display/d435_right.jpg`
- `GET /display/d435.jpg`
- `GET /display/wrist.jpg`
- `GET /display/debug.jpg`

### MJPEG Stream
- `GET /stream/composite.mjpg`
- `GET /stream/d435_left.mjpg`
- `GET /stream/d435_right.mjpg`
- `GET /stream/d435.mjpg`
- `GET /stream/wrist.mjpg`
- `GET /stream/debug.mjpg`

### Motion / EE
- `GET /motion_profile`
- `POST /motion_profile`
- `GET /motion_profile_percent`
- `POST /motion_profile_percent`
- `GET /coordinate_frames`
- `GET /delta_pose_calibration`
- `GET /ready_pose`
- `POST /ready_pose`
- `GET /ee_pose`
- `POST /ee_move`
- `POST /position_convert`
- `POST /delta_pose_convert`
- `POST /ee_move_delta_raw`

### Object / Scene
- `GET /object_poses`
- `GET /scene_object_poses`
- `POST /object_pose`
- `POST /clear_object_poses`

### Task / Monitor Control
- `POST /task`
- `POST /abort_task`
- `GET /monitor_detection`
- `POST /monitor_detection`
- `GET /monitor_focus_highlight`
- `POST /monitor_focus_highlight`
- `POST /monitor_target`
- `POST /start_monitor`
- `POST /stop_monitor`
- `POST /stop`

## 6. General / Status API

### GET `/health`

確認 API 是否存活。

```bash
curl -s http://127.0.0.1:8765/health
```

### GET `/status`

讀取完整 runtime snapshot。

常用欄位：
- `current_kind`: `monitor` / `task` / `idle`
- `current_running`
- `current_pid`
- `current_task`
- `monitor_target`
- `monitor_detection_enabled`
- `monitor_focus_highlight_enabled`
- `motion_profile`
- `ee_move_limits`
- `object_physics_mode`
- `ready_pose`
- `object_pose_overrides`
- `last_result`
- `web_display_meta`

```bash
curl -s http://127.0.0.1:8765/status
```

### GET `/supported_classes`

查詢目前支援的類別清單。

相容 alias：
- `GET /supported_targets`

回傳欄位：
- `supported_classes`
- `supported_targets`
- `target_supported_modes`
- `target_metadata`

```bash
curl -s http://127.0.0.1:8765/supported_classes
```

### GET `/last_result`

讀取上一個 task 結果。

```bash
curl -s http://127.0.0.1:8765/last_result
```

## 7. UI / WebRTC API

### GET `/` and GET `/ui`

回傳內建控制頁。

```bash
curl -s http://127.0.0.1:8765/ui
```

### GET `/webrtc/`

回傳內建 WebRTC 監看頁。

```bash
curl -s http://127.0.0.1:8765/webrtc/
```

### GET `/webrtc/health`

透過 `8765` 代理到 WebRTC companion health。

```bash
curl -s http://127.0.0.1:8765/webrtc/health
```

### POST `/webrtc/offer`

WebRTC SDP offer/answer 協商入口。

這個端點主要是給前端頁面使用，但若你要自己實作客戶端也可以直接打。

Request body 由 WebRTC client 產生，典型會包含：
- `sdp`
- `type`

```bash
curl -s -X POST http://127.0.0.1:8765/webrtc/offer \
  -H "Content-Type: application/json" \
  -d '{"type":"offer","sdp":"..."}'
```

目前成功時可協商四個 video tracks：
- `d435_left`
- `d435_right`
- `wrist`
- `debug`

## 8. Display / Image API

### GET `/display/meta`

讀取目前 display 狀態摘要。

常見欄位：
- `meta.source_kind`
- `meta.mode`
- `meta.target`
- `meta.overlay_target`
- `meta.state`
- `meta.phase`
- `meta.available_views`
- `meta.image_paths`

```bash
curl -s http://127.0.0.1:8765/display/meta
```

### GET `/display/*.jpg`

讀取目前最新單張影格。

可用：
- `/display/composite.jpg`
- `/display/d435_left.jpg`
- `/display/d435_right.jpg`
- `/display/d435.jpg`
- `/display/wrist.jpg`
- `/display/debug.jpg`

說明：
- `/display/d435.jpg` 是相容別名，等同左 D435

例如：

```bash
curl -o wrist.jpg http://127.0.0.1:8765/display/wrist.jpg
```

## 9. MJPEG Stream API

### GET `/stream/*.mjpg`

取得 multipart MJPEG stream。

可用：
- `/stream/composite.mjpg`
- `/stream/d435_left.mjpg`
- `/stream/d435_right.mjpg`
- `/stream/d435.mjpg`
- `/stream/wrist.mjpg`
- `/stream/debug.mjpg`

`/stream/d435.mjpg` 同樣是左 D435 相容別名。

例如：

```bash
curl -I http://127.0.0.1:8765/stream/wrist.mjpg
```

## 10. Motion Profile API

### GET `/motion_profile`

讀取目前速度設定。

```bash
curl -s http://127.0.0.1:8765/motion_profile
```

### POST `/motion_profile`

直接設定速度參數。

可用欄位：
- `coarse_move_max_step_xy_m`
- `coarse_move_max_step_z_m`
- `task_max_step_xy_m`
- `task_max_step_z_m`
- `task_max_step_rise_m`

範例：

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
- task 執行中會拒絕更新
- 後端有最小值保護

### GET `/motion_profile_percent`

讀取 `0~100%` 百分比速度映射與目前值。

```bash
curl -s http://127.0.0.1:8765/motion_profile_percent
```

### POST `/motion_profile_percent`

直接用百分比設定速度。

接受：
- `speed_percent`
- `percent`

```bash
curl -s -X POST http://127.0.0.1:8765/motion_profile_percent \
  -H "Content-Type: application/json" \
  -d '{"speed_percent": 60}'
```

## 11. End-Effector API

### GET `/delta_pose_calibration`

讀取目前 `Delta 六軸 -> 0422 虛擬座標` 的粗轉換參數。

回傳會直接標示：
- 哪些量是固定標定值
- 哪些量仍然是粗估
- 目前姿態映射只會用 `tool-down + yaw`

```bash
curl -s http://127.0.0.1:8765/delta_pose_calibration
```

### GET `/coordinate_frames`

讀取目前支援的座標框架與粗標定參數。

目前支援的 `coordinate_frame`：
- `sim_world_m`
- `delta_xyz_m`
- `delta_xyz_mm`
- `delta_xyz_raw`
- `conveyor_semantic_m`

```bash
curl -s http://127.0.0.1:8765/coordinate_frames
```

### POST `/position_convert`

把位置座標從現實側 frame 轉成 `0422` 虛擬世界座標，但不真的移動手臂或物體。

Request body：

```json
{
  "position": [490.127, 0.0, 425.027],
  "coordinate_frame": "delta_xyz_mm"
}
```

```bash
curl -s -X POST http://127.0.0.1:8765/position_convert \
  -H "Content-Type: application/json" \
  -d '{
    "position": [490.127, 0.0, 425.027],
    "coordinate_frame": "delta_xyz_mm"
  }'
```

### GET `/ready_pose`

讀取內建的 lab9 conveyor ready pose。

這組 pose 目前對應：
- 使用者提供的台達 ready joint：`490127,0,425027,179999,0,0`
- `0422` 內已驗證的 ready EE 座標
- 夾爪朝正下方

回傳中常見欄位：
- `ready_pose.ee_position_m`
- `ready_pose.reference_tool_xyz_m`
- `ready_pose.yaw_deg`
- `ready_pose.tool_direction`
- `ready_pose.source_delta_joint_counts`
- `ready_pose.ee_coordinate_frames`

```bash
curl -s http://127.0.0.1:8765/ready_pose
```

### POST `/ready_pose`

讓夾爪回到已驗證的 ready pose。

這個 API 內部直接走 `/ee_move` 同一套 tool-down 姿態解算，不會只移位置而把夾爪角度做歪。

Request body：

```json
{
  "blocking": true,
  "timeout_s": 20.0
}
```

```bash
curl -s -X POST http://127.0.0.1:8765/ready_pose \
  -H "Content-Type: application/json" \
  -d '{
    "blocking": true,
    "timeout_s": 20.0
  }'
```

### GET `/ee_pose`

讀取當前末端位置。

Query parameters：
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
- `result.ee_coordinate_frames`
- `result.tool_xyz_m`
- `result.tool_quat_wxyz`
- `result.tool_yaw_deg`
- `result.tool_coordinate_frames`
- `result.arm_joint_names`
- `result.arm_joint_positions_rad`
- `result.arm_joint_positions_deg`

注意：
- `result.ee_coordinate_frames.delta_xyz_*` 是從目前 sim pose 反推回 Delta 側的 coarse 參考值
- 這些 query-side inverse 欄位適合 debug / 比對，不應視為精標定 ground truth

### POST `/ee_move`

直接指定末端世界座標。

Request body：

```json
{
  "position": [490.127, 0.0, 425.027],
  "coordinate_frame": "delta_xyz_mm",
  "yaw_deg": 0.0,
  "blocking": true,
  "timeout_s": 35.0
}
```

也接受：
- `xyz`

額外可用欄位：
- `coordinate_frame`
- `units`

```bash
curl -s -X POST http://127.0.0.1:8765/ee_move \
  -H "Content-Type: application/json" \
  -d '{
    "position": [490.127, 0.0, 425.027],
    "coordinate_frame": "delta_xyz_mm",
    "yaw_deg": 0.0,
    "blocking": true,
    "timeout_s": 35.0
  }'
```

注意：
- 如果 `coordinate_frame=sim_world_m`，`position` 才是 `0422` 世界座標公尺值
- 如果 `coordinate_frame=delta_xyz_*` 或 `conveyor_semantic_m`，後端會先轉成 `0422`
- 若超出 `status.ee_move_limits`，後端會直接拒絕並回 `400`
- 回傳中會多帶 `converted_position`

### POST `/delta_pose_convert`

把台達 6 軸座標先轉成 `0422` 虛擬世界座標，但不真的移動手臂。

這個端點適合做：
- 先看轉換後的 `sim_ee_position_m`
- 檢查這次輸入是否已經超出目前粗標定的參考範圍
- 在外部系統真正呼叫移動前，先做 dry-run 驗證

Request body：

```json
{
  "delta_pose": [490.127, 0.000, 425.027, 179.999, 0.000, 0.000],
  "units": "mm_deg"
}
```

也接受：
- `delta_pose_raw`: `[490127, 0, 425027, 179999, 0, 0]`
- 或直接送 `x,y,z,rx,ry,rz`

支援的 `units`：
- `auto`
- `mm_deg`
- `raw_counts`
- `m_deg`

回傳中常見欄位：
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

直接接收台達 6 軸座標，先轉成 `0422` 虛擬 EE 目標，再送進目前的 `/ee_move` 控制鏈。

目前姿態行為：
- 位置：用粗標定的 `Delta -> 0422` 轉換
- 姿態：固定 `tool-down`
- yaw：用 `ready_yaw + (rz - ready_rz)` 近似
- `rx` / `ry` 目前只保留在回傳資訊，不會驅動到 IK

Request body：

```json
{
  "delta_pose_raw": [490127, 0, 425027, 179999, 0, 0],
  "units": "raw_counts",
  "blocking": true,
  "timeout_s": 35.0,
  "include_ee_pose": true
}
```

回傳中常見欄位：
- `converted_pose`
- `result`
- `ee_pose_after_move`

如果 `blocking=true` 且 `include_ee_pose=true`，後端會在移動完成後再查一次 `/ee_pose`，把當下的關節角一起回來。

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

### Delta API Validation Notes

2026-04-23 已做兩輪驗證：

1. 介面層煙測
   - 臨時服務：`127.0.0.1:8786 --no-auto-monitor --no-webrtc`
   - 結果檔：
     - [api_delta_smoke_8786_20260423.json](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/api_delta_smoke_8786_20260423.json)
   - 驗證通過：
     - `GET /delta_pose_calibration`
     - `GET /status`
     - `POST /delta_pose_convert` for:
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

2. 正式 live 服務驗證
   - 結果檔：
     - [api_delta_live_8765_20260423.json](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/api_delta_live_8765_20260423.json)
   - 關鍵結果：
     - `GET /delta_pose_calibration` -> `200`
     - `GET /ee_pose?blocking=true&timeout_s=8` -> `200`
       - 已確認回傳：
         - `arm_joint_names`
         - `arm_joint_positions_rad`
         - `arm_joint_positions_deg`
       - `arm_joint_count = 6`
     - `POST /ee_move_delta_raw` with `ready_raw` -> `200`
       - `result.result.reached = true`
     - `POST /ee_move_delta_raw` with `left22_mm` -> 多次 `409`
       - `result.result.reached = false`
       - `final_error_m` 約 `0.23 ~ 0.29`
     - 從失敗的 `left22_mm` 狀態回 `ready_raw`：
       - 有一輪成功
       - 也有一輪 `409 / reached=false`
       - 代表粗轉換在大幅側向位移下，live IK 收斂仍不穩

結論：
- `delta_pose_convert` 目前可用於轉換與 dry-run 檢查
- `ee_move_delta_raw` 對 `ready` 這類已驗證 anchor 可用
- `ee_move_delta_raw` 對 `left22_mm` 這種較大 lateral offset 目前仍可能收斂失敗
- 這套轉換目前應視為 `coarse_xy + ready_anchor`，不應當作精標定結果

影像證據：
- [after_left22_d435_left.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_left22_d435_left.jpg)
- [after_left22_wrist.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_left22_wrist.jpg)
- [after_left22_debug.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_left22_debug.jpg)
- [after_ready_d435_left.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_ready_d435_left.jpg)
- [after_ready_wrist.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_ready_wrist.jpg)
- [after_ready_debug.jpg](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/delta_api_live_frames_20260423/after_ready_debug.jpg)

## 12. Object / Scene API

### GET `/object_poses`

讀取目前 API 記錄的 pose override，不是即時計算的場景 bbox。

override 內也會附上：
- `coordinate_frames`
- `object_position_semantics`

注意：
- `coordinate_frames.sim_world_m` 是 override 直接使用的 `0422` 世界座標
- `coordinate_frames.delta_xyz_*` 與 `conveyor_semantic_m` 是從 sim pose 反推的 coarse 參考值

```bash
curl -s http://127.0.0.1:8765/object_poses
```

### GET `/scene_object_poses`

讀取場景中物體的即時幾何資訊。

Query parameters：
- `target=<name>`
- `blocking=true|false`
- `timeout_s=<seconds>`

預設：
- `blocking=true`
- `timeout_s=10`

```bash
curl -s "http://127.0.0.1:8765/scene_object_poses"
curl -s "http://127.0.0.1:8765/scene_object_poses?target=board"
```

每個物體常見欄位：
- `bbox_center_xyz_m`
- `bbox_min_xyz_m`
- `bbox_max_xyz_m`
- `support_z_m`
- `body_xyz_m`
- `body_quat_wxyz`
- `yaw_deg`
- `kinematic_enabled`
- `physics_mode`
- `coordinate_frames`
- `object_position_semantics`

注意：
- `coordinate_frames.sim_world_m` 對應即時場景幾何
- `coordinate_frames.delta_xyz_*` 與 `conveyor_semantic_m` 來自 inverse conversion
- 目前 inverse 的 Delta 側回推仍是 coarse，不應直接拿去做精準 real-world 校正

### POST `/object_pose`

更新物體位置 / 姿態。

必要欄位：
- `target`
- `position` 或 `xyz`

其中 `position[2]` 的語義是：
- 物體底部的 `support_z`
- 不是 rigid body root 的 z

旋轉欄位優先順序：
1. `quat_wxyz`
2. `rpy_deg`
3. `yaw_deg`

支援的 `coordinate_frame`：
- `sim_world_m`
- `delta_xyz_m`
- `delta_xyz_mm`
- `delta_xyz_raw`
- `conveyor_semantic_m`

Request examples：

```json
{
  "target": "board",
  "position": [0.30, 0.10, -0.0055],
  "coordinate_frame": "conveyor_semantic_m"
}
```

```json
{
  "target": "board",
  "position": [0.30, 0.10, -0.0055],
  "coordinate_frame": "conveyor_semantic_m",
  "yaw_deg": 90
}
```

```json
{
  "target": "board",
  "position": [-0.88, -1.92, 1.019],
  "quat_wxyz": [1, 0, 0, 0]
}
```

```bash
curl -s -X POST http://127.0.0.1:8765/object_pose \
  -H "Content-Type: application/json" \
  -d '{
    "target": "board",
    "position": [0.30, 0.10, -0.0055],
    "coordinate_frame": "conveyor_semantic_m",
    "yaw_deg": 90
  }'
```

可選欄位：
- `restart_monitor`

但在 0422 單一 instance 模式下，這個欄位只做相容保留，不再靠 restart 去套用變更。

回傳中會多帶：
- `converted_position`

### POST `/clear_object_poses`

清除 pose override。

清全部：

```bash
curl -s -X POST http://127.0.0.1:8765/clear_object_poses \
  -H "Content-Type: application/json" \
  -d '{}'
```

清單一物體：

```bash
curl -s -X POST http://127.0.0.1:8765/clear_object_poses \
  -H "Content-Type: application/json" \
  -d '{"target":"board"}'
```

## 13. Task API

### POST `/task`

下發抓取任務。

Request body：

```json
{
  "mode": "suction",
  "target": "board",
  "record": false,
  "place_xyz": [0.25, 0.15, -0.0055],
  "place_coordinate_frame": "conveyor_semantic_m",
  "force_interrupt": false
}
```

欄位說明：
- `mode`: 目前請用 `suction`
- `target`: 物體名稱
- `record`: 是否錄影
- `place_xyz`: 可選，指定放置位置 `[x,y,z]`
- `place_coordinate_frame`: 預設 `sim_world_m`
- `place_units`: 只在 `delta_xyz_*` frame 需要時使用，預設 `auto`
- `force_interrupt`: 若已有 task 在跑，是否搶占

如果有帶 `place_xyz`，回傳會多帶：
- `converted_place_xyz`

```bash
curl -s -X POST http://127.0.0.1:8765/task \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "suction",
    "target": "board",
    "record": false,
    "place_xyz": [0.25, 0.15, -0.0055],
    "place_coordinate_frame": "conveyor_semantic_m",
    "force_interrupt": false
  }'
```

### POST `/abort_task`

只中止目前 task，不關 monitor、不關 API。

```bash
curl -s -X POST http://127.0.0.1:8765/abort_task \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Task Concurrency

若 task 正在執行：
- `force_interrupt=false`：通常回 `409`
- `force_interrupt=true`：搶占前一個 task

建議外部系統流程：
1. 先查 `/status`
2. 確認 `current_kind != "task"`
3. 再送 `/task`

## 14. Monitor Control API

### GET `/monitor_detection`

讀取 monitor 是否啟用 detection overlay。

```bash
curl -s http://127.0.0.1:8765/monitor_detection
```

### POST `/monitor_detection`

更新 detection overlay 開關。

Request body：

```json
{
  "enabled": true
}
```

可選：
- `restart_monitor`

```bash
curl -s -X POST http://127.0.0.1:8765/monitor_detection \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### GET `/monitor_focus_highlight`

讀取 focus highlight 開關。

```bash
curl -s http://127.0.0.1:8765/monitor_focus_highlight
```

### POST `/monitor_focus_highlight`

更新 focus highlight 開關。

```bash
curl -s -X POST http://127.0.0.1:8765/monitor_focus_highlight \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### POST `/monitor_target`

切換 monitor 的 focus target。

```bash
curl -s -X POST http://127.0.0.1:8765/monitor_target \
  -H "Content-Type: application/json" \
  -d '{"target":"board"}'
```

### POST `/start_monitor`

啟動 monitor。

```bash
curl -s -X POST http://127.0.0.1:8765/start_monitor \
  -H "Content-Type: application/json" \
  -d '{}'
```

### POST `/stop_monitor`

只關 monitor，不關 API。

```bash
curl -s -X POST http://127.0.0.1:8765/stop_monitor \
  -H "Content-Type: application/json" \
  -d '{}'
```

### POST `/stop`

停止整個 runtime。

這會讓：
- task 停止
- monitor 停止
- `auto_monitor=false`

```bash
curl -s -X POST http://127.0.0.1:8765/stop \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 15. Coordinate Conversion Regression

2026-04-24 已對正式 `127.0.0.1:8765` 再跑一輪 live regression：
- [summary.json](/home/leon/isaac_ros2_nav2/python_file/0422/demo_outputs/tmp/coord_api_regression_20260424/summary.json)

這輪已驗證：
- `GET /coordinate_frames`
- `POST /position_convert`
- `POST /ee_move` with `coordinate_frame=delta_xyz_mm`
- `GET /ee_pose` 回傳 `ee_coordinate_frames / tool_coordinate_frames / arm_joint_positions_*`
- `GET /scene_object_poses`
- `GET /object_poses`
- `POST /object_pose` with `coordinate_frame=conveyor_semantic_m`
- `POST /object_pose` with `coordinate_frame=delta_xyz_mm`
- `POST /clear_object_poses`
- `POST /task` with `place_coordinate_frame=conveyor_semantic_m`
- `POST /abort_task`

關鍵結論：
- forward conversion 可用：
  - `delta_xyz_* -> sim_world_m`
  - `conveyor_semantic_m -> sim_world_m`
- `ee_move` / `object_pose` / `task.place_xyz` 已能直接吃現實側 frame
- query API 回傳的 `coordinate_frames.delta_xyz_*` 目前是 coarse inverse
- 這些 inverse 欄位適合 debug / 對照，不應拿來當精標定結果

## 16. Common Workflows

### 16.1 只看畫面

1. `GET /ui`
2. `GET /webrtc/`
3. 或 `GET /stream/*.mjpg`

### 16.2 場景同步

1. `GET /scene_object_poses`
2. `POST /object_pose`
3. `POST /clear_object_poses`

### 16.3 控制末端

1. `GET /ee_pose`
2. `POST /ee_move`

### 16.4 下發抓取

1. `GET /status`
2. `POST /task`
3. 輪詢 `GET /status`
4. `GET /last_result`

### 16.5 搶占 / 中止

1. `POST /abort_task`
2. `GET /last_result`
3. 必要時 `POST /start_monitor`

## 17. Notes

- `0422` 已經是單一 Isaac instance 架構，`task`、`object_pose`、`monitor_target` 這些操作不會靠 restart Isaac 來達成。
- `d435` 類路徑是左側 D435 的相容別名：
  - `/display/d435.jpg`
  - `/stream/d435.mjpg`
- 外部瀏覽器建議直接走 `8765/webrtc/`，不要直接依賴 `8771`。
