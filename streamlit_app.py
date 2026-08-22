import streamlit as st
import pandas as pd
from datetime import date
import sqlite3
import io
import calendar

# ============================================================
# ⚙️ PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Permanent Furniture Workshop Record System")
st.caption("👷 Attendance • 🌓 Half Days • 🌴 Leaves • ⏰ Overtime • 💰 Monthly Salary")

DB_FILE = "workshop.db"


# ============================================================
# 🗄️ DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def table_exists(cursor, table_name):
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name=?
    """, (table_name,))
    return cursor.fetchone() is not None


# ============================================================
# 🔧 DATABASE INITIALIZATION + SAFE MIGRATION
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
                start_date TEXT
            )
        """)

        worker_cols = get_columns(cursor, "workers")

        if "start_date" not in worker_cols:
            cursor.execute(
                "ALTER TABLE workers ADD COLUMN start_date TEXT"
            )

        # ----------------------------------------------------
        # 📝 LOGS
        # ----------------------------------------------------

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

        log_cols = get_columns(cursor, "logs")

        log_missing_columns = {
            "work_type": "TEXT DEFAULT 'Full Day'",
            "work_value": "REAL DEFAULT 1.0",
            "ot_hours": "REAL DEFAULT 0.0",
            "ot_money": "REAL DEFAULT 0.0",
            "ot_notes": "TEXT",
            "remarks": "TEXT"
        }

        for col_name, col_definition in log_missing_columns.items():

            if col_name not in log_cols:

                cursor.execute(
                    f"ALTER TABLE logs ADD COLUMN {col_name} {col_definition}"
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

        leave_cols = get_columns(cursor, "leaves")

        if "leave_value" not in leave_cols:
            cursor.execute(
                "ALTER TABLE leaves ADD COLUMN leave_value REAL DEFAULT 1.0"
            )

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
        # 💰 FINANCIALS
        # ----------------------------------------------------

        financial_required = {
            "payment_id",
            "worker_id",
            "month_key",
            "daily_wage",
            "total_worked_days",
            "ot_hours",
            "ot_money",
            "gross_earned",
            "taken_money",
            "advance_reason",
            "shop_deduction",
            "received_money",
            "remaining_due",
            "status",
            "updated_at"
        }

        if table_exists(cursor, "financials"):

            existing_financial_cols = set(
                get_columns(cursor, "financials")
            )

            # Old schema detected → rebuild safely
            if not financial_required.issubset(existing_financial_cols):

                backup_name = "financials_old_backup"

                if table_exists(cursor, backup_name):
                    cursor.execute(
                        f"DROP TABLE {backup_name}"
                    )

                cursor.execute("""
                    ALTER TABLE financials
                    RENAME TO financials_old_backup
                """)

                cursor.execute("""
                    CREATE TABLE financials (
                        payment_id TEXT PRIMARY KEY,
                        worker_id TEXT NOT NULL,
                        month_key TEXT NOT NULL,
                        daily_wage REAL NOT NULL DEFAULT 0,
                        total_worked_days REAL NOT NULL DEFAULT 0,
                        ot_hours REAL NOT NULL DEFAULT 0,
                        ot_money REAL NOT NULL DEFAULT 0,
                        gross_earned REAL NOT NULL DEFAULT 0,
                        taken_money REAL NOT NULL DEFAULT 0,
                        advance_reason TEXT,
                        shop_deduction REAL NOT NULL DEFAULT 0,
                        received_money REAL NOT NULL DEFAULT 0,
                        remaining_due REAL NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'Unpaid',
                        updated_at TEXT,
                        FOREIGN KEY(worker_id)
                            REFERENCES workers(worker_id)
                            ON DELETE CASCADE,
                        UNIQUE(worker_id, month_key)
                    )
                """)

        else:

            cursor.execute("""
                CREATE TABLE financials (
                    payment_id TEXT PRIMARY KEY,
                    worker_id TEXT NOT NULL,
                    month_key TEXT NOT NULL,
                    daily_wage REAL NOT NULL DEFAULT 0,
                    total_worked_days REAL NOT NULL DEFAULT 0,
                    ot_hours REAL NOT NULL DEFAULT 0,
                    ot_money REAL NOT NULL DEFAULT 0,
                    gross_earned REAL NOT NULL DEFAULT 0,
                    taken_money REAL NOT NULL DEFAULT 0,
                    advance_reason TEXT,
                    shop_deduction REAL NOT NULL DEFAULT 0,
                    received_money REAL NOT NULL DEFAULT 0,
                    remaining_due REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'Unpaid',
                    updated_at TEXT,
                    FOREIGN KEY(worker_id)
                        REFERENCES workers(worker_id)
                        ON DELETE CASCADE,
                    UNIQUE(worker_id, month_key)
                )
            """)

        # Create unique index safely
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_financial_worker_month
            ON financials(worker_id, month_key)
        """)

        # ----------------------------------------------------
        # 📅 PREVENT DUPLICATE ATTENDANCE
        # ----------------------------------------------------

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_worker_work_date
            ON logs(worker_id, work_date)
        """)

        conn.commit()


