import streamlit as st
import pandas as pd
import sqlite3
import io
import calendar
from datetime import date, datetime, timedelta


# ============================================================
# 🪚 MANISH FURNITURE WORKSHOP MANAGEMENT SYSTEM
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

DB_FILE = "workshop.db"


# ============================================================
# 🗄️ DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def table_columns(table_name):
    """Return all column names from a table."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]


def ensure_column(table_name, column_name, column_definition):
    """Safely add a column if it does not already exist."""
    cols = table_columns(table_name)

    if column_name not in cols:
        with get_connection() as conn:
            conn.execute(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} {column_definition}"
            )
            conn.commit()


# ============================================================
# 🔧 DATABASE INITIALIZATION + AUTOMATIC MIGRATION
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
                phone TEXT DEFAULT '',
                skill TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                active INTEGER DEFAULT 1
            )
        """)

        # ----------------------------------------------------
        # 📅 DAILY WORK RECORDS
        #
        # Each selected work date gets one record.
        # work_type:
        # Full Day = 1.0
        # Half Day = 0.5
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_type TEXT DEFAULT 'Full Day',
                work_value REAL DEFAULT 1.0,
                ot_done INTEGER DEFAULT 0,
                ot_money REAL DEFAULT 0.0,
                remarks TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(worker_id)
            )
        """)

        # ----------------------------------------------------
        # 🌴 LEAVES
        # Single date only
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT DEFAULT 'Holiday',
                leave_value REAL DEFAULT 1.0,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(worker_id)
            )
        """)

        # ----------------------------------------------------
        # 🛒 SHOP CONSUMPTION
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL DEFAULT 0.0,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(worker_id)
            )
        """)

        # ----------------------------------------------------
        # 💵 ADVANCES - SEPARATE TABLE
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                advance_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                advance_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(worker_id)
            )
        """)

        # ----------------------------------------------------
        # 💰 MONTHLY FINANCIALS
        #
        # UNIQUE(worker_id, month_key)
        # prevents duplicate monthly records.
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                daily_wage REAL DEFAULT 0.0,
                total_worked_days REAL DEFAULT 0.0,
                total_ot_money REAL DEFAULT 0.0,
                gross_earned REAL DEFAULT 0.0,
                advance_amount REAL DEFAULT 0.0,
                shop_deduction REAL DEFAULT 0.0,
                total_deduction REAL DEFAULT 0.0,
                amount_paid REAL DEFAULT 0.0,
                balance_due REAL DEFAULT 0.0,
                status TEXT DEFAULT 'Unpaid',
                notes TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(worker_id),
                UNIQUE(worker_id, month_key)
            )
        """)

        # ----------------------------------------------------
        # 🔐 UNIQUE INDEXES
        # ----------------------------------------------------
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_work_log_unique
            ON work_logs(worker_id, work_date)
        """)

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_unique
            ON leaves(worker_id, leave_date)
        """)

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_financial_unique
            ON financials(worker_id, month_key)
        """)

        conn.commit()

    # ========================================================
    # 🛠️ MIGRATE OLDER DATABASES
    # ========================================================

    ensure_column("workers", "phone", "TEXT DEFAULT ''")
    ensure_column("workers", "skill", "TEXT DEFAULT ''")
    ensure_column("workers", "start_date", "TEXT DEFAULT ''")
    ensure_column("workers", "active", "INTEGER DEFAULT 1")

    ensure_column("work_logs", "work_type", "TEXT DEFAULT 'Full Day'")
    ensure_column("work_logs", "work_value", "REAL DEFAULT 1.0")
    ensure_column("work_logs", "ot_done", "INTEGER DEFAULT 0")
    ensure_column("work_logs", "ot_money", "REAL DEFAULT 0.0")
    ensure_column("work_logs", "remarks", "TEXT DEFAULT ''")
    ensure_column("work_logs", "created_at", "TEXT DEFAULT ''")

    ensure_column("leaves", "leave_type", "TEXT DEFAULT 'Holiday'")
    ensure_column("leaves", "leave_value", "REAL DEFAULT 1.0")
    ensure_column("leaves", "reason", "TEXT DEFAULT ''")
    ensure_column("leaves", "created_at", "TEXT DEFAULT ''")

    ensure_column("shop_consumption", "entry_date", "TEXT DEFAULT ''")
    ensure_column("shop_consumption", "item_name", "TEXT DEFAULT ''")
    ensure_column("shop_consumption", "item_cost", "REAL DEFAULT 0.0")
    ensure_column("shop_consumption", "notes", "TEXT DEFAULT ''")

    ensure_column("advances", "advance_date", "TEXT DEFAULT ''")
    ensure_column("advances", "amount", "REAL DEFAULT 0.0")
    ensure_column("advances", "reason", "TEXT DEFAULT ''")

    ensure_column("financials", "worker_id", "TEXT DEFAULT ''")
    ensure_column("financials", "month_key", "TEXT DEFAULT ''")
    ensure_column("financials", "daily_wage", "REAL DEFAULT 0.0")
    ensure_column("financials", "total_worked_days", "REAL DEFAULT 0.0")
    ensure_column("financials", "total_ot_money", "REAL DEFAULT 0.0")
    ensure_column("financials", "gross_earned", "REAL DEFAULT 0.0")
    ensure_column("financials", "advance_amount", "REAL DEFAULT 0.0")
    ensure_column("financials", "shop_deduction", "REAL DEFAULT 0.0")
    ensure_column("financials", "total_deduction", "REAL DEFAULT 0.0")
    ensure_column("financials", "amount_paid", "REAL DEFAULT 0.0")
    ensure_column("financials", "balance_due", "REAL DEFAULT 0.0")
    ensure_column("financials", "status", "TEXT DEFAULT 'Unpaid'")
    ensure_column("financials", "notes", "TEXT DEFAULT ''")
    ensure_column("financials", "updated_at", "TEXT DEFAULT ''")


