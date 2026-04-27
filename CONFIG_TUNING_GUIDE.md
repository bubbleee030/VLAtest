# Config Tuning Guide

這份文件是給現在這套 `voice_pick` demo 用的快速調整指南。  
重點不是列出所有欄位，而是回答：

- 我想改語音辨識，要改哪裡？
- 我想改 NLU 對應詞，要改哪裡？
- 我想改手臂速度、home、ready、pick，要改哪裡？
- 我想改 UI 顯示哪些模組，要改哪裡？
- 我想改相機、claw、tactile sensor，要改哪裡？

## 1. 語音辨識 ASR

檔案：`config/voice_config.yaml`

### 你想達成的目的

#### 改 ASR 引擎
- `engine: "whisper"`
- `engine: "breeze-asr"`

建議：
- demo 穩定優先：用 `whisper`
- 如果之後要實驗更強中文辨識：再試 `breeze-asr`

#### 改 Whisper 模型大小
- `whisper.model_size`

可選：
- `tiny`
- `base`
- `small`
- `medium`
- `large`

建議：
- 現場 demo：`small`
- 要更快：`base`
- 要更準但更慢：`medium`

#### 固定語言
- `whisper.language`

可選：
- `null`：自動判斷
- `"zh"`：固定中文
- `"en"`：固定英文

建議：
- 中文 demo：改成 `"zh"` 會比較穩

#### 控制錄音長度
- `microphone.record_seconds`

用途：
- 每次語音最多錄多久

建議：
- 短句 demo：`4` 到 `5`
- 句子稍長：`6` 到 `8`

#### 控制靜音自動停止
- `microphone.silence_threshold`
- `microphone.silence_duration_s`

用途：
- 人停下來多久後自動停止收音

## 2. NLU 對應詞與口語別名

### 2.1 物件基本名稱

檔案：`config/objects.yaml`

這裡放的是：
- 物件 key
- YOLO class
- 中英文基本名稱
- 固定 pick pose

### 你想達成的目的

#### 改某個物件在 UI 顯示的中文名
- 改 `classes.<object_key>.chinese`

例子：
```yaml
knife:
  chinese: ["刀子", "菜刀"]
```

注意：
- 這裡現在主要是基本名稱
- 不建議把太泛的詞塞在這裡，例如 `紅色`、`板`、`刀`

#### 改某個物件預設要用哪一筆 teach / replay recording
- 改 `classes.<object_key>.default_teach_recording`

例子：
```yaml
trapezoid:
  default_teach_recording: "trapezoid_v2.merged"
```

用途：
- 當你在 `Teach` 模式或語音/NLU 已經辨到該物件時，系統會優先拿這筆 recording 去 replay
- 很適合把新錄好的 `.merged` 版本設成目前主用版本

### 2.2 語音/NLU 專用 mapping

檔案：`config/nlu_aliases.yaml`

這是現在最重要的語音 mapping 檔。

#### 你想修 ASR 常見錯字
- 改 `global_normalization`

例子：
```yaml
global_normalization:
  "梯型": "梯形"
  "紅色方塊": "紅色梯形"
```

用途：
- ASR 先把文字修正，再送 NLU

#### 你想指定「講這句就等於某個物件」
- 改 `phrase_map`

例子：
```yaml
phrase_map:
  "紅色": "trapezoid"
  "小湯匙": "coffee_scoop"
  "奶油刀": "butter_knife"
```

用途：
- 這層優先度最高
- 適合放你現場常講的口語短句

注意：
- 泛詞像 `紅色` 會非常強，因為它會直接指定物件
- 如果你不想再讓 `紅色 -> trapezoid`，把這條刪掉就好

#### 你想補某個物件更多口語別名
- 改 `object_alias_overrides`

例子：
```yaml
trapezoid:
  chinese: ["梯形積木", "紅色梯形木塊"]
```

用途：
- 這層比 `phrase_map` 弱
- 適合補充「常見講法」，但不要放太泛的詞

## 3. 口語講稿資料

檔案：`config/speech_prompts.yaml`

這份現在不顯示在 UI 上，但你可以把它當成自己的 demo 小抄資料庫。

### 你想達成的目的

#### 設定預設關注的物件
- `active_object`

