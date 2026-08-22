import streamlit as st
import pandas as pd
import sqlite3
import io
import calendar
from datetime import date, datetime, timedelta

# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Management System",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Management System")

# New database name to avoid conflicts with old database schema
DB_FILE = "workshop_v2.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


# ============================================================
# DATABASE SETUP
# ============================================================

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
                start_date TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # WORK LOGS
        #
        # Each selected date creates one record.
        #
        # work_value:
        # Full Day = 1.0
        # Half Day = 0.5
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                work_type TEXT NOT NULL,
                work_value REAL NOT NULL,
                remarks TEXT,

                FOREIGN KEY(worker_id)
                REFERENCES workers(worker_id)
                ON DELETE CASCADE,

                UNIQUE(worker_id, work_date)
            )
        """)

        # ----------------------------------------------------
        # OVERTIME
        #
        # One OT record per work log
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS overtime (
                ot_id TEXT PRIMARY KEY,
                log_id TEXT NOT NULL UNIQUE,
                worker_id TEXT NOT NULL,
                ot_date TEXT NOT NULL,
                ot_hours REAL NOT NULL DEFAULT 0,
                ot_rate REAL NOT NULL DEFAULT 0,
                ot_amount REAL NOT NULL DEFAULT 0,
                notes TEXT,

                FOREIGN KEY(log_id)
                REFERENCES work_logs(log_id)
                ON DELETE CASCADE,

                FOREIGN KEY(worker_id)
                REFERENCES workers(worker_id)
                ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # LEAVES / HOLIDAYS
        #
        # Each leave date is one record
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                leave_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                leave_value REAL NOT NULL DEFAULT 1.0,
                reason TEXT,

                FOREIGN KEY(worker_id)
                REFERENCES workers(worker_id)
                ON DELETE CASCADE,

                UNIQUE(worker_id, leave_date)
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
        # MONTHLY PAYMENTS
        #
        # IMPORTANT:
        # Unique by worker + month.
        # NOT log_id.
        #
        # This prevents your previous IntegrityError problem.
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_payments (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,

                daily_wage REAL NOT NULL DEFAULT 0,
                total_work_days REAL NOT NULL DEFAULT 0,

                regular_wage REAL NOT NULL DEFAULT 0,
                ot_amount REAL NOT NULL DEFAULT 0,

                gross_salary REAL NOT NULL DEFAULT 0,

                advance_deduction REAL NOT NULL DEFAULT 0,
                shop_deduction REAL NOT NULL DEFAULT 0,

                final_payable REAL NOT NULL DEFAULT 0,

                paid_amount REAL NOT NULL DEFAULT 0,
                balance REAL NOT NULL DEFAULT 0,

                status TEXT NOT NULL,

                created_at TEXT NOT NULL,

                FOREIGN KEY(worker_id)
                REFERENCES workers(worker_id)
                ON DELETE CASCADE,

                UNIQUE(worker_id, month_key)
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


def get_next_id(prefix, table, id_col):

    df = run_query(
        f"SELECT {id_col} FROM {table}"
    )

    if df.empty:
        return f"{prefix}001"

    numbers = []

    for value in df[id_col]:

        digits = "".join(
            filter(str.isdigit, str(value))
        )

        if digits:
            numbers.append(int(digits))

    next_number = max(numbers) + 1 if numbers else 1

    return f"{prefix}{next_number:03d}"


# ============================================================
# DATE HELPERS
# ============================================================

def get_month_key(selected_date):

    return selected_date.strftime("%Y-%m")


def get_month_name(month_key):

    try:

        year, month = month_key.split("-")

        return datetime(
            int(year),
            int(month),
            1
        ).strftime("%B %Y")

    except:
        return month_key


def get_dates_between(start_date, end_date):

    dates = []

    current = start_date

    while current <= end_date:

        dates.append(current)

        current += timedelta(days=1)

    return dates


def get_month_start_end(month_key):

    year, month = map(int, month_key.split("-"))

    start_date = date(year, month, 1)

    last_day = calendar.monthrange(year, month)[1]

    end_date = date(
        year,
        month,
        last_day
    )

    return start_date, end_date


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
            start_date AS 'Started Work On'
        FROM workers
        ORDER BY name
    """)