# Run database setup
init_db()


# ============================================================
# 🧰 DATABASE HELPERS
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


def get_next_id(prefix, table_name, column_name):

    df = run_query(
        f"SELECT {column_name} FROM {table_name}"
    )

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[column_name].dropna().astype(str):
        digits = "".join(ch for ch in value if ch.isdigit())

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


# ============================================================
# 📥 DATA LOADERS
# ============================================================

def load_workers():
    return run_query("""
        SELECT
            worker_id AS "Worker ID",
            name AS "Name",
            phone AS "Phone",
            skill AS "Skill",
            start_date AS "Started Work",
            CASE
                WHEN active = 1 THEN 'Active'
                ELSE 'Inactive'
            END AS "Status"
        FROM workers
        ORDER BY name
    """)


def load_work_logs():
    return run_query("""
        SELECT
            wl.log_id AS "Log ID",
            wl.worker_id AS "Worker ID",
            w.name AS "Worker Name",
            wl.work_date AS "Work Date",
            wl.work_type AS "Work Type",
            wl.work_value AS "Worked Days",
            CASE
                WHEN wl.ot_done = 1 THEN 'Yes'
                ELSE 'No'
            END AS "OT Done",
            wl.ot_money AS "OT Money (NPR)",
            wl.remarks AS "Remarks"
        FROM work_logs wl
        LEFT JOIN workers w
            ON wl.worker_id = w.worker_id
        ORDER BY wl.work_date DESC, w.name
    """)


def load_leaves():
    return run_query("""
        SELECT
            l.leave_id AS "Leave ID",
            l.worker_id AS "Worker ID",
            w.name AS "Worker Name",
            l.leave_date AS "Leave Date",
            l.leave_type AS "Leave Type",
            l.leave_value AS "Days Deducted",
            l.reason AS "Reason"
        FROM leaves l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.leave_date DESC, w.name
    """)


def load_consumption():
    return run_query("""
        SELECT
            sc.item_id AS "Item ID",
            sc.worker_id AS "Worker ID",
            w.name AS "Worker Name",
            sc.entry_date AS "Date",
            sc.item_name AS "Item",
            sc.item_cost AS "Cost (NPR)",
            sc.notes AS "Notes"
        FROM shop_consumption sc
        LEFT JOIN workers w
            ON sc.worker_id = w.worker_id
        ORDER BY sc.entry_date DESC, w.name
    """)


def load_advances():
    return run_query("""
        SELECT
            a.advance_id AS "Advance ID",
            a.worker_id AS "Worker ID",
            w.name AS "Worker Name",
            a.advance_date AS "Advance Date",
            a.amount AS "Amount (NPR)",
            a.reason AS "Reason"
        FROM advances a
        LEFT JOIN workers w
            ON a.worker_id = w.worker_id
        ORDER BY a.advance_date DESC, w.name
    """)


