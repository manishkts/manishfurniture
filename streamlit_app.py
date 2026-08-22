import streamlit as st
import pandas as pd
from datetime import date, datetime
import calendar
import sqlite3
import io

# ============================================================
# 🪚 FURNITURE WORKSHOP RECORD SYSTEM
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    layout="wide"
)

st.title("🪚 Permanent Furniture Workshop Record System")

DB_FILE = "workshop.db"


# ============================================================
# 🗄️ DATABASE FUNCTIONS
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def add_column_if_missing(cursor, table_name, column_name, definition):
    columns = [
        row[1]
        for row in cursor.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    ]

    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # ====================================================
        # 👷 WORKERS
        # ====================================================

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

        # ====================================================
        # 📝 DAILY WORK LOGS
        # ====================================================

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
                UNIQUE(worker_id, work_date),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

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

        # ====================================================
        # 🌴 LEAVES
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                reason TEXT,
                UNIQUE(worker_id, leave_date),
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ====================================================
        # 🛒 SHOP CONSUMPTION
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL NOT NULL,
                notes TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ====================================================
        # 💸 ADVANCES
        # ====================================================

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

        # ====================================================
        # 💵 PAYMENTS
        # ====================================================

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

        # ====================================================
        # 💰 FIX OLD FINANCIAL TABLE
        # ====================================================

        table_exists = cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name='financials'
        """).fetchone()

        if table_exists:

            financial_columns = [
                row[1]
                for row in cursor.execute(
                    "PRAGMA table_info(financials)"
                ).fetchall()
            ]

            # Old database used log_id.
            # New database uses worker_id + month_key.
            if (
                "worker_id" not in financial_columns
                or "month_key" not in financial_columns
            ):

                backup_exists = cursor.execute("""
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table'
                    AND name='financials_old_backup'
                """).fetchone()

                if not backup_exists:
                    cursor.execute("""
                        ALTER TABLE financials
                        RENAME TO financials_old_backup
                    """)
                else:
                    cursor.execute("""
                        DROP TABLE financials
                    """)

        # ====================================================
        # 💰 MONTHLY FINANCIALS
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,

                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,

                daily_wage REAL NOT NULL DEFAULT 0,

                total_worked_days REAL DEFAULT 0,
                total_ot_money REAL DEFAULT 0,

                total_earned REAL DEFAULT 0,

                total_advance REAL DEFAULT 0,
                total_shop_deduction REAL DEFAULT 0,
                total_paid REAL DEFAULT 0,

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

        # ====================================================
        # 🔎 INDEXES
        # ====================================================

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_worker_date
            ON logs(worker_id, work_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_leaves_worker_date
            ON leaves(worker_id, leave_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_financials_worker_month
            ON financials(worker_id, month_key)
        """)

        conn.commit()


# ============================================================
# ⚙️ DATABASE HELPERS
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


def get_next_id(prefix, table, column):
    df = run_query(
        f"SELECT {column} FROM {table}"
    )

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[column].dropna():
        digits = "".join(
            char for char in str(value)
            if char.isdigit()
        )

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


def month_bounds(month_key):
    year, month = map(int, month_key.split("-"))

    start_date = f"{year:04d}-{month:02d}-01"

    last_day = calendar.monthrange(year, month)[1]

    end_date = (
        f"{year:04d}-{month:02d}-{last_day:02d}"
    )

    return start_date, end_date


