import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import sqlite3
import io
import calendar
import uuid

# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Record System")
st.caption("👷 Attendance • 🌓 Half Days • 🌴 Leaves • ⏰ Overtime • 💰 Monthly Payroll")

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


def run_many(query, params_list):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(query, params_list)
        conn.commit()


def generate_id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:10].upper()}"


# ============================================================
# DATABASE SETUP
# ============================================================
def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # ----------------------------------------------------
        # WORKERS
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                skill TEXT,
                start_date TEXT
            )
        """)

        if not column_exists(cursor, "workers", "start_date"):
            cursor.execute("""
                ALTER TABLE workers
                ADD COLUMN start_date TEXT
            """)

        # ----------------------------------------------------
        # ATTENDANCE
        # Each selected date gets one record
        # Full Day = 1.0
        # Half Day = 0.5
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                attendance_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                day_value REAL NOT NULL DEFAULT 1.0,
                remarks TEXT,
                UNIQUE(worker_id, work_date),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # OVERTIME
        # OT money is directly entered
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS overtime (
                ot_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                ot_date TEXT NOT NULL,
                ot_money REAL NOT NULL DEFAULT 0,
                notes TEXT,
                UNIQUE(worker_id, ot_date),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # LEAVES / HOLIDAYS
        # SINGLE DATE ONLY
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                day_value REAL NOT NULL DEFAULT 1.0,
                reason TEXT,
                UNIQUE(worker_id, leave_date),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # SHOP CONSUMPTION
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # ADVANCES / MONEY TAKEN
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                advance_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                advance_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                reason TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # MONTHLY FINANCIAL RECORD
        # ONE RECORD PER WORKER PER MONTH
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                daily_wage REAL NOT NULL DEFAULT 0,
                worked_days REAL NOT NULL DEFAULT 0,
                basic_earned REAL NOT NULL DEFAULT 0,
                ot_earned REAL NOT NULL DEFAULT 0,
                total_earned REAL NOT NULL DEFAULT 0,
                advances REAL NOT NULL DEFAULT 0,
                shop_deductions REAL NOT NULL DEFAULT 0,
                paid_money REAL NOT NULL DEFAULT 0,
                remaining_due REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Unpaid',
                UNIQUE(worker_id, month_key),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        conn.commit()


init_db()


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


def load_attendance():
    return run_query("""
        SELECT
            a.attendance_id AS 'Attendance ID',
            a.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            a.work_date AS 'Work Date',
            a.day_value AS 'Worked Day Value',
            a.remarks AS 'Remarks'
        FROM attendance a
        LEFT JOIN workers w
            ON a.worker_id = w.worker_id
        ORDER BY a.work_date DESC, w.name
    """)


def load_overtime():
    return run_query("""
        SELECT
            o.ot_id AS 'OT ID',
            o.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            o.ot_date AS 'OT Date',
            o.ot_money AS 'OT Money (NPR)',
            o.notes AS 'OT Details'
        FROM overtime o
        LEFT JOIN workers w
            ON o.worker_id = w.worker_id
        ORDER BY o.ot_date DESC, w.name
    """)


def load_leaves():
    return run_query("""
        SELECT
            l.leave_id AS 'Leave ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.leave_date AS 'Leave Date',
            l.leave_type AS 'Leave Type',
            l.day_value AS 'Leave Day Value',
            l.reason AS 'Reason'
        FROM leaves l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.leave_date DESC, w.name
    """)


def load_consumption():
    return run_query("""
        SELECT
            s.item_id AS 'Item ID',
            s.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            s.entry_date AS 'Date',
            s.item_name AS 'Item',
            s.item_cost AS 'Cost (NPR)',
            s.notes AS 'Notes'
        FROM shop_consumption s
        LEFT JOIN workers w
            ON s.worker_id = w.worker_id
        ORDER BY s.entry_date DESC, w.name
    """)


def load_advances():
    return run_query("""
        SELECT
            a.advance_id AS 'Advance ID',
            a.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            a.advance_date AS 'Date',
            a.amount AS 'Money Taken (NPR)',
            a.reason AS 'Reason'
        FROM advances a
        LEFT JOIN workers w
            ON a.worker_id = w.worker_id
        ORDER BY a.advance_date DESC, w.name
    """)


def load_financials():
    return run_query("""
        SELECT
            f.payment_id AS 'Payment ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month',
            f.daily_wage AS 'Daily Wage (NPR)',
            f.worked_days AS 'Worked Days',
            f.basic_earned AS 'Basic Earned (NPR)',
            f.ot_earned AS 'OT Earned (NPR)',
            f.total_earned AS 'Total Earned (NPR)',
            f.advances AS 'Money Taken (NPR)',
            f.shop_deductions AS 'Shop Deductions (NPR)',
            f.paid_money AS 'Paid Money (NPR)',
            f.remaining_due AS 'Remaining Due (NPR)',
            f.status AS 'Status'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# DATE / MONTH FUNCTIONS
# ============================================================
def get_month_key(d):
    return d.strftime("%Y-%m")