#### 幫某個物件準備好講的句子
- `objects.<object_key>.stable_lines`
- `objects.<object_key>.natural_lines`
- `objects.<object_key>.avoid_lines`

用途：
- `stable_lines`：最穩、最短、最建議 demo 念的句子
- `natural_lines`：比較像自然說話
- `avoid_lines`：容易誤辨或誤對應的講法

## 4. 手臂動作、Home、Ready、Pick

檔案：`config/demo_config.yaml`

這是整個 demo 的主設定。

### 4.1 安全範圍

#### 改 XYZ 安全邊界
- `safety_boundary`

用途：
- 超過這個範圍，手臂會拒絕移動

#### 改更細的 pose limit
- `pose_limits`

用途：
- 額外限制 x/y/z/rx/ry

注意：
- `pose_limits.enforce_maintenance_limits` 預設用途是把範圍收斂到 maintenance 腳本註解的保守範圍
- 如果你錄到的 teach/replay 點低於 maintenance 的 `z_min`，但仍高於你自己的安全桌面高度，可以設：
```yaml
pose_limits:
  enforce_maintenance_limits: false
  z_min: 100000
```
- 這不是完全關 safety；它仍會用 `pose_limits` / `safety_boundary` 的 x/y/z 範圍擋掉超界動作
- `pose_limits.enforce_rotation_limits` 目前預設是 `false`
- 因為你現在很多 pose 的姿態值跟 maintenance 註解不完全一致，直接打開可能會把現有動作卡死

### 4.2 Pick 速度

#### 改 approach / descend 速度
- `speed.fast_percent`
- `speed.slow_percent`

用途：
- `fast_percent`：靠近物件上方時
- `slow_percent`：最後下壓、夾取前

#### 改切慢速的高度
- `speed.speed_switch_z_offset_um`

用途：
- 距離目標 Z 多近時，從快切慢

### 4.3 Ready

#### 改 Ready 的速度與等待方式
- `ready_motion.speed_percent`
- `ready_motion.verify_in_position`
- `ready_motion.verify_timeout_s`

用途：
- 控制按 `Ready` 時怎麼走

### 4.4 Home

#### 改 Home 策略
- `home_routing.default_strategy`

可選：
- `"native_1405"`
- staged route

#### 改 staged home route
- `home_routing.staged_route`

用途：
- 如果 native home 不夠安全，可以改多段 home 路徑

### 4.5 Pick / Replay 結尾要回哪

#### 改固定 pick 收尾
- `pick_sequence.return_pose`

建議：
- 現在通常用 `"ready"`

#### Teach raw replay 收尾
- `teach.raw_replay_return_pose`

## 5. Teach、錄製、dataset、auto-label

檔案：`config/demo_config.yaml`

### 你想達成的目的

#### 開關 teach
- `teach.enabled`

#### 改 teach replay 預設模式
- `teach.default_replay_mode`

可選：
- `"phase"`
- `"phase_axis_split"`
- `"raw"`

用途：
- `phase`：照 phase 點位直接走，每一段一次送完整 pose
- `phase_axis_split`：同一份 phase YAML，但每段拆成 `先 XY/姿態，再 Z`
- `raw`：照 teach waypoint 原始回放

建議：
- 如果你想讓動作看起來更果斷、避免靠近物體時多軸一起下壓，先試 `phase_axis_split`
- 目前這份 repo 已預設切到 `phase_axis_split`

#### 改 teach phase replay 預設速度/高度
- `teach.phase_templates.default.hover_z_offset_um`
- `teach.phase_templates.default.pregrasp_z_offset_um`
- `teach.phase_templates.default.lift_z_offset_um`
- `teach.phase_templates.default.fast_percent`
- `teach.phase_templates.default.slow_percent`
- `teach.phase_templates.default.pregrasp_percent`
- `teach.phase_templates.default.grasp_percent`
- `teach.phase_templates.default.lift_percent`

#### 改 teach phase replay 的夾爪開合速度
- `teach.phase_templates.default.gripper_position_move_mode`
- `teach.phase_templates.default.gripper_open_step_ticks`
- `teach.phase_templates.default.gripper_open_step_delay_s`
- `teach.phase_templates.default.gripper_close_step_ticks`
- `teach.phase_templates.default.gripper_close_step_delay_s`

