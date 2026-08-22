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

st.title("🪚 Furniture Workshop Record & Payroll System")
st.caption("👷 Workers • 📅 Attendance • 🌓 Half Days • 🌴 Leaves • ⏰ OT • 💸 Advances • 💰 Payroll")

DB_FILE = "workshop.db"


# ============================================================
# 🗄️ DATABASE FUNCTIONS
# ============================================================

def get_connection():
    """Create SQLite database connection."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def get_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def ensure_column(cursor, table_name, column_name, definition):
    """Add a missing column safely."""
    if table_exists(cursor, table_name):
        columns = get_columns(cursor, table_name)

        if column_name not in columns:
            try:
                cursor.execute(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column_name} {definition}"
                )
            except sqlite3.OperationalError:
                pass


def init_db():
    """
    Create current tables and safely add missing columns
    to older versions of workshop.db.
    """

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
        # 📅 ATTENDANCE LOGS
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

        # ----------------------------------------------------
        # 🛒 SHOP CONSUMPTION
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
        # 💰 PAYMENTS MADE TO WORKER
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
        # 🧮 MONTHLY FINANCIAL RECORD
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT,
                month_key TEXT,
                daily_wage REAL DEFAULT 0,
                total_worked_days REAL DEFAULT 0,
                total_ot_money REAL DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_advance REAL DEFAULT 0,
                total_shop_deduction REAL DEFAULT 0,
                total_paid REAL DEFAULT 0,
                remaining_due REAL DEFAULT 0,
                status TEXT DEFAULT 'Unpaid',
                updated_at TEXT
            )
        """)

        # ====================================================
        # 🛠️ SAFE MIGRATION FOR OLD DATABASES
        # ====================================================

        worker_columns = [
            ("start_date", "TEXT"),
            ("active", "INTEGER DEFAULT 1")
        ]

        for column, definition in worker_columns:
            ensure_column(cursor, "workers", column, definition)

        log_columns = [
            ("work_status", "TEXT DEFAULT 'Full Day'"),
            ("worked_value", "REAL DEFAULT 1.0"),
            ("ot_done", "INTEGER DEFAULT 0"),
            ("ot_money", "REAL DEFAULT 0.0"),
            ("ot_notes", "TEXT"),
            ("remarks", "TEXT")
        ]

        for column, definition in log_columns:
            ensure_column(cursor, "logs", column, definition)

        leave_columns = [
            ("leave_value", "REAL DEFAULT 1.0"),
            ("reason", "TEXT")
        ]

        for column, definition in leave_columns:
            ensure_column(cursor, "leaves", column, definition)

        financial_columns = [
            ("worker_id", "TEXT"),
            ("month_key", "TEXT"),
            ("daily_wage", "REAL DEFAULT 0"),
            ("total_worked_days", "REAL DEFAULT 0"),
            ("total_ot_money", "REAL DEFAULT 0"),
            ("total_earned", "REAL DEFAULT 0"),
            ("total_advance", "REAL DEFAULT 0"),
            ("total_shop_deduction", "REAL DEFAULT 0"),
            ("total_paid", "REAL DEFAULT 0"),
            ("remaining_due", "REAL DEFAULT 0"),
            ("status", "TEXT DEFAULT 'Unpaid'"),
            ("updated_at", "TEXT")
        ]

        for column, definition in financial_columns:
            ensure_column(cursor, "financials", column, definition)

        # Fix NULL values from old databases

        cursor.execute("""
            UPDATE logs
            SET worked_value = 1.0
            WHERE worked_value IS NULL
        """)

        cursor.execute("""
            UPDATE logs
            SET ot_money = 0.0
            WHERE ot_money IS NULL
        """)

        cursor.execute("""
            UPDATE logs
            SET ot_done = 0
            WHERE ot_done IS NULL
        """)

        cursor.execute("""
            UPDATE leaves
            SET leave_value = 1.0
            WHERE leave_value IS NULL
        """)

        # Helpful indexes

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_worker_date
            ON logs(worker_id, work_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_leaves_worker_date
            ON leaves(worker_id, leave_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_advances_worker_date
            ON advances(worker_id, advance_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_worker_date
            ON payments(worker_id, payment_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_financial_worker_month
            ON financials(worker_id, month_key)
        """)

        conn.commit()


init_db()


# ============================================================
# 🔧 DATABASE HELPERS
# ============================================================

def run_query(query, params=()):
    """Run SELECT query and return DataFrame."""

    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def run_action(query, params=()):
    """Run INSERT, UPDATE or DELETE."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()


def get_next_id(prefix, table, id_column):
    """Generate next ID such as W001, L001, LV001."""

    df = run_query(
        f"SELECT {id_column} FROM {table}"
    )

    numbers = []

    if not df.empty:

        for value in df[id_column].dropna():

            digits = "".join(
                char for char in str(value)
                if char.isdigit()
            )

            if digits:
                numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


def month_key(year, month):
    return f"{year:04d}-{month:02d}"


def get_month_range(year, month):

    last_day = calendar.monthrange(year, month)[1]

    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    return start_date, end_date


def get_worker_labels(df):

    return (
        df["Worker ID"].astype(str)
        + " - "
        + df["Name"].astype(str)
    ).tolist()


# ============================================================
# 📥 DATA LOADERS
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
            COALESCE(w.name, 'Unknown') AS 'Worker Name',
            l.work_date AS 'Date',
            COALESCE(l.work_status, 'Full Day') AS 'Work Status',
            COALESCE(l.worked_value, 1.0) AS 'Worked Days',
            CASE
                WHEN COALESCE(l.ot_done, 0) = 1 THEN 'Yes'
                ELSE 'No'
            END AS 'OT Done',
            COALESCE(l.ot_money, 0) AS 'OT Money (NPR)',
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
            COALESCE(w.name, 'Unknown') AS 'Worker Name',
            lv.leave_date AS 'Leave Date',
            lv.leave_type AS 'Leave Type',
            COALESCE(lv.leave_value, 1.0) AS 'Leave Days',
            lv.reason AS 'Reason'
        FROM leaves lv

        LEFT JOIN workers w
        ON lv.worker_id = w.worker_id

        ORDER BY lv.leave_date DESC, w.name
    """)


def load_shop():

    return run_query("""
        SELECT
            sc.item_id AS 'Item ID',
            sc.worker_id AS 'Worker ID',
            COALESCE(w.name, 'Unknown') AS 'Worker Name',
            sc.entry_date AS 'Date',
            sc.item_name AS 'Item',
            COALESCE(sc.item_cost, 0) AS 'Cost (NPR)',
            sc.notes AS 'Notes'
        FROM shop_consumption sc

        LEFT JOIN workers w
        ON sc.worker_id = w.worker_id

        ORDER BY sc.entry_date DESC
    """)


def load_advances():

    return run_query("""
        SELECT
            a.advance_id AS 'Advance ID',
            a.worker_id AS 'Worker ID',
            COALESCE(w.name, 'Unknown') AS 'Worker Name',
            a.advance_date AS 'Date',
            COALESCE(a.amount, 0) AS 'Amount (NPR)',
            a.reason AS 'Reason'
        FROM advances a

        LEFT JOIN workers w
        ON a.worker_id = w.worker_id

        ORDER BY a.advance_date DESC
    """)


def load_payments():

    return run_query("""
        SELECT
            p.payment_id AS 'Payment ID',
            p.worker_id AS 'Worker ID',
            COALESCE(w.name, 'Unknown') AS 'Worker Name',
            p.payment_date AS 'Date',
            COALESCE(p.amount, 0) AS 'Amount Paid (NPR)',
            p.notes AS 'Notes'
        FROM payments p

        LEFT JOIN workers w
        ON p.worker_id = w.worker_id

        ORDER BY p.payment_date DESC
    """)


def load_financials():

    return run_query("""
        SELECT
            f.payment_id AS 'Record ID',
            f.worker_id AS 'Worker ID',
            COALESCE(w.name, 'Unknown') AS 'Worker Name',
            f.month_key AS 'Month',
            COALESCE(f.daily_wage, 0) AS 'Daily Wage (NPR)',
            COALESCE(f.total_worked_days, 0) AS 'Worked Days',
            COALESCE(f.total_ot_money, 0) AS 'OT Money (NPR)',
            COALESCE(f.total_earned, 0) AS 'Total Earned (NPR)',
            COALESCE(f.total_advance, 0) AS 'Advance (NPR)',
            COALESCE(f.total_shop_deduction, 0) AS 'Shop Deduction (NPR)',
            COALESCE(f.total_paid, 0) AS 'Paid (NPR)',
            COALESCE(f.remaining_due, 0) AS 'Remaining Due (NPR)',
            COALESCE(f.status, 'Unpaid') AS 'Status',
            f.updated_at AS 'Updated'
        FROM financials f

        LEFT JOIN workers w
        ON f.worker_id = w.worker_id

        WHERE
            f.worker_id IS NOT NULL
            AND f.month_key IS NOT NULL

        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# 🧮 MONTHLY PAYROLL CALCULATION
# ============================================================

def get_monthly_summary(worker_id, year, month, daily_wage):

    month_start, month_end = get_month_range(year, month)

    start_string = month_start.isoformat()
    end_string = month_end.isoformat()

    # --------------------------------------------------------
    # 👷 WORKER INFORMATION
    # --------------------------------------------------------

    worker_df = run_query("""
        SELECT start_date
        FROM workers
        WHERE worker_id = ?
    """, (worker_id,))

    if worker_df.empty:
        return None

    worker_start = worker_df.iloc[0]["start_date"]

    # --------------------------------------------------------
    # 📅 ATTENDANCE
    # --------------------------------------------------------

    logs = run_query("""
        SELECT
            work_date,
            worked_value,
            ot_money
        FROM logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_string,
        end_string
    ))

    # --------------------------------------------------------
    # 🌴 LEAVES
    # --------------------------------------------------------

    leaves = run_query("""
        SELECT
            leave_date,
            leave_value
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_string,
        end_string
    ))

    # --------------------------------------------------------
    # 🛒 SHOP DEDUCTION
    # --------------------------------------------------------

    shop_df = run_query("""
        SELECT COALESCE(SUM(item_cost), 0) AS total
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_string,
        end_string
    ))

    shop_total = float(shop_df.iloc[0]["total"])

    # --------------------------------------------------------
    # 💸 ADVANCES
    # --------------------------------------------------------

    advance_df = run_query("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_string,
        end_string
    ))

    advance_total = float(advance_df.iloc[0]["total"])

    # --------------------------------------------------------
    # 💰 PAYMENTS
    # --------------------------------------------------------

    payment_df = run_query("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments
        WHERE worker_id = ?
        AND payment_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_string,
        end_string
    ))

    paid_total = float(payment_df.iloc[0]["total"])

    # --------------------------------------------------------
    # ☀️ FULL DAY + 🌓 HALF DAY
    # --------------------------------------------------------

    if logs.empty:

        worked_days = 0.0
        full_days = 0
        half_days = 0
        ot_money = 0.0

    else:

        logs["worked_value"] = pd.to_numeric(
            logs["worked_value"],
            errors="coerce"
        ).fillna(0)

        logs["ot_money"] = pd.to_numeric(
            logs["ot_money"],
            errors="coerce"
        ).fillna(0)

        worked_days = float(logs["worked_value"].sum())

        full_days = int(
            (logs["worked_value"] == 1.0).sum()
        )

        half_days = int(
            (logs["worked_value"] == 0.5).sum()
        )

        ot_money = float(
            logs["ot_money"].sum()
        )

    # --------------------------------------------------------
    # 🌴 LEAVE DAYS
    # --------------------------------------------------------

    if leaves.empty:

        leave_days = 0.0

    else:

        leaves["leave_value"] = pd.to_numeric(
            leaves["leave_value"],
            errors="coerce"
        ).fillna(0)

        leave_days = float(
            leaves["leave_value"].sum()
        )

    # --------------------------------------------------------
    # 💵 SALARY CALCULATION
    # --------------------------------------------------------

    regular_salary = daily_wage * worked_days

    total_earned = regular_salary + ot_money

    total_deductions = (
        advance_total
        + shop_total
        + paid_total
    )

    remaining_due = (
        total_earned
        - total_deductions
    )

    # --------------------------------------------------------
    # 📌 STATUS
    # --------------------------------------------------------

    if total_earned <= 0:

        status = "⚪ No Work Recorded"

    elif remaining_due <= 0:

        status = "🟢 Fully Settled"

    elif (
        advance_total > 0
        or shop_total > 0
        or paid_total > 0
    ):

        status = "🟡 Partially Paid"

    else:

        status = "🔴 Unpaid"

    return {
        "month_key": month_key(year, month),
        "month_start": start_string,
        "month_end": end_string,
        "worker_start": worker_start,
        "worked_days": worked_days,
        "full_days": full_days,
        "half_days": half_days,
        "leave_days": leave_days,
        "ot_money": ot_money,
        "regular_salary": regular_salary,
        "total_earned": total_earned,
        "shop_total": shop_total,
        "advance_total": advance_total,
        "paid_total": paid_total,
        "remaining_due": remaining_due,
        "status": status
    }


def save_monthly_financial(worker_id, summary, daily_wage):

    existing = run_query("""
        SELECT payment_id
        FROM financials
        WHERE worker_id = ?
        AND month_key = ?
        ORDER BY rowid DESC
        LIMIT 1
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
            daily_wage,
            summary["worked_days"],
            summary["ot_money"],
            summary["total_earned"],
            summary["advance_total"],
            summary["shop_total"],
            summary["paid_total"],
            summary["remaining_due"],
            summary["status"],
            now
        ))

    else:

        record_id = existing.iloc[0]["payment_id"]

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
            WHERE payment_id = ?
        """, (
            daily_wage,
            summary["worked_days"],
            summary["ot_money"],
            summary["total_earned"],
            summary["advance_total"],
            summary["shop_total"],
            summary["paid_total"],
            summary["remaining_due"],
            summary["status"],
            now,
            record_id
        ))


# ============================================================
# 📊 EXPORT
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
            sheet_name="Attendance",
            index=False
        )

        load_leaves().to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        load_shop().to_excel(
            writer,
            sheet_name="Shop Items",
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

    return output.getvalue()


# ============================================================
# 📥 LOAD CURRENT DATA
# ============================================================

df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_shop = load_shop()
df_advances = load_advances()
df_payments = load_payments()
df_financials = load_financials()


# ============================================================
# 📍 SIDEBAR
# ============================================================

st.sidebar.title("🪚 Workshop Menu")

menu = st.sidebar.radio(
    "📍 Navigation",
    [
        "📊 Dashboard",
        "👷 Manage Workers",
        "📅 Daily Attendance & OT",
        "🌴 Leaves & Holidays",
        "🛒 Shop Items Taken",
        "💸 Money Taken / Advances",
        "💰 Money Paid to Worker",
        "🧮 Monthly Payroll",
        "🔎 Worker Search & Records"
    ]
)

st.sidebar.markdown("---")

st.sidebar.subheader("📥 Export Reports")

st.sidebar.download_button(
    label="📊 Download Complete Excel Report",
    data=generate_excel(),
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)


# ============================================================
# 📊 DASHBOARD
# ============================================================

if menu == "📊 Dashboard":

    st.subheader("📊 Workshop Live Dashboard")

    total_workers = len(df_workers)

    total_earned = (
        df_financials["Total Earned (NPR)"].sum()
        if not df_financials.empty
        else 0
    )

    total_ot = (
        df_logs["OT Money (NPR)"].sum()
        if not df_logs.empty
        else 0
    )

    total_advance = (
        df_advances["Amount (NPR)"].sum()
        if not df_advances.empty
        else 0
    )

    total_due = (
        df_financials["Remaining Due (NPR)"].sum()
        if not df_financials.empty
        else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("👷 Total Workers", total_workers)
    c2.metric("💵 Total Earned", f"NPR {total_earned:,.2f}")
    c3.metric("⏰ Total OT", f"NPR {total_ot:,.2f}")
    c4.metric("💸 Total Advances", f"NPR {total_advance:,.2f}")
    c5.metric("📌 Remaining Due", f"NPR {total_due:,.2f}")

    st.markdown("---")

    st.subheader("📅 Recent Attendance")

    st.dataframe(
        df_logs.head(20),
        use_container_width=True
    )


# ============================================================
# 👷 MANAGE WORKERS
# ============================================================

elif menu == "👷 Manage Workers":

    st.subheader("👷 Manage Workshop Workers")

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("### ➕ Add New Worker")

        with st.form(
            "add_worker_form",
            clear_on_submit=True
        ):

            worker_name = st.text_input(
                "👤 Worker Full Name"
            )

            phone = st.text_input(
                "📱 Phone Number"
            )

            skill = st.selectbox(
                "🛠️ Role / Skill",
                [
                    "🪚 Carpenter",
                    "🪵 Specialist Carpenter",
                    "🎨 Carver",
                    "✨ Finisher / Polisher",
                    "🖌️ Painter",
                    "🤝 Helper",
                    "🔧 Other"
                ]
            )

            start_date = st.date_input(
                "📆 Date Started Working",
                value=date.today()
            )

            submitted = st.form_submit_button(
                "➕ Register Worker"
            )

            if submitted:

                if worker_name.strip():

                    worker_id = get_next_id(
                        "W",
                        "workers",
                        "worker_id"
                    )

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
                        worker_name.strip(),
                        phone.strip(),
                        skill,
                        start_date.isoformat()
                    ))

                    st.success(
                        f"✅ {worker_name} added successfully!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ Please enter the worker name."
                    )

    with col2:

        st.markdown("### ❌ Delete Worker")

        if df_workers.empty:

            st.info("ℹ️ No workers available.")

        else:

            selected_worker = st.selectbox(
                "🔎 Select Worker",
                get_worker_labels(df_workers),
                key="delete_worker"
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            st.warning(
                "⚠️ Deleting a worker can also delete related records."
            )

            if st.button(
                "🗑️ Delete Selected Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (worker_id,)
                )

                st.success(
                    "✅ Worker deleted successfully!"
                )

                st.rerun()

    st.markdown("---")

    st.subheader("📋 Worker List")

    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# 📅 ATTENDANCE AND OT
# ============================================================

elif menu == "📅 Daily Attendance & OT":

    st.subheader(
        "📅 Daily Attendance • 🌓 Half Day • ⏰ Overtime"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

    else:

        selected_worker = st.selectbox(
            "👷 Select Worker",
            get_worker_labels(df_workers)
        )

        worker_id = selected_worker.split(
            " - "
        )[0]

        date_mode = st.radio(
            "📅 Select Work Date Type",
            [
                "📆 One Work Date",
                "🗓️ Multiple Work Dates"
            ],
            horizontal=True
        )

        selected_dates = []

        if date_mode == "📆 One Work Date":

            work_date = st.date_input(
                "📅 Work Date",
                value=date.today()
            )

            selected_dates = [work_date]

        else:

            st.info(
                "💡 Select the start and end date. Every date between them will be recorded."
            )

            date_range = st.date_input(
                "🗓️ Select Work Date Range",
                value=(
                    date.today(),
                    date.today()
                )
            )

            if (
                isinstance(date_range, tuple)
                and len(date_range) == 2
            ):

                start_date = date_range[0]
                end_date = date_range[1]

                current = start_date

                while current <= end_date:

                    selected_dates.append(current)

                    current += timedelta(days=1)

        work_type = st.radio(
            "☀️ Select Work Type",
            [
                "☀️ Full Day",
                "🌓 Half Day"
            ],
            horizontal=True
        )

        if work_type == "☀️ Full Day":

            worked_value = 1.0

        else:

            worked_value = 0.5

        ot_done = st.checkbox(
            "⏰ Did the worker work overtime?"
        )

        if ot_done:

            ot_money = st.number_input(
                "💵 OT Money for EACH Selected Date (NPR)",
                min_value=0.0,
                value=0.0,
                step=50.0
            )

            ot_notes = st.text_input(
                "📝 OT Work Details"
            )

        else:

            ot_money = 0.0
            ot_notes = ""

        remarks = st.text_input(
            "📝 Work Remarks"
        )

        if selected_dates:

            st.info(
                f"📅 Selected Work Dates: {len(selected_dates)} | "
                f"🧮 Worked Day Value: {len(selected_dates) * worked_value}"
            )

        if st.button(
            "💾 Save Attendance Records",
            type="primary"
        ):

            if not selected_dates:

                st.error(
                    "❌ Please select at least one date."
                )

            else:

                saved_count = 0
                skipped_count = 0

                for selected_date in selected_dates:

                    existing = run_query("""
                        SELECT log_id
                        FROM logs
                        WHERE worker_id = ?
                        AND work_date = ?
                    """, (
                        worker_id,
                        selected_date.isoformat()
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
                            selected_date.isoformat(),
                            "Full Day"
                            if worked_value == 1.0
                            else "Half Day",
                            worked_value,
                            1 if ot_done else 0,
                            ot_money,
                            ot_notes,
                            remarks
                        ))

                        saved_count += 1

                    else:

                        skipped_count += 1

                st.success(
                    f"✅ Saved {saved_count} attendance record(s)."
                )

                if skipped_count:

                    st.warning(
                        f"⚠️ Skipped {skipped_count} duplicate date(s)."
                    )

                st.rerun()

        st.markdown("---")

        st.subheader("📋 Attendance Records")

        st.dataframe(
            load_logs(),
            use_container_width=True
        )

        if not df_logs.empty:

            st.subheader("🗑️ Delete Attendance Record")

            log_options = (
                df_logs["Log ID"].astype(str)
                + " | "
                + df_logs["Worker Name"].astype(str)
                + " | "
                + df_logs["Date"].astype(str)
            ).tolist()

            selected_log = st.selectbox(
                "📅 Select Attendance Record",
                log_options
            )

            delete_log_id = selected_log.split(
                " | "
            )[0]

            if st.button("❌ Delete Attendance"):

                run_action(
                    "DELETE FROM logs WHERE log_id = ?",
                    (delete_log_id,)
                )

                st.success(
                    "✅ Attendance deleted."
                )

                st.rerun()


# ============================================================
# 🌴 LEAVES AND HOLIDAYS
# ============================================================

elif menu == "🌴 Leaves & Holidays":

    st.subheader("🌴 Worker Leave & Holiday Records")

    st.info(
        "📅 Leave/Holiday uses ONE DATE only and will not automatically add any work day."
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown("### ➕ Add Leave / Holiday")

            with st.form(
                "leave_form",
                clear_on_submit=True
            ):

                selected_worker = st.selectbox(
                    "👷 Select Worker",
                    get_worker_labels(df_workers),
                    key="leave_worker"
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                leave_date = st.date_input(
                    "🌴 Leave / Holiday Date",
                    value=date.today()
                )

                leave_type = st.selectbox(
                    "🏖️ Leave Type",
                    [
                        "🌴 Casual Leave",
                        "🤒 Sick Leave",
                        "🎉 Festival Holiday",
                        "🏛️ Public Holiday",
                        "❌ Unpaid Leave",
                        "🏖️ Other"
                    ]
                )

                reason = st.text_input(
                    "📝 Reason / Remarks"
                )

                submitted = st.form_submit_button(
                    "💾 Save Leave / Holiday"
                )

                if submitted:

                    existing = run_query("""
                        SELECT leave_id
                        FROM leaves
                        WHERE worker_id = ?
                        AND leave_date = ?
                    """, (
                        worker_id,
                        leave_date.isoformat()
                    ))

                    if not existing.empty:

                        st.warning(
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
                            leave_date.isoformat(),
                            leave_type,
                            1.0,
                            reason
                        ))

                        st.success(
                            "✅ Leave / Holiday recorded!"
                        )

                        st.rerun()

        with col2:

            st.markdown("### ❌ Delete Leave")

            if df_leaves.empty:

                st.info(
                    "ℹ️ No leave records available."
                )

            else:

                leave_options = (
                    df_leaves["Leave ID"].astype(str)
                    + " | "
                    + df_leaves["Worker Name"].astype(str)
                    + " | "
                    + df_leaves["Leave Date"].astype(str)
                ).tolist()

                selected_leave = st.selectbox(
                    "🌴 Select Leave Record",
                    leave_options
                )

                delete_leave_id = selected_leave.split(
                    " | "
                )[0]

                if st.button(
                    "🗑️ Delete Leave Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM leaves WHERE leave_id = ?",
                        (delete_leave_id,)
                    )

                    st.success(
                        "✅ Leave record deleted!"
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_leaves(),
        use_container_width=True
    )


# ============================================================
# 🛒 SHOP ITEMS
# ============================================================

elif menu == "🛒 Shop Items Taken":

    st.subheader("🛒 Shop Items Taken by Workers")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

        with st.form(
            "shop_form",
            clear_on_submit=True
        ):

            selected_worker = st.selectbox(
                "👷 Select Worker",
                get_worker_labels(df_workers)
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            item_date = st.date_input(
                "📅 Date Taken",
                value=date.today()
            )

            item_name = st.text_input(
                "🛒 Item Name"
            )

            item_cost = st.number_input(
                "💵 Item Cost (NPR)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            notes = st.text_input(
                "📝 Notes"
            )

            submitted = st.form_submit_button(
                "➕ Add Shop Item"
            )

            if submitted:

                if item_name.strip():

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
                        item_date.isoformat(),
                        item_name.strip(),
                        item_cost,
                        notes
                    ))

                    st.success(
                        "✅ Shop item recorded!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ Please enter item name."
                    )

    st.markdown("---")

    st.dataframe(
        load_shop(),
        use_container_width=True
    )


# ============================================================
# 💸 ADVANCES
# ============================================================

elif menu == "💸 Money Taken / Advances":

    st.subheader("💸 Worker Money Taken / Advance")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

        with st.form(
            "advance_form",
            clear_on_submit=True
        ):

            selected_worker = st.selectbox(
                "👷 Select Worker",
                get_worker_labels(df_workers)
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            advance_date = st.date_input(
                "📅 Date Money Taken",
                value=date.today()
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

            submitted = st.form_submit_button(
                "💾 Save Advance"
            )

            if submitted:

                if amount > 0:

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
                        advance_date.isoformat(),
                        amount,
                        reason
                    ))

                    st.success(
                        "✅ Advance recorded!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ Enter an amount greater than zero."
                    )

    st.markdown("---")

    st.dataframe(
        load_advances(),
        use_container_width=True
    )


# ============================================================
# 💰 MONEY PAID
# ============================================================

elif menu == "💰 Money Paid to Worker":

    st.subheader("💰 Record Money Paid to Worker")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

        with st.form(
            "payment_form",
            clear_on_submit=True
        ):

            selected_worker = st.selectbox(
                "👷 Select Worker",
                get_worker_labels(df_workers)
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            payment_date = st.date_input(
                "📅 Payment Date",
                value=date.today()
            )

            amount = st.number_input(
                "💰 Amount Paid (NPR)",
                min_value=0.0,
                value=0.0,
                step=100.0
            )

            notes = st.text_input(
                "📝 Payment Notes"
            )

            submitted = st.form_submit_button(
                "💾 Save Payment"
            )

            if submitted:

                if amount > 0:

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
                        payment_date.isoformat(),
                        amount,
                        notes
                    ))

                    st.success(
                        "✅ Payment recorded!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ Enter an amount greater than zero."
                    )

    st.markdown("---")

    st.dataframe(
        load_payments(),
        use_container_width=True
    )


# ============================================================
# 🧮 MONTHLY PAYROLL
# ============================================================

elif menu == "🧮 Monthly Payroll":

    st.subheader("🧮 Automatic Monthly Payroll")

    st.info("""
### 📌 Automatic Calculation

**☀️ Full Day = 1 day**

**🌓 Half Day = 0.5 day**

**⏰ OT = Total OT money entered in attendance**

**💵 Regular Salary = Daily Wage × Total Worked Days**

**💰 Total Earned = Regular Salary + OT Money**

**➖ Remaining Due = Total Earned − Advances − Shop Items − Money Already Paid**
""")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

        selected_worker = st.selectbox(
            "👷 Select Worker for Payroll",
            get_worker_labels(df_workers)
        )

        worker_id = selected_worker.split(
            " - "
        )[0]

        col1, col2, col3 = st.columns(3)

        with col1:

            selected_year = st.selectbox(
                "📅 Select Year",
                list(
                    range(
                        date.today().year - 3,
                        date.today().year + 2
                    )
                ),
                index=3
            )

        with col2:

            month_names = list(calendar.month_name)[1:]

            selected_month_name = st.selectbox(
                "🗓️ Select Month",
                month_names,
                index=date.today().month - 1
            )

            selected_month = month_names.index(
                selected_month_name
            ) + 1

        with col3:

            daily_wage = st.number_input(
                "💵 Daily Wage (NPR)",
                min_value=0.0,
                value=1500.0,
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

            st.subheader(
                f"📊 {selected_month_name} {selected_year} Summary"
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "☀️ Full Days",
                summary["full_days"]
            )

            c2.metric(
                "🌓 Half Days",
                summary["half_days"]
            )

            c3.metric(
                "🧮 Total Worked Days",
                summary["worked_days"]
            )

            c4.metric(
                "🌴 Leave Days",
                summary["leave_days"]
            )

            c5, c6, c7, c8 = st.columns(4)

            c5.metric(
                "⏰ OT Money",
                f"NPR {summary['ot_money']:,.2f}"
            )

            c6.metric(
                "💵 Regular Salary",
                f"NPR {summary['regular_salary']:,.2f}"
            )

            c7.metric(
                "💰 Total Earned",
                f"NPR {summary['total_earned']:,.2f}"
            )

            c8.metric(
                "📌 Remaining Due",
                f"NPR {summary['remaining_due']:,.2f}"
            )

            st.markdown("### ➖ Deductions")

            d1, d2, d3 = st.columns(3)

            d1.metric(
                "💸 Advances",
                f"NPR {summary['advance_total']:,.2f}"
            )

            d2.metric(
                "🛒 Shop Items",
                f"NPR {summary['shop_total']:,.2f}"
            )

            d3.metric(
                "💰 Already Paid",
                f"NPR {summary['paid_total']:,.2f}"
            )

            st.success(
                f"📌 Status: {summary['status']}"
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
                    "✅ Monthly payroll saved successfully!"
                )

                st.rerun()

    st.markdown("---")

    st.subheader("📋 Saved Monthly Payroll Records")

    st.dataframe(
        load_financials(),
        use_container_width=True
    )


# ============================================================
# 🔎 WORKER SEARCH
# ============================================================

elif menu == "🔎 Worker Search & Records":

    st.subheader(
        "🔎 Search Worker and View All Records"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ No workers available."
        )

    else:

        search_name = st.text_input(
            "🔎 Search Worker by Name"
        )

        filtered_workers = df_workers.copy()

        if search_name.strip():

            filtered_workers = filtered_workers[
                filtered_workers["Name"]
                .str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if filtered_workers.empty:

            st.warning(
                "❌ No worker found."
            )

        else:

            selected_worker = st.selectbox(
                "👷 Select Worker",
                get_worker_labels(filtered_workers)
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            worker_info = df_workers[
                df_workers["Worker ID"] == worker_id
            ].iloc[0]

            st.markdown(
                f"## 👷 {worker_info['Name']}"
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "📱 Phone",
                str(worker_info["Phone"])
            )

            c2.metric(
                "🛠️ Skill",
                str(worker_info["Skill"])
            )

            c3.metric(
                "📆 Started",
                str(worker_info["Started Work On"])
            )

            c4.metric(
                "📋 Worker ID",
                str(worker_id)
            )

            st.markdown("---")

            year = st.selectbox(
                "📅 Filter Year",
                list(
                    range(
                        date.today().year - 3,
                        date.today().year + 2
                    )
                ),
                index=3,
                key="search_year"
            )

            month_names = list(calendar.month_name)[1:]

            month_name = st.selectbox(
                "🗓️ Filter Month",
                month_names,
                index=date.today().month - 1,
                key="search_month"
            )

            month = month_names.index(
                month_name
            ) + 1

            month_start, month_end = get_month_range(
                year,
                month
            )

            start_string = month_start.isoformat()
            end_string = month_end.isoformat()

            # ------------------------------------------------
            # 📅 ATTENDANCE
            # ------------------------------------------------

            st.subheader("📅 Work Days")

            attendance = run_query("""
                SELECT
                    work_date AS 'Date',
                    work_status AS 'Work Status',
                    worked_value AS 'Worked Days',
                    CASE
                        WHEN ot_done = 1 THEN 'Yes'
                        ELSE 'No'
                    END AS 'OT Done',
                    ot_money AS 'OT Money (NPR)',
                    ot_notes AS 'OT Details',
                    remarks AS 'Remarks'
                FROM logs
                WHERE worker_id = ?
                AND work_date BETWEEN ? AND ?
                ORDER BY work_date
            """, (
                worker_id,
                start_string,
                end_string
            ))

            if attendance.empty:

                st.info(
                    "ℹ️ No work records for this month."
                )

            else:

                total_worked = attendance[
                    "Worked Days"
                ].sum()

                st.success(
                    f"🧮 Total Worked Days: {total_worked}"
                )

                st.dataframe(
                    attendance,
                    use_container_width=True
                )

            # ------------------------------------------------
            # 🌴 LEAVES
            # ------------------------------------------------

            st.subheader("🌴 Leaves & Holidays")

            worker_leaves = run_query("""
                SELECT
                    leave_date AS 'Date',
                    leave_type AS 'Leave Type',
                    leave_value AS 'Leave Days',
                    reason AS 'Reason'
                FROM leaves
                WHERE worker_id = ?
                AND leave_date BETWEEN ? AND ?
                ORDER BY leave_date
            """, (
                worker_id,
                start_string,
                end_string
            ))

            st.dataframe(
                worker_leaves,
                use_container_width=True
            )

            # ------------------------------------------------
            # 💸 ADVANCES
            # ------------------------------------------------

            st.subheader("💸 Money Taken / Advances")

            worker_advances = run_query("""
                SELECT
                    advance_date AS 'Date',
                    amount AS 'Amount (NPR)',
                    reason AS 'Reason'
                FROM advances
                WHERE worker_id = ?
                AND advance_date BETWEEN ? AND ?
                ORDER BY advance_date
            """, (
                worker_id,
                start_string,
                end_string
            ))

            st.dataframe(
                worker_advances,
                use_container_width=True
            )

            # ------------------------------------------------
            # 🛒 SHOP ITEMS
            # ------------------------------------------------

            st.subheader("🛒 Shop Items")

            worker_shop = run_query("""
                SELECT
                    entry_date AS 'Date',
                    item_name AS 'Item',
                    item_cost AS 'Cost (NPR)',
                    notes AS 'Notes'
                FROM shop_consumption
                WHERE worker_id = ?
                AND entry_date BETWEEN ? AND ?
                ORDER BY entry_date
            """, (
                worker_id,
                start_string,
                end_string
            ))

            st.dataframe(
                worker_shop,
                use_container_width=True
            )

            # ------------------------------------------------
            # 💰 PAYMENTS
            # ------------------------------------------------

            st.subheader("💰 Money Paid")

            worker_payments = run_query("""
                SELECT
                    payment_date AS 'Date',
                    amount AS 'Amount Paid (NPR)',
                    notes AS 'Notes'
                FROM payments
                WHERE worker_id = ?
                AND payment_date BETWEEN ? AND ?
                ORDER BY payment_date
            """, (
                worker_id,
                start_string,
                end_string
            ))

            st.dataframe(
                worker_payments,
                use_container_width=True
            )

            # ------------------------------------------------
            # 🧮 FINANCIAL RECORD
            # ------------------------------------------------

            st.subheader("🧮 Saved Payroll")

            worker_financial = run_query("""
                SELECT
                    month_key AS 'Month',
                    daily_wage AS 'Daily Wage (NPR)',
                    total_worked_days AS 'Worked Days',
                    total_ot_money AS 'OT Money (NPR)',
                    total_earned AS 'Total Earned (NPR)',
                    total_advance AS 'Advance (NPR)',
                    total_shop_deduction AS 'Shop Deduction (NPR)',
                    total_paid AS 'Paid (NPR)',
                    remaining_due AS 'Remaining Due (NPR)',
                    status AS 'Status',
                    updated_at AS 'Updated'
                FROM financials
                WHERE worker_id = ?
                AND month_key = ?
            """, (
                worker_id,
                month_key(year, month)
            ))

            if worker_financial.empty:

                st.info(
                    "ℹ️ No saved payroll yet for this month."
                )

            else:

                st.dataframe(
                    worker_financial,
                    use_container_width=True
                )


# ============================================================
# 🏁 END
# ============================================================