# Initialize database
init_db()


# ============================================================
# 🧰 DATABASE HELPERS
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


def get_next_id(prefix, table, id_col):

    df = run_query(
        f"SELECT {id_col} FROM {table}"
    )

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[id_col].dropna():

        digits = "".join(
            filter(str.isdigit, str(value))
        )

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


# ============================================================
# 📂 DATA LOADERS
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
            l.log_id AS 'Log ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.work_date AS 'Work Date',
            l.work_type AS 'Work Type',
            l.work_value AS 'Worked Days',
            l.ot_hours AS 'OT Hours',
            l.ot_money AS 'OT Money (NPR)',
            l.ot_notes AS 'OT Details',
            l.remarks AS 'Remarks'
        FROM logs l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.work_date DESC, w.name
    """)


def load_consumption():

    return run_query("""
        SELECT
            sc.item_id AS 'Item ID',
            sc.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            sc.entry_date AS 'Date',
            sc.item_name AS 'Item Consumed',
            sc.item_cost AS 'Cost (NPR)',
            sc.notes AS 'Notes'
        FROM shop_consumption sc
        LEFT JOIN workers w
            ON sc.worker_id = w.worker_id
        ORDER BY sc.entry_date DESC, w.name
    """)


def load_leaves():

    return run_query("""
        SELECT
            l.leave_id AS 'Leave ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.leave_date AS 'Leave Date',
            l.leave_type AS 'Leave Type',
            l.leave_value AS 'Leave Days',
            l.reason AS 'Reason / Remarks'
        FROM leaves l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.leave_date DESC, w.name
    """)


def load_financials():

    return run_query("""
        SELECT
            f.payment_id AS 'Payment ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month',
            f.daily_wage AS 'Daily Wage (NPR)',
            f.total_worked_days AS 'Total Worked Days',
            f.ot_hours AS 'Total OT Hours',
            f.ot_money AS 'Total OT Money (NPR)',
            f.gross_earned AS 'Gross Earned (NPR)',
            f.taken_money AS 'Taken Money / Advance (NPR)',
            f.advance_reason AS 'Advance Reason',
            f.shop_deduction AS 'Shop Deduction (NPR)',
            f.received_money AS 'Money Paid (NPR)',
            f.remaining_due AS 'Remaining Due (NPR)',
            f.status AS 'Status',
            f.updated_at AS 'Last Updated'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# 📊 MONTHLY SUMMARY
# ============================================================

def get_monthly_summary(worker_id, month_key):

    logs = run_query("""
        SELECT
            COALESCE(SUM(work_value), 0) AS total_worked_days,
            COALESCE(SUM(ot_hours), 0) AS total_ot_hours,
            COALESCE(SUM(ot_money), 0) AS total_ot_money
        FROM logs
        WHERE worker_id = ?
        AND substr(work_date, 1, 7) = ?
    """, (
        worker_id,
        month_key
    ))

    leaves = run_query("""
        SELECT
            COALESCE(SUM(leave_value), 0) AS total_leave_days
        FROM leaves
        WHERE worker_id = ?
        AND substr(leave_date, 1, 7) = ?
    """, (
        worker_id,
        month_key
    ))

    shop = run_query("""
        SELECT
            COALESCE(SUM(item_cost), 0) AS shop_deduction
        FROM shop_consumption
        WHERE worker_id = ?
        AND substr(entry_date, 1, 7) = ?
    """, (
        worker_id,
        month_key
    ))

    return {
        "total_worked_days": float(
            logs.iloc[0]["total_worked_days"]
        ),
        "total_ot_hours": float(
            logs.iloc[0]["total_ot_hours"]
        ),
        "total_ot_money": float(
            logs.iloc[0]["total_ot_money"]
        ),
        "total_leave_days": float(
            leaves.iloc[0]["total_leave_days"]
        ),
        "shop_deduction": float(
            shop.iloc[0]["shop_deduction"]
        )
    }


