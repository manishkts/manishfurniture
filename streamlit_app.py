import streamlit as st
import pandas as pd
from datetime import date, datetime
import sqlite3
import io
import calendar

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Record & Salary System")
st.caption(
    "Monthly attendance, half days, holidays, overtime, advances, "
    "shop deductions and automatic salary calculation."
)

DB_FILE = "workshop.db"


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Important for foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def add_column_if_missing(conn, table_name, column_name, definition):
    columns = table_columns(conn, table_name)

    if column_name not in columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def init_db():
    """
    Creates tables and safely adds new columns to older databases.
    """

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

        add_column_if_missing(
            conn,
            "workers",
            "start_date",
            "TEXT"
        )

        # ----------------------------------------------------
        # ATTENDANCE / DAILY WORK LOG
        # work_status:
        # Full Day = 1.0
        # Half Day = 0.5
        # Absent = 0.0
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_status TEXT DEFAULT 'Full Day',
                worked_days REAL DEFAULT 1.0,
                ot_done INTEGER DEFAULT 0,
                ot_money REAL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # Migration for old logs table
        add_column_if_missing(
            conn,
            "logs",
            "work_status",
            "TEXT DEFAULT 'Full Day'"
        )

        add_column_if_missing(
            conn,
            "logs",
            "worked_days",
            "REAL DEFAULT 1.0"
        )

        add_column_if_missing(
            conn,
            "logs",
            "ot_done",
            "INTEGER DEFAULT 0"
        )

        add_column_if_missing(
            conn,
            "logs",
            "ot_money",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "logs",
            "ot_notes",
            "TEXT"
        )

        add_column_if_missing(
            conn,
            "logs",
            "remarks",
            "TEXT"
        )

        # Old database compatibility:
        # If old OT Hours exists, keep it. New app uses OT Money.
        add_column_if_missing(
            conn,
            "logs",
            "ot_hours",
            "REAL DEFAULT 0.0"
        )

        # ----------------------------------------------------
        # LEAVES / HOLIDAYS
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # SHOP CONSUMPTION / DEDUCTIONS
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_consumption (
                item_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_cost REAL NOT NULL DEFAULT 0.0,
                notes TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # ADVANCES
        # Separate table allows multiple advances in one month
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                advance_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                advance_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                reason TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # PAYMENTS
        # Separate table allows multiple payments
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0.0,
                notes TEXT,
                FOREIGN KEY(worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # FINANCIALS
        # Monthly salary records
        # ----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT,
                month_key TEXT,
                daily_wage REAL DEFAULT 0.0,
                days_worked REAL DEFAULT 0.0,
                ot_money REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0,
                taken_money REAL DEFAULT 0.0,
                advance_reason TEXT,
                received_money REAL DEFAULT 0.0,
                status TEXT DEFAULT 'Unpaid'
            )
        """)

        # Migration-safe additions for old financials table
        add_column_if_missing(
            conn,
            "financials",
            "worker_id",
            "TEXT"
        )

        add_column_if_missing(
            conn,
            "financials",
            "month_key",
            "TEXT"
        )

        add_column_if_missing(
            conn,
            "financials",
            "daily_wage",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "financials",
            "days_worked",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "financials",
            "ot_money",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "financials",
            "total_earned",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "financials",
            "taken_money",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "financials",
            "advance_reason",
            "TEXT"
        )

        add_column_if_missing(
            conn,
            "financials",
            "received_money",
            "REAL DEFAULT 0.0"
        )

        add_column_if_missing(
            conn,
            "financials",
            "status",
            "TEXT DEFAULT 'Unpaid'"
        )

        # Old database compatibility
        add_column_if_missing(
            conn,
            "financials",
            "log_id",
            "TEXT"
        )

        add_column_if_missing(
            conn,
            "financials",
            "ot_rate_per_hour",
            "REAL DEFAULT 0.0"
        )

        conn.commit()


# Run database setup before any query
init_db()


def run_query(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def run_action(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()


def get_next_id(prefix, table, id_col):
    df = run_query(f"SELECT {id_col} FROM {table}")

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[id_col].dropna():
        digits = "".join(filter(str.isdigit, str(value)))
        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


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
            l.work_date AS 'Date',
            COALESCE(l.work_status, 'Full Day') AS 'Work Status',
            COALESCE(l.worked_days, 1.0) AS 'Worked Days',
            COALESCE(l.ot_done, 0) AS 'OT Done',
            COALESCE(l.ot_money, 0.0) AS 'OT Money (NPR)',
            COALESCE(l.ot_notes, '') AS 'OT Details',
            COALESCE(l.remarks, '') AS 'Remarks'
        FROM logs l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.work_date DESC
    """)


