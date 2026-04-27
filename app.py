import streamlit as st
import sqlite3
import pandas as pd

# Database එක සම්බන්ධ කිරීම
def get_connection():
    conn = sqlite3.connect('business_pro.db', check_same_thread=False)
    return conn

conn = get_connection()
c = conn.cursor()

# මූලික Tables සකස් කිරීම
c.execute('CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY, shop_name TEXT, inv_no TEXT, bill_amt REAL, balance REAL)')
conn.commit()

st.set_page_config(page_title="My Business Web App", layout="centered")

st.title("💼 ව්‍යාපාරික කළමනාකරණ පද්ධතිය")

# පසෙකින් ඇති මෙනුව (Sidebar)
menu = ["Dashboard", "බිල්පත් ඇතුළත් කිරීම", "දත්ත බැලීම"]
choice = st.sidebar.selectbox("මෙනුව", menu)

if choice == "බිල්පත් ඇතුළත් කිරීම":
    st.subheader("අලුත් බිල්පතක් එක් කරන්න")
    with st.form("my_form"):
        shop = st.text_input("කඩේ නම")
        inv = st.text_input("Invoice අංකය")
        amount = st.number_input("මුදල", min_value=0.0)
        submit = st.form_submit_button("Save කරන්න")
        
        if submit:
            c.execute('INSERT INTO bills (shop_name, inv_no, bill_amt, balance) VALUES (?,?,?,?)', (shop, inv, amount, amount))
            conn.commit()
            st.success("දත්ත සාර්ථකව ඇතුළත් කළා!")

elif choice == "Dashboard":
    st.write("ඔබේ ව්‍යාපාරයේ වත්මන් තත්ත්වය මෙතැනින් බලන්න.")
    df = pd.read_sql_query("SELECT * FROM bills", conn)
    st.table(df)