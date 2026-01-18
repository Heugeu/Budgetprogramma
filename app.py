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

menu = ["🏠 Dashboard", "📝 Transacties", "📁 Categorieën", "📊 Grafiek", "📄 PDF Export"]
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
    st.subheader("Nieuwe Transactie Toevoegen")
    col1, col2, col3 = st.columns(3)
    t_date = col1.date_input("Datum", datetime.now(), key="date")
    t_type = col2.selectbox("Type", ["Inkomst", "Uitgave"], key="type")
    t_amt = col3.number_input("Bedrag (€)", min_value=0.00, step=0.01, format="%.2f", value=0.00, key="amt")
    
    c.execute("SELECT name FROM categories")
    cats = [row[0] for row in c.fetchall()]
    
    col4, col5 = st.columns([1, 2])
    t_cat = col4.selectbox("Categorie", cats, key="cat")
    t_desc = col5.text_input("Omschrijving", key="desc")
    
    if st.button("💾 Transactie Opslaan"):
        if t_amt <= 0:
            st.error("Voer een bedrag hoger dan 0.00 in.")
        else:
            final_amt = t_amt if t_type == "Inkomst" else -t_amt
            c.execute("INSERT INTO transactions (date, type, amount, description, category) VALUES (?,?,?,?,?)",
                      (t_date.strftime("%Y-%m-%d"), t_type, round(final_amt, 2), t_desc, t_cat))
            conn.commit()
            st.success("Transactie opgeslagen!")
            st.rerun()

    st.divider()
    st.subheader("Historiek")
    df = get_all_transactions()
    if not df.empty:
        df_display = df.sort_values(by="date", ascending=False).copy()
        df_display['amount'] = df_display['amount'].map('{:,.2f}'.format)
        
        def color_saldo(val):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}'

        st.dataframe(df_display.style.applymap(color_saldo, subset=['Saldo']), use_container_width=True)
        
        st.divider()
        trans_to_del = st.selectbox("Selecteer ID om te verwijderen", df['id'].tolist())
        if st.button("🗑️ Verwijder Transactie"):
            c.execute("DELETE FROM transactions WHERE id = ?", (trans_to_del,))
            conn.commit()
            st.warning(f"Transactie {trans_to_del} verwijderd.")
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
            except:
                st.error("Deze categorie bestaat al.")

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
        else:
            col2.write(f"({count} items)")

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
            ax.plot(filtered_df['date'], filtered_df['Saldo'], marker='o', color='blue', linewidth=2)
            ax.fill_between(filtered_df['date'], filtered_df['Saldo'], 0, 
                            where=(filtered_df['Saldo'] >= 0), color='green', alpha=0.3)
            ax.fill_between(filtered_df['date'], filtered_df['Saldo'], 0, 
                            where=(filtered_df['Saldo'] < 0), color='red', alpha=0.3)
            ax.axhline(0, color='black', linewidth=1)
            plt.xticks(rotation=45)
            st.pyplot(fig)
        else:
            st.info("Geen data gevonden voor de geselecteerde periode.")

# --- PDF EXPORT (VERBETERDE VERSIE TEGEN RUNTIME ERROR) ---
elif choice == "📄 PDF Export":
    st.subheader("Exporteer naar PDF")
    col_p1, col_p2 = st.columns(2)
    pdf_date = col_p1.date_input("Startdatum PDF", datetime.now().replace(day=1))
    pdf_months = col_p2.selectbox("Aantal maanden", [1, 2, 3, 4])
    
    if st.button("📥 Genereer PDF Overzicht"):
        df = get_all_transactions()
        if not df.empty:
            # Datum conversies voor correcte vergelijking
            df['date_dt'] = pd.to_datetime(df['date']).dt.date
            today = datetime.now().date()
            end_pdf = pdf_date + timedelta(days=30 * pdf_months)
            
            mask = (df['date_dt'] >= pdf_date) & (df['date_dt'] <= end_pdf)
            pdf_df = df.loc[mask].sort_values(by="date", ascending=False)
            
            if pdf_df.empty:
                st.warning("Geen transacties gevonden voor de geselecteerde periode.")
            else:
                # PDF genereren in een buffer
                buffer = io.BytesIO()
                p = canvas.Canvas(buffer, pagesize=letter)
                
                # Titel en Legende
                p.setFont("Helvetica-Bold", 14)
                p.drawString(50, 750, f"Financieel Overzicht - Patrick")
                p.setFont("Helvetica", 10)
                p.drawString(50, 735, "Legende: VET = verleden/vandaag | CURSIEF = toekomst")
                
                # Header
                y = 710
                p.setFont("Helvetica-Bold", 9)
                p.drawString(50, y, "Datum")
                p.drawString(120, y, "Type")
                p.drawString(180, y, "Omschrijving")
                p.drawString(380, y, "Bedrag")
                p.drawString(480, y, "Saldo")
                p.line(50, y-2, 550, y-2)
                
                for index, row in pdf_df.iterrows():
                    y -= 20
                    # Check voor pagina-einde
                    if y < 50:
                        p.showPage()
                        y = 750
                    
                    is_future = row['date_dt'] > today
                    
                    # Kies stijl: Helvetica-Bold (Vet) of Helvetica-Oblique (Cursief)
                    current_font = "Helvetica-Oblique" if is_future else "Helvetica-Bold"
                    p.setFont(current_font, 9)
                    
                    p.drawString(50, y, str(row['date']))
                    p.drawString(120, y, str(row['type']))
                    
                    desc_text = str(row['description'])
                    desc_display = (desc_text[:35] + '..') if len(desc_text) > 35 else desc_text
                    p.drawString(180, y, desc_display)
                    p.drawString(380, y, f"€{row['amount']:.2f}")
                    
                    # Kleur voor saldo
                    if row['Saldo'] < 0:
                        p.setFillColor(colors.red)
                    else:
                        p.setFillColor(colors.green)
                    
                    p.drawString(480, y, f"€{row['Saldo']:.2f}")
                    p.setFillColor(colors.black) # Reset naar zwart voor volgende regel

                p.showPage()
                p.save() # Slechts één keer aanroepen aan het einde
                
                # De downloadknop
                st.download_button(
                    label="Klik hier om PDF te downloaden",
                    data=buffer.getvalue(),
                    file_name=f"overzicht_patrick_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
        else:
            st.warning("De database bevat nog geen transacties.")


