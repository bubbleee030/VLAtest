import os
from pathlib import Path

import cv2
import threading

YOLO_CONFIG_DIR = Path(__file__).resolve().parent.parent / "data" / "models" / "ultralytics"
YOLO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(YOLO_CONFIG_DIR))

from ultralytics import YOLO

class UVC_Camera_Thread:
    """專門負責背景抓圖的類別，解決影像延遲問題"""
    def __init__(self, src=2):
        self.cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.ret, self.frame = self.cap.read()
        self.running = True
        
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def update(self):
        while self.running:
            if self.cap.isOpened():
                self.ret, self.frame = self.cap.read()

    def read(self):
        return self.ret, self.frame

    def stop(self):
        self.running = False
        self.thread.join()
        self.cap.release()

class Detector:
    """封裝 YOLO 模型與判斷邏輯"""
    def __init__(self, model_path):
        self.model = YOLO(model_path)
        # 這裡定義你所有的合法標籤，包含你之後想加的 chopsticks
        self.valid_labels = [
            'board', 'chopstick', 'coffeespoon', 'knife', 'scissors', 'spatula', 'spoon', 'stick', 'trapezoid', 'tweezer'
        ]

    def get_labels_and_frame(self, frame):
        """辨識畫面並回傳標籤清單與標記後的影像"""
        results = self.model(frame, conf=0.5, verbose=False)
        
        # 取得所有偵測到的標籤
        detected_labels = []
        for box in results[0].boxes:
            label = self.model.names[int(box.cls[0])]
            detected_labels.append(label)
            
        annotated_frame = results[0].plot()
        return detected_labels, annotated_frame

    def check_presence(self, target, detected_list):
        """核心邏輯：判斷目標是否存在並輸出訊息"""
        if target in detected_list:
            print(f"Detected {target}, starting picking sequence.")
            return 1
        else:
            print(f"Did not detect {target}.")
            return 0