def load_financials():
    return run_query("""
        SELECT
            f.payment_id AS "Payment ID",
            f.worker_id AS "Worker ID",
            w.name AS "Worker Name",
            f.month_key AS "Month",
            f.daily_wage AS "Daily Wage (NPR)",
            f.total_worked_days AS "Worked Days",
            f.total_ot_money AS "OT Money (NPR)",
            f.gross_earned AS "Gross Earned (NPR)",
            f.advance_amount AS "Advance (NPR)",
            f.shop_deduction AS "Shop Deduction (NPR)",
            f.total_deduction AS "Total Deduction (NPR)",
            f.amount_paid AS "Paid Amount (NPR)",
            f.balance_due AS "Balance Due (NPR)",
            f.status AS "Status",
            f.notes AS "Notes"
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# 📅 MONTH HELPERS
# ============================================================

def get_month_key(year, month):
    return f"{year}-{month:02d}"


def month_key_to_label(month_key):

    try:
        year, month = month_key.split("-")
        return datetime(
            int(year),
            int(month),
            1
        ).strftime("%B %Y")
    except Exception:
        return month_key


def get_month_dates(year, month):

    last_day = calendar.monthrange(year, month)[1]

    return (
        date(year, month, 1),
        date(year, month, last_day)
    )


def get_month_range(month_key):

    year, month = map(int, month_key.split("-"))

    start_date, end_date = get_month_dates(year, month)

    return (
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    )


# ============================================================
# 🧮 MONTHLY CALCULATION
# ============================================================

def calculate_worker_month(worker_id, month_key):

    start_date, end_date = get_month_range(month_key)

    # --------------------------------------------------------
    # 👷 WORKER
    # --------------------------------------------------------
    worker_df = run_query("""
        SELECT *
        FROM workers
        WHERE worker_id = ?
    """, (worker_id,))

    if worker_df.empty:
        return None

    worker = worker_df.iloc[0]

    # --------------------------------------------------------
    # 📅 WORK LOGS
    # --------------------------------------------------------
    work_df = run_query("""
        SELECT
            work_value,
            ot_money
        FROM work_logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (worker_id, start_date, end_date))

    if work_df.empty:
        total_worked_days = 0.0
        total_ot_money = 0.0
    else:
        total_worked_days = float(
            pd.to_numeric(
                work_df["work_value"],
                errors="coerce"
            ).fillna(0).sum()
        )

        total_ot_money = float(
            pd.to_numeric(
                work_df["ot_money"],
                errors="coerce"
            ).fillna(0).sum()
        )

    # --------------------------------------------------------
    # 🌴 LEAVES
    #
    # Leaves are recorded separately.
    # If there is no work log for that day, they are already
    # not counted as worked days.
    #
    # We still show total leave days in the summary.
    # --------------------------------------------------------
    leave_df = run_query("""
        SELECT leave_value
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (worker_id, start_date, end_date))

    if leave_df.empty:
        total_leave_days = 0.0
    else:
        total_leave_days = float(
            pd.to_numeric(
                leave_df["leave_value"],
                errors="coerce"
            ).fillna(0).sum()
        )

    # --------------------------------------------------------
    # 💵 ADVANCES
    # --------------------------------------------------------
    advance_df = run_query("""
        SELECT amount
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (worker_id, start_date, end_date))

    if advance_df.empty:
        total_advance = 0.0
    else:
        total_advance = float(
            pd.to_numeric(
                advance_df["amount"],
                errors="coerce"
            ).fillna(0).sum()
        )

    # --------------------------------------------------------
    # 🛒 SHOP ITEMS
    # --------------------------------------------------------
    shop_df = run_query("""
        SELECT item_cost
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (worker_id, start_date, end_date))

    if shop_df.empty:
        total_shop = 0.0
    else:
        total_shop = float(
            pd.to_numeric(
                shop_df["item_cost"],
                errors="coerce"
            ).fillna(0).sum()
        )

    return {
        "worker_id": worker_id,
        "worker_name": worker["name"],
        "start_date": worker["start_date"],
        "month_key": month_key,
        "month_label": month_key_to_label(month_key),
        "worked_days": total_worked_days,
        "leave_days": total_leave_days,
        "ot_money": total_ot_money,
        "advance": total_advance,
        "shop_deduction": total_shop
    }


# ============================================================
# 💰 SAVE / UPDATE MONTHLY FINANCIAL
# ============================================================

def save_monthly_financial(
    worker_id,
    month_key,
    daily_wage,
    amount_paid,
    notes=""
):

    summary = calculate_worker_month(
        worker_id,
        month_key
    )

    if summary is None:
        return False, "Worker not found."

    worked_days = float(summary["worked_days"])
    ot_money = float(summary["ot_money"])
    advance_amount = float(summary["advance"])
    shop_deduction = float(summary["shop_deduction"])

    gross_earned = (
        worked_days * float(daily_wage)
    ) + ot_money

    total_deduction = (
        advance_amount + shop_deduction
    )

    balance_due = (
        gross_earned
        - total_deduction
        - float(amount_paid)
    )

    if balance_due <= 0:
        status = "Fully Settled"
    elif amount_paid > 0:
        status = "Partially Paid"
    else:
        status = "Unpaid"

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Check whether the monthly record exists
    existing = run_query("""
        SELECT payment_id
        FROM financials
        WHERE worker_id = ?
        AND month_key = ?
    """, (worker_id, month_key))

    if existing.empty:

        payment_id = get_next_id(
            "P",
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
                gross_earned,
                advance_amount,
                shop_deduction,
                total_deduction,
                amount_paid,
                balance_due,
                status,
                notes,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            payment_id,
            worker_id,
            month_key,
            float(daily_wage),
            worked_days,
            ot_money,
            gross_earned,
            advance_amount,
            shop_deduction,
            total_deduction,
            float(amount_paid),
            balance_due,
            status,
            notes,
            now
        ))

    else:

        payment_id = existing.iloc[0]["payment_id"]

        run_action("""
            UPDATE financials
            SET
                daily_wage = ?,
                total_worked_days = ?,
                total_ot_money = ?,
                gross_earned = ?,
                advance_amount = ?,
                shop_deduction = ?,
                total_deduction = ?,
                amount_paid = ?,
                balance_due = ?,
                status = ?,
                notes = ?,
                updated_at = ?
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            float(daily_wage),
            worked_days,
            ot_money,
            gross_earned,
            advance_amount,
            shop_deduction,
            total_deduction,
            float(amount_paid),
            balance_due,
            status,
            notes,
            now,
            worker_id,
            month_key
        ))

    return True, "Monthly financial record saved successfully."


