import streamlit as st
import pandas as pd
import sqlite3
import io
import calendar
import shutil
from pathlib import Path
from datetime import date, datetime, timedelta

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Record & Monthly Payroll System")
st.caption(
    "👷 Attendance • 🌓 Half Days • 🌴 Leaves • ⏰ OT • 💵 Advances • "
    "🛒 Shop Deductions • 💰 Monthly Payroll"
)

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "workshop.db"
BACKUP_DIR = BASE_DIR / "database_backups"
MAX_BACKUPS = 30


def backup_database_on_startup():
    """
    Create a timestamped backup once for each Streamlit process start.
    Do not overwrite the main database.
    Keep the newest MAX_BACKUPS backups.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = BACKUP_DIR / f"workshop_backup_{timestamp}.db"
    try:
        source = sqlite3.connect(str(DB_FILE))
        destination = sqlite3.connect(str(backup_file))
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        backups = sorted(
            BACKUP_DIR.glob("workshop_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for old_backup in backups[MAX_BACKUPS:]:
            try:
                old_backup.unlink()
            except OSError:
                pass

        return backup_file

    except Exception:
        try:
            if backup_file.exists():
                backup_file.unlink()
        except Exception:
            pass
        return None

def startup_backup():
    return backup_database_on_startup()


STARTUP_BACKUP = startup_backup()

def get_connection():
    conn = sqlite3.connect(
        str(DB_FILE),
        check_same_thread=False,
        timeout=30
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def table_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def add_column_if_missing(cursor, table_name, column_name, definition):
    columns = table_columns(cursor, table_name)

    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {definition}"
        )

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # WORKERS
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

        add_column_if_missing(cursor, "workers", "start_date", "TEXT")
        add_column_if_missing(cursor, "workers", "active", "INTEGER DEFAULT 1")

        # WORK LOGS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_type TEXT DEFAULT 'Full Day',
                work_value REAL DEFAULT 1.0,
                ot_hours REAL DEFAULT 0.0,
                ot_money REAL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        add_column_if_missing(cursor, "logs", "work_type", "TEXT DEFAULT 'Full Day'")
        add_column_if_missing(cursor, "logs", "work_value", "REAL DEFAULT 1.0")
        add_column_if_missing(cursor, "logs", "ot_hours", "REAL DEFAULT 0.0")
        add_column_if_missing(cursor, "logs", "ot_money", "REAL DEFAULT 0.0")
        add_column_if_missing(cursor, "logs", "ot_notes", "TEXT")
        add_column_if_missing(cursor, "logs", "remarks", "TEXT")

        # LEAVES
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

        add_column_if_missing(cursor, "leaves", "leave_value", "REAL DEFAULT 1.0")
        add_column_if_missing(cursor, "leaves", "reason", "TEXT")

        # SHOP CONSUMPTION
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

        add_column_if_missing(cursor, "shop_consumption", "notes", "TEXT")

        # ADVANCES
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

        # FINANCIALS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT,
                month_key TEXT,
                daily_wage REAL DEFAULT 0,
                worked_days REAL DEFAULT 0,
                leave_days REAL DEFAULT 0,
                ot_money REAL DEFAULT 0,
                gross_earned REAL DEFAULT 0,
                advance_amount REAL DEFAULT 0,
                shop_deduction REAL DEFAULT 0,
                money_paid REAL DEFAULT 0,
                remaining_due REAL DEFAULT 0,
                status TEXT DEFAULT 'Unpaid',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(worker_id, month_key),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        financial_columns = {
            "worker_id": "TEXT",
            "month_key": "TEXT",
            "daily_wage": "REAL DEFAULT 0",
            "worked_days": "REAL DEFAULT 0",
            "leave_days": "REAL DEFAULT 0",
            "ot_money": "REAL DEFAULT 0",
            "gross_earned": "REAL DEFAULT 0",
            "advance_amount": "REAL DEFAULT 0",
            "shop_deduction": "REAL DEFAULT 0",
            "money_paid": "REAL DEFAULT 0",
            "remaining_due": "REAL DEFAULT 0",
            "status": "TEXT DEFAULT 'Unpaid'",
            "created_at": "TEXT",
            "updated_at": "TEXT"
        }

        for column_name, definition in financial_columns.items():
            add_column_if_missing(
                cursor,
                "financials",
                column_name,
                definition
            )

        # INDEXES
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
            CREATE INDEX IF NOT EXISTS idx_shop_worker_date
            ON shop_consumption(worker_id, entry_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_financials_worker_month
            ON financials(worker_id, month_key)
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_unique_worker_date
            ON logs(worker_id, work_date)
        """)

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_leaves_unique_worker_date
            ON leaves(worker_id, leave_date)
        """)

        conn.commit()


init_db()

def run_query(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def run_action(query, params=()):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()


def get_next_id(prefix, table_name, column_name):
    try:
        df = run_query(f"SELECT {column_name} FROM {table_name}")
    except Exception:
        return f"{prefix}001"

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[column_name].dropna():
        value = str(value)
        digits = "".join(char for char in value if char.isdigit())

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1
    return f"{prefix}{next_number:03d}"


def get_worker_name(worker_id):
    df = run_query(
        "SELECT name FROM workers WHERE worker_id = ?",
        (worker_id,)
    )

    if df.empty:
        return worker_id

    return str(df.iloc[0]["name"])

def month_start_end(month_key):
    year, month = map(int, month_key.split("-"))

    first_day = date(year, month, 1)
    last_day = date(
        year,
        month,
        calendar.monthrange(year, month)[1]
    )

    return first_day, last_day


def month_label(month_key):
    year, month = map(int, month_key.split("-"))

    return date(year, month, 1).strftime("%B %Y")


def get_month_options():
    months = set()

    queries = [
        "SELECT work_date AS d FROM logs",
        "SELECT leave_date AS d FROM leaves",
        "SELECT advance_date AS d FROM advances",
        "SELECT entry_date AS d FROM shop_consumption"
    ]

    for query in queries:
        try:
            df = run_query(query)

            if not df.empty:
                dates = pd.to_datetime(
                    df["d"],
                    errors="coerce"
                ).dropna()

                for value in dates:
                    months.add(value.strftime("%Y-%m"))

        except Exception:
            pass

    months.add(date.today().strftime("%Y-%m"))

    return sorted(months, reverse=True)

def load_workers():
    return run_query("""
        SELECT
            worker_id AS 'Worker ID',
            name AS 'Name',
            phone AS 'Phone',
            skill AS 'Skill',
            start_date AS 'Start Date',
            CASE
                WHEN active = 1 THEN 'Active'
                ELSE 'Inactive'
            END AS 'Status'
        FROM workers
        ORDER BY name
    """)


def load_logs():
    return run_query("""
        SELECT
            l.log_id AS 'Log ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.work_date AS 'Work Date',
            l.work_type AS 'Work Type',
            COALESCE(l.work_value, 1.0) AS 'Worked Days',
            COALESCE(l.ot_hours, 0.0) AS 'OT Hours',
            COALESCE(l.ot_money, 0.0) AS 'OT Money (NPR)',
            COALESCE(l.ot_notes, '') AS 'OT Details',
            COALESCE(l.remarks, '') AS 'Remarks'
        FROM logs l
        LEFT JOIN workers w ON l.worker_id = w.worker_id
        ORDER BY l.work_date DESC, w.name
    """)


def load_leaves():
    return run_query("""
        SELECT
            l.leave_id AS 'Leave ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.leave_date AS 'Leave Date',
            l.leave_type AS 'Leave Type',
            COALESCE(l.leave_value, 1.0) AS 'Leave Days',
            COALESCE(l.reason, '') AS 'Reason'
        FROM leaves l
        LEFT JOIN workers w ON l.worker_id = w.worker_id
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
            COALESCE(s.item_cost, 0.0) AS 'Cost (NPR)',
            COALESCE(s.notes, '') AS 'Notes'
        FROM shop_consumption s
        LEFT JOIN workers w ON s.worker_id = w.worker_id
        ORDER BY s.entry_date DESC, w.name
    """)


def load_advances():
    return run_query("""
        SELECT
            a.advance_id AS 'Advance ID',
            a.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            a.advance_date AS 'Advance Date',
            COALESCE(a.amount, 0.0) AS 'Amount (NPR)',
            COALESCE(a.reason, '') AS 'Reason'
        FROM advances a
        LEFT JOIN workers w ON a.worker_id = w.worker_id
        ORDER BY a.advance_date DESC, w.name
    """)


def load_financials():
    return run_query("""
        SELECT
            f.payment_id AS 'Payment ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month',
            COALESCE(f.daily_wage, 0.0) AS 'Daily Wage (NPR)',
            COALESCE(f.worked_days, 0.0) AS 'Worked Days',
            COALESCE(f.leave_days, 0.0) AS 'Leave Days',
            COALESCE(f.ot_money, 0.0) AS 'OT Money (NPR)',
            COALESCE(f.gross_earned, 0.0) AS 'Gross Earned (NPR)',
            COALESCE(f.advance_amount, 0.0) AS 'Advance Deduction (NPR)',
            COALESCE(f.shop_deduction, 0.0) AS 'Shop Deduction (NPR)',
            COALESCE(f.money_paid, 0.0) AS 'Money Paid (NPR)',
            COALESCE(f.remaining_due, 0.0) AS 'Remaining Due (NPR)',
            COALESCE(f.status, 'Unpaid') AS 'Status'
        FROM financials f
        LEFT JOIN workers w ON f.worker_id = w.worker_id
        WHERE f.worker_id IS NOT NULL
        ORDER BY f.month_key DESC, w.name
    """)

def calculate_monthly_summary(worker_id, month_key):
    start_date, end_date = month_start_end(month_key)

    worker_df = run_query(
        "SELECT start_date FROM workers WHERE worker_id = ?",
        (worker_id,)
    )

    worker_start = None

    if not worker_df.empty:
        value = worker_df.iloc[0]["start_date"]

        if pd.notna(value) and str(value).strip():
            try:
                worker_start = datetime.strptime(
                    str(value),
                    "%Y-%m-%d"
                ).date()
            except Exception:
                worker_start = None

    logs = run_query("""
        SELECT
            work_date,
            COALESCE(work_value, 1.0) AS work_value,
            COALESCE(ot_money, 0.0) AS ot_money
        FROM logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    if worker_start and not logs.empty:
        logs = logs[
            pd.to_datetime(
                logs["work_date"],
                errors="coerce"
            ).dt.date >= worker_start
        ]

    worked_days = (
        pd.to_numeric(logs["work_value"], errors="coerce")
        .fillna(0)
        .sum()
        if not logs.empty else 0.0
    )

    total_ot_money = (
        pd.to_numeric(logs["ot_money"], errors="coerce")
        .fillna(0)
        .sum()
        if not logs.empty else 0.0
    )

    leaves = run_query("""
        SELECT
            leave_date,
            COALESCE(leave_value, 1.0) AS leave_value
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    if worker_start and not leaves.empty:
        leaves = leaves[
            pd.to_datetime(
                leaves["leave_date"],
                errors="coerce"
            ).dt.date >= worker_start
        ]

    leave_days = (
        pd.to_numeric(leaves["leave_value"], errors="coerce")
        .fillna(0)
        .sum()
        if not leaves.empty else 0.0
    )

    advances = run_query("""
        SELECT COALESCE(amount, 0.0) AS amount
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    advance_total = (
        pd.to_numeric(advances["amount"], errors="coerce")
        .fillna(0)
        .sum()
        if not advances.empty else 0.0
    )

    shop = run_query("""
        SELECT COALESCE(item_cost, 0.0) AS item_cost
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    ))

    shop_total = (
        pd.to_numeric(shop["item_cost"], errors="coerce")
        .fillna(0)
        .sum()
        if not shop.empty else 0.0
    )

    return {
        "month_key": month_key,
        "worked_days": float(worked_days),
        "leave_days": float(leave_days),
        "ot_money": float(total_ot_money),
        "advance_total": float(advance_total),
        "shop_total": float(shop_total),
        "work_record_count": len(logs),
        "leave_record_count": len(leaves)
    }


def save_monthly_financial(worker_id, month_key, daily_wage, money_paid):
    summary = calculate_monthly_summary(worker_id, month_key)

    worked_days = summary["worked_days"]
    leave_days = summary["leave_days"]
    ot_money = summary["ot_money"]
    advance_total = summary["advance_total"]
    shop_total = summary["shop_total"]

    gross_earned = (daily_wage * worked_days) + ot_money

    remaining_due = (
        gross_earned
        - advance_total
        - shop_total
        - money_paid
    )

    if remaining_due <= 0:
        status = "Fully Settled"
    elif money_paid > 0 or advance_total > 0:
        status = "Partially Paid"
    else:
        status = "Unpaid"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = run_query("""
        SELECT payment_id
        FROM financials
        WHERE worker_id = ?
        AND month_key = ?
    """, (worker_id, month_key))

    if existing.empty:
        payment_id = get_next_id("P", "financials", "payment_id")

        run_action("""
            INSERT INTO financials (
                payment_id, worker_id, month_key, daily_wage,
                worked_days, leave_days, ot_money, gross_earned,
                advance_amount, shop_deduction, money_paid,
                remaining_due, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payment_id, worker_id, month_key, daily_wage,
            worked_days, leave_days, ot_money, gross_earned,
            advance_total, shop_total, money_paid,
            remaining_due, status, now, now
        ))
    else:
        payment_id = str(existing.iloc[0]["payment_id"])

        run_action("""
            UPDATE financials
            SET daily_wage = ?,
                worked_days = ?,
                leave_days = ?,
                ot_money = ?,
                gross_earned = ?,
                advance_amount = ?,
                shop_deduction = ?,
                money_paid = ?,
                remaining_due = ?,
                status = ?,
                updated_at = ?
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            daily_wage, worked_days, leave_days, ot_money,
            gross_earned, advance_total, shop_total,
            money_paid, remaining_due, status, now,
            worker_id, month_key
        ))

    return {
        "payment_id": payment_id,
        "worked_days": worked_days,
        "leave_days": leave_days,
        "ot_money": ot_money,
        "advance_total": advance_total,
        "shop_total": shop_total,
        "gross_earned": gross_earned,
        "remaining_due": remaining_due,
        "status": status
    }


def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def generate_excel():
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        load_workers().to_excel(writer, sheet_name="Workers", index=False)
        load_logs().to_excel(writer, sheet_name="Work Logs", index=False)
        load_leaves().to_excel(writer, sheet_name="Leaves", index=False)
        load_advances().to_excel(writer, sheet_name="Advances", index=False)
        load_consumption().to_excel(
            writer,
            sheet_name="Shop Deductions",
            index=False
        )
        load_financials().to_excel(
            writer,
            sheet_name="Monthly Payroll",
            index=False
        )

    return output.getvalue()
df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_advances = load_advances()
df_consumption = load_consumption()
df_financials = load_financials()
st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Choose Section",
    [
        "📊 Dashboard & Monthly View",
        "👷 Manage Workers",
        "📝 Log Work & OT",
        "🌴 Leaves & Holidays",
        "💵 Advances / Money Taken",
        "🛒 Shop Items Consumed",
        "💰 Financial Payouts",
        "🔎 Worker Search & Records"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("💾 Database & Backups")

st.sidebar.success(
    f"Permanent database: {DB_FILE.name}"
)

if STARTUP_BACKUP:
    st.sidebar.info(
        f"✅ Startup backup created:\n"
        f"{STARTUP_BACKUP.name}"
    )
else:
    st.sidebar.info(
        "ℹ️ No startup backup was needed or the database "
        "did not exist yet."
    )

backup_files = sorted(
    BACKUP_DIR.glob("workshop_backup_*.db"),
    key=lambda p: p.stat().st_mtime,
    reverse=True
)

st.sidebar.caption(
    f"📦 Stored backups: {len(backup_files)} / {MAX_BACKUPS}"
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Reports")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Download All Records Excel",
    data=excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
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
        "📝 Work Logs CSV",
        convert_df_to_csv(df_logs),
        f"work_logs_{date.today()}.csv",
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
        "💵 Advances CSV",
        convert_df_to_csv(df_advances),
        f"advances_{date.today()}.csv",
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
        "💰 Financial CSV",
        convert_df_to_csv(df_financials),
        f"financials_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

if menu == "📊 Dashboard & Monthly View":
    st.subheader("📊 Workshop Live Summary")

    total_workers = len(df_workers)

    total_worked_days = (
        pd.to_numeric(df_logs["Worked Days"], errors="coerce")
        .fillna(0).sum()
        if not df_logs.empty else 0
    )

    total_ot_money = (
        pd.to_numeric(df_logs["OT Money (NPR)"], errors="coerce")
        .fillna(0).sum()
        if not df_logs.empty else 0
    )

    total_advances = (
        pd.to_numeric(df_advances["Amount (NPR)"], errors="coerce")
        .fillna(0).sum()
        if not df_advances.empty else 0
    )

    total_paid = (
        pd.to_numeric(df_financials["Money Paid (NPR)"], errors="coerce")
        .fillna(0).sum()
        if not df_financials.empty else 0
    )

    total_due = (
        pd.to_numeric(df_financials["Remaining Due (NPR)"], errors="coerce")
        .fillna(0).sum()
        if not df_financials.empty else 0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("👷 Workers", total_workers)
    c2.metric("📅 Worked Days", f"{total_worked_days:.1f}")
    c3.metric("⏰ OT Money", f"NPR {total_ot_money:,.2f}")
    c4.metric("💵 Advances", f"NPR {total_advances:,.2f}")
    c5.metric("💰 Paid", f"NPR {total_paid:,.2f}")
    c6.metric("📌 Remaining", f"NPR {total_due:,.2f}")

    st.markdown("---")
    st.subheader("📅 Monthly Attendance Records")

    if df_logs.empty:
        st.info("ℹ️ No work records available yet.")
    else:
        logs_copy = df_logs.copy()

        logs_copy["Month Key"] = pd.to_datetime(
            logs_copy["Work Date"],
            errors="coerce"
        ).dt.strftime("%Y-%m")

        months = sorted(
            logs_copy["Month Key"].dropna().unique(),
            reverse=True
        )

        selected_month = st.selectbox("📅 Select Month", months)

        monthly_logs = logs_copy[
            logs_copy["Month Key"] == selected_month
        ]

        st.success(
            f"📊 Total worked days for {month_label(selected_month)}: "
            f"{monthly_logs['Worked Days'].sum():.1f}"
        )

        st.dataframe(
            monthly_logs.drop(columns=["Month Key"]),
            use_container_width=True
        )

elif menu == "👷 Manage Workers":
    st.subheader("👷 Workshop Workers")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### ➕ Add New Worker")

        with st.form("add_worker_form", clear_on_submit=True):
            worker_id = get_next_id("W", "workers", "worker_id")

            name = st.text_input("👤 Worker Full Name")
            phone = st.text_input("📱 Mobile Number")

            skill = st.selectbox(
                "🛠️ Role / Skill",
                [
                    "Specialist Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Painter",
                    "Helper",
                    "Other"
                ]
            )

            start_date = st.date_input(
                "📅 Starting Date of Work",
                date.today()
            )

            submit = st.form_submit_button("➕ Register Worker")

            if submit:
                if not name.strip():
                    st.error("⚠️ Please enter the worker's name.")
                else:
                    run_action("""
                        INSERT INTO workers (
                            worker_id, name, phone, skill,
                            start_date, active
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

                    st.success(f"✅ {name} added successfully!")
                    st.rerun()

    with col2:
        st.markdown("### 🗑️ Delete Worker")

        if df_workers.empty:
            st.info("ℹ️ No workers available.")
        else:
            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox("👤 Select Worker", worker_options)
            delete_worker_id = selected.split(" - ", 1)[0]

            if st.button("🗑️ Delete Selected Worker", type="primary"):
                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (delete_worker_id,)
                )

                st.success("✅ Worker deleted successfully!")
                st.rerun()

    st.markdown("---")
    st.dataframe(load_workers(), use_container_width=True)

elif menu == "📝 Log Work & OT":
    st.subheader("📝 Record Work Attendance & Overtime")

    if df_workers.empty:
        st.warning("⚠️ Please add a worker first.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### ➕ Add Work Record")

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options,
                key="work_worker"
            )

            worker_id = selected_worker.split(" - ", 1)[0]

            date_mode = st.radio(
                "📅 Choose Date Selection Type",
                ["📆 Single Date", "📅 Date Range"],
                horizontal=True
            )

            if date_mode == "📆 Single Date":
                selected_work_dates = [
                    st.date_input(
                        "📅 Select Work Date",
                        date.today()
                    )
                ]
            else:
                selected_range = st.date_input(
                    "📅 Select Start and End Date",
                    value=(date.today(), date.today())
                )

                if (
                    isinstance(selected_range, (tuple, list))
                    and len(selected_range) == 2
                ):
                    start_work_date = selected_range[0]
                    end_work_date = selected_range[1]

                    if start_work_date > end_work_date:
                        start_work_date, end_work_date = (
                            end_work_date,
                            start_work_date
                        )

                    selected_work_dates = []
                    current_date = start_work_date

                    while current_date <= end_work_date:
                        selected_work_dates.append(current_date)
                        current_date += timedelta(days=1)
                else:
                    selected_work_dates = []

            st.info(
                f"📌 Total selected work dates: "
                f"{len(selected_work_dates)}"
            )

            work_type = st.radio(
                "🕒 Work Type",
                ["☀️ Full Day", "🌓 Half Day"],
                horizontal=True
            )

            work_value = 1.0 if work_type == "☀️ Full Day" else 0.5

            st.markdown("---")
            st.markdown("### ⏰ Overtime")

            has_ot = st.radio(
                "Did the worker work OT?",
                ["❌ No OT", "✅ Yes, Worked OT"],
                horizontal=True
            )

            if has_ot == "✅ Yes, Worked OT":
                ot_hours = st.number_input(
                    "⏱️ OT Hours",
                    min_value=0.0,
                    value=1.0,
                    step=0.5
                )

                ot_money = st.number_input(
                    "💵 OT Money for Each Selected Date (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=50.0
                )

                ot_notes = st.text_input("📋 OT Work Details")
            else:
                ot_hours = 0.0
                ot_money = 0.0
                ot_notes = ""

            remarks = st.text_input("📝 Work Remarks")

            if st.button("💾 Save Work Record", type="primary"):
                if not selected_work_dates:
                    st.error("⚠️ Please select a valid date.")
                else:
                    added = 0
                    skipped = 0

                    for work_date in selected_work_dates:
                        date_string = work_date.strftime("%Y-%m-%d")

                        existing = run_query("""
                            SELECT log_id
                            FROM logs
                            WHERE worker_id = ?
                            AND work_date = ?
                        """, (worker_id, date_string))

                        if existing.empty:
                            log_id = get_next_id(
                                "L",
                                "logs",
                                "log_id"
                            )

                            run_action("""
                                INSERT INTO logs (
                                    log_id, worker_id, work_date,
                                    work_type, work_value,
                                    ot_hours, ot_money,
                                    ot_notes, remarks
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                log_id,
                                worker_id,
                                date_string,
                                "Full Day" if work_value == 1.0 else "Half Day",
                                work_value,
                                ot_hours,
                                ot_money,
                                ot_notes,
                                remarks
                            ))

                            added += 1
                        else:
                            skipped += 1

                    if added > 0:
                        st.success(
                            f"✅ {added} work record(s) saved successfully!"
                        )

                    if skipped > 0:
                        st.warning(
                            f"⚠️ {skipped} date(s) already had work "
                            f"records and were skipped."
                        )

                    st.rerun()

        with col2:
            st.markdown("### 🗑️ Delete Work Record")

            if df_logs.empty:
                st.info("ℹ️ No work records available.")
            else:
                log_options = (
                    df_logs["Log ID"].astype(str)
                    + " | "
                    + df_logs["Worker Name"].astype(str)
                    + " | "
                    + df_logs["Work Date"].astype(str)
                )

                selected_log = st.selectbox(
                    "📝 Select Work Record",
                    log_options
                )

                log_id = selected_log.split(" | ", 1)[0]

                if st.button("🗑️ Delete Work Record", type="primary"):
                    run_action(
                        "DELETE FROM logs WHERE log_id = ?",
                        (log_id,)
                    )

                    st.success("✅ Work record deleted.")
                    st.rerun()

        st.markdown("---")
        st.dataframe(load_logs(), use_container_width=True)

elif menu == "🌴 Leaves & Holidays":
    st.subheader("🌴 Worker Leaves & Holidays")

    if df_workers.empty:
        st.warning("⚠️ Please add a worker first.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### ➕ Add Leave Record")

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

            worker_id = selected_worker.split(" - ", 1)[0]

            leave_date = st.date_input(
                "📅 Leave / Holiday Date",
                date.today()
            )

            leave_type = st.selectbox(
                "🌴 Leave Type",
                [
                    "Casual Leave",
                    "Sick Leave",
                    "Festival / Public Holiday",
                    "Unpaid Leave",
                    "Other"
                ]
            )

            leave_value = st.radio(
                "🕒 Leave Duration",
                ["🌞 Full Day", "🌓 Half Day"],
                horizontal=True
            )

            leave_days = 1.0 if leave_value == "🌞 Full Day" else 0.5

            reason = st.text_input("📝 Reason / Remarks")

            if st.button("💾 Save Leave Record", type="primary"):
                date_string = leave_date.strftime("%Y-%m-%d")

                existing = run_query("""
                    SELECT leave_id
                    FROM leaves
                    WHERE worker_id = ?
                    AND leave_date = ?
                """, (worker_id, date_string))

                if not existing.empty:
                    st.error(
                        "⚠️ A leave record already exists for this "
                        "worker on this date."
                    )
                else:
                    leave_id = get_next_id("LV", "leaves", "leave_id")

                    run_action("""
                        INSERT INTO leaves (
                            leave_id, worker_id, leave_date,
                            leave_type, leave_value, reason
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        leave_id,
                        worker_id,
                        date_string,
                        leave_type,
                        leave_days,
                        reason
                    ))

                    st.success("✅ Leave record saved successfully!")
                    st.rerun()

        with col2:
            st.markdown("### 🗑️ Delete Leave Record")

            if df_leaves.empty:
                st.info("ℹ️ No leave records available.")
            else:
                leave_options = (
                    df_leaves["Leave ID"].astype(str)
                    + " | "
                    + df_leaves["Worker Name"].astype(str)
                    + " | "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "🌴 Select Leave Record",
                    leave_options
                )

                leave_id = selected_leave.split(" | ", 1)[0]

                if st.button("🗑️ Delete Leave Record", type="primary"):
                    run_action(
                        "DELETE FROM leaves WHERE leave_id = ?",
                        (leave_id,)
                    )

                    st.success("✅ Leave record deleted.")
                    st.rerun()

        st.markdown("---")
        st.dataframe(load_leaves(), use_container_width=True)
elif menu == "💵 Advances / Money Taken":
    st.subheader("💵 Worker Advances / Money Taken")

    if df_workers.empty:
        st.warning("⚠️ Please add a worker first.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### ➕ Record Advance")

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

            worker_id = selected_worker.split(" - ", 1)[0]

            advance_date = st.date_input(
                "📅 Advance Date",
                date.today()
            )

            amount = st.number_input(
                "💵 Advance Amount (NPR)",
                min_value=0.0,
                value=0.0,
                step=100.0
            )

            reason = st.text_input("📝 Reason for Advance")

            if st.button("💾 Save Advance", type="primary"):
                if amount <= 0:
                    st.error(
                        "⚠️ Enter an advance amount greater than zero."
                    )
                else:
                    advance_id = get_next_id(
                        "A",
                        "advances",
                        "advance_id"
                    )

                    run_action("""
                        INSERT INTO advances (
                            advance_id, worker_id,
                            advance_date, amount, reason
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
                        f"✅ NPR {amount:,.2f} advance recorded!"
                    )
                    st.rerun()

        with col2:
            st.markdown("### 🗑️ Delete Advance")

            if df_advances.empty:
                st.info("ℹ️ No advance records available.")
            else:
                advance_options = (
                    df_advances["Advance ID"].astype(str)
                    + " | "
                    + df_advances["Worker Name"].astype(str)
                    + " | NPR "
                    + df_advances["Amount (NPR)"].astype(str)
                )

                selected_advance = st.selectbox(
                    "💵 Select Advance",
                    advance_options
                )

                advance_id = selected_advance.split(" | ", 1)[0]

                if st.button("🗑️ Delete Advance", type="primary"):
                    run_action(
                        "DELETE FROM advances WHERE advance_id = ?",
                        (advance_id,)
                    )

                    st.success("✅ Advance deleted.")
                    st.rerun()

        st.markdown("---")
        st.dataframe(load_advances(), use_container_width=True)
elif menu == "🛒 Shop Items Consumed":
    st.subheader("🛒 Shop & Canteen Items Consumed")

    if df_workers.empty:
        st.warning("⚠️ Please add a worker first.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### ➕ Add Shop Deduction")

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

            worker_id = selected_worker.split(" - ", 1)[0]

            item_date = st.date_input("📅 Date", date.today())
            item_name = st.text_input("🛒 Item Name")

            item_cost = st.number_input(
                "💰 Cost (NPR)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            notes = st.text_input("📝 Notes")

            if st.button("💾 Save Shop Record", type="primary"):
                if not item_name.strip():
                    st.error("⚠️ Please enter the item name.")
                elif item_cost <= 0:
                    st.error("⚠️ Enter an amount greater than zero.")
                else:
                    item_id = get_next_id(
                        "C",
                        "shop_consumption",
                        "item_id"
                    )

                    run_action("""
                        INSERT INTO shop_consumption (
                            item_id, worker_id, entry_date,
                            item_name, item_cost, notes
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        item_id,
                        worker_id,
                        item_date.strftime("%Y-%m-%d"),
                        item_name.strip(),
                        item_cost,
                        notes
                    ))

                    st.success("✅ Shop deduction recorded!")
                    st.rerun()

        with col2:
            st.markdown("### 🗑️ Delete Shop Record")

            if df_consumption.empty:
                st.info("ℹ️ No shop records available.")
            else:
                shop_options = (
                    df_consumption["Item ID"].astype(str)
                    + " | "
                    + df_consumption["Worker Name"].astype(str)
                    + " | "
                    + df_consumption["Item"].astype(str)
                )

                selected_shop = st.selectbox(
                    "🛒 Select Shop Record",
                    shop_options
                )

                item_id = selected_shop.split(" | ", 1)[0]

                if st.button("🗑️ Delete Shop Record", type="primary"):
                    run_action(
                        "DELETE FROM shop_consumption WHERE item_id = ?",
                        (item_id,)
                    )

                    st.success("✅ Shop record deleted.")
                    st.rerun()

        st.markdown("---")
        st.dataframe(
            load_consumption(),
            use_container_width=True
        )

elif menu == "💰 Financial Payouts":
    st.subheader("💰 Monthly Financial Payouts")

    if df_workers.empty:
        st.warning("⚠️ Please add a worker first.")
    else:
        worker_options = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "👷 Select Worker for Payroll",
            worker_options,
            key="payroll_worker"
        )

        worker_id = selected_worker.split(" - ", 1)[0]

        months = get_month_options()

        selected_month = st.selectbox(
            "📅 Select Payroll Month",
            months,
            format_func=month_label
        )

        summary = calculate_monthly_summary(
            worker_id,
            selected_month
        )

        st.markdown("---")
        st.markdown(
            f"### 📊 Automatic Summary: "
            f"{get_worker_name(worker_id)} - "
            f"{month_label(selected_month)}"
        )

        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("📅 Worked Days", f"{summary['worked_days']:.1f}")
        c2.metric("🌴 Leave Days", f"{summary['leave_days']:.1f}")
        c3.metric("⏰ OT Money", f"NPR {summary['ot_money']:,.2f}")
        c4.metric("💵 Advances", f"NPR {summary['advance_total']:,.2f}")
        c5.metric("🛒 Shop Deductions", f"NPR {summary['shop_total']:,.2f}")

        existing_financial = run_query("""
            SELECT daily_wage, money_paid
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (worker_id, selected_month))

        default_wage = 1500.0
        default_paid = 0.0

        if not existing_financial.empty:
            default_wage = float(
                existing_financial.iloc[0]["daily_wage"] or 0
            )
            default_paid = float(
                existing_financial.iloc[0]["money_paid"] or 0
            )

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            daily_wage = st.number_input(
                "💰 Daily Wage Rate (NPR)",
                min_value=0.0,
                value=default_wage,
                step=100.0
            )

        with col2:
            money_paid = st.number_input(
                "💵 Total Money Paid This Month (NPR)",
                min_value=0.0,
                value=default_paid,
                step=100.0
            )

        gross_preview = (
            daily_wage * summary["worked_days"]
            + summary["ot_money"]
        )

        due_preview = (
            gross_preview
            - summary["advance_total"]
            - summary["shop_total"]
            - money_paid
        )

        st.markdown("### 🧮 Automatic Salary Calculation")

        p1, p2, p3 = st.columns(3)

        p1.metric("💰 Gross Earned", f"NPR {gross_preview:,.2f}")

        p2.metric(
            "➖ Total Deductions",
            f"NPR "
            f"{summary['advance_total'] + summary['shop_total']:,.2f}"
        )

        p3.metric("📌 Remaining Due", f"NPR {due_preview:,.2f}")

        st.info(
            "🧮 Formula: Gross = (Daily Wage × Worked Days) + OT Money. "
            "Remaining = Gross − Advances − Shop Deductions − Money Paid."
        )

        if st.button(
            "💾 Save / Update Monthly Financial Record",
            type="primary"
        ):
            result = save_monthly_financial(
                worker_id,
                selected_month,
                daily_wage,
                money_paid
            )

            st.success(
                f"✅ Financial record {result['payment_id']} saved successfully!"
            )
            st.rerun()

    st.markdown("---")
    st.markdown("### 📋 All Monthly Financial Records")

    st.dataframe(
        load_financials(),
        use_container_width=True
    )

elif menu == "🔎 Worker Search & Records":
    st.subheader("🔎 Search Worker and View Complete Records")

    if df_workers.empty:
        st.warning("⚠️ No workers available.")
    else:
        worker_options = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "👷 Search Worker",
            worker_options
        )

        worker_id = selected_worker.split(" - ", 1)[0]

        months = get_month_options()

        selected_month = st.selectbox(
            "📅 Select Month",
            months,
            format_func=month_label
        )

        summary = calculate_monthly_summary(
            worker_id,
            selected_month
        )

        st.markdown("---")
        st.markdown(f"## 👤 {get_worker_name(worker_id)}")

        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("📅 Worked Days", f"{summary['worked_days']:.1f}")
        c2.metric("🌴 Leave Days", f"{summary['leave_days']:.1f}")
        c3.metric("⏰ OT Money", f"NPR {summary['ot_money']:,.2f}")
        c4.metric("💵 Advances", f"NPR {summary['advance_total']:,.2f}")
        c5.metric("🛒 Shop Deductions", f"NPR {summary['shop_total']:,.2f}")

        start_date, end_date = month_start_end(selected_month)

        st.markdown("---")
        st.markdown("### 📝 Work Records")

        worker_logs = run_query("""
            SELECT
                l.log_id AS 'Log ID',
                l.work_date AS 'Date',
                l.work_type AS 'Work Type',
                COALESCE(l.work_value, 1.0) AS 'Worked Days',
                COALESCE(l.ot_hours, 0.0) AS 'OT Hours',
                COALESCE(l.ot_money, 0.0) AS 'OT Money (NPR)',
                COALESCE(l.ot_notes, '') AS 'OT Details',
                COALESCE(l.remarks, '') AS 'Remarks'
            FROM logs l
            WHERE l.worker_id = ?
            AND l.work_date BETWEEN ? AND ?
            ORDER BY l.work_date
        """, (
            worker_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))

        st.dataframe(worker_logs, use_container_width=True)

        st.markdown("### 🌴 Leave Records")

        worker_leaves = run_query("""
            SELECT
                leave_id AS 'Leave ID',
                leave_date AS 'Date',
                leave_type AS 'Leave Type',
                COALESCE(leave_value, 1.0) AS 'Leave Days',
                COALESCE(reason, '') AS 'Reason'
            FROM leaves
            WHERE worker_id = ?
            AND leave_date BETWEEN ? AND ?
            ORDER BY leave_date
        """, (
            worker_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))

        st.dataframe(worker_leaves, use_container_width=True)

        st.markdown("### 💵 Advance Records")

        worker_advances = run_query("""
            SELECT
                advance_id AS 'Advance ID',
                advance_date AS 'Date',
                amount AS 'Amount (NPR)',
                COALESCE(reason, '') AS 'Reason'
            FROM advances
            WHERE worker_id = ?
            AND advance_date BETWEEN ? AND ?
            ORDER BY advance_date
        """, (
            worker_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))

        st.dataframe(worker_advances, use_container_width=True)

        st.markdown("### 🛒 Shop Item Records")

        worker_shop = run_query("""
            SELECT
                item_id AS 'Item ID',
                entry_date AS 'Date',
                item_name AS 'Item',
                item_cost AS 'Cost (NPR)',
                COALESCE(notes, '') AS 'Notes'
            FROM shop_consumption
            WHERE worker_id = ?
            AND entry_date BETWEEN ? AND ?
            ORDER BY entry_date
        """, (
            worker_id,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ))

        st.dataframe(worker_shop, use_container_width=True)

        st.markdown("### 💰 Monthly Payroll Record")

        worker_financial = run_query("""
            SELECT
                payment_id AS 'Payment ID',
                month_key AS 'Month',
                daily_wage AS 'Daily Wage (NPR)',
                worked_days AS 'Worked Days',
                leave_days AS 'Leave Days',
                ot_money AS 'OT Money (NPR)',
                gross_earned AS 'Gross Earned (NPR)',
                advance_amount AS 'Advance Deduction (NPR)',
                shop_deduction AS 'Shop Deduction (NPR)',
                money_paid AS 'Money Paid (NPR)',
                remaining_due AS 'Remaining Due (NPR)',
                status AS 'Status'
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (worker_id, selected_month))

        if worker_financial.empty:
            st.info(
                "ℹ️ No saved financial payout record for this month yet."
            )
        else:
            st.dataframe(
                worker_financial,
                use_container_width=True
            )
