import sqlite3
import pandas as pd
import streamlit as st

DB_FILE = "workshop.db"

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def safe_add_column(table_name, column_name, column_type):
    """Safely adds a missing column using PRAGMA inspection."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    cols = [c[1] for c in cursor.fetchall()]
    if column_name not in cols:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.close()

def repair_and_init_db():
    """Initializes tables and ensures schema integrity."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financials (
            payment_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            month_year TEXT NOT NULL,
            daily_wage REAL NOT NULL,
            days_worked REAL NOT NULL,
            ot_hours REAL DEFAULT 0.0,
            ot_rate_per_hour REAL DEFAULT 0.0,
            total_earned REAL NOT NULL,
            taken_money REAL NOT NULL,
            advance_reason TEXT,
            shop_deductions REAL DEFAULT 0.0,
            received_money REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (worker_id) REFERENCES workers (worker_id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

    # Explicitly attempt to add optional columns if missing
    safe_add_column("financials", "ot_hours", "REAL DEFAULT 0.0")
    safe_add_column("financials", "ot_rate_per_hour", "REAL DEFAULT 0.0")
    safe_add_column("financials", "shop_deductions", "REAL DEFAULT 0.0")

# Ensure schema runs on startup
repair_and_init_db()

def load_financials():
    """Loads financials dynamically without throwing DatabaseError on missing columns."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(financials)")
    cols = [c[1] for c in cursor.fetchall()]
    conn.close()

    # Dynamic column mapping to avoid SELECT execution errors
    ot_hrs_col = "f.ot_hours" if "ot_hours" in cols else "0.0"
    ot_rate_col = "f.ot_rate_per_hour" if "ot_rate_per_hour" in cols else "0.0"
    shop_ded_col = "f.shop_deductions" if "shop_deductions" in cols else "0.0"

    query = f"""
        SELECT f.payment_id AS 'Payment ID', f.worker_id AS 'Worker ID', w.name AS 'Worker Name',
               f.month_year AS 'Month', f.daily_wage AS 'Daily Wage (NPR)', 
               f.days_worked AS 'Net Days Worked', {ot_hrs_col} AS 'Total OT Hours',
               {ot_rate_col} AS 'OT Rate/Hr (NPR)', f.total_earned AS 'Total Earned (NPR)', 
               f.taken_money AS 'Advances (NPR)', {shop_ded_col} AS 'Shop Deductions (NPR)',
               f.received_money AS 'Paid Out (NPR)', f.status AS 'Status' 
        FROM financials f
        LEFT JOIN workers w ON f.worker_id = w.worker_id
    """
    return run_query(query)
