import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- DATABASE SETUP ---
def get_connection():
    conn = sqlite3.connect('business_pro.db', check_same_thread=False)
    return conn

conn = get_connection()
c = conn.cursor()

def init_db():
    # Bills Table
    c.execute('''CREATE TABLE IF NOT EXISTS bills 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, system_date TEXT, inv_date TEXT, del_date TEXT, 
                 shop_name TEXT, sales_ref TEXT, town TEXT, inv_no TEXT, bill_amt REAL, paid_amt REAL, balance REAL)''')
    # Cheques Table
    c.execute('''CREATE TABLE IF NOT EXISTS cheques
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, system_date TEXT, received_date TEXT, 
                  shop_name TEXT, town TEXT, bank TEXT, chq_no TEXT, amount REAL, status TEXT)''')
    # Sales Reps
    c.execute('''CREATE TABLE IF NOT EXISTS sales_reps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    # Payment History
    c.execute('''CREATE TABLE IF NOT EXISTS payment_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, bill_id INTEGER, amount REAL, pay_date TEXT)''')
    conn.commit()

init_db()

# --- APP CONFIG & STYLING ---
st.set_page_config(page_title="Business Pro - Mobile Web", layout="wide")

# Sidebar Menu
st.sidebar.title("📌 Main Menu")
menu = ["🏠 Dashboard", "📝 Bill Entry", "📜 View Bills", "🏦 Cheque Management", "👥 Sales Reps"]
choice = st.sidebar.radio("Go to", menu)

# --- HELPER FUNCTIONS ---
def get_reps():
    c.execute("SELECT name FROM sales_reps")
    return [r[0] for r in c.fetchall()]

# --- 1. DASHBOARD ---
if choice == "🏠 Dashboard":
    st.title("📊 Business Dashboard")
    
    # Calculate Summary
    total_sales = pd.read_sql_query("SELECT SUM(bill_amt) FROM bills", conn).iloc[0,0] or 0
    total_balance = pd.read_sql_query("SELECT SUM(balance) FROM bills", conn).iloc[0,0] or 0
    total_chq = pd.read_sql_query("SELECT SUM(amount) FROM cheques WHERE status='Received'", conn).iloc[0,0] or 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Sales", f"Rs. {total_sales:,.2f}")
    col2.metric("Outstanding Balance", f"Rs. {total_balance:,.2f}", delta_color="inverse")
    col3.metric("Pending Cheques", f"Rs. {total_chq:,.2f}")

    st.divider()
    st.subheader("Recent Bills")
    df_recent = pd.read_sql_query("SELECT shop_name, inv_no, balance FROM bills ORDER BY id DESC LIMIT 5", conn)
    st.table(df_recent)

# --- 2. BILL ENTRY ---
elif choice == "📝 Bill Entry":
    st.title("➕ New Bill Entry")
    reps = get_reps()
    
    with st.form("bill_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            shop = st.text_input("Shop Name")
            inv_no = st.text_input("Invoice Number")
            town = st.text_input("Town")
        with col2:
            amount = st.number_input("Total Amount", min_value=0.0)
            inv_date = st.date_input("Invoice Date")
            rep = st.selectbox("Sales Rep", reps if reps else ["No Reps Added"])
        
        submitted = st.form_submit_button("Save Bill")
        if submitted:
            now = datetime.now().strftime("%Y-%m-%d")
            c.execute('''INSERT INTO bills (system_date, inv_date, shop_name, sales_ref, town, inv_no, bill_amt, paid_amt, balance) 
                         VALUES (?,?,?,?,?,?,?,?,?)''', 
                      (now, str(inv_date), shop, rep, town, inv_no, amount, 0, amount))
            conn.commit()
            st.success("Bill saved successfully!")

# --- 3. VIEW BILLS & PAYMENTS ---
elif choice == "📜 View Bills":
    st.title("🔍 Search & Manage Bills")
    search_query = st.text_input("Search by Shop Name or Inv No")
    
    query = "SELECT * FROM bills"
    if search_query:
        query += f" WHERE shop_name LIKE '%{search_query}%' OR inv_no LIKE '%{search_query}%'"
    
    df = pd.read_sql_query(query, conn)
    
    for index, row in df.iterrows():
        with st.expander(f"{row['shop_name']} - {row['inv_no']} (Bal: Rs.{row['balance']})"):
            st.write(f"Date: {row['inv_date']} | Total: Rs.{row['bill_amt']}")
            
            # Payment Section
            if row['balance'] > 0:
                pay_amt = st.number_input(f"Pay Amount for {row['inv_no']}", min_value=0.0, max_value=row['balance'], key=f"pay_{row['id']}")
                if st.button(f"Update Payment", key=f"btn_{row['id']}"):
                    new_paid = row['paid_amt'] + pay_amt
                    new_bal = row['bill_amt'] - new_paid
                    c.execute("UPDATE bills SET paid_amt=?, balance=? WHERE id=?", (new_paid, new_bal, row['id']))
                    c.execute("INSERT INTO payment_history (bill_id, amount, pay_date) VALUES (?,?,?)", 
                              (row['id'], pay_amt, datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    st.rerun()

# --- 4. CHEQUE MANAGEMENT ---
elif choice == "🏦 Cheque Management":
    st.title("Cheque Management")
    tab1, tab2 = st.tabs(["Add Cheque", "View All Cheques"])
    
    with tab1:
        with st.form("chq_form"):
            c_shop = st.text_input("Shop Name")
            c_bank = st.text_input("Bank Name")
            c_no = st.text_input("Cheque Number")
            c_amt = st.number_input("Amount", min_value=0.0)
            c_date = st.date_input("Received Date")
            if st.form_submit_button("Save Cheque"):
                c.execute("INSERT INTO cheques (system_date, received_date, shop_name, bank, chq_no, amount, status) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d"), str(c_date), c_shop, c_bank, c_no, c_amt, 'Received'))
                conn.commit()
                st.success("Cheque added!")

    with tab2:
        status_filter = st.selectbox("Filter by Status", ["Received", "Banked", "Returned"])
        df_chq = pd.read_sql_query(f"SELECT * FROM cheques WHERE status='{status_filter}'", conn)
        st.dataframe(df_chq, use_container_width=True)

# --- 5. SALES REPS ---
elif choice == "👥 Sales Reps":
    st.title("Manage Sales Representatives")
    new_rep = st.text_input("Rep Name")
    if st.button("Add Representative"):
        try:
            c.execute("INSERT INTO sales_reps (name) VALUES (?)", (new_rep,))
            conn.commit()
            st.success("Rep added!")
        except:
            st.error("Already exists!")
    
    df_reps = pd.read_sql_query("SELECT * FROM sales_reps", conn)
    st.table(df_reps)