import streamlit as st
import pandas as pd
from datetime import date
import sqlite3
import io
import calendar

# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Record & Monthly Payroll System")

DB_FILE = "workshop.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# DATABASE SETUP AND MIGRATION
# ============================================================

def init_db():

    with get_connection() as conn:
        cursor = conn.cursor()

        # ---------------- WORKERS ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                skill TEXT,
                start_date TEXT
            )
        """)

        cursor.execute("PRAGMA table_info(workers)")
        worker_columns = [row[1] for row in cursor.fetchall()]

        if "start_date" not in worker_columns:
            cursor.execute(
                "ALTER TABLE workers ADD COLUMN start_date TEXT"
            )

        # ---------------- DAILY WORK LOGS ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_days REAL DEFAULT 1.0,
                ot_hours REAL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        cursor.execute("PRAGMA table_info(logs)")
        log_columns = [row[1] for row in cursor.fetchall()]

        if "work_days" not in log_columns:
            cursor.execute(
                "ALTER TABLE logs ADD COLUMN work_days REAL DEFAULT 1.0"
            )

        if "ot_hours" not in log_columns:
            cursor.execute(
                "ALTER TABLE logs ADD COLUMN ot_hours REAL DEFAULT 0.0"
            )

        if "ot_notes" not in log_columns:
            cursor.execute(
                "ALTER TABLE logs ADD COLUMN ot_notes TEXT"
            )

        # ---------------- SHOP CONSUMPTION ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL NOT NULL,
                notes TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------- LEAVES ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------- MONEY TAKEN / ADVANCE ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                advance_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                advance_date TEXT NOT NULL,
                amount REAL NOT NULL,
                reason TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ---------------- MONTHLY PAYROLL ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_payroll (
                payroll_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                payroll_year INTEGER NOT NULL,
                payroll_month INTEGER NOT NULL,

                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,

                calendar_days REAL DEFAULT 0,
                paid_leave_days REAL DEFAULT 0,
                unpaid_leave_days REAL DEFAULT 0,
                worked_days REAL DEFAULT 0,

                daily_wage REAL DEFAULT 0,
                base_salary REAL DEFAULT 0,

                total_ot_hours REAL DEFAULT 0,
                ot_rate REAL DEFAULT 0,
                ot_amount REAL DEFAULT 0,

                total_earned REAL DEFAULT 0,
                advance_deduction REAL DEFAULT 0,
                shop_deduction REAL DEFAULT 0,
                paid_amount REAL DEFAULT 0,
                balance_due REAL DEFAULT 0,

                status TEXT DEFAULT 'Unpaid',

                UNIQUE(worker_id, payroll_year, payroll_month),

                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # Keep old financial table for compatibility
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
                status TEXT NOT NULL
            )
        """)

        conn.commit()


init_db()


# ============================================================
# DATABASE HELPERS
# ============================================================