def load_work_logs():

    return run_query("""
        SELECT
            wl.log_id AS 'Log ID',
            wl.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            wl.work_date AS 'Work Date',
            wl.work_type AS 'Work Type',
            wl.work_value AS 'Worked Days',
            wl.remarks AS 'Remarks'
        FROM work_logs wl
        LEFT JOIN workers w
            ON wl.worker_id = w.worker_id
        ORDER BY wl.work_date DESC
    """)


def load_overtime():

    return run_query("""
        SELECT
            o.ot_id AS 'OT ID',
            o.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            o.ot_date AS 'OT Date',
            o.ot_hours AS 'OT Hours',
            o.ot_rate AS 'OT Rate (NPR)',
            o.ot_amount AS 'OT Amount (NPR)',
            o.notes AS 'OT Notes'
        FROM overtime o
        LEFT JOIN workers w
            ON o.worker_id = w.worker_id
        ORDER BY o.ot_date DESC
    """)


def load_leaves():

    return run_query("""
        SELECT
            l.leave_id AS 'Leave ID',
            l.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            l.leave_date AS 'Leave Date',
            l.leave_type AS 'Leave Type',
            l.leave_value AS 'Days Deducted',
            l.reason AS 'Reason'
        FROM leaves l
        LEFT JOIN workers w
            ON l.worker_id = w.worker_id
        ORDER BY l.leave_date DESC
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
            mp.payment_id AS 'Payment ID',
            mp.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            mp.month_key AS 'Month Key',
            mp.daily_wage AS 'Daily Wage',
            mp.total_work_days AS 'Total Worked Days',
            mp.regular_wage AS 'Regular Wage',
            mp.ot_amount AS 'OT Amount',
            mp.gross_salary AS 'Gross Salary',
            mp.advance_deduction AS 'Advance Deduction',
            mp.shop_deduction AS 'Shop Deduction',
            mp.final_payable AS 'Final Payable',
            mp.paid_amount AS 'Paid Amount',
            mp.balance AS 'Balance',
            mp.status AS 'Status'
        FROM monthly_payments mp
        LEFT JOIN workers w
            ON mp.worker_id = w.worker_id
        ORDER BY mp.month_key DESC, w.name
    """)


# ============================================================
# CALCULATION FUNCTIONS
# ============================================================

