import tensorflow as tf
from tensorflow.keras.preprocessing import image
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
from tkinter import filedialog
import os


# --- STEP 6: LIVE TEST WITH HUMAN REVIEW FALLBACK (LOCAL VERSION) ---

# 1. Hide the background Tkinter window
root = tk.Tk()
root.withdraw()
# Make sure the dialog pops up on top of other windows
root.attributes('-topmost', True) 

print("WAITING FOR PANEL TO SELECT AN IMAGE...")

# 2. Open a native file explorer dialog
file_path = filedialog.askopenfilename(
    title="Select an Image for Classification Test",
    filetypes=[("Image Files", "*.jpg *.jpeg *.png")]
)

if not file_path:
    print("❌ No file selected. Exiting.")
else:
    print(f"File selected: {os.path.basename(file_path)}")
    
    # Optional: If you saved your model to a file, uncomment the line below to load it
    # model = tf.keras.models.load_model('my_traffic_model.keras')
    print(f"File selected: {os.path.basename(file_path)}")
    
    # LOAD YOUR SPECIFIC LOCAL MODEL
    print("Loading zimbabwe_traffic_model.h5... Please wait.")
    model = tf.keras.models.load_model('zimbabwe_traffic_model.h5')

    # 3. Process the image
    img = image.load_img(file_path, target_size=(150, 150))
    img_array = image.img_to_array(img)
    img_array = tf.expand_dims(img_array, 0)

    # 4. Make the prediction
    predictions = model.predict(img_array)
    score = tf.nn.softmax(predictions[0])

    # NOTE: Ensure your class_names list matches your training script
    # If train_ds is not in this script, define them manually:
    class_names = ['ambulance', 'civilian_car', 'fire_truck', 'police_car']
    #class_names = train_ds.class_names 
    
    predicted_class = class_names[np.argmax(score)]
    confidence = 100 * np.max(score)

    # 5. Display the image
    plt.figure(figsize=(4, 4))
    plt.imshow(image.load_img(file_path))
    plt.title(f"Prediction: {predicted_class.upper()}")
    plt.axis('off')
    plt.show(block=False) # block=False lets the console text print immediately
    plt.pause(0.1)

    # 6. Output the results
    print("-" * 50)
    print(f"AI PREDICTION: {predicted_class.upper()}")
    print(f"CONFIDENCE:    {confidence:.2f}%")
    print("-" * 50)

    # --- THE INNOVATION: HUMAN REVIEW LOGIC ---
    CONFIDENCE_THRESHOLD = 75.0  

    if confidence < CONFIDENCE_THRESHOLD:
        print(f"⚠️ WARNING: LOW CONFIDENCE - {confidence:.2f}%")
        print("   ACTION:  FLAGGED FOR HUMAN OPERATOR REVIEW.")
        print("   STATUS:  Sent to Dashboard Queue.")

    elif predicted_class == 'civilian_car':
        print("🚗 STATUS:  CIVILIAN VEHICLE")
        print("   ACTION:  AUTOMATED FINE ISSUED.")

    else:
        print(f"🚨 STATUS:  EMERGENCY VEHICLE ({predicted_class.upper()})")
        print("   ACTION:  EXEMPT FROM FINE. Allowed to pass.")
    print("-" * 50)
    
    # Keep the plot open until the user closes it
    plt.show()