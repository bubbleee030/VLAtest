import customtkinter
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import queue
import threading
import time
import serial
import sys
import socket
import requests

url = "http://192.168.1.100:5001/get_sensor"

print("開始監聽感測器資料... (按 Ctrl+C 停止)")

class Receiver:
    def __init__(self, data_queue):
        self.data_queue = data_queue
        
    def receive_data(self):
        """監聽來自 AGX 廣播的數據"""
        try:
            while True:
                try:
                    # 發送請求獲取資料
                    response = requests.get(url, timeout=2) # 加上 timeout 避免網路卡住
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data["status"] == "success":
                            v1 = data.get("analog_value1", 0)
                            v2 = data.get("analog_value2", 0)
                            v3 = data.get("analog_value3", 0)
                            if self.data_queue.full():
                                self.data_queue.get_nowait()
                            self.data_queue.put((v1, v2, v3))
                        else:
                            print(f"AGX 發生錯誤: {data['message']}")
                    else:
                        print(f"HTTP 錯誤碼: {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"連線失敗: {e}")
                    
                # 決定你要多快去要一次資料 (例如 0.1 秒要一次)
                time.sleep(0.05) 
                
        except KeyboardInterrupt:
            print("\n已停止讀取。")
        
# --- 繪圖核心類別 ---
class StatusPlot:
    def __init__(self, parent, data_queue, on_display):
        self.on_display = on_display
        self.data_queue = data_queue
        
        # 僅儲存單一數據的歷史紀錄
        self.histories = [
            [0 for _ in range(self.on_display)], # Data 1
            [0 for _ in range(self.on_display)], # Data 2
            [0 for _ in range(self.on_display)]  # Data 3
        ]
        self.x_axis = [i for i in range(self.on_display)]

        # 建立 4 個子圖
        self.fig, self.axes = plt.subplots(nrows=3 ,ncols=1, figsize=(8, 9))
        self.lines = []
        
        colors = ["red", "blue", "green"]
        titles = ["Sensor 1", "Sensor 2", "Sensor 3"]

        # 初始化所有圖表
        for i in range(3):
            if i < 2:
                self.axes[i].get_xaxis().set_visible(False)
            
            # 每個圖表先畫上一條紅線
            line, = self.axes[i].plot(self.x_axis, self.histories[i], color=colors[i])
            self.lines.append(line)
            
            # 預設 Y 軸範圍
            self.axes[i].set_ylim(0, 1100) 
            self.axes[i].set_title(titles[i], fontsize=10)

        self.fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True, padx=10, pady=10)

    def update_plot(self):
        """只更新第一個圖表的數據"""
        while True:
            if not self.data_queue.empty():
                data_tuple = self.data_queue.get()
                
                for i in range(3):
                    # 更新對應的歷史紀錄
                    self.histories[i].append(data_tuple[i])
                    if len(self.histories[i]) > self.on_display:
                        self.histories[i].pop(0)
                
               
                    self.lines[i].set_ydata(self.histories[i])
                # 重新繪製畫布
            self.canvas.draw_idle()
            
            time.sleep(0.01)

# --- 主程式 ---
def main():
    root = customtkinter.CTk()
    root.title("Arduino Single Channel Monitor")
    root.geometry("800x800")
    customtkinter.set_appearance_mode('light')

    # 設定 Queue
    data_queue = queue.Queue(maxsize=50)

    # 1. 建立圖表 (顯示最近 100 筆數據)
    plot_mgr = StatusPlot(root, data_queue, on_display=100)

    # 2. 建立 Arduino 讀取器 (請確認你的 Port)
    arduino = Receiver(data_queue)

    # 3. 啟動執行緒
    t_read = threading.Thread(target=arduino.receive_data, daemon=True)
    t_read.start()
    
    t_plot = threading.Thread(target=plot_mgr.update_plot, daemon=True)
    t_plot.start()

    root.protocol("WM_DELETE_WINDOW", sys.exit)
    root.mainloop()

if __name__ == "__main__":
    main()