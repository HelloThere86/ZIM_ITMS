import cv2
import numpy as np
import easyocr
import json
import os
from datetime import datetime
from ultralytics import YOLO
import tensorflow as tf

print("Initializing ITMS Edge AI...")

# 1. Load Models
yolo_model = YOLO('yolov8n.pt') # YOLO for car detection
cnn_model = tf.keras.models.load_model('zimbabwe_traffic_model.h5') # Your Custom CNN
reader = easyocr.Reader(['en']) # OCR for plates

classes = ['ambulance', 'civilian_car', 'fire_truck', 'police_car']
DB_PATH = "violation_database.json"

# Initialize JSON DB if it doesn't exist
if not os.path.exists(DB_PATH):
    with open(DB_PATH, "w") as f:
        json.dump([], f)

# 2. Setup Video Stream (Use a traffic video file instead of live webcam)
# REPLACE 'test_traffic.mp4' with a video file when running
cap = cv2.VideoCapture('test_traffic.mp4') 

# Define Virtual Stop Line
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
line_y = int(height * 0.7) if height > 0 else 300

def log_violation(plate_text, vehicle_class, conf):
    with open(DB_PATH, "r") as f:
        data = json.load(f)
    
    data.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "plate_number": plate_text,
        "vehicle_class": vehicle_class,
        "ai_confidence": round(float(conf), 2)
    })
    
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=4)
    print(f"[LOGGED] Plate: {plate_text} | Class: {vehicle_class} | Conf: {conf:.2f}%")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    # Draw Red Light Line
    cv2.line(frame, (0, line_y), (width, line_y), (0, 0, 255), 3)

    # YOLO Detection
    results = yolo_model(frame, verbose=False)
    
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        if int(box.cls[0]) in[2, 3, 5, 7]: # Cars, buses, trucks
            
            # Check if crossing the red line
            if y2 > line_y and y2 < line_y + 15: # Only trigger exactly when crossing
                
                # CROP THE CAR IMAGE for the CNN
                car_crop = frame[y1:y2, x1:x2]
                if car_crop.size == 0: continue
                
                # --- EXEMPTION LOGIC (Your CNN) ---
                img_resized = cv2.resize(car_crop, (150, 150))
                img_array = tf.expand_dims(img_resized / 255.0, 0)
                
                predictions = cnn_model.predict(img_array, verbose=0)
                score = tf.nn.softmax(predictions[0])
                pred_class = classes[np.argmax(score)]
                confidence = 100 * np.max(score)
                
                # --- OCR (Read Plate) ---
                plate_text = "UNKNOWN"
                ocr_result = reader.readtext(car_crop)
                if ocr_result:
                    plate_text = ocr_result[0][1] # Get highest confidence text
                
                # Draw Red Box for Violation
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                
                # Action based on CNN Output
                if pred_class == 'civilian_car' or confidence < 96.0:
                    log_violation(plate_text, pred_class, confidence)
                else:
                    print(f"🚨 EXEMPTION GRANTED: {pred_class.upper()} ({confidence:.2f}%)")

    # Display (Optional: comment out if running on cloud)
    cv2.imshow("ITMS Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()