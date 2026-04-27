import requests
import keyboard
import time

# ⚠️ 請將這裡換成你 AGX 目前的區域網路 IP
AGX_IP = "192.168.1.100" 
API_URL = f"http://{AGX_IP}:5002/command"

# 你定義的控制按鍵清單
valid_keys = ['v', 'c', 'o', '1', '2', '3', '4', '5', '6', '7']

print(f"🔗 準備連線至 AGX ({API_URL})")
print("🎮 開始監聽鍵盤按鍵... (按下 'x' 退出遙控)")

def send_command(key):
    try:
        # 發送 JSON 格式的指令給 AGX
        response = requests.post(API_URL, json={"action": key}, timeout=1)
        if response.status_code == 200:
            print(f"已發送: {key} -> 回傳位置: {response.json()['current_pos']}")
    except requests.exceptions.RequestException as e:
        print(f"網路連線錯誤: {e}")

try:
    while True:
        # 掃描所有有效按鍵
        for key in valid_keys:
            if keyboard.is_pressed(key):
                send_command(key)
                # 稍微暫停，避免網路請求過於密集而癱瘓伺服器
                # 如果覺得夾爪動得太慢，可以把這個值調小，或把伺服器端的 gripper_speed 調大
                time.sleep(0.05) 
                
        if keyboard.is_pressed('x'):
            print("🛑 停止遙控，關閉系統中...")
            # 傳送停止訊號給 AGX，關閉馬達扭力
            requests.get(f"http://{AGX_IP}:5000/stop")
            break
            
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\n強制退出。")