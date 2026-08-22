code = r'''import streamlit as st
import pandas as pd
from datetime import date, datetime
import calendar
import sqlite3
import io

st.set_page_config(page_title="Furniture Workshop Tracker", layout="wide")
st.title("🪚 Permanent Furniture Workshop Record System")
DB_FILE = "workshop.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def add_column_if_missing(cur, table, column, definition):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS workers(
            worker_id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT,
            skill TEXT, start_date TEXT, active INTEGER DEFAULT 1)""")
        add_column_if_missing(c, "workers", "start_date", "TEXT")
        add_column_if_missing(c, "workers", "active", "INTEGER DEFAULT 1")

        c.execute("""CREATE TABLE IF NOT EXISTS logs(
            log_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, work_date TEXT NOT NULL,
            work_status TEXT DEFAULT 'Full Day', worked_value REAL DEFAULT 1.0,
            ot_done INTEGER DEFAULT 0, ot_money REAL DEFAULT 0.0,
            ot_notes TEXT, remarks TEXT,
            UNIQUE(worker_id, work_date),
            FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE)""")
        for col, definition in [
            ("work_status","TEXT DEFAULT 'Full Day'"), ("worked_value","REAL DEFAULT 1.0"),
            ("ot_done","INTEGER DEFAULT 0"), ("ot_money","REAL DEFAULT 0.0"),
            ("ot_notes","TEXT"), ("remarks","TEXT")]:
            add_column_if_missing(c, "logs", col, definition)

        c.execute("""CREATE TABLE IF NOT EXISTS leaves(
            leave_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, leave_date TEXT NOT NULL,
            leave_type TEXT NOT NULL, reason TEXT,
            UNIQUE(worker_id, leave_date),
            FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE)""")

        c.execute("""CREATE TABLE IF NOT EXISTS shop_consumption(
            item_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, entry_date TEXT NOT NULL,
            item_name TEXT NOT NULL, item_cost REAL NOT NULL, notes TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE)""")

        c.execute("""CREATE TABLE IF NOT EXISTS advances(
            advance_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, advance_date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0, reason TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE)""")

        c.execute("""CREATE TABLE IF NOT EXISTS payments(
            payment_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, payment_date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0, notes TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE)""")

        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='financials'").fetchone()
        if exists:
            cols = [r[1] for r in c.execute("PRAGMA table_info(financials)").fetchall()]
            if "worker_id" not in cols or "month_key" not in cols:
                backup = "financials_old_backup"
                if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (backup,)).fetchone():
                    c.execute("ALTER TABLE financials RENAME TO financials_old_backup")
                else:
                    c.execute("DROP TABLE financials")

        c.execute("""CREATE TABLE IF NOT EXISTS financials(
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
            FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE CASCADE)""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_logs_worker_date ON logs(worker_id, work_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_leave_worker_date ON leaves(worker_id, leave_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_fin_worker_month ON financials(worker_id, month_key)")
        conn.commit()

def run_query(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def run_action(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()

def get_next_id(prefix, table, col):
    df = run_query(f"SELECT {col} FROM {table}")
    nums = []
    for v in ([] if df.empty else df[col].dropna().astype(str).tolist()):
        digits = "".join(ch for ch in v if ch.isdigit())
        if digits: nums.append(int(digits))
    return f"{prefix}{(max(nums)+1 if nums else 1):03d}"

def month_bounds(month_key):
    y, m = map(int, month_key.split("-"))
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{calendar.monthrange(y,m)[1]:02d}"

def month_label(month_key):
    y, m = map(int, month_key.split("-"))
    return f"{calendar.month_name[m]} {y}"

def load_workers():
    return run_query("""SELECT worker_id AS 'Worker ID', name AS 'Name', phone AS 'Phone',
                        skill AS 'Skill', start_date AS 'Started Work'
                        FROM workers WHERE active=1 ORDER BY name""")

def load_logs():
    return run_query("""SELECT l.log_id AS 'Log ID', l.worker_id AS 'Worker ID',
        w.name AS 'Worker Name', l.work_date AS 'Date', l.work_status AS 'Work Type',
        l.worked_value AS 'Worked Days', l.ot_done AS 'OT Done',
        l.ot_money AS 'OT Money (NPR)', l.ot_notes AS 'OT Details',
        l.remarks AS 'Remarks'
        FROM logs l LEFT JOIN workers w ON l.worker_id=w.worker_id
        ORDER BY l.work_date DESC, w.name""")

def load_leaves():
    return run_query("""SELECT l.leave_id AS 'Leave ID', l.worker_id AS 'Worker ID',
        w.name AS 'Worker Name', l.leave_date AS 'Leave Date',
        l.leave_type AS 'Leave Type', l.reason AS 'Reason'
        FROM leaves l LEFT JOIN workers w ON l.worker_id=w.worker_id
        ORDER BY l.leave_date DESC, w.name""")

def load_consumption():
    return run_query("""SELECT s.item_id AS 'Item ID', s.worker_id AS 'Worker ID',
        w.name AS 'Worker Name', s.entry_date AS 'Date',
        s.item_name AS 'Item Consumed', s.item_cost AS 'Cost (NPR)', s.notes AS 'Notes'
        FROM shop_consumption s LEFT JOIN workers w ON s.worker_id=w.worker_id
        ORDER BY s.entry_date DESC, w.name""")

def load_advances():
    return run_query("""SELECT a.advance_id AS 'Advance ID', a.worker_id AS 'Worker ID',
        w.name AS 'Worker Name', a.advance_date AS 'Date',
        a.amount AS 'Amount (NPR)', a.reason AS 'Reason'
        FROM advances a LEFT JOIN workers w ON a.worker_id=w.worker_id
        ORDER BY a.advance_date DESC, w.name""")

def load_payments():
    return run_query("""SELECT p.payment_id AS 'Payment ID', p.worker_id AS 'Worker ID',
        w.name AS 'Worker Name', p.payment_date AS 'Date',
        p.amount AS 'Amount (NPR)', p.notes AS 'Notes'
        FROM payments p LEFT JOIN workers w ON p.worker_id=w.worker_id
        ORDER BY p.payment_date DESC, w.name""")

def load_financials():
    return run_query("""SELECT f.payment_id AS 'Payment ID', f.worker_id AS 'Worker ID',
        w.name AS 'Worker Name', f.month_key AS 'Month Key',
        f.daily_wage AS 'Daily Wage (NPR)', f.total_worked_days AS 'Total Worked Days',
        f.total_ot_money AS 'Total OT Money (NPR)', f.total_earned AS 'Total Earned (NPR)',
        f.total_advance AS 'Money Taken / Advance (NPR)',
        f.total_shop_deduction AS 'Shop Deduction (NPR)',
        f.total_paid AS 'Total Paid (NPR)', f.remaining_due AS 'Remaining Due (NPR)',
        f.status AS 'Status'
        FROM financials f LEFT JOIN workers w ON f.worker_id=w.worker_id
        ORDER BY f.month_key DESC, w.name""")

def monthly_summary(worker_id, month_key):
    start, end = month_bounds(month_key)
    work = run_query("""SELECT COALESCE(SUM(worked_value),0) AS v,
                        COALESCE(SUM(ot_money),0) AS ot
                        FROM logs WHERE worker_id=? AND work_date BETWEEN ? AND ?""",
                     (worker_id, start, end)).iloc[0]
    leaves = run_query("""SELECT COUNT(*) AS c FROM leaves
                          WHERE worker_id=? AND leave_date BETWEEN ? AND ?""",
                       (worker_id, start, end)).iloc[0]["c"]
    adv = run_query("""SELECT COALESCE(SUM(amount),0) AS v FROM advances
                       WHERE worker_id=? AND advance_date BETWEEN ? AND ?""",
                    (worker_id, start, end)).iloc[0]["v"]
    shop = run_query("""SELECT COALESCE(SUM(item_cost),0) AS v FROM shop_consumption
                        WHERE worker_id=? AND entry_date BETWEEN ? AND ?""",
                     (worker_id, start, end)).iloc[0]["v"]
    paid = run_query("""SELECT COALESCE(SUM(amount),0) AS v FROM payments
                        WHERE worker_id=? AND payment_date BETWEEN ? AND ?""",
                     (worker_id, start, end)).iloc[0]["v"]
    return {
        "worked_days": float(work["v"]), "ot_money": float(work["ot"]),
        "leave_days": int(leaves), "advance": float(adv),
        "shop": float(shop), "paid": float(paid)
    }

def save_monthly_financial(worker_id, month_key, daily_wage):
    s = monthly_summary(worker_id, month_key)
    earned = s["worked_days"] * float(daily_wage) + s["ot_money"]
    due = earned - s["advance"] - s["shop"] - s["paid"]
    status = "Fully Settled" if due <= 0 else ("Partially Paid" if s["paid"] > 0 or s["advance"] > 0 else "Unpaid")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = run_query("SELECT payment_id FROM financials WHERE worker_id=? AND month_key=?",
                         (worker_id, month_key))
    if existing.empty:
        pid = get_next_id("P", "financials", "payment_id")
        run_action("""INSERT INTO financials(
            payment_id,worker_id,month_key,daily_wage,total_worked_days,total_ot_money,
            total_earned,total_advance,total_shop_deduction,total_paid,remaining_due,
            status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid,worker_id,month_key,daily_wage,s["worked_days"],s["ot_money"],earned,
             s["advance"],s["shop"],s["paid"],due,status,now,now))
    else:
        run_action("""UPDATE financials SET daily_wage=?,total_worked_days=?,total_ot_money=?,
            total_earned=?,total_advance=?,total_shop_deduction=?,total_paid=?,
            remaining_due=?,status=?,updated_at=?
            WHERE worker_id=? AND month_key=?""",
            (daily_wage,s["worked_days"],s["ot_money"],earned,s["advance"],s["shop"],
             s["paid"],due,status,now,worker_id,month_key))

init_db()
df_workers, df_logs, df_leaves = load_workers(), load_logs(), load_leaves()
df_consumption, df_advances, df_payments = load_consumption(), load_advances(), load_payments()
df_financials = load_financials()

def generate_excel():
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_workers.to_excel(writer, sheet_name="Workers", index=False)
        df_logs.to_excel(writer, sheet_name="Attendance", index=False)
        df_leaves.to_excel(writer, sheet_name="Leaves", index=False)
        df_consumption.to_excel(writer, sheet_name="Shop", index=False)
        df_advances.to_excel(writer, sheet_name="Advances", index=False)
        df_payments.to_excel(writer, sheet_name="Payments", index=False)
        df_financials.to_excel(writer, sheet_name="Monthly Financials", index=False)
    return out.getvalue()

st.sidebar.header("📍 Navigation")
menu = st.sidebar.radio("Go to:", [
    "📊 Dashboard & Monthly View", "👥 Manage Workers", "📝 Log Daily Work & OT",
    "🌴 Manage Leaves & Holidays", "🛒 Shop Items Consumed",
    "💸 Money Taken / Advance", "💵 Worker Payments", "💰 Financial Payouts",
    "🔎 Search Worker Records"
])
st.sidebar.markdown("---")
st.sidebar.download_button("📥 Export All Data (Excel .xlsx)", generate_excel(),
    f"workshop_report_{date.today()}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True)

if menu == "📊 Dashboard & Monthly View":
    st.subheader("📊 Workshop Live Summary")
    total_earned = df_financials["Total Earned (NPR)"].sum() if not df_financials.empty else 0
    total_due = df_financials["Remaining Due (NPR)"].sum() if not df_financials.empty else 0
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("👷 Active Workers", len(df_workers))
    c2.metric("💰 Total Labor Bill", f"NPR {total_earned:,.2f}")
    c3.metric("⏰ Total OT", f"NPR {(df_financials['Total OT Money (NPR)'].sum() if not df_financials.empty else 0):,.2f}")
    c4.metric("📌 Remaining Due", f"NPR {total_due:,.2f}")
    if not df_logs.empty:
        months = sorted(pd.to_datetime(df_logs["Date"]).dt.strftime("%Y-%m").unique(), reverse=True)
        mk = st.selectbox("🗓️ Select Month", months, format_func=month_label)
        view = df_logs[pd.to_datetime(df_logs["Date"]).dt.strftime("%Y-%m")==mk]
        st.dataframe(view, use_container_width=True)
    else: st.info("No attendance records yet.")

elif menu == "👥 Manage Workers":
    st.subheader("👥 Workshop Carpentry Team")
    a,b = st.columns(2)
    with a:
        with st.form("worker", clear_on_submit=True):
            name=st.text_input("👤 Worker Full Name")
            phone=st.text_input("📱 Mobile Number")
            skill=st.selectbox("🛠️ Role",["Specialist Carpenter","Carver","Finisher / Polisher","Helper"])
            start=st.date_input("📅 Started Work",date.today())
            if st.form_submit_button("➕ Register Worker") and name.strip():
                run_action("INSERT INTO workers(worker_id,name,phone,skill,start_date) VALUES(?,?,?,?,?)",
                           (get_next_id("W","workers","worker_id"),name.strip(),phone,skill,start.isoformat()))
                st.success("✅ Worker added."); st.rerun()
    with b:
        if not df_workers.empty:
            choice=st.selectbox("🗑️ Select Worker to Delete",df_workers["Worker ID"]+" - "+df_workers["Name"])
            if st.button("❌ Delete Selected Worker",type="primary"):
                run_action("DELETE FROM workers WHERE worker_id=?",(choice.split(" - ")[0],))
                st.success("Deleted."); st.rerun()
    st.dataframe(load_workers(),use_container_width=True)

elif menu == "📝 Log Daily Work & OT":
    st.subheader("📝 Record Daily Work & OT")
    if df_workers.empty: st.warning("⚠️ Add a worker first.")
    else:
        with st.form("attendance",clear_on_submit=True):
            wc=st.selectbox("👷 Select Worker",df_workers["Worker ID"]+" - "+df_workers["Name"])
            wid=wc.split(" - ")[0]
            dates=st.date_input("📅 Select One or Multiple Work Dates",date.today())
            selected_dates=dates if isinstance(dates,tuple) else [dates]
            status=st.selectbox("🕘 Work Type",["Full Day","Half Day"])
            worked=1.0 if status=="Full Day" else 0.5
            ot=st.checkbox("⏰ Did the worker do OT?")
            ot_money=st.number_input("💵 OT Money (NPR)",0.0,step=50.0) if ot else 0.0
            ot_notes=st.text_input("📝 OT Details") if ot else ""
            remarks=st.text_input("💬 Remarks")
            if st.form_submit_button("💾 Save Work Record"):
                saved=0
                with get_connection() as conn:
                    for d in selected_dates:
                        ds=d.isoformat()
                        exists=conn.execute("SELECT 1 FROM logs WHERE worker_id=? AND work_date=?",(wid,ds)).fetchone()
                        if not exists:
                            lid=get_next_id("L","logs","log_id")
                            conn.execute("""INSERT INTO logs(log_id,worker_id,work_date,work_status,worked_value,
                                ot_done,ot_money,ot_notes,remarks) VALUES(?,?,?,?,?,?,?,?,?)""",
                                (lid,wid,ds,status,worked,int(ot),ot_money,ot_notes,remarks)); saved+=1
                    conn.commit()
                st.success(f"✅ Saved {saved} work date(s). Existing dates were kept unchanged.")
                st.rerun()
    st.dataframe(load_logs(),use_container_width=True)

elif menu == "🌴 Manage Leaves & Holidays":
    st.subheader("🌴 Worker Leaves & Holidays")
    if df_workers.empty: st.warning("⚠️ Add a worker first.")
    else:
        with st.form("leave",clear_on_submit=True):
            wc=st.selectbox("👷 Select Worker",df_workers["Worker ID"]+" - "+df_workers["Name"])
            d=st.date_input("📅 Leave Date",date.today())
            typ=st.selectbox("🌴 Leave Type",["Casual Leave","Sick Leave","Festival / Public Holiday","Unpaid Leave"])
            reason=st.text_input("💬 Reason")
            if st.form_submit_button("💾 Record Leave"):
                wid=wc.split(" - ")[0]
                try:
                    run_action("INSERT INTO leaves VALUES(?,?,?,?,?)",(get_next_id("LV","leaves","leave_id"),wid,d.isoformat(),typ,reason))
                    st.success("✅ Leave recorded."); st.rerun()
                except sqlite3.IntegrityError: st.warning("⚠️ A leave record already exists for this worker and date.")
    st.dataframe(load_leaves(),use_container_width=True)

elif menu == "🛒 Shop Items Consumed":
    st.subheader("🛒 Shop & Canteen Items")
    if df_workers.empty: st.warning("⚠️ Add a worker first.")
    else:
        with st.form("shop",clear_on_submit=True):
            wc=st.selectbox("👷 Select Worker",df_workers["Worker ID"]+" - "+df_workers["Name"])
            d=st.date_input("📅 Date",date.today()); item=st.text_input("🛒 Item")
            cost=st.number_input("💰 Cost (NPR)",0.0,step=10.0); notes=st.text_input("💬 Notes")
            if st.form_submit_button("💾 Record Item") and item.strip():
                run_action("INSERT INTO shop_consumption VALUES(?,?,?,?,?,?)",
                    (get_next_id("C","shop_consumption","item_id"),wc.split(" - ")[0],d.isoformat(),item,cost,notes))
                st.success("✅ Recorded."); st.rerun()
    st.dataframe(load_consumption(),use_container_width=True)

elif menu == "💸 Money Taken / Advance":
    st.subheader("💸 Money Taken / Advance")
    if df_workers.empty: st.warning("⚠️ Add a worker first.")
    else:
        with st.form("advance",clear_on_submit=True):
            wc=st.selectbox("👷 Select Worker",df_workers["Worker ID"]+" - "+df_workers["Name"])
            d=st.date_input("📅 Date",date.today()); amount=st.number_input("💸 Amount (NPR)",0.0,step=100.0)
            reason=st.text_input("📝 Reason")
            if st.form_submit_button("💾 Save Advance") and amount>0:
                run_action("INSERT INTO advances VALUES(?,?,?,?,?)",
                    (get_next_id("A","advances","advance_id"),wc.split(" - ")[0],d.isoformat(),amount,reason))
                st.success("✅ Advance recorded."); st.rerun()
    st.dataframe(load_advances(),use_container_width=True)

elif menu == "💵 Worker Payments":
    st.subheader("💵 Payment Made to Worker")
    if df_workers.empty: st.warning("⚠️ Add a worker first.")
    else:
        with st.form("payment",clear_on_submit=True):
            wc=st.selectbox("👷 Select Worker",df_workers["Worker ID"]+" - "+df_workers["Name"])
            d=st.date_input("📅 Payment Date",date.today()); amount=st.number_input("💵 Amount Paid (NPR)",0.0,step=100.0)
            notes=st.text_input("📝 Notes")
            if st.form_submit_button("💾 Save Payment") and amount>0:
                run_action("INSERT INTO payments VALUES(?,?,?,?,?)",
                    (get_next_id("PAY","payments","payment_id"),wc.split(" - ")[0],d.isoformat(),amount,notes))
                st.success("✅ Payment recorded."); st.rerun()
    st.dataframe(load_payments(),use_container_width=True)

elif menu == "💰 Financial Payouts":
    st.subheader("💰 Monthly Financial Payout Calculator")
    if df_workers.empty: st.warning("⚠️ Add a worker first.")
    else:
        wc=st.selectbox("🔎 Select Worker",df_workers["Worker ID"]+" - "+df_workers["Name"])
        wid=wc.split(" - ")[0]
        all_months=set(pd.date_range(date.today().replace(day=1), periods=1, freq="MS").strftime("%Y-%m"))
        if not df_logs.empty:
            all_months |= set(pd.to_datetime(df_logs[df_logs["Worker ID"]==wid]["Date"]).dt.strftime("%Y-%m"))
        mk=st.selectbox("🗓️ Select Month",sorted(all_months,reverse=True),format_func=month_label)
        old=run_query("SELECT daily_wage FROM financials WHERE worker_id=? AND month_key=?",(wid,mk))
        default=float(old.iloc[0,0]) if not old.empty else 1500.0
        wage=st.number_input("💰 Daily Wage (NPR)",0.0,value=default,step=100.0)
        s=monthly_summary(wid,mk)
        earned=s["worked_days"]*wage+s["ot_money"]; due=earned-s["advance"]-s["shop"]-s["paid"]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("📅 Worked Days",f"{s['worked_days']:.1f}")
        c2.metric("🌴 Leave Days",s["leave_days"])
        c3.metric("⏰ OT Money",f"NPR {s['ot_money']:,.2f}")
        c4.metric("📌 Remaining Due",f"NPR {due:,.2f}")
        st.info(f"🧮 Total Earned = ({s['worked_days']:.1f} × NPR {wage:,.2f}) + NPR {s['ot_money']:,.2f} = NPR {earned:,.2f}")
        if st.button("💾 Save / Update Monthly Financial Record",type="primary"):
            save_monthly_financial(wid,mk,wage)
            st.success("✅ Monthly financial record saved without duplicate records."); st.rerun()
    st.dataframe(load_financials(),use_container_width=True)

elif menu == "🔎 Search Worker Records":
    st.subheader("🔎 Search Complete Worker Records")
    if df_workers.empty: st.info("No workers found.")
    else:
        name=st.selectbox("👤 Search Worker by Name",df_workers["Name"])
        wid=df_workers[df_workers["Name"]==name]["Worker ID"].iloc[0]
        months=sorted(set(pd.to_datetime(df_logs[df_logs["Worker ID"]==wid]["Date"]).dt.strftime("%Y-%m")) if not df_logs.empty else [],reverse=True)
        if months:
            mk=st.selectbox("🗓️ Filter Month",months,format_func=month_label)
            start,end=month_bounds(mk)
        else: start,end="0000-01-01","9999-12-31"
        st.markdown("### 📝 Work Records")
        st.dataframe(run_query("SELECT * FROM logs WHERE worker_id=? AND work_date BETWEEN ? AND ? ORDER BY work_date",(wid,start,end)),use_container_width=True)
        st.markdown("### 🌴 Leave Records")
        st.dataframe(run_query("SELECT * FROM leaves WHERE worker_id=? AND leave_date BETWEEN ? AND ? ORDER BY leave_date",(wid,start,end)),use_container_width=True)
        st.markdown("### 💸 Money Taken")
        st.dataframe(run_query("SELECT * FROM advances WHERE worker_id=? AND advance_date BETWEEN ? AND ? ORDER BY advance_date",(wid,start,end)),use_container_width=True)
        st.markdown("### 💰 Monthly Financial Records")
        st.dataframe(run_query("SELECT * FROM financials WHERE worker_id=? ORDER BY month_key DESC",(wid,)),use_container_width=True)
'''
path="/mnt/data/streamlit_app.py"
open(path,"w",encoding="utf-8").write(code)
print(path)