用途：
- 這些是之後新產生 `.phases.yaml` 的預設值
- `close_step_ticks` 越小、`close_step_delay_s` 越大，夾取就越慢、越保守
- 如果你想對齊 AGX 那支 `gripper_speed = 10` 的手感，先從 `gripper_close_step_ticks: 10` 開始

#### 直接改單一 recording 的 phase YAML
- `data/teach_recordings/<name>.phases.yaml`
- `gripper.position_move_mode`
- `gripper.open_step_ticks`
- `gripper.open_step_delay_s`
- `gripper.open_wait_s`
- `gripper.open_tolerance_ticks`
- `gripper.close_step_ticks`
- `gripper.close_step_delay_s`
- `gripper.close_wait_s`
- `gripper.close_tolerance_ticks`
- `gripper.release_step_ticks`
- `gripper.release_step_delay_s`
- `gripper.release_wait_s`
- `gripper.release_tolerance_ticks`
- `speed.pregrasp_percent`
- `speed.grasp_percent`
- `speed.place_percent`
- `speed.place_descend_percent`
- `place_hover_pose`
- `place_pose`
- `place_lift_pose`

用途：
- 只改某一筆 replay 的夾爪速度，不影響其他 recording
- 這通常比改全域預設更適合現場微調
- `pregrasp_percent` 只控制接近物體前最後一段下降
- `grasp_percent` 只控制真正進入夾取點的最後一小段
- 如果 phase YAML 有 `place_hover_pose` / `place_pose`，Phase Replay 會在夾起後多走放置流程
- `release_positions` 是放置點要開到的爪子位置，`release_step_*` 控制開爪速度
- `*_wait_s` 會在送出目標位置後輪詢 `/state.current_pos`，等到爪子實際接近目標再往下走
- `*_tolerance_ticks` 是允許誤差；現場 demo 可以先用 `35` 到 `50`
- 如果這兩個沒填，系統會 fallback 到舊的 `slow_percent`

#### 改 teach 錄影/資料集輸出
- `teach.dataset_capture.enabled`
- `teach.dataset_capture.output_root`
- `teach.dataset_capture.image_fps`
- `teach.dataset_capture.telemetry_hz`
- `teach.dataset_capture.camera_streams`

#### 改自動標註 YOLO
- `teach.auto_label.enabled`
- `teach.auto_label.streams`
- `teach.auto_label.model_path`
- `teach.auto_label.conf`

## 6. UI 顯示哪些模組

檔案：`config/demo_config.yaml`

### 你想達成的目的

#### 關掉某個模組但保留後端
- `modules.<module>.show_in_ui: false`

#### 整個模組連後端都關掉
- `modules.<module>.enabled: false`

常用例子：
```yaml
modules:
  teach: { enabled: false, show_in_ui: false }
  virtual_env: { enabled: false, show_in_ui: false }
  virtual_env_data: { enabled: false, show_in_ui: false }
  sensor_chart: { enabled: true, show_in_ui: true }
```

補充：
- `virtual_env` 控制三個虛擬畫面 view
- `virtual_env_data` 只控制 `Digital Twin Data` 資訊面板
- 如果你只想保留虛擬影像、不想顯示那塊資訊欄，就把 `virtual_env_data.show_in_ui` 關掉

## 7. Tactile / Sensor API

檔案：`config/demo_config.yaml`

### 你想達成的目的

#### 改 tactile sensor API 位址
- `sensor_api.base_url`
- `sensor_api.endpoint`

#### 改更新頻率
- `sensor_api.poll_hz`

#### 改圖表保留長度
- `sensor_api.history_points`

#### 改 Y 軸範圍
- `sensor_api.y_min`
- `sensor_api.y_max`

#### 讓 tactile 圖自動縮放
- `sensor_api.auto_range`
- `sensor_api.auto_range_padding_ratio`
- `sensor_api.min_range_span`

用途：
- `auto_range: true` 時，圖表會依目前資料自動調整 Y 軸
- 感測值忽然變大時，不會整條跑出畫面

建議：
- demo 現場：`auto_range: true`
- 如果你要固定量測範圍：改成 `false`，再手動設 `y_min/y_max`

## 8. Digital Twin / 虛擬環境

檔案：`config/demo_config.yaml`

### 你想達成的目的

#### 改數位雙生 API 位址
- `virtual_env.base_url`

