import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import io

# --- DATABASE INITIALISATIE ---
def init_db():
    conn = sqlite3.connect("finance.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY, date TEXT, type TEXT, 
                  amount REAL, description TEXT, category TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS categories (name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT UNIQUE, value REAL)')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("start_balance", 0.0)')
    for cat in ["Loon", "Boodschappen", "Huur", "Vrije tijd"]:
        c.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))
    conn.commit()
    return conn

conn = init_db()
c = conn.cursor()

# --- HELPER FUNCTIES ---
def get_start_balance():
    c.execute('SELECT value FROM settings WHERE key="start_balance"')
    res = c.fetchone()
    return res[0] if res else 0.0

def update_start_balance(new_val):
    c.execute('UPDATE settings SET value = ? WHERE key="start_balance"', (new_val,))
    conn.commit()

def get_all_transactions():
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date ASC", conn)
    start_bal = get_start_balance()
    if not df.empty:
        df['Saldo'] = (start_bal + df['amount'].cumsum()).round(2)
    else:
        df = pd.DataFrame(columns=['id', 'date', 'type', 'amount', 'description', 'category', 'Saldo'])
    return df

# --- STREAMLIT UI CONFIG ---
st.set_page_config(page_title="Budgetprogramma Heugeu Patrick", layout="wide")
st.title("💰 BUDGETPROGRAMMA VAN HEUGEU PATRICK")

# Session State voor bewerk-modus
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

# HOOFDMENU (ZONDER GRAFIEK)
menu = ["🏠 Dashboard", "📝 Transacties", "📁 Categorieën", "📄 PDF Export"]
choice = st.sidebar.selectbox("Navigatie", menu)

# --- DASHBOARD / STARTSALDO ---
if choice == "🏠 Dashboard":
    st.subheader("Instellingen")
    current_start = get_start_balance()
    new_start = st.number_input("Huidig Startsaldo (€)", value=float(current_start), step=10.0, format="%.2f")
    if st.button("Startsaldo Bijwerken"):
        update_start_balance(new_start)
        st.success("Startsaldo aangepast!")
    
    df = get_all_transactions()
    current_total = df['Saldo'].iloc[-1] if not df.empty else current_start
    st.metric("Totaal Saldo (incl. toekomst)", f"€ {current_total:.2f}")

# --- TRANSACTIES ---
elif choice == "📝 Transacties":
    df = get_all_transactions()
    
    # MODUS BEPALEN (Nieuw vs Bewerken)
    if st.session_state.editing_id:
        st.subheader(f"📝 Transactie wijzigen (ID: {st.session_state.editing_id})")
        edit_data = df[df['id'] == st.session_state.editing_id].iloc[0]
        default_date = datetime.strptime(edit_data['date'], "%Y-%m-%d")
        default_type = edit_data['type']
        default_amt = abs(edit_data['amount'])
        default_cat = edit_data['category']
        default_desc = edit_data['description']
        button_label = "💾 Wijzigingen Opslaan"
    else:
        st.subheader("➕ Nieuwe Transactie toevoegen")
        default_date = datetime.now()
        default_type = "Uitgave"
        default_amt = 0.00
        default_cat = "Boodschappen"
        default_desc = ""
        button_label = "💾 Transactie Opslaan"

    # INVOERVELDEN
    col1, col2, col3 = st.columns(3)
    t_date = col1.date_input("Datum", default_date, key="in_date")
    t_type = col2.selectbox("Type", ["Inkomst", "Uitgave"], index=0 if default_type == "Inkomst" else 1, key="in_type")
    t_amt = col3.number_input("Bedrag (€)", min_value=0.00, step=0.01, format="%.2f", value=default_amt, key="in_amt")
    
    c.execute("SELECT name FROM categories")
    cats = [row[0]





