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
    cats = [row[0] for row in c.fetchall()]
    
    col4, col5 = st.columns([1, 2])
    try: cat_index = cats.index(default_cat)
    except: cat_index = 0
    t_cat = col4.selectbox("Categorie", cats, index=cat_index, key="in_cat")
    t_desc = col5.text_input("Omschrijving", value=default_desc, key="in_desc")
    
    col_btn1, col_btn2 = st.columns([1, 5])
    if col_btn1.button(button_label, type="primary"):
        if t_amt <= 0:
            st.error("Voer een bedrag hoger dan 0.00 in.")
        else:
            final_amt = t_amt if t_type == "Inkomst" else -t_amt
            if st.session_state.editing_id:
                c.execute("""UPDATE transactions SET date=?, type=?, amount=?, description=?, category=? WHERE id=?""",
                          (t_date.strftime("%Y-%m-%d"), t_type, round(final_amt, 2), t_desc, t_cat, st.session_state.editing_id))
                st.session_state.editing_id = None
                st.success("Transactie gewijzigd!")
            else:
                c.execute("INSERT INTO transactions (date, type, amount, description, category) VALUES (?,?,?,?,?)",
                          (t_date.strftime("%Y-%m-%d"), t_type, round(final_amt, 2), t_desc, t_cat))
                st.success("Transactie opgeslagen!")
            conn.commit()
            st.rerun()

    if st.session_state.editing_id:
        if col_btn2.button("❌ Annuleren"):
            st.session_state.editing_id = None
            st.rerun()

    st.divider()
    st.subheader("Historiek")
    if not df.empty:
        df_display = df.sort_values(by="date", ascending=False).copy()
        df_display['amount'] = df_display['amount'].map('{:,.2f}'.format)
        
        def color_saldo(val):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}'

        st.dataframe(df_display.style.applymap(color_saldo, subset=['Saldo']), use_container_width=True)
        
        st.divider()
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            selected_id = st.selectbox("Selecteer ID voor actie", df['id'].tolist(), key="select_id")
        with col_act2:
            st.write("Acties:")
            sub1, sub2 = st.columns(2)
            if sub1.button("✏️ Wijzig Transactie"):
                st.session_state.editing_id = selected_id
                st.rerun()
            if sub2.button("🗑️ Verwijder Transactie"):
                c.execute("DELETE FROM transactions WHERE id = ?", (selected_id,))
                conn.commit()
                st.warning(f"Transactie {selected_id} verwijderd.")
                st.rerun()

# --- CATEGORIEËN ---
elif choice == "📁 Categorieën":
    st.subheader("Categoriebeheer")
    new_cat = st.text_input("Nieuwe Categorie Naam")
    if st.button("Toevoegen"):
        if new_cat:
            try:
                c.execute("INSERT INTO categories (name) VALUES (?)", (new_cat,))
                conn.commit()
                st.success(f"Categorie '{new_cat}' toegevoegd!")
                st.rerun()
            except: st.error("Deze categorie bestaat al.")

    st.write("Bestaande categorieën:")
    c.execute("SELECT name FROM categories")
    for row in c.fetchall():
        col1, col2 = st.columns([3, 1])
        col1.write(row[0])
        c.execute("SELECT COUNT(*) FROM transactions WHERE category = ?", (row[0],))
        count = c.fetchone()[0]
        if count == 0:
            if col2.button("Verwijder", key=f"del_{row[0]}"):
                c.execute("DELETE FROM categories WHERE name = ?", (row[0],))
                conn.commit()
                st.rerun()
        else: col2.write(f"({count} items)")

# --- PDF EXPORT ---
elif choice == "📄 PDF Export":
    st.subheader("Exporteer naar PDF")
    col_p1, col_p2 = st.columns(2)
    pdf_date = col_p1.date_input("Startdatum PDF", datetime.now().date())
    pdf_months = col_p2.selectbox("Aantal maanden", [1, 2, 3, 4])
    
    if st.button("📥 Genereer PDF Overzicht"):
        df = get_all_transactions()
        if not df.empty:
            df['date_dt'] = pd.to_datetime(df['date']).dt.date
            today = datetime.now().date()
            end_pdf = pdf_date + timedelta(days=30 * pdf_months)
            mask = (df['date_dt'] >= pdf_date) & (df['date_dt'] <= end_pdf)
            pdf_df = df.loc[mask].sort_values(by="date", ascending=False)
            
            if not pdf_df.empty:
                buffer = io.BytesIO()
                p = canvas.Canvas(buffer, pagesize=letter)
                p.setFont("Helvetica-Bold", 14)
                p.drawString(50, 750, "Financieel Overzicht - Patrick")
                p.setFont("Helvetica", 10)
                p.drawString(50, 735, "VET = verleden/vandaag | CURSIEF = toekomst")
                y = 710
                p.setFont("Helvetica-Bold", 9)
                p.drawString(50, y, "Datum"); p.drawString(120, y, "Type"); p.drawString(180, y, "Omschrijving"); p.drawString(380, y, "Bedrag"); p.drawString(480, y, "Saldo")
                p.line(50, y-2, 550, y-2)
                for _, row in pdf_df.iterrows():
                    y -= 20
                    if y < 50: p.showPage(); y = 750
                    p.setFont("Helvetica-Oblique" if row['date_dt'] > today else "Helvetica-Bold", 9)
                    p.drawString(50, y, str(row['date']))
                    p.drawString(120, y, str(row['type']))
                    desc = (str(row['description'])[:35] + '..') if len(str(row['description'])) > 35 else str(row['description'])
                    p.drawString(180, y, desc)
                    p.drawString(380, y, f"€{row['amount']:.2f}")
                    p.setFillColor(colors.red if row['Saldo'] < 0 else colors.green)
                    p.drawString(480, y, f"€{row['Saldo']:.2f}")
                    p.setFillColor(colors.black)
                p.showPage(); p.save()
                st.download_button("Download PDF", data=buffer.getvalue(), file_name="overzicht_patrick.pdf", mime="application/pdf")
            else: st.warning("Geen transacties gevonden voor deze periode.")