def get_worker_month_summary(worker_id, month_key):

    start_date, end_date = get_month_start_end(month_key)

    # --------------------------------------------------------
    # GET WORK DAYS
    # --------------------------------------------------------

    work_df = run_query("""
        SELECT
            work_date,
            work_value
        FROM work_logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.isoformat(),
        end_date.isoformat()
    ))

    if work_df.empty:

        total_worked_days = 0.0

    else:

        total_worked_days = float(
            pd.to_numeric(
                work_df["work_value"]
            ).sum()
        )

    # --------------------------------------------------------
    # GET LEAVES
    # --------------------------------------------------------

    leave_df = run_query("""
        SELECT
            leave_date,
            leave_value
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.isoformat(),
        end_date.isoformat()
    ))

    if leave_df.empty:

        total_leave_days = 0.0

    else:

        total_leave_days = float(
            pd.to_numeric(
                leave_df["leave_value"]
            ).sum()
        )

    # --------------------------------------------------------
    # GET OT
    # --------------------------------------------------------

    ot_df = run_query("""
        SELECT
            ot_hours,
            ot_amount
        FROM overtime
        WHERE worker_id = ?
        AND ot_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.isoformat(),
        end_date.isoformat()
    ))

    if ot_df.empty:

        total_ot_hours = 0.0
        total_ot_amount = 0.0

    else:

        total_ot_hours = float(
            pd.to_numeric(
                ot_df["ot_hours"]
            ).sum()
        )

        total_ot_amount = float(
            pd.to_numeric(
                ot_df["ot_amount"]
            ).sum()
        )

    # --------------------------------------------------------
    # ADVANCES
    # --------------------------------------------------------

    advance_df = run_query("""
        SELECT amount
        FROM advances
        WHERE worker_id = ?
        AND advance_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.isoformat(),
        end_date.isoformat()
    ))

    total_advance = 0.0

    if not advance_df.empty:

        total_advance = float(
            pd.to_numeric(
                advance_df["amount"]
            ).sum()
        )

    # --------------------------------------------------------
    # SHOP CONSUMPTION
    # --------------------------------------------------------

    consumption_df = run_query("""
        SELECT item_cost
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_date.isoformat(),
        end_date.isoformat()
    ))

    total_consumption = 0.0

    if not consumption_df.empty:

        total_consumption = float(
            pd.to_numeric(
                consumption_df["item_cost"]
            ).sum()
        )

    return {
        "worked_days": total_worked_days,
        "leave_days": total_leave_days,
        "ot_hours": total_ot_hours,
        "ot_amount": total_ot_amount,
        "advance": total_advance,
        "consumption": total_consumption,
        "work_df": work_df,
        "leave_df": leave_df
    }


# ============================================================
# GET ALL DATA
# ============================================================

df_workers = load_workers()
df_work_logs = load_work_logs()
df_overtime = load_overtime()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_advances = load_advances()
df_payments = load_payments()


# ============================================================
# EXPORT EXCEL
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

        df_work_logs.to_excel(
            writer,
            sheet_name="Work Logs",
            index=False
        )

        df_overtime.to_excel(
            writer,
            sheet_name="Overtime",
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
            sheet_name="Monthly Payments",
            index=False
        )

    return output.getvalue()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Select Page",
    [
        "Dashboard",
        "Manage Workers",
        "Record Work Days",
        "Record Overtime",
        "Leaves & Holidays",
        "Shop Consumption",
        "Money Taken / Advances",
        "Monthly Financial Payout",
        "Worker Search & Monthly Records"
    ]
)

st.sidebar.markdown("---")

excel_data = generate_excel()

st.sidebar.download_button(
    "📥 Export All Records to Excel",
    excel_data,
    file_name=f"workshop_report_{date.today()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)


# ============================================================
# DASHBOARD
# ============================================================

if menu == "Dashboard":

    st.subheader("📊 Workshop Dashboard")

    total_workers = len(df_workers)

    total_work_days = (
        df_work_logs["Worked Days"].sum()
        if not df_work_logs.empty
        else 0
    )

    total_ot_money = (
        df_overtime["OT Amount (NPR)"].sum()
        if not df_overtime.empty
        else 0
    )

    total_advances = (
        df_advances["Amount (NPR)"].sum()
        if not df_advances.empty
        else 0
    )

    total_shop = (
        df_consumption["Cost (NPR)"].sum()
        if not df_consumption.empty
        else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Total Workers", total_workers)
    c2.metric("Total Worked Days", f"{total_work_days:.1f}")
    c3.metric("Total OT Money", f"NPR {total_ot_money:,.2f}")
    c4.metric("Total Advances", f"NPR {total_advances:,.2f}")
    c5.metric("Shop Deductions", f"NPR {total_shop:,.2f}")

    st.markdown("---")

    st.subheader("📅 Monthly Summary")

    if df_work_logs.empty:

        st.info("No work records available.")

    else:

        temp = df_work_logs.copy()

        temp["Month"] = pd.to_datetime(
            temp["Work Date"]
        ).dt.strftime("%Y-%m")

        months = sorted(
            temp["Month"].unique(),
            reverse=True
        )

        selected_month = st.selectbox(
            "Select Month",
            months,
            format_func=get_month_name
        )

        month_logs = temp[
            temp["Month"] == selected_month
        ]

        st.dataframe(
            month_logs,
            use_container_width=True
        )


# ============================================================
# MANAGE WORKERS
# ============================================================

elif menu == "Manage Workers":

    st.subheader("👷 Manage Workers")

    col1, col2 = st.columns(2)

    # ADD WORKER
    with col1:

        st.markdown("### ➕ Add New Worker")

        with st.form(
            "add_worker",
            clear_on_submit=True
        ):

            worker_id = get_next_id(
                "W",
                "workers",
                "worker_id"
            )

            name = st.text_input(
                "Worker Full Name"
            )

            phone = st.text_input(
                "Phone Number"
            )

            skill = st.selectbox(
                "Skill / Role",
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
                "Date Worker Started Work",
                date.today()
            )

            submitted = st.form_submit_button(
                "Save Worker"
            )

            if submitted:

                if not name.strip():

                    st.error(
                        "Please enter worker name."
                    )

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
                        start_date.isoformat()
                    ))

                    st.success(
                        f"{name} added successfully."
                    )

                    st.rerun()

    # DELETE WORKER
    with col2:

        st.markdown("### ❌ Delete Worker")

        if df_workers.empty:

            st.info("No workers available.")

        else:

            choices = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "Select Worker",
                choices
            )

            delete_id = selected.split(" - ")[0]

            if st.button(
                "Delete Selected Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (delete_id,)
                )

                st.success(
                    "Worker deleted."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# RECORD WORK DAYS
# ============================================================

elif menu == "Record Work Days":

    st.subheader("📝 Record Work Days")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        st.info(
            "You can select one date or multiple dates. "
            "Each date will be saved separately."
        )

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(" - ")[0]

        record_method = st.radio(
            "Select Date Method",
            [
                "Single Date",
                "Multiple Dates",
                "Date Range"
            ],
            horizontal=True
        )

        if record_method == "Single Date":

            selected_dates = [
                st.date_input(
                    "Select Work Date",
                    date.today()
                )
            ]

        elif record_method == "Multiple Dates":

            selected_dates = st.date_input(
                "Select Work Dates",
                value=[],
                format="YYYY-MM-DD"
            )

            if not isinstance(selected_dates, list):

                selected_dates = [selected_dates]

        else:

            date_range = st.date_input(
                "Select Start and End Date",
                value=(
                    date.today(),
                    date.today()
                )
            )

            if (
                isinstance(date_range, tuple)
                and len(date_range) == 2
            ):

                selected_dates = get_dates_between(
                    date_range[0],
                    date_range[1]
                )

            else:

                selected_dates = []

        work_type = st.radio(
            "Work Type",
            [
                "Full Day",
                "Half Day"
            ],
            horizontal=True
        )

        work_value = (
            1.0
            if work_type == "Full Day"
            else 0.5
        )

        remarks = st.text_input(
            "Remarks"
        )

        if selected_dates:

            st.write(
                f"### Selected Work Dates: {len(selected_dates)}"
            )

            preview = pd.DataFrame({
                "Work Date": selected_dates,
                "Work Type": [
                    work_type
                ] * len(selected_dates),
                "Worked Day Value": [
                    work_value
                ] * len(selected_dates)
            })

            st.dataframe(
                preview,
                use_container_width=True
            )

        if st.button(
            "💾 Save Work Records",
            type="primary"
        ):

            if not selected_dates:

                st.error(
                    "Please select at least one date."
                )

            else:

                saved = 0
                skipped = 0

                for work_date in selected_dates:

                    existing = run_query("""
                        SELECT log_id
                        FROM work_logs
                        WHERE worker_id = ?
                        AND work_date = ?
                    """, (
                        worker_id,
                        work_date.isoformat()
                    ))

                    if existing.empty:

                        log_id = get_next_id(
                            "L",
                            "work_logs",
                            "log_id"
                        )

                        run_action("""
                            INSERT INTO work_logs
                            (
                                log_id,
                                worker_id,
                                work_date,
                                work_type,
                                work_value,
                                remarks
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            log_id,
                            worker_id,
                            work_date.isoformat(),
                            work_type,
                            work_value,
                            remarks
                        ))

                        saved += 1

                    else:

                        skipped += 1

                st.success(
                    f"{saved} work record(s) saved. "
                    f"{skipped} duplicate date(s) skipped."
                )

                st.rerun()

    st.markdown("---")

    st.subheader("📋 Work Records")

    st.dataframe(
        load_work_logs(),
        use_container_width=True
    )