def load_leaves():
    return run_query("""
        SELECT
            lv.leave_id AS 'Leave ID',
            lv.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            lv.leave_date AS 'Leave Date',
            lv.leave_type AS 'Leave Type',
            lv.reason AS 'Reason'
        FROM leaves lv
        LEFT JOIN workers w
            ON lv.worker_id = w.worker_id
        ORDER BY lv.leave_date DESC
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
        ORDER BY sc.entry_date DESC
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
        ORDER BY a.advance_date DESC
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
        ORDER BY p.payment_date DESC
    """)


def load_financials():
    """
    IMPORTANT:
    This query does not assume every old database column is perfect.
    It uses only migration-supported columns.
    """

    return run_query("""
        SELECT
            f.payment_id AS 'Record ID',
            f.worker_id AS 'Worker ID',
            COALESCE(w.name, 'Unknown / Old Record') AS 'Worker Name',
            f.month_key AS 'Month',
            COALESCE(f.daily_wage, 0) AS 'Daily Wage (NPR)',
            COALESCE(f.days_worked, 0) AS 'Worked Days',
            COALESCE(f.ot_money, 0) AS 'OT Money (NPR)',
            COALESCE(f.total_earned, 0) AS 'Total Earned (NPR)',
            COALESCE(f.taken_money, 0) AS 'Advance Stored (NPR)',
            COALESCE(f.received_money, 0) AS 'Paid Stored (NPR)',
            COALESCE(f.status, 'Unpaid') AS 'Status'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY
            COALESCE(f.month_key, '') DESC,
            COALESCE(w.name, '')
    """)


# ============================================================
# MONTH / DATE FUNCTIONS
# ============================================================

def month_key_from_date(value):
    return pd.to_datetime(value).strftime("%Y-%m")


def month_name(month_key):
    try:
        dt = datetime.strptime(month_key, "%Y-%m")
        return dt.strftime("%B %Y")
    except Exception:
        return month_key


def get_month_options():
    months = set()

    dataframes = [
        load_logs(),
        load_leaves(),
        load_consumption(),
        load_advances(),
        load_payments(),
        load_financials()
    ]

    date_columns = [
        "Date",
        "Leave Date",
        "Date",
        "Date",
        "Date",
        "Month"
    ]

    for df, col in zip(dataframes, date_columns):
        if not df.empty and col in df.columns:

            for value in df[col].dropna():

                try:
                    if col == "Month":
                        if len(str(value)) >= 7:
                            months.add(str(value)[:7])
                    else:
                        months.add(
                            pd.to_datetime(value).strftime("%Y-%m")
                        )
                except Exception:
                    pass

    # Always include current month
    months.add(date.today().strftime("%Y-%m"))

    return sorted(months, reverse=True)


# ============================================================
# MONTHLY WORKER CALCULATION
# ============================================================

