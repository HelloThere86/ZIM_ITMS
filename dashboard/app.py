import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
import numpy as np
from streamlit_option_menu import option_menu

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="ITMS - ZRP Dashboard", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS FOR FIGMA-LIKE STYLING ---
st.markdown("""
    <style>
    /* KPI Card Styling */
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 5% 5% 5% 10%;
        border-radius: 10px;
        box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.05);
    }
    /* Hide top header line */
    header {visibility: hidden;}
    /* Main background color */
    .stApp {background-color: #f8f9fa;}
    </style>
""", unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
DB_PATH = "../database/itms_production.db"
EVIDENCE_DIR = "evidence"

def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def fetch_data(query, params=()):
    conn = get_db_connection()
    if conn:
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    return pd.DataFrame()

def execute_query(query, params=()):
    conn = get_db_connection()
    if conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        conn.close()

# --- FETCH KPI METRICS ---
df_all = fetch_data("SELECT * FROM violation")
if not df_all.empty:
    total_flagged = len(df_all[df_all['status'] == 'Pending'])
    total_approved = len(df_all[df_all['status'].isin(['Approved', 'AutoApproved'])])
    total_rejected = len(df_all[df_all['status'] == 'Rejected'])
else:
    total_flagged = total_approved = total_rejected = 0

# --- SIDEBAR NAVIGATION (Matches Figma) ---
with st.sidebar:
    st.markdown("<h2 style='color: white; text-align: center;'>🔒 ITMS</h2>", unsafe_allow_html=True)
    st.markdown("---")
    
    selected = option_menu(
        menu_title=None,
        options=["Dashboard", "Flagged Violations", "Evidence Search", "System Health", "Audit Trail", "Config"],
        icons=["grid", "flag", "search", "activity", "receipt", "gear"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "gray", "font-size": "18px"}, 
            "nav-link": {"font-size": "15px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
            "nav-link-selected": {"background-color": "#4A5568", "color": "white", "icon-color": "white"},
        }
    )

# ==========================================
# PAGE 1: DASHBOARD OVERVIEW
# ==========================================
if selected == "Dashboard":
    st.header("Dashboard Overview")
    
    # KPI Row
    col1, col2, col3 = st.columns(3)
    col1.metric("Flagged", f"{total_flagged}", "Total Violations", delta_color="off")
    col2.metric("Approved", f"{total_approved}", "Traffic Violations", delta_color="off")
    col3.metric("Rejected", f"{total_rejected}", "Total", delta_color="off")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Navigation Cards Row 1
    c1, c2 = st.columns(2)
    with c1:
        with st.container():
            st.markdown("### 🚩 Flagged Violations")
            st.write("Review and process flagged traffic violations")
            st.markdown(f"## {total_flagged}")
    with c2:
        with st.container():
            st.markdown("### 🔍 Evidence Search")
            st.write("Search and export violation evidence")
            st.markdown("## ➔")
            
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Navigation Cards Row 2
    c3, c4 = st.columns(2)
    with c3:
        with st.container():
            st.markdown("### 📈 System Health")
            st.write("Monitor system status and alerts")
            st.button("All Systems Operational", disabled=True)
    with c4:
        with st.container():
            st.markdown("### 📑 Audit Trail")
            st.write("View system activity and user actions")
            st.write("🟢 2 Active Users • Last activity: Just now")

# ==========================================
# PAGE 2: FLAGGED VIOLATIONS
# ==========================================
elif selected == "Flagged Violations":
    st.header("Flagged Violations")
    
    # KPI Row
    col1, col2, col3 = st.columns(3)
    col1.metric("Flagged", f"{total_flagged}", "Total Violations")
    col2.metric("Approved", f"{total_approved}", "Traffic Violations")
    col3.metric("Rejected", f"{total_rejected}", "Traffic Violations")
    
    st.markdown("---")
    
    # Data Table
    df_flagged = fetch_data("SELECT violation_id as ID, plate_number, intersection_id, timestamp as TIME, confidence_score as CONFIDENCE, status as STATUS FROM violation ORDER BY timestamp DESC")
    
    if not df_flagged.empty:
        # Formatting for UI
        df_flagged['CONFIDENCE'] = df_flagged['CONFIDENCE'].apply(lambda x: f"{x:.0f}%")
        # Replace intersection ID with mock name for display
        df_flagged['INTERSECTION'] = "Kirkman / Harare Dr" 
        
        st.dataframe(df_flagged[['ID', 'plate_number', 'INTERSECTION', 'TIME', 'CONFIDENCE', 'STATUS']], use_container_width=True, hide_index=True)
        
        st.markdown("### Review Action Panel")
        action_id = st.selectbox("Select ID to Review", df_flagged[df_flagged['STATUS'] == 'Pending']['ID'].tolist())
        
        if action_id:
            case_data = fetch_data("SELECT * FROM violation WHERE violation_id=?", (action_id,)).iloc[0]
            col_img, col_act = st.columns(2)
            with col_img:
                img_path = os.path.join(EVIDENCE_DIR, str(case_data['image_path']))
                if os.path.exists(img_path):
                    st.image(img_path, use_container_width=True)
                else:
                    st.error("Image missing from server.")
            with col_act:
                st.write(f"**Plate:** {case_data['plate_number']}")
                st.write(f"**AI Note:** {case_data['review_note']}")
                if st.button("Approve (Issue Fine)", type="primary"):
                    execute_query("UPDATE violation SET status='Approved' WHERE violation_id=?", (action_id,))
                    st.success("Approved!")
                    st.rerun()
                if st.button("Reject (Exempt)"):
                    execute_query("UPDATE violation SET status='Rejected' WHERE violation_id=?", (action_id,))
                    st.info("Rejected.")
                    st.rerun()
    else:
        st.info("No violations logged yet.")

# ==========================================
# PAGE 3: EVIDENCE SEARCH
# ==========================================
elif selected == "Evidence Search":
    st.header("Evidence Search")
    
    with st.form("search_form"):
        st.write("Search Filters:")
        c1, c2, c3 = st.columns(3)
        plate_search = c1.text_input("Plate Number", placeholder="Enter plate number")
        inter_search = c2.selectbox("Intersection",["All", "Kirkman / Harare Dr", "Samora Ave", "Julius Nyerere Rd"])
        date_search = c3.date_input("Date Range",[])
        
        submit = st.form_submit_button("🔍 Search")
        
    if submit:
        query = f"SELECT violation_id, plate_number, timestamp, status FROM violation WHERE plate_number LIKE '%{plate_search}%'"
        res = fetch_data(query)
        if not res.empty:
            st.dataframe(res, use_container_width=True, hide_index=True)
            st.button("📥 Export Evidence Package")
        else:
            st.warning("No evidence found matching those filters.")

# ==========================================
# PAGE 4: SYSTEM HEALTH
# ==========================================
elif selected == "System Health":
    st.header("System Health")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", "320", "Traffic Violations")
    c2.metric("Flagged", "45", "Flagged Violations")
    c3.metric("Network", "⚠️ Offline", "Edge Mode Active", delta_color="inverse")
    
    st.markdown("---")
    c_chart, c_alerts = st.columns([2, 1])
    
    with c_chart:
        st.write("**Traffic Violations Trend**")
        # Dummy data for chart to match mockup
        chart_data = pd.DataFrame(np.random.randn(20, 1).cumsum() + 150, columns=['Violations'])
        st.line_chart(chart_data)
        
    with c_alerts:
        st.write("**Alerts**")
        st.error("❗ Camera 3 Offline")
        st.warning("⚠️ Low Storage Space")
        st.error("❗ Network Error (Sync Paused)")

# ==========================================
# PAGE 5: AUDIT TRAIL
# ==========================================
elif selected == "Audit Trail":
    st.header("Audit Trail")
    st.write("**2 Active Users** • Last Activity: Today 11:30 AM")
    
    # Mock data to match your figma design
    audit_data = pd.DataFrame({
        "TIMESTAMP":["02/22/2026 10:14", "02/21/2026 15:35", "02/21/2026 09:00"],
        "USER":["J.Dube", "A.Ncube", "System"],
        "ACTION": ["Approved", "UPDATE CONFIG", "Sync"],
        "ENTITY": ["Violation V-101", "System Config", "Database"],
        "DETAILS":["Status changed to Approved", "Clip Duration set to 15s", "Synced 42 offline records"]
    })
    st.dataframe(audit_data, use_container_width=True, hide_index=True)

# ==========================================
# PAGE 6: CONFIGURATION
# ==========================================
elif selected == "Config":
    st.header("⚙️ System Configuration")
    
    st.write("### Camera Settings")
    st.selectbox("Clip Duration",["10s", "15s", "30s"], index=1)
    st.selectbox("Image Quality", ["Standard", "High", "Ultra"], index=1)
    
    st.write("### Detection Settings")
    st.number_input("Auto-Flag Threshold (%)", min_value=50, max_value=100, value=96)
    st.checkbox("Enable Night Mode (Enhanced IR detection)", value=True)
    
    st.write("### Storage Settings")
    st.selectbox("Retention Period",["30 days", "60 days", "90 days", "Indefinite"], index=1)
    
    st.markdown("---")
    col1, col2 = st.columns([8, 1])
    col2.button("Save Changes", type="primary")