# ============================================================
# 📤 EXPORT FUNCTIONS
# ============================================================

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")


def generate_excel():

    workers = load_workers()
    work_logs = load_work_logs()
    leaves = load_leaves()
    consumption = load_consumption()
    advances = load_advances()
    financials = load_financials()

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        workers.to_excel(
            writer,
            sheet_name="Workers",
            index=False
        )

        work_logs.to_excel(
            writer,
            sheet_name="Work Records",
            index=False
        )

        leaves.to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        consumption.to_excel(
            writer,
            sheet_name="Shop Items",
            index=False
        )

        advances.to_excel(
            writer,
            sheet_name="Advances",
            index=False
        )

        financials.to_excel(
            writer,
            sheet_name="Financials",
            index=False
        )

    return output.getvalue()


# ============================================================
# 📥 LOAD CURRENT DATA
# ============================================================

df_workers = load_workers()
df_work_logs = load_work_logs()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_advances = load_advances()
df_financials = load_financials()


# ============================================================
# 🎨 HEADER
# ============================================================

st.title("🪚 Permanent Furniture Workshop Record System")
st.caption(
    "👷 Workers • 📅 Work Days • 🌴 Holidays • ⏰ OT • 💵 Advances • 💰 Monthly Salary"
)


# ============================================================
# 📍 SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Choose Section",
    [
        "📊 Dashboard",
        "👷 Manage Workers",
        "📅 Work Days & OT",
        "🌴 Leaves & Holidays",
        "🛒 Shop Items Consumed",
        "💵 Advances",
        "💰 Financial Payouts",
        "🔎 Worker Monthly Records"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Reports")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Download Complete Excel Report",
    data=excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("📄 Download CSV Files"):

    st.download_button(
        "👷 Workers CSV",
        convert_df_to_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "📅 Work Records CSV",
        convert_df_to_csv(df_work_logs),
        f"work_records_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "🌴 Leaves CSV",
        convert_df_to_csv(df_leaves),
        f"leaves_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "🛒 Shop Items CSV",
        convert_df_to_csv(df_consumption),
        f"shop_items_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "💵 Advances CSV",
        convert_df_to_csv(df_advances),
        f"advances_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "💰 Financials CSV",
        convert_df_to_csv(df_financials),
        f"financials_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )


# ============================================================
# 📊 1. DASHBOARD
# ============================================================

if menu == "📊 Dashboard":

    st.subheader("📊 Workshop Live Summary")

    total_workers = len(df_workers)

    total_worked_days = (
        pd.to_numeric(
            df_work_logs["Worked Days"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_work_logs.empty
        else 0
    )

    total_ot = (
        pd.to_numeric(
            df_work_logs["OT Money (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_work_logs.empty
        else 0
    )

    total_advances = (
        pd.to_numeric(
            df_advances["Amount (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_advances.empty
        else 0
    )

    total_shop = (
        pd.to_numeric(
            df_consumption["Cost (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_consumption.empty
        else 0
    )

    total_balance = (
        pd.to_numeric(
            df_financials["Balance Due (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_financials.empty
        else 0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("👷 Workers", total_workers)
    c2.metric("📅 Total Worked Days", f"{total_worked_days:.1f}")
    c3.metric("⏰ Total OT", f"NPR {total_ot:,.2f}")
    c4.metric("💵 Advances", f"NPR {total_advances:,.2f}")
    c5.metric("🛒 Shop Deductions", f"NPR {total_shop:,.2f}")
    c6.metric("💰 Balance Due", f"NPR {total_balance:,.2f}")

    st.markdown("---")

    st.subheader("📅 Recent Work Records")

    if df_work_logs.empty:
        st.info("No work records yet.")
    else:
        st.dataframe(
            df_work_logs.head(20),
            use_container_width=True
        )


# ============================================================
# 👷 2. MANAGE WORKERS
# ============================================================

elif menu == "👷 Manage Workers":

    st.subheader("👷 Workshop Workers")

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

            name = st.text_input("👤 Worker Full Name")
            phone = st.text_input("📱 Mobile Number")

            skill = st.selectbox(
                "🛠️ Role / Skill",
                [
                    "Specialist Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Helper",
                    "Painter",
                    "Other"
                ]
            )

            start_date = st.date_input(
                "🚀 Started Work From",
                value=date.today()
            )

            submit = st.form_submit_button(
                "➕ Register Worker"
            )

            if submit:

                if not name.strip():
                    st.error("⚠️ Please enter the worker name.")
                else:

                    run_action("""
                        INSERT INTO workers (
                            worker_id,
                            name,
                            phone,
                            skill,
                            start_date,
                            active
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        worker_id,
                        name.strip(),
                        phone.strip(),
                        skill,
                        start_date.strftime("%Y-%m-%d"),
                        1
                    ))

                    st.success(
                        f"✅ {name} added successfully!"
                    )

                    st.rerun()

    with col2:

        st.markdown("### 🗑️ Delete Worker")

        if df_workers.empty:
            st.info("No workers available.")
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

            delete_id = selected.split(" - ")[0]

            if st.button(
                "🗑️ Delete Selected Worker",
                type="primary"
            ):

                try:
                    run_action(
                        "DELETE FROM workers WHERE worker_id = ?",
                        (delete_id,)
                    )

                    st.success(
                        "✅ Worker deleted."
                    )

                    st.rerun()

                except Exception as e:
                    st.error(
                        f"⚠️ Cannot delete worker: {e}"
                    )

    st.markdown("---")
    st.subheader("📋 All Workers")
    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# 📅 3. WORK DAYS & OT
# ============================================================

elif menu == "📅 Work Days & OT":

    st.subheader("📅 Record Work Days & ⏰ Overtime")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Add Work Record"
            )

            with st.form(
                "work_log_form",
                clear_on_submit=True
            ):

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "👷 Select Worker",
                    worker_options
                )

                worker_id = (
                    worker_choice.split(" - ")[0]
                )

                work_dates = st.date_input(
                    "📅 Select One or Multiple Work Dates",
                    value=date.today()
                )

                work_type = st.radio(
                    "🕐 Work Type",
                    ["Full Day", "Half Day"],
                    horizontal=True
                )

                work_value = (
                    1.0
                    if work_type == "Full Day"
                    else 0.5
                )

                ot_done = st.checkbox(
                    "⏰ Did the worker work OT?"
                )

                if ot_done:

                    ot_money = st.number_input(
                        "💰 Total OT Money for Each Selected Day (NPR)",
                        min_value=0.0,
                        value=0.0,
                        step=50.0
                    )

                else:
                    ot_money = 0.0

                remarks = st.text_input(
                    "📝 Remarks"
                )

                submit = st.form_submit_button(
                    "💾 Save Work Record(s)"
                )

                if submit:

                    # Handle Streamlit single or range date
                    if isinstance(work_dates, tuple):

                        selected_dates = []

                        start_d = work_dates[0]
                        end_d = work_dates[1]

                        if start_d and end_d:

                            current = start_d

                            while current <= end_d:

                                selected_dates.append(
                                    current
                                )

                                current += timedelta(days=1)

                    else:
                        selected_dates = [work_dates]

                    saved = 0
                    skipped = 0

                    for selected_date in selected_dates:

                        date_text = selected_date.strftime(
                            "%Y-%m-%d"
                        )

                        # Do not add duplicate date
                        existing = run_query("""
                            SELECT log_id
                            FROM work_logs
                            WHERE worker_id = ?
                            AND work_date = ?
                        """, (
                            worker_id,
                            date_text
                        ))

                        if not existing.empty:
                            skipped += 1
                            continue

                        log_id = get_next_id(
                            "L",
                            "work_logs",
                            "log_id"
                        )

                        run_action("""
                            INSERT INTO work_logs (
                                log_id,
                                worker_id,
                                work_date,
                                work_type,
                                work_value,
                                ot_done,
                                ot_money,
                                remarks
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            log_id,
                            worker_id,
                            date_text,
                            work_type,
                            work_value,
                            1 if ot_done else 0,
                            ot_money,
                            remarks
                        ))

                        saved += 1

                    st.success(
                        f"✅ Saved {saved} work record(s). "
                        f"Skipped {skipped} duplicate date(s)."
                    )

                    st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Work Record"
            )

            if df_work_logs.empty:

                st.info(
                    "No work records available."
                )

            else:

                options = (
                    df_work_logs["Log ID"].astype(str)
                    + " - "
                    + df_work_logs["Worker Name"].astype(str)
                    + " - "
                    + df_work_logs["Work Date"].astype(str)
                )

                selected = st.selectbox(
                    "Select Work Record",
                    options
                )

                log_id = selected.split(" - ")[0]

                if st.button(
                    "🗑️ Delete Work Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM work_logs WHERE log_id = ?",
                        (log_id,)
                    )

                    st.success(
                        "✅ Work record deleted."
                    )

                    st.rerun()

    st.markdown("---")
    st.subheader("📋 All Work Records")

    st.dataframe(
        load_work_logs(),
        use_container_width=True
    )


# ============================================================
# 🌴 4. LEAVES & HOLIDAYS
# ============================================================

elif menu == "🌴 Leaves & Holidays":

    st.subheader(
        "🌴 Worker Leaves & Holidays"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Record Leave"
            )

            with st.form(
                "leave_form",
                clear_on_submit=True
            ):

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "👷 Select Worker",
                    worker_options
                )

                worker_id = (
                    worker_choice.split(" - ")[0]
                )

                # SINGLE DATE ONLY
                leave_date = st.date_input(
                    "🌴 Leave / Holiday Date",
                    value=date.today()
                )

                leave_type = st.selectbox(
                    "📌 Leave Type",
                    [
                        "Casual Leave",
                        "Sick Leave",
                        "Festival / Public Holiday",
                        "Unpaid Leave",
                        "Personal Leave"
                    ]
                )

                leave_duration = st.radio(
                    "🕐 Leave Duration",
                    [
                        "Full Day",
                        "Half Day"
                    ],
                    horizontal=True
                )

                leave_value = (
                    1.0
                    if leave_duration == "Full Day"
                    else 0.5
                )

                reason = st.text_input(
                    "📝 Reason / Remarks"
                )

                submit = st.form_submit_button(
                    "💾 Save Leave"
                )

                if submit:

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

                    if not existing.empty:

                        st.error(
                            "⚠️ A leave record already exists for this worker on this date."
                        )

                    else:

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

                        st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Leave"
            )

            if df_leaves.empty:

                st.info(
                    "No leave records available."
                )

            else:

                options = (
                    df_leaves["Leave ID"].astype(str)
                    + " - "
                    + df_leaves["Worker Name"].astype(str)
                    + " - "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected = st.selectbox(
                    "Select Leave Record",
                    options
                )

                leave_id = selected.split(
                    " - "
                )[0]

                if st.button(
                    "🗑️ Delete Leave Record",
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
# 🛒 5. SHOP ITEMS CONSUMED
# ============================================================

elif menu == "🛒 Shop Items Consumed":

    st.subheader(
        "🛒 Shop & Canteen Items Taken"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Add Item / Expense"
            )

            with st.form(
                "shop_form",
                clear_on_submit=True
            ):

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "👷 Select Worker",
                    worker_options
                )

                worker_id = (
                    worker_choice.split(" - ")[0]
                )

                entry_date = st.date_input(
                    "📅 Date",
                    value=date.today()
                )

                item_name = st.text_input(
                    "🛒 Item Name"
                )

                item_cost = st.number_input(
                    "💰 Cost (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=10.0
                )

                notes = st.text_input(
                    "📝 Notes"
                )

                submit = st.form_submit_button(
                    "💾 Save Item"
                )

                if submit:

                    if not item_name.strip():

                        st.error(
                            "⚠️ Please enter an item name."
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
                            entry_date.strftime("%Y-%m-%d"),
                            item_name.strip(),
                            item_cost,
                            notes
                        ))

                        st.success(
                            "✅ Item record saved."
                        )

                        st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Item Record"
            )

            if df_consumption.empty:

                st.info(
                    "No item records available."
                )

            else:

                options = (
                    df_consumption["Item ID"].astype(str)
                    + " - "
                    + df_consumption["Worker Name"].astype(str)
                    + " - "
                    + df_consumption["Item"].astype(str)
                )

                selected = st.selectbox(
                    "Select Record",
                    options
                )

                item_id = selected.split(
                    " - "
                )[0]

                if st.button(
                    "🗑️ Delete Item Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM shop_consumption WHERE item_id = ?",
                        (item_id,)
                    )

                    st.success(
                        "✅ Item record deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_consumption(),
        use_container_width=True
    )


# ============================================================
# 💵 6. ADVANCES
# ============================================================

elif menu == "💵 Advances":

    st.subheader(
        "💵 Worker Advance Money"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Give / Record Advance"
            )

            with st.form(
                "advance_form",
                clear_on_submit=True
            ):

                worker_options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "👷 Select Worker",
                    worker_options
                )

                worker_id = (
                    worker_choice.split(" - ")[0]
                )

                advance_date = st.date_input(
                    "📅 Advance Date",
                    value=date.today()
                )

                amount = st.number_input(
                    "💵 Advance Amount (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

                reason = st.text_input(
                    "📝 Reason for Advance"
                )

                submit = st.form_submit_button(
                    "💾 Save Advance"
                )

                if submit:

                    if amount <= 0:

                        st.error(
                            "⚠️ Advance amount must be greater than 0."
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
                            advance_date.strftime("%Y-%m-%d"),
                            amount,
                            reason
                        ))

                        st.success(
                            "✅ Advance saved successfully."
                        )

                        st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Advance"
            )

            if df_advances.empty:

                st.info(
                    "No advance records available."
                )

            else:

                options = (
                    df_advances["Advance ID"].astype(str)
                    + " - "
                    + df_advances["Worker Name"].astype(str)
                    + " - NPR "
                    + df_advances["Amount (NPR)"].astype(str)
                )

                selected = st.selectbox(
                    "Select Advance",
                    options
                )

                advance_id = selected.split(
                    " - "
                )[0]

                if st.button(
                    "🗑️ Delete Advance",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM advances WHERE advance_id = ?",
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
# 💰 7. FINANCIAL PAYOUTS
# ============================================================

elif menu == "💰 Financial Payouts":

    st.subheader(
        "💰 Monthly Financial Payouts"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        worker_options = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        col1, col2, col3 = st.columns(3)

        with col1:

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            worker_id = (
                selected_worker.split(" - ")[0]
            )

        with col2:

            selected_year = st.selectbox(
                "📅 Select Year",
                list(
                    range(
                        date.today().year - 2,
                        date.today().year + 3
                    )
                ),
                index=2
            )

        with col3:

            month_names = list(
                calendar.month_name
            )[1:]

            selected_month_name = st.selectbox(
                "🗓️ Select Month",
                month_names,
                index=date.today().month - 1
            )

            selected_month = month_names.index(
                selected_month_name
            ) + 1

        month_key = get_month_key(
            selected_year,
            selected_month
        )

        summary = calculate_worker_month(
            worker_id,
            month_key
        )

        if summary:

            st.markdown("---")
            st.subheader(
                f"📊 {summary['worker_name']} - {summary['month_label']}"
            )

            c1, c2, c3, c4, c5 = st.columns(5)

            c1.metric(
                "📅 Worked Days",
                f"{summary['worked_days']:.1f}"
            )

            c2.metric(
                "🌴 Leave Days",
                f"{summary['leave_days']:.1f}"
            )

            c3.metric(
                "⏰ OT Money",
                f"NPR {summary['ot_money']:,.2f}"
            )

            c4.metric(
                "💵 Advances",
                f"NPR {summary['advance']:,.2f}"
            )

            c5.metric(
                "🛒 Shop Items",
                f"NPR {summary['shop_deduction']:,.2f}"
            )

            # Existing financial record
            existing_financial = run_query("""
                SELECT *
                FROM financials
                WHERE worker_id = ?
                AND month_key = ?
            """, (
                worker_id,
                month_key
            ))

            if existing_financial.empty:

                default_wage = 1500.0
                default_paid = 0.0
                default_notes = ""

            else:

                existing_row = (
                    existing_financial.iloc[0]
                )

                default_wage = float(
                    existing_row["daily_wage"]
                    or 0
                )

                default_paid = float(
                    existing_row["amount_paid"]
                    or 0
                )

                default_notes = str(
                    existing_row["notes"]
                    or ""
                )

            st.markdown("---")
            st.subheader(
                "🧮 Salary Calculation"
            )

            with st.form(
                "monthly_financial_form"
            ):

                daily_wage = st.number_input(
                    "💰 Daily Wage (NPR)",
                    min_value=0.0,
                    value=default_wage,
                    step=100.0
                )

                calculated_wage = (
                    summary["worked_days"]
                    * daily_wage
                )

                gross_preview = (
                    calculated_wage
                    + summary["ot_money"]
                )

                deduction_preview = (
                    summary["advance"]
                    + summary["shop_deduction"]
                )

                balance_preview = (
                    gross_preview
                    - deduction_preview
                    - default_paid
                )

                p1, p2, p3 = st.columns(3)

                p1.metric(
                    "📅 Work Salary",
                    f"NPR {calculated_wage:,.2f}"
                )

                p2.metric(
                    "⏰ + OT Money",
                    f"NPR {summary['ot_money']:,.2f}"
                )

                p3.metric(
                    "💰 Gross Earned",
                    f"NPR {gross_preview:,.2f}"
                )

                amount_paid = st.number_input(
                    "💳 Amount Paid to Worker (NPR)",
                    min_value=0.0,
                    value=default_paid,
                    step=100.0
                )

                notes = st.text_input(
                    "📝 Financial Notes",
                    value=default_notes
                )

                final_balance = (
                    gross_preview
                    - deduction_preview
                    - amount_paid
                )

                st.info(
                    f"📌 **Calculation:** "
                    f"({summary['worked_days']:.1f} Worked Days × NPR {daily_wage:,.2f}) "
                    f"+ NPR {summary['ot_money']:,.2f} OT "
                    f"- NPR {summary['advance']:,.2f} Advance "
                    f"- NPR {summary['shop_deduction']:,.2f} Shop "
                    f"- NPR {amount_paid:,.2f} Paid "
                    f"= **NPR {final_balance:,.2f} Balance**"
                )

                submit = st.form_submit_button(
                    "💾 Save / Update Monthly Financial Record"
                )

                if submit:

                    success, message = save_monthly_financial(
                        worker_id,
                        month_key,
                        daily_wage,
                        amount_paid,
                        notes
                    )

                    if success:

                        st.success(
                            f"✅ {message}"
                        )

                        st.rerun()

                    else:

                        st.error(
                            f"⚠️ {message}"
                        )

    st.markdown("---")
    st.subheader(
        "📋 All Monthly Financial Records"
    )

    st.dataframe(
        load_financials(),
        use_container_width=True
    )


# ============================================================
# 🔎 8. WORKER MONTHLY RECORDS
# ============================================================

elif menu == "🔎 Worker Monthly Records":

    st.subheader(
        "🔎 Search Worker & View Complete Monthly Records"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ No workers available."
        )

    else:

        worker_options = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "🔎 Search / Select Worker",
            worker_options
        )

        worker_id = selected_worker.split(
            " - "
        )[0]

        worker_name = selected_worker.split(
            " - ",
            1
        )[1]

        st.success(
            f"👷 Showing all records for **{worker_name}**"
        )

        # ----------------------------------------------------
        # 📅 MONTH SELECTOR
        # ----------------------------------------------------
        available_months = set()

        for table_name, date_column in [
            ("work_logs", "work_date"),
            ("leaves", "leave_date"),
            ("shop_consumption", "entry_date"),
            ("advances", "advance_date")
        ]:

            month_df = run_query(f"""
                SELECT DISTINCT substr(
                    {date_column},
                    1,
                    7
                ) AS month_key
                FROM {table_name}
                WHERE worker_id = ?
            """, (worker_id,))

            if not month_df.empty:

                available_months.update(
                    month_df["month_key"]
                    .dropna()
                    .tolist()
                )

        financial_months = run_query("""
            SELECT DISTINCT month_key
            FROM financials
            WHERE worker_id = ?
        """, (worker_id,))

        if not financial_months.empty:

            available_months.update(
                financial_months["month_key"]
                .dropna()
                .tolist()
            )

        available_months = sorted(
            list(available_months),
            reverse=True
        )

        if not available_months:

            st.info(
                "No monthly records found for this worker."
            )

        else:

            month_labels = {
                key: month_key_to_label(key)
                for key in available_months
            }

            selected_label = st.selectbox(
                "🗓️ Select Month",
                [
                    month_labels[key]
                    for key in available_months
                ]
            )

            selected_month_key = next(
                key
                for key, label
                in month_labels.items()
                if label == selected_label
            )

            summary = calculate_worker_month(
                worker_id,
                selected_month_key
            )

            if summary:

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "📅 Worked Days",
                    f"{summary['worked_days']:.1f}"
                )

                c2.metric(
                    "🌴 Holidays / Leave",
                    f"{summary['leave_days']:.1f}"
                )

                c3.metric(
                    "⏰ OT Money",
                    f"NPR {summary['ot_money']:,.2f}"
                )

                c4.metric(
                    "💵 Advance",
                    f"NPR {summary['advance']:,.2f}"
                )

            start_date, end_date = get_month_range(
                selected_month_key
            )

            st.markdown("---")
            st.markdown(
                "### 📅 Worked Days"
            )

            worker_work = run_query("""
                SELECT
                    log_id AS "Log ID",
                    work_date AS "Date",
                    work_type AS "Work Type",
                    work_value AS "Days",
                    CASE
                        WHEN ot_done = 1 THEN 'Yes'
                        ELSE 'No'
                    END AS "OT",
                    ot_money AS "OT Money (NPR)",
                    remarks AS "Remarks"
                FROM work_logs
                WHERE worker_id = ?
                AND work_date BETWEEN ? AND ?
                ORDER BY work_date
            """, (
                worker_id,
                start_date,
                end_date
            ))

            st.dataframe(
                worker_work,
                use_container_width=True
            )

            st.markdown(
                "### 🌴 Holidays & Leaves"
            )

            worker_leaves = run_query("""
                SELECT
                    leave_date AS "Date",
                    leave_type AS "Leave Type",
                    leave_value AS "Days",
                    reason AS "Reason"
                FROM leaves
                WHERE worker_id = ?
                AND leave_date BETWEEN ? AND ?
                ORDER BY leave_date
            """, (
                worker_id,
                start_date,
                end_date
            ))

            st.dataframe(
                worker_leaves,
                use_container_width=True
            )

            st.markdown(
                "### 💵 Advance Money"
            )

            worker_advances = run_query("""
                SELECT
                    advance_date AS "Date",
                    amount AS "Amount (NPR)",
                    reason AS "Reason"
                FROM advances
                WHERE worker_id = ?
                AND advance_date BETWEEN ? AND ?
                ORDER BY advance_date
            """, (
                worker_id,
                start_date,
                end_date
            ))

            st.dataframe(
                worker_advances,
                use_container_width=True
            )

            st.markdown(
                "### 🛒 Shop Items"
            )

            worker_shop = run_query("""
                SELECT
                    entry_date AS "Date",
                    item_name AS "Item",
                    item_cost AS "Cost (NPR)",
                    notes AS "Notes"
                FROM shop_consumption
                WHERE worker_id = ?
                AND entry_date BETWEEN ? AND ?
                ORDER BY entry_date
            """, (
                worker_id,
                start_date,
                end_date
            ))

            st.dataframe(
                worker_shop,
                use_container_width=True
            )

            st.markdown(
                "### 💰 Monthly Financial Record"
            )

            worker_financial = run_query("""
                SELECT
                    daily_wage AS "Daily Wage (NPR)",
                    total_worked_days AS "Worked Days",
                    total_ot_money AS "OT Money (NPR)",
                    gross_earned AS "Gross Earned (NPR)",
                    advance_amount AS "Advance (NPR)",
                    shop_deduction AS "Shop Deduction (NPR)",
                    total_deduction AS "Total Deduction (NPR)",
                    amount_paid AS "Paid (NPR)",
                    balance_due AS "Balance Due (NPR)",
                    status AS "Status",
                    notes AS "Notes"
                FROM financials
                WHERE worker_id = ?
                AND month_key = ?
            """, (
                worker_id,
                selected_month_key
            ))

            if worker_financial.empty:

                st.info(
                    "ℹ️ Monthly financial payout has not been saved yet."
                )

            else:

                st.dataframe(
                    worker_financial,
                    use_container_width=True
                )
