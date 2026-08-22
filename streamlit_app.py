import streamlit as st
import pandas as pd
from datetime import date
import sqlite3
import io
import calendar

# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Furniture Workshop Tracker",
    page_icon="🪚",
    layout="wide"
)

st.title("🪚 Furniture Workshop Record System")
st.caption("Workers • Attendance • Half Days • Holidays • OT • Advances • Monthly Payouts")

DB_FILE = "workshop.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Important for foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def table_columns(table_name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]


# ============================================================
# DATABASE SETUP + MIGRATION
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
                start_date TEXT
            )
        """)

        worker_cols = table_columns("workers")

        if "start_date" not in worker_cols:
            cursor.execute("""
                ALTER TABLE workers
                ADD COLUMN start_date TEXT
            """)

        # ----------------------------------------------------
        # LOGS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                days_worked REAL DEFAULT 1.0,
                ot_hours REAL DEFAULT 0.0,
                ot_notes TEXT,
                remarks TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        log_cols = table_columns("logs")

        if "days_worked" not in log_cols:
            cursor.execute("""
                ALTER TABLE logs
                ADD COLUMN days_worked REAL DEFAULT 1.0
            """)

        if "ot_hours" not in log_cols:
            cursor.execute("""
                ALTER TABLE logs
                ADD COLUMN ot_hours REAL DEFAULT 0.0
            """)

        if "ot_notes" not in log_cols:
            cursor.execute("""
                ALTER TABLE logs
                ADD COLUMN ot_notes TEXT
            """)

        if "remarks" not in log_cols:
            cursor.execute("""
                ALTER TABLE logs
                ADD COLUMN remarks TEXT
            """)

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
                FOREIGN KEY (worker_id)
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
                item_cost REAL NOT NULL,
                notes TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE
            )
        """)

        # ----------------------------------------------------
        # MONTHLY FINANCIALS
        # ----------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financials (
                payment_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                month_key TEXT NOT NULL,
                daily_wage REAL DEFAULT 0.0,
                total_worked_days REAL DEFAULT 0.0,
                total_ot_hours REAL DEFAULT 0.0,
                ot_rate_per_hour REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0,
                taken_money REAL DEFAULT 0.0,
                advance_reason TEXT,
                shop_deduction REAL DEFAULT 0.0,
                received_money REAL DEFAULT 0.0,
                remaining_due REAL DEFAULT 0.0,
                status TEXT,
                FOREIGN KEY (worker_id)
                    REFERENCES workers(worker_id)
                    ON DELETE CASCADE,
                UNIQUE(worker_id, month_key)
            )
        """)

        # Add columns if an older financials table exists
        financial_cols = table_columns("financials")

        migration_columns = {
            "worker_id": "TEXT",
            "month_key": "TEXT",
            "daily_wage": "REAL DEFAULT 0.0",
            "total_worked_days": "REAL DEFAULT 0.0",
            "total_ot_hours": "REAL DEFAULT 0.0",
            "ot_rate_per_hour": "REAL DEFAULT 0.0",
            "total_earned": "REAL DEFAULT 0.0",
            "taken_money": "REAL DEFAULT 0.0",
            "advance_reason": "TEXT",
            "shop_deduction": "REAL DEFAULT 0.0",
            "received_money": "REAL DEFAULT 0.0",
            "remaining_due": "REAL DEFAULT 0.0",
            "status": "TEXT"
        }

        for col_name, col_type in migration_columns.items():

            if col_name not in financial_cols:

                try:
                    cursor.execute(
                        f"""
                        ALTER TABLE financials
                        ADD COLUMN {col_name} {col_type}
                        """
                    )
                except sqlite3.OperationalError:
                    pass

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_logs_worker_date
            ON logs(worker_id, work_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_leaves_worker_date
            ON leaves(worker_id, leave_date)
        """)

        conn.commit()


