import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import date, datetime

# =========================================================
# 🪚 FURNITURE WORKSHOP RECORD SYSTEM
# =========================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

DB_FILE = "workshop.db"


# =========================================================
# 🔧 DATABASE HELPERS
# =========================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row["name"] for row in rows]


def add_column_if_missing(conn, table_name, column_name, definition):
    cols = table_columns(conn, table_name)
    if column_name not in cols:
        conn.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {definition}"
        )


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # -------------------------------------------------
        # 👷 WORKERS
        # -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                skill TEXT,
                start_date TEXT
            )
        """)

        add_column_if_missing(
            conn, "workers", "start_date", "TEXT"
        )

        # -------------------------------------------------
        # 📅 DAILY WORK LOGS
        # work_fraction:
        # 1.0 = full day
        # 0.5 = half day
        # -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_fraction REAL NOT NULL DEFAULT 1.0,
                ot_done INTEGER NOT NULL DEFAULT 0,
                ot_money REAL NOT NULL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE,
                UNIQUE(worker_id, work_date)
            )
        """)

        add_column_if_missing(
            conn, "logs", "work_fraction",
            "REAL NOT NULL DEFAULT 1.0"
        )
        add_column_if_missing(
            conn, "logs", "ot_done",
            "INTEGER NOT NULL DEFAULT 0"
        )
        add_column_if_missing(
            conn, "logs", "ot_money",
            "REAL NOT NULL DEFAULT 0.0"
        )
        add_column_if_missing(
            conn, "logs", "ot_notes", "TEXT"
        )
        add_column_if_missing(
            conn, "logs", "remarks", "TEXT"
        )

        # Compatibility with old database
        cols = table_columns(conn, "logs")

        if "ot_hours" not in cols:
            try:
                conn.execute(
                    "ALTER TABLE logs "
                    "ADD COLUMN ot_hours REAL DEFAULT 0.0"
                )
            except sqlite3.OperationalError:
                pass

        # -------------------------------------------------
        # 🏖️ LEAVES / HOLIDAYS
        # One leave record = one date
        # -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                leave_fraction REAL NOT NULL DEFAULT 1.0,
                reason TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE,
                UNIQUE(worker_id, leave_date)
            )
        """)

        add_column_if_missing(
            conn, "leaves", "leave_fraction",
            "REAL NOT NULL DEFAULT 1.0"
        )

        # -------------------------------------------------
        # 🛒 SHOP CONSUMPTION
        # -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL NOT NULL DEFAULT 0.0,
                notes TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------
        # 💸 SEPARATE ADVANCES
        # -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                advance_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                advance_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                reason TEXT,
                month_key TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # -------------------------------------------------
        # 💰 MONTHLY FINANCIALS
        # One record per worker per month
        # -------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                daily_wage REAL NOT NULL DEFAULT 0.0,
                worked_days REAL NOT NULL DEFAULT 0.0,
                total_ot_money REAL NOT NULL DEFAULT 0.0,
                gross_earned REAL NOT NULL DEFAULT 0.0,
                advance_total REAL NOT NULL DEFAULT 0.0,
                shop_deduction REAL NOT NULL DEFAULT 0.0,
                received_money REAL NOT NULL DEFAULT 0.0,
                remaining_due REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT '🔴 Unpaid',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE,
                UNIQUE(worker_id, month_key)
            )
        """)

        # Add missing financial columns for old DB versions
        financial_columns = {
            "worker_id": "TEXT",
            "month_key": "TEXT",
            "daily_wage": "REAL NOT NULL DEFAULT 0.0",
            "worked_days": "REAL NOT NULL DEFAULT 0.0",
            "total_ot_money": "REAL NOT NULL DEFAULT 0.0",
            "gross_earned": "REAL NOT NULL DEFAULT 0.0",
            "advance_total": "REAL NOT NULL DEFAULT 0.0",
            "shop_deduction": "REAL NOT NULL DEFAULT 0.0",
            "received_money": "REAL NOT NULL DEFAULT 0.0",
            "remaining_due": "REAL NOT NULL DEFAULT 0.0",
            "status": "TEXT NOT NULL DEFAULT '🔴 Unpaid'",
            "created_at": "TEXT",
            "updated_at": "TEXT"
        }

        for col_name, definition in financial_columns.items():
            add_column_if_missing(
                conn,
                "financials",
                col_name,
                definition
            )

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