#### 改要顯示哪些 view
- `virtual_env.desired_views`

例子：
```yaml
virtual_env:
  desired_views: ["wrist"]
```

用途：
- 如果你只想先看一個視角、降低畫面更新壓力，可以先只留 `wrist`

#### 改 arm sync 模式
- `virtual_env.sync.arm.mode`

可選：
- `delta_raw`
- `direct_ee_move`

用途：
- `delta_raw`：走 0422 的 `/ee_move_delta_raw`
- `direct_ee_move`：走本地粗轉換後的 `/ee_move`

#### 改 digital twin arm sync 頻率
- `virtual_env.sync.min_interval_s`

建議：
- 要更即時：先試 `0.15` 到 `0.2`
- 如果開始常出 `409`：再調回 `0.25` 到 `0.35`

#### 改 delta raw 單位
- `virtual_env.sync.arm.delta_units`

可選：
- `raw_counts`
- `mm_deg`

建議：
- 優先用 `raw_counts`

#### 改 digital twin arm sync timeout
- `virtual_env.sync.arm.timeout_s`
- `virtual_env.sync.request_timeout_s`

用途：
- 遠端 0422 API 太慢時可以稍微放寬

#### 開關 scene object sync
- `virtual_env.sync.objects.enabled`
- `virtual_env.sync.objects.sync_on_start`
- `virtual_env.sync.objects.sync_on_reload`
- `virtual_env.sync.objects.clear_before_sync`

用途：
- 把本地物件設定同步到 0422 `/object_pose`
- 如果你只想同步手臂、不想碰虛擬物件，就把它關掉
- `clear_before_sync: true` 會先呼叫 `/clear_object_poses` 再重送全部 mapping

#### 改 scene object sync 的座標語義
- `virtual_env.sync.objects.coordinate_frame`
- `virtual_env.sync.objects.use_pick_pose_as_object_pose`
- `virtual_env.sync.objects.use_pick_rz_as_yaw`
- `virtual_env.sync.objects.default_pick_z_offset_mm`

建議：
- 目前預設用 `delta_xyz_mm`
- 位置會優先用每個物件 `fixed_poses.pick`
- `position[2]` 會用 `pick_z - pick_z_offset_mm` 推估物體 support z

#### 改 local object key 對到 0422 的 target 名稱
- `virtual_env.sync.objects.mappings`

例子：
```yaml
virtual_env:
  sync:
    objects:
      mappings:
        trapezoid:
          target: "unnamed1_red"
        tweezers:
          target: "forcept"
```

用途：
- 0422 的類別名稱和本地 repo 不完全一樣時，在這裡對齊
- 例如：
  - `trapezoid -> unnamed1_red`
  - `scissors -> shears`
  - `butter_knife -> butterknife`
  - `tweezers -> forcept`

#### 直接覆寫單一物件的虛擬場景位置
- `virtual_env.sync.objects.mappings.<object>.position`
- `virtual_env.sync.objects.mappings.<object>.coordinate_frame`
- `virtual_env.sync.objects.mappings.<object>.yaw_deg`

用途：
- 如果你不想用 `fixed_poses.pick` 推估，可以直接手填要送到 0422 的物件位置

## 9. Claw Cam / 相機 / YOLO

檔案：`config/demo_config.yaml`

### 你想達成的目的

#### 改 claw camera index
- `cameras.claw.source`

#### 改 claw cam 延遲與畫質
- `cameras.claw.performance_profile`

可選：
- `quality`
- `balanced`
- `low_latency`

#### 微調 claw profile
- `cameras.claw.profiles.<profile>.capture_w`
- `stream_w`
- `stream_h`
- `infer_w`
- `infer_h`
- `stream_fps`
- `jpeg_quality`
- `infer_interval_s`

建議：
- 很卡：先切 `low_latency`
- 想看清楚：用 `balanced` 或 `quality`

#### 改 claw YOLO 模型
- `cameras.claw.model_path`
- `cameras.claw.conf`
- `cameras.claw.enable_yolo`

#### 改 RealSense 相機開關
- `cameras.cam1.enabled`
- `cameras.cam2.enabled`
- `cameras.cam1.enable_depth`
- `cameras.cam2.enable_depth`

## 10. Arm / Gripper / Modbus 網路

### 10.1 改 gripper 絕對位置模式的速度