def month_label(month_key):
    year, month = map(int, month_key.split("-"))
    return f"{calendar.month_name[month]} {year}"


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
            start_date AS 'Started Work'
        FROM workers
        WHERE active = 1
        ORDER BY name
    """)


def load_logs():
    return run_query("""
        SELECT
            l.log_id AS 'Log ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.work_date AS 'Date',
            l.work_status AS 'Work Type',
            l.worked_value AS 'Worked Days',
            l.ot_done AS 'OT Done',
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
            l.leave_id AS 'Leave ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.leave_date AS 'Leave Date',
            l.leave_type AS 'Leave Type',
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
            s.item_name AS 'Item Consumed',
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
            p.amount AS 'Amount (NPR)',
            p.notes AS 'Notes'
        FROM payments p
        LEFT JOIN workers w
            ON p.worker_id = w.worker_id
        ORDER BY p.payment_date DESC, w.name
    """)


def load_financials():
    return run_query("""
        SELECT
            f.payment_id AS 'Payment ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month Key',
            f.daily_wage AS 'Daily Wage (NPR)',
            f.total_worked_days AS 'Total Worked Days',
            f.total_ot_money AS 'Total OT Money (NPR)',
            f.total_earned AS 'Total Earned (NPR)',
            f.total_advance AS 'Money Taken / Advance (NPR)',
            f.total_shop_deduction AS 'Shop Deduction (NPR)',
            f.total_paid AS 'Total Paid (NPR)',
            f.remaining_due AS 'Remaining Due (NPR)',
            f.status AS 'Status'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# 🧮 MONTHLY CALCULATION
# ============================================================