# ============================================================
# 💰 SAVE MONTHLY FINANCIAL
# ============================================================

def save_monthly_financial(
    worker_id,
    month_key,
    daily_wage,
    taken_money=0.0,
    advance_reason="",
    received_money=0.0
):

    summary = get_monthly_summary(
        worker_id,
        month_key
    )

    total_worked_days = summary["total_worked_days"]
    total_ot_hours = summary["total_ot_hours"]
    total_ot_money = summary["total_ot_money"]
    shop_deduction = summary["shop_deduction"]

    daily_wage = float(daily_wage or 0)
    taken_money = float(taken_money or 0)
    received_money = float(received_money or 0)

    # 💰 Salary calculation
    regular_salary = (
        total_worked_days * daily_wage
    )

    gross_earned = (
        regular_salary + total_ot_money
    )

    remaining_due = (
        gross_earned
        - taken_money
        - shop_deduction
        - received_money
    )

    if remaining_due <= 0:
        status = "Fully Settled"

    elif (
        taken_money > 0
        or received_money > 0
        or shop_deduction > 0
    ):
        status = "Partially Paid"

    else:
        status = "Unpaid"

    updated_at = pd.Timestamp.now().strftime(
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

    # --------------------------------------------------------
    # ➕ INSERT NEW
    # --------------------------------------------------------

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
                ot_hours,
                ot_money,
                gross_earned,
                taken_money,
                advance_reason,
                shop_deduction,
                received_money,
                remaining_due,
                status,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
        """, (
            payment_id,
            worker_id,
            month_key,
            daily_wage,
            total_worked_days,
            total_ot_hours,
            total_ot_money,
            gross_earned,
            taken_money,
            advance_reason,
            shop_deduction,
            received_money,
            remaining_due,
            status,
            updated_at
        ))

    # --------------------------------------------------------
    # 🔄 UPDATE EXISTING
    # --------------------------------------------------------

    else:

        payment_id = existing.iloc[0]["payment_id"]

        run_action("""
            UPDATE financials
            SET
                daily_wage = ?,
                total_worked_days = ?,
                ot_hours = ?,
                ot_money = ?,
                gross_earned = ?,
                taken_money = ?,
                advance_reason = ?,
                shop_deduction = ?,
                received_money = ?,
                remaining_due = ?,
                status = ?,
                updated_at = ?
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            daily_wage,
            total_worked_days,
            total_ot_hours,
            total_ot_money,
            gross_earned,
            taken_money,
            advance_reason,
            shop_deduction,
            received_money,
            remaining_due,
            status,
            updated_at,
            worker_id,
            month_key
        ))

    return payment_id


# ============================================================
# 📥 EXPORT FUNCTIONS
# ============================================================

def generate_excel():

    df_workers = load_workers()
    df_logs = load_logs()
    df_consumption = load_consumption()
    df_leaves = load_leaves()
    df_financials = load_financials()

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
            sheet_name="Attendance & OT",
            index=False
        )

        df_leaves.to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        df_consumption.to_excel(
            writer,
            sheet_name="Shop Items",
            index=False
        )

        df_financials.to_excel(
            writer,
            sheet_name="Financials",
            index=False
        )

    return output.getvalue()


def convert_df_to_csv(df):

    return df.to_csv(
        index=False
    ).encode("utf-8")


# ============================================================
# 📂 LOAD CURRENT DATA
# ============================================================

df_workers = load_workers()
df_logs = load_logs()
df_consumption = load_consumption()
df_leaves = load_leaves()
df_financials = load_financials()