# ============================================================
# OVERTIME
# ============================================================

elif menu == "Record Overtime":

    st.subheader("⏰ Record Overtime")

    if df_work_logs.empty:

        st.warning(
            "Record work days first."
        )

    else:

        ot_logs = run_query("""
            SELECT
                wl.log_id,
                wl.worker_id,
                w.name,
                wl.work_date
            FROM work_logs wl
            LEFT JOIN workers w
                ON wl.worker_id = w.worker_id
            LEFT JOIN overtime o
                ON wl.log_id = o.log_id
            WHERE o.log_id IS NULL
            ORDER BY wl.work_date DESC
        """)

        if ot_logs.empty:

            st.info(
                "All work records already have OT entries."
            )

        else:

            choices = (
                ot_logs["log_id"].astype(str)
                + " - "
                + ot_logs["name"].astype(str)
                + " - "
                + ot_logs["work_date"].astype(str)
            )

            selected = st.selectbox(
                "Select Work Record",
                choices
            )

            log_id = selected.split(" - ")[0]

            row = ot_logs[
                ot_logs["log_id"] == log_id
            ].iloc[0]

            worker_id = row["worker_id"]
            ot_date = row["work_date"]

            ot_done = st.radio(
                "Did the worker do overtime?",
                [
                    "No",
                    "Yes"
                ],
                horizontal=True
            )

            if ot_done == "Yes":

                ot_hours = st.number_input(
                    "OT Hours",
                    min_value=0.0,
                    value=1.0,
                    step=0.5
                )

                ot_rate = st.number_input(
                    "OT Money Per Hour (NPR)",
                    min_value=0.0,
                    value=200.0,
                    step=50.0
                )

            else:

                ot_hours = 0.0
                ot_rate = 0.0

            ot_amount = ot_hours * ot_rate

            st.metric(
                "Automatic OT Amount",
                f"NPR {ot_amount:,.2f}"
            )

            notes = st.text_input(
                "OT Notes"
            )

            if st.button(
                "Save OT Record",
                type="primary"
            ):

                ot_id = get_next_id(
                    "OT",
                    "overtime",
                    "ot_id"
                )

                run_action("""
                    INSERT INTO overtime
                    (
                        ot_id,
                        log_id,
                        worker_id,
                        ot_date,
                        ot_hours,
                        ot_rate,
                        ot_amount,
                        notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ot_id,
                    log_id,
                    worker_id,
                    ot_date,
                    ot_hours,
                    ot_rate,
                    ot_amount,
                    notes
                ))

                st.success(
                    f"OT saved. OT Amount = NPR {ot_amount:,.2f}"
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_overtime(),
        use_container_width=True
    )


# ============================================================
# LEAVES & HOLIDAYS
# ============================================================

elif menu == "Leaves & Holidays":

    st.subheader("🌴 Leaves & Holidays")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(" - ")[0]

        leave_dates = st.date_input(
            "Select Leave Date(s)",
            value=[],
            format="YYYY-MM-DD"
        )

        if not isinstance(leave_dates, list):

            leave_dates = [leave_dates]

        leave_type = st.selectbox(
            "Leave Type",
            [
                "Unpaid Leave",
                "Sick Leave",
                "Casual Leave",
                "Festival Holiday",
                "Public Holiday",
                "Other"
            ]
        )

        leave_duration = st.radio(
            "Leave Duration",
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
            "Reason"
        )

        if st.button(
            "Save Leave Record",
            type="primary"
        ):

            if not leave_dates:

                st.error(
                    "Please select at least one leave date."
                )

            else:

                saved = 0
                skipped = 0

                for leave_date in leave_dates:

                    existing = run_query("""
                        SELECT leave_id
                        FROM leaves
                        WHERE worker_id = ?
                        AND leave_date = ?
                    """, (
                        worker_id,
                        leave_date.isoformat()
                    ))

                    if existing.empty:

                        leave_id = get_next_id(
                            "LV",
                            "leaves",
                            "leave_id"
                        )

                        run_action("""
                            INSERT INTO leaves
                            (
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
                            leave_value,
                            reason
                        ))

                        saved += 1

                    else:

                        skipped += 1

                st.success(
                    f"{saved} leave record(s) saved. "
                    f"{skipped} duplicate date(s) skipped."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_leaves(),
        use_container_width=True
    )


