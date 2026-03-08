import cv2
import numpy as np
import easyocr
import sqlite3
import os
import time
from datetime import datetime
from ultralytics import YOLO
import tensorflow as tf

# --- CONFIGURATION ---
VIDEO_SOURCE = 'test_traffic.mp4' # Change to 0 for Webcam
MODEL_PATH = 'zimbabwe_traffic_model.h5'
DB_PATH = '../database/itms_production.db'
CONFIDENCE_THRESHOLD = 96.0 # Strict threshold for exemption

print("Initializing ITMS Edge AI...")

# 1. Load Models
print("... Loading YOLOv8 ...")
yolo_model = YOLO('yolov8n.pt') 

print("... Loading Custom Exemption CNN ...")
if os.path.exists(MODEL_PATH):
    cnn_model = tf.keras.models.load_model(MODEL_PATH)
    classes = ['ambulance', 'civilian_car', 'fire_truck', 'police_car']
else:
    print(f"ERROR: {MODEL_PATH} not found! Please download it from Drive.")
    exit()

print("... Loading OCR Engine ...")
reader = easyocr.Reader(['en'], gpu=False) # Set gpu=True if you have NVIDIA CUDA

# 2. Database Logger
def log_violation(plate, v_class, conf, frame_img):
    """Logs violation to SQLite Database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save the image snapshot
        img_filename = f"violation_{int(time.time())}.jpg"
        img_path = os.path.join("../dashboard/evidence", img_filename)
        os.makedirs("../dashboard/evidence", exist_ok=True)
        cv2.imwrite(img_path, frame_img)
        
        # Determine Status
        # If AI says Emergency but low confidence -> REVIEW
        # If AI says Civilian -> APPROVED (Auto-fine)
        status = 'Pending'
        decision = 'LoggedOnly'
        
        if v_class == 'civilian_car':
            status = 'AutoApproved'
            decision = 'Auto'
        elif conf < CONFIDENCE_THRESHOLD:
            status = 'Pending' # Flag for human review
            decision = 'Flagged'
        else:
            status = 'Rejected' # Exemption granted automatically
            decision = 'Auto'

        c.execute('''INSERT INTO violation 
                     (plate_number, timestamp, image_path, confidence_score, decision_type, status, review_note) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (plate, timestamp, img_filename, float(conf), decision, status, f"Detected Class: {v_class}"))
        
        conn.commit()
        conn.close()
        print(f"💾 [DATABASE] Logged: {plate} | {v_class} | {status}")
        
    except Exception as e:
        print(f"❌ Database Error: {e}")

# 3. Process Video
cap = cv2.VideoCapture(VIDEO_SOURCE)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Virtual Loop Line (70% down the screen)
line_y = int(height * 0.7)

print("System Online. Processing Video...")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    # Draw Red Line
    cv2.line(frame, (0, line_y), (width, line_y), (0, 0, 255), 3)
    cv2.putText(frame, "ENFORCEMENT ZONE", (10, line_y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

    # YOLO Detection
    results = yolo_model(frame, verbose=False)
    
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls = int(box.cls[0])
        
        # 2=Car, 3=Motorcycle, 5=Bus, 7=Truck
        if cls in [2, 3, 5, 7]:
            
            # Check for Line Crossing (Bottom of car hits line)
            if y2 > line_y and y2 < line_y + 10: # Only trigger once per car
                
                # --- EXEMPTION CHECK ---
                car_crop = frame[y1:y2, x1:x2]
                if car_crop.size == 0: continue
                
                # Preprocess for CNN
                img_resized = cv2.resize(car_crop, (150, 150))
                img_array = tf.expand_dims(img_resized / 255.0, 0)
                
                # Predict
                preds = cnn_model.predict(img_array, verbose=0)
                score = tf.nn.softmax(preds[0])
                pred_class = classes[np.argmax(score)]
                confidence = 100 * np.max(score)
                
                # --- OCR CHECK ---
                plate_text = "Unknown"
                try:
                    ocr_res = reader.readtext(car_crop)
                    if ocr_res:
                        plate_text = ocr_res[0][1].upper() # Get text
                except:
                    pass
                
                # Visual Feedback
                color = (0, 0, 255) # Red for civilian
                if pred_class != 'civilian_car':
                    color = (0, 255, 0) # Green for Emergency
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                cv2.putText(frame, f"{pred_class.upper()} {confidence:.1f}%", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # Log to DB
                log_violation(plate_text, pred_class, confidence, car_crop)

    cv2.imshow("ITMS Camera Feed", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()