檔案：`config/demo_config.yaml`

#### 你想達成的目的

#### 讓全開比較快
- `gripper.open_step_ticks`
- `gripper.open_step_delay_s`

#### 讓夾取比較慢、比較安全
- `gripper.close_step_ticks`
- `gripper.close_step_delay_s`

#### 切換成分段移動或直接跳目標值
- `gripper.position_move_mode`

可選：
- `"stepped"`
- `"direct"`

建議：
- demo / 真機夾取：`"stepped"`
- 如果你只是想快速測 API：`"direct"`

用途：
- 這只影響 `Phase Replay` / `set_position` 這類絕對位置控制
- 它不是 AGX `command=c/o` 的 delay，而是把目標位置拆成很多小步去走

### 9.1 Demo 實際連線優先順序

檔案：`config/demo_config.yaml`

#### 改手臂連線候選位址
- `arm.connections`

#### 改 gripper API 候選位址
- `gripper.endpoints`

### 9.2 Modbus 暫存器與命令碼

檔案：`config/modbus_config.yaml`

這份通常不要亂改，除非你在對照手冊。

### 你可能會動到的地方

#### 改 home / stop 命令碼
- `commands.home`
- `commands.motion_stop`

#### 改 servo / pose / speed register
- `registers.*`

#### 改 GO 目標座標系 / 插補模式
- `motion.move_mode`

用途：
- `3`：Joint/ACS mode，這是 `weekly_route_test.py` / `weekly_maintenence.py` 目前使用的設定
- `0`：World/MCS Cartesian mode，可用於實驗較直覺的 XYZ 走法，但不等於 weekly 腳本
- 如果要完全對齊 weekly 腳本，這裡保持 `3`

#### 改 default speed
- `motion.default_speed_percent`

#### 確認 speed register 真的有被控制器吃到
- `motion.verify_speed_write`

用途：
- 設成 `true` 時，每次 move 前會寫入 mode/speed，接著讀回 register
- 如果 terminal 顯示 `Motion config OK: mode=3 speed=60% override=100.0%`，代表 Modbus 速度暫存器與全域 override 都吃到了
- 如果顯示 `readback mismatch`，代表控制器沒有照我們寫入的值更新，下一步要查暫存器或控制器狀態

#### 設定全域 Robot Speed Override
- `registers.robot_speed_override`
- `motion.set_robot_speed_override`
- `motion.robot_speed_override_percent`

用途：
- 手冊的 `0x0246` 是 Robot Speed Override，單位是 `0.1%`
- `robot_speed_override_percent: 100` 會寫入 `1000`
- 如果這個全域倍率被控制器或 DRAStudio 設低，`0x0324` 寫 100% 也會看起來很慢

#### 查手冊後新增的 GO 加速度 / 姿態 / Frame
- `registers.acceleration`
- `registers.target_posture`
- `registers.user_frame`
- `registers.tool_frame`
- `motion.set_acceleration`
- `motion.acceleration_raw`
- `motion.set_target_posture`
- `motion.target_posture`
- `motion.set_frames`
- `motion.user_frame`
- `motion.tool_frame`

用途：
- 手冊裡 `0x0324` 只是 GO speed `%`
- 手冊另有 `0x030A ACC`，單位是 raw controller unit，這很可能影響「顯示 100% 但實際加速很慢」
- 手冊 GO 範例也會設定 `0x033D posture`、`0x033C UserFrame`、`0x033F ToolFrame`
- 目前預設只讀回這些值，不主動寫入，避免一口氣改變真機規劃行為

建議現場測法：
```yaml
motion:
  set_acceleration: true
  acceleration_raw: 1000
```

如果速度有明顯改善，再逐步提高或降低 `acceleration_raw`。如果手臂動作變突兀或不安全，立刻改回：
```yaml
motion:
  set_acceleration: false
```

進階測試：
- `tools/trapezoid_weekly_phase_test.py` 支援 `--acc-raw`、`--posture`、`--user-frame`、`--tool-frame`
- 可以先用單獨腳本測低階 Modbus 行為，再決定要不要放回 dashboard

#### 改實際送到手臂的速度上限
- `safety.max_speed_percent`

