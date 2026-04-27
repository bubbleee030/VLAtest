# Digital Twin Alignment Guide

這份文件是給目前這個 repo 用的「真實世界畫面 vs 數位雙生畫面對齊」操作指南。

你現在這套系統要分成兩個層次看：

1. **手臂對齊**
   - 真實手臂的位置，要能在 0422 虛擬環境裡跑到接近同一個位置
2. **畫面對齊**
   - 虛擬環境顯示的 `d435_left / d435_right / wrist` 視角，要跟 realworld 相機看起來接近

先講最重要的結論：

- 目前 repo 原本是用本地 `mm -> m + offset` 的粗轉換去推虛擬手臂
- 你學長給的 REST API 文件裡，0422 已經有比較正式的：
  - `POST /delta_pose_convert`
  - `POST /ee_move_delta_raw`
- 所以現在建議優先使用 **`delta_raw` sync mode**

---

## 1. 現在已經改好的地方

檔案：`config/demo_config.yaml`

現在 `virtual_env.sync.arm` 已經新增：

```yaml
virtual_env:
  sync:
    arm:
      mode: "delta_raw"
      delta_units: "raw_counts"
      include_ee_pose: false
```

意思是：

- `mode: "delta_raw"`
  - 走 0422 的 `/ee_move_delta_raw`
- `delta_units: "raw_counts"`
  - 直接用 Modbus 讀到的原始 controller counts
  - 這比我們自己先轉成 mm 再外插通常更接近學長那邊的轉換鏈

如果你想切回舊模式：

```yaml
virtual_env:
  sync:
    arm:
      mode: "direct_ee_move"
```

---

## 2. 先做哪一種對齊

建議順序：

1. **先對齊 arm anchor**
2. **再觀察虛擬視角**
3. **最後才處理物件 scene alignment**

不要一開始就同時動很多東西，不然你會不知道是：

- arm 轉換錯
- view camera 不對
- 還是虛擬物件位置根本沒同步

---

## 3. 第一關：Ready Anchor 對齊

你要先確認這兩邊的 ready 是同一件事。

本地真實手臂 ready：
- `config/demo_config.yaml`
- `ready_pose: [490127, 0, 425027, 179999, 0, 0]`

0422 REST 文件也有寫：
- `GET /ready_pose`
- `POST /ready_pose`
- 這組 ready 對應同一個 Delta ready anchor

### 建議操作

1. 真實手臂按 `Ready`
2. 確認本地 arm monitor 真的到：
   - `490.127, 0, 425.027, 179.999, 0, 0`
3. 看數位雙生面板裡的 `Arm Sync`
   - 應該會顯示 `delta_raw | ok ...`
4. 看虛擬畫面中的手臂末端，是否在 ready 附近

### 如果 ready 都對不齊

先不要調 view，也不要調 object。
先檢查：

- `virtual_env.base_url`
- 0422 server 是否真的在跑
- Digital Twin Data 面板是不是有 `Connected`
- `mode` 是不是 `delta_raw`

---

## 4. 第二關：Arm Sync 模式怎麼選

### 模式 A：`delta_raw`（建議）

用途：
- 讓 0422 自己用它的 `Delta -> Sim` 轉換

優點：
- 比本地粗 offset 外插更符合學長那套服務
- 更接近 REST 文件的正式用法

缺點：
- 文件有提到：
  - 大 lateral offset 還是可能不穩
  - 有些情況會回 `409`

### 模式 B：`direct_ee_move`

用途：
- 繼續用本地 `mm_to_m_scale + offsets + yaw_offset` 去推 `/ee_move`

優點：
- 你可以用 `Calibrate Current` 直接校正
- 對單一 anchor 微調很方便

缺點：
- 本質上是本地粗轉換
- 更容易出現「看起來差不多，但不是 0422 正式語義」的情況

### 什麼時候切回 `direct_ee_move`

如果你遇到：
- `delta_raw` 一直 `409`
- remote monitor 沒在跑
- 或 ready 可以，但其他位置一直漂很大

可以先切回：

```yaml
virtual_env:
  sync:
    arm:
      mode: "direct_ee_move"
```

然後再用 UI 的：
- `Calibrate Current`
- `Reset Calib`

去微調目前 anchor。

---

## 5. 第三關：畫面為什麼還可能看起來不對

就算 arm 對了，畫面還是可能不對，因為還有兩個問題：

### 5.1 虛擬 camera view 不一定和真實 camera 外參一樣

目前顯示的是：
- `d435_left`
- `d435_right`
- `wrist`

設定在：

```yaml
virtual_env:
  desired_views: ["d435_left", "d435_right", "wrist"]
```