# Initialize database
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

    for value in df[id_col].dropna():

        digits = "".join(
            filter(str.isdigit, str(value))
        )

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
            start_date AS 'Started Working'
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
            l.days_worked AS 'Days Worked',
            l.ot_hours AS 'OT Hours',
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


def load_financials():

    return run_query("""
        SELECT
            f.payment_id AS 'Payment ID',
            f.worker_id AS 'Worker ID',
            w.name AS 'Worker Name',
            f.month_key AS 'Month',
            f.daily_wage AS 'Daily Wage (NPR)',
            f.total_worked_days AS 'Total Worked Days',
            f.total_ot_hours AS 'Total OT Hours',
            f.ot_rate_per_hour AS 'OT Rate/Hr (NPR)',
            f.total_earned AS 'Total Earned (NPR)',
            f.taken_money AS 'Taken / Advance (NPR)',
            f.advance_reason AS 'Advance Reason',
            f.shop_deduction AS 'Shop Deduction (NPR)',
            f.received_money AS 'Money Paid (NPR)',
            f.remaining_due AS 'Remaining Due (NPR)',
            f.status AS 'Status'
        FROM financials f
        LEFT JOIN workers w
            ON f.worker_id = w.worker_id
        ORDER BY f.month_key DESC, w.name
    """)


# ============================================================
# MONTH HELPERS
# ============================================================

def month_key_from_date(selected_date):

    return selected_date.strftime("%Y-%m")


def month_display(month_key):

    try:

        year, month = month_key.split("-")

        return date(
            int(year),
            int(month),
            1
        ).strftime("%B %Y")

    except Exception:

        return month_key


def get_month_dates(month_key):

    year, month = map(int, month_key.split("-"))

    last_day = calendar.monthrange(
        year,
        month
    )[1]

    return (
        date(year, month, 1),
        date(year, month, last_day)
    )


def calculate_worker_month(worker_id, month_key):

    start_month, end_month = get_month_dates(month_key)

    # --------------------------------------------------------
    # WORK RECORDS
    # --------------------------------------------------------

    work_df = run_query("""
        SELECT
            COALESCE(SUM(days_worked), 0) AS total_days,
            COALESCE(SUM(ot_hours), 0) AS total_ot
        FROM logs
        WHERE worker_id = ?
        AND work_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_month.strftime("%Y-%m-%d"),
        end_month.strftime("%Y-%m-%d")
    ))

    total_days = float(
        work_df.iloc[0]["total_days"]
    )

    total_ot = float(
        work_df.iloc[0]["total_ot"]
    )

    # --------------------------------------------------------
    # HOLIDAYS / LEAVES
    # --------------------------------------------------------

    leave_df = run_query("""
        SELECT COUNT(*) AS total_leaves
        FROM leaves
        WHERE worker_id = ?
        AND leave_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_month.strftime("%Y-%m-%d"),
        end_month.strftime("%Y-%m-%d")
    ))

    total_leaves = int(
        leave_df.iloc[0]["total_leaves"]
    )

    # --------------------------------------------------------
    # SHOP DEDUCTIONS
    # --------------------------------------------------------

    shop_df = run_query("""
        SELECT COALESCE(SUM(item_cost), 0) AS total_shop
        FROM shop_consumption
        WHERE worker_id = ?
        AND entry_date BETWEEN ? AND ?
    """, (
        worker_id,
        start_month.strftime("%Y-%m-%d"),
        end_month.strftime("%Y-%m-%d")
    ))

    total_shop = float(
        shop_df.iloc[0]["total_shop"]
    )

    return {
        "worked_days": total_days,
        "ot_hours": total_ot,
        "leave_days": total_leaves,
        "shop_deduction": total_shop
    }


# ============================================================
# LOAD CURRENT DATA
# ============================================================

df_workers = load_workers()
df_logs = load_logs()
df_leaves = load_leaves()
df_consumption = load_consumption()
df_financials = load_financials()