def calculate_worker_month(worker_id, selected_month, daily_wage):

    # Get attendance
    attendance = run_query("""
        SELECT
            work_date,
            COALESCE(worked_days, 1.0) AS worked_days,
            COALESCE(ot_money, 0.0) AS ot_money
        FROM logs
        WHERE worker_id = ?
    """, (worker_id,))

    if not attendance.empty:
        attendance["month_key"] = pd.to_datetime(
            attendance["work_date"]
        ).dt.strftime("%Y-%m")

        attendance = attendance[
            attendance["month_key"] == selected_month
        ]
    else:
        attendance = pd.DataFrame()

    # Actual attendance
    if not attendance.empty:
        worked_days = float(attendance["worked_days"].sum())
        total_ot = float(attendance["ot_money"].sum())
    else:
        worked_days = 0.0
        total_ot = 0.0

    # Leaves
    leaves = run_query("""
        SELECT leave_date, leave_type
        FROM leaves
        WHERE worker_id = ?
    """, (worker_id,))

    leave_count = 0

    if not leaves.empty:
        leaves["month_key"] = pd.to_datetime(
            leaves["leave_date"]
        ).dt.strftime("%Y-%m")

        leaves = leaves[leaves["month_key"] == selected_month]

        leave_count = len(leaves)

    # Shop deductions
    consumption = run_query("""
        SELECT
            entry_date,
            COALESCE(item_cost, 0) AS item_cost
        FROM shop_consumption
        WHERE worker_id = ?
    """, (worker_id,))

    shop_deduction = 0.0

    if not consumption.empty:
        consumption["month_key"] = pd.to_datetime(
            consumption["entry_date"]
        ).dt.strftime("%Y-%m")

        consumption = consumption[
            consumption["month_key"] == selected_month
        ]

        shop_deduction = float(
            consumption["item_cost"].sum()
        )

    # Advances
    advances = run_query("""
        SELECT
            advance_date,
            COALESCE(amount, 0) AS amount
        FROM advances
        WHERE worker_id = ?
    """, (worker_id,))

    advance_amount = 0.0

    if not advances.empty:
        advances["month_key"] = pd.to_datetime(
            advances["advance_date"]
        ).dt.strftime("%Y-%m")

        advances = advances[
            advances["month_key"] == selected_month
        ]

        advance_amount = float(
            advances["amount"].sum()
        )

    # Payments already given
    payments = run_query("""
        SELECT
            payment_date,
            COALESCE(amount, 0) AS amount
        FROM payments
        WHERE worker_id = ?
    """, (worker_id,))

    paid_amount = 0.0

    if not payments.empty:
        payments["month_key"] = pd.to_datetime(
            payments["payment_date"]
        ).dt.strftime("%Y-%m")

        payments = payments[
            payments["month_key"] == selected_month
        ]

        paid_amount = float(
            payments["amount"].sum()
        )

    # Salary calculation
    regular_wage = daily_wage * worked_days

    total_earned = regular_wage + total_ot

    total_deductions = (
        advance_amount
        + shop_deduction
        + paid_amount
    )

    remaining_due = total_earned - total_deductions

    if total_earned <= 0:
        status = "No Attendance"
    elif remaining_due <= 0:
        status = "Fully Settled"
    elif total_deductions > 0:
        status = "Partially Paid"
    else:
        status = "Unpaid"

    return {
        "worked_days": worked_days,
        "leave_count": leave_count,
        "total_ot": total_ot,
        "shop_deduction": shop_deduction,
        "advance_amount": advance_amount,
        "paid_amount": paid_amount,
        "regular_wage": regular_wage,
        "total_earned": total_earned,
        "total_deductions": total_deductions,
        "remaining_due": remaining_due,
        "status": status
    }


# ============================================================
# EXPORT
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
            sheet_name="Monthly Financials",
            index=False
        )

    return output.getvalue()


def convert_df_to_csv(df):
    return df.to_csv(index=False).encode("utf-8")


# ============================================================
# LOAD DATA
# ============================================================

df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_advances = load_advances()
df_payments = load_payments()
df_financials = load_financials()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Go to:",
    [
        "Dashboard",
        "Manage Workers",
        "Daily Attendance & OT",
        "Leaves & Holidays",
        "Shop Items",
        "Advances",
        "Payments",
        "Monthly Financial Payout",
        "Worker Search"
    ]
)

st.sidebar.markdown("---")
st.sidebar.header("📥 Export")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Download Complete Excel Report",
    data=excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    use_container_width=True
)


# ============================================================
# DASHBOARD
# ============================================================