這只能保證「看同名視角」，
不能保證 0422 裡的 camera pose 已經和你的 real camera 外參完全一致。

### 5.2 虛擬物件位置沒有自動跟真實物件同步

這個 repo 現在已經同步：
- arm
- gripper
- **scene object（可選）**

scene object sync 目前走的是：
- `config/objects.yaml` 每個物件的 `fixed_poses.pick`
- 再用 `pick_z_offset_mm` 推估物體 support z
- 最後送到 0422 的 `/object_pose`

所以如果你看到：
- 虛擬手臂大致正確
- 虛擬物件還是偏掉一些

那通常不是手臂 sync 壞掉，而是：
- local object key 對 remote target 名稱沒對好
- 或 `fixed_poses.pick` 本身就不是物件幾何中心
- 或需要在 `virtual_env.sync.objects.mappings.<object>.position` 手調

---

## 6. 什麼叫「真的對齊」

你要把目標拆開看：

### 目標 A：手臂末端位置對齊

判定方式：
- 真實手臂到 ready / 某固定 pose
- 虛擬手臂末端也在相近位置

### 目標 B：手腕視角大致對齊

判定方式：
- wrist view 中，手臂與工作區相對關係接近 realworld

### 目標 C：場景物件也對齊

判定方式：
- 桌上的 board / spoon / trapezoid 在虛擬畫面中也在差不多位置

目前 repo 已經做到：
- A
- 部分 B
- 基礎版 C

但 C 仍然是「用 pick pose 推估」的近似同步，不是相機/深度即時量到的精準 scene reconstruction。

---

## 7. 建議的實測流程

### Step 1
重啟 `tools/voice_pick_demo.py`

### Step 2
確認：

```yaml
virtual_env:
  enabled: true
  sync:
    enabled: true
    arm:
      enabled: true
      mode: "delta_raw"
```

### Step 3
讓真實手臂去 `Ready`

### Step 4
看 UI 的 `Digital Twin Data`

重點看：
- `Connected`
- `Arm Sync`
- `Views`
- `Error`

### Step 5
比對：
- 真實 `Cam1/Cam2/Wrist`
- 虛擬 `d435_left/d435_right/wrist`

先只看：
- 手臂末端位置
- 手腕相對工作區方向

不要先看物件。

### Step 5.5
如果 arm 對了，再確認 scene object sync 有沒有上去：

- `Reload Config` 後看 backend log
- 或手動打：
  - `POST /api/virtual_env/sync_scene_objects`

如果 mapping 有對上，你應該會看到虛擬場景裡：
- `trapezoid -> unnamed1_red`
- `scissors -> shears`
- `butter_knife -> butterknife`
- `tweezers -> forcept`

### Step 6
如果 ready 都不對：

改成：

```yaml
virtual_env:
  sync:
    arm:
      mode: "direct_ee_move"
```

然後用 `Calibrate Current` 對單一 anchor 做微調。

---

## 8. 你現在最常要改的欄位

### 改數位雙生 base URL

檔案：`config/demo_config.yaml`

```yaml
virtual_env:
  base_url: "http://140.127.205.127:8765"
```

### 改 arm sync 模式

```yaml
virtual_env:
  sync:
    arm:
      mode: "delta_raw"
```

或

```yaml
virtual_env:
  sync:
    arm:
      mode: "direct_ee_move"
```

### 改 delta raw 單位

```yaml
virtual_env:
  sync:
    arm:
      delta_units: "raw_counts"
```

如果真的拿不到 raw，再改：

```yaml
delta_units: "mm_deg"
```

### 改虛擬顯示的 view 順序

```yaml
virtual_env:
  desired_views: ["d435_left", "d435_right", "wrist"]
```

---

## 9. 現階段的限制

目前這個 repo 還沒有：

1. 用 realworld 相機/深度即時估物體真實幾何位置後再送 `/object_pose`
2. 自動做 real camera 外參對 sim camera 外參標定
3. 根據 realworld YOLO/深度結果，持續動態更新 scene object

所以如果你要的是「整張畫面幾乎一模一樣」，
下一步一定會需要補：

- scene object sync
- 或 camera extrinsic alignment

---

## 10. 下一步最值得做什麼

如果你現在要的是「先有感對齊」，最值得先做的是：

1. 用 `delta_raw` 把 arm sync 收斂
2. 用 ready anchor 驗證手臂是否對齊
3. 再決定要不要做 scene object sync

如果你要的是「虛擬畫面裡的物件位置更貼近真實桌面」，
現在第一步已經有了：

- `virtual_env.sync.objects.mappings`
- `/object_pose` scene sync

接下來要做的才會是更進一步：
- 用真實相機量物體中心與 yaw
- 再把那個結果持續送進 0422