def get_month_label(month_key):
    try:
        return datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
    except:
        return month_key


def month_range(month_key):
    year, month = map(int, month_key.split("-"))
    last_day = calendar.monthrange(year, month)[1]

    start = date(year, month, 1)
    end = date(year, month, last_day)

    return start, end


def get_available_months():
    dates = []

    tables = [
        ("attendance", "work_date"),
        ("leaves", "leave_date"),
        ("overtime", "ot_date"),
        ("shop_consumption", "entry_date"),
        ("advances", "advance_date")
    ]

    for table, column in tables:
        df = run_query(f"SELECT DISTINCT substr({column}, 1, 7) AS month_key FROM {table}")
        if not df.empty:
            dates.extend(df["month_key"].dropna().tolist())

    dates.append(date.today().strftime("%Y-%m"))

    return sorted(list(set(dates)), reverse=True)


# ============================================================
# WORKER MONTHLY CALCULATION
# ============================================================
def calculate_worker_month(worker_id, month_key, daily_wage):
    start_date, end_date = month_range(month_key)

    # Worker starting date
    worker_df = run_query("""
        SELECT start_date
        FROM workers
        WHERE worker_id = ?
    """, (worker_id,))

    worker_start = None

    if not worker_df.empty:
        value = worker_df.iloc[0]["start_date"]

        if value and pd.notna(value):
            try:
                worker_start = datetime.strptime(str(value), "%Y-%m-%d").date()
            except:
                worker_start = None

    # Attendance
    attendance_df = run_query("""
        SELECT COALESCE(SUM(day_value), 0) AS total
        FROM attendance
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    worked_days = float(attendance_df.iloc[0]["total"] or 0)

    # Leaves
    leaves_df = run_query("""
        SELECT COALESCE(SUM(day_value), 0) AS total
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    leave_days = float(leaves_df.iloc[0]["total"] or 0)

    # OT
    ot_df = run_query("""
        SELECT COALESCE(SUM(ot_money), 0) AS total
        FROM overtime
        WHERE worker_id = ?
        AND ot_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    ot_earned = float(ot_df.iloc[0]["total"] or 0)

    # Advances
    advance_df = run_query("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    advances = float(advance_df.iloc[0]["total"] or 0)

    # Shop deductions
    consumption_df = run_query("""
        SELECT COALESCE(SUM(item_cost), 0) AS total
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    shop_deductions = float(consumption_df.iloc[0]["total"] or 0)

    # Number of calendar days worker could have worked
    effective_start = start_date

    if worker_start and worker_start > effective_start:
        effective_start = worker_start

    if effective_start > end_date:
        possible_days = 0
    else:
        possible_days = (end_date - effective_start).days + 1

    # Attendance is the actual calculation
    # Leave is shown separately.
    # If attendance was accidentally entered on a leave date,
    # remove that overlapping value.
    overlap_df = run_query("""
        SELECT COALESCE(SUM(a.day_value), 0) AS total
        FROM attendance a
        INNER JOIN leaves l
            ON a.worker_id = l.worker_id
            AND a.work_date = l.leave_date
        WHERE a.worker_id = ?
        AND a.work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    overlap_days = float(overlap_df.iloc[0]["total"] or 0)

    final_worked_days = max(0, worked_days - overlap_days)

    basic_earned = final_worked_days * daily_wage
    total_earned = basic_earned + ot_earned

    return {
        "possible_days": possible_days,
        "raw_worked_days": worked_days,
        "leave_days": leave_days,
        "overlap_days": overlap_days,
        "worked_days": final_worked_days,
        "basic_earned": basic_earned,
        "ot_earned": ot_earned,
        "total_earned": total_earned,
        "advances": advances,
        "shop_deductions": shop_deductions
    }


# ============================================================
# EXPORT FUNCTIONS
# ============================================================
def generate_excel():
    workers = load_workers()
    attendance = load_attendance()
    overtime = load_overtime()
    leaves = load_leaves()
    consumption = load_consumption()
    advances = load_advances()
    financials = load_financials()

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        workers.to_excel(writer, sheet_name="Workers", index=False)
        attendance.to_excel(writer, sheet_name="Attendance", index=False)
        overtime.to_excel(writer, sheet_name="Overtime", index=False)
        leaves.to_excel(writer, sheet_name="Leaves", index=False)
        consumption.to_excel(writer, sheet_name="Shop Items", index=False)
        advances.to_excel(writer, sheet_name="Advances", index=False)
        financials.to_excel(writer, sheet_name="Financials", index=False)

    return output.getvalue()


def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")


# ============================================================
# LOAD DATA
# ============================================================
df_workers = load_workers()
df_attendance = load_attendance()
df_overtime = load_overtime()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_advances = load_advances()
df_financials = load_financials()


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Select Section",
    [
        "📊 Dashboard",
        "👷 Manage Workers",
        "📅 Work Attendance",
        "⏰ Overtime",
        "🌴 Leaves & Holidays",
        "🛒 Shop Items",
        "💵 Money Taken / Advance",
        "💰 Monthly Financial Payout",
        "🔎 Worker Search & Monthly Records"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Reports")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Download Complete Excel Report",
    excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("📄 Download CSV Files"):
    st.download_button(
        "👷 Workers CSV",
        convert_df_to_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "📅 Attendance CSV",
        convert_df_to_csv(df_attendance),
        f"attendance_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "⏰ Overtime CSV",
        convert_df_to_csv(df_overtime),
        f"overtime_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "🌴 Leaves CSV",
        convert_df_to_csv(df_leaves),
        f"leaves_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "🛒 Shop Items CSV",
        convert_df_to_csv(df_consumption),
        f"shop_items_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "💵 Advances CSV",
        convert_df_to_csv(df_advances),
        f"advances_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "💰 Financials CSV",
        convert_df_to_csv(df_financials),
        f"financials_{date.today()}.csv",
        "text/csv"
    )


# ============================================================
# 1. DASHBOARD
# ============================================================
if menu == "📊 Dashboard":

    st.subheader("📊 Workshop Monthly Dashboard")

    if df_financials.empty:
        total_earned = 0.0
        total_advances = 0.0
        total_shop = 0.0
        total_paid = 0.0
        total_due = 0.0
    else:
        total_earned = float(df_financials["Total Earned (NPR)"].sum())
        total_advances = float(df_financials["Money Taken (NPR)"].sum())
        total_shop = float(df_financials["Shop Deductions (NPR)"].sum())
        total_paid = float(df_financials["Paid Money (NPR)"].sum())
        total_due = float(df_financials["Remaining Due (NPR)"].sum())

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("💰 Total Earned", f"NPR {total_earned:,.2f}")
    c2.metric("💵 Money Taken", f"NPR {total_advances:,.2f}")
    c3.metric("🛒 Shop Deductions", f"NPR {total_shop:,.2f}")
    c4.metric("✅ Paid", f"NPR {total_paid:,.2f}")
    c5.metric("📌 Remaining Due", f"NPR {total_due:,.2f}")

    st.markdown("---")

    months = get_available_months()

    selected_month = st.selectbox(
        "🗓️ Select Month",
        months,
        format_func=get_month_label
    )

    st.subheader(f"📅 Summary: {get_month_label(selected_month)}")

    month_start, month_end = month_range(selected_month)

    attendance_month = df_attendance.copy()

    if not attendance_month.empty:
        attendance_month = attendance_month[
            attendance_month["Work Date"].str.startswith(selected_month)
        ]

    overtime_month = df_overtime.copy()

    if not overtime_month.empty:
        overtime_month = overtime_month[
            overtime_month["OT Date"].str.startswith(selected_month)
        ]

    leave_month = df_leaves.copy()

    if not leave_month.empty:
        leave_month = leave_month[
            leave_month["Leave Date"].str.startswith(selected_month)
        ]

    total_work_days = (
        attendance_month["Worked Day Value"].sum()
        if not attendance_month.empty else 0
    )

    total_ot = (
        overtime_month["OT Money (NPR)"].sum()
        if not overtime_month.empty else 0
    )

    total_leave = (
        leave_month["Leave Day Value"].sum()
        if not leave_month.empty else 0
    )

    a, b, c = st.columns(3)

    a.metric("👷 Total Worked Days", f"{total_work_days:.1f}")
    b.metric("⏰ Total OT Money", f"NPR {total_ot:,.2f}")
    c.metric("🌴 Total Leave Days", f"{total_leave:.1f}")

    st.markdown("---")

    st.subheader("📋 Monthly Financial Records")

    if df_financials.empty:
        st.info("No monthly financial records created yet.")
    else:
        month_financials = df_financials[
            df_financials["Month"] == selected_month
        ]

        st.dataframe(
            month_financials,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# 2. MANAGE WORKERS
# ============================================================
elif menu == "👷 Manage Workers":

    st.subheader("👷 Manage Workshop Workers")

    left, right = st.columns(2)

    with left:

        st.markdown("### ➕ Add New Worker")

        with st.form("add_worker_form", clear_on_submit=True):

            worker_name = st.text_input("👤 Worker Full Name")

            worker_phone = st.text_input("📱 Mobile Number")

            worker_skill = st.selectbox(
                "🛠️ Worker Role / Skill",
                [
                    "Specialist Carpenter",
                    "Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Painter",
                    "Helper",
                    "Other"
                ]
            )

            worker_start_date = st.date_input(
                "📅 Date Worker Started Working",
                value=date.today()
            )

            submit_worker = st.form_submit_button(
                "➕ Register Worker"
            )

            if submit_worker:

                if not worker_name.strip():
                    st.error("❌ Please enter worker name.")
                else:
                    worker_id = generate_id("W")

                    run_action("""
                        INSERT INTO workers
                        (worker_id, name, phone, skill, start_date)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        worker_id,
                        worker_name.strip(),
                        worker_phone.strip(),
                        worker_skill,
                        worker_start_date.strftime("%Y-%m-%d")
                    ))

                    st.success("✅ Worker added successfully!")
                    st.rerun()

    with right:

        st.markdown("### 🗑️ Delete Worker")

        if df_workers.empty:
            st.info("No workers available.")
        else:

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            delete_worker_id = selected_worker.split(" - ")[0]

            if st.button(
                "❌ Delete Selected Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (delete_worker_id,)
                )

                st.success("✅ Worker deleted successfully.")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Registered Workers")

    st.dataframe(
        load_workers(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 3. WORK ATTENDANCE
# ============================================================
elif menu == "📅 Work Attendance":

    st.subheader("📅 Record Worker Attendance")

    if df_workers.empty:

        st.warning("⚠️ Please add a worker first.")

    else:

        st.info(
            "💡 You can select one date or multiple dates. "
            "Each selected date will be saved as a separate attendance record."
        )

        left, right = st.columns(2)

        with left:

            st.markdown("### ➕ Add Work Attendance")

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="attendance_worker"
            )

            attendance_worker_id = selected_worker.split(" - ")[0]

            selected_dates = st.date_input(
                "📅 Select Work Date(s)",
                value=date.today(),
                key="attendance_dates"
            )

            day_type = st.radio(
                "🌓 Type of Work",
                ["☀️ Full Day", "🌗 Half Day"],
                horizontal=True
            )

            if day_type == "☀️ Full Day":
                day_value = 1.0
            else:
                day_value = 0.5

            attendance_remarks = st.text_input(
                "📝 Remarks"
            )

            # Convert one or multiple dates safely
            if isinstance(selected_dates, tuple):

                if len(selected_dates) == 2:
                    start_d, end_d = selected_dates

                    if start_d and end_d:
                        dates_to_save = []
                        current_date = start_d

                        while current_date <= end_d:
                            dates_to_save.append(current_date)
                            current_date += timedelta(days=1)
                    else:
                        dates_to_save = []
                else:
                    dates_to_save = []

            elif isinstance(selected_dates, list):
                dates_to_save = selected_dates

            else:
                dates_to_save = [selected_dates]

            if dates_to_save:
                st.success(
                    f"📅 Selected {len(dates_to_save)} date(s) "
                    f"= {len(dates_to_save) * day_value:.1f} worked day value"
                )

            if st.button(
                "💾 Save Work Attendance",
                type="primary"
            ):

                saved = 0
                skipped = 0

                for work_d in dates_to_save:

                    work_date_string = work_d.strftime("%Y-%m-%d")

                    existing = run_query("""
                        SELECT attendance_id
                        FROM attendance
                        WHERE worker_id = ?
                        AND work_date = ?
                    """, (
                        attendance_worker_id,
                        work_date_string
                    ))

                    if existing.empty:

                        run_action("""
                            INSERT INTO attendance
                            (attendance_id, worker_id, work_date, day_value, remarks)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            generate_id("A"),
                            attendance_worker_id,
                            work_date_string,
                            day_value,
                            attendance_remarks
                        ))

                        saved += 1

                    else:
                        skipped += 1

                if saved > 0:
                    st.success(
                        f"✅ Saved {saved} attendance record(s)."
                    )

                if skipped > 0:
                    st.warning(
                        f"⚠️ {skipped} record(s) already existed and were skipped."
                    )

                st.rerun()

        with right:

            st.markdown("### 🗑️ Delete Attendance")

            if df_attendance.empty:

                st.info("No attendance records available.")

            else:

                attendance_options = (
                    df_attendance["Attendance ID"].astype(str)
                    + " - "
                    + df_attendance["Worker Name"].astype(str)
                    + " - "
                    + df_attendance["Work Date"].astype(str)
                )

                selected_attendance = st.selectbox(
                    "📋 Select Attendance Record",
                    attendance_options
                )

                delete_attendance_id = selected_attendance.split(" - ")[0]

                if st.button(
                    "❌ Delete Attendance Record"
                ):

                    run_action("""
                        DELETE FROM attendance
                        WHERE attendance_id = ?
                    """, (delete_attendance_id,))

                    st.success("✅ Attendance deleted.")
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Attendance Records")

    st.dataframe(
        load_attendance(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 4. OVERTIME
# ============================================================
elif menu == "⏰ Overtime":

    st.subheader("⏰ Worker Overtime Record")

    if df_workers.empty:

        st.warning("⚠️ Please add a worker first.")

    else:

        left, right = st.columns(2)

        with left:

            st.markdown("### ➕ Record Overtime")

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="ot_worker"
            )

            ot_worker_id = selected_worker.split(" - ")[0]

            ot_date = st.date_input(
                "📅 Overtime Date",
                value=date.today()
            )

            did_ot = st.radio(
                "⏰ Did the worker do overtime?",
                ["❌ No", "✅ Yes"],
                horizontal=True
            )

            if did_ot == "✅ Yes":

                ot_money = st.number_input(
                    "💰 Total Overtime Money (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

                ot_notes = st.text_input(
                    "📝 OT Work Details"
                )

                if st.button(
                    "💾 Save Overtime",
                    type="primary"
                ):

                    if ot_money <= 0:

                        st.error(
                            "❌ Please enter overtime money."
                        )

                    else:

                        existing = run_query("""
                            SELECT ot_id
                            FROM overtime
                            WHERE worker_id = ?
                            AND ot_date = ?
                        """, (
                            ot_worker_id,
                            ot_date.strftime("%Y-%m-%d")
                        ))

                        if existing.empty:

                            run_action("""
                                INSERT INTO overtime
                                (ot_id, worker_id, ot_date, ot_money, notes)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                generate_id("OT"),
                                ot_worker_id,
                                ot_date.strftime("%Y-%m-%d"),
                                ot_money,
                                ot_notes
                            ))

                        else:

                            run_action("""
                                UPDATE overtime
                                SET ot_money = ?,
                                    notes = ?
                                WHERE worker_id = ?
                                AND ot_date = ?
                            """, (
                                ot_money,
                                ot_notes,
                                ot_worker_id,
                                ot_date.strftime("%Y-%m-%d")
                            ))

                        st.success(
                            f"✅ OT saved: NPR {ot_money:,.2f}"
                        )

                        st.rerun()

            else:

                st.info(
                    "ℹ️ No overtime will be recorded."
                )

        with right:

            st.markdown("### 🗑️ Delete Overtime")

            if df_overtime.empty:

                st.info("No overtime records.")

            else:

                ot_options = (
                    df_overtime["OT ID"].astype(str)
                    + " - "
                    + df_overtime["Worker Name"].astype(str)
                    + " - "
                    + df_overtime["OT Date"].astype(str)
                )

                selected_ot = st.selectbox(
                    "⏰ Select OT Record",
                    ot_options
                )

                delete_ot_id = selected_ot.split(" - ")[0]

                if st.button(
                    "❌ Delete OT Record"
                ):

                    run_action("""
                        DELETE FROM overtime
                        WHERE ot_id = ?
                    """, (delete_ot_id,))

                    st.success("✅ Overtime deleted.")
                    st.rerun()

    st.markdown("---")
    st.dataframe(
        load_overtime(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 5. LEAVES & HOLIDAYS
# ============================================================
elif menu == "🌴 Leaves & Holidays":

    st.subheader("🌴 Worker Leaves & Holidays")

    if df_workers.empty:

        st.warning("⚠️ Please add a worker first.")

    else:

        left, right = st.columns(2)

        with left:

            st.markdown("### ➕ Record Leave / Holiday")

            st.info(
                "📅 Leave/Holiday is recorded for ONE DATE ONLY."
            )

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="leave_worker"
            )

            leave_worker_id = selected_worker.split(" - ")[0]

            # SINGLE DATE ONLY
            leave_date = st.date_input(
                "📅 Leave / Holiday Date",
                value=date.today(),
                key="single_leave_date"
            )

            leave_type = st.selectbox(
                "🌴 Leave Type",
                [
                    "Casual Leave",
                    "Sick Leave",
                    "Festival / Public Holiday",
                    "Unpaid Leave",
                    "Personal Leave",
                    "Other"
                ]
            )

            leave_day_type = st.radio(
                "🌓 Leave Duration",
                [
                    "🌕 Full Day Leave",
                    "🌗 Half Day Leave"
                ],
                horizontal=True
            )

            leave_day_value = (
                1.0
                if leave_day_type == "🌕 Full Day Leave"
                else 0.5
            )

            leave_reason = st.text_input(
                "📝 Reason / Remarks"
            )

            if st.button(
                "💾 Save Leave / Holiday",
                type="primary"
            ):

                existing = run_query("""
                    SELECT leave_id
                    FROM leaves
                    WHERE worker_id = ?
                    AND leave_date = ?
                """, (
                    leave_worker_id,
                    leave_date.strftime("%Y-%m-%d")
                ))

                if existing.empty:

                    run_action("""
                        INSERT INTO leaves
                        (leave_id, worker_id, leave_date,
                         leave_type, day_value, reason)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        generate_id("LV"),
                        leave_worker_id,
                        leave_date.strftime("%Y-%m-%d"),
                        leave_type,
                        leave_day_value,
                        leave_reason
                    ))

                    st.success(
                        "✅ Leave/Holiday saved successfully."
                    )

                else:

                    run_action("""
                        UPDATE leaves
                        SET leave_type = ?,
                            day_value = ?,
                            reason = ?
                        WHERE worker_id = ?
                        AND leave_date = ?
                    """, (
                        leave_type,
                        leave_day_value,
                        leave_reason,
                        leave_worker_id,
                        leave_date.strftime("%Y-%m-%d")
                    ))

                    st.success(
                        "✅ Existing leave record updated."
                    )

                st.rerun()

        with right:

            st.markdown("### 🗑️ Delete Leave Record")

            if df_leaves.empty:

                st.info("No leave records available.")

            else:

                leave_options = (
                    df_leaves["Leave ID"].astype(str)
                    + " - "
                    + df_leaves["Worker Name"].astype(str)
                    + " - "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "🌴 Select Leave Record",
                    leave_options
                )

                delete_leave_id = selected_leave.split(" - ")[0]

                if st.button(
                    "❌ Delete Leave Record"
                ):

                    run_action("""
                        DELETE FROM leaves
                        WHERE leave_id = ?
                    """, (delete_leave_id,))

                    st.success("✅ Leave record deleted.")
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Leave & Holiday Records")

    st.dataframe(
        load_leaves(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 6. SHOP ITEMS
# ============================================================
elif menu == "🛒 Shop Items":

    st.subheader("🛒 Shop Items Taken by Workers")

    if df_workers.empty:

        st.warning("⚠️ Please add a worker first.")

    else:

        left, right = st.columns(2)

        with left:

            st.markdown("### ➕ Add Shop Item")

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="shop_worker"
            )

            shop_worker_id = selected_worker.split(" - ")[0]

            item_date = st.date_input(
                "📅 Date Taken",
                value=date.today()
            )

            item_name = st.text_input(
                "🛒 Item Name"
            )

            item_cost = st.number_input(
                "💰 Item Cost (NPR)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            item_notes = st.text_input(
                "📝 Notes"
            )

            if st.button(
                "💾 Save Shop Item",
                type="primary"
            ):

                if not item_name.strip():

                    st.error("❌ Please enter item name.")

                else:

                    run_action("""
                        INSERT INTO shop_consumption
                        (item_id, worker_id, entry_date,
                         item_name, item_cost, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        generate_id("C"),
                        shop_worker_id,
                        item_date.strftime("%Y-%m-%d"),
                        item_name,
                        item_cost,
                        item_notes
                    ))

                    st.success("✅ Shop item saved.")
                    st.rerun()

        with right:

            st.markdown("### 🗑️ Delete Shop Item")

            if df_consumption.empty:

                st.info("No shop records.")

            else:

                shop_options = (
                    df_consumption["Item ID"].astype(str)
                    + " - "
                    + df_consumption["Worker Name"].astype(str)
                    + " - "
                    + df_consumption["Item"].astype(str)
                )

                selected_shop = st.selectbox(
                    "🛒 Select Shop Record",
                    shop_options
                )

                delete_shop_id = selected_shop.split(" - ")[0]

                if st.button(
                    "❌ Delete Shop Record"
                ):

                    run_action("""
                        DELETE FROM shop_consumption
                        WHERE item_id = ?
                    """, (delete_shop_id,))

                    st.success("✅ Shop record deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_consumption(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 7. MONEY TAKEN / ADVANCE
# ============================================================
elif menu == "💵 Money Taken / Advance":

    st.subheader("💵 Worker Money Taken / Advance")

    if df_workers.empty:

        st.warning("⚠️ Please add a worker first.")

    else:

        left, right = st.columns(2)

        with left:

            st.markdown("### ➕ Record Money Taken")

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="advance_worker"
            )

            advance_worker_id = selected_worker.split(" - ")[0]

            advance_date = st.date_input(
                "📅 Date Money Taken",
                value=date.today()
            )

            advance_amount = st.number_input(
                "💰 Amount Taken (NPR)",
                min_value=0.0,
                value=0.0,
                step=100.0
            )

            advance_reason = st.text_input(
                "📝 Reason"
            )

            if st.button(
                "💾 Save Money Taken",
                type="primary"
            ):

                if advance_amount <= 0:

                    st.error("❌ Enter an amount greater than zero.")

                else:

                    run_action("""
                        INSERT INTO advances
                        (advance_id, worker_id, advance_date,
                         amount, reason)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        generate_id("ADV"),
                        advance_worker_id,
                        advance_date.strftime("%Y-%m-%d"),
                        advance_amount,
                        advance_reason
                    ))

                    st.success("✅ Money taken record saved.")
                    st.rerun()

        with right:

            st.markdown("### 🗑️ Delete Money Record")

            if df_advances.empty:

                st.info("No advance records.")

            else:

                advance_options = (
                    df_advances["Advance ID"].astype(str)
                    + " - "
                    + df_advances["Worker Name"].astype(str)
                    + " - NPR "
                    + df_advances["Money Taken (NPR)"].astype(str)
                )

                selected_advance = st.selectbox(
                    "💵 Select Record",
                    advance_options
                )

                delete_advance_id = selected_advance.split(" - ")[0]

                if st.button(
                    "❌ Delete Money Record"
                ):

                    run_action("""
                        DELETE FROM advances
                        WHERE advance_id = ?
                    """, (delete_advance_id,))

                    st.success("✅ Record deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_advances(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 8. MONTHLY FINANCIAL PAYOUT
# ============================================================
elif menu == "💰 Monthly Financial Payout":

    st.subheader("💰 Monthly Financial Payout")

    if df_workers.empty:

        st.warning("⚠️ Please add a worker first.")

    else:

        left, right = st.columns(2)

        with left:

            st.markdown("### 🧮 Calculate Monthly Salary")

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="financial_worker"
            )

            financial_worker_id = selected_worker.split(" - ")[0]

            months = get_available_months()

            selected_month = st.selectbox(
                "🗓️ Select Salary Month",
                months,
                format_func=get_month_label,
                key="financial_month"
            )

            existing_financial = run_query("""
                SELECT *
                FROM financials
                WHERE worker_id = ?
                AND month_key = ?
            """, (
                financial_worker_id,
                selected_month
            ))

            default_wage = 1500.0
            default_paid = 0.0

            if not existing_financial.empty:

                default_wage = float(
                    existing_financial.iloc[0]["daily_wage"]
                )

                default_paid = float(
                    existing_financial.iloc[0]["paid_money"]
                )

            daily_wage = st.number_input(
                "💰 Daily Wage (NPR)",
                min_value=0.0,
                value=default_wage,
                step=100.0
            )

            calculation = calculate_worker_month(
                financial_worker_id,
                selected_month,
                daily_wage
            )

            st.markdown("### 📊 Automatic Calculation")

            cc1, cc2, cc3 = st.columns(3)

            cc1.metric(
                "📅 Calendar Days Available",
                calculation["possible_days"]
            )

            cc2.metric(
                "👷 Worked Days",
                f'{calculation["worked_days"]:.1f}'
            )

            cc3.metric(
                "🌴 Leave Days",
                f'{calculation["leave_days"]:.1f}'
            )

            cc4, cc5 = st.columns(2)

            cc4.metric(
                "💰 Basic Salary",
                f'NPR {calculation["basic_earned"]:,.2f}'
            )

            cc5.metric(
                "⏰ OT Money",
                f'NPR {calculation["ot_earned"]:,.2f}'
            )

            st.metric(
                "🏆 Total Earned",
                f'NPR {calculation["total_earned"]:,.2f}'
            )

            st.metric(
                "💵 Money Taken Automatically",
                f'NPR {calculation["advances"]:,.2f}'
            )

            st.metric(
                "🛒 Shop Deductions Automatically",
                f'NPR {calculation["shop_deductions"]:,.2f}'
            )

            paid_money = st.number_input(
                "💳 Additional Money Paid to Worker (NPR)",
                min_value=0.0,
                value=default_paid,
                step=100.0
            )

            remaining_due = (
                calculation["total_earned"]
                - calculation["advances"]
                - calculation["shop_deductions"]
                - paid_money
            )

            if remaining_due <= 0:
                status = "Fully Settled"
            elif paid_money > 0:
                status = "Partially Paid"
            else:
                status = "Unpaid"

            st.metric(
                "📌 Remaining Balance",
                f"NPR {remaining_due:,.2f}"
            )

            st.write(f"📍 Status: **{status}**")

            if st.button(
                "💾 Save / Update Monthly Financial Record",
                type="primary"
            ):

                if existing_financial.empty:

                    run_action("""
                        INSERT INTO financials
                        (
                            payment_id,
                            worker_id,
                            month_key,
                            daily_wage,
                            worked_days,
                            basic_earned,
                            ot_earned,
                            total_earned,
                            advances,
                            shop_deductions,
                            paid_money,
                            remaining_due,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        generate_id("P"),
                        financial_worker_id,
                        selected_month,
                        daily_wage,
                        calculation["worked_days"],
                        calculation["basic_earned"],
                        calculation["ot_earned"],
                        calculation["total_earned"],
                        calculation["advances"],
                        calculation["shop_deductions"],
                        paid_money,
                        remaining_due,
                        status
                    ))

                    st.success(
                        "✅ Monthly financial record created."
                    )

                else:

                    run_action("""
                        UPDATE financials
                        SET
                            daily_wage = ?,
                            worked_days = ?,
                            basic_earned = ?,
                            ot_earned = ?,
                            total_earned = ?,
                            advances = ?,
                            shop_deductions = ?,
                            paid_money = ?,
                            remaining_due = ?,
                            status = ?
                        WHERE worker_id = ?
                        AND month_key = ?
                    """, (
                        daily_wage,
                        calculation["worked_days"],
                        calculation["basic_earned"],
                        calculation["ot_earned"],
                        calculation["total_earned"],
                        calculation["advances"],
                        calculation["shop_deductions"],
                        paid_money,
                        remaining_due,
                        status,
                        financial_worker_id,
                        selected_month
                    ))

                    st.success(
                        "✅ Monthly financial record updated."
                    )

                st.rerun()

        with right:

            st.markdown("### 🗑️ Delete Financial Record")

            if df_financials.empty:

                st.info("No financial records.")

            else:

                financial_options = (
                    df_financials["Payment ID"].astype(str)
                    + " - "
                    + df_financials["Worker Name"].astype(str)
                    + " - "
                    + df_financials["Month"].map(get_month_label)
                )

                selected_financial = st.selectbox(
                    "💰 Select Financial Record",
                    financial_options
                )

                delete_payment_id = selected_financial.split(" - ")[0]

                if st.button(
                    "❌ Delete Financial Record"
                ):

                    run_action("""
                        DELETE FROM financials
                        WHERE payment_id = ?
                    """, (delete_payment_id,))

                    st.success("✅ Financial record deleted.")
                    st.rerun()

    st.markdown("---")

    st.subheader("📋 All Monthly Financial Records")

    st.dataframe(
        load_financials(),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# 9. WORKER SEARCH & MONTHLY RECORDS
# ============================================================
elif menu == "🔎 Worker Search & Monthly Records":

    st.subheader("🔎 Search Worker and View All Records")

    if df_workers.empty:

        st.warning("⚠️ No workers registered.")

    else:

        search_name = st.text_input(
            "🔍 Search Worker Name"
        )

        search_df = df_workers.copy()

        if search_name.strip():

            search_df = search_df[
                search_df["Name"].str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if search_df.empty:

            st.warning("❌ No worker found.")

        else:

            worker_options = (
                search_df["Worker ID"].astype(str)
                + " - "
                + search_df["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="search_worker"
            )

            search_worker_id = selected_worker.split(" - ")[0]

            months = get_available_months()

            selected_month = st.selectbox(
                "🗓️ Select Month",
                months,
                format_func=get_month_label,
                key="search_month"
            )

            worker_info = df_workers[
                df_workers["Worker ID"] == search_worker_id
            ]

            if not worker_info.empty:

                row = worker_info.iloc[0]

                st.markdown("### 👷 Worker Information")

                c1, c2, c3, c4 = st.columns(4)

                c1.metric("👤 Name", row["Name"])
                c2.metric("📱 Phone", row["Phone"])
                c3.metric("🛠️ Skill", row["Skill"])
                c4.metric("📅 Started", row["Start Date"])

            st.markdown("---")

            calculation = calculate_worker_month(
                search_worker_id,
                selected_month,
                0
            )

            financial_record = df_financials[
                (df_financials["Worker ID"] == search_worker_id)
                &
                (df_financials["Month"] == selected_month)
            ]

            st.markdown(
                f"## 📊 {get_month_label(selected_month)} Summary"
            )

            s1, s2, s3, s4 = st.columns(4)

            s1.metric(
                "👷 Worked Days",
                f'{calculation["worked_days"]:.1f}'
            )

            s2.metric(
                "🌴 Leave Days",
                f'{calculation["leave_days"]:.1f}'
            )

            s3.metric(
                "⏰ OT Money",
                f'NPR {calculation["ot_earned"]:,.2f}'
            )

            s4.metric(
                "💵 Money Taken",
                f'NPR {calculation["advances"]:,.2f}'
            )

            if not financial_record.empty:

                fin = financial_record.iloc[0]

                st.markdown("### 💰 Salary Summary")

                f1, f2, f3, f4 = st.columns(4)

                f1.metric(
                    "💰 Total Earned",
                    f'NPR {float(fin["Total Earned (NPR)"]):,.2f}'
                )

                f2.metric(
                    "🛒 Shop Deduction",
                    f'NPR {float(fin["Shop Deductions (NPR)"]):,.2f}'
                )

                f3.metric(
                    "💳 Paid",
                    f'NPR {float(fin["Paid Money (NPR)"]):,.2f}'
                )

                f4.metric(
                    "📌 Due",
                    f'NPR {float(fin["Remaining Due (NPR)"]):,.2f}'
                )

            else:

                st.info(
                    "ℹ️ No financial payout record saved for this month yet."
                )

            st.markdown("---")

            # Attendance
            st.markdown("### 📅 Work Attendance")

            worker_attendance = df_attendance[
                (df_attendance["Worker ID"] == search_worker_id)
                &
                (df_attendance["Work Date"].str.startswith(selected_month))
            ]

            st.dataframe(
                worker_attendance,
                use_container_width=True,
                hide_index=True
            )

            # Leaves
            st.markdown("### 🌴 Leaves & Holidays")

            worker_leaves = df_leaves[
                (df_leaves["Worker ID"] == search_worker_id)
                &
                (df_leaves["Leave Date"].str.startswith(selected_month))
            ]

            st.dataframe(
                worker_leaves,
                use_container_width=True,
                hide_index=True
            )

            # OT
            st.markdown("### ⏰ Overtime")

            worker_ot = df_overtime[
                (df_overtime["Worker ID"] == search_worker_id)
                &
                (df_overtime["OT Date"].str.startswith(selected_month))
            ]

            st.dataframe(
                worker_ot,
                use_container_width=True,
                hide_index=True
            )

            # Advances
            st.markdown("### 💵 Money Taken / Advance")

            worker_advances = df_advances[
                (df_advances["Worker ID"] == search_worker_id)
                &
                (df_advances["Date"].str.startswith(selected_month))
            ]

            st.dataframe(
                worker_advances,
                use_container_width=True,
                hide_index=True
            )

            # Shop
            st.markdown("### 🛒 Shop Items Taken")

            worker_shop = df_consumption[
                (df_consumption["Worker ID"] == search_worker_id)
                &
                (df_consumption["Date"].str.startswith(selected_month))
            ]

            st.dataframe(
                worker_shop,
                use_container_width=True,
                hide_index=True
            )