# ============================================================
# 📍 SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Choose an Option:",
    [
        "📊 Dashboard & Monthly View",
        "👷 Manage Workers",
        "📝 Log Work & OT",
        "🌴 Leaves & Holidays",
        "🛒 Shop Items Consumed",
        "💰 Financial Payouts",
        "🔎 Search Worker Records"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export Reports")

excel_data = generate_excel()

st.sidebar.download_button(
    label="📊 Download Complete Excel Report",
    data=excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("📄 Download CSV Reports"):

    st.download_button(
        "👷 Workers CSV",
        convert_df_to_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )

    st.download_button(
        "📝 Attendance CSV",
        convert_df_to_csv(df_logs),
        f"attendance_{date.today()}.csv",
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
        "💰 Financial CSV",
        convert_df_to_csv(df_financials),
        f"financials_{date.today()}.csv",
        "text/csv",
        use_container_width=True
    )


# ============================================================
# 📊 DASHBOARD
# ============================================================

if menu == "📊 Dashboard & Monthly View":

    st.subheader("📊 Workshop Live Summary")

    total_workers = len(df_workers)

    total_worked_days = (
        pd.to_numeric(
            df_logs["Worked Days"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_logs.empty else 0
    )

    total_ot_money = (
        pd.to_numeric(
            df_logs["OT Money (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_logs.empty else 0
    )

    total_paid = (
        pd.to_numeric(
            df_financials["Money Paid (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_financials.empty else 0
    )

    total_due = (
        pd.to_numeric(
            df_financials["Remaining Due (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_financials.empty else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("👷 Total Workers", total_workers)
    c2.metric("📅 Total Worked Days", f"{total_worked_days:.1f}")
    c3.metric("⏰ Total OT Money", f"NPR {total_ot_money:,.2f}")
    c4.metric("💵 Total Paid", f"NPR {total_paid:,.2f}")
    c5.metric("💰 Total Remaining", f"NPR {total_due:,.2f}")

    st.markdown("---")
    st.subheader("📅 Monthly Attendance Summary")

    if df_logs.empty:

        st.info("ℹ️ No work records available yet.")

    else:

        df_logs_copy = df_logs.copy()

        df_logs_copy["Month"] = pd.to_datetime(
            df_logs_copy["Work Date"]
        ).dt.strftime("%Y-%m")

        months = sorted(
            df_logs_copy["Month"].dropna().unique(),
            reverse=True
        )

        selected_month = st.selectbox(
            "📅 Select Month:",
            months
        )

        monthly_logs = df_logs_copy[
            df_logs_copy["Month"] == selected_month
        ]

        st.dataframe(
            monthly_logs.drop(
                columns=["Month"]
            ),
            use_container_width=True
        )


# ============================================================
# 👷 MANAGE WORKERS
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

            name = st.text_input(
                "👤 Worker Full Name"
            )

            phone = st.text_input(
                "📱 Mobile Number"
            )

            skill = st.selectbox(
                "🛠️ Role / Skill",
                [
                    "Specialist Carpenter",
                    "Carver",
                    "Finisher / Polisher",
                    "Helper",
                    "Other"
                ]
            )

            start_date = st.date_input(
                "📅 Started Working From",
                value=date.today()
            )

            submit = st.form_submit_button(
                "➕ Register Worker"
            )

            if submit:

                if not name.strip():

                    st.error(
                        "⚠️ Please enter the worker's name."
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
                        f"✅ {name} added successfully!"
                    )

                    st.rerun()

    with col2:

        st.markdown("### 🗑️ Delete Worker")

        if df_workers.empty:

            st.info(
                "ℹ️ No workers available."
            )

        else:

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "👤 Select Worker",
                worker_options
            )

            delete_worker_id = selected.split(
                " - "
            )[0]

            if st.button(
                "🗑️ Delete Selected Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (delete_worker_id,)
                )

                st.success(
                    "✅ Worker deleted successfully!"
                )

                st.rerun()

    st.markdown("---")
    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# 📝 LOG WORK & OT
# ============================================================

elif menu == "📝 Log Work & OT":

    st.subheader("📝 Record Work Attendance & Overtime")

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

            worker_id = selected_worker.split(
                " - "
            )[0]

            selected_dates = st.date_input(
                "📅 Select One or Multiple Work Dates",
                value=[date.today()],
                key="work_dates"
            )

            if not isinstance(
                selected_dates,
                (list, tuple)
            ):
                selected_dates = [selected_dates]

            work_type = st.radio(
                "🕒 Work Type",
                [
                    "☀️ Full Day",
                    "🌓 Half Day"
                ],
                horizontal=True
            )

            work_value = (
                1.0
                if work_type == "☀️ Full Day"
                else 0.5
            )

            st.markdown("---")
            st.markdown("### ⏰ Overtime")

            has_ot = st.radio(
                "Did the worker work OT?",
                [
                    "❌ No OT",
                    "✅ Yes, Worked OT"
                ],
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
                    "💵 Total OT Money (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=50.0
                )

                ot_notes = st.text_input(
                    "📋 OT Work Details"
                )

            else:

                ot_hours = 0.0
                ot_money = 0.0
                ot_notes = ""

            remarks = st.text_input(
                "📝 Work Remarks"
            )

            if st.button(
                "💾 Save Work Record",
                type="primary"
            ):

                added = 0
                skipped = 0

                for work_date in selected_dates:

                    existing = run_query("""
                        SELECT log_id
                        FROM logs
                        WHERE worker_id = ?
                        AND work_date = ?
                    """, (
                        worker_id,
                        work_date.strftime("%Y-%m-%d")
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
                                work_type,
                                work_value,
                                ot_hours,
                                ot_money,
                                ot_notes,
                                remarks
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            log_id,
                            worker_id,
                            work_date.strftime("%Y-%m-%d"),
                            work_type.replace("☀️ ", "").replace("🌓 ", ""),
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
                        f"✅ {added} work date(s) saved!"
                    )

                if skipped > 0:

                    st.warning(
                        f"⚠️ {skipped} duplicate date(s) skipped."
                    )

                st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Work Record"
            )

            if df_logs.empty:

                st.info(
                    "ℹ️ No work records available."
                )

            else:

                options = (
                    df_logs["Log ID"].astype(str)
                    + " | "
                    + df_logs["Worker Name"].astype(str)
                    + " | "
                    + df_logs["Work Date"].astype(str)
                )

                selected_log = st.selectbox(
                    "📝 Select Work Record",
                    options
                )

                log_id = selected_log.split(
                    " | "
                )[0]

                if st.button(
                    "🗑️ Delete Work Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM logs WHERE log_id = ?",
                        (log_id,)
                    )

                    st.success(
                        "✅ Work record deleted!"
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
                "### ➕ Record Leave / Holiday"
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

                selected_worker = st.selectbox(
                    "👷 Select Worker",
                    worker_options
                )

                worker_id = selected_worker.split(
                    " - "
                )[0]

                # SINGLE DATE ONLY
                leave_date = st.date_input(
                    "📅 Leave / Holiday Date",
                    value=date.today()
                )

                leave_type = st.selectbox(
                    "🌴 Leave Type",
                    [
                        "🌴 Casual Leave",
                        "🤒 Sick Leave",
                        "🎉 Festival / Public Holiday",
                        "🚫 Unpaid Leave",
                        "🏖️ Other Leave"
                    ]
                )

                leave_duration = st.radio(
                    "🕒 Leave Duration",
                    [
                        "☀️ Full Day",
                        "🌓 Half Day"
                    ],
                    horizontal=True
                )

                leave_value = (
                    1.0
                    if leave_duration == "☀️ Full Day"
                    else 0.5
                )

                reason = st.text_input(
                    "📝 Reason / Remarks"
                )

                submit = st.form_submit_button(
                    "💾 Save Leave Record"
                )

                if submit:

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
                        leave_date.strftime("%Y-%m-%d"),
                        leave_type,
                        leave_value,
                        reason
                    ))

                    st.success(
                        "✅ Leave record saved!"
                    )

                    st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Leave Record"
            )

            if df_leaves.empty:

                st.info(
                    "ℹ️ No leave records available."
                )

            else:

                options = (
                    df_leaves["Leave ID"].astype(str)
                    + " | "
                    + df_leaves["Worker Name"].astype(str)
                    + " | "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "🌴 Select Leave Record",
                    options
                )

                leave_id = selected_leave.split(
                    " | "
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

elif menu == "🛒 Shop Items Consumed":

    st.subheader(
        "🛒 Shop Items Consumed by Workers"
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

                item_date = st.date_input(
                    "📅 Date"
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

                submit = st.form_submit_button(
                    "💾 Save Shop Item"
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
                            item_date.strftime("%Y-%m-%d"),
                            item_name,
                            item_cost,
                            notes
                        ))

                        st.success(
                            "✅ Shop item recorded!"
                        )

                        st.rerun()

        with col2:

            st.markdown(
                "### 🗑️ Delete Shop Item"
            )

            if df_consumption.empty:

                st.info(
                    "ℹ️ No shop records available."
                )

            else:

                options = (
                    df_consumption["Item ID"].astype(str)
                    + " | "
                    + df_consumption["Worker Name"].astype(str)
                    + " | "
                    + df_consumption["Item Consumed"].astype(str)
                )

                selected_item = st.selectbox(
                    "🛒 Select Shop Record",
                    options
                )

                item_id = selected_item.split(
                    " | "
                )[0]

                if st.button(
                    "🗑️ Delete Shop Record",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM shop_consumption WHERE item_id = ?",
                        (item_id,)
                    )

                    st.success(
                        "✅ Shop record deleted!"
                    )

                    st.rerun()

    st.markdown("---")
    st.dataframe(
        load_consumption(),
        use_container_width=True
    )


# ============================================================
# 💰 FINANCIAL PAYOUTS
# ============================================================

elif menu == "💰 Financial Payouts":

    st.subheader(
        "💰 Monthly Financial Payouts"
    )

    if df_workers.empty:

        st.warning(
            "⚠️ Please add workers first."
        )

    else:

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

        worker_id = selected_worker.split(
            " - "
        )[0]

        selected_month_date = st.date_input(
            "📅 Select Any Date From the Salary Month",
            value=date.today(),
            key="financial_month"
        )

        month_key = selected_month_date.strftime(
            "%Y-%m"
        )

        summary = get_monthly_summary(
            worker_id,
            month_key
        )

        st.markdown(
            f"### 📊 Automatic Monthly Summary — {month_key}"
        )

        a, b, c, d = st.columns(4)

        a.metric(
            "📅 Worked Days",
            f"{summary['total_worked_days']:.1f}"
        )

        b.metric(
            "🌴 Leave Days",
            f"{summary['total_leave_days']:.1f}"
        )

        c.metric(
            "⏰ OT Hours",
            f"{summary['total_ot_hours']:.1f}"
        )

        d.metric(
            "💵 OT Money",
            f"NPR {summary['total_ot_money']:,.2f}"
        )

        existing = run_query("""
            SELECT *
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            worker_id,
            month_key
        ))

        if existing.empty:

            default_wage = 1500.0
            default_taken = 0.0
            default_reason = ""
            default_received = 0.0

        else:

            row = existing.iloc[0]

            default_wage = float(
                row["daily_wage"]
            )

            default_taken = float(
                row["taken_money"]
            )

            default_reason = str(
                row["advance_reason"] or ""
            )

            default_received = float(
                row["received_money"]
            )

        st.markdown("---")
        st.markdown(
            "### 💰 Salary & Payment Details"
        )

        with st.form(
            "financial_form"
        ):

            daily_wage = st.number_input(
                "💵 Daily Wage (NPR)",
                min_value=0.0,
                value=default_wage,
                step=100.0
            )

            regular_salary_preview = (
                summary["total_worked_days"]
                * daily_wage
            )

            gross_preview = (
                regular_salary_preview
                + summary["total_ot_money"]
            )

            st.info(
                f"📅 Regular Salary: NPR {regular_salary_preview:,.2f}\n\n"
                f"⏰ OT Money: NPR {summary['total_ot_money']:,.2f}\n\n"
                f"💰 Gross Earned: NPR {gross_preview:,.2f}\n\n"
                f"🛒 Shop Deduction: NPR {summary['shop_deduction']:,.2f}"
            )

            taken_money = st.number_input(
                "💸 Taken Money / Advance (NPR)",
                min_value=0.0,
                value=default_taken,
                step=100.0
            )

            advance_reason = st.text_input(
                "📝 Advance Reason",
                value=default_reason
            )

            received_money = st.number_input(
                "💵 Money Already Paid (NPR)",
                min_value=0.0,
                value=default_received,
                step=100.0
            )

            estimated_due = (
                gross_preview
                - taken_money
                - summary["shop_deduction"]
                - received_money
            )

            st.success(
                f"💰 Estimated Remaining Due: "
                f"NPR {estimated_due:,.2f}"
            )

            submit = st.form_submit_button(
                "💾 Save / Update Monthly Financial Record"
            )

            if submit:

                payment_id = save_monthly_financial(
                    worker_id=worker_id,
                    month_key=month_key,
                    daily_wage=daily_wage,
                    taken_money=taken_money,
                    advance_reason=advance_reason,
                    received_money=received_money
                )

                st.success(
                    f"✅ Financial record {payment_id} saved successfully!"
                )

                st.rerun()

    st.markdown("---")
    st.subheader(
        "📋 All Monthly Financial Records"
    )

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

        st.warning(
            "⚠️ No workers registered."
        )

    else:

        search_name = st.text_input(
            "🔍 Search Worker Name"
        )

        search_df = df_workers.copy()

        if search_name:

            search_df = search_df[
                search_df["Name"]
                .astype(str)
                .str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if search_df.empty:

            st.warning(
                "❌ No worker found."
            )

        else:

            options = (
                search_df["Worker ID"].astype(str)
                + " - "
                + search_df["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "👤 Select Worker",
                options
            )

            worker_id = selected_worker.split(
                " - "
            )[0]

            worker_info = search_df[
                search_df["Worker ID"] == worker_id
            ].iloc[0]

            st.markdown(
                f"### 👤 {worker_info['Name']}"
            )

            c1, c2, c3 = st.columns(3)

            c1.write(
                f"🛠️ **Skill:** {worker_info['Skill']}"
            )

            c2.write(
                f"📱 **Phone:** {worker_info['Phone']}"
            )

            c3.write(
                f"📅 **Started:** {worker_info['Start Date']}"
            )

            worker_logs = run_query("""
                SELECT
                    log_id AS 'Log ID',
                    work_date AS 'Work Date',
                    work_type AS 'Work Type',
                    work_value AS 'Worked Days',
                    ot_hours AS 'OT Hours',
                    ot_money AS 'OT Money (NPR)',
                    ot_notes AS 'OT Details',
                    remarks AS 'Remarks'
                FROM logs
                WHERE worker_id = ?
                ORDER BY work_date DESC
            """, (
                worker_id,
            ))

            worker_leaves = run_query("""
                SELECT
                    leave_date AS 'Leave Date',
                    leave_type AS 'Leave Type',
                    leave_value AS 'Leave Days',
                    reason AS 'Reason'
                FROM leaves
                WHERE worker_id = ?
                ORDER BY leave_date DESC
            """, (
                worker_id,
            ))

            worker_shop = run_query("""
                SELECT
                    entry_date AS 'Date',
                    item_name AS 'Item',
                    item_cost AS 'Cost (NPR)',
                    notes AS 'Notes'
                FROM shop_consumption
                WHERE worker_id = ?
                ORDER BY entry_date DESC
            """, (
                worker_id,
            ))

            worker_financials = run_query("""
                SELECT
                    month_key AS 'Month',
                    daily_wage AS 'Daily Wage',
                    total_worked_days AS 'Worked Days',
                    ot_hours AS 'OT Hours',
                    ot_money AS 'OT Money',
                    gross_earned AS 'Gross Earned',
                    taken_money AS 'Advance',
                    shop_deduction AS 'Shop Deduction',
                    received_money AS 'Paid',
                    remaining_due AS 'Remaining Due',
                    status AS 'Status'
                FROM financials
                WHERE worker_id = ?
                ORDER BY month_key DESC
            """, (
                worker_id,
            ))

            tab1, tab2, tab3, tab4 = st.tabs([
                "📝 Work Days",
                "🌴 Leaves",
                "🛒 Shop Items",
                "💰 Monthly Money"
            ])

            with tab1:

                st.dataframe(
                    worker_logs,
                    use_container_width=True
                )

            with tab2:

                st.dataframe(
                    worker_leaves,
                    use_container_width=True
                )

            with tab3:

                st.dataframe(
                    worker_shop,
                    use_container_width=True
                )

            with tab4:

                st.dataframe(
                    worker_financials,
                    use_container_width=True
                )
