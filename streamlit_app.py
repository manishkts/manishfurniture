import streamlit as st
import pandas as pd
import sqlite3
import io
import calendar
from datetime import date, datetime, timedelta


# ============================================================
# 🪚 FURNITURE WORKSHOP RECORD & PAYROLL SYSTEM
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Record & Monthly Payroll System")
st.caption(
    "👷 Attendance • 🌓 Half Days • 🌴 Leaves • ⏰ OT Money • "
    "💸 Advances • 🛒 Shop Deductions • 💰 Monthly Salary"
)

DB_FILE = "workshop.db"


# ============================================================
# 🗄️ DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def add_column_if_missing(cursor, table, column, definition):
    columns = get_columns(cursor, table)

    if column not in columns:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


# ============================================================
# 🏗️ DATABASE SETUP AND MIGRATION
# ============================================================

def init_db():

    with get_connection() as conn:

        cursor = conn.cursor()

        # ----------------------------------------------------
        # 👷 WORKERS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                skill TEXT,
                start_date TEXT,
                active INTEGER DEFAULT 1
            )
        """)

        # ----------------------------------------------------
        # 📝 ATTENDANCE LOGS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_status TEXT DEFAULT 'Full Day',
                worked_value REAL DEFAULT 1.0,
                ot_done INTEGER DEFAULT 0,
                ot_money REAL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # Add missing columns from old databases
        add_column_if_missing(
            cursor,
            "logs",
            "work_status",
            "TEXT DEFAULT 'Full Day'"
        )

        add_column_if_missing(
            cursor,
            "logs",
            "worked_value",
            "REAL DEFAULT 1.0"
        )

        add_column_if_missing(
            cursor,
            "logs",
            "ot_done",
            "INTEGER DEFAULT 0"
        )

        add_column_if_missing(
            cursor,
            "logs",
            "ot_money",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            cursor,
            "logs",
            "ot_notes",
            "TEXT"
        )

        add_column_if_missing(
            cursor,
            "logs",
            "remarks",
            "TEXT"
        )

        # ----------------------------------------------------
        # 🌴 LEAVES
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                leave_value REAL DEFAULT 1.0,
                reason TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        add_column_if_missing(
            cursor,
            "leaves",
            "leave_value",
            "REAL DEFAULT 1.0"
        )

        # ----------------------------------------------------
        # 🛒 SHOP ITEMS
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
        # 💸 ADVANCES
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
        # 💵 PAYMENTS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # 💰 MONTHLY FINANCIALS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                daily_wage REAL NOT NULL DEFAULT 0,
                total_worked_days REAL NOT NULL DEFAULT 0,
                total_ot_money REAL NOT NULL DEFAULT 0,
                total_earned REAL NOT NULL DEFAULT 0,
                total_advance REAL NOT NULL DEFAULT 0,
                total_shop_deduction REAL NOT NULL DEFAULT 0,
                total_paid REAL NOT NULL DEFAULT 0,
                remaining_due REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Unpaid',
                updated_at TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # 🔧 MIGRATE OLD WORKERS TABLE
        # ----------------------------------------------------

        add_column_if_missing(
            cursor,
            "workers",
            "start_date",
            "TEXT"
        )

        add_column_if_missing(
            cursor,
            "workers",
            "active",
            "INTEGER DEFAULT 1"
        )

        conn.commit()


init_db()


# ============================================================
# 🔧 DATABASE HELPERS
# ============================================================

def run_query(query, params=()):

    with get_connection() as conn:
        return pd.read_sql_query(
            query,
            conn,
            params=params
        )


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


def get_month_key(year, month):

    return f"{int(year):04d}-{int(month):02d}"


def get_month_start_end(year, month):

    year = int(year)
    month = int(month)

    last_day = calendar.monthrange(
        year,
        month
    )[1]

    start_date = date(
        year,
        month,
        1
    )

    end_date = date(
        year,
        month,
        last_day
    )

    return (
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    )


def worker_label(df):

    return (
        df["Worker ID"].astype(str)
        + " - "
        + df["Name"].astype(str)
    )


# ============================================================
# 📊 DATA LOADERS
# ============================================================

def load_workers():

    return run_query("""
        SELECT
            worker_id AS 'Worker ID',
            name AS 'Name',
            phone AS 'Phone',
            skill AS 'Skill',
            start_date AS 'Started Work On'
        FROM workers
        ORDER BY name
    """)


def load_logs():

    return run_query("""
        SELECT
            l.log_id AS 'Log ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.work_date AS 'Date',
            l.work_status AS 'Work Status',
            l.worked_value AS 'Worked Days Value',
            CASE
                WHEN l.ot_done = 1 THEN 'Yes'
                ELSE 'No'
            END AS 'OT Done',
            l.ot_money AS 'OT Money (NPR)',
            l.ot_notes AS 'OT Details',
            l.remarks AS 'Remarks'
        FROM logs l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.work_date DESC, w.name
    """)


def load_leaves():

    return run_query("""
        SELECT
            lv.leave_id AS 'Leave ID',
            lv.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            lv.leave_date AS 'Leave Date',
            lv.leave_type AS 'Leave Type',
            lv.leave_value AS 'Leave Days',
            lv.reason AS 'Reason'
        FROM leaves lv
        LEFT JOIN workers w
            ON lv.worker_id = w.worker_id
        ORDER BY lv.leave_date DESC, w.name
    """)


def load_consumption():

    return run_query("""
        SELECT
            sc.item_id AS 'Item ID',
            sc.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            sc.entry_date AS 'Date',
            sc.item_name AS 'Item',
            sc.item_cost AS 'Cost (NPR)',
            sc.notes AS 'Notes'
        FROM shop_consumption sc
        LEFT JOIN workers w
            ON sc.worker_id = w.worker_id
        ORDER BY sc.entry_date DESC, w.name
    """)


def load_advances():

    return run_query("""
        SELECT
            a.advance_id AS 'Advance ID',
            a.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            a.advance_date AS 'Date',
            a.amount AS 'Amount (NPR)',
            a.reason AS 'Reason'
        FROM advances a
        LEFT JOIN workers w
            ON a.worker_id = w.worker_id
        ORDER BY a.advance_date DESC, w.name
    """)


def load_payments():

    return run_query("""
        SELECT
            p.payment_id AS 'Payment ID',
            p.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            p.payment_date AS 'Date',
            p.amount AS 'Amount Paid (NPR)',
            p.notes AS 'Notes'
        FROM payments p
        LEFT JOIN workers w
            ON p.worker_id = w.worker_id
        ORDER BY p.payment_date DESC, w.name
    """)


def load_financials():

    return run_query("""
        SELECT
            f.payment_id AS 'Record ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month',
            f.daily_wage AS 'Daily Wage (NPR)',
            f.total_worked_days AS 'Worked Days',
            f.total_ot_money AS 'OT Money (NPR)',
            f.total_earned AS 'Total Earned (NPR)',
            f.total_advance AS 'Advance (NPR)',
            f.total_shop_deduction AS 'Shop Deduction (NPR)',
            f.total_paid AS 'Paid (NPR)',
            f.remaining_due AS 'Remaining Due (NPR)',
            f.status AS 'Status',
            f.updated_at AS 'Updated'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# 📅 MONTHLY PAYROLL CALCULATION
