import cv2
import threading
import sys
from ObjectDetection import UVC_Camera_Thread, Detector

# --- 全域變數，用於執行緒之間的通訊 ---
user_command = None
exit_flag = False

def input_listener():
    """ 專門在背景等待終端機輸入的工人 """
    global user_command, exit_flag
    while not exit_flag:
        # 這個 input 會一直停在這裡等，但不會影響主畫面的顯示
        line = sys.stdin.readline().strip()
        if line.lower() == 'exit' or line.lower() == 'q':
            exit_flag = True
            break
        if line:
            user_command = line

def main():
    global user_command, exit_flag
    
    # 1. 初始化
    camera = UVC_Camera_Thread(src=15)
    detector = Detector("/home/ical/Desktop/finalyolo/yolo12sbest.pt")

    # 顯示可用清單
    print("\n" + "="*30)
    print("系統啟動！可用標籤：", ", ".join(detector.valid_labels))
    print("操作方式：隨時在下方輸入標籤並按 Enter，輸入 'exit' 離開。")
    print("="*30)
    print("你想夾的東西 :")

    # 2. 啟動背景輸入監聽器
    t = threading.Thread(target=input_listener, daemon=True)
    t.start()

    try:
        while not exit_flag:
            ret, frame = camera.read()
            if not ret or frame is None:
                continue

            # 辨識當前畫面
            current_labels, annotated_frame = detector.get_labels_and_frame(frame)
            
            # 即時顯示監控畫面
            cv2.imshow("AMB82 Real-time Monitoring", annotated_frame)

            # 3. 檢查是否有新指令進來 (這就是按下 Enter 的那一瞬間)
            if user_command is not None:
                target = user_command
                user_command = None  # 立即清空指令，確保不重複觸發

                if target in detector.valid_labels:
                    # 在這裡進行判斷邏輯
                    status = detector.check_presence(target, current_labels)
                    
                    if status == 1:
                        # 這裡放夾取程式整合：arm.pick(target) !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                        pass
                else:
                    print(f"提示：標籤 '{target}' 無效或拼錯了。")

            # 視窗必須有的 waitKey
            if cv2.waitKey(1) & 0xFF == ord('q'):
                exit_flag = True

    finally:
        exit_flag = True
        camera.stop()
        cv2.destroyAllWindows()
        print("\n程序已安全關閉。")

if __name__ == "__main__":
    main()