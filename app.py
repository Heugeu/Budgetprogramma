import streamlit as st
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
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
    # Standaard categorieën
    for cat in ["Loon", "Boodschappen", "Huur", "Vrije tijd"]:
        c.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))
    conn.commit()
    return conn

conn = init_db()
c = conn.cursor()

# --- HELPER FUNCTIES ---
def get_start_balance():
    c.execute('SELECT value FROM settings WHERE key="start_balance"')
    return c.fetchone()[0]

def update_start_balance(new_val):
    c.execute('UPDATE settings SET value = ? WHERE key="start_balance"', (new_val,))
    conn.commit()

def get_all_transactions():
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date ASC", conn)
    start_bal = get_start_balance()
    # Bereken lopend saldo
    df['Saldo'] = start_bal + df['amount'].cumsum()
    return df

# --- STREAMLIT UI ---
st.set_page_config(page_title="Budgetprogramma Heugeu Patrick", layout="wide")
st.title("💰 BUDGETPROGRAMMA VAN HEUGEU PATRICK")

menu = ["🏠 Dashboard", "📝 Transacties", "📁 Categorieën", "📊 Grafiek", "📄 PDF Export"]
choice = st.sidebar.selectbox("Navigatie", menu)

# --- DASHBOARD / STARTSALDO ---
if choice == "🏠 Dashboard":
    st.subheader("Instellingen")
    current_start = get_start_balance()
    new_start = st.number_input("Huidig Startsaldo (€)", value=float(current_start), step=10.0)
    if st.button("Startsaldo Bijwerken"):
        update_start_balance(new_start)
        st.success("Startsaldo aangepast!")
    
    df = get_all_transactions()
    current_total = df['Saldo'].iloc[-1] if not df.empty else current_start
    st.metric("Totaal Saldo (incl. toekomst)", f"€ {current_total:.2f}")

# --- TRANSACTIES ---
elif choice == "📝 Transacties":
    st.subheader("Nieuwe Transactie Toevoegen")
    with st.form("trans_form"):
        col1, col2, col3 = st.columns(3)
        t_date = col1.date_input("Datum", datetime.now())
        t_type = col2.selectbox("Type", ["Inkomst", "Uitgave"])
        t_amt = col3.number_input("Bedrag", min_value=0.01, step=0.01)
        
        c.execute("SELECT name FROM categories")
        cats = [row[0] for row in c.fetchall()]
        t_cat = st.selectbox("Categorie", cats)
        t_desc = st.text_input("Omschrijving")
        
        if st.form_submit_button("Opslaan"):
            final_amt = t_amt if t_type == "Inkomst" else -t_amt
            c.execute("INSERT INTO transactions (date, type, amount, description, category) VALUES (?,?,?,?,?)",
                      (t_date.strftime("%Y-%m-%d"), t_type, final_amt, t_desc, t_cat))
            conn.commit()
            st.success("Transactie opgeslagen!")

    st.subheader("Historiek")
    df = get_all_transactions()
    if not df.empty:
        # Omgekeerde volgorde voor weergave
        df_display = df.sort_values(by="date", ascending=False).copy()
        
        # Kleurstyling functie
        def color_saldo(val):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}'

        st.dataframe(df_display.style.applymap(color_saldo, subset=['Saldo']))
        
        # Verwijderen sectie
        st.divider()
        trans_to_del = st.selectbox("Selecteer ID om te verwijderen", df['id'].tolist())
        if st.button("Verwijder Transactie"):
            c.execute("DELETE FROM transactions WHERE id = ?", (trans_to_del,))
            conn.commit()
            st.warning(f"Transactie {trans_to_del} verwijderd.")
            st.rerun()

# --- CATEGORIEËN ---
elif choice == "📁 Categorieën":
    st.subheader("Categoriebeheer")
    new_cat = st.text_input("Nieuwe Categorie Naam")
    if st.button("Toevoegen"):
        try:
            c.execute("INSERT INTO categories (name) VALUES (?)", (new_cat,))
            conn.commit()
            st.success("Toegevoegd!")
        except:
            st.error("Categorie bestaat al.")

    st.write("Bestaande categorieën:")
    c.execute("SELECT name FROM categories")
    for row in c.fetchall():
        col1, col2 = st.columns([3, 1])
        col1.write(row[0])
        # Check of cat gebruikt wordt
        c.execute("SELECT COUNT(*) FROM transactions WHERE category = ?", (row[0],))
        if c.fetchone()[0] == 0:
            if col2.button("Verwijder", key=row[0]):
                c.execute("DELETE FROM categories WHERE name = ?", (row[0],))
                conn.commit()
                st.rerun()

# --- GRAFIEK ---
elif choice == "📊 Grafiek":
    st.subheader("Saldo Verloop")
    months = st.radio("Periode (maanden)", [1, 2, 3, 4], horizontal=True)
    start_date = st.date_input("Startdatum grafiek", datetime.now().replace(day=1))
    end_date = start_date + timedelta(days=30 * months)
    
    df = get_all_transactions()
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        mask = (df['date'] >= pd.Timestamp(start_date)) & (df['date'] <= pd.Timestamp(end_date))
        filtered_df = df.loc[mask]
        
        if not filtered_df.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(filtered_df['date'], filtered_df['Saldo'], marker='o', color='blue')
            ax.fill_between(filtered_df['date'], filtered_df['Saldo'], 0, 
                            where=(filtered_df['Saldo'] >= 0), color='green', alpha=0.3)
            ax.fill_between(filtered_df['date'], filtered_df['Saldo'], 0, 
                            where=(filtered_df['Saldo'] < 0), color='red', alpha=0.3)
            ax.axhline(0, color='black', linewidth=1)
            plt.xticks(rotation=45)
            st.pyplot(fig)
        else:
            st.info("Geen data voor deze periode.")

# --- PDF EXPORT ---
elif choice == "📄 PDF Export":
    st.subheader("Exporteer naar PDF")
    pdf_date = st.date_input("Startdatum PDF", datetime.now().replace(day=1))
    pdf_months = st.selectbox("Aantal maanden", [1, 2, 3, 4])
    
    if st.button("Genereer PDF"):
        df = get_all_transactions()
        df['date'] = pd.to_datetime(df['date'])
        end_pdf = pd.Timestamp(pdf_date) + timedelta(days=30 * pdf_months)
        mask = (df['date'] >= pd.Timestamp(pdf_date)) & (df['date'] <= end_pdf)
        pdf_df = df.loc[mask].sort_values(by="date", ascending=False)
        
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, 750, "Financieel Overzicht - Patrick")
        
        y = 710
        p.setFont("Helvetica-Bold", 10)
        p.drawString(50, y, "Datum")
        p.drawString(150, y, "Type")
        p.drawString(250, y, "Bedrag")
        p.drawString(350, y, "Saldo")
        
        p.setFont("Helvetica", 10)
        for index, row in pdf_df.iterrows():
            y -= 20
            p.drawString(50, y, str(row['date'].date()))
            p.drawString(150, y, row['type'])
            p.drawString(250, y, f"€{row['amount']:.2f}")
            
            if row['Saldo'] < 0: p.setFillColor(colors.red)
            else: p.setFillColor(colors.green)
            
            p.drawString(350, y, f"€{row['Saldo']:.2f}")
            p.setFillColor(colors.black)
            
            if y < 50:
                p.showPage()
                y = 750

        p.save()
        st.download_button("Download PDF", data=buffer.getvalue(), file_name="overzicht.pdf", mime="application/pdf")