# ============================================================

def get_monthly_summary(
    worker_id,
    year,
    month,
    daily_wage
):

    month_key = get_month_key(year, month)

    month_start, month_end = get_month_start_end(
        year,
        month
    )

    # --------------------------------------------------------
    # 👷 WORKER START DATE
    # --------------------------------------------------------

    worker_df = run_query("""
        SELECT start_date
        FROM workers
        WHERE worker_id = ?
    """, (worker_id,))

    if worker_df.empty:
        return None

    start_date = worker_df.iloc[0]["start_date"]

    # --------------------------------------------------------
    # 📝 ATTENDANCE
    # --------------------------------------------------------

    attendance_df = run_query("""
        SELECT
            work_date,
            work_status,
            worked_value,
            ot_money,
            ot_notes
        FROM logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
        ORDER BY work_date
    """, (
        worker_id,
        month_start,
        month_end
    ))

    # --------------------------------------------------------
    # 🌴 LEAVES
    # --------------------------------------------------------

    leaves_df = run_query("""
        SELECT
            leave_date,
            leave_type,
            leave_value,
            reason
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
        ORDER BY leave_date
    """, (
        worker_id,
        month_start,
        month_end
    ))

    # --------------------------------------------------------
    # 🛒 SHOP DEDUCTIONS
    # --------------------------------------------------------

    shop_df = run_query("""
        SELECT
            COALESCE(SUM(item_cost), 0) AS total_shop
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        month_start,
        month_end
    ))

    # --------------------------------------------------------
    # 💸 ADVANCES
    # --------------------------------------------------------

    advance_df = run_query("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_advance
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (
        worker_id,
        month_start,
        month_end
    ))

    # --------------------------------------------------------
    # 💵 PAYMENTS
    # --------------------------------------------------------

    paid_df = run_query("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_paid
        FROM payments
        WHERE worker_id = ?
        AND payment_date BETWEEN ? AND ?
    """, (
        worker_id,
        month_start,
        month_end
    ))

    # --------------------------------------------------------
    # 🧮 WORKED DAYS
    # --------------------------------------------------------

    worked_days = 0.0
    full_days = 0
    half_days = 0
    absent_days = 0

    if not attendance_df.empty:

        values = pd.to_numeric(
            attendance_df["worked_value"],
            errors="coerce"
        ).fillna(0)

        worked_days = float(values.sum())

        full_days = int((values == 1.0).sum())

        half_days = int((values == 0.5).sum())

        absent_days = int((values == 0.0).sum())

    # --------------------------------------------------------
    # 🌴 LEAVE DAYS
    # --------------------------------------------------------

    leave_days = 0.0

    if not leaves_df.empty:

        leave_days = float(
            pd.to_numeric(
                leaves_df["leave_value"],
                errors="coerce"
            ).fillna(0).sum()
        )

    # --------------------------------------------------------
    # ⏰ OT MONEY
    # --------------------------------------------------------

    total_ot_money = 0.0

    if not attendance_df.empty:

        total_ot_money = float(
            pd.to_numeric(
                attendance_df["ot_money"],
                errors="coerce"
            ).fillna(0).sum()
        )

    # --------------------------------------------------------
    # 💰 TOTALS
    # --------------------------------------------------------

    total_shop = float(
        shop_df.iloc[0]["total_shop"] or 0
    )

    total_advance = float(
        advance_df.iloc[0]["total_advance"] or 0
    )

    total_paid = float(
        paid_df.iloc[0]["total_paid"] or 0
    )

    regular_wage = float(daily_wage) * worked_days

    total_earned = (
        regular_wage
        + total_ot_money
    )

    remaining_due = (
        total_earned
        - total_advance
        - total_shop
        - total_paid
    )

    if remaining_due <= 0 and total_earned > 0:

        status = "Fully Settled"

    elif (
        total_advance > 0
        or total_shop > 0
        or total_paid > 0
    ):

        status = "Partially Paid"

    else:

        status = "Unpaid"

    return {

        "month_key": month_key,

        "month_start": month_start,

        "month_end": month_end,

        "start_date": start_date,

        "attendance_days_recorded": len(
            attendance_df
        ),

        "full_days": full_days,

        "half_days": half_days,

        "absent_days": absent_days,

        "worked_days": worked_days,

        "leave_days": leave_days,

        "total_ot_money": total_ot_money,

        "regular_wage": regular_wage,

        "total_earned": total_earned,

        "total_shop": total_shop,

        "total_advance": total_advance,

        "total_paid": total_paid,

        "remaining_due": remaining_due,

        "status": status,

        "attendance_df": attendance_df,

        "leaves_df": leaves_df
    }


# ============================================================
# 💾 SAVE MONTHLY PAYROLL
# ============================================================

