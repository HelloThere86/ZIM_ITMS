import streamlit as st
import pandas as pd
import json
import os

# Set page layout
st.set_page_config(page_title="ZRP ITMS Dashboard", layout="wide")

st.title("🚨 ZRP Intelligent Traffic Management System")
st.subheader("Law Enforcement Evidence Vault & Review Queue")

# Path to our simulated database
DB_PATH = "../cv_module/violation_database.json"

def load_data():
    if not os.path.exists(DB_PATH):
        return[]
    with open(DB_PATH, "r") as file:
        return json.load(file)

data = load_data()

if not data:
    st.info("No violations currently logged in the database.")
else:
    # Separate data into High Confidence (Automated) and Low Confidence (Human Review)
    df = pd.DataFrame(data)
    
    tab1, tab2 = st.tabs(["✅ Automated Fines (High Confidence)", "⚠️ Human Review Queue"])
    
    with tab1:
        st.write("### Verified Violations")
        auto_fines = df[df['ai_confidence'] >= 96.0]
        if not auto_fines.empty:
            st.dataframe(auto_fines[['timestamp', 'plate_number', 'vehicle_class', 'ai_confidence']])
        else:
            st.success("No automated fines pending.")

    with tab2:
        st.write("### Requires Manual Verification")
        st.write("The AI flagged these as potential emergencies but confidence was below the 96% legal threshold.")
        review_queue = df[df['ai_confidence'] < 96.0]
        
        for index, row in review_queue.iterrows():
            with st.expander(f"Review Case: {row['timestamp']} - Guessed: {row['vehicle_class']}"):
                col1, col2 = st.columns(2)
                with col1:
                    # In a real app, we show the saved image here
                    st.image("https://via.placeholder.com/400x200.png?text=Traffic+Camera+Capture", caption="Incident Snapshot")
                with col2:
                    st.write(f"**Detected Plate:** {row['plate_number']}")
                    st.write(f"**AI Guess:** {row['vehicle_class']}")
                    st.write(f"**Confidence:** {row['ai_confidence']}%")
                    
                    if st.button(f"Approve as Civilian (Issue Fine) ##{index}"):
                        st.success("Fine Issued.")
                    if st.button(f"Confirm Exemption (Dismiss) ##{index}"):
                        st.info("Case Dismissed. Logged as Emergency.")