def monthly_summary(worker_id, month_key):

    start_date, end_date = month_bounds(month_key)

    work_data = run_query("""
        SELECT
            COALESCE(SUM(worked_value), 0) AS worked_days,
            COALESCE(SUM(ot_money), 0) AS ot_money
        FROM logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date,
        end_date
    ))

    leave_data = run_query("""
        SELECT COUNT(*) AS leave_days
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date,
        end_date
    ))

    advance_data = run_query("""
        SELECT COALESCE(SUM(amount), 0) AS total_advance
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date,
        end_date
    ))

    shop_data = run_query("""
        SELECT COALESCE(SUM(item_cost), 0) AS total_shop
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date,
        end_date
    ))

    payment_data = run_query("""
        SELECT COALESCE(SUM(amount), 0) AS total_paid
        FROM payments
        WHERE worker_id = ?
        AND payment_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date,
        end_date
    ))

    return {
        "worked_days": float(
            work_data.iloc[0]["worked_days"]
        ),
        "ot_money": float(
            work_data.iloc[0]["ot_money"]
        ),
        "leave_days": int(
            leave_data.iloc[0]["leave_days"]
        ),
        "advance": float(
            advance_data.iloc[0]["total_advance"]
        ),
        "shop": float(
            shop_data.iloc[0]["total_shop"]
        ),
        "paid": float(
            payment_data.iloc[0]["total_paid"]
        )
    }


# ============================================================
# 💾 SAVE MONTHLY FINANCIAL
# ============================================================

def save_monthly_financial(
    worker_id,
    month_key,
    daily_wage
):

    summary = monthly_summary(
        worker_id,
        month_key
    )

    total_earned = (
        summary["worked_days"] * daily_wage
    ) + summary["ot_money"]

    remaining_due = (
        total_earned
        - summary["advance"]
        - summary["shop"]
        - summary["paid"]
    )

    if remaining_due <= 0:
        status = "Fully Settled"

    elif (
        summary["advance"] > 0
        or summary["paid"] > 0
    ):
        status = "Partially Paid"

    else:
        status = "Unpaid"

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    existing = run_query("""
        SELECT payment_id
        FROM financials
        WHERE worker_id = ?
        AND month_key = ?
    """, (
        worker_id,
        month_key
    ))

    # ========================================================
    # ➕ INSERT NEW MONTHLY RECORD
    # ========================================================

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
                total_earned,
                total_advance,
                total_shop_deduction,
                total_paid,
                remaining_due,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payment_id,
            worker_id,
            month_key,
            daily_wage,
            summary["worked_days"],
            summary["ot_money"],
            total_earned,
            summary["advance"],
            summary["shop"],
            summary["paid"],
            remaining_due,
            status,
            now,
            now
        ))

    # ========================================================
    # 🔄 UPDATE EXISTING MONTHLY RECORD
    # ========================================================

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
            daily_wage,
            summary["worked_days"],
            summary["ot_money"],
            total_earned,
            summary["advance"],
            summary["shop"],
            summary["paid"],
            remaining_due,
            status,
            now,
            worker_id,
            month_key
        ))


# ============================================================
# 🚀 INITIALIZE DATABASE
# ============================================================

init_db()

df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_advances = load_advances()
df_payments = load_payments()
df_financials = load_financials()


# ============================================================
# 📥 EXPORT EXCEL
# ============================================================

def generate_excel():

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df_workers.to_excel(
            writer,
            sheet_name="Workers",
            index=False
        )

        df_logs.to_excel(
            writer,
            sheet_name="Attendance",
            index=False
        )

        df_leaves.to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        df_consumption.to_excel(
            writer,
            sheet_name="Shop Consumption",
            index=False
        )

        df_advances.to_excel(
            writer,
            sheet_name="Advances",
            index=False
        )

        df_payments.to_excel(
            writer,
            sheet_name="Payments",
            index=False
        )

        df_financials.to_excel(
            writer,
            sheet_name="Monthly Financials",
            index=False
        )

    return output.getvalue()


# ============================================================
# 📍 SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Go to:",
    [
        "📊 Dashboard & Monthly View",
        "👥 Manage Workers",
        "📝 Log Daily Work & OT",
        "🌴 Manage Leaves & Holidays",
        "🛒 Shop Items Consumed",
        "💸 Money Taken / Advance",
        "💵 Worker Payments",
        "💰 Financial Payouts",
        "🔎 Search Worker Records"
    ]
)

st.sidebar.markdown("---")

st.sidebar.download_button(
    label="📥 Export All Data (Excel .xlsx)",
    data=generate_excel(),
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)


# ============================================================
# 📊 DASHBOARD
# ============================================================

if menu == "📊 Dashboard & Monthly View":

    st.subheader("📊 Workshop Live Summary")

    total_earned = (
        df_financials["Total Earned (NPR)"].sum()
        if not df_financials.empty
        else 0
    )

    total_ot = (
        df_financials["Total OT Money (NPR)"].sum()
        if not df_financials.empty
        else 0
    )

    total_due = (
        df_financials["Remaining Due (NPR)"].sum()
        if not df_financials.empty
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "👷 Active Workers",
        len(df_workers)
    )

    col2.metric(
        "💰 Total Labor Bill",
        f"NPR {total_earned:,.2f}"
    )

    col3.metric(
        "⏰ Total OT Money",
        f"NPR {total_ot:,.2f}"
    )

    col4.metric(
        "📌 Remaining Due",
        f"NPR {total_due:,.2f}"
    )

    st.markdown("---")

    if not df_logs.empty:

        available_months = sorted(
            pd.to_datetime(
                df_logs["Date"]
            ).dt.strftime("%Y-%m").unique(),
            reverse=True
        )

        selected_month = st.selectbox(
            "🗓️ Select Month",
            available_months,
            format_func=month_label
        )

        monthly_logs = df_logs[
            pd.to_datetime(
                df_logs["Date"]
            ).dt.strftime("%Y-%m")
            == selected_month
        ]

        st.subheader(
            f"📋 Attendance for {month_label(selected_month)}"
        )

        st.dataframe(
            monthly_logs,
            use_container_width=True
        )

    else:
        st.info("ℹ️ No attendance records yet.")


# ============================================================
# 👥 MANAGE WORKERS
# ============================================================

elif menu == "👥 Manage Workers":

    st.subheader("👥 Workshop Carpentry Team")

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("### ➕ Add New Worker")

        with st.form(
            "add_worker",
            clear_on_submit=True
        ):

            name = st.text_input(
                "👤 Worker Full Name"
            )

            phone = st.text_input(
                "📱 Mobile Number"
            )

            skill = st.selectbox(
                "🛠️ Role / Specialist Area",
                [
                    "Specialist Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Helper"
                ]
            )

            start_date = st.date_input(
                "📅 Date Started Work",
                date.today()
            )

            submit = st.form_submit_button(
                "➕ Register New Worker"
            )

            if submit:

                if not name.strip():

                    st.warning(
                        "⚠️ Please enter worker name."
                    )

                else:

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
                        name.strip(),
                        phone,
                        skill,
                        start_date.isoformat()
                    ))

                    st.success(
                        "✅ Worker registered successfully!"
                    )

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

            selected = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            if st.button(
                "❌ Delete Selected Worker",
                type="primary"
            ):

                worker_id = selected.split(
                    " - "
                )[0]

                run_action("""
                    DELETE FROM workers
                    WHERE worker_id = ?
                """, (worker_id,))

                st.success(
                    "✅ Worker deleted successfully."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# 📝 LOG DAILY WORK & OT
# ============================================================

elif menu == "📝 Log Daily Work & OT":

    st.subheader("📝 Record Daily Work & OT")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

    else:

        with st.form(
            "attendance_form",
            clear_on_submit=True
        ):

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            selected_dates = st.date_input(
                "📅 Select Work Date or Date Range",
                date.today()
            )

            work_type = st.selectbox(
                "🕘 Work Type",
                [
                    "Full Day",
                    "Half Day"
                ]
            )

            worked_value = (
                1.0
                if work_type == "Full Day"
                else 0.5
            )

            did_ot = st.checkbox(
                "⏰ Did the worker do overtime?"
            )

            if did_ot:

                ot_money = st.number_input(
                    "💵 Total OT Money for Each Selected Date (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=50.0
                )

                ot_notes = st.text_input(
                    "📝 OT Details"
                )

            else:

                ot_money = 0.0
                ot_notes = ""

            remarks = st.text_input(
                "💬 Remarks"
            )

            submit = st.form_submit_button(
                "💾 Save Work Record"
            )

            if submit:

                # Streamlit date_input:
                # One date -> date object
                # Range -> tuple(start_date, end_date)

                if isinstance(
                    selected_dates,
                    tuple
                ):

                    start_day = selected_dates[0]
                    end_day = selected_dates[1]

                    date_list = pd.date_range(
                        start_day,
                        end_day,
                        freq="D"
                    ).date.tolist()

                else:

                    date_list = [selected_dates]

                saved_count = 0
                skipped_count = 0

                with get_connection() as conn:

                    cursor = conn.cursor()

                    for work_date in date_list:

                        work_date_text = (
                            work_date.isoformat()
                        )

                        existing = cursor.execute("""
                            SELECT log_id
                            FROM logs
                            WHERE worker_id = ?
                            AND work_date = ?
                        """, (
                            worker_id,
                            work_date_text
                        )).fetchone()

                        if existing:

                            skipped_count += 1
                            continue

                        log_id = get_next_id(
                            "L",
                            "logs",
                            "log_id"
                        )

                        cursor.execute("""
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
                            work_date_text,
                            work_type,
                            worked_value,
                            int(did_ot),
                            ot_money,
                            ot_notes,
                            remarks
                        ))

                        saved_count += 1

                    conn.commit()

                st.success(
                    f"✅ Saved {saved_count} work record(s)."
                )

                if skipped_count > 0:

                    st.warning(
                        f"⚠️ {skipped_count} date(s) already existed and were not duplicated."
                    )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_logs(),
        use_container_width=True
    )