def save_monthly_financial(
    worker_id,
    summary,
    daily_wage
):

    existing = run_query("""
        SELECT payment_id
        FROM financials
        WHERE worker_id = ?
        AND month_key = ?
    """, (
        worker_id,
        summary["month_key"]
    ))

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    if existing.empty:

        record_id = get_next_id(
            "MF",
            "financials",
            "payment_id"
        )

        run_action("""
            INSERT INTO financials (
                payment_id,
                worker_id,
                month_key,
                daily_wage,
                total_worked_days,
                total_ot_money,
                total_earned,
                total_advance,
                total_shop_deduction,
                total_paid,
                remaining_due,
                status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id,
            worker_id,
            summary["month_key"],
            float(daily_wage),
            summary["worked_days"],
            summary["total_ot_money"],
            summary["total_earned"],
            summary["total_advance"],
            summary["total_shop"],
            summary["total_paid"],
            summary["remaining_due"],
            summary["status"],
            now
        ))

    else:

        run_action("""
            UPDATE financials
            SET
                daily_wage = ?,
                total_worked_days = ?,
                total_ot_money = ?,
                total_earned = ?,
                total_advance = ?,
                total_shop_deduction = ?,
                total_paid = ?,
                remaining_due = ?,
                status = ?,
                updated_at = ?
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            float(daily_wage),
            summary["worked_days"],
            summary["total_ot_money"],
            summary["total_earned"],
            summary["total_advance"],
            summary["total_shop"],
            summary["total_paid"],
            summary["remaining_due"],
            summary["status"],
            now,
            worker_id,
            summary["month_key"]
        ))


# ============================================================
# 📥 EXPORT FUNCTIONS
# ============================================================

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
            sheet_name="Attendance & OT",
            index=False
        )

        load_leaves().to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        load_consumption().to_excel(
            writer,
            sheet_name="Shop Deductions",
            index=False
        )

        load_advances().to_excel(
            writer,
            sheet_name="Advances",
            index=False
        )

        load_payments().to_excel(
            writer,
            sheet_name="Payments",
            index=False
        )

        load_financials().to_excel(
            writer,
            sheet_name="Monthly Payroll",
            index=False
        )

    output.seek(0)

    return output.getvalue()


def convert_df_to_csv(df):

    return df.to_csv(
        index=False
    ).encode("utf-8")


# ============================================================
# 📊 LOAD DATA
# ============================================================

df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_advances = load_advances()
df_payments = load_payments()
df_financials = load_financials()


# ============================================================
# 📍 SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Go to:",
    [
        "📊 Dashboard",
        "👥 Manage Workers",
        "📝 Daily Attendance & OT",
        "🌴 Leaves & Holidays",
        "🛒 Shop Items Taken",
        "💸 Money Taken / Advances",
        "💵 Money Paid to Worker",
        "💰 Monthly Payroll",
        "🔎 Worker Search & Monthly Records"
    ]
)

st.sidebar.markdown("---")

st.sidebar.header("📥 Export Reports")

try:

    excel_data = generate_excel()

    st.sidebar.download_button(
        "📊 Download All Data (Excel)",
        data=excel_data,
        file_name=(
            f"workshop_report_{date.today()}.xlsx"
        ),
        mime=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True
    )

except Exception:

    st.sidebar.warning(
        "⚠️ Excel export unavailable. "
        "Make sure openpyxl is installed."
    )


with st.sidebar.expander(
    "📄 Download CSV Files"
):

    st.download_button(
        "👷 Workers CSV",
        convert_df_to_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "📝 Attendance CSV",
        convert_df_to_csv(df_logs),
        f"attendance_{date.today()}.csv",
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
        "💸 Advances CSV",
        convert_df_to_csv(df_advances),
        f"advances_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "💵 Payments CSV",
        convert_df_to_csv(df_payments),
        f"payments_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "💰 Payroll CSV",
        convert_df_to_csv(df_financials),
        f"payroll_{date.today()}.csv",
        "text/csv"
    )


# ============================================================
# 📊 DASHBOARD
# ============================================================

