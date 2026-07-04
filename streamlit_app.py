import streamlit as st
import pandas as pd
from datetime import date

# Set page configurations
st.set_page_config(page_title="Furniture Workshop Tracker", layout="wide")
st.title("🪚 Furniture Workshop Record System")

# Initialize database-like states if they don't exist yet
if "workers" not in st.session_state:
    st.session_state.workers = pd.DataFrame(columns=["Worker ID", "Name", "Phone", "Skill"])
if "logs" not in st.session_state:
    st.session_state.logs = pd.DataFrame(columns=["Log ID", "Worker ID", "Furniture Item", "Qty", "Start Date", "End Date", "Status"])
if "financials" not in st.session_state:
    st.session_state.financials = pd.DataFrame(columns=["Payment ID", "Log ID", "Total Wage (NPR)", "Advance Paid (NPR)", "Balance Due (NPR)", "Status"])

# Sidebar navigation menu
menu = st.sidebar.radio("Navigation Menu", ["Dashboard Summary", "Manage Workers", "Log Daily Work", "Financial Payouts"])

# --- 1. DASHBOARD OVERVIEW ---
if menu == "Dashboard Summary":
    st.subheader("📊 Workshop Live Summary")
    
    if not st.session_state.financials.empty:
        total_wages = st.session_state.financials["Total Wage (NPR)"].sum()
        total_advances = st.session_state.financials["Advance Paid (NPR)"].sum()
        total_dues = st.session_state.financials["Balance Due (NPR)"].sum()
    else:
        total_wages, total_advances, total_dues = 0.0, 0.0, 0.0
        
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Labor Expenses", f"NPR {total_wages:,.2f}")
    col2.metric("Total Advances Disbursed", f"NPR {total_advances:,.2f}")
    col3.metric("Outstanding Balance Due", f"NPR {total_dues:,.2f}", delta_color="inverse")

    st.markdown("---")
    st.subheader("📋 Current Active Jobs Log")
    if not st.session_state.logs.empty:
        st.dataframe(st.session_state.logs, use_container_width=True)
    else:
        st.info("No work orders logged yet. Go to 'Log Daily Work' to start.")

# --- 2. MANAGE WORKERS ---
elif menu == "Manage Workers":
    st.subheader("👥 Workshop Carpentry Team")
    
    # Form to add a new worker
    with st.form("Add Worker Form", clear_on_submit=True):
        w_id = f"W00{len(st.session_state.workers) + 1}"
        w_name = st.text_input("Worker Full Name:")
        w_phone = st.text_input("Mobile Number:")
        w_skill = st.selectbox("Role / Specialist Area:", ["Specialist Carpenter", "Carver", "Finisher / Polisher", "Helper"])
        submit_worker = st.form_submit_button("Register New Worker")
        
        if submit_worker and w_name:
            new_worker = pd.DataFrame([[w_id, w_name, w_phone, w_skill]], columns=st.session_state.workers.columns)
            st.session_state.workers = pd.concat([st.session_state.workers, new_worker], ignore_index=True)
            st.success(f"Successfully added worker {w_name} with ID {w_id}!")

    st.dataframe(st.session_state.workers, use_container_width=True)

# --- 3. LOG DAILY WORK ---
elif menu == "Log Daily Work":
    st.subheader("📝 Assign & Log Production Units")
    
    if st.session_state.workers.empty:
        st.warning("Please add at least one worker in 'Manage Workers' before creating records.")
    else:
        with st.form("Add Log Form", clear_on_submit=True):
            l_id = f"L00{len(st.session_state.logs) + 1}"
            worker_choice = st.selectbox("Assign to Worker:", st.session_state.workers["Worker ID"] + " - " + st.session_state.workers["Name"])
            selected_w_id = worker_choice.split(" - ")[0]
            
            item_name = st.text_input("Furniture Item Name (e.g. Sofa, Dining Table):")
            quantity = st.number_input("Quantity Produced:", min_value=1, value=1)
            start_d = st.date_input("Start Date", date.today())
            end_d = st.date_input("Expected/End Date", date.today())
            job_status = st.selectbox("Current Production Stage:", ["In Progress", "Completed", "Quality Checked"])
            
            submit_log = st.form_submit_button("Save Production Entry")
            
            if submit_log and item_name:
                new_log = pd.DataFrame([[l_id, selected_w_id, item_name, quantity, start_d, end_d, job_status]], columns=st.session_state.logs.columns)
                st.session_state.logs = pd.concat([st.session_state.logs, new_log], ignore_index=True)
                st.success(f"Production record {l_id} saved!")

        st.dataframe(st.session_state.logs, use_container_width=True)

# --- 4. FINANCIAL PAYOUTS ---
elif menu == "Financial Payouts":
    st.subheader("💰 Ledger Accounts & Labor Wages")
    
    if st.session_state.logs.empty:
        st.warning("No production units logged yet. Create records under 'Log Daily Work'.")
    else:
        with st.form("Add Payment Details", clear_on_submit=True):
            unlinked_logs = st.session_state.logs[~st.session_state.logs["Log ID"].isin(st.session_state.financials["Log ID"])]
            
            if unlinked_logs.empty:
                st.info("All logged jobs already have financial records established.")
                submit_fin = False
            else:
                p_id = f"P00{len(st.session_state.financials) + 1}"
                log_choice = st.selectbox("Select Unbilled Log ID:", unlinked_logs["Log ID"] + " (" + unlinked_logs["Furniture Item"] + ")")
                selected_l_id = log_choice.split(" (")[0]
                
                wage = st.number_input("Agreed Total Wage Cost (NPR):", min_value=0.0, step=500.0)
                advance = st.number_input("Upfront Advance Paid (NPR):", min_value=0.0, step=500.0)
                
                submit_fin = st.form_submit_button("Record Financial Entry")
                
                if submit_fin:
                    due = wage - advance
                    p_status = "Fully Paid" if due == 0 else ("Unpaid" if advance == 0 else "Partially Paid")
                    new_fin = pd.DataFrame([[p_id, selected_l_id, wage, advance, due, p_status]], columns=st.session_state.financials.columns)
                    st.session_state.financials = pd.concat([st.session_state.financials, new_fin], ignore_index=True)
                    st.success("Financial ledger entry updated!")

        st.dataframe(st.session_state.financials, use_container_width=True)