# ============================================================
# 🌴 LEAVES
# ============================================================

elif menu == "🌴 Manage Leaves & Holidays":

    st.subheader("🌴 Worker Leaves & Holidays")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

    else:

        with st.form(
            "leave_form",
            clear_on_submit=True
        ):

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            leave_date = st.date_input(
                "📅 Leave Date",
                date.today()
            )

            leave_type = st.selectbox(
                "🌴 Leave Type",
                [
                    "Casual Leave",
                    "Sick Leave",
                    "Festival / Public Holiday",
                    "Unpaid Leave"
                ]
            )

            reason = st.text_input(
                "💬 Reason / Remarks"
            )

            submit = st.form_submit_button(
                "💾 Record Leave"
            )

            if submit:

                try:

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
                            reason
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        leave_id,
                        worker_id,
                        leave_date.isoformat(),
                        leave_type,
                        reason
                    ))

                    st.success(
                        "✅ Leave recorded successfully."
                    )

                    st.rerun()

                except sqlite3.IntegrityError:

                    st.warning(
                        "⚠️ This worker already has a leave record for this date."
                    )

    st.markdown("---")

    st.dataframe(
        load_leaves(),
        use_container_width=True
    )


# ============================================================
# 🛒 SHOP ITEMS
# ============================================================