# ============================================================
# EXPORT HELPERS
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
            sheet_name="Work Records",
            index=False
        )

        df_leaves.to_excel(
            writer,
            sheet_name="Leaves",
            index=False
        )

        df_consumption.to_excel(
            writer,
            sheet_name="Shop Expenses",
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
# SIDEBAR
# ============================================================

st.sidebar.header("📍 Navigation")

menu = st.sidebar.radio(
    "Go to:",
    [
        "Dashboard",
        "Manage Workers",
        "Log Work Days & OT",
        "Leaves & Holidays",
        "Shop Items",
        "Monthly Financial Payout",
        "Worker Monthly Search"
    ]
)

st.sidebar.markdown("---")

st.sidebar.header("📥 Export Reports")

excel_data = generate_excel()

st.sidebar.download_button(
    "📊 Export All Data - Excel",
    excel_data,
    f"workshop_report_{date.today()}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

with st.sidebar.expander("Export CSV Files"):

    st.download_button(
        "Workers CSV",
        convert_df_to_csv(df_workers),
        f"workers_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Work Records CSV",
        convert_df_to_csv(df_logs),
        f"work_records_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Leaves CSV",
        convert_df_to_csv(df_leaves),
        f"leaves_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Shop Items CSV",
        convert_df_to_csv(df_consumption),
        f"shop_items_{date.today()}.csv",
        "text/csv"
    )

    st.download_button(
        "Financials CSV",
        convert_df_to_csv(df_financials),
        f"financials_{date.today()}.csv",
        "text/csv"
    )


# ============================================================
# 1. DASHBOARD
# ============================================================

if menu == "Dashboard":

    st.subheader("📊 Workshop Dashboard")

    total_workers = len(df_workers)

    total_work_days = (
        pd.to_numeric(
            df_logs["Days Worked"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_logs.empty
        else 0
    )

    total_ot = (
        pd.to_numeric(
            df_logs["OT Hours"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_logs.empty
        else 0
    )

    total_leaves = len(df_leaves)

    total_due = (
        pd.to_numeric(
            df_financials["Remaining Due (NPR)"],
            errors="coerce"
        ).fillna(0).sum()
        if not df_financials.empty
        else 0
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric(
        "Total Workers",
        total_workers
    )

    col2.metric(
        "Total Worked Days",
        f"{total_work_days:.1f}"
    )

    col3.metric(
        "Total OT Hours",
        f"{total_ot:.1f}"
    )

    col4.metric(
        "Leave Records",
        total_leaves
    )

    col5.metric(
        "Total Remaining Due",
        f"NPR {total_due:,.2f}"
    )

    st.markdown("---")

    if not df_logs.empty:

        df_months = df_logs.copy()

        df_months["Date Object"] = pd.to_datetime(
            df_months["Date"]
        )

        df_months["Month"] = (
            df_months["Date Object"]
            .dt.strftime("%Y-%m")
        )

        months = sorted(
            df_months["Month"].unique(),
            reverse=True
        )

        selected_month = st.selectbox(
            "Select Month",
            months,
            format_func=month_display
        )

        monthly_logs = df_months[
            df_months["Month"] == selected_month
        ].drop(
            columns=["Date Object", "Month"]
        )

        st.subheader(
            f"📅 Work Records - {month_display(selected_month)}"
        )

        st.dataframe(
            monthly_logs,
            use_container_width=True
        )

    else:

        st.info("No work records yet.")


# ============================================================
# 2. MANAGE WORKERS
# ============================================================

elif menu == "Manage Workers":

    st.subheader("👥 Manage Workers")

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("### Add New Worker")

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
                "Date Started Working",
                value=date.today()
            )

            submit = st.form_submit_button(
                "➕ Add Worker"
            )

            if submit:

                if not name.strip():

                    st.error(
                        "Please enter the worker name."
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

            choices = (
                df_workers["Worker ID"].astype(str)
                + " - "
                + df_workers["Name"].astype(str)
            )

            selected = st.selectbox(
                "Select Worker",
                choices,
                key="delete_worker"
            )

            delete_id = selected.split(" - ")[0]

            if st.button(
                "❌ Delete Worker",
                type="primary"
            ):

                run_action(
                    "DELETE FROM workers WHERE worker_id = ?",
                    (delete_id,)
                )

                st.success(
                    "Worker deleted successfully."
                )

                st.rerun()

    st.markdown("---")

    st.dataframe(
        load_workers(),
        use_container_width=True
    )


# ============================================================
# 3. LOG WORK DAYS AND OT
# ============================================================

elif menu == "Log Work Days & OT":

    st.subheader("📝 Record Work Days, Half Days & OT")

    if df_workers.empty:

        st.warning(
            "Please add a worker first."
        )

    else:

        col1, col2 = st.columns(2)

        # ----------------------------------------------------
        # ADD WORK RECORD
        # ----------------------------------------------------

        with col1:

            st.markdown("### Add Work Record(s)")

            with st.form(
                "work_log_form",
                clear_on_submit=True
            ):

                worker_choices = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "Select Worker",
                    worker_choices
                )

                selected_worker_id = (
                    worker_choice.split(" - ")[0]
                )

                st.markdown(
                    "### 📅 Select One Date or Multiple Dates"
                )

                # Date range selector
                selected_date_range = st.date_input(
                    "Work Date / Date Range",
                    value=(date.today(), date.today()),
                    help=(
                        "For one day select the same start and end date. "
                        "For multiple days select the first and last date."
                    )
                )

                work_type = st.selectbox(
                    "Work Type",
                    [
                        "Full Day",
                        "Half Day"
                    ]
                )

                days_worked_value = (
                    1.0
                    if work_type == "Full Day"
                    else 0.5
                )

                st.markdown("---")

                did_ot = st.checkbox(
                    "Yes, worker did overtime"
                )

                if did_ot:

                    ot_hours = st.number_input(
                        "OT Hours Per Day",
                        min_value=0.0,
                        value=2.0,
                        step=0.5
                    )

                    ot_notes = st.text_input(
                        "OT Details"
                    )

                else:

                    ot_hours = 0.0
                    ot_notes = ""

                remarks = st.text_input(
                    "Work Remarks"
                )

                save_logs = st.form_submit_button(
                    "💾 Save Work Record(s)"
                )

                if save_logs:

                    # ----------------------------------------
                    # DATE RANGE HANDLING
                    # ----------------------------------------

                    if isinstance(
                        selected_date_range,
                        tuple
                    ):

                        start_date = (
                            selected_date_range[0]
                        )

                        end_date = (
                            selected_date_range[1]
                        )

                    else:

                        start_date = selected_date_range
                        end_date = selected_date_range

                    if start_date is None:

                        st.error(
                            "Please select a work date."
                        )

                    else:

                        if end_date is None:
                            end_date = start_date

                        if end_date < start_date:

                            st.error(
                                "End date cannot be before start date."
                            )

                        else:

                            date_list = pd.date_range(
                                start=start_date,
                                end=end_date,
                                freq="D"
                            ).date.tolist()

                            saved_count = 0
                            skipped_count = 0

                            for current_date in date_list:

                                formatted_date = (
                                    current_date.strftime(
                                        "%Y-%m-%d"
                                    )
                                )

                                # Check duplicate date
                                existing = run_query("""
                                    SELECT log_id
                                    FROM logs
                                    WHERE worker_id = ?
                                    AND work_date = ?
                                """, (
                                    selected_worker_id,
                                    formatted_date
                                ))

                                if not existing.empty:

                                    skipped_count += 1
                                    continue

                                log_id = get_next_id(
                                    "L",
                                    "logs",
                                    "log_id"
                                )

                                run_action("""
                                    INSERT INTO logs
                                    (
                                        log_id,
                                        worker_id,
                                        work_date,
                                        days_worked,
                                        ot_hours,
                                        ot_notes,
                                        remarks
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    log_id,
                                    selected_worker_id,
                                    formatted_date,
                                    days_worked_value,
                                    ot_hours,
                                    ot_notes,
                                    remarks
                                ))

                                saved_count += 1

                            actual_work_days = (
                                saved_count
                                * days_worked_value
                            )

                            if saved_count > 0:

                                st.success(
                                    f"""
Saved {saved_count} work date(s).

Total worked days added:
{actual_work_days:.1f}

Work type:
{work_type}
                                    """
                                )

                            if skipped_count > 0:

                                st.warning(
                                    f"{skipped_count} date(s) already existed and were skipped."
                                )

                            st.rerun()

        # ----------------------------------------------------
        # DELETE WORK RECORD
        # ----------------------------------------------------

        with col2:

            st.markdown("### Delete Work Record")

            if df_logs.empty:

                st.info(
                    "No work records available."
                )

            else:

                log_choices = (
                    df_logs["Log ID"].astype(str)
                    + " | "
                    + df_logs["Worker Name"].astype(str)
                    + " | "
                    + df_logs["Date"].astype(str)
                )

                selected_log = st.selectbox(
                    "Select Work Record",
                    log_choices
                )

                delete_log_id = (
                    selected_log.split(" | ")[0]
                )

                if st.button(
                    "❌ Delete Selected Record",
                    type="primary"
                ):

                    run_action("""
                        DELETE FROM logs
                        WHERE log_id = ?
                    """, (
                        delete_log_id,
                    ))

                    st.success(
                        "Work record deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.subheader("📋 All Work Records")

    st.dataframe(
        load_logs(),
        use_container_width=True
    )


# ============================================================
# 4. LEAVES AND HOLIDAYS
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

            st.markdown("### Add Leave / Holiday")

            with st.form(
                "leave_form",
                clear_on_submit=True
            ):

                worker_choices = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "Select Worker",
                    worker_choices,
                    key="leave_worker"
                )

                worker_id = (
                    worker_choice.split(" - ")[0]
                )

                leave_date = st.date_input(
                    "Leave Date",
                    value=date.today()
                )

                leave_type = st.selectbox(
                    "Leave Type",
                    [
                        "Casual Leave",
                        "Sick Leave",
                        "Festival Holiday",
                        "Public Holiday",
                        "Unpaid Leave"
                    ]
                )

                reason = st.text_input(
                    "Reason / Remarks"
                )

                save_leave = st.form_submit_button(
                    "Save Leave"
                )

                if save_leave:

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

                        st.warning(
                            "This worker already has a leave record on this date."
                        )

                    else:

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
                                reason
                            )
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            leave_id,
                            worker_id,
                            leave_date.strftime("%Y-%m-%d"),
                            leave_type,
                            reason
                        ))

                        st.success(
                            "Leave recorded successfully."
                        )

                        st.rerun()

        with col2:

            st.markdown("### Delete Leave")

            if df_leaves.empty:

                st.info(
                    "No leave records."
                )

            else:

                leave_choices = (
                    df_leaves["Leave ID"].astype(str)
                    + " | "
                    + df_leaves["Worker Name"].astype(str)
                    + " | "
                    + df_leaves["Leave Date"].astype(str)
                )

                selected_leave = st.selectbox(
                    "Select Leave Record",
                    leave_choices
                )

                leave_id = (
                    selected_leave.split(" | ")[0]
                )

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
# 5. SHOP ITEMS
# ============================================================

elif menu == "Shop Items":

    st.subheader("🛒 Shop Items Taken by Workers")

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

                worker_choices = (
                    df_workers["Worker ID"].astype(str)
                    + " - "
                    + df_workers["Name"].astype(str)
                )

                worker_choice = st.selectbox(
                    "Select Worker",
                    worker_choices,
                    key="shop_worker"
                )

                worker_id = (
                    worker_choice.split(" - ")[0]
                )

                entry_date = st.date_input(
                    "Date",
                    value=date.today()
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

                save_item = st.form_submit_button(
                    "Save Shop Item"
                )

                if save_item:

                    if not item_name.strip():

                        st.error(
                            "Please enter an item name."
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
                            entry_date.strftime("%Y-%m-%d"),
                            item_name,
                            item_cost,
                            notes
                        ))

                        st.success(
                            "Shop item recorded."
                        )

                        st.rerun()

        with col2:

            st.markdown("### Delete Shop Item")

            if df_consumption.empty:

                st.info(
                    "No shop item records."
                )

            else:

                item_choices = (
                    df_consumption["Item ID"].astype(str)
                    + " | "
                    + df_consumption["Worker Name"].astype(str)
                    + " | "
                    + df_consumption["Item"].astype(str)
                )

                selected_item = st.selectbox(
                    "Select Item",
                    item_choices
                )

                item_id = (
                    selected_item.split(" | ")[0]
                )

                if st.button(
                    "❌ Delete Item",
                    type="primary"
                ):

                    run_action("""
                        DELETE FROM shop_consumption
                        WHERE item_id = ?
                    """, (
                        item_id,
                    ))

                    st.success(
                        "Shop item deleted."
                    )

                    st.rerun()

    st.markdown("---")

    st.dataframe(
        load_consumption(),
        use_container_width=True
    )


# ============================================================
# 6. MONTHLY FINANCIAL PAYOUT
# ============================================================

elif menu == "Monthly Financial Payout":

    st.subheader("💰 Monthly Financial Payout")

    if df_workers.empty:

        st.warning(
            "Please add workers first."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        col1, col2 = st.columns(2)

        with col1:

            selected_worker = st.selectbox(
                "Select Worker",
                worker_choices,
                key="financial_worker"
            )

            worker_id = (
                selected_worker.split(" - ")[0]
            )

        with col2:

            selected_month_date = st.date_input(
                "Select Any Date in the Month",
                value=date.today(),
                key="financial_month"
            )

            selected_month = month_key_from_date(
                selected_month_date
            )

        # ----------------------------------------------------
        # CALCULATE AUTOMATICALLY
        # ----------------------------------------------------

        summary = calculate_worker_month(
            worker_id,
            selected_month
        )

        st.markdown("---")

        st.subheader(
            f"Automatic Calculation - {month_display(selected_month)}"
        )

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "Worked Days",
            f"{summary['worked_days']:.1f}"
        )

        m2.metric(
            "Leave Days",
            summary["leave_days"]
        )

        m3.metric(
            "OT Hours",
            f"{summary['ot_hours']:.1f}"
        )

        m4.metric(
            "Shop Deduction",
            f"NPR {summary['shop_deduction']:,.2f}"
        )

        st.info(
            "Worked days are calculated automatically from Full Day (1.0) and Half Day (0.5) records."
        )

        # Existing financial record
        existing_financial = run_query("""
            SELECT *
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            worker_id,
            selected_month
        ))

        if existing_financial.empty:

            existing_daily_wage = 1500.0
            existing_ot_rate = 200.0
            existing_taken = 0.0
            existing_reason = ""
            existing_paid = 0.0

        else:

            row = existing_financial.iloc[0]

            existing_daily_wage = float(
                row["daily_wage"]
                if pd.notna(row["daily_wage"])
                else 1500.0
            )

            existing_ot_rate = float(
                row["ot_rate_per_hour"]
                if pd.notna(row["ot_rate_per_hour"])
                else 200.0
            )

            existing_taken = float(
                row["taken_money"]
                if pd.notna(row["taken_money"])
                else 0.0
            )

            existing_reason = str(
                row["advance_reason"]
                if pd.notna(row["advance_reason"])
                else ""
            )

            existing_paid = float(
                row["received_money"]
                if pd.notna(row["received_money"])
                else 0.0
            )

        # ----------------------------------------------------
        # FINANCIAL FORM
        # ----------------------------------------------------

        with st.form("monthly_financial_form"):

            daily_wage = st.number_input(
                "Daily Wage Rate (NPR)",
                min_value=0.0,
                value=existing_daily_wage,
                step=100.0
            )

            ot_rate = st.number_input(
                "OT Money Per Hour (NPR)",
                min_value=0.0,
                value=existing_ot_rate,
                step=50.0
            )

            taken_money = st.number_input(
                "Money Taken / Advance (NPR)",
                min_value=0.0,
                value=existing_taken,
                step=100.0
            )

            advance_reason = st.text_input(
                "Reason for Advance",
                value=existing_reason
            )

            received_money = st.number_input(
                "Money Paid to Worker (NPR)",
                min_value=0.0,
                value=existing_paid,
                step=100.0
            )

            # Automatic calculations
            normal_wage = (
                summary["worked_days"]
                * daily_wage
            )

            ot_money = (
                summary["ot_hours"]
                * ot_rate
            )

            total_earned = (
                normal_wage
                + ot_money
            )

            remaining_due = (
                total_earned
                - taken_money
                - summary["shop_deduction"]
                - received_money
            )

            st.markdown("---")

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Normal Wage",
                f"NPR {normal_wage:,.2f}"
            )

            c2.metric(
                "OT Money",
                f"NPR {ot_money:,.2f}"
            )

            c3.metric(
                "Total Earned",
                f"NPR {total_earned:,.2f}"
            )

            st.metric(
                "Remaining Due",
                f"NPR {remaining_due:,.2f}"
            )

            if remaining_due <= 0:

                status = "Fully Settled"

            elif received_money > 0 or taken_money > 0:

                status = "Partially Paid"

            else:

                status = "Unpaid"

            save_financial = st.form_submit_button(
                "💾 Save / Update Monthly Payout"
            )

            if save_financial:

                if existing_financial.empty:

                    payment_id = get_next_id(
                        "P",
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
                            total_worked_days,
                            total_ot_hours,
                            ot_rate_per_hour,
                            total_earned,
                            taken_money,
                            advance_reason,
                            shop_deduction,
                            received_money,
                            remaining_due,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        payment_id,
                        worker_id,
                        selected_month,
                        daily_wage,
                        summary["worked_days"],
                        summary["ot_hours"],
                        ot_rate,
                        total_earned,
                        taken_money,
                        advance_reason,
                        summary["shop_deduction"],
                        received_money,
                        remaining_due,
                        status
                    ))

                else:

                    run_action("""
                        UPDATE financials
                        SET
                            daily_wage = ?,
                            total_worked_days = ?,
                            total_ot_hours = ?,
                            ot_rate_per_hour = ?,
                            total_earned = ?,
                            taken_money = ?,
                            advance_reason = ?,
                            shop_deduction = ?,
                            received_money = ?,
                            remaining_due = ?,
                            status = ?
                        WHERE worker_id = ?
                        AND month_key = ?
                    """, (
                        daily_wage,
                        summary["worked_days"],
                        summary["ot_hours"],
                        ot_rate,
                        total_earned,
                        taken_money,
                        advance_reason,
                        summary["shop_deduction"],
                        received_money,
                        remaining_due,
                        status,
                        worker_id,
                        selected_month
                    ))

                st.success(
                    "Monthly financial record saved successfully."
                )

                st.rerun()

        st.markdown("---")

        st.subheader("📋 All Monthly Financial Records")

        st.dataframe(
            load_financials(),
            use_container_width=True
        )


# ============================================================
# 7. WORKER MONTHLY SEARCH
# ============================================================

elif menu == "Worker Monthly Search":

    st.subheader("🔎 Search Worker Records")

    if df_workers.empty:

        st.warning(
            "No workers available."
        )

    else:

        worker_choices = (
            df_workers["Worker ID"].astype(str)
            + " - "
            + df_workers["Name"].astype(str)
        )

        col1, col2 = st.columns(2)

        with col1:

            selected_worker = st.selectbox(
                "Search Worker by Name",
                worker_choices
            )

            worker_id = (
                selected_worker.split(" - ")[0]
            )

        with col2:

            selected_date = st.date_input(
                "Select Month",
                value=date.today(),
                key="search_month"
            )

            selected_month = month_key_from_date(
                selected_date
            )

        start_month, end_month = get_month_dates(
            selected_month
        )

        worker_info = run_query("""
            SELECT *
            FROM workers
            WHERE worker_id = ?
        """, (
            worker_id,
        ))

        summary = calculate_worker_month(
            worker_id,
            selected_month
        )

        st.markdown("---")

        if not worker_info.empty:

            worker = worker_info.iloc[0]

            st.subheader(
                f"👷 {worker['name']}"
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Started Working",
                worker["start_date"]
                if pd.notna(worker["start_date"])
                else "Not Set"
            )

            c2.metric(
                "Total Worked Days",
                f"{summary['worked_days']:.1f}"
            )

            c3.metric(
                "Total OT Hours",
                f"{summary['ot_hours']:.1f}"
            )

            c4.metric(
                "Leave Days",
                summary["leave_days"]
            )

        # ----------------------------------------------------
        # WORK RECORDS
        # ----------------------------------------------------

        worker_logs = run_query("""
            SELECT
                log_id AS 'Log ID',
                work_date AS 'Date',
                days_worked AS 'Days Worked',
                ot_hours AS 'OT Hours',
                ot_notes AS 'OT Details',
                remarks AS 'Remarks'
            FROM logs
            WHERE worker_id = ?
            AND work_date BETWEEN ? AND ?
            ORDER BY work_date
        """, (
            worker_id,
            start_month.strftime("%Y-%m-%d"),
            end_month.strftime("%Y-%m-%d")
        ))

        st.markdown("---")

        st.subheader(
            f"📅 Work Days - {month_display(selected_month)}"
        )

        st.dataframe(
            worker_logs,
            use_container_width=True
        )

        # ----------------------------------------------------
        # LEAVES
        # ----------------------------------------------------

        worker_leaves = run_query("""
            SELECT
                leave_date AS 'Date',
                leave_type AS 'Leave Type',
                reason AS 'Reason'
            FROM leaves
            WHERE worker_id = ?
            AND leave_date BETWEEN ? AND ?
            ORDER BY leave_date
        """, (
            worker_id,
            start_month.strftime("%Y-%m-%d"),
            end_month.strftime("%Y-%m-%d")
        ))

        st.subheader("🌴 Holidays / Leaves")

        st.dataframe(
            worker_leaves,
            use_container_width=True
        )

        # ----------------------------------------------------
        # SHOP ITEMS
        # ----------------------------------------------------

        worker_items = run_query("""
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
            start_month.strftime("%Y-%m-%d"),
            end_month.strftime("%Y-%m-%d")
        ))

        st.subheader("🛒 Money / Items Taken")

        st.dataframe(
            worker_items,
            use_container_width=True
        )

        # ----------------------------------------------------
        # FINANCIAL RECORD
        # ----------------------------------------------------

        worker_financial = run_query("""
            SELECT
                daily_wage AS 'Daily Wage',
                total_worked_days AS 'Worked Days',
                total_ot_hours AS 'OT Hours',
                ot_rate_per_hour AS 'OT Rate/Hr',
                total_earned AS 'Total Earned',
                taken_money AS 'Advance Taken',
                shop_deduction AS 'Shop Deduction',
                received_money AS 'Money Paid',
                remaining_due AS 'Remaining Due',
                status AS 'Status'
            FROM financials
            WHERE worker_id = ?
            AND month_key = ?
        """, (
            worker_id,
            selected_month
        ))

        st.subheader("💰 Monthly Financial Record")

        if worker_financial.empty:

            st.info(
                "No monthly financial payout has been saved yet."
            )

        else:

            st.dataframe(
                worker_financial,
                use_container_width=True
            )