# ============================================================
# SHOP CONSUMPTION
# ============================================================

elif menu == "Shop Consumption":

    st.subheader("🛒 Shop Items Consumed")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(" - ")[0]

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

        notes = st.text_input(
            "Notes"
        )

        if st.button(
            "Save Shop Consumption",
            type="primary"
        ):

            if not item_name.strip():

                st.error(
                    "Enter item name."
                )

            else:

                item_id = get_next_id(
                    "C",
                    "shop_consumption",
                    "item_id"
                )

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
                    item_date.isoformat(),
                    item_name,
                    item_cost,
                    notes
                ))

                st.success(
                    "Shop consumption saved."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_consumption(),
        use_container_width=True
    )


# ============================================================
# ADVANCES / MONEY TAKEN
# ============================================================

elif menu == "Money Taken / Advances":

    st.subheader("💵 Money Taken / Advance")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(" - ")[0]

        advance_date = st.date_input(
            "Date",
            date.today()
        )

        amount = st.number_input(
            "Money Taken / Advance Amount (NPR)",
            min_value=0.0,
            value=0.0,
            step=100.0
        )

        reason = st.text_input(
            "Reason"
        )

        if st.button(
            "Save Advance",
            type="primary"
        ):

            if amount <= 0:

                st.error(
                    "Amount must be greater than zero."
                )

            else:

                advance_id = get_next_id(
                    "A",
                    "advances",
                    "advance_id"
                )

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
                    advance_date.isoformat(),
                    amount,
                    reason
                ))

                st.success(
                    "Advance saved."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_advances(),
        use_container_width=True
    )