if menu == "📊 Dashboard":

    st.subheader("📊 Workshop Dashboard")

    total_workers = len(df_workers)

    total_earned = (
        pd.to_numeric(
            df_financials["Total Earned (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_financials.empty
        else 0.0
    )

    total_due = (
        pd.to_numeric(
            df_financials["Remaining Due (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_financials.empty
        else 0.0
    )

    total_advances = (
        pd.to_numeric(
            df_advances["Amount (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_advances.empty
        else 0.0
    )

    total_ot = (
        pd.to_numeric(
            df_logs["OT Money (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_logs.empty
        else 0.0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("👷 Workers", total_workers)

    c2.metric(
        "💰 Total Payroll",
        f"NPR {total_earned:,.2f}"
    )

    c3.metric(
        "📌 Remaining Due",
        f"NPR {total_due:,.2f}"
    )

    c4.metric(
        "💸 Total Advances",
        f"NPR {total_advances:,.2f}"
    )

    c5.metric(
        "⏰ Total OT Money",
        f"NPR {total_ot:,.2f}"
    )

    st.markdown("---")

    st.subheader("📝 Recent Attendance")

    if df_logs.empty:

        st.info("ℹ️ No attendance records yet.")

    else:

        st.dataframe(
            df_logs.head(20),
            use_container_width=True
        )

    st.subheader("💰 Saved Monthly Payroll")

    if df_financials.empty:

        st.info(
            "ℹ️ No monthly payroll records saved yet."
        )

    else:

        st.dataframe(
            df_financials,
            use_container_width=True
        )


# ============================================================
# 👥 MANAGE WORKERS
# ============================================================

elif menu == "👥 Manage Workers":

    st.subheader("👥 Manage Workers")

    col1, col2 = st.columns(2)

    with col1:

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

            name = st.text_input(
                "👤 Worker Full Name"
            )

            phone = st.text_input(
                "📱 Phone Number"
            )

            skill = st.selectbox(
                "🛠️ Role / Skill",
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

            start_date = st.date_input(
                "📅 Date Started Working",
                date.today()
            )

            submit = st.form_submit_button(
                "➕ Add Worker"
            )

            if submit:

                if not name.strip():

                    st.error(
                        "⚠️ Please enter the worker name."
                    )

                else:

                    run_action("""
                        INSERT INTO workers (
                            worker_id,
                            name,
                            phone,
                            skill,
                            start_date
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        worker_id,
                        name.strip(),
                        phone.strip(),
                        skill,
                        start_date.strftime("%Y-%m-%d")
                    ))

                    st.success(
                        f"✅ {name} added successfully."
                    )

                    st.rerun()

    with col2:

        st.markdown("### ✏️ Edit / 🗑️ Delete Worker")

        if df_workers.empty:

            st.info("ℹ️ No workers available.")

        else:

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="manage_worker_select"
            )

            worker_id = selected.split(" - ")[0]

            row = df_workers[
                df_workers["Worker ID"] == worker_id
            ].iloc[0]

            with st.form("edit_worker_form"):

                edit_name = st.text_input(
                    "👤 Name",
                    value=str(row["Name"])
                )

                edit_phone = st.text_input(
                    "📱 Phone",
                    value=(
                        ""
                        if pd.isna(row["Phone"])
                        else str(row["Phone"])
                    )
                )

                skills = [
                    "Specialist Carpenter",
                    "Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Painter",
                    "Helper",
                    "Other"
                ]

                current_skill = str(row["Skill"])

                skill_index = (
                    skills.index(current_skill)
                    if current_skill in skills
                    else 0
                )

                edit_skill = st.selectbox(
                    "🛠️ Skill",
                    skills,
                    index=skill_index
                )

                try:

                    edit_start = pd.to_datetime(
                        row["Started Work On"]
                    ).date()

                except Exception:

                    edit_start = date.today()

                edit_start = st.date_input(
                    "📅 Started Work On",
                    edit_start
                )

                update = st.form_submit_button(
                    "💾 Update Worker"
                )

                if update:

                    run_action("""
                        UPDATE workers
                        SET
                            name = ?,
                            phone = ?,
                            skill = ?,
                            start_date = ?
                        WHERE worker_id = ?
                    """, (
                        edit_name.strip(),
                        edit_phone.strip(),
                        edit_skill,
                        edit_start.strftime("%Y-%m-%d"),
                        worker_id
                    ))

                    st.success(
                        "✅ Worker updated successfully."
                    )

                    st.rerun()

            if st.button(
                "❌ Delete Selected Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (worker_id,)
                )

                st.success(
                    "✅ Worker and linked records deleted."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# 📝 DAILY ATTENDANCE & OT
# ============================================================

elif menu == "📝 Daily Attendance & OT":

    st.subheader(
        "📝 Daily Attendance, 🌓 Half Day & ⏰ OT Money"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        # ====================================================
        # ➕ ADD MULTIPLE WORK RECORDS
        # ====================================================

        with col1:

            st.markdown(
                "### ➕ Add Work Record"
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="attendance_worker"
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            # ------------------------------------------------
            # 📅 DATE MODE
            # ------------------------------------------------

            date_mode = st.radio(
                "📅 Select Work Date Method",
                [
                    "📌 Single Date",
                    "📆 Multiple Separate Dates",
                    "🗓️ Date Range"
                ],
                horizontal=True,
                key="attendance_date_mode"
            )

            selected_dates = []

            # --------------------------------------------
            # 📌 SINGLE DATE
            # --------------------------------------------

            if date_mode == "📌 Single Date":

                single_date = st.date_input(
                    "📅 Select Work Date",
                    value=date.today(),
                    key="single_work_date"
                )

                selected_dates = [
                    single_date
                ]

            # --------------------------------------------
            # 📆 MULTIPLE SEPARATE DATES
            # --------------------------------------------

            elif (
                date_mode
                == "📆 Multiple Separate Dates"
            ):

                st.info(
                    "📆 Choose a month and select any "
                    "separate dates you want."
                )

                md1, md2 = st.columns(2)

                with md1:

                    multi_month = st.selectbox(
                        "📅 Month",
                        list(range(1, 13)),
                        format_func=lambda m:
                            calendar.month_name[m],
                        index=date.today().month - 1,
                        key="multi_month"
                    )

                with md2:

                    multi_year = st.number_input(
                        "📅 Year",
                        min_value=2020,
                        max_value=2100,
                        value=date.today().year,
                        step=1,
                        key="multi_year"
                    )

                days_in_month = calendar.monthrange(
                    int(multi_year),
                    int(multi_month)
                )[1]

                available_dates = [
                    date(
                        int(multi_year),
                        int(multi_month),
                        day_number
                    )
                    for day_number in range(
                        1,
                        days_in_month + 1
                    )
                ]

                selected_dates = st.multiselect(
                    "📆 Select Multiple Work Dates",
                    options=available_dates,
                    format_func=lambda d:
                        d.strftime(
                            "%d %B %Y (%A)"
                        ),
                    key="multiple_work_dates"
                )

            # --------------------------------------------
            # 🗓️ DATE RANGE
            # --------------------------------------------

            else:

                range_value = st.date_input(
                    "🗓️ Select Start Date and End Date",
                    value=(
                        date.today(),
                        date.today()
                    ),
                    key="work_date_range"
                )

                if (
                    isinstance(
                        range_value,
                        (list, tuple)
                    )
                    and len(range_value) == 2
                ):

                    start_date, end_date = range_value

                    if start_date <= end_date:

                        current_date = start_date

                        while current_date <= end_date:

                            selected_dates.append(
                                current_date
                            )

                            current_date += timedelta(
                                days=1
                            )

                    else:

                        st.error(
                            "⚠️ End date cannot be before "
                            "start date."
                        )

            # --------------------------------------------
            # 📊 SELECTED DATE SUMMARY
            # --------------------------------------------

            selected_dates = sorted(
                list(set(selected_dates))
            )

            if selected_dates:

                st.success(
                    f"✅ Total Work Dates Selected: "
                    f"{len(selected_dates)}"
                )

                with st.expander(
                    "📅 View Selected Dates"
                ):

                    for selected_date in selected_dates:

                        st.write(
                            f"• {selected_date.strftime('%d %B %Y (%A)')}"
                        )

            else:

                st.info(
                    "ℹ️ Select at least one work date."
                )

            # ------------------------------------------------
            # 🕒 WORK STATUS
            # ------------------------------------------------

            status = st.radio(
                "🕒 Work Status",
                [
                    "☀️ Full Day",
                    "🌓 Half Day",
                    "❌ Absent"
                ],
                horizontal=True
            )

            status_values = {
                "☀️ Full Day": 1.0,
                "🌓 Half Day": 0.5,
                "❌ Absent": 0.0
            }

            worked_value = status_values[
                status
            ]

            clean_status = status.replace(
                "☀️ ",
                ""
            ).replace(
                "🌓 ",
                ""
            ).replace(
                "❌ ",
                ""
            )

            # ------------------------------------------------
            # ⏰ OT
            # ------------------------------------------------

            st.markdown("---")

            st.markdown(
                "### ⏰ Overtime"
            )

            did_ot = st.radio(
                "Did the worker work OT?",
                [
                    "❌ No OT",
                    "✅ Yes, Worked OT"
                ],
                horizontal=True
            )

            if (
                did_ot
                == "✅ Yes, Worked OT"
            ):

                ot_money = st.number_input(
                    "💵 Total OT Money (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=50.0
                )

                ot_notes = st.text_input(
                    "📋 OT Work Details"
                )

                ot_done = 1

            else:

                ot_money = 0.0

                ot_notes = ""

                ot_done = 0

            remarks = st.text_input(
                "📝 Work Remarks"
            )

            # ------------------------------------------------
            # 💾 SAVE ALL SELECTED DATES
            # ------------------------------------------------

            if st.button(
                "💾 Save Work Record",
                type="primary"
            ):

                if not selected_dates:

                    st.error(
                        "⚠️ Please select at least one date."
                    )

                else:

                    added = 0
                    updated = 0

                    for selected_date in selected_dates:

                        date_text = (
                            selected_date.strftime(
                                "%Y-%m-%d"
                            )
                        )

                        existing = run_query("""
                            SELECT log_id
                            FROM logs
                            WHERE worker_id = ?
                            AND work_date = ?
                        """, (
                            worker_id,
                            date_text
                        ))

                        if existing.empty:

                            log_id = get_next_id(
                                "L",
                                "logs",
                                "log_id"
                            )

                            run_action("""
                                INSERT INTO logs (
                                    log_id,
                                    worker_id,
                                    work_date,
                                    work_status,
                                    worked_value,
                                    ot_done,
                                    ot_money,
                                    ot_notes,
                                    remarks
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                log_id,
                                worker_id,
                                date_text,
                                clean_status,
                                worked_value,
                                ot_done,
                                ot_money,
                                ot_notes,
                                remarks
                            ))

                            added += 1

                        else:

                            log_id = existing.iloc[0][
                                "log_id"
                            ]

                            run_action("""
                                UPDATE logs
                                SET
                                    work_status = ?,
                                    worked_value = ?,
                                    ot_done = ?,
                                    ot_money = ?,
                                    ot_notes = ?,
                                    remarks = ?
                                WHERE log_id = ?
                            """, (
                                clean_status,
                                worked_value,
                                ot_done,
                                ot_money,
                                ot_notes,
                                remarks,
                                log_id
                            ))

                            updated += 1

                    st.success(
                        f"✅ Saved {added} new record(s) "
                        f"and updated {updated} existing record(s)."
                    )

                    st.rerun()

        # ====================================================
        # 🗑️ DELETE ATTENDANCE
        # ====================================================

        with col2:

            st.markdown(
                "### 🗑️ Delete Attendance Record"
            )

            if df_logs.empty:

                st.info(
                    "ℹ️ No attendance records."
                )

            else:

                record_options = (
                    df_logs["Log ID"].astype(str)
                    + " - "
                    + df_logs["Worker Name"].astype(str)
                    + " - "
                    + df_logs["Date"].astype(str)
                )

                selected_record = st.selectbox(
                    "📝 Select Record",
                    record_options,
                    key="delete_attendance"
                )

                delete_id = selected_record.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Attendance",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM logs WHERE log_id = ?",
                        (delete_id,)
                    )

                    st.success(
                        "✅ Attendance record deleted."
                    )

                    st.rerun()

        st.markdown("---")

        st.dataframe(
            load_logs(),
            use_container_width=True
        )


# ============================================================
# 🌴 LEAVES & HOLIDAYS
# ============================================================

elif menu == "🌴 Leaves & Holidays":

    st.subheader("🌴 Leaves & Holidays")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Add Leave Record"
            )

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="leave_worker"
            )

            worker_id = selected.split(
                " - "
            )[0]

            # Single date only
            leave_date = st.date_input(
                "📅 Leave Date",
                date.today()
            )

            leave_type = st.selectbox(
                "🌴 Leave Type",
                [
                    "☀️ Full Day Leave",
                    "🌓 Half Day Leave",
                    "🤒 Sick Leave",
                    "🎉 Festival / Public Holiday",
                    "❌ Unpaid Leave"
                ]
            )

            leave_value = (
                0.5
                if leave_type == "🌓 Half Day Leave"
                else 1.0
            )

            reason = st.text_input(
                "📝 Reason / Remarks"
            )

            if st.button(
                "💾 Save Leave"
            ):

                date_text = leave_date.strftime(
                    "%Y-%m-%d"
                )

                existing = run_query("""
                    SELECT leave_id
                    FROM leaves
                    WHERE worker_id = ?
                    AND leave_date = ?
                """, (
                    worker_id,
                    date_text
                ))

                if existing.empty:

                    leave_id = get_next_id(
                        "LV",
                        "leaves",
                        "leave_id"
                    )

                    run_action("""
                        INSERT INTO leaves (
                            leave_id,
                            worker_id,
                            leave_date,
                            leave_type,
                            leave_value,
                            reason
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        leave_id,
                        worker_id,
                        date_text,
                        leave_type,
                        leave_value,
                        reason
                    ))

                    st.success(
                        "✅ Leave record saved."
                    )

                else:

                    leave_id = existing.iloc[0][
                        "leave_id"
                    ]

                    run_action("""
                        UPDATE leaves
                        SET
                            leave_type = ?,
                            leave_value = ?,
                            reason = ?
                        WHERE leave_id = ?
                    """, (
                        leave_type,
                        leave_value,
                        reason,
                        leave_id
                    ))

                    st.success(
                        "✅ Leave record updated."
                    )

                st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Leave Record"
            )

            if df_leaves.empty:

                st.info(
                    "ℹ️ No leave records."
                )

            else:

                options = (
                    df_leaves["Leave ID"].astype(str)
                    + " - "
                    + df_leaves["Worker Name"].astype(str)
                    + " - "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "🌴 Select Leave",
                    options,
                    key="delete_leave"
                )

                leave_id = selected_leave.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Leave",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM leaves WHERE leave_id = ?",
                        (leave_id,)
                    )

                    st.success(
                        "✅ Leave deleted."
                    )

                    st.rerun()

        st.markdown("---")

        st.dataframe(
            load_leaves(),
            use_container_width=True
        )


# ============================================================
# 🛒 SHOP ITEMS TAKEN
# ============================================================

elif menu == "🛒 Shop Items Taken":

    st.subheader(
        "🛒 Shop / Canteen Items Taken"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Add Shop Item"
            )

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="shop_worker"
            )

            worker_id = selected.split(
                " - "
            )[0]

            item_date = st.date_input(
                "📅 Date",
                date.today(),
                key="shop_date"
            )

            item_name = st.text_input(
                "🛒 Item Taken"
            )

            item_cost = st.number_input(
                "💵 Cost (NPR)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            notes = st.text_input(
                "📝 Notes"
            )

            if st.button(
                "💾 Save Shop Item"
            ):

                if not item_name.strip():

                    st.error(
                        "⚠️ Please enter the item name."
                    )

                else:

                    item_id = get_next_id(
                        "C",
                        "shop_consumption",
                        "item_id"
                    )

                    run_action("""
                        INSERT INTO shop_consumption (
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
                        item_date.strftime(
                            "%Y-%m-%d"
                        ),
                        item_name.strip(),
                        item_cost,
                        notes
                    ))

                    st.success(
                        "✅ Shop item recorded."
                    )

                    st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Shop Record"
            )

            if df_consumption.empty:

                st.info(
                    "ℹ️ No shop records."
                )

            else:

                options = (
                    df_consumption["Item ID"].astype(str)
                    + " - "
                    + df_consumption[
                        "Worker Name"
                    ].astype(str)
                    + " - "
                    + df_consumption["Item"].astype(str)
                )

                selected_item = st.selectbox(
                    "🛒 Select Item Record",
                    options,
                    key="delete_shop"
                )

                item_id = selected_item.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Shop Record",
                    type="primary"
                ):

                    run_action(
                        """
                        DELETE FROM shop_consumption
                        WHERE item_id = ?
                        """,
                        (item_id,)
                    )

                    st.success(
                        "✅ Shop record deleted."
                    )

                    st.rerun()

        st.markdown("---")

        st.dataframe(
            load_consumption(),
            use_container_width=True
        )


# ============================================================
# 💸 MONEY TAKEN / ADVANCES
# ============================================================

elif menu == "💸 Money Taken / Advances":

    st.subheader(
        "💸 Money Taken / Advances"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Add Advance"
            )

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="advance_worker"
            )

            worker_id = selected.split(
                " - "
            )[0]

            advance_date = st.date_input(
                "📅 Advance Date",
                date.today()
            )

            amount = st.number_input(
                "💸 Amount Taken (NPR)",
                min_value=0.0,
                value=0.0,
                step=100.0
            )

            reason = st.text_input(
                "📝 Reason"
            )

            if st.button(
                "💾 Save Advance"
            ):

                if amount <= 0:

                    st.error(
                        "⚠️ Amount must be greater than 0."
                    )

                else:

                    advance_id = get_next_id(
                        "A",
                        "advances",
                        "advance_id"
                    )

                    run_action("""
                        INSERT INTO advances (
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
                        advance_date.strftime(
                            "%Y-%m-%d"
                        ),
                        amount,
                        reason
                    ))

                    st.success(
                        "✅ Advance recorded."
                    )

                    st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Advance"
            )

            if df_advances.empty:

                st.info(
                    "ℹ️ No advance records."
                )

            else:

                options = (
                    df_advances[
                        "Advance ID"
                    ].astype(str)
                    + " - "
                    + df_advances[
                        "Worker Name"
                    ].astype(str)
                    + " - NPR "
                    + df_advances[
                        "Amount (NPR)"
                    ].astype(str)
                )

                selected_advance = st.selectbox(
                    "💸 Select Advance",
                    options,
                    key="delete_advance"
                )

                advance_id = selected_advance.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Advance",
                    type="primary"
                ):

                    run_action(
                        """
                        DELETE FROM advances
                        WHERE advance_id = ?
                        """,
                        (advance_id,)
                    )

                    st.success(
                        "✅ Advance deleted."
                    )

                    st.rerun()

        st.markdown("---")

        st.dataframe(
            load_advances(),
            use_container_width=True
        )


# ============================================================
# 💵 MONEY PAID TO WORKER
# ============================================================

elif menu == "💵 Money Paid to Worker":

    st.subheader(
        "💵 Money Paid to Worker"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Record Payment"
            )

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="paid_worker"
            )

            worker_id = selected.split(
                " - "
            )[0]

            payment_date = st.date_input(
                "📅 Payment Date",
                date.today()
            )

            amount = st.number_input(
                "💵 Amount Paid (NPR)",
                min_value=0.0,
                value=0.0,
                step=100.0
            )

            notes = st.text_input(
                "📝 Payment Notes"
            )

            if st.button(
                "💾 Save Payment"
            ):

                if amount <= 0:

                    st.error(
                        "⚠️ Amount must be greater than 0."
                    )

                else:

                    payment_id = get_next_id(
                        "PAY",
                        "payments",
                        "payment_id"
                    )

                    run_action("""
                        INSERT INTO payments (
                            payment_id,
                            worker_id,
                            payment_date,
                            amount,
                            notes
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        payment_id,
                        worker_id,
                        payment_date.strftime(
                            "%Y-%m-%d"
                        ),
                        amount,
                        notes
                    ))

                    st.success(
                        "✅ Payment recorded."
                    )

                    st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Payment"
            )

            if df_payments.empty:

                st.info(
                    "ℹ️ No payment records."
                )

            else:

                options = (
                    df_payments[
                        "Payment ID"
                    ].astype(str)
                    + " - "
                    + df_payments[
                        "Worker Name"
                    ].astype(str)
                    + " - NPR "
                    + df_payments[
                        "Amount Paid (NPR)"
                    ].astype(str)
                )

                selected_payment = st.selectbox(
                    "💵 Select Payment",
                    options,
                    key="delete_payment"
                )

                payment_id = selected_payment.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Payment",
                    type="primary"
                ):

                    run_action(
                        """
                        DELETE FROM payments
                        WHERE payment_id = ?
                        """,
                        (payment_id,)
                    )

                    st.success(
                        "✅ Payment deleted."
                    )

                    st.rerun()

        st.markdown("---")

        st.dataframe(
            load_payments(),
            use_container_width=True
        )


# ============================================================
# 💰 MONTHLY PAYROLL
# ============================================================

elif menu == "💰 Monthly Payroll":

    st.subheader(
        "💰 Automatic Monthly Payroll"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        c1, c2, c3 = st.columns(3)

        with c1:

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(df_workers),
                key="payroll_worker"
            )

            worker_id = selected.split(
                " - "
            )[0]

        with c2:

            selected_month = st.selectbox(
                "📅 Month",
                list(range(1, 13)),
                format_func=lambda m:
                    calendar.month_name[m],
                index=date.today().month - 1
            )

        with c3:

            selected_year = st.number_input(
                "📅 Year",
                min_value=2020,
                max_value=2100,
                value=date.today().year,
                step=1
            )

        month_key = get_month_key(
            selected_year,
            selected_month
        )

        old_financial = run_query("""
            SELECT daily_wage
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            worker_id,
            month_key
        ))

        if old_financial.empty:

            default_wage = 1500.0

        else:

            default_wage = float(
                old_financial.iloc[0]["daily_wage"]
            )

        daily_wage = st.number_input(
            "💵 Daily Wage (NPR)",
            min_value=0.0,
            value=default_wage,
            step=100.0
        )

        summary = get_monthly_summary(
            worker_id,
            selected_year,
            selected_month,
            daily_wage
        )

        if summary:

            st.markdown("---")

            st.markdown(
                f"### 📅 {calendar.month_name[selected_month]} "
                f"{selected_year} Summary"
            )

            m1, m2, m3, m4, m5, m6 = st.columns(6)

            m1.metric(
                "☀️ Full Days",
                summary["full_days"]
            )

            m2.metric(
                "🌓 Half Days",
                summary["half_days"]
            )

            m3.metric(
                "📝 Worked Days",
                f'{summary["worked_days"]:.1f}'
            )

            m4.metric(
                "🌴 Leave Days",
                f'{summary["leave_days"]:.1f}'
            )

            m5.metric(
                "⏰ OT Money",
                f'NPR {summary["total_ot_money"]:,.2f}'
            )

            m6.metric(
                "📋 Records",
                summary["attendance_days_recorded"]
            )

            st.info(
                "🧮 Full Day = 1.0 day | "
                "Half Day = 0.5 day | "
                "Absent = 0 day. "
                "OT money entered in attendance is automatically added."
            )

            st.markdown(
                "### 🧮 Salary Calculation"
            )

            a, b, c, d = st.columns(4)

            a.metric(
                "💵 Regular Wage",
                f'NPR {summary["regular_wage"]:,.2f}'
            )

            b.metric(
                "💰 Total Earned + OT",
                f'NPR {summary["total_earned"]:,.2f}'
            )

            c.metric(
                "➖ Total Deductions",
                f'NPR {summary["total_advance"] + summary["total_shop"]:,.2f}'
            )

            d.metric(
                "📌 Remaining Due",
                f'NPR {summary["remaining_due"]:,.2f}'
            )

            st.markdown("#### 🔢 Calculation")

            st.code(
                f"""Regular Wage = Daily Wage × Worked Days
NPR {daily_wage:,.2f} × {summary["worked_days"]:.1f}
= NPR {summary["regular_wage"]:,.2f}

Total Earned = Regular Wage + OT Money
NPR {summary["regular_wage"]:,.2f}
+ NPR {summary["total_ot_money"]:,.2f}
= NPR {summary["total_earned"]:,.2f}

Remaining Due = Total Earned - Advance - Shop Deduction - Paid
NPR {summary["total_earned"]:,.2f}
- NPR {summary["total_advance"]:,.2f}
- NPR {summary["total_shop"]:,.2f}
- NPR {summary["total_paid"]:,.2f}
= NPR {summary["remaining_due"]:,.2f}""",
                language="text"
            )

            d1, d2, d3 = st.columns(3)

            d1.metric(
                "💸 Advance Taken",
                f'NPR {summary["total_advance"]:,.2f}'
            )

            d2.metric(
                "🛒 Shop Deduction",
                f'NPR {summary["total_shop"]:,.2f}'
            )

            d3.metric(
                "💵 Already Paid",
                f'NPR {summary["total_paid"]:,.2f}'
            )

            st.markdown(
                f"### 📌 Status: {summary['status']}"
            )

            if st.button(
                "💾 Save / Update Monthly Payroll",
                type="primary"
            ):

                save_monthly_financial(
                    worker_id,
                    summary,
                    daily_wage
                )

                st.success(
                    "✅ Monthly payroll saved successfully."
                )

                st.rerun()

            st.markdown("---")

            st.markdown(
                "### 📝 Attendance Used for Calculation"
            )

            if summary["attendance_df"].empty:

                st.info(
                    "ℹ️ No attendance records for this month."
                )

            else:

                st.dataframe(
                    summary["attendance_df"],
                    use_container_width=True
                )

            st.markdown(
                "### 🌴 Leave Records for This Month"
            )

            if summary["leaves_df"].empty:

                st.info(
                    "ℹ️ No leave records for this month."
                )

            else:

                st.dataframe(
                    summary["leaves_df"],
                    use_container_width=True
                )

        st.markdown("---")

        st.subheader(
            "💰 Saved Monthly Payroll"
        )

        st.dataframe(
            load_financials(),
            use_container_width=True
        )


# ============================================================
# 🔎 WORKER SEARCH & MONTHLY RECORDS
# ============================================================

elif menu == "🔎 Worker Search & Monthly Records":

    st.subheader(
        "🔎 Search Worker and View Monthly Records"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ No workers available."
        )

    else:

        search_text = st.text_input(
            "🔎 Search by Worker Name",
            placeholder="Type a worker name..."
        )

        filtered_workers = df_workers.copy()

        if search_text.strip():

            filtered_workers = filtered_workers[
                filtered_workers["Name"]
                .astype(str)
                .str.contains(
                    search_text,
                    case=False,
                    na=False
                )
            ]

        if filtered_workers.empty:

            st.warning(
                "⚠️ No worker found."
            )

        else:

            selected = st.selectbox(
                "👷 Select Worker",
                worker_label(filtered_workers),
                key="search_worker"
            )

            worker_id = selected.split(
                " - "
            )[0]

            worker_row = filtered_workers[
                filtered_workers["Worker ID"]
                == worker_id
            ].iloc[0]

            st.markdown(
                "### 👤 Worker Information"
            )

            x1, x2, x3, x4 = st.columns(4)

            x1.write(
                f"**👤 Name:** {worker_row['Name']}"
            )

            x2.write(
                f"**📱 Phone:** {worker_row['Phone']}"
            )

            x3.write(
                f"**🛠️ Skill:** {worker_row['Skill']}"
            )

            x4.write(
                f"**📅 Started:** "
                f"{worker_row['Started Work On']}"
            )

            years = list(
                range(
                    date.today().year - 5,
                    date.today().year + 2
                )
            )

            c1, c2 = st.columns(2)

            with c1:

                month = st.selectbox(
                    "📅 Select Month",
                    list(range(1, 13)),
                    format_func=lambda m:
                        calendar.month_name[m],
                    index=date.today().month - 1,
                    key="search_month"
                )

            with c2:

                year = st.selectbox(
                    "📅 Select Year",
                    years,
                    index=years.index(
                        date.today().year
                    ),
                    key="search_year"
                )

            month_start, month_end = (
                get_month_start_end(
                    year,
                    month
                )
            )

            saved = run_query("""
                SELECT daily_wage
                FROM financials
                WHERE worker_id = ?
                AND month_key = ?
            """, (
                worker_id,
                get_month_key(year, month)
            ))

            if saved.empty:

                default_wage = 1500.0

            else:

                default_wage = float(
                    saved.iloc[0]["daily_wage"]
                )

            view_wage = st.number_input(
                "💵 Daily Wage for Calculation Preview",
                min_value=0.0,
                value=default_wage,
                step=100.0,
                key="search_wage"
            )

            summary = get_monthly_summary(
                worker_id,
                year,
                month,
                view_wage
            )

            st.markdown(
                f"## 📅 {calendar.month_name[month]} "
                f"{year} — {worker_row['Name']}"
            )

            a1, a2, a3, a4, a5 = st.columns(5)

            a1.metric(
                "📝 Worked Days",
                f'{summary["worked_days"]:.1f}'
            )

            a2.metric(
                "🌴 Leave Days",
                f'{summary["leave_days"]:.1f}'
            )

            a3.metric(
                "⏰ OT Money",
                f'NPR {summary["total_ot_money"]:,.2f}'
            )

            a4.metric(
                "💰 Total Earned",
                f'NPR {summary["total_earned"]:,.2f}'
            )

            a5.metric(
                "📌 Remaining Due",
                f'NPR {summary["remaining_due"]:,.2f}'
            )

            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📝 Attendance",
                "🌴 Leaves",
                "⏰ OT",
                "💸 Money Taken / 🛒 Shop",
                "💵 Payments & 💰 Payroll"
            ])

            # ------------------------------------------------
            # ATTENDANCE TAB
            # ------------------------------------------------

            with tab1:

                attendance = run_query("""
                    SELECT
                        work_date AS Date,
                        work_status AS Status,
                        worked_value AS 'Worked Day Value',
                        ot_money AS 'OT Money (NPR)',
                        remarks AS Remarks
                    FROM logs
                    WHERE worker_id = ?
                    AND work_date BETWEEN ? AND ?
                    ORDER BY work_date
                """, (
                    worker_id,
                    month_start,
                    month_end
                ))

                st.dataframe(
                    attendance,
                    use_container_width=True
                )

            # ------------------------------------------------
            # LEAVES TAB
            # ------------------------------------------------

            with tab2:

                leaves = run_query("""
                    SELECT
                        leave_date AS Date,
                        leave_type AS 'Leave Type',
                        leave_value AS 'Leave Value',
                        reason AS Reason
                    FROM leaves
                    WHERE worker_id = ?
                    AND leave_date BETWEEN ? AND ?
                    ORDER BY leave_date
                """, (
                    worker_id,
                    month_start,
                    month_end
                ))

                st.dataframe(
                    leaves,
                    use_container_width=True
                )

            # ------------------------------------------------
            # OT TAB
            # ------------------------------------------------

            with tab3:

                ot = run_query("""
                    SELECT
                        work_date AS Date,
                        ot_money AS 'OT Money (NPR)',
                        ot_notes AS Details
                    FROM logs
                    WHERE worker_id = ?
                    AND work_date BETWEEN ? AND ?
                    AND ot_money > 0
                    ORDER BY work_date
                """, (
                    worker_id,
                    month_start,
                    month_end
                ))

                if ot.empty:

                    st.info(
                        "ℹ️ No OT recorded this month."
                    )

                else:

                    st.dataframe(
                        ot,
                        use_container_width=True
                    )

                    total_ot_month = pd.to_numeric(
                        ot["OT Money (NPR)"],
                        errors="coerce"
                    ).fillna(0).sum()

                    st.success(
                        f"⏰ Total OT Money: "
                        f"NPR {total_ot_month:,.2f}"
                    )

            # ------------------------------------------------
            # ADVANCE AND SHOP TAB
            # ------------------------------------------------

            with tab4:

                st.markdown(
                    "#### 💸 Advances"
                )

                advances = run_query("""
                    SELECT
                        advance_date AS Date,
                        amount AS 'Amount (NPR)',
                        reason AS Reason
                    FROM advances
                    WHERE worker_id = ?
                    AND advance_date BETWEEN ? AND ?
                    ORDER BY advance_date
                """, (
                    worker_id,
                    month_start,
                    month_end
                ))

                st.dataframe(
                    advances,
                    use_container_width=True
                )

                st.markdown(
                    "#### 🛒 Shop Items"
                )

                shop = run_query("""
                    SELECT
                        entry_date AS Date,
                        item_name AS Item,
                        item_cost AS 'Cost (NPR)',
                        notes AS Notes
                    FROM shop_consumption
                    WHERE worker_id = ?
                    AND entry_date BETWEEN ? AND ?
                    ORDER BY entry_date
                """, (
                    worker_id,
                    month_start,
                    month_end
                ))

                st.dataframe(
                    shop,
                    use_container_width=True
                )

            # ------------------------------------------------
            # PAYMENTS AND PAYROLL TAB
            # ------------------------------------------------

            with tab5:

                st.markdown(
                    "#### 💵 Payments Given"
                )

                payments = run_query("""
                    SELECT
                        payment_date AS Date,
                        amount AS 'Amount Paid (NPR)',
                        notes AS Notes
                    FROM payments
                    WHERE worker_id = ?
                    AND payment_date BETWEEN ? AND ?
                    ORDER BY payment_date
                """, (
                    worker_id,
                    month_start,
                    month_end
                ))

                st.dataframe(
                    payments,
                    use_container_width=True
                )

                st.markdown(
                    "#### 💰 Saved Monthly Payroll"
                )

                payroll = run_query("""
                    SELECT
                        *
                    FROM financials
                    WHERE worker_id = ?
                    AND month_key = ?
                """, (
                    worker_id,
                    get_month_key(year, month)
                ))

                st.dataframe(
                    payroll,
                    use_container_width=True
                )


# ============================================================
# 🪚 FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "🪚 Furniture Workshop Record System • "
    "SQLite Database: workshop.db"
)