用途：
- 這是底層 `ArmController.move_to()` 的最後速度上限
- 如果 phase YAML 寫 `70`，但 terminal 顯示 `@ 50% speed`，通常就是這裡被設成 `50`
- 依手冊 `0x0324` 的 GO speed 合理範圍是 `1-100%`，不建議設超過 100
- 改完這份通常需要重開後端，因為低階 Modbus controller 可能已經載入舊設定

注意：
- 如果不是在對照手臂手冊，不建議直接改這份

## 11. 常見目標對照表

### 我想讓「紅色」不要再直接等於梯形
- 改 `config/nlu_aliases.yaml`
- 刪掉：
```yaml
phrase_map:
  "紅色": "trapezoid"
```

### 我想讓「梯型」也能辨成梯形
- 改 `config/nlu_aliases.yaml`
- 保留：
```yaml
global_normalization:
  "梯型": "梯形"
```

### 我想讓「小湯匙」一定指向 coffee scoop
- 改 `config/nlu_aliases.yaml`
- 保留：
```yaml
phrase_map:
  "小湯匙": "coffee_scoop"
```

### 我想讓 UI 更乾淨，錄完後不要看到 teach
- 改 `config/demo_config.yaml`
```yaml
modules:
  teach:
    enabled: false
    show_in_ui: false
```

### 我想讓 claw cam 更順
- 改 `config/demo_config.yaml`
```yaml
cameras:
  claw:
    performance_profile: "low_latency"
```

### 我想讓 tactile 圖不要被固定 Y 軸卡死
- 改 `config/demo_config.yaml`
```yaml
sensor_api:
  auto_range: true
  auto_range_padding_ratio: 0.08
  min_range_span: 300
```

### 我想讓數位雙生更即時
- 改 `config/demo_config.yaml`
```yaml
virtual_env:
  desired_views: ["wrist"]
  sync:
    min_interval_s: 0.15
    request_timeout_s: 0.5
    arm:
      mode: "delta_raw"
      timeout_s: 0.15
```

### 我想讓 Ready 慢一點或快一點
- 改 `config/demo_config.yaml`
```yaml
ready_motion:
  speed_percent: 40
```

### 我想讓 fixed pick 更果斷
- 改 `config/demo_config.yaml`
```yaml
speed:
  fast_percent: 70
  slow_percent: 25
```

## 12. 建議修改順序

如果你要現場快速調整，建議順序是：

1. 先改 `config/nlu_aliases.yaml`
2. 再改 `config/voice_config.yaml`
3. 再改 `config/demo_config.yaml`
4. 最後才碰 `config/modbus_config.yaml`

原因：
- NLU mapping 最常改，也最安全
- ASR 次之
- demo 動作設定再來
- Modbus 最底層，風險最高

## 13. 修改後怎麼生效

現在 UI 的 `Quick Pick` 面板有一顆 `Reload Config` 按鈕。  
大部分日常調整可以先這樣做：

1. 改 YAML
2. 按 `Reload Config`
3. 看 log 確認 `Runtime config reloaded`

### 哪些通常可以直接 Reload
- `config/demo_config.yaml`
  - `speed`
  - `ready_motion`
  - `home_routing`
  - `modules`
  - `teach`
  - `trajectory`
  - `sensor_api`
  - `virtual_env`
- `config/nlu_aliases.yaml`
- `config/objects.yaml`
- `config/speech_prompts.yaml`
- `config/voice_config.yaml`

用途：
- NLU mapping
- UI 顯示開關
- tactile 圖表參數
- digital twin sync 參數
- teach / phase replay 參數
- Offline ASR 的設定

注意：
- Offline ASR 在 `Reload Config` 後，會在下一次離線辨識時重新建立

### 哪些改完通常還是建議重啟後端
- `config/demo_config.yaml`
  - `cameras.*.source`
  - 某些相機硬體初始化相關欄位
- `config/modbus_config.yaml`
  - register / command / motion 底層定義

原因：
- 這些設定牽涉到已經開著的 camera / controller runtime
- 熱重載只會更新高層 config，不保證把底層硬體連線完全重建

### 最保險的做法
如果你改的是相機來源、Modbus 底層命令，或 reload 後體感不對，還是建議：

1. 停掉現在的 `tools/voice_pick_demo.py`
2. 重新啟動
3. 瀏覽器重新整理

如果只是前端顯示不更新，建議再做一次 `Ctrl+F5`。