# ============================================================
# MONTHLY FINANCIAL PAYOUT
# ============================================================

elif menu == "Monthly Financial Payout":

    st.subheader("💰 Monthly Financial Payout")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        selected_worker = st.selectbox(
            "Select Worker",
            worker_choices
        )

        worker_id = selected_worker.split(" - ")[0]

        payment_month = st.date_input(
            "Select Any Date in the Payment Month",
            date.today()
        )

        month_key = get_month_key(
            payment_month
        )

        st.subheader(
            f"📅 {get_month_name(month_key)}"
        )

        summary = get_worker_month_summary(
            worker_id,
            month_key
        )

        worked_days = summary["worked_days"]
        leave_days = summary["leave_days"]
        ot_hours = summary["ot_hours"]
        ot_amount = summary["ot_amount"]
        advance = summary["advance"]
        consumption = summary["consumption"]

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Total Worked Days",
            f"{worked_days:.1f}"
        )

        c2.metric(
            "Leave / Holiday Days",
            f"{leave_days:.1f}"
        )

        c3.metric(
            "Total OT Hours",
            f"{ot_hours:.1f}"
        )

        c4.metric(
            "Total OT Money",
            f"NPR {ot_amount:,.2f}"
        )

        st.info(
            "Worked days are automatically calculated from "
            "your Full Day and Half Day work records."
        )

        daily_wage = st.number_input(
            "Daily Wage (NPR)",
            min_value=0.0,
            value=1500.0,
            step=100.0
        )

        # ----------------------------------------------------
        # AUTOMATIC CALCULATION
        # ----------------------------------------------------

        regular_wage = daily_wage * worked_days

        gross_salary = regular_wage + ot_amount

        final_payable = (
            gross_salary
            - advance
            - consumption
        )

        st.markdown("### 🧮 Automatic Salary Calculation")

        calc1, calc2, calc3 = st.columns(3)

        calc1.metric(
            "Regular Wage",
            f"NPR {regular_wage:,.2f}"
        )

        calc2.metric(
            "Advance Deduction",
            f"NPR {advance:,.2f}"
        )

        calc3.metric(
            "Shop Deduction",
            f"NPR {consumption:,.2f}"
        )

        st.markdown(
            f"""
            **Calculation:**

            `Daily Wage × Total Worked Days`

            `{daily_wage:,.2f} × {worked_days:.1f}`

            = **NPR {regular_wage:,.2f}**

            **Plus OT:**

            `+ NPR {ot_amount:,.2f}`

            **Minus Advance:**

            `- NPR {advance:,.2f}`

            **Minus Shop Items:**

            `- NPR {consumption:,.2f}`
            """
        )

        st.success(
            f"Final Payable Salary: NPR {final_payable:,.2f}"
        )

        paid_amount = st.number_input(
            "Amount Paid Now (NPR)",
            min_value=0.0,
            value=max(0.0, final_payable),
            step=100.0
        )

        balance = final_payable - paid_amount

        if balance <= 0:

            status = "Fully Settled"

        elif paid_amount > 0:

            status = "Partially Paid"

        else:

            status = "Unpaid"

        st.metric(
            "Remaining Balance",
            f"NPR {balance:,.2f}"
        )

        st.write(
            f"**Status: {status}**"
        )

        # Check existing payment
        existing_payment = run_query("""
            SELECT payment_id
            FROM monthly_payments
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            worker_id,
            month_key
        ))

        if existing_payment.empty:

            if st.button(
                "💾 Save Monthly Payment",
                type="primary"
            ):

                payment_id = get_next_id(
                    "P",
                    "monthly_payments",
                    "payment_id"
                )

                run_action("""
                    INSERT INTO monthly_payments
                    (
                        payment_id,
                        worker_id,
                        month_key,
                        daily_wage,
                        total_work_days,
                        regular_wage,
                        ot_amount,
                        gross_salary,
                        advance_deduction,
                        shop_deduction,
                        final_payable,
                        paid_amount,
                        balance,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    payment_id,
                    worker_id,
                    month_key,
                    daily_wage,
                    worked_days,
                    regular_wage,
                    ot_amount,
                    gross_salary,
                    advance,
                    consumption,
                    final_payable,
                    paid_amount,
                    balance,
                    status,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ))

                st.success(
                    "Monthly payment saved successfully."
                )

                st.rerun()

        else:

            payment_id = existing_payment.iloc[0]["payment_id"]

            st.warning(
                f"A payment already exists for this worker "
                f"for {get_month_name(month_key)}."
            )

            if st.button(
                "🔄 Update Monthly Payment",
                type="primary"
            ):

                run_action("""
                    UPDATE monthly_payments
                    SET
                        daily_wage = ?,
                        total_work_days = ?,
                        regular_wage = ?,
                        ot_amount = ?,
                        gross_salary = ?,
                        advance_deduction = ?,
                        shop_deduction = ?,
                        final_payable = ?,
                        paid_amount = ?,
                        balance = ?,
                        status = ?
                    WHERE payment_id = ?
                """, (
                    daily_wage,
                    worked_days,
                    regular_wage,
                    ot_amount,
                    gross_salary,
                    advance,
                    consumption,
                    final_payable,
                    paid_amount,
                    balance,
                    status,
                    payment_id
                ))

                st.success(
                    "Monthly payment updated successfully."
                )

                st.rerun()

    st.markdown("---")

    st.subheader("📋 Saved Monthly Payments")

    st.dataframe(
        load_payments(),
        use_container_width=True
    )


