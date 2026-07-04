import streamlit as st
import pandas as pd
from datetime import time
import os

# Set page configurations
st.set_page_config(page_title="Furniture Workshop Tracker", layout="wide")
st.title("🪚 Permanent Furniture Workshop Record System")

# Helper function to load data permanently from files
def load_data(file_name, columns):
    if os.path.exists(file_name):
        return pd.read_csv(file_name)
    return pd.DataFrame(columns=columns)

# Helper function to save data permanently to files
def save_data(df, file_name):
    df.to_csv(file_name, index=False)

# Load data into session state permanently
if "workers" not in st.session_state:
    st.session_state.workers = load_data("workers.csv", ["Worker ID", "Name", "Phone", "Skill"])
if "logs" not in st.session_state:
    st.session_state.logs = load_data("logs.csv", ["Log ID", "Worker ID", "Starting Time", "Ended Time"])
if "financials" not in st.session_state:
    st.session_state.financials = load_data("financials.csv", ["Payment ID", "Log ID", "Daily Wage (NPR)", "Days Worked", "Total Earned (NPR)", "Taken Money / Advance (NPR)", "Total Received Money (NPR)", "Status"])

# Sidebar navigation menu
menu = st.sidebar.radio("Navigation Menu", ["Dashboard Summary", "Manage Workers", "Log Daily Work", "Financial Payouts"])

# --- 1. DASHBOARD OVERVIEW ---
if menu == "Dashboard Summary":
    st.subheader("📊 Workshop Live Summary")
    
    if not st.session_state.financials.empty:
        total_wages = pd.to_numeric(st.session_state.financials["Total Earned (NPR)"]).sum()
        total_taken = pd.to_numeric(st.session_state.financials["Taken Money / Advance (NPR)"]).sum()
        total_received = pd.to_numeric(st.session_state.financials["Total Received Money (NPR)"]).sum()
        total_dues = total_wages - (total_taken + total_received)
    else:
        total_wages, total_taken, total_received, total_dues = 0.0, 0.0, 0.0, 0.0
        
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Labor Bill", f"NPR {total_wages:,.2f}")
    col2.metric("Total Taken Money (Advances)", f"NPR {total_taken:,.2f}")
    col3.metric("Total Received Money (Paid Out)", f"NPR {total_received:,.2f}")
    col4.metric("Remaining Balance Due", f"NPR {total_dues:,.2f}", delta_color="inverse")

    st.markdown("---")
    st.subheader("📋 Shift Work Logs")
    if not st.session_state.logs.empty:
        st.dataframe(st.session_state.logs, use_container_width=True)
    else:
        st.info("No workshop shifts logged yet. Go to 'Log Daily Work' to start.")

# --- 2. MANAGE WORKERS ---
elif menu == "Manage Workers":
    st.subheader("👥 Workshop Carpentry Team")
    
    col_add, col_del = st.columns(2)
    
    # Form to add a worker
    with col_add:
        st.markdown("### Add New Worker")
        with st.form("Add Worker Form", clear_on_submit=True):
            w_id = f"W00{len(st.session_state.workers) + 1}"
            w_name = st.text_input("Worker Full Name:")
            w_phone = st.text_input("Mobile Number:")
            w_skill = st.selectbox("Role / Specialist Area:", ["Specialist Carpenter", "Carver", "Finisher / Polisher", "Helper"])
            submit_worker = st.form_submit_button("Register New Worker")
            
            if submit_worker and w_name:
                new_worker = pd.DataFrame([[w_id, w_name, w_phone, w_skill]], columns=st.session_state.workers.columns)
                st.session_state.workers = pd.concat([st.session_state.workers, new_worker], ignore_index=True)
                save_data(st.session_state.workers, "workers.csv")
                st.success(f"Successfully added worker {w_name} with ID {w_id}!")
                st.rerun()

    # Section to delete a worker
    with col_del:
        st.markdown("### Delete Worker Info")
        if st.session_state.workers.empty:
            st.info("No workers registered yet to remove.")
        else:
            worker_list = st.session_state.workers["Worker ID"].astype(str) + " - " + st.session_state.workers["Name"].astype(str)
            worker_to_delete = st.selectbox("Select Worker to Delete:", worker_list)
            delete_w_id = worker_to_delete.split(" - ")[0]
            
            if st.button("❌ Delete Selected Worker", type="primary"):
                # Remove the worker from data frame
                st.session_state.workers = st.session_state.workers[st.session_state.workers["Worker ID"] != delete_w_id]
                save_data(st.session_state.workers, "workers.csv")
                st.success(f"Removed worker record for {worker_to_delete}!")
                st.rerun()

    st.markdown("---")
    st.markdown("### Active Workers Directory")
    st.dataframe(st.session_state.workers, use_container_width=True)