elif menu == "🛒 Shop Items Consumed":

    st.subheader(
        "🛒 Shop & Canteen Items Consumed"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

    else:

        with st.form(
            "shop_form",
            clear_on_submit=True
        ):

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            entry_date = st.date_input(
                "📅 Date",
                date.today()
            )

            item_name = st.text_input(
                "🛒 Item Consumed / Taken"
            )

            item_cost = st.number_input(
                "💰 Cost (NPR)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            notes = st.text_input(
                "💬 Notes"
            )

            submit = st.form_submit_button(
                "💾 Record Item"
            )

            if submit and item_name.strip():

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
                    entry_date.isoformat(),
                    item_name,
                    item_cost,
                    notes
                ))

                st.success(
                    "✅ Shop item recorded."
                )

                st.rerun()

    st.dataframe(
        load_consumption(),
        use_container_width=True
    )


# ============================================================
# 💸 ADVANCE / MONEY TAKEN
# ============================================================

elif menu == "💸 Money Taken / Advance":

    st.subheader("💸 Money Taken / Advance")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

    else:

        with st.form(
            "advance_form",
            clear_on_submit=True
        ):

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            advance_date = st.date_input(
                "📅 Date",
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

            submit = st.form_submit_button(
                "💾 Save Advance"
            )

            if submit and amount > 0:

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
                    "✅ Advance recorded successfully."
                )

                st.rerun()

    st.dataframe(
        load_advances(),
        use_container_width=True
    )


# ============================================================
# 💵 WORKER PAYMENTS
# ============================================================

elif menu == "💵 Worker Payments":

    st.subheader("💵 Payment Made to Worker")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

    else:

        with st.form(
            "payment_form",
            clear_on_submit=True
        ):

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_options
            )

            worker_id = selected_worker.split(
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
                "📝 Notes"
            )

            submit = st.form_submit_button(
                "💾 Save Payment"
            )

            if submit and amount > 0:

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
                    "✅ Payment recorded successfully."
                )

                st.rerun()

    st.dataframe(
        load_payments(),
        use_container_width=True
    )


# ============================================================
# 💰 MONTHLY FINANCIAL PAYOUT
# ============================================================

