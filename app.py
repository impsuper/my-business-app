import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- DATABASE සම්බන්ධතාවය ---
def get_connection():
    conn = sqlite3.connect('business_pro.db', check_same_thread=False)
    return conn

conn = get_connection()
c = conn.cursor()

# --- අවශ්‍ය වගු (Tables) පරීක්ෂා කිරීම ---
def init_db():
    c.execute('''CREATE TABLE IF NOT EXISTS bills 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, system_date TEXT, inv_date TEXT, del_date TEXT, 
                 shop_name TEXT, sales_ref TEXT, town TEXT, inv_no TEXT, bill_amt REAL, paid_amt REAL, balance REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS cheques
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, received_date TEXT, shop_name TEXT, 
                  bank TEXT, chq_no TEXT, amount REAL, status TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sales_reps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    conn.commit()

init_db()

# --- UI සැකසුම් ---
st.set_page_config(page_title="Business Pro Web", layout="wide")

# මොබයිල් එකේදී පෙනෙන ආකාරය හැඩගැස්වීමට CSS
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    @media (max-width: 600px) {
        .stDataFrame { width: 100% !important; }
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 Business Pro Management")

# --- පැති මෙනුව (Sidebar) ---
menu = ["Dashboard", "බිල්පත් (Bills)", "චෙක්පත් (Cheques)", "අලෙවි නියෝජිතයන් (Reps)"]
choice = st.sidebar.selectbox("ප්‍රධාන මෙනුව", menu)

# --- 1. DASHBOARD ---
if choice == "Dashboard":
    st.subheader("ව්‍යාපාරික සාරාංශය")
    
    col1, col2, col3 = st.columns(3)
    
    # දත්ත ගණනය කිරීම
    total_bills = pd.read_sql_query("SELECT SUM(bill_amt) FROM bills", conn).iloc[0,0] or 0
    total_balance = pd.read_sql_query("SELECT SUM(balance) FROM bills", conn).iloc[0,0] or 0
    total_cheques = pd.read_sql_query("SELECT SUM(amount) FROM cheques WHERE status='Received'", conn).iloc[0,0] or 0

    col1.metric("මුළු බිල්පත් වටිනාකම", f"Rs. {total_bills:,.2f}")
    col2.metric("ඉතිරි මුදල (Total Balance)", f"Rs. {total_balance:,.2f}", delta_color="inverse")
    col3.metric("අතේ ඇති චෙක්පත්", f"Rs. {total_cheques:,.2f}")

# --- 2. BILLS MANAGEMENT ---
elif choice == "බිල්පත් (Bills)":
    tab1, tab2 = st.tabs(["නව බිල්පතක්", "සියලුම බිල්පත්"])
    
    with tab1:
        st.write("අලුත් බිල්පතක් ඇතුළත් කරන්න")
        with st.form("bill_form", clear_on_submit=True):
            shop = st.text_input("කඩේ නම (Shop Name)")
            inv_no = st.text_input("Invoice අංකය")
            amount = st.number_input("මුළු මුදල", min_value=0.0)
            date = st.date_input("දිනය", datetime.now())
            
            submitted = st.form_submit_button("Save කරන්න")
            if submitted:
                c.execute('''INSERT INTO bills (system_date, inv_date, shop_name, inv_no, bill_amt, paid_amt, balance) 
                             VALUES (?,?,?,?,?,?,?)''', 
                          (datetime.now().strftime("%Y-%m-%d"), str(date), shop, inv_no, amount, 0, amount))
                conn.commit()
                st.success("බිල්පත සාර්ථකව ඇතුළත් කළා!")

    with tab2:
        df_bills = pd.read_sql_query("SELECT id, inv_date, shop_name, inv_no, bill_amt, balance FROM bills", conn)
        st.dataframe(df_bills, use_container_width=True)

# --- 3. CHEQUE MANAGEMENT ---
elif choice == "චෙක්පත් (Cheques)":
    st.subheader("චෙක්පත් කළමනාකරණය")
    with st.expander("නව චෙක්පතක් ඇතුළත් කරන්න"):
        with st.form("cheque_form"):
            c_shop = st.text_input("කඩේ නම")
            c_bank = st.text_input("බැංකුව")
            c_no = st.text_input("චෙක් අංකය")
            c_amt = st.number_input("මුදල", min_value=0.0)
            c_date = st.date_input("ලැබුණු දිනය")
            
            if st.form_submit_button("Save Cheque"):
                c.execute("INSERT INTO cheques (received_date, shop_name, bank, chq_no, amount, status) VALUES (?,?,?,?,?,?)",
                          (str(c_date), c_shop, c_bank, c_no, c_amt, 'Received'))
                conn.commit()
                st.info("චෙක්පත ඇතුළත් කළා.")

    df_chq = pd.read_sql_query("SELECT * FROM cheques", conn)
    st.table(df_chq)

# --- 4. SALES REPS ---
elif choice == "අලෙවි නියෝජිතයන් (Reps)":
    st.subheader("Sales Representatives")
    new_rep = st.text_input("නියෝජිතයෙකුගේ නම")
    if st.button("Add Rep"):
        try:
            c.execute("INSERT INTO sales_reps (name) VALUES (?)", (new_rep,))
            conn.commit()
            st.success(f"{new_rep} එකතු කළා!")
        except:
            st.error("මෙම නම දැනටමත් පවතී.")
    
    reps = pd.read_sql_query("SELECT name FROM sales_reps", conn)
    st.write(reps)