if menu == "Dashboard":

    st.subheader("📊 Workshop Dashboard")

    total_workers = len(df_workers)

    total_worked_days = (
        float(df_logs["Worked Days"].sum())
        if not df_logs.empty
        else 0.0
    )

    total_ot = (
        float(df_logs["OT Money (NPR)"].sum())
        if not df_logs.empty
        else 0.0
    )

    total_advances = (
        float(df_advances["Amount (NPR)"].sum())
        if not df_advances.empty
        else 0.0
    )

    total_paid = (
        float(df_payments["Amount Paid (NPR)"].sum())
        if not df_payments.empty
        else 0.0
    )

    total_shop = (
        float(df_consumption["Cost (NPR)"].sum())
        if not df_consumption.empty
        else 0.0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Workers", total_workers)
    c2.metric("Total Worked Days", f"{total_worked_days:.1f}")
    c3.metric("Total OT Money", f"NPR {total_ot:,.2f}")
    c4.metric("Advances", f"NPR {total_advances:,.2f}")
    c5.metric("Shop Deductions", f"NPR {total_shop:,.2f}")
    c6.metric("Money Paid", f"NPR {total_paid:,.2f}")

    st.markdown("---")

    st.subheader("🗓️ Monthly Attendance View")

    months = get_month_options()

    selected_month = st.selectbox(
        "Select Month",
        months,
        format_func=month_name
    )

    if not df_logs.empty:

        temp = df_logs.copy()
        temp["Month"] = pd.to_datetime(
            temp["Date"]
        ).dt.strftime("%Y-%m")

        monthly_logs = temp[
            temp["Month"] == selected_month
        ]

        if monthly_logs.empty:
            st.info("No attendance records for this month.")
        else:

            st.dataframe(
                monthly_logs.drop(columns=["Month"]),
                use_container_width=True
            )

            summary = (
                monthly_logs
                .groupby("Worker Name")
                .agg(
                    Worked_Days=("Worked Days", "sum"),
                    OT_Money=("OT Money (NPR)", "sum")
                )
                .reset_index()
            )

            summary.columns = [
                "Worker Name",
                "Total Worked Days",
                "Total OT Money (NPR)"
            ]

            st.markdown("### Monthly Worker Summary")
            st.dataframe(
                summary,
                use_container_width=True
            )


# ============================================================
# MANAGE WORKERS
# ============================================================

elif menu == "Manage Workers":

    st.subheader("👥 Manage Workers")

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("### Add Worker")

        with st.form(
            "add_worker_form",
            clear_on_submit=True
        ):

            worker_id = get_next_id(
                "W",
                "workers",
                "worker_id"
            )

            name = st.text_input("Worker Full Name")
            phone = st.text_input("Phone Number")

            skill = st.selectbox(
                "Role / Skill",
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
                "Date Started Working",
                value=date.today()
            )

            submit = st.form_submit_button(
                "➕ Add Worker"
            )

            if submit:

                if not name.strip():
                    st.error("Please enter worker name.")

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
                        name.strip(),
                        phone.strip(),
                        skill,
                        start_date.strftime("%Y-%m-%d")
                    ))

                    st.success(
                        f"{name} added successfully."
                    )

                    st.rerun()

    with col2:

        st.markdown("### Delete Worker")

        if df_workers.empty:

            st.info("No workers available.")

        else:

            options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "Select Worker",
                options
            )

            worker_id = selected.split(" - ")[0]

            if st.button(
                "❌ Delete Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (worker_id,)
                )

                st.success("Worker deleted.")
                st.rerun()

    st.markdown("---")
    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# DAILY ATTENDANCE AND OT
# ============================================================