elif menu == "💰 Financial Payouts":

    st.subheader(
        "💰 Monthly Financial Payout Calculator"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add at least one worker first."
        )

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

        worker_id = selected_worker.split(
            " - "
        )[0]

        worker_logs = df_logs[
            df_logs["Worker ID"] == worker_id
        ] if not df_logs.empty else pd.DataFrame()

        months = set()

        months.add(
            date.today().strftime("%Y-%m")
        )

        if not worker_logs.empty:

            log_months = pd.to_datetime(
                worker_logs["Date"]
            ).dt.strftime("%Y-%m").unique()

            months.update(log_months)

        available_months = sorted(
            months,
            reverse=True
        )

        month_key = st.selectbox(
            "🗓️ Select Month",
            available_months,
            format_func=month_label
        )

        existing_wage = run_query("""
            SELECT daily_wage
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            worker_id,
            month_key
        ))

        default_wage = (
            float(existing_wage.iloc[0]["daily_wage"])
            if not existing_wage.empty
            else 1500.0
        )

        daily_wage = st.number_input(
            "💰 Daily Wage (NPR)",
            min_value=0.0,
            value=default_wage,
            step=100.0
        )

        summary = monthly_summary(
            worker_id,
            month_key
        )

        regular_wage = (
            summary["worked_days"]
            * daily_wage
        )

        total_earned = (
            regular_wage
            + summary["ot_money"]
        )

        remaining_due = (
            total_earned
            - summary["advance"]
            - summary["shop"]
            - summary["paid"]
        )

        st.markdown("---")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "📅 Total Worked Days",
            f"{summary['worked_days']:.1f}"
        )

        col2.metric(
            "🌴 Leave Days",
            summary["leave_days"]
        )

        col3.metric(
            "⏰ OT Money",
            f"NPR {summary['ot_money']:,.2f}"
        )

        col4.metric(
            "📌 Remaining Due",
            f"NPR {remaining_due:,.2f}"
        )

        st.markdown("### 🧮 Automatic Calculation")

        st.info(
            f"""
**Regular Wage:**  
{summary['worked_days']:.1f} worked days × NPR {daily_wage:,.2f}
= **NPR {regular_wage:,.2f}**

**OT Money:** NPR {summary['ot_money']:,.2f}

**Total Earned:** **NPR {total_earned:,.2f}**

**Money Taken / Advance:** NPR {summary['advance']:,.2f}

**Shop Deductions:** NPR {summary['shop']:,.2f}

**Already Paid:** NPR {summary['paid']:,.2f}

**Remaining Due:** **NPR {remaining_due:,.2f}**
            """
        )

        if st.button(
            "💾 Save / Update Monthly Financial Record",
            type="primary"
        ):

            save_monthly_financial(
                worker_id,
                month_key,
                daily_wage
            )

            st.success(
                "✅ Monthly financial record saved successfully!"
            )

            st.rerun()

    st.markdown("---")

    st.dataframe(
        load_financials(),
        use_container_width=True
    )


# ============================================================
# 🔎 SEARCH WORKER RECORDS
# ============================================================

elif menu == "🔎 Search Worker Records":

    st.subheader(
        "🔎 Search Complete Worker Records"
    )

    if df_workers.empty:

        st.info(
            "ℹ️ No workers found."
        )

    else:

        selected_name = st.selectbox(
            "👤 Search Worker by Name",
            df_workers["Name"].tolist()
        )

        worker_row = df_workers[
            df_workers["Name"] == selected_name
        ].iloc[0]

        worker_id = worker_row["Worker ID"]

        st.markdown(
            f"## 👷 {selected_name}"
        )

        st.write(
            f"🆔 **Worker ID:** {worker_id}"
        )

        st.write(
            f"🛠️ **Role:** {worker_row['Skill']}"
        )

        st.write(
            f"📅 **Started Work:** {worker_row['Started Work']}"
        )

        worker_logs = df_logs[
            df_logs["Worker ID"] == worker_id
        ] if not df_logs.empty else pd.DataFrame()

        if not worker_logs.empty:

            months = sorted(
                pd.to_datetime(
                    worker_logs["Date"]
                ).dt.strftime("%Y-%m").unique(),
                reverse=True
            )

            selected_month = st.selectbox(
                "🗓️ Select Month",
                months,
                format_func=month_label
            )

            start_date, end_date = month_bounds(
                selected_month
            )

        else:

            start_date = "0000-01-01"
            end_date = "9999-12-31"

        st.markdown("---")

        st.markdown("### 📝 Work Records")

        work_records = run_query("""
            SELECT *
            FROM logs
            WHERE worker_id = ?
            AND work_date BETWEEN ? AND ?
            ORDER BY work_date
        """, (
            worker_id,
            start_date,
            end_date
        ))

        st.dataframe(
            work_records,
            use_container_width=True
        )

        st.markdown("### 🌴 Leave Records")

        leave_records = run_query("""
            SELECT *
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
            leave_records,
            use_container_width=True
        )

        st.markdown("### 💸 Money Taken / Advance")

        advance_records = run_query("""
            SELECT *
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
            advance_records,
            use_container_width=True
        )

        st.markdown("### 🛒 Shop Items")

        shop_records = run_query("""
            SELECT *
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
            shop_records,
            use_container_width=True
        )

        st.markdown("### 💵 Payments")

        payment_records = run_query("""
            SELECT *
            FROM payments
            WHERE worker_id = ?
            AND payment_date BETWEEN ? AND ?
            ORDER BY payment_date
        """, (
            worker_id,
            start_date,
            end_date
        ))

        st.dataframe(
            payment_records,
            use_container_width=True
        )

        st.markdown("### 💰 Monthly Financial Records")

        financial_records = run_query("""
            SELECT *
            FROM financials
            WHERE worker_id = ?
            ORDER BY month_key DESC
        """, (
            worker_id,
        ))

        st.dataframe(
            financial_records,
            use_container_width=True
        )