def run_query(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def run_action(query, params=()):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()


def get_next_id(prefix, table, id_column):

    df = run_query(
        f"SELECT {id_column} FROM {table}"
    )

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[id_column].dropna():
        digits = "".join(
            filter(str.isdigit, str(value))
        )

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


def get_end_of_month(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


# ============================================================
# DATA LOADERS
# ============================================================

def load_workers():

    return run_query("""
        SELECT
            worker_id AS 'Worker ID',
            name AS 'Name',
            phone AS 'Phone',
            skill AS 'Skill',
            start_date AS 'Start Date'
        FROM workers
        ORDER BY name
    """)


def load_logs():

    return run_query("""
        SELECT
            logs.log_id AS 'Log ID',
            logs.worker_id AS 'Worker ID',
            workers.name AS 'Worker Name',
            logs.work_date AS 'Date',
            logs.work_days AS 'Worked Days',
            logs.ot_hours AS 'OT Hours',
            logs.ot_notes AS 'OT Details',
            logs.remarks AS 'Shift Remarks'
        FROM logs
        LEFT JOIN workers
            ON logs.worker_id = workers.worker_id
        ORDER BY logs.work_date DESC
    """)


def load_consumption():

    return run_query("""
        SELECT
            sc.item_id AS 'Item ID',
            sc.worker_id AS 'Worker ID',
            workers.name AS 'Worker Name',
            sc.entry_date AS 'Date',
            sc.item_name AS 'Item Consumed',
            sc.item_cost AS 'Cost (NPR)',
            sc.notes AS 'Notes'
        FROM shop_consumption sc
        LEFT JOIN workers
            ON sc.worker_id = workers.worker_id
        ORDER BY sc.entry_date DESC
    """)


def load_leaves():

    return run_query("""
        SELECT
            leaves.leave_id AS 'Leave ID',
            leaves.worker_id AS 'Worker ID',
            workers.name AS 'Worker Name',
            leaves.leave_date AS 'Leave Date',
            leaves.leave_type AS 'Leave Type',
            leaves.reason AS 'Reason'
        FROM leaves
        LEFT JOIN workers
            ON leaves.worker_id = workers.worker_id
        ORDER BY leaves.leave_date DESC
    """)


def load_advances():

    return run_query("""
        SELECT
            advances.advance_id AS 'Advance ID',
            advances.worker_id AS 'Worker ID',
            workers.name AS 'Worker Name',
            advances.advance_date AS 'Date',
            advances.amount AS 'Amount (NPR)',
            advances.reason AS 'Reason'
        FROM advances
        LEFT JOIN workers
            ON advances.worker_id = workers.worker_id
        ORDER BY advances.advance_date DESC
    """)


def load_monthly_payroll():

    return run_query("""
        SELECT
            mp.payroll_id AS 'Payroll ID',
            mp.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            mp.payroll_year AS 'Year',
            mp.payroll_month AS 'Month Number',
            mp.period_start AS 'Period Start',
            mp.period_end AS 'Period End',
            mp.calendar_days AS 'Calendar Days',
            mp.paid_leave_days AS 'Paid Leave Days',
            mp.unpaid_leave_days AS 'Unpaid Leave Days',
            mp.worked_days AS 'Worked Days',
            mp.daily_wage AS 'Daily Wage (NPR)',
            mp.base_salary AS 'Base Salary (NPR)',
            mp.total_ot_hours AS 'OT Hours',
            mp.ot_rate AS 'OT Rate (NPR)',
            mp.ot_amount AS 'OT Amount (NPR)',
            mp.total_earned AS 'Total Earned (NPR)',
            mp.advance_deduction AS 'Money Taken (NPR)',
            mp.shop_deduction AS 'Shop Deduction (NPR)',
            mp.paid_amount AS 'Amount Paid (NPR)',
            mp.balance_due AS 'Balance Due (NPR)',
            mp.status AS 'Status'
        FROM monthly_payroll mp
        LEFT JOIN workers w
            ON mp.worker_id = w.worker_id
        ORDER BY
            mp.payroll_year DESC,
            mp.payroll_month DESC,
            w.name
    """)


# ============================================================
# AUTOMATIC MONTHLY CALCULATION
# ============================================================

def calculate_monthly_worker_data(
    worker_id,
    worker_start_date,
    year,
    month
):

    if not worker_start_date:
        return None

    month_start = date(year, month, 1)
    month_end = get_end_of_month(year, month)

    worker_start = pd.to_datetime(
        worker_start_date
    ).date()

    # Worker had not started yet
    if worker_start > month_end:
        return None

    period_start = max(
        worker_start,
        month_start
    )

    start_text = period_start.strftime("%Y-%m-%d")
    end_text = month_end.strftime("%Y-%m-%d")

    calendar_days = (
        month_end - period_start
    ).days + 1

    # --------------------------------------------------------
    # ACTUAL WORK RECORDS
    # Full Day = 1.0
    # Half Day = 0.5
    # --------------------------------------------------------

    work_df = run_query("""
        SELECT
            COALESCE(SUM(work_days), 0) AS total_worked_days,
            COALESCE(SUM(ot_hours), 0) AS total_ot_hours,
            COUNT(*) AS attendance_records
        FROM logs
        WHERE worker_id = ?
        AND work_date >= ?
        AND work_date <= ?
    """, (
        worker_id,
        start_text,
        end_text
    ))

    actual_worked_days = float(
        work_df.iloc[0]["total_worked_days"]
    )

    total_ot_hours = float(
        work_df.iloc[0]["total_ot_hours"]
    )

    attendance_records = int(
        work_df.iloc[0]["attendance_records"]
    )

    # --------------------------------------------------------
    # LEAVE RECORDS
    # --------------------------------------------------------

    leave_df = run_query("""
        SELECT leave_date, leave_type
        FROM leaves
        WHERE worker_id = ?
        AND leave_date >= ?
        AND leave_date <= ?
    """, (
        worker_id,
        start_text,
        end_text
    ))

    paid_leave_days = 0.0
    unpaid_leave_days = 0.0

    paid_types = [
        "Casual Leave",
        "Sick Leave",
        "Festival / Public Holiday"
    ]

    for _, leave in leave_df.iterrows():

        if leave["leave_type"] in paid_types:
            paid_leave_days += 1.0
        else:
            unpaid_leave_days += 1.0

    # --------------------------------------------------------
    # FINAL WORKED / PAYABLE DAYS
    #
    # If attendance records exist:
    # actual full + half days
    # + paid leave days
    #
    # If no attendance records exist:
    # calendar period
    # - unpaid leave days
    # --------------------------------------------------------

    if attendance_records > 0:

        worked_days = (
            actual_worked_days
            + paid_leave_days
        )

        worked_days = min(
            worked_days,
            float(calendar_days)
        )

    else:

        worked_days = max(
            0.0,
            float(calendar_days) - unpaid_leave_days
        )

    # --------------------------------------------------------
    # MONEY TAKEN / ADVANCES
    # --------------------------------------------------------

    advance_df = run_query("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_advance
        FROM advances
        WHERE worker_id = ?
        AND advance_date >= ?
        AND advance_date <= ?
    """, (
        worker_id,
        start_text,
        end_text
    ))

    total_advance = float(
        advance_df.iloc[0]["total_advance"]
    )

    # --------------------------------------------------------
    # SHOP ITEMS
    # --------------------------------------------------------

    shop_df = run_query("""
        SELECT
            COALESCE(SUM(item_cost), 0) AS total_shop
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date >= ?
        AND entry_date <= ?
    """, (
        worker_id,
        start_text,
        end_text
    ))

    total_shop = float(
        shop_df.iloc[0]["total_shop"]
    )

    return {
        "period_start": period_start,
        "period_end": month_end,
        "calendar_days": float(calendar_days),
        "actual_worked_days": actual_worked_days,
        "paid_leave_days": paid_leave_days,
        "unpaid_leave_days": unpaid_leave_days,
        "worked_days": worked_days,
        "total_ot_hours": total_ot_hours,
        "total_advance": total_advance,
        "total_shop": total_shop,
        "attendance_records": attendance_records
    }


# ============================================================
# EXPORT FUNCTIONS
# ============================================================

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")


def generate_excel():

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        load_workers().to_excel(
            writer,
            sheet_name="Workers",
            index=False
        )

        load_logs().to_excel(
            writer,
            sheet_name="Attendance_OT",
            index=False
        )

        load_leaves().to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        load_advances().to_excel(
            writer,
            sheet_name="Money_Taken",
            index=False
        )

        load_consumption().to_excel(
            writer,
            sheet_name="Shop_Items",
            index=False
        )

        load_monthly_payroll().to_excel(
            writer,
            sheet_name="Monthly_Payroll",
            index=False
        )

    return output.getvalue()


# ============================================================
# LOAD DATA
# ============================================================

df_workers = load_workers()
df_logs = load_logs()
df_consumption = load_consumption()
df_leaves = load_leaves()
df_advances = load_advances()
df_payroll = load_monthly_payroll()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Go to:",
    [
        "📊 Dashboard",
        "👥 Manage Workers",
        "📝 Daily Work & OT",
        "🌴 Leaves & Holidays",
        "🛒 Shop Items",
        "💵 Money Taken / Advance",
        "💰 Monthly Financial Payout",
        "🔎 Search Worker Records"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Records")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Export All Records (Excel)",
    data=excel_data,
    file_name=f"workshop_records_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("📄 Export Individual CSV Files"):

    st.download_button(
        "Workers CSV",
        convert_df_to_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Attendance CSV",
        convert_df_to_csv(df_logs),
        f"attendance_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Leaves CSV",
        convert_df_to_csv(df_leaves),
        f"leaves_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Money Taken CSV",
        convert_df_to_csv(df_advances),
        f"money_taken_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Monthly Payroll CSV",
        convert_df_to_csv(df_payroll),
        f"monthly_payroll_{date.today()}.csv",
        "text/csv"
    )


# ============================================================
# DASHBOARD
# ============================================================

if menu == "📊 Dashboard":

    st.subheader("📊 Workshop Dashboard")

    total_workers = len(df_workers)

    if df_payroll.empty:

        total_earned = 0.0
        total_paid = 0.0
        total_due = 0.0
        total_taken = 0.0

    else:

        total_earned = pd.to_numeric(
            df_payroll["Total Earned (NPR)"],
            errors="coerce"
        ).fillna(0).sum()

        total_paid = pd.to_numeric(
            df_payroll["Amount Paid (NPR)"],
            errors="coerce"
        ).fillna(0).sum()

        total_due = pd.to_numeric(
            df_payroll["Balance Due (NPR)"],
            errors="coerce"
        ).fillna(0).sum()

        total_taken = pd.to_numeric(
            df_payroll["Money Taken (NPR)"],
            errors="coerce"
        ).fillna(0).sum()

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Total Workers", total_workers)
    c2.metric("Total Earned", f"NPR {total_earned:,.2f}")
    c3.metric("Money Taken", f"NPR {total_taken:,.2f}")
    c4.metric("Total Paid", f"NPR {total_paid:,.2f}")
    c5.metric("Balance Due", f"NPR {total_due:,.2f}")

    st.markdown("---")
    st.subheader("📅 Monthly Payroll Records")

    if df_payroll.empty:
        st.info("No monthly payroll records yet.")
    else:

        display_payroll = df_payroll.copy()

        display_payroll["Month"] = (
            display_payroll["Month Number"]
            .apply(lambda x: calendar.month_name[int(x)])
            + " "
            + display_payroll["Year"].astype(str)
        )

        st.dataframe(
            display_payroll,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# MANAGE WORKERS
# ============================================================

elif menu == "👥 Manage Workers":

    st.subheader("👥 Manage Workshop Workers")

    col_add, col_delete = st.columns(2)

    with col_add:

        st.markdown("### ➕ Add New Worker")

        with st.form(
            "add_worker_form",
            clear_on_submit=True
        ):

            worker_id = get_next_id(
                "W",
                "workers",
                "worker_id"
            )

            worker_name = st.text_input("Worker Full Name")
            worker_phone = st.text_input("Mobile Number")

            worker_skill = st.selectbox(
                "Role / Skill",
                [
                    "Specialist Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Helper"
                ]
            )

            worker_start = st.date_input(
                "Date Started Working",
                date.today()
            )

            submit_worker = st.form_submit_button(
                "Register Worker"
            )

            if submit_worker:

                if not worker_name.strip():
                    st.error("Please enter the worker name.")

                else:

                    run_action("""
                        INSERT INTO workers
                        (
                            worker_id,
                            name,
                            phone,
                            skill,
                            start_date
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        worker_id,
                        worker_name.strip(),
                        worker_phone.strip(),
                        worker_skill,
                        worker_start.strftime("%Y-%m-%d")
                    ))

                    st.success(
                        f"{worker_name} added successfully."
                    )

                    st.rerun()

    with col_delete:

        st.markdown("### ❌ Delete Worker")

        if df_workers.empty:
            st.info("No workers found.")
        else:

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "Select Worker",
                worker_options,
                key="delete_worker"
            )

            selected_id = selected.split(" - ")[0]

            if st.button(
                "Delete Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (selected_id,)
                )

                st.success("Worker deleted.")
                st.rerun()

    st.markdown("---")
    st.dataframe(
        load_workers(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# DAILY WORK AND HALF DAY / FULL DAY
# ============================================================

elif menu == "📝 Daily Work & OT":

    st.subheader(
        "📝 Daily Work, Full Day, Half Day & OT"
    )

    if df_workers.empty:

        st.warning(
            "Please register a worker first."
        )

    else:

        col_add, col_delete = st.columns(2)

        with col_add:

            st.markdown("### ➕ Add Daily Work Record")

            with st.form(
                "daily_work_form",
                clear_on_submit=True
            ):

                log_id = get_next_id(
                    "L",
                    "logs",
                    "log_id"
                )

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                selected_worker = st.selectbox(
                    "Select Worker",
                    worker_options
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                work_day = st.date_input(
                    "Work Date",
                    date.today()
                )

                work_type = st.selectbox(
                    "Work Type",
                    [
                        "Full Day",
                        "Half Day"
                    ]
                )

                if work_type == "Full Day":
                    work_days = 1.0
                else:
                    work_days = 0.5

                ot_hours = st.number_input(
                    "OT Hours",
                    min_value=0.0,
                    value=0.0,
                    step=0.5
                )

                ot_notes = st.text_input(
                    "OT Details"
                )

                remarks = st.text_input(
                    "Work / Shift Remarks"
                )

                submit = st.form_submit_button(
                    "💾 Save Work Record"
                )

                if submit:

                    existing = run_query("""
                        SELECT log_id
                        FROM logs
                        WHERE worker_id = ?
                        AND work_date = ?
                    """, (
                        worker_id,
                        work_day.strftime("%Y-%m-%d")
                    ))

                    if not existing.empty:

                        st.error(
                            "This worker already has a work record for this date."
                        )

                    else:

                        run_action("""
                            INSERT INTO logs
                            (
                                log_id,
                                worker_id,
                                work_date,
                                work_days,
                                ot_hours,
                                ot_notes,
                                remarks
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            log_id,
                            worker_id,
                            work_day.strftime("%Y-%m-%d"),
                            work_days,
                            ot_hours,
                            ot_notes,
                            remarks
                        ))

                        st.success(
                            f"{work_type} recorded successfully."
                        )

                        st.rerun()

        with col_delete:

            st.markdown("### ❌ Delete Work Record")

            if df_logs.empty:

                st.info("No work records found.")

            else:

                log_options = (
                    df_logs["Log ID"].astype(str)
                    + " - "
                    + df_logs["Worker Name"].astype(str)
                    + " - "
                    + df_logs["Date"].astype(str)
                )

                selected_log = st.selectbox(
                    "Select Record",
                    log_options,
                    key="delete_log"
                )

                log_id = selected_log.split(" - ")[0]

                if st.button(
                    "Delete Work Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM logs WHERE log_id = ?",
                        (log_id,)
                    )

                    st.success("Work record deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_logs(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# LEAVES AND HOLIDAYS
# ============================================================

elif menu == "🌴 Leaves & Holidays":

    st.subheader("🌴 Leaves & Holidays")

    if df_workers.empty:

        st.warning("Please add workers first.")

    else:

        col_add, col_delete = st.columns(2)

        with col_add:

            st.markdown("### ➕ Add Leave / Holiday")

            with st.form(
                "leave_form",
                clear_on_submit=True
            ):

                leave_id = get_next_id(
                    "LV",
                    "leaves",
                    "leave_id"
                )

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                selected_worker = st.selectbox(
                    "Select Worker",
                    worker_options
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                leave_day = st.date_input(
                    "Leave Date",
                    date.today()
                )

                leave_type = st.selectbox(
                    "Leave Type",
                    [
                        "Casual Leave",
                        "Sick Leave",
                        "Festival / Public Holiday",
                        "Unpaid Leave"
                    ]
                )

                reason = st.text_input(
                    "Reason / Remarks"
                )

                submit = st.form_submit_button(
                    "Save Leave"
                )

                if submit:

                    existing = run_query("""
                        SELECT leave_id
                        FROM leaves
                        WHERE worker_id = ?
                        AND leave_date = ?
                    """, (
                        worker_id,
                        leave_day.strftime("%Y-%m-%d")
                    ))

                    if not existing.empty:

                        st.error(
                            "A leave record already exists for this date."
                        )

                    else:

                        run_action("""
                            INSERT INTO leaves
                            (
                                leave_id,
                                worker_id,
                                leave_date,
                                leave_type,
                                reason
                            )
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            leave_id,
                            worker_id,
                            leave_day.strftime("%Y-%m-%d"),
                            leave_type,
                            reason
                        ))

                        st.success("Leave record saved.")
                        st.rerun()

        with col_delete:

            st.markdown("### ❌ Delete Leave")

            if df_leaves.empty:

                st.info("No leave records found.")

            else:

                leave_options = (
                    df_leaves["Leave ID"].astype(str)
                    + " - "
                    + df_leaves["Worker Name"].astype(str)
                    + " - "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "Select Leave",
                    leave_options
                )

                leave_id = selected_leave.split(
                    " - "
                )[0]

                if st.button(
                    "Delete Leave",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM leaves WHERE leave_id = ?",
                        (leave_id,)
                    )

                    st.success("Leave deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_leaves(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# SHOP ITEMS
# ============================================================

elif menu == "🛒 Shop Items":

    st.subheader(
        "🛒 Shop / Canteen Items Taken"
    )

    if df_workers.empty:

        st.warning("Please add workers first.")

    else:

        col_add, col_delete = st.columns(2)

        with col_add:

            with st.form(
                "shop_form",
                clear_on_submit=True
            ):

                item_id = get_next_id(
                    "C",
                    "shop_consumption",
                    "item_id"
                )

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                selected_worker = st.selectbox(
                    "Select Worker",
                    worker_options
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                item_date = st.date_input(
                    "Date",
                    date.today()
                )

                item_name = st.text_input(
                    "Item Name"
                )

                item_cost = st.number_input(
                    "Cost (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=10.0
                )

                notes = st.text_input("Notes")

                submit = st.form_submit_button(
                    "Record Item"
                )

                if submit and item_name.strip():

                    run_action("""
                        INSERT INTO shop_consumption
                        (
                            item_id,
                            worker_id,
                            entry_date,
                            item_name,
                            item_cost,
                            notes
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        item_id,
                        worker_id,
                        item_date.strftime("%Y-%m-%d"),
                        item_name,
                        item_cost,
                        notes
                    ))

                    st.success("Shop item recorded.")
                    st.rerun()

        with col_delete:

            if df_consumption.empty:

                st.info("No shop records found.")

            else:

                item_options = (
                    df_consumption["Item ID"].astype(str)
                    + " - "
                    + df_consumption["Worker Name"].astype(str)
                    + " - "
                    + df_consumption["Item Consumed"].astype(str)
                )

                selected_item = st.selectbox(
                    "Select Shop Record",
                    item_options
                )

                item_id = selected_item.split(
                    " - "
                )[0]

                if st.button(
                    "Delete Shop Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM shop_consumption WHERE item_id = ?",
                        (item_id,)
                    )

                    st.success("Shop record deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_consumption(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# MONEY TAKEN / ADVANCE
# ============================================================

elif menu == "💵 Money Taken / Advance":

    st.subheader(
        "💵 Worker Money Taken / Advances"
    )

    if df_workers.empty:

        st.warning("Please add workers first.")

    else:

        col_add, col_delete = st.columns(2)

        with col_add:

            with st.form(
                "advance_form",
                clear_on_submit=True
            ):

                advance_id = get_next_id(
                    "A",
                    "advances",
                    "advance_id"
                )

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                selected_worker = st.selectbox(
                    "Select Worker",
                    worker_options
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                advance_date = st.date_input(
                    "Date Money Taken",
                    date.today()
                )

                amount = st.number_input(
                    "Amount Taken (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

                reason = st.text_input(
                    "Reason"
                )

                submit = st.form_submit_button(
                    "Record Money Taken"
                )

                if submit:

                    if amount <= 0:

                        st.error(
                            "Amount must be greater than zero."
                        )

                    else:

                        run_action("""
                            INSERT INTO advances
                            (
                                advance_id,
                                worker_id,
                                advance_date,
                                amount,
                                reason
                            )
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            advance_id,
                            worker_id,
                            advance_date.strftime("%Y-%m-%d"),
                            amount,
                            reason
                        ))

                        st.success(
                            "Money taken recorded."
                        )

                        st.rerun()

        with col_delete:

            if df_advances.empty:

                st.info("No money records found.")

            else:

                advance_options = (
                    df_advances["Advance ID"].astype(str)
                    + " - "
                    + df_advances["Worker Name"].astype(str)
                    + " - NPR "
                    + df_advances["Amount (NPR)"].astype(str)
                )

                selected_advance = st.selectbox(
                    "Select Money Record",
                    advance_options
                )

                advance_id = selected_advance.split(
                    " - "
                )[0]

                if st.button(
                    "Delete Money Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM advances WHERE advance_id = ?",
                        (advance_id,)
                    )

                    st.success("Money record deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_advances(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# MONTHLY FINANCIAL PAYOUT
# ============================================================

elif menu == "💰 Monthly Financial Payout":

    st.subheader(
        "💰 Automatic Monthly Salary & Payout"
    )

    if df_workers.empty:

        st.warning(
            "Please register workers first."
        )

    else:

        col1, col2, col3 = st.columns(3)

        with col1:

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "Select Worker",
                worker_options
            )

        with col2:

            selected_year = st.selectbox(
                "Year",
                list(
                    range(
                        date.today().year - 2,
                        date.today().year + 3
                    )
                ),
                index=2
            )

        with col3:

            selected_month = st.selectbox(
                "Month",
                list(range(1, 13)),
                index=date.today().month - 1,
                format_func=lambda x: calendar.month_name[x]
            )

        selected_worker_id = selected_worker.split(
            " - "
        )[0]

        worker_row = df_workers[
            df_workers["Worker ID"] == selected_worker_id
        ].iloc[0]

        calculation = calculate_monthly_worker_data(
            selected_worker_id,
            worker_row["Start Date"],
            selected_year,
            selected_month
        )

        if calculation is None:

            st.warning(
                "This worker had not started during the selected month."
            )

        else:

            st.markdown("---")
            st.subheader("📅 Automatic Monthly Calculation")

            c1, c2, c3, c4, c5 = st.columns(5)

            c1.metric(
                "Period Days",
                f"{calculation['calendar_days']:.1f}"
            )

            c2.metric(
                "Actual Work Days",
                f"{calculation['actual_worked_days']:.1f}"
            )

            c3.metric(
                "Paid Leave",
                f"{calculation['paid_leave_days']:.1f}"
            )

            c4.metric(
                "Unpaid Leave",
                f"{calculation['unpaid_leave_days']:.1f}"
            )

            c5.metric(
                "Final Payable Days",
                f"{calculation['worked_days']:.1f}"
            )

            st.info(
                f"📅 Salary Period: "
                f"{calculation['period_start'].strftime('%d %B %Y')} "
                f"to "
                f"{calculation['period_end'].strftime('%d %B %Y')}"
            )

            st.caption(
                "Full Day = 1.0 | Half Day = 0.5 | "
                "Paid Leave = payable | Unpaid Leave = deducted"
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Total OT",
                f"{calculation['total_ot_hours']:.1f} Hours"
            )

            c2.metric(
                "Money Taken",
                f"NPR {calculation['total_advance']:,.2f}"
            )

            c3.metric(
                "Shop Deduction",
                f"NPR {calculation['total_shop']:,.2f}"
            )

            existing_payroll = run_query("""
                SELECT *
                FROM monthly_payroll
                WHERE worker_id = ?
                AND payroll_year = ?
                AND payroll_month = ?
            """, (
                selected_worker_id,
                selected_year,
                selected_month
            ))

            if existing_payroll.empty:

                payroll_id = get_next_id(
                    "MP",
                    "monthly_payroll",
                    "payroll_id"
                )

                default_wage = 1500.0
                default_ot_rate = 200.0
                default_paid = 0.0

            else:

                existing = existing_payroll.iloc[0]

                payroll_id = existing["payroll_id"]
                default_wage = float(existing["daily_wage"])
                default_ot_rate = float(existing["ot_rate"])
                default_paid = float(existing["paid_amount"])

            st.markdown("---")
            st.subheader("🧾 Payroll Details")

            with st.form("monthly_payroll_form"):

                daily_wage = st.number_input(
                    "Daily Wage (NPR)",
                    min_value=0.0,
                    value=default_wage,
                    step=100.0
                )

                ot_rate = st.number_input(
                    "OT Rate Per Hour (NPR)",
                    min_value=0.0,
                    value=default_ot_rate,
                    step=50.0
                )

                paid_amount = st.number_input(
                    "Amount Paid to Worker (NPR)",
                    min_value=0.0,
                    value=default_paid,
                    step=100.0
                )

                base_salary = (
                    calculation["worked_days"]
                    * daily_wage
                )

                ot_amount = (
                    calculation["total_ot_hours"]
                    * ot_rate
                )

                total_earned = (
                    base_salary
                    + ot_amount
                )

                balance_due = (
                    total_earned
                    - calculation["total_advance"]
                    - calculation["total_shop"]
                    - paid_amount
                )

                p1, p2, p3 = st.columns(3)

                p1.metric(
                    "Base Salary",
                    f"NPR {base_salary:,.2f}"
                )

                p2.metric(
                    "OT Amount",
                    f"NPR {ot_amount:,.2f}"
                )

                p3.metric(
                    "Balance Due",
                    f"NPR {balance_due:,.2f}"
                )

                submit_payroll = st.form_submit_button(
                    "💾 Save / Update Monthly Payroll"
                )

                if submit_payroll:

                    if balance_due <= 0:
                        status = "Fully Settled"
                    elif paid_amount > 0:
                        status = "Partially Paid"
                    else:
                        status = "Unpaid"

                    if existing_payroll.empty:

                        run_action("""
                            INSERT INTO monthly_payroll
                            (
                                payroll_id,
                                worker_id,
                                payroll_year,
                                payroll_month,
                                period_start,
                                period_end,
                                calendar_days,
                                paid_leave_days,
                                unpaid_leave_days,
                                worked_days,
                                daily_wage,
                                base_salary,
                                total_ot_hours,
                                ot_rate,
                                ot_amount,
                                total_earned,
                                advance_deduction,
                                shop_deduction,
                                paid_amount,
                                balance_due,
                                status
                            )
                            VALUES
                            (
                                ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                        """, (
                            payroll_id,
                            selected_worker_id,
                            selected_year,
                            selected_month,
                            calculation["period_start"].strftime("%Y-%m-%d"),
                            calculation["period_end"].strftime("%Y-%m-%d"),
                            calculation["calendar_days"],
                            calculation["paid_leave_days"],
                            calculation["unpaid_leave_days"],
                            calculation["worked_days"],
                            daily_wage,
                            base_salary,
                            calculation["total_ot_hours"],
                            ot_rate,
                            ot_amount,
                            total_earned,
                            calculation["total_advance"],
                            calculation["total_shop"],
                            paid_amount,
                            balance_due,
                            status
                        ))

                    else:

                        run_action("""
                            UPDATE monthly_payroll
                            SET
                                period_start = ?,
                                period_end = ?,
                                calendar_days = ?,
                                paid_leave_days = ?,
                                unpaid_leave_days = ?,
                                worked_days = ?,
                                daily_wage = ?,
                                base_salary = ?,
                                total_ot_hours = ?,
                                ot_rate = ?,
                                ot_amount = ?,
                                total_earned = ?,
                                advance_deduction = ?,
                                shop_deduction = ?,
                                paid_amount = ?,
                                balance_due = ?,
                                status = ?
                            WHERE worker_id = ?
                            AND payroll_year = ?
                            AND payroll_month = ?
                        """, (
                            calculation["period_start"].strftime("%Y-%m-%d"),
                            calculation["period_end"].strftime("%Y-%m-%d"),
                            calculation["calendar_days"],
                            calculation["paid_leave_days"],
                            calculation["unpaid_leave_days"],
                            calculation["worked_days"],
                            daily_wage,
                            base_salary,
                            calculation["total_ot_hours"],
                            ot_rate,
                            ot_amount,
                            total_earned,
                            calculation["total_advance"],
                            calculation["total_shop"],
                            paid_amount,
                            balance_due,
                            status,
                            selected_worker_id,
                            selected_year,
                            selected_month
                        ))

                    st.success(
                        "Monthly payroll saved successfully."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_monthly_payroll(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# SEARCH WORKER RECORDS
# ============================================================

elif menu == "🔎 Search Worker Records":

    st.subheader(
        "🔎 Search Worker and View Complete Records"
    )

    if df_workers.empty:

        st.warning("No workers available.")

    else:

        search_text = st.text_input(
            "Search Worker Name or Worker ID"
        )

        search_df = df_workers.copy()

        if search_text.strip():

            search_df = search_df[
                search_df["Name"].str.contains(
                    search_text,
                    case=False,
                    na=False
                )
                |
                search_df["Worker ID"].str.contains(
                    search_text,
                    case=False,
                    na=False
                )
            ]

        if search_df.empty:

            st.warning("No worker found.")

        else:

            worker_options = (
                search_df["Worker ID"].astype(str)
                + " - "
                + search_df["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "Select Worker",
                worker_options
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            worker = df_workers[
                df_workers["Worker ID"] == worker_id
            ].iloc[0]

            st.markdown("---")
            st.subheader(
                f"👤 {worker['Name']} - Complete Record"
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Worker ID",
                worker["Worker ID"]
            )

            c2.metric(
                "Started Work",
                str(worker["Start Date"])
                if pd.notna(worker["Start Date"])
                else "Not Set"
            )

            c3.metric(
                "Role",
                worker["Skill"]
            )

            c4.metric(
                "Phone",
                worker["Phone"]
            )

            # MONTHLY PAYROLL
            st.markdown("---")
            st.subheader(
                "💰 Monthly Worked Days & Payroll"
            )

            worker_payroll = load_monthly_payroll()

            worker_payroll = worker_payroll[
                worker_payroll["Worker ID"] == worker_id
            ].copy()

            if worker_payroll.empty:

                st.info(
                    "No monthly payroll records saved yet."
                )

            else:

                worker_payroll["Month"] = (
                    worker_payroll["Month Number"]
                    .apply(
                        lambda x: calendar.month_name[int(x)]
                    )
                    + " "
                    + worker_payroll["Year"].astype(str)
                )

                columns = [
                    "Month",
                    "Period Start",
                    "Period End",
                    "Worked Days",
                    "Paid Leave Days",
                    "Unpaid Leave Days",
                    "OT Hours",
                    "Total Earned (NPR)",
                    "Money Taken (NPR)",
                    "Shop Deduction (NPR)",
                    "Amount Paid (NPR)",
                    "Balance Due (NPR)",
                    "Status"
                ]

                st.dataframe(
                    worker_payroll[columns],
                    use_container_width=True,
                    hide_index=True
                )

            # DAILY WORK
            st.markdown("---")
            st.subheader(
                "📝 Daily Full Day / Half Day Records"
            )

            worker_logs = load_logs()

            worker_logs = worker_logs[
                worker_logs["Worker ID"] == worker_id
            ]

            if worker_logs.empty:

                st.info("No work records found.")

            else:

                total_work_days = pd.to_numeric(
                    worker_logs["Worked Days"],
                    errors="coerce"
                ).fillna(0).sum()

                total_ot = pd.to_numeric(
                    worker_logs["OT Hours"],
                    errors="coerce"
                ).fillna(0).sum()

                a1, a2 = st.columns(2)

                a1.metric(
                    "Total Recorded Work Days",
                    f"{total_work_days:.1f}"
                )

                a2.metric(
                    "Total Recorded OT",
                    f"{total_ot:.1f} Hours"
                )

                st.dataframe(
                    worker_logs,
                    use_container_width=True,
                    hide_index=True
                )

            # LEAVES
            st.markdown("---")
            st.subheader(
                "🌴 Holidays & Leave Records"
            )

            worker_leaves = load_leaves()

            worker_leaves = worker_leaves[
                worker_leaves["Worker ID"] == worker_id
            ]

            if worker_leaves.empty:
                st.info("No leave records found.")
            else:
                st.dataframe(
                    worker_leaves,
                    use_container_width=True,
                    hide_index=True
                )

            # MONEY TAKEN
            st.markdown("---")
            st.subheader(
                "💵 Money Taken / Advance"
            )

            worker_advances = load_advances()

            worker_advances = worker_advances[
                worker_advances["Worker ID"] == worker_id
            ]

            if worker_advances.empty:

                st.info("No money taken records found.")

            else:

                total_taken = pd.to_numeric(
                    worker_advances["Amount (NPR)"],
                    errors="coerce"
                ).fillna(0).sum()

                st.metric(
                    "Total Money Taken",
                    f"NPR {total_taken:,.2f}"
                )

                st.dataframe(
                    worker_advances,
                    use_container_width=True,
                    hide_index=True
                )

            # SHOP ITEMS
            st.markdown("---")
            st.subheader("🛒 Shop Items Taken")

            worker_shop = load_consumption()

            worker_shop = worker_shop[
                worker_shop["Worker ID"] == worker_id
            ]

            if worker_shop.empty:

                st.info("No shop items recorded.")

            else:

                total_shop = pd.to_numeric(
                    worker_shop["Cost (NPR)"],
                    errors="coerce"
                ).fillna(0).sum()

                st.metric(
                    "Total Shop Items Cost",
                    f"NPR {total_shop:,.2f}"
                )

                st.dataframe(
                    worker_shop,
                    use_container_width=True,
                    hide_index=True
                )