elif menu == "Daily Attendance & OT":

    st.subheader("📝 Daily Attendance & Overtime")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### Add Attendance"
            )

            with st.form(
                "attendance_form",
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

                worker_choice = st.selectbox(
                    "Select Worker",
                    worker_options
                )

                worker_id = worker_choice.split(
                    " - "
                )[0]

                work_date = st.date_input(
                    "Work Date",
                    date.today()
                )

                work_status = st.selectbox(
                    "Attendance Status",
                    [
                        "Full Day",
                        "Half Day",
                        "Absent"
                    ]
                )

                # Automatic worked day value
                if work_status == "Full Day":
                    worked_days = 1.0
                elif work_status == "Half Day":
                    worked_days = 0.5
                else:
                    worked_days = 0.0

                st.info(
                    f"Worked day value: {worked_days}"
                )

                st.markdown("---")
                st.markdown("### ⏰ Overtime")

                ot_done = st.checkbox(
                    "Did the worker do OT?"
                )

                if ot_done:

                    ot_money = st.number_input(
                        "Total OT Money Earned (NPR)",
                        min_value=0.0,
                        value=0.0,
                        step=100.0
                    )

                    ot_notes = st.text_input(
                        "OT Work Details"
                    )

                else:

                    ot_money = 0.0
                    ot_notes = ""

                remarks = st.text_input(
                    "Remarks"
                )

                submit = st.form_submit_button(
                    "💾 Save Attendance"
                )

                if submit:

                    formatted_date = work_date.strftime(
                        "%Y-%m-%d"
                    )

                    # Prevent duplicate worker/date
                    duplicate = run_query("""
                        SELECT log_id
                        FROM logs
                        WHERE worker_id = ?
                        AND work_date = ?
                    """, (
                        worker_id,
                        formatted_date
                    ))

                    if not duplicate.empty:

                        st.error(
                            "Attendance already exists "
                            "for this worker on this date."
                        )

                    else:

                        run_action("""
                            INSERT INTO logs
                            (
                                log_id,
                                worker_id,
                                work_date,
                                work_status,
                                worked_days,
                                ot_done,
                                ot_money,
                                ot_notes,
                                remarks
                            )
                            VALUES
                            (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            log_id,
                            worker_id,
                            formatted_date,
                            work_status,
                            worked_days,
                            1 if ot_done else 0,
                            ot_money,
                            ot_notes,
                            remarks
                        ))

                        st.success(
                            "Attendance saved successfully."
                        )

                        st.rerun()

        with col2:

            st.markdown(
                "### Delete Attendance"
            )

            if df_logs.empty:

                st.info(
                    "No attendance records."
                )

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
                    log_options
                )

                log_id = selected_log.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Attendance",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM logs WHERE log_id = ?",
                        (log_id,)
                    )

                    st.success(
                        "Attendance deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_logs(),
        use_container_width=True
    )


# ============================================================
# LEAVES
# ============================================================

elif menu == "Leaves & Holidays":

    st.subheader("🌴 Leaves & Holidays")

    if df_workers.empty:

        st.warning(
            "Please add workers first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

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

                choice = st.selectbox(
                    "Worker",
                    worker_options
                )

                worker_id = choice.split(
                    " - "
                )[0]

                leave_date = st.date_input(
                    "Leave Date",
                    date.today()
                )

                leave_type = st.selectbox(
                    "Leave Type",
                    [
                        "Holiday",
                        "Casual Leave",
                        "Sick Leave",
                        "Unpaid Leave"
                    ]
                )

                reason = st.text_input(
                    "Reason / Notes"
                )

                submit = st.form_submit_button(
                    "Record Leave"
                )

                if submit:

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
                        leave_date.strftime(
                            "%Y-%m-%d"
                        ),
                        leave_type,
                        reason
                    ))

                    st.success(
                        "Leave recorded."
                    )

                    st.rerun()

        with col2:

            if df_leaves.empty:

                st.info(
                    "No leave records."
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
                    "Delete Leave",
                    options
                )

                leave_id = selected.split(
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
                        "Leave deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_leaves(),
        use_container_width=True
    )


# ============================================================
# SHOP ITEMS
# ============================================================

elif menu == "Shop Items":

    st.subheader("🛒 Shop Items / Worker Deductions")

    if df_workers.empty:

        st.warning(
            "Please add workers first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            with st.form(
                "shop_form",
                clear_on_submit=True
            ):

                item_id = get_next_id(
                    "C",
                    "shop_consumption",
                    "item_id"
                )

                options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                choice = st.selectbox(
                    "Worker",
                    options
                )

                worker_id = choice.split(
                    " - "
                )[0]

                entry_date = st.date_input(
                    "Date",
                    date.today()
                )

                item_name = st.text_input(
                    "Item Taken"
                )

                item_cost = st.number_input(
                    "Cost (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=10.0
                )

                notes = st.text_input(
                    "Notes"
                )

                submit = st.form_submit_button(
                    "Record Item"
                )

                if submit:

                    if not item_name.strip():

                        st.error(
                            "Enter item name."
                        )

                    else:

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
                            entry_date.strftime(
                                "%Y-%m-%d"
                            ),
                            item_name,
                            item_cost,
                            notes
                        ))

                        st.success(
                            "Shop item recorded."
                        )

                        st.rerun()

        with col2:

            if not df_consumption.empty:

                options = (
                    df_consumption["Item ID"].astype(str)
                    + " - "
                    + df_consumption["Worker Name"].astype(str)
                    + " - "
                    + df_consumption["Item"].astype(str)
                )

                selected = st.selectbox(
                    "Delete Item Record",
                    options
                )

                item_id = selected.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Item",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM shop_consumption WHERE item_id = ?",
                        (item_id,)
                    )

                    st.success(
                        "Item deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_consumption(),
        use_container_width=True
    )


# ============================================================
# ADVANCES
# ============================================================

elif menu == "Advances":

    st.subheader("💵 Money Taken / Advances")

    if df_workers.empty:

        st.warning(
            "Please add workers first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            with st.form(
                "advance_form",
                clear_on_submit=True
            ):

                advance_id = get_next_id(
                    "A",
                    "advances",
                    "advance_id"
                )

                options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                choice = st.selectbox(
                    "Worker",
                    options
                )

                worker_id = choice.split(
                    " - "
                )[0]

                advance_date = st.date_input(
                    "Date Taken",
                    date.today()
                )

                amount = st.number_input(
                    "Money Taken (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

                reason = st.text_input(
                    "Reason"
                )

                submit = st.form_submit_button(
                    "Record Advance"
                )

                if submit and amount > 0:

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
                        advance_date.strftime(
                            "%Y-%m-%d"
                        ),
                        amount,
                        reason
                    ))

                    st.success(
                        "Advance recorded."
                    )

                    st.rerun()

        with col2:

            if not df_advances.empty:

                options = (
                    df_advances["Advance ID"].astype(str)
                    + " - "
                    + df_advances["Worker Name"].astype(str)
                    + " - NPR "
                    + df_advances["Amount (NPR)"].astype(str)
                )

                selected = st.selectbox(
                    "Delete Advance",
                    options
                )

                advance_id = selected.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Advance",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM advances WHERE advance_id = ?",
                        (advance_id,)
                    )

                    st.success(
                        "Advance deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_advances(),
        use_container_width=True
    )


# ============================================================
# PAYMENTS
# ============================================================

elif menu == "Payments":

    st.subheader("💰 Salary Payments Given")

    if df_workers.empty:

        st.warning(
            "Please add workers first."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            with st.form(
                "payment_form",
                clear_on_submit=True
            ):

                payment_id = get_next_id(
                    "PAY",
                    "payments",
                    "payment_id"
                )

                options = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                choice = st.selectbox(
                    "Worker",
                    options
                )

                worker_id = choice.split(
                    " - "
                )[0]

                payment_date = st.date_input(
                    "Payment Date",
                    date.today()
                )

                amount = st.number_input(
                    "Amount Paid (NPR)",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

                notes = st.text_input(
                    "Payment Notes"
                )

                submit = st.form_submit_button(
                    "Record Payment"
                )

                if submit and amount > 0:

                    run_action("""
                        INSERT INTO payments
                        (
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
                        "Payment recorded."
                    )

                    st.rerun()

        with col2:

            if not df_payments.empty:

                options = (
                    df_payments["Payment ID"].astype(str)
                    + " - "
                    + df_payments["Worker Name"].astype(str)
                    + " - NPR "
                    + df_payments[
                        "Amount Paid (NPR)"
                    ].astype(str)
                )

                selected = st.selectbox(
                    "Delete Payment",
                    options
                )

                payment_id = selected.split(
                    " - "
                )[0]

                if st.button(
                    "❌ Delete Payment",
                    type="primary"
                ):

                    run_action(
                        "DELETE FROM payments WHERE payment_id = ?",
                        (payment_id,)
                    )

                    st.success(
                        "Payment deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_payments(),
        use_container_width=True
    )


# ============================================================
# MONTHLY FINANCIAL PAYOUT
# ============================================================

elif menu == "Monthly Financial Payout":

    st.subheader(
        "📅 Monthly Salary Calculation"
    )

    if df_workers.empty:

        st.warning(
            "Please add workers first."
        )

    else:

        months = get_month_options()

        col1, col2 = st.columns(2)

        with col1:

            selected_month = st.selectbox(
                "Select Salary Month",
                months,
                format_func=month_name
            )

        with col2:

            worker_options = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            worker_choice = st.selectbox(
                "Select Worker",
                worker_options
            )

        worker_id = worker_choice.split(
            " - "
        )[0]

        worker_name = worker_choice.split(
            " - ",
            1
        )[1]

        st.markdown("---")

        st.markdown(
            f"### Salary Calculation: "
            f"{worker_name} — "
            f"{month_name(selected_month)}"
        )

        daily_wage = st.number_input(
            "Daily Wage (NPR)",
            min_value=0.0,
            value=1500.0,
            step=100.0
        )

        result = calculate_worker_month(
            worker_id,
            selected_month,
            daily_wage
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Total Worked Days",
            f"{result['worked_days']:.1f}"
        )

        c2.metric(
            "Leave Records",
            result["leave_count"]
        )

        c3.metric(
            "Total OT Money",
            f"NPR {result['total_ot']:,.2f}"
        )

        c4.metric(
            "Regular Wage",
            f"NPR {result['regular_wage']:,.2f}"
        )

        c5, c6, c7, c8 = st.columns(4)

        c5.metric(
            "Advances",
            f"NPR {result['advance_amount']:,.2f}"
        )

        c6.metric(
            "Shop Deductions",
            f"NPR {result['shop_deduction']:,.2f}"
        )

        c7.metric(
            "Money Paid",
            f"NPR {result['paid_amount']:,.2f}"
        )

        c8.metric(
            "Remaining Due",
            f"NPR {result['remaining_due']:,.2f}"
        )

        st.markdown("---")

        st.write(
            "### 🧮 Automatic Calculation"
        )

        st.info(
            f"""
**Worked Days:** {result['worked_days']:.1f}

**Regular Wage:** NPR {daily_wage:,.2f} × {result['worked_days']:.1f}
= **NPR {result['regular_wage']:,.2f}**

**OT Money:** NPR {result['total_ot']:,.2f}

**Total Earned:** Regular Wage + OT
= **NPR {result['total_earned']:,.2f}**

**Total Deductions:** Advance + Shop Items + Payments
= **NPR {result['total_deductions']:,.2f}**

### Final Remaining Due:
**NPR {result['remaining_due']:,.2f}**

**Status: {result['status']}**
"""
        )

        st.markdown("---")

        if st.button(
            "💾 Save Monthly Financial Record",
            type="primary"
        ):

            existing = run_query("""
                SELECT payment_id
                FROM financials
                WHERE worker_id = ?
                AND month_key = ?
            """, (
                worker_id,
                selected_month
            ))

            if existing.empty:

                record_id = get_next_id(
                    "MF",
                    "financials",
                    "payment_id"
                )

                run_action("""
                    INSERT INTO financials
                    (
                        payment_id,
                        worker_id,
                        month_key,
                        daily_wage,
                        days_worked,
                        ot_money,
                        total_earned,
                        taken_money,
                        received_money,
                        status
                    )
                    VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record_id,
                    worker_id,
                    selected_month,
                    daily_wage,
                    result["worked_days"],
                    result["total_ot"],
                    result["total_earned"],
                    result["advance_amount"],
                    result["paid_amount"],
                    result["status"]
                ))

            else:

                record_id = existing.iloc[0][
                    "payment_id"
                ]

                run_action("""
                    UPDATE financials
                    SET
                        daily_wage = ?,
                        days_worked = ?,
                        ot_money = ?,
                        total_earned = ?,
                        taken_money = ?,
                        received_money = ?,
                        status = ?
                    WHERE payment_id = ?
                """, (
                    daily_wage,
                    result["worked_days"],
                    result["total_ot"],
                    result["total_earned"],
                    result["advance_amount"],
                    result["paid_amount"],
                    result["status"],
                    record_id
                ))

            st.success(
                "Monthly financial record saved successfully."
            )

            st.rerun()

        st.markdown("---")

        st.subheader(
            "Saved Monthly Financial Records"
        )

        st.dataframe(
            load_financials(),
            use_container_width=True
        )


# ============================================================
# WORKER SEARCH
# ============================================================

elif menu == "Worker Search":

    st.subheader(
        "🔎 Search Complete Worker Record"
    )

    if df_workers.empty:

        st.warning(
            "No workers registered."
        )

    else:

        search_name = st.text_input(
            "Search Worker Name"
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
                "No worker found."
            )

        else:

            options = (
                filtered_workers["Worker ID"].astype(str)
                + " - "
                + filtered_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "Select Worker",
                options
            )

            worker_id = selected.split(
                " - "
            )[0]

            worker_info = filtered_workers[
                filtered_workers["Worker ID"] == worker_id
            ].iloc[0]

            st.markdown("### 👤 Worker Information")

            a, b, c, d = st.columns(4)

            a.metric(
                "Name",
                worker_info["Name"]
            )

            b.metric(
                "Role",
                worker_info["Skill"]
            )

            c.metric(
                "Phone",
                worker_info["Phone"]
            )

            d.metric(
                "Started Work",
                worker_info["Started Work"]
            )

            st.markdown("---")

            months = get_month_options()

            selected_month = st.selectbox(
                "Select Month for Complete Record",
                months,
                format_func=month_name,
                key="search_month"
            )

            st.markdown(
                f"## 📅 {month_name(selected_month)}"
            )

            # ATTENDANCE
            attendance = df_logs[
                df_logs["Worker ID"] == worker_id
            ].copy()

            if not attendance.empty:

                attendance["Month"] = pd.to_datetime(
                    attendance["Date"]
                ).dt.strftime("%Y-%m")

                attendance = attendance[
                    attendance["Month"] == selected_month
                ]

            # LEAVES
            leaves = df_leaves[
                df_leaves["Worker ID"] == worker_id
            ].copy()

            if not leaves.empty:

                leaves["Month"] = pd.to_datetime(
                    leaves["Leave Date"]
                ).dt.strftime("%Y-%m")

                leaves = leaves[
                    leaves["Month"] == selected_month
                ]

            # SHOP
            shop = df_consumption[
                df_consumption["Worker ID"] == worker_id
            ].copy()

            if not shop.empty:

                shop["Month"] = pd.to_datetime(
                    shop["Date"]
                ).dt.strftime("%Y-%m")

                shop = shop[
                    shop["Month"] == selected_month
                ]

            # ADVANCES
            advances = df_advances[
                df_advances["Worker ID"] == worker_id
            ].copy()

            if not advances.empty:

                advances["Month"] = pd.to_datetime(
                    advances["Date"]
                ).dt.strftime("%Y-%m")

                advances = advances[
                    advances["Month"] == selected_month
                ]

            # PAYMENTS
            payments = df_payments[
                df_payments["Worker ID"] == worker_id
            ].copy()

            if not payments.empty:

                payments["Month"] = pd.to_datetime(
                    payments["Date"]
                ).dt.strftime("%Y-%m")

                payments = payments[
                    payments["Month"] == selected_month
                ]

            total_days = (
                float(attendance["Worked Days"].sum())
                if not attendance.empty
                else 0.0
            )

            total_ot = (
                float(
                    attendance["OT Money (NPR)"].sum()
                )
                if not attendance.empty
                else 0.0
            )

            total_advance = (
                float(
                    advances["Amount (NPR)"].sum()
                )
                if not advances.empty
                else 0.0
            )

            total_shop = (
                float(
                    shop["Cost (NPR)"].sum()
                )
                if not shop.empty
                else 0.0
            )

            total_paid = (
                float(
                    payments[
                        "Amount Paid (NPR)"
                    ].sum()
                )
                if not payments.empty
                else 0.0
            )

            x1, x2, x3, x4, x5 = st.columns(5)

            x1.metric(
                "Worked Days",
                f"{total_days:.1f}"
            )

            x2.metric(
                "OT Money",
                f"NPR {total_ot:,.2f}"
            )

            x3.metric(
                "Advances",
                f"NPR {total_advance:,.2f}"
            )

            x4.metric(
                "Shop Deductions",
                f"NPR {total_shop:,.2f}"
            )

            x5.metric(
                "Money Paid",
                f"NPR {total_paid:,.2f}"
            )

            st.markdown("---")

            st.markdown(
                "### 📝 Attendance Records"
            )

            if attendance.empty:
                st.info(
                    "No attendance for this month."
                )
            else:
                st.dataframe(
                    attendance.drop(
                        columns=["Month"]
                    ),
                    use_container_width=True
                )

            st.markdown(
                "### 🌴 Leave Records"
            )

            if leaves.empty:
                st.info(
                    "No leaves for this month."
                )
            else:
                st.dataframe(
                    leaves.drop(
                        columns=["Month"]
                    ),
                    use_container_width=True
                )

            st.markdown(
                "### 🛒 Shop Items Taken"
            )

            if shop.empty:
                st.info(
                    "No shop deductions."
                )
            else:
                st.dataframe(
                    shop.drop(
                        columns=["Month"]
                    ),
                    use_container_width=True
                )

            st.markdown(
                "### 💵 Money Taken / Advances"
            )

            if advances.empty:
                st.info(
                    "No advances."
                )
            else:
                st.dataframe(
                    advances.drop(
                        columns=["Month"]
                    ),
                    use_container_width=True
                )

            st.markdown(
                "### 💰 Salary Payments"
            )

            if payments.empty:
                st.info(
                    "No salary payments."
                )
            else:
                st.dataframe(
                    payments.drop(
                        columns=["Month"]
                    ),
                    use_container_width=True
                )


# ============================================================
# END
# ============================================================