def get_next_id(prefix, table, id_col):
    try:
        df = run_query(f"SELECT {id_col} FROM {table}")
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[id_col].dropna():
        digits = "".join(
            character
            for character in str(value)
            if character.isdigit()
        )

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


# =========================================================
# 📥 DATA LOADERS
# =========================================================

def load_workers():
    return run_query("""
        SELECT
            worker_id AS 'Worker ID',
            name AS 'Name',
            phone AS 'Phone',
            skill AS 'Skill',
            start_date AS 'Started Work'
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
            CASE
                WHEN l.work_fraction = 0.5
                THEN '🌗 Half Day'
                ELSE '☀️ Full Day'
            END AS 'Work Type',
            l.work_fraction AS 'Worked Days',
            CASE
                WHEN l.ot_done = 1 THEN '✅ Yes'
                ELSE '❌ No'
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
            l.leave_id AS 'Leave ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.leave_date AS 'Leave Date',
            l.leave_type AS 'Leave Type',
            CASE
                WHEN l.leave_fraction = 0.5
                THEN '🌗 Half Day'
                ELSE '🏖️ Full Day'
            END AS 'Leave Duration',
            l.reason AS 'Reason / Remarks'
        FROM leaves l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.leave_date DESC, w.name
    """)


def load_advances():
    return run_query("""
        SELECT
            a.advance_id AS 'Advance ID',
            a.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            a.advance_date AS 'Advance Date',
            a.month_key AS 'Month',
            a.amount AS 'Advance Amount (NPR)',
            a.reason AS 'Reason'
        FROM advances a
        LEFT JOIN workers w
            ON a.worker_id = w.worker_id
        ORDER BY a.advance_date DESC, w.name
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


def load_financials():
    return run_query("""
        SELECT
            f.payment_id AS 'Payment ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month',
            f.daily_wage AS 'Daily Wage (NPR)',
            f.worked_days AS 'Worked Days',
            f.total_ot_money AS 'Total OT Money (NPR)',
            f.gross_earned AS 'Gross Earned (NPR)',
            f.advance_total AS 'Total Advance (NPR)',
            f.shop_deduction AS 'Shop Deduction (NPR)',
            f.received_money AS 'Salary Paid (NPR)',
            f.remaining_due AS 'Remaining Due (NPR)',
            f.status AS 'Status'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# =========================================================
# 🧮 CALCULATION FUNCTIONS
# =========================================================

def get_month_work_summary(worker_id, month_key):
    df = run_query("""
        SELECT
            COALESCE(SUM(work_fraction), 0) AS worked_days,
            COALESCE(SUM(ot_money), 0) AS total_ot_money,
            COUNT(*) AS total_work_records
        FROM logs
        WHERE worker_id = ?
          AND substr(work_date, 1, 7) = ?
    """, (worker_id, month_key))

    if df.empty:
        return {
            "worked_days": 0.0,
            "total_ot_money": 0.0,
            "total_work_records": 0
        }

    row = df.iloc[0]

    return {
        "worked_days": float(row["worked_days"] or 0),
        "total_ot_money": float(row["total_ot_money"] or 0),
        "total_work_records": int(row["total_work_records"] or 0)
    }


def get_month_leave_summary(worker_id, month_key):
    df = run_query("""
        SELECT
            COALESCE(SUM(leave_fraction), 0) AS leave_days
        FROM leaves
        WHERE worker_id = ?
          AND substr(leave_date, 1, 7) = ?
    """, (worker_id, month_key))

    if df.empty:
        return 0.0

    return float(df.iloc[0]["leave_days"] or 0)


def get_month_advance(worker_id, month_key):
    df = run_query("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_advance
        FROM advances
        WHERE worker_id = ?
          AND month_key = ?
    """, (worker_id, month_key))

    if df.empty:
        return 0.0

    return float(df.iloc[0]["total_advance"] or 0)


def get_month_shop_deduction(worker_id, month_key):
    df = run_query("""
        SELECT
            COALESCE(SUM(item_cost), 0) AS total_cost
        FROM shop_consumption
        WHERE worker_id = ?
          AND substr(entry_date, 1, 7) = ?
    """, (worker_id, month_key))

    if df.empty:
        return 0.0

    return float(df.iloc[0]["total_cost"] or 0)


def calculate_status(remaining_due, gross_earned):
    if gross_earned <= 0:
        return "⚪ No Earnings"

    if remaining_due <= 0:
        return "✅ Fully Settled"

    if remaining_due < gross_earned:
        return "🟡 Partially Paid"

    return "🔴 Unpaid"


def calculate_monthly_salary(
    worker_id,
    month_key,
    daily_wage,
    received_money
):
    summary = get_month_work_summary(worker_id, month_key)

    worked_days = summary["worked_days"]
    total_ot_money = summary["total_ot_money"]

    total_advance = get_month_advance(
        worker_id,
        month_key
    )

    shop_deduction = get_month_shop_deduction(
        worker_id,
        month_key
    )

    wage_amount = daily_wage * worked_days

    gross_earned = (
        wage_amount
        + total_ot_money
    )

    remaining_due = (
        gross_earned
        - total_advance
        - shop_deduction
        - received_money
    )

    status = calculate_status(
        remaining_due,
        gross_earned
    )

    return {
        "worked_days": worked_days,
        "total_ot_money": total_ot_money,
        "total_advance": total_advance,
        "shop_deduction": shop_deduction,
        "gross_earned": gross_earned,
        "remaining_due": remaining_due,
        "status": status
    }


def save_monthly_financial(
    worker_id,
    month_key,
    daily_wage,
    received_money
):
    calculation = calculate_monthly_salary(
        worker_id,
        month_key,
        daily_wage,
        received_money
    )

    existing = run_query("""
        SELECT payment_id
        FROM financials
        WHERE worker_id = ?
          AND month_key = ?
    """, (worker_id, month_key))

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

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
                worked_days,
                total_ot_money,
                gross_earned,
                advance_total,
                shop_deduction,
                received_money,
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
            calculation["worked_days"],
            calculation["total_ot_money"],
            calculation["gross_earned"],
            calculation["total_advance"],
            calculation["shop_deduction"],
            received_money,
            calculation["remaining_due"],
            calculation["status"],
            now,
            now
        ))

    else:

        payment_id = existing.iloc[0]["payment_id"]

        run_action("""
            UPDATE financials
            SET
                daily_wage = ?,
                worked_days = ?,
                total_ot_money = ?,
                gross_earned = ?,
                advance_total = ?,
                shop_deduction = ?,
                received_money = ?,
                remaining_due = ?,
                status = ?,
                updated_at = ?
            WHERE payment_id = ?
        """, (
            daily_wage,
            calculation["worked_days"],
            calculation["total_ot_money"],
            calculation["gross_earned"],
            calculation["total_advance"],
            calculation["shop_deduction"],
            received_money,
            calculation["remaining_due"],
            calculation["status"],
            now,
            payment_id
        ))

    return calculation


# =========================================================
# 📊 LOAD DATA
# =========================================================

df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_advances = load_advances()
df_consumption = load_consumption()
df_financials = load_financials()


# =========================================================
# 📥 EXPORT FUNCTIONS
# =========================================================

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
            sheet_name="Work Records",
            index=False
        )

        df_leaves.to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        df_advances.to_excel(
            writer,
            sheet_name="Advances",
            index=False
        )

        df_consumption.to_excel(
            writer,
            sheet_name="Shop Items",
            index=False
        )

        df_financials.to_excel(
            writer,
            sheet_name="Monthly Financials",
            index=False
        )

    return output.getvalue()


def convert_csv(df):
    return df.to_csv(
        index=False
    ).encode("utf-8")


# =========================================================
# 🎨 HEADER
# =========================================================

st.title("🪚 Permanent Furniture Workshop Record System")
st.caption(
    "👷 Workers • 📅 Attendance • 🌗 Half Days • ⏱️ OT • 🏖️ Leaves • 💸 Advances • 💰 Monthly Salary"
)


# =========================================================
# 📍 SIDEBAR
# =========================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Choose an option:",
    [
        "📊 Dashboard",
        "👷 Manage Workers",
        "📅 Work Attendance & OT",
        "🏖️ Leaves & Holidays",
        "💸 Advance Money",
        "🛒 Shop Items",
        "💰 Monthly Financial Payout",
        "🔎 Worker Search"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Records")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Download All Records (Excel)",
    data=excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("📄 Download CSV Files"):

    st.download_button(
        "👷 Workers CSV",
        convert_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "📅 Work Records CSV",
        convert_csv(df_logs),
        f"work_records_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "🏖️ Leaves CSV",
        convert_csv(df_leaves),
        f"leaves_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "💸 Advances CSV",
        convert_csv(df_advances),
        f"advances_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "💰 Financials CSV",
        convert_csv(df_financials),
        f"financials_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )


# =========================================================
# 📊 DASHBOARD
# =========================================================

if menu == "📊 Dashboard":

    st.subheader("📊 Workshop Dashboard")

    total_workers = len(df_workers)

    total_worked_days = (
        pd.to_numeric(
            df_logs["Worked Days"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_logs.empty
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

    total_advances = (
        pd.to_numeric(
            df_advances["Advance Amount (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_advances.empty
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

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("👷 Workers", total_workers)
    c2.metric("📅 Total Worked Days", f"{total_worked_days:.1f}")
    c3.metric("⏱️ Total OT", f"NPR {total_ot:,.2f}")
    c4.metric("💸 Total Advances", f"NPR {total_advances:,.2f}")
    c5.metric("💰 Remaining Due", f"NPR {total_due:,.2f}")

    st.markdown("---")

    st.subheader("📅 Monthly Summary")

    if df_logs.empty:
        st.info("📭 No work records available yet.")
    else:
        month_list = sorted(
            pd.to_datetime(
                df_logs["Work Date"]
            ).dt.strftime("%Y-%m").unique(),
            reverse=True
        )

        selected_month = st.selectbox(
            "🗓️ Select Month",
            month_list
        )

        month_logs = df_logs[
            df_logs["Work Date"].astype(str).str.startswith(
                selected_month
            )
        ]

        st.dataframe(
            month_logs,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# 👷 MANAGE WORKERS
# =========================================================

elif menu == "👷 Manage Workers":

    st.subheader("👷 Manage Workshop Workers")

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

            worker_name = st.text_input(
                "👤 Worker Full Name"
            )

            worker_phone = st.text_input(
                "📱 Mobile Number"
            )

            worker_skill = st.selectbox(
                "🛠️ Role / Skill",
                [
                    "Specialist Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Helper",
                    "Other"
                ]
            )

            worker_start_date = st.date_input(
                "🚀 Date Started Work",
                date.today()
            )

            submit = st.form_submit_button(
                "➕ Register Worker"
            )

            if submit:

                if not worker_name.strip():
                    st.error("⚠️ Please enter the worker name.")

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
                        worker_name.strip(),
                        worker_phone.strip(),
                        worker_skill,
                        worker_start_date.strftime("%Y-%m-%d")
                    ))

                    st.success(
                        f"✅ {worker_name} added successfully!"
                    )

                    st.rerun()

    with col2:

        st.markdown("### 🗑️ Delete Worker")

        if df_workers.empty:

            st.info("📭 No workers available.")

        else:

            choices = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "👷 Select Worker",
                choices
            )

            delete_worker_id = selected.split(
                " - "
            )[0]

            if st.button(
                "🗑️ Delete Selected Worker",
                type="primary"
            ):

                run_action("""
                    DELETE FROM workers
                    WHERE worker_id = ?
                """, (delete_worker_id,))

                st.success("🗑️ Worker deleted.")
                st.rerun()

    st.markdown("---")
    st.dataframe(
        df_workers,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 📅 WORK ATTENDANCE & OT
# =========================================================

elif menu == "📅 Work Attendance & OT":

    st.subheader("📅 Record Work Attendance & ⏱️ OT")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        st.markdown(
            "### ➕ Add Work Record"
        )

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "👷 Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(
            " - "
        )[0]

        work_type = st.radio(
            "📌 Work Type",
            [
                "☀️ Full Day",
                "🌗 Half Day"
            ],
            horizontal=True
        )

        work_fraction = (
            1.0
            if work_type == "☀️ Full Day"
            else 0.5
        )

        st.info(
            "📅 You can select one date or multiple dates."
        )

        selected_dates = st.date_input(
            "📆 Select Work Date(s)",
            value=date.today()
        )

        if isinstance(selected_dates, tuple):

            start_date = selected_dates[0]
            end_date = selected_dates[1] if len(selected_dates) > 1 else selected_dates[0]

            date_range = pd.date_range(
                start=start_date,
                end=end_date,
                freq="D"
            )

            work_dates = [
                d.date()
                for d in date_range
            ]

        elif isinstance(selected_dates, list):

            work_dates = selected_dates

        else:

            work_dates = [selected_dates]

        ot_done = st.checkbox(
            "⏱️ Yes, worker did OT"
        )

        if ot_done:

            ot_money = st.number_input(
                "💵 OT Money for EACH Selected Work Date (NPR)",
                min_value=0.0,
                value=0.0,
                step=100.0
            )

            ot_notes = st.text_input(
                "📝 OT Details / Job"
            )

        else:

            ot_money = 0.0
            ot_notes = ""

        remarks = st.text_input(
            "📝 Work Remarks"
        )

        if st.button(
            "💾 Save Work Record(s)",
            type="primary"
        ):

            saved = 0
            skipped = 0

            for selected_date in work_dates:

                date_string = selected_date.strftime(
                    "%Y-%m-%d"
                )

                existing = run_query("""
                    SELECT log_id
                    FROM logs
                    WHERE worker_id = ?
                      AND work_date = ?
                """, (
                    worker_id,
                    date_string
                ))

                if not existing.empty:
                    skipped += 1
                    continue

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
                        work_fraction,
                        ot_done,
                        ot_money,
                        ot_notes,
                        remarks
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id,
                    worker_id,
                    date_string,
                    work_fraction,
                    1 if ot_done else 0,
                    ot_money,
                    ot_notes,
                    remarks
                ))

                saved += 1

            if saved > 0:
                st.success(
                    f"✅ Saved {saved} work record(s)."
                )

            if skipped > 0:
                st.warning(
                    f"⚠️ Skipped {skipped} duplicate date(s)."
                )

            st.rerun()

    st.markdown("---")
    st.subheader("📋 Work Records")

    st.dataframe(
        df_logs,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 🏖️ LEAVES & HOLIDAYS
# =========================================================

elif menu == "🏖️ Leaves & Holidays":

    st.subheader("🏖️ Worker Leaves & Holidays")

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### ➕ Record Leave / Holiday"
            )

            with st.form(
                "leave_form",
                clear_on_submit=True
            ):

                worker_choices = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                selected_worker = st.selectbox(
                    "👷 Select Worker",
                    worker_choices
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                leave_date = st.date_input(
                    "📅 Leave Date",
                    date.today()
                )

                leave_type = st.selectbox(
                    "🏖️ Leave Type",
                    [
                        "Casual Leave",
                        "Sick Leave",
                        "Festival / Public Holiday",
                        "Unpaid Leave",
                        "Other"
                    ]
                )

                leave_duration = st.radio(
                    "⏳ Leave Duration",
                    [
                        "🏖️ Full Day",
                        "🌗 Half Day"
                    ],
                    horizontal=True
                )

                leave_fraction = (
                    1.0
                    if leave_duration == "🏖️ Full Day"
                    else 0.5
                )

                leave_reason = st.text_input(
                    "📝 Reason / Remarks"
                )

                submit_leave = st.form_submit_button(
                    "💾 Save Leave Record"
                )

                if submit_leave:

                    existing = run_query("""
                        SELECT leave_id
                        FROM leaves
                        WHERE worker_id = ?
                          AND leave_date = ?
                    """, (
                        worker_id,
                        leave_date.strftime("%Y-%m-%d")
                    ))

                    if not existing.empty:

                        st.error(
                            "⚠️ A leave record already exists for this date."
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
                                leave_fraction,
                                reason
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            leave_id,
                            worker_id,
                            leave_date.strftime("%Y-%m-%d"),
                            leave_type,
                            leave_fraction,
                            leave_reason
                        ))

                        st.success(
                            "🏖️ Leave record saved successfully!"
                        )

                        st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Leave"
            )

            if df_leaves.empty:

                st.info("📭 No leave records.")

            else:

                leave_choices = (
                    df_leaves["Leave ID"].astype(str)
                    + " - "
                    + df_leaves["Worker Name"].astype(str)
                    + " - "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "🏖️ Select Leave",
                    leave_choices
                )

                leave_id = selected_leave.split(
                    " - "
                )[0]

                if st.button(
                    "🗑️ Delete Leave",
                    type="primary"
                ):

                    run_action("""
                        DELETE FROM leaves
                        WHERE leave_id = ?
                    """, (leave_id,))

                    st.success("🗑️ Leave deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        df_leaves,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 💸 ADVANCE MONEY
# =========================================================

elif menu == "💸 Advance Money":

    st.subheader(
        "💸 Separate Worker Advance Money"
    )

    st.info(
        "💡 Advances are recorded separately and automatically deducted from the worker's monthly salary."
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

                worker_choices = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                selected_worker = st.selectbox(
                    "👷 Select Worker",
                    worker_choices
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                advance_date = st.date_input(
                    "📅 Advance Date",
                    date.today()
                )

                advance_amount = st.number_input(
                    "💵 Advance Amount (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

                advance_reason = st.text_input(
                    "📝 Reason / Remarks"
                )

                submit_advance = st.form_submit_button(
                    "💸 Save Advance"
                )

                if submit_advance:

                    if advance_amount <= 0:

                        st.error(
                            "⚠️ Enter an amount greater than NPR 0."
                        )

                    else:

                        advance_id = get_next_id(
                            "A",
                            "advances",
                            "advance_id"
                        )

                        month_key = advance_date.strftime(
                            "%Y-%m"
                        )

                        run_action("""
                            INSERT INTO advances (
                                advance_id,
                                worker_id,
                                advance_date,
                                amount,
                                reason,
                                month_key,
                                created_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            advance_id,
                            worker_id,
                            advance_date.strftime("%Y-%m-%d"),
                            advance_amount,
                            advance_reason,
                            month_key,
                            datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        ))

                        st.success(
                            f"💸 NPR {advance_amount:,.2f} advance recorded!"
                        )

                        st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Advance"
            )

            if df_advances.empty:

                st.info("📭 No advances recorded.")

            else:

                advance_choices = (
                    df_advances["Advance ID"].astype(str)
                    + " - "
                    + df_advances["Worker Name"].astype(str)
                    + " - NPR "
                    + df_advances[
                        "Advance Amount (NPR)"
                    ].astype(str)
                )

                selected_advance = st.selectbox(
                    "💸 Select Advance",
                    advance_choices
                )

                advance_id = selected_advance.split(
                    " - "
                )[0]

                if st.button(
                    "🗑️ Delete Advance",
                    type="primary"
                ):

                    run_action("""
                        DELETE FROM advances
                        WHERE advance_id = ?
                    """, (advance_id,))

                    st.success("🗑️ Advance deleted.")
                    st.rerun()

    st.markdown("---")

    st.dataframe(
        df_advances,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 🛒 SHOP ITEMS
# =========================================================

elif menu == "🛒 Shop Items":

    st.subheader(
        "🛒 Shop Items Consumed by Workers"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add a worker first."
        )

    else:

        with st.form(
            "shop_item_form",
            clear_on_submit=True
        ):

            worker_choices = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👷 Select Worker",
                worker_choices
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            item_date = st.date_input(
                "📅 Date",
                date.today()
            )

            item_name = st.text_input(
                "🛒 Item Name"
            )

            item_cost = st.number_input(
                "💵 Cost (NPR)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            item_notes = st.text_input(
                "📝 Notes"
            )

            submit_item = st.form_submit_button(
                "💾 Save Shop Item"
            )

            if submit_item:

                if not item_name.strip():

                    st.error(
                        "⚠️ Please enter the item name."
                    )

                elif item_cost <= 0:

                    st.error(
                        "⚠️ Enter a cost greater than NPR 0."
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
                        item_date.strftime("%Y-%m-%d"),
                        item_name.strip(),
                        item_cost,
                        item_notes
                    ))

                    st.success(
                        "🛒 Shop item recorded!"
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        df_consumption,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 💰 MONTHLY FINANCIAL PAYOUT
# =========================================================

elif menu == "💰 Monthly Financial Payout":

    st.subheader(
        "💰 Monthly Worker Salary & Payout"
    )

    st.info(
        "🧮 Formula: Gross Salary = Daily Wage × Actual Worked Days + OT Money. "
        "Remaining Due = Gross Salary − Separate Advances − Shop Deductions − Salary Paid."
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "👷 Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(
            " - "
        )[0]

        available_months = set()

        if not df_logs.empty:
            available_months.update(
                df_logs["Work Date"]
                .astype(str)
                .str[:7]
                .tolist()
            )

        if not df_advances.empty:
            available_months.update(
                df_advances["Month"]
                .astype(str)
                .tolist()
            )

        if not df_financials.empty:
            available_months.update(
                df_financials["Month"]
                .astype(str)
                .tolist()
            )

        current_month = date.today().strftime(
            "%Y-%m"
        )

        available_months.add(current_month)

        month_options = sorted(
            list(available_months),
            reverse=True
        )

        month_key = st.selectbox(
            "🗓️ Select Month",
            month_options
        )

        worker_row = df_workers[
            df_workers["Worker ID"] == worker_id
        ].iloc[0]

        st.write(
            f"🚀 **Started Work:** {worker_row['Started Work']}"
        )

        work_summary = get_month_work_summary(
            worker_id,
            month_key
        )

        leave_days = get_month_leave_summary(
            worker_id,
            month_key
        )

        total_advance = get_month_advance(
            worker_id,
            month_key
        )

        shop_deduction = get_month_shop_deduction(
            worker_id,
            month_key
        )

        existing_financial = run_query("""
            SELECT *
            FROM financials
            WHERE worker_id = ?
              AND month_key = ?
        """, (
            worker_id,
            month_key
        ))

        default_wage = 1500.0
        default_received = 0.0

        if not existing_financial.empty:

            default_wage = float(
                existing_financial.iloc[0][
                    "daily_wage"
                ] or 0
            )

            default_received = float(
                existing_financial.iloc[0][
                    "received_money"
                ] or 0
            )

        col1, col2 = st.columns(2)

        with col1:

            daily_wage = st.number_input(
                "💵 Daily Wage (NPR)",
                min_value=0.0,
                value=default_wage,
                step=100.0
            )

        with col2:

            received_money = st.number_input(
                "💰 Salary Paid This Month (NPR)",
                min_value=0.0,
                value=default_received,
                step=100.0
            )

        calculation = calculate_monthly_salary(
            worker_id,
            month_key,
            daily_wage,
            received_money
        )

        st.markdown("---")
        st.subheader("🧮 Automatic Calculation")

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "📅 Actual Worked Days",
            f"{calculation['worked_days']:.1f}"
        )

        m2.metric(
            "🏖️ Leave Days",
            f"{leave_days:.1f}"
        )

        m3.metric(
            "⏱️ Total OT Money",
            f"NPR {calculation['total_ot_money']:,.2f}"
        )

        m4.metric(
            "💸 Separate Advances",
            f"NPR {calculation['total_advance']:,.2f}"
        )

        m5, m6, m7, m8 = st.columns(4)

        m5.metric(
            "💰 Gross Earned",
            f"NPR {calculation['gross_earned']:,.2f}"
        )

        m6.metric(
            "🛒 Shop Deduction",
            f"NPR {calculation['shop_deduction']:,.2f}"
        )

        m7.metric(
            "💵 Salary Paid",
            f"NPR {received_money:,.2f}"
        )

        m8.metric(
            "📌 Remaining Due",
            f"NPR {calculation['remaining_due']:,.2f}"
        )

        st.success(
            f"📋 Current Status: **{calculation['status']}**"
        )

        st.markdown("---")

        if st.button(
            "💾 Save / Update Monthly Financial Record",
            type="primary",
            use_container_width=True
        ):

            final_calculation = save_monthly_financial(
                worker_id,
                month_key,
                daily_wage,
                received_money
            )

            st.success(
                "✅ Monthly financial record saved successfully!"
            )

            st.info(
                f"📅 Worked Days: {final_calculation['worked_days']:.1f} | "
                f"⏱️ OT: NPR {final_calculation['total_ot_money']:,.2f} | "
                f"💸 Advance: NPR {final_calculation['total_advance']:,.2f} | "
                f"💰 Remaining: NPR {final_calculation['remaining_due']:,.2f}"
            )

            st.rerun()

    st.markdown("---")

    st.subheader(
        "📋 Saved Monthly Financial Records"
    )

    st.dataframe(
        df_financials,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 🔎 WORKER SEARCH
# =========================================================

elif menu == "🔎 Worker Search":

    st.subheader(
        "🔎 Search Worker & View All Records"
    )

    if df_workers.empty:

        st.info(
            "📭 No workers available."
        )

    else:

        search_text = st.text_input(
            "🔎 Search Worker Name"
        ).strip().lower()

        filtered_workers = df_workers.copy()

        if search_text:

            filtered_workers = filtered_workers[
                filtered_workers["Name"]
                .astype(str)
                .str.lower()
                .str.contains(
                    search_text,
                    na=False
                )
            ]

        if filtered_workers.empty:

            st.warning(
                "⚠️ No worker found."
            )

        else:

            choices = (
                filtered_workers["Worker ID"].astype(str)
                + " - "
                + filtered_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "👷 Select Worker",
                choices
            )

            worker_id = selected.split(
                " - "
            )[0]

            worker_data = df_workers[
                df_workers["Worker ID"] == worker_id
            ].iloc[0]

            st.markdown(
                "### 👤 Worker Information"
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "👤 Name",
                worker_data["Name"]
            )

            c2.metric(
                "📱 Phone",
                worker_data["Phone"]
                if pd.notna(worker_data["Phone"])
                else "-"
            )

            c3.metric(
                "🛠️ Skill",
                worker_data["Skill"]
            )

            c4.metric(
                "🚀 Started",
                worker_data["Started Work"]
                if pd.notna(
                    worker_data["Started Work"]
                )
                else "-"
            )

            worker_logs = df_logs[
                df_logs["Worker ID"] == worker_id
            ]

            worker_leaves = df_leaves[
                df_leaves["Worker ID"] == worker_id
            ]

            worker_advances = df_advances[
                df_advances["Worker ID"] == worker_id
            ]

            worker_financials = df_financials[
                df_financials["Worker ID"] == worker_id
            ]

            worker_shop = df_consumption[
                df_consumption["Worker ID"] == worker_id
            ]

            st.markdown("---")

            tabs = st.tabs([
                "📅 Work Days",
                "🏖️ Holidays / Leaves",
                "💸 Advances",
                "🛒 Shop Items",
                "💰 Financials"
            ])

            with tabs[0]:

                st.subheader(
                    "📅 Work Records"
                )

                if worker_logs.empty:
                    st.info("📭 No work records.")
                else:
                    st.dataframe(
                        worker_logs,
                        use_container_width=True,
                        hide_index=True
                    )

            with tabs[1]:

                st.subheader(
                    "🏖️ Leave Records"
                )

                if worker_leaves.empty:
                    st.info("📭 No leave records.")
                else:
                    st.dataframe(
                        worker_leaves,
                        use_container_width=True,
                        hide_index=True
                    )

            with tabs[2]:

                st.subheader(
                    "💸 Advance Records"
                )

                if worker_advances.empty:
                    st.info("📭 No advances.")
                else:
                    st.dataframe(
                        worker_advances,
                        use_container_width=True,
                        hide_index=True
                    )

            with tabs[3]:

                st.subheader(
                    "🛒 Shop Consumption"
                )

                if worker_shop.empty:
                    st.info("📭 No shop records.")
                else:
                    st.dataframe(
                        worker_shop,
                        use_container_width=True,
                        hide_index=True
                    )

            with tabs[4]:

                st.subheader(
                    "💰 Monthly Financial Records"
                )

                if worker_financials.empty:
                    st.info(
                        "📭 No monthly financial records."
                    )
                else:
                    st.dataframe(
                        worker_financials,
                        use_container_width=True,
                        hide_index=True
                    )


# =========================================================
# 🪚 FOOTER
# =========================================================

st.markdown("---")
st.caption(
    "🪚 Furniture Workshop Record System | 📅 Permanent Monthly Records | 💰 Automatic Salary Calculation"
)