# ============================================================
# WORKER SEARCH & MONTHLY RECORDS
# ============================================================

elif menu == "Worker Search & Monthly Records":

    st.subheader(
        "🔍 Search Worker and View All Records"
    )

    if df_workers.empty:

        st.warning(
            "No workers available."
        )

    else:

        search_name = st.text_input(
            "Search Worker by Name"
        )

        search_df = df_workers.copy()

        if search_name.strip():

            search_df = search_df[
                search_df["Name"]
                .str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if search_df.empty:

            st.warning(
                "No worker found."
            )

        else:

            choices = (
                search_df["Worker ID"].astype(str)
                + " - "
                + search_df["Name"].astype(str)
            )

            selected_worker = st.selectbox(
                "Select Worker",
                choices
            )

            worker_id = selected_worker.split(" - ")[0]

            worker = df_workers[
                df_workers["Worker ID"] == worker_id
            ].iloc[0]

            st.markdown("### 👷 Worker Information")

            a, b, c = st.columns(3)

            a.metric(
                "Worker Name",
                worker["Name"]
            )

            b.metric(
                "Role",
                worker["Skill"]
            )

            c.metric(
                "Started Work",
                worker["Started Work On"]
            )

            # Get available months
            worker_logs = run_query("""
                SELECT work_date
                FROM work_logs
                WHERE worker_id = ?
            """, (worker_id,))

            if worker_logs.empty:

                month_key = date.today().strftime(
                    "%Y-%m"
                )

            else:

                worker_logs["month_key"] = pd.to_datetime(
                    worker_logs["work_date"]
                ).dt.strftime("%Y-%m")

                available_months = sorted(
                    worker_logs["month_key"]
                    .unique(),
                    reverse=True
                )

                month_key = st.selectbox(
                    "Select Month",
                    available_months,
                    format_func=get_month_name
                )

            summary = get_worker_month_summary(
                worker_id,
                month_key
            )

            st.markdown(
                f"## 📅 {get_month_name(month_key)} Records"
            )

            # ------------------------------------------------
            # WORK DAYS
            # ------------------------------------------------

            work_records = run_query("""
                SELECT
                    work_date AS 'Date',
                    work_type AS 'Work Type',
                    work_value AS 'Worked Day',
                    remarks AS 'Remarks'
                FROM work_logs
                WHERE worker_id = ?
                AND substr(work_date, 1, 7) = ?
                ORDER BY work_date
            """, (
                worker_id,
                month_key
            ))

            # ------------------------------------------------
            # LEAVES
            # ------------------------------------------------

            leave_records = run_query("""
                SELECT
                    leave_date AS 'Date',
                    leave_type AS 'Leave Type',
                    leave_value AS 'Days',
                    reason AS 'Reason'
                FROM leaves
                WHERE worker_id = ?
                AND substr(leave_date, 1, 7) = ?
                ORDER BY leave_date
            """, (
                worker_id,
                month_key
            ))

            # ------------------------------------------------
            # OT
            # ------------------------------------------------

            ot_records = run_query("""
                SELECT
                    ot_date AS 'Date',
                    ot_hours AS 'OT Hours',
                    ot_rate AS 'Rate',
                    ot_amount AS 'OT Money',
                    notes AS 'Notes'
                FROM overtime
                WHERE worker_id = ?
                AND substr(ot_date, 1, 7) = ?
                ORDER BY ot_date
            """, (
                worker_id,
                month_key
            ))

            # ------------------------------------------------
            # ADVANCES
            # ------------------------------------------------

            advance_records = run_query("""
                SELECT
                    advance_date AS 'Date',
                    amount AS 'Amount',
                    reason AS 'Reason'
                FROM advances
                WHERE worker_id = ?
                AND substr(advance_date, 1, 7) = ?
                ORDER BY advance_date
            """, (
                worker_id,
                month_key
            ))

            # ------------------------------------------------
            # SHOP ITEMS
            # ------------------------------------------------

            shop_records = run_query("""
                SELECT
                    entry_date AS 'Date',
                    item_name AS 'Item',
                    item_cost AS 'Cost',
                    notes AS 'Notes'
                FROM shop_consumption
                WHERE worker_id = ?
                AND substr(entry_date, 1, 7) = ?
                ORDER BY entry_date
            """, (
                worker_id,
                month_key
            ))

            m1, m2, m3, m4, m5 = st.columns(5)

            m1.metric(
                "Worked Days",
                f"{summary['worked_days']:.1f}"
            )

            m2.metric(
                "Leave Days",
                f"{summary['leave_days']:.1f}"
            )

            m3.metric(
                "OT Hours",
                f"{summary['ot_hours']:.1f}"
            )

            m4.metric(
                "Advance Taken",
                f"NPR {summary['advance']:,.2f}"
            )

            m5.metric(
                "Shop Taken",
                f"NPR {summary['consumption']:,.2f}"
            )

            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📝 Work Days",
                "🌴 Holidays",
                "⏰ Overtime",
                "💵 Money Taken",
                "🛒 Shop Items"
            ])

            with tab1:

                st.dataframe(
                    work_records,
                    use_container_width=True
                )

                st.write(
                    f"### Total Worked Days: "
                    f"{summary['worked_days']:.1f}"
                )

            with tab2:

                st.dataframe(
                    leave_records,
                    use_container_width=True
                )

                st.write(
                    f"### Total Leave Days: "
                    f"{summary['leave_days']:.1f}"
                )

            with tab3:

                st.dataframe(
                    ot_records,
                    use_container_width=True
                )

                st.write(
                    f"### Total OT Hours: "
                    f"{summary['ot_hours']:.1f}"
                )

                st.write(
                    f"### Total OT Money: NPR "
                    f"{summary['ot_amount']:,.2f}"
                )

            with tab4:

                st.dataframe(
                    advance_records,
                    use_container_width=True
                )

                st.write(
                    f"### Total Money Taken: NPR "
                    f"{summary['advance']:,.2f}"
                )

            with tab5:

                st.dataframe(
                    shop_records,
                    use_container_width=True
                )

                st.write(
                    f"### Total Shop Deduction: NPR "
                    f"{summary['consumption']:,.2f}"
                )
