import streamlit as st
import pandas as pd
from datetime import date
import sqlite3
import io

# Set page configurations
st.set_page_config(page_title="Furniture Workshop Tracker", layout="wide")
st.title("🪚 Permanent Furniture Workshop Record System")

DB_FILE = "workshop.db"

# --- DATABASE SETUP & HELPERS ---
def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes and updates database schema dynamically."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Workers Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                skill TEXT
            )
        """)
        
        # Logs Table with OT Support
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                ot_hours REAL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY (worker_id) REFERENCES workers (worker_id) ON DELETE CASCADE
            )
        """)

        # Migration helper to ensure ot_hours column exists in existing databases
        cursor.execute("PRAGMA table_info(logs)")
        columns = [col[1] for col in cursor.fetchall()]
        if "ot_hours" not in columns:
            cursor.execute("ALTER TABLE logs ADD COLUMN ot_hours REAL DEFAULT 0.0")
            cursor.execute("ALTER TABLE logs ADD COLUMN ot_notes TEXT")
        
        # Shop Consumption Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL NOT NULL,
                notes TEXT,
                FOREIGN KEY (worker_id) REFERENCES workers (worker_id) ON DELETE CASCADE
            )
        """)

        # Leaves & Holidays Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (worker_id) REFERENCES workers (worker_id) ON DELETE CASCADE
            )
        """)
        
        # Financials Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                log_id TEXT UNIQUE NOT NULL,
                daily_wage REAL NOT NULL,
                days_worked REAL NOT NULL,
                ot_rate_per_hour REAL DEFAULT 0.0,
                total_earned REAL NOT NULL,
                taken_money REAL NOT NULL,
                advance_reason TEXT,
                received_money REAL NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (log_id) REFERENCES logs (log_id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("PRAGMA table_info(financials)")
        f_cols = [col[1] for col in cursor.fetchall()]
        if "ot_rate_per_hour" not in f_cols:
            cursor.execute("ALTER TABLE financials ADD COLUMN ot_rate_per_hour REAL DEFAULT 0.0")

        conn.commit()

# Run database setup
init_db()

def run_query(query, params=()):
    """Executes a read query and returns a Pandas DataFrame."""
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def run_action(query, params=()):
    """Executes an INSERT, UPDATE, or DELETE query."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def get_next_id(prefix, table, id_col):
    """Generates the next unique ID safely."""
    df = run_query(f"SELECT {id_col} FROM {table}")
    if df.empty:
        return f"{prefix}001"
    
    nums = []
    for val in df[id_col].dropna():
        digits = ''.join(filter(str.isdigit, str(val)))
        if digits:
            nums.append(int(digits))
            
    next_num = max(nums) + 1 if nums else 1
    return f"{prefix}{next_num:03d}"

# --- DATA LOADERS ---
def load_workers():
    return run_query("SELECT worker_id AS 'Worker ID', name AS 'Name', phone AS 'Phone', skill AS 'Skill' FROM workers")

def load_logs():
    return run_query("""
        SELECT logs.log_id AS 'Log ID', logs.worker_id AS 'Worker ID', workers.name AS 'Worker Name', 
               logs.work_date AS 'Date', logs.ot_hours AS 'OT Hours', logs.ot_notes AS 'OT Details', 
               logs.remarks AS 'Shift Remarks' 
        FROM logs
        LEFT JOIN workers ON logs.worker_id = workers.worker_id
    """)

def load_consumption():
    return run_query("""
        SELECT sc.item_id AS 'Item ID', sc.worker_id AS 'Worker ID', workers.name AS 'Worker Name',
               sc.entry_date AS 'Date', sc.item_name AS 'Item Consumed', 
               sc.item_cost AS 'Cost (NPR)', sc.notes AS 'Notes'
        FROM shop_consumption sc
        LEFT JOIN workers ON sc.worker_id = workers.worker_id
    """)

def load_leaves():
    return run_query("""
        SELECT leaves.leave_id AS 'Leave ID', leaves.worker_id AS 'Worker ID', workers.name AS 'Worker Name',
               leaves.leave_date AS 'Leave Date', leaves.leave_type AS 'Leave Type', 
               leaves.reason AS 'Reason / Remarks' 
        FROM leaves
        LEFT JOIN workers ON leaves.worker_id = workers.worker_id
    """)

def load_financials():
    return run_query("""
        SELECT payment_id AS 'Payment ID', log_id AS 'Log ID', daily_wage AS 'Daily Wage (NPR)', 
               days_worked AS 'Days Worked', ot_rate_per_hour AS 'OT Rate/Hr (NPR)', total_earned AS 'Total Earned (NPR)', 
               taken_money AS 'Taken Money / Advance (NPR)', advance_reason AS 'Advance Reason',
               received_money AS 'Total Received Money (NPR)', status AS 'Status' 
        FROM financials
    """)

# Fetch data for current session
df_workers = load_workers()
df_logs = load_logs()
df_consumption = load_consumption()
df_leaves = load_leaves()
df_financials = load_financials()

# --- EXPORT HELPER FUNCTIONS ---
def generate_excel():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_workers.to_excel(writer, sheet_name='Workers', index=False)
        df_logs.to_excel(writer, sheet_name='Shift Logs & OT', index=False)
        df_consumption.to_excel(writer, sheet_name='Shop Consumptions', index=False)
        df_leaves.to_excel(writer, sheet_name='Leaves & Holidays', index=False)
        df_financials.to_excel(writer, sheet_name='Financials', index=False)
    return output.getvalue()

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- SIDEBAR NAVIGATION ---
st.sidebar.header("📍 Navigation")
menu = st.sidebar.radio("Go to:", [
    "Dashboard & Monthly View", 
    "Manage Workers", 
    "Log Daily Work & OT", 
    "Shop Items Consumed",
    "Manage Leaves & Holidays", 
    "Financial Payouts"
])

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Reports")

excel_data = generate_excel()
st.sidebar.download_button(
    label="📊 Export All Data (Excel .xlsx)",
    data=excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("📄 Export Individual CSVs"):
    st.download_button("Download Workers CSV", convert_df_to_csv(df_workers), f"workers_{date.today()}.csv", "text/csv", use_container_width=True)
    st.download_button("Download Shift Logs & OT CSV", convert_df_to_csv(df_logs), f"logs_{date.today()}.csv", "text/csv", use_container_width=True)
    st.download_button("Download Shop Expenses CSV", convert_df_to_csv(df_consumption), f"consumption_{date.today()}.csv", "text/csv", use_container_width=True)
    st.download_button("Download Leaves CSV", convert_df_to_csv(df_leaves), f"leaves_{date.today()}.csv", "text/csv", use_container_width=True)
    st.download_button("Download Financials CSV", convert_df_to_csv(df_financials), f"financials_{date.today()}.csv", "text/csv", use_container_width=True)

# --- 1. DASHBOARD & MONTHLY ATTENDANCE / OT OVERVIEW ---
if menu == "Dashboard & Monthly View":
    st.subheader("📊 Workshop Live Summary & Monthly OT Tracker")
    
    # Financial Metrics
    if not df_financials.empty:
        total_wages = pd.to_numeric(df_financials["Total Earned (NPR)"]).sum()
        total_taken = pd.to_numeric(df_financials["Taken Money / Advance (NPR)"]).sum()
        total_received = pd.to_numeric(df_financials["Total Received Money (NPR)"]).sum()
        total_consumed = pd.to_numeric(df_consumption["Cost (NPR)"]).sum() if not df_consumption.empty else 0.0
        total_dues = total_wages - (total_taken + total_received + total_consumed)
    else:
        total_wages, total_taken, total_received, total_consumed, total_dues = 0.0, 0.0, 0.0, 0.0, 0.0
        
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Labor Bill", f"NPR {total_wages:,.2f}")
    col2.metric("Total Advances Given", f"NPR {total_taken:,.2f}")
    col3.metric("Shop Items Deductions", f"NPR {total_consumed:,.2f}")
    col4.metric("Total Paid Out", f"NPR {total_received:,.2f}")
    col5.metric("Remaining Balance Due", f"NPR {total_dues:,.2f}", delta_color="inverse")

    st.markdown("---")
    st.subheader("🗓️ Monthly Attendance & Overtime (OT) Filter")
    
    if not df_logs.empty:
        df_logs['Date_Obj'] = pd.to_datetime(df_logs['Date'])
        df_logs['Month_Year'] = df_logs['Date_Obj'].dt.strftime('%B %Y')
        
        available_months = df_logs['Month_Year'].unique().tolist()
        selected_month = st.selectbox("Select Month to Filter Attendance & OT:", available_months)
        
        filtered_logs = df_logs[df_logs['Month_Year'] == selected_month].drop(columns=['Date_Obj', 'Month_Year'])
        
        # Display OT Summary
        ot_logs = filtered_logs[filtered_logs['OT Hours'] > 0]
        
        st.markdown(f"### ⏰ Overtime Summary for {selected_month}")
        if not ot_logs.empty:
            total_ot_hrs = ot_logs['OT Hours'].sum()
            st.success(f"Total Overtime Worked in **{selected_month}**: **{total_ot_hrs:.1f} Hours** across **{len(ot_logs)} shift(s)**.")
            st.dataframe(ot_logs[['Log ID', 'Worker Name', 'Date', 'OT Hours', 'OT Details', 'Shift Remarks']], use_container_width=True)
        else:
            st.info(f"No overtime logged for {selected_month}.")
            
        st.markdown(f"### 📋 All Attendance Logs for {selected_month}")
        st.dataframe(filtered_logs, use_container_width=True)
    else:
        st.info("No workshop shifts or OT logged yet.")

# --- 2. MANAGE WORKERS ---
elif menu == "Manage Workers":
    st.subheader("👥 Workshop Carpentry Team")
    col_add, col_del = st.columns(2)
    
    with col_add:
        st.markdown("### Add New Worker")
        with st.form("Add Worker Form", clear_on_submit=True):
            w_id = get_next_id("W", "workers", "worker_id")
            w_name = st.text_input("Worker Full Name:")
            w_phone = st.text_input("Mobile Number:")
            w_skill = st.selectbox("Role / Specialist Area:", ["Specialist Carpenter", "Carver", "Finisher / Polisher", "Helper"])
            submit_worker = st.form_submit_button("Register New Worker")
            
            if submit_worker and w_name:
                run_action("INSERT INTO workers (worker_id, name, phone, skill) VALUES (?, ?, ?, ?)", (w_id, w_name, w_phone, w_skill))
                st.success(f"Successfully added worker {w_name}!")
                st.rerun()

    with col_del:
        st.markdown("### Delete Worker Info")
        if df_workers.empty:
            st.info("No workers registered yet.")
        else:
            worker_list = df_workers["Worker ID"].astype(str) + " - " + df_workers["Name"].astype(str)
            worker_to_delete = st.selectbox("Select Worker to Delete:", worker_list)
            delete_w_id = worker_to_delete.split(" - ")[0]
            
            if st.button("❌ Delete Selected Worker", type="primary"):
                run_action("DELETE FROM workers WHERE worker_id = ?", (delete_w_id,))
                st.success("Removed worker record!")
                st.rerun()

    st.markdown("---")
    st.dataframe(load_workers(), use_container_width=True)

# --- 3. LOG DAILY WORK & OT ---
elif menu == "Log Daily Work & OT":
    st.subheader("📝 Record Shift Entry & Overtime (OT)")
    col_add, col_del = st.columns(2)
    
    with col_add:
        st.markdown("### Log Shift & OT Hours")
        if df_workers.empty:
            st.warning("Please add at least one worker first.")
        else:
            with st.form("Add Log Form", clear_on_submit=True):
                l_id = get_next_id("L", "logs", "log_id")
                worker_choices = df_workers["Worker ID"].astype(str) + " - " + df_workers["Name"].astype(str)
                worker_choice = st.selectbox("Select Worker:", worker_choices)
                selected_w_id = worker_choice.split(" - ")[0]
                
                work_date = st.date_input("Work Date", date.today())
                
                st.markdown("---")
                st.write("⏰ **Overtime Details (Optional)**")
                worked_ot = st.checkbox("Worker Worked Overtime (OT) on this Date?")
                ot_hours = st.number_input("OT Hours Worked:", min_value=0.0, value=2.0, step=0.5) if worked_ot else 0.0
                ot_notes = st.text_input("OT Project / Job Details:") if worked_ot else ""
                
                st.markdown("---")
                shift_remarks = st.text_input("Regular Shift Remarks:")
                submit_log = st.form_submit_button("Save Attendance & OT Entry")
                
                if submit_log:
                    formatted_date = work_date.strftime("%Y-%m-%d")
                    
                    run_action(
                        "INSERT INTO logs (log_id, worker_id, work_date, ot_hours, ot_notes, remarks) VALUES (?, ?, ?, ?, ?, ?)",
                        (l_id, selected_w_id, formatted_date, ot_hours, ot_notes, shift_remarks)
                    )
                    st.success(f"Shift entry recorded under log {l_id}!")
                    st.rerun()

    with col_del:
        st.markdown("### Delete a Shift Log")
        if df_logs.empty:
            st.info("No logs available to delete.")
        else:
            log_list = df_logs["Log ID"].astype(str) + " (Worker: " + df_logs["Worker ID"].astype(str) + " on " + df_logs["Date"].astype(str) + ")"
            log_to_delete = st.selectbox("Select Log ID to Delete:", log_list)
            delete_l_id = log_to_delete.split(" (")[0]
            
            if st.button("❌ Delete Selected Log", type="primary"):
                run_action("DELETE FROM financials WHERE log_id = ?", (delete_l_id,))
                run_action("DELETE FROM logs WHERE log_id = ?", (delete_l_id,))
                st.success("Log entry deleted successfully!")
                st.rerun()

    st.markdown("---")
    st.dataframe(load_logs(), use_container_width=True)

# --- 4. SHOP ITEMS CONSUMED ---
elif menu == "Shop Items Consumed":
    st.subheader("🛒 Shop & Canteen Items Consumed by Workers")
    col_add, col_del = st.columns(2)
    
    with col_add:
        st.markdown("### Log Item Taken / Consumed")
        if df_workers.empty:
            st.warning("Please add at least one worker first.")
        else:
            with st.form("Add Consumption Form", clear_on_submit=True):
                c_id = get_next_id("C", "shop_consumption", "item_id")
                worker_choices = df_workers["Worker ID"].astype(str) + " - " + df_workers["Name"].astype(str)
                worker_choice = st.selectbox("Select Worker:", worker_choices)
                selected_w_id = worker_choice.split(" - ")[0]
                
                c_date = st.date_input("Date Taken", date.today())
                item_name = st.text_input("Item Consumed / Taken (e.g., Tea & Snacks, Nails, Varnish, Food):")
                item_cost = st.number_input("Item Total Cost (NPR):", min_value=0.0, value=50.0, step=10.0)
                item_notes = st.text_input("Additional Notes / Remarks:")
                
                submit_c = st.form_submit_button("Record Expense")
                
                if submit_c and item_name:
                    run_action(
                        "INSERT INTO shop_consumption (item_id, worker_id, entry_date, item_name, item_cost, notes) VALUES (?, ?, ?, ?, ?, ?)",
                        (c_id, selected_w_id, c_date.strftime("%Y-%m-%d"), item_name, item_cost, item_notes)
                    )
                    st.success(f"Recorded {item_name} for NPR {item_cost}!")
                    st.rerun()

    with col_del:
        st.markdown("### Remove Consumption Entry")
        if df_consumption.empty:
            st.info("No shop consumption records logged yet.")
        else:
            c_list = df_consumption["Item ID"].astype(str) + " (" + df_consumption["Item Consumed"].astype(str) + " - NPR " + df_consumption["Cost (NPR)"].astype(str) + ")"
            c_to_delete = st.selectbox("Select Record to Remove:", c_list)
            delete_c_id = c_to_delete.split(" (")[0]
            
            if st.button("❌ Delete Selected Record", type="primary"):
                run_action("DELETE FROM shop_consumption WHERE item_id = ?", (delete_c_id,))
                st.success("Consumption record removed!")
                st.rerun()

    st.markdown("---")
    st.dataframe(load_consumption(), use_container_width=True)

# --- 5. MANAGE LEAVES & HOLIDAYS ---
elif menu == "Manage Leaves & Holidays":
    st.subheader("🌴 Worker Leaves & Workshop Holidays")
    col_add, col_del = st.columns(2)
    
    with col_add:
        st.markdown("### Record Leave / Absence")
        if df_workers.empty:
            st.warning("Please add at least one worker first.")
        else:
            with st.form("Add Leave Form", clear_on_submit=True):
                lv_id = get_next_id("LV", "leaves", "leave_id")
                worker_choices = df_workers["Worker ID"].astype(str) + " - " + df_workers["Name"].astype(str)
                worker_choice = st.selectbox("Select Worker:", worker_choices)
                selected_w_id = worker_choice.split(" - ")[0]
                
                leave_d = st.date_input("Leave Date", date.today())
                leave_type = st.selectbox("Leave Type:", ["Casual Leave", "Sick Leave", "Festival / Public Holiday", "Unpaid Leave"])
                leave_reason = st.text_input("Reason / Remarks for Leave:")
                
                submit_leave = st.form_submit_button("Record Leave Entry")
                
                if submit_leave:
                    run_action(
                        "INSERT INTO leaves (leave_id, worker_id, leave_date, leave_type, reason) VALUES (?, ?, ?, ?, ?)",
                        (lv_id, selected_w_id, leave_d.strftime("%Y-%m-%d"), leave_type, leave_reason)
                    )
                    st.success(f"Recorded {leave_type} for worker on {leave_d.strftime('%B %d, %Y')}!")
                    st.rerun()

    with col_del:
        st.markdown("### Remove Leave Entry")
        if df_leaves.empty:
            st.info("No leave records logged yet.")
        else:
            leave_list = df_leaves["Leave ID"].astype(str) + " (Worker: " + df_leaves["Worker ID"].astype(str) + " on " + df_leaves["Leave Date"].astype(str) + ")"
            leave_to_delete = st.selectbox("Select Leave ID to Remove:", leave_list)
            delete_lv_id = leave_to_delete.split(" (")[0]
            
            if st.button("❌ Delete Selected Leave Record", type="primary"):
                run_action("DELETE FROM leaves WHERE leave_id = ?", (delete_lv_id,))
                st.success("Leave record removed!")
                st.rerun()

    st.markdown("---")
    st.dataframe(load_leaves(), use_container_width=True)

# --- 6. FINANCIAL PAYOUTS ---
elif menu == "Financial Payouts":
    st.subheader("💰 Daily Wage Ledger & Payout Accounts")
    
    if df_logs.empty:
        st.warning("No shift timings logged yet.")
    else:
        col_form, col_del = st.columns(2)
        
        with col_form:
            action = st.radio("Choose Action:", ["Add New Record", "Edit / Update Existing Record"], horizontal=True)
            unlinked_logs = df_logs[~df_logs["Log ID"].isin(df_financials["Log ID"])] if not df_financials.empty else df_logs
            
            if action == "Add New Record":
                st.markdown("### Add Payout Record")
                if unlinked_logs.empty:
                    st.info("All logged shifts already have financial records.")
                    
                with st.form("Add Financial Form", clear_on_submit=True):
                    p_id = get_next_id("P", "financials", "payment_id")
                    if not unlinked_logs.empty:
                        log_choices = unlinked_logs["Log ID"].astype(str) + " (Worker: " + unlinked_logs["Worker Name"].astype(str) + " on " + unlinked_logs["Date"].astype(str) + ")"
                        log_choice = st.selectbox("Select Unbilled Log ID:", log_choices)
                        selected_l_id = log_choice.split(" (")[0]
                        
                        # Get log details for OT
                        selected_log = unlinked_logs[unlinked_logs["Log ID"] == selected_l_id].iloc[0]
                        log_ot_hours = float(selected_log["OT Hours"]) if pd.notnull(selected_log["OT Hours"]) else 0.0
                    else:
                        st.selectbox("Select Log ID:", ["No unbilled logs available"], disabled=True)
                        selected_l_id = None
                        log_ot_hours = 0.0
                        
                    daily_wage = st.number_input("Worker Daily Wage Rate (NPR):", min_value=0.0, value=1500.0, step=100.0)
                    days_worked = st.number_input("Number of Days Worked:", min_value=0.5, value=1.0, step=0.5)
                    
                    st.write(f"⏱️ **Logged OT Hours for this Shift:** `{log_ot_hours}` Hours")
                    ot_rate = st.number_input("OT Rate Per Hour (NPR):", min_value=0.0, value=200.0, step=50.0) if log_ot_hours > 0 else 0.0
                    
                    taken_money = st.number_input("Taken Money / Advance Given (NPR):", min_value=0.0, value=0.0, step=100.0)
                    adv_reason = st.text_input("Reason for Advance / Taken Money:")
                    received_money = st.number_input("Worker Total Received Money (NPR):", min_value=0.0, value=0.0, step=100.0)
                    
                    submit_fin = st.form_submit_button("Record Financial Entry")
                    
                    if submit_fin and selected_l_id:
                        total_earned = (daily_wage * days_worked) + (log_ot_hours * ot_rate)
                        remaining_due = total_earned - (taken_money + received_money)
                        p_status = "Fully Settled" if remaining_due <= 0 else ("Partially Paid" if received_money > 0 or taken_money > 0 else "Unpaid")
                        
                        run_action("""
                            INSERT INTO financials (payment_id, log_id, daily_wage, days_worked, ot_rate_per_hour, total_earned, taken_money, advance_reason, received_money, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (p_id, selected_l_id, daily_wage, days_worked, ot_rate, total_earned, taken_money, adv_reason, received_money, p_status))
                        
                        st.success("Financial ledger entry updated!")
                        st.rerun()
            
            else:
                st.markdown("### Edit Existing Record")
                if df_financials.empty:
                    st.info("No entries recorded yet to edit.")
                else:
                    edit_list = df_financials["Payment ID"].astype(str) + " (Log Ref: " + df_financials["Log ID"].astype(str) + ")"
                    selected_edit = st.selectbox("Select Payment ID to Edit:", edit_list)
                    edit_p_id = selected_edit.split(" (")[0]
                    
                    row_data = df_financials[df_financials["Payment ID"] == edit_p_id].iloc[0]
                    linked_log = df_logs[df_logs["Log ID"] == row_data["Log ID"]].iloc[0]
                    log_ot_hours = float(linked_log["OT Hours"]) if pd.notnull(linked_log["OT Hours"]) else 0.0
                    
                    with st.form("Edit Financial Form"):
                        st.write(f"Editing **{edit_p_id}** linked to Log ID: **{row_data['Log ID']}**")
                        
                        edit_wage = st.number_input("Worker Daily Wage Rate (NPR):", min_value=0.0, value=float(row_data["Daily Wage (NPR)"]), step=100.0)
                        edit_days = st.number_input("Number of Days Worked:", min_value=0.5, value=float(row_data["Days Worked"]), step=0.5)
                        
                        st.write(f"⏱️ **Logged OT Hours:** `{log_ot_hours}` Hours")
                        edit_ot_rate = st.number_input("OT Rate Per Hour (NPR):", min_value=0.0, value=float(row_data["OT Rate/Hr (NPR)"]), step=50.0) if log_ot_hours > 0 else 0.0
                        
                        edit_taken = st.number_input("Taken Money / Advance Given (NPR):", min_value=0.0, value=float(row_data["Taken Money / Advance (NPR)"]), step=100.0)
                        edit_adv_reason = st.text_input("Reason for Advance / Taken Money:", value=str(row_data["Advance Reason"] or ""))
                        edit_received = st.number_input("Worker Total Received Money (NPR):", min_value=0.0, value=float(row_data["Total Received Money (NPR)"]), step=100.0)
                        
                        update_fin = st.form_submit_button("Update Financial Entry")
                        
                        if update_fin:
                            total_earned = (edit_wage * edit_days) + (log_ot_hours * edit_ot_rate)
                            remaining_due = total_earned - (edit_taken + edit_received)
                            p_status = "Fully Settled" if remaining_due <= 0 else ("Partially Paid" if edit_received > 0 or edit_taken > 0 else "Unpaid")
                            
                            run_action("""
                                UPDATE financials 
                                SET daily_wage = ?, days_worked = ?, ot_rate_per_hour = ?, total_earned = ?, taken_money = ?, advance_reason = ?, received_money = ?, status = ?
                                WHERE payment_id = ?
                            """, (edit_wage, edit_days, edit_ot_rate, total_earned, edit_taken, edit_adv_reason, edit_received, p_status, edit_p_id))
                            
                            st.success(f"Record {edit_p_id} updated successfully!")
                            st.rerun()

        with col_del:
            st.markdown("### Delete Payout Record")
            if df_financials.empty:
                st.info("No payout entries to remove.")
            else:
                fin_list = df_financials["Payment ID"].astype(str) + " (Log Ref: " + df_financials["Log ID"].astype(str) + ")"
                fin_to_delete = st.selectbox("Select Payment ID to Remove:", fin_list)
                delete_p_id = fin_to_delete.split(" (")[0]
                
                if st.button("❌ Delete Selected Financial Record", type="primary"):
                    run_action("DELETE FROM financials WHERE payment_id = ?", (delete_p_id,))
                    st.success("Financial entry deleted successfully!")
                    st.rerun()

        st.markdown("---")
        st.dataframe(load_financials(), use_container_width=True)