# --- 3. LOG DAILY WORK ---
elif menu == "Log Daily Work":
    st.subheader("📝 Record Shift Timings")
    
    if st.session_state.workers.empty:
        st.warning("Please add at least one worker in 'Manage Workers' before recording attendance logs.")
    else:
        with st.form("Add Log Form", clear_on_submit=True):
            l_id = f"L00{len(st.session_state.logs) + 1}"
            worker_choices = st.session_state.workers["Worker ID"].astype(str) + " - " + st.session_state.workers["Name"].astype(str)
            worker_choice = st.selectbox("Select Worker:", worker_choices)
            selected_w_id = worker_choice.split(" - ")[0]
            
            start_t = st.time_input("Starting Time", time(9, 0))
            end_t = st.time_input("Ended Time", time(18, 0))
            
            submit_log = st.form_submit_button("Save Attendance Entry")
            
            if submit_log:
                new_log = pd.DataFrame([[l_id, selected_w_id, start_t.strftime("%I:%M %p"), end_t.strftime("%I:%M %p")]], columns=st.session_state.logs.columns)
                st.session_state.logs = pd.concat([st.session_state.logs, new_log], ignore_index=True)
                save_data(st.session_state.logs, "logs.csv")
                st.success(f"Shift timing recorded under log {l_id}!")
                st.rerun()

        st.dataframe(st.session_state.logs, use_container_width=True)

# --- 4. FINANCIAL PAYOUTS ---
elif menu == "Financial Payouts":
    st.subheader("💰 Daily Wage Ledger & Payout Accounts")
    
    if st.session_state.logs.empty:
        st.warning("No shift timings logged yet. Create records under 'Log Daily Work'.")
    else:
        unlinked_logs = st.session_state.logs[~st.session_state.logs["Log ID"].isin(st.session_state.financials["Log ID"])]
        
        if unlinked_logs.empty:
            st.info("All logged shifts already have financial records established.")
        
        with st.form("Add Payment Details", clear_on_submit=True):
            p_id = f"P00{len(st.session_state.financials) + 1}"
            
            if not unlinked_logs.empty:
                log_choices = unlinked_logs["Log ID"].astype(str) + " (Worker: " + unlinked_logs["Worker ID"].astype(str) + ")"
                log_choice = st.selectbox("Select Unbilled Log ID:", log_choices)
                selected_l_id = log_choice.split(" (")[0]
            else:
                st.selectbox("Select Log ID:", ["No unbilled logs available"], disabled=True)
                selected_l_id = None
                
            daily_wage = st.number_input("Worker Daily Wage Rate (NPR):", min_value=0.0, value=1500.0, step=100.0)
            days_worked = st.number_input("Number of Days Worked:", min_value=0.5, value=1.0, step=0.5)
            
            taken_money = st.number_input("Taken Money / Advance Given (NPR):", min_value=0.0, value=0.0, step=100.0)
            received_money = st.number_input("Worker Total Received Money from Business (NPR):", min_value=0.0, value=0.0, step=100.0)
            
            submit_fin = st.form_submit_button("Record Financial Entry")
            
            if submit_fin:
                if selected_l_id is None:
                    st.error("Cannot record payment without a valid unbilled Log ID.")
                else:
                    total_earned = daily_wage * days_worked
                    remaining_due = total_earned - (taken_money + received_money)
                    
                    if remaining_due <= 0:
                        p_status = "Fully Settled"
                    elif received_money > 0 or taken_money > 0:
                        p_status = "Partially Paid"
                    else:
                        p_status = "Unpaid"
                        
                    new_fin = pd.DataFrame([[p_id, selected_l_id, daily_wage, days_worked, total_earned, taken_money, received_money, p_status]], columns=st.session_state.financials.columns)
                    st.session_state.financials = pd.concat([st.session_state.financials, new_fin], ignore_index=True)
                    save_data(st.session_state.financials, "financials.csv")
                    st.success("Financial ledger entry updated!")
                    st.rerun()

        st.dataframe(st.session_state.financials, use_container_width=True)
