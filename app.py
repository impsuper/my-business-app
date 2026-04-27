# -*- coding: utf-8 -*-
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_file, make_response)
import sqlite3, io, os
from datetime import datetime, date
from functools import wraps
from fpdf import FPDF
from database import get_db, init_db, get_company, get_all_company, DB

app = Flask(__name__)
app.secret_key = 'CreditManager_Secret_2024_!@#'

# ─── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return decorated

# ─── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        uname  = request.form.get('username','').strip()
        passwd = request.form.get('password','')
        conn   = get_db()
        user   = conn.execute(
            "SELECT username,password,role,display_name FROM users WHERE username=? AND password=?",
            (uname, passwd)).fetchone()
        conn.close()
        if user:
            session['user']   = user['username']
            session['role']   = user['role']
            session['dname']  = user['display_name'] or user['username']
            return redirect(url_for('dashboard'))
        flash('Username හෝ Password වැරදියි!', 'error')
    company = get_company('company_name') or 'SEWWANDI AGENCIES'
    return render_template('login.html', company=company)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    conn   = get_db()
    p_cnt, p_bal = conn.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM bills WHERE balance>0").fetchone()
    c_cnt, c_val = conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cheques WHERE status='received'").fetchone()
    r_cnt, r_bal = conn.execute("SELECT COUNT(*), COALESCE(SUM(returned_balance),0) FROM cheques WHERE status='returned'").fetchone()
    conn.close()
    company = get_company('company_name') or 'SEWWANDI AGENCIES'
    stats   = dict(p_cnt=p_cnt or 0, p_bal=p_bal or 0,
                   c_cnt=c_cnt or 0, c_val=c_val or 0,
                   r_cnt=r_cnt or 0, r_bal=r_bal or 0)
    return render_template('dashboard.html', company=company, stats=stats)

# ─── Bills ─────────────────────────────────────────────────────────────────────

@app.route('/bills/pending')
@login_required
def bills_pending():
    q    = request.args.get('q','').strip()
    srep = request.args.get('srep','').strip()
    like = f'%{q}%'
    conn = get_db()
    reps = [r['name'] for r in conn.execute("SELECT name FROM sales_reps ORDER BY name")]
    rows = conn.execute("""SELECT * FROM bills WHERE balance>0
        AND (shop_name LIKE ? OR inv_no LIKE ? OR town LIKE ? OR sales_ref LIKE ?)
        ORDER BY inv_date DESC""", (like,like,like,like)).fetchall()
    total = sum(r['balance'] for r in rows)
    conn.close()
    company = get_company('company_name')
    return render_template('bills_pending.html', bills=rows, total=total,
                           q=q, srep=srep, reps=reps, company=company)

@app.route('/bills/add', methods=['POST'])
@login_required
def bill_add():
    f = request.form
    today = datetime.now().strftime('%Y-%m-%d')
    amt   = float(f.get('bill_amt',0) or 0)
    conn  = get_db()
    conn.execute("""INSERT INTO bills
        (system_date,inv_date,del_date,shop_name,sales_ref,town,inv_no,bill_amt,paid_amt,balance)
        VALUES (?,?,?,?,?,?,?,?,0,?)""",
        (today, f.get('inv_date',today), f.get('del_date',today),
         f.get('shop_name',''), f.get('sales_ref',''),
         f.get('town',''), f.get('inv_no',''), amt, amt))
    conn.commit(); conn.close()
    flash('Bill successfully saved!', 'success')
    return redirect(url_for('bills_pending'))

@app.route('/bills/pay', methods=['POST'])
@login_required
def bill_pay():
    bill_id  = request.form.get('bill_id')
    pay_type = request.form.get('pay_type','full')
    conn     = get_db()
    bill     = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
    if not bill:
        flash('Bill not found.', 'error'); return redirect(url_for('bills_pending'))
    today    = datetime.now().strftime('%Y-%m-%d')
    if pay_type == 'full':
        new_paid = bill['paid_amt'] + bill['balance']
        conn.execute("UPDATE bills SET paid_amt=?, balance=0 WHERE id=?", (new_paid, bill_id))
        conn.execute("INSERT INTO payment_history(bill_id,amount,pay_date) VALUES(?,?,?)",
                     (bill_id, bill['balance'], today))
    else:
        part_amt = float(request.form.get('part_amt', 0) or 0)
        if part_amt <= 0 or part_amt > bill['balance']:
            flash('Invalid payment amount.', 'error')
            conn.close()
            return redirect(url_for('bills_pending'))
        conn.execute("UPDATE bills SET paid_amt=paid_amt+?, balance=balance-? WHERE id=?",
                     (part_amt, part_amt, bill_id))
        conn.execute("INSERT INTO payment_history(bill_id,amount,pay_date) VALUES(?,?,?)",
                     (bill_id, part_amt, today))
    conn.commit(); conn.close()
    flash('Payment recorded!', 'success')
    return redirect(url_for('bills_pending'))

@app.route('/bills/delete', methods=['POST'])
@admin_required
def bill_delete():
    bill_id = request.form.get('bill_id')
    conn    = get_db()
    conn.execute("DELETE FROM bills WHERE id=?", (bill_id,))
    conn.execute("DELETE FROM payment_history WHERE bill_id=?", (bill_id,))
    conn.commit(); conn.close()
    flash('Bill deleted.', 'info')
    return redirect(url_for('bills_pending'))

@app.route('/bills/settled')
@login_required
def bills_settled():
    q    = request.args.get('q','').strip()
    like = f'%{q}%'
    conn = get_db()
    rows = conn.execute("""SELECT b.*, GROUP_CONCAT(ph.pay_date||'='||ph.amount,'|') as pay_hist
        FROM bills b LEFT JOIN payment_history ph ON b.id=ph.bill_id
        WHERE b.balance<=0
        AND (b.shop_name LIKE ? OR b.inv_no LIKE ? OR b.town LIKE ?)
        GROUP BY b.id ORDER BY b.inv_date DESC""", (like,like,like)).fetchall()
    total = conn.execute("SELECT COALESCE(SUM(bill_amt),0) FROM bills WHERE balance<=0").fetchone()[0]
    conn.close()
    company = get_company('company_name')
    return render_template('bills_settled.html', bills=rows, total=total, q=q, company=company)

@app.route('/bills/payment-history/<int:bill_id>')
@login_required
def bill_payment_history(bill_id):
    conn = get_db()
    hist = conn.execute(
        "SELECT pay_date, amount FROM payment_history WHERE bill_id=? ORDER BY id DESC", (bill_id,)).fetchall()
    bill = conn.execute("SELECT shop_name, inv_no, bill_amt FROM bills WHERE id=?", (bill_id,)).fetchone()
    conn.close()
    return jsonify({'history': [dict(h) for h in hist], 'bill': dict(bill) if bill else {}})

# ─── Cheques ───────────────────────────────────────────────────────────────────

@app.route('/cheques/received')
@login_required
def cheques_received():
    q    = request.args.get('q','').strip()
    like = f'%{q}%'
    today= date.today()
    conn = get_db()
    rows = conn.execute("""SELECT * FROM cheques WHERE status='received'
        AND (shop_name LIKE ? OR bank LIKE ? OR chq_no LIKE ? OR town LIKE ?)
        ORDER BY chq_date ASC""", (like,like,like,like)).fetchall()

    result = []
    for r in rows:
        rd = dict(r)
        try:
            recv_d = datetime.strptime(r['received_date'], '%Y-%m-%d').date()
            chq_d  = datetime.strptime(r['chq_date'], '%Y-%m-%d').date()
            rd['age']        = (recv_d - chq_d).days
            rd['days_to_bank']= (chq_d - today).days
            rd['overdue']    = rd['days_to_bank'] < 0
            rd['age_red']    = rd['age'] > 21
        except:
            rd['age'] = rd['days_to_bank'] = 'N/A'
            rd['overdue'] = rd['age_red'] = False
        result.append(rd)

    total = sum(r['amount'] for r in rows)
    company = get_company('company_name')
    return render_template('cheques_received.html', cheques=result,
                           total=total, q=q, company=company, today=str(today))

@app.route('/cheques/add', methods=['POST'])
@login_required
def cheque_add():
    f     = request.form
    today = datetime.now().strftime('%Y-%m-%d')
    conn  = get_db()
    conn.execute("""INSERT INTO cheques
        (system_date,received_date,shop_name,town,bank,chq_no,amount,chq_date,status,collected_by)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (today, f.get('received_date',today), f.get('shop_name',''), f.get('town',''),
         f.get('bank',''), f.get('chq_no',''), float(f.get('amount',0) or 0),
         f.get('chq_date',''), 'received', f.get('collected_by','')))
    conn.commit(); conn.close()
    flash('Cheque saved!', 'success')
    return redirect(url_for('cheques_received'))

@app.route('/cheques/bank', methods=['POST'])
@login_required
def cheque_bank():
    chq_id     = request.form.get('chq_id')
    banked_date= request.form.get('banked_date', datetime.now().strftime('%Y-%m-%d'))
    conn       = get_db()
    conn.execute("UPDATE cheques SET status='banked', banked_date=? WHERE id=?", (banked_date, chq_id))
    conn.commit(); conn.close()
    flash('Cheque marked as Banked!', 'success')
    return redirect(url_for('cheques_received'))

@app.route('/cheques/return', methods=['POST'])
@login_required
def cheque_return():
    chq_id       = request.form.get('chq_id')
    returned_date= request.form.get('returned_date', datetime.now().strftime('%Y-%m-%d'))
    conn         = get_db()
    chq          = conn.execute("SELECT amount FROM cheques WHERE id=?", (chq_id,)).fetchone()
    if chq:
        conn.execute("""UPDATE cheques SET status='returned', returned_date=?,
            returned_balance=?, returned_settled=0 WHERE id=?""",
            (returned_date, chq['amount'], chq_id))
        conn.commit()
    conn.close()
    flash('Cheque marked as Returned!', 'warning')
    return redirect(url_for('cheques_received'))

@app.route('/cheques/delete', methods=['POST'])
@admin_required
def cheque_delete():
    chq_id = request.form.get('chq_id')
    conn   = get_db()
    conn.execute("DELETE FROM cheques WHERE id=?", (chq_id,))
    conn.execute("DELETE FROM ret_chq_payments WHERE chq_id=?", (chq_id,))
    conn.commit(); conn.close()
    flash('Cheque deleted.', 'info')
    return redirect(request.referrer or url_for('cheques_received'))

@app.route('/cheques/banked')
@login_required
def cheques_banked():
    q    = request.args.get('q','').strip()
    like = f'%{q}%'
    conn = get_db()
    rows = conn.execute("""SELECT * FROM cheques WHERE status='banked'
        AND (shop_name LIKE ? OR bank LIKE ? OR chq_no LIKE ?)
        ORDER BY banked_date DESC""", (like,like,like)).fetchall()
    total = sum(r['amount'] for r in rows)
    company = get_company('company_name')
    conn.close()
    return render_template('cheques_banked.html', cheques=rows, total=total, q=q, company=company)

@app.route('/cheques/returned')
@login_required
def cheques_returned():
    q    = request.args.get('q','').strip()
    like = f'%{q}%'
    conn = get_db()
    rows = conn.execute("""SELECT * FROM cheques WHERE status='returned'
        AND (shop_name LIKE ? OR bank LIKE ? OR chq_no LIKE ?)
        ORDER BY returned_date DESC""", (like,like,like)).fetchall()
    result = []
    for r in rows:
        rd = dict(r)
        try:
            recv_d = datetime.strptime(r['received_date'], '%Y-%m-%d').date()
            chq_d  = datetime.strptime(r['chq_date'], '%Y-%m-%d').date()
            rd['age'] = (recv_d - chq_d).days
        except:
            rd['age'] = 'N/A'
        result.append(rd)
    total_bal = sum((r['returned_balance'] or r['amount']) for r in rows)
    company = get_company('company_name')
    conn.close()
    return render_template('cheques_returned.html', cheques=result,
                           total_bal=total_bal, q=q, company=company)

@app.route('/cheques/pay-returned', methods=['POST'])
@login_required
def cheque_pay_returned():
    chq_id   = request.form.get('chq_id')
    pay_amt  = float(request.form.get('pay_amt', 0) or 0)
    note     = request.form.get('note','')
    today    = datetime.now().strftime('%Y-%m-%d')
    conn     = get_db()
    chq      = conn.execute("SELECT returned_balance, amount FROM cheques WHERE id=?", (chq_id,)).fetchone()
    if not chq:
        flash('Cheque not found.', 'error'); return redirect(url_for('cheques_returned'))
    balance  = chq['returned_balance'] or chq['amount']
    if pay_amt <= 0 or pay_amt > balance:
        flash('Invalid payment amount.', 'error'); conn.close(); return redirect(url_for('cheques_returned'))
    new_bal  = balance - pay_amt
    settled  = 1 if new_bal <= 0 else 0
    conn.execute("UPDATE cheques SET returned_balance=?, returned_settled=? WHERE id=?",
                 (new_bal, settled, chq_id))
    conn.execute("INSERT INTO ret_chq_payments(chq_id,amount,pay_date,note) VALUES(?,?,?,?)",
                 (chq_id, pay_amt, today, note))
    conn.commit(); conn.close()
    flash('Returned cheque payment recorded!', 'success')
    return redirect(url_for('cheques_returned'))

@app.route('/cheques/ret-history/<int:chq_id>')
@login_required
def ret_chq_history(chq_id):
    conn = get_db()
    hist = conn.execute(
        "SELECT pay_date, amount, note FROM ret_chq_payments WHERE chq_id=? ORDER BY id DESC", (chq_id,)).fetchall()
    conn.close()
    return jsonify([dict(h) for h in hist])

# ─── Daily Summary ─────────────────────────────────────────────────────────────

@app.route('/daily-summary')
@login_required
def daily_summary():
    today     = date.today()
    today_str = str(today)
    conn      = get_db()

    # Bill summary
    b_today_cnt, b_today_val = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(bill_amt),0) FROM bills WHERE inv_date=?", (today_str,)).fetchone()
    b_today_pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payment_history WHERE pay_date=?", (today_str,)).fetchone()[0]
    b_pending_cnt, b_pending_bal = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(balance),0) FROM bills WHERE balance>0").fetchone()

    # Aging buckets
    all_pending = conn.execute(
        "SELECT inv_date, balance FROM bills WHERE balance>0").fetchall()
    buckets = {'0-30 Days': 0, '31-60 Days': 0, '61-90 Days': 0, '90+ Days': 0}
    for row in all_pending:
        try:
            inv_d  = datetime.strptime(row['inv_date'], '%Y-%m-%d').date()
            age    = (today - inv_d).days
            if age <= 30:    buckets['0-30 Days']  += row['balance']
            elif age <= 60:  buckets['31-60 Days'] += row['balance']
            elif age <= 90:  buckets['61-90 Days'] += row['balance']
            else:            buckets['90+ Days']   += row['balance']
        except: pass

    # Cheque summary
    def chq_q(status, date_col=None):
        if date_col:
            return conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cheques WHERE status=? AND {date_col}=?",
                (status, today_str)).fetchone()
        return conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cheques WHERE status=?", (status,)).fetchone()

    ctr, ctv = chq_q('received','received_date')
    ctb_cnt, ctb_val = chq_q('banked','banked_date')
    ctr2_cnt, ctr2_val = chq_q('returned','returned_date')
    ca_recv_cnt, ca_recv_val = chq_q('received')
    ca_ret_cnt, ca_ret_bal  = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(returned_balance),SUM(amount)) FROM cheques WHERE status='returned'").fetchone()
    conn.close()

    summary = dict(
        today=today_str,
        b_today_cnt=b_today_cnt or 0, b_today_val=b_today_val or 0,
        b_today_pay=b_today_pay or 0,
        b_pending_cnt=b_pending_cnt or 0, b_pending_bal=b_pending_bal or 0,
        buckets=buckets,
        ctr=ctr or 0, ctv=ctv or 0,
        ctb_cnt=ctb_cnt or 0, ctb_val=ctb_val or 0,
        ctr2_cnt=ctr2_cnt or 0, ctr2_val=ctr2_val or 0,
        ca_recv_cnt=ca_recv_cnt or 0, ca_recv_val=ca_recv_val or 0,
        ca_ret_cnt=ca_ret_cnt or 0, ca_ret_bal=ca_ret_bal or 0,
    )
    company = get_company('company_name')
    return render_template('daily_summary.html', s=summary, company=company)

# ─── Users ─────────────────────────────────────────────────────────────────────

@app.route('/users')
@login_required
@admin_required
def users():
    conn  = get_db()
    users = conn.execute("SELECT id, username, display_name, role FROM users ORDER BY id").fetchall()
    conn.close()
    company = get_company('company_name')
    return render_template('users.html', users=users, company=company)

@app.route('/users/add', methods=['POST'])
@login_required
@admin_required
def user_add():
    f    = request.form
    conn = get_db()
    try:
        conn.execute("INSERT INTO users(username,password,role,display_name) VALUES(?,?,?,?)",
                     (f.get('username','').strip(), f.get('password',''),
                      f.get('role','user'), f.get('display_name','').strip()))
        conn.commit()
        flash('User added!', 'success')
    except Exception as e:
        flash(f'Error: Username already exists.', 'error')
    conn.close()
    return redirect(url_for('users'))

@app.route('/users/delete', methods=['POST'])
@login_required
@admin_required
def user_delete():
    uid  = request.form.get('user_id')
    if str(uid) == '1':
        flash('Cannot delete admin.', 'error')
        return redirect(url_for('users'))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit(); conn.close()
    flash('User deleted.', 'info')
    return redirect(url_for('users'))

@app.route('/users/reset-password', methods=['POST'])
@login_required
@admin_required
def user_reset_pw():
    uid  = request.form.get('user_id')
    pw   = request.form.get('new_pw','')
    conn = get_db()
    conn.execute("UPDATE users SET password=? WHERE id=?", (pw, uid))
    conn.commit(); conn.close()
    flash('Password reset.', 'success')
    return redirect(url_for('users'))

# ─── Company Profile ───────────────────────────────────────────────────────────

@app.route('/company', methods=['GET','POST'])
@login_required
@admin_required
def company():
    if request.method == 'POST':
        conn = get_db()
        for key in ['company_name','address','email','phone1','phone2','phone3']:
            conn.execute("INSERT OR REPLACE INTO company_profile VALUES(?,?)",
                         (key, request.form.get(key,'')))
        conn.commit(); conn.close()
        flash('Company profile saved!', 'success')
        return redirect(url_for('company'))
    profile = get_all_company()
    company_name = get_company('company_name')
    return render_template('company.html', profile=profile, company=company_name)

# ─── Settings ──────────────────────────────────────────────────────────────────

@app.route('/settings', methods=['GET','POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        conn   = get_db()
        if action == 'change_pw':
            old = request.form.get('old_pw','')
            new = request.form.get('new_pw','')
            cfm = request.form.get('cfm_pw','')
            row = conn.execute("SELECT password FROM users WHERE username=?",
                               (session['user'],)).fetchone()
            if not row or row['password'] != old:
                flash('Old password incorrect.', 'error')
            elif new != cfm:
                flash('New passwords do not match.', 'error')
            elif not new:
                flash('Password cannot be empty.', 'error')
            else:
                conn.execute("UPDATE users SET password=? WHERE username=?", (new, session['user']))
                conn.execute("UPDATE settings SET value=? WHERE key='password'", (new,))
                conn.commit()
                flash('Password changed!', 'success')
        conn.close()
        return redirect(url_for('settings'))
    company_name = get_company('company_name')
    return render_template('settings.html', company=company_name)

# ─── PDF Exports ───────────────────────────────────────────────────────────────

def _pdf_header(pdf, title, subtitle='', landscape=False):
    cname = get_company('company_name') or 'SEWWANDI AGENCIES'
    caddr = get_company('address') or ''
    w     = 277 if landscape else 190
    pdf.set_fill_color(22, 50, 90); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 15)
    pdf.cell(w, 10, cname, 0, 1, 'C', fill=True)
    if caddr:
        pdf.set_font("Arial", '', 9)
        pdf.cell(w, 6, caddr, 0, 1, 'C', fill=True)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(w, 8, title, 0, 1, 'C', fill=True)
    pdf.set_font("Arial", '', 8)
    gen_by = session.get('dname', '')
    pdf.cell(w, 6,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  Generated by: {gen_by}",
        0, 1, 'C', fill=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(3)

@app.route('/pdf/bills')
@login_required
def pdf_bills():
    filt = request.args.get('filter','pending')
    conn = get_db()
    if filt == 'settled':
        rows = conn.execute("SELECT * FROM bills WHERE balance<=0 ORDER BY inv_date DESC").fetchall()
        title = 'SETTLED BILLS REPORT'
    else:
        rows = conn.execute("SELECT * FROM bills WHERE balance>0 ORDER BY inv_date DESC").fetchall()
        title = 'PENDING BILLS REPORT'
    conn.close()

    pdf = FPDF(); pdf.add_page(); pdf.set_margins(10,10,10)
    _pdf_header(pdf, title)

    headers = ["ID","Inv Date","Del Date","Shop Name","Town","Sales Ref","Inv No","Amount","Paid","Balance"]
    widths  = [12, 24, 24, 46, 26, 24, 22, 26, 22, 24]
    pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(180, 210, 250)
    for h, w in zip(headers, widths): pdf.cell(w, 8, h, 1, 0, 'C', fill=True)
    pdf.ln()

    alt = [(240,248,255),(255,255,255)]
    pdf.set_font("Arial", '', 7)
    for i, r in enumerate(rows):
        r2, g2, b2 = alt[i % 2]; pdf.set_fill_color(r2,g2,b2)
        vals = [str(r['id']), r['inv_date'] or '', r['del_date'] or '',
                (r['shop_name'] or '')[:28], r['town'] or '', r['sales_ref'] or '',
                r['inv_no'] or '', f"Rs.{r['bill_amt']:,.0f}",
                f"Rs.{r['paid_amt']:,.0f}", f"Rs.{r['balance']:,.0f}"]
        for v, w in zip(vals, widths): pdf.cell(w, 7, v, 1, 0, 'C', fill=True)
        pdf.ln()

    total = sum(r['balance'] for r in rows)
    pdf.set_font("Arial",'B',8); pdf.set_fill_color(200,220,255)
    pdf.cell(sum(widths[:-1]), 7, "TOTAL BALANCE", 1, 0, 'R', fill=True)
    pdf.cell(widths[-1], 7, f"Rs.{total:,.0f}", 1, 1, 'R', fill=True)

    buf = io.BytesIO(); pdf.output(buf); buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"Bills_{filt}_{date.today()}.pdf",
                     mimetype='application/pdf')

@app.route('/pdf/cheques')
@login_required
def pdf_cheques():
    filt = request.args.get('filter','all')
    conn = get_db()
    bq   = "SELECT * FROM cheques"
    if filt == 'received':  rows_all = {'received': conn.execute(bq+" WHERE status='received' ORDER BY chq_date").fetchall()}
    elif filt == 'banked':  rows_all = {'banked':   conn.execute(bq+" WHERE status='banked'   ORDER BY chq_date").fetchall()}
    elif filt == 'returned':rows_all = {'returned': conn.execute(bq+" WHERE status='returned' ORDER BY chq_date").fetchall()}
    else:
        rows_all = {
            'received': conn.execute(bq+" WHERE status='received' ORDER BY chq_date").fetchall(),
            'banked':   conn.execute(bq+" WHERE status='banked'   ORDER BY chq_date").fetchall(),
            'returned': conn.execute(bq+" WHERE status='returned' ORDER BY chq_date").fetchall(),
        }
    conn.close()

    pdf = FPDF(orientation='L'); pdf.add_page(); pdf.set_margins(8,8,8)
    _pdf_header(pdf, f"CHEQUE REPORT - {filt.upper()}", landscape=True)

    col_w   = [10, 27, 50, 25, 28, 22, 30, 27, 22, 22]
    headers = ["ID","Recv Date","Shop Name","Town","Bank","Chq No","Amount","Chq Date","Status","Collected By"]
    label_colors = {'received':(180,230,200),'banked':(180,200,255),'returned':(255,180,180)}

    def draw_table(status, rows):
        total = sum(r['amount'] for r in rows)
        pdf.set_font("Arial",'B',10)
        rc, gc, bc = label_colors.get(status,(180,210,250))
        pdf.set_fill_color(44,80,130); pdf.set_text_color(255,255,255)
        pdf.cell(277, 8, f"  {status.upper()} CHEQUES  |  Count: {len(rows)}   Total: Rs. {total:,.2f}", 0,1,'L',fill=True)
        pdf.set_text_color(0,0,0); pdf.ln(1)
        pdf.set_font("Arial",'B',8)
        pdf.set_fill_color(rc,gc,bc)
        for h, w in zip(headers, col_w): pdf.cell(w, 8, h, 1, 0,'C', fill=True)
        pdf.ln()
        alt = [(240,248,255),(255,255,255)]
        pdf.set_font("Arial",'',7)
        for i, r in enumerate(rows):
            if status == 'returned': pdf.set_fill_color(255,200,200)
            else:
                r2,g2,b2 = alt[i%2]; pdf.set_fill_color(r2,g2,b2)
            vals = [str(r['id']), r['received_date'] or '', (r['shop_name'] or '')[:30],
                    r['town'] or '', r['bank'] or '', r['chq_no'] or '',
                    f"Rs.{r['amount']:,.0f}", r['chq_date'] or '',
                    (r['status'] or '').upper(), r['collected_by'] or '']
            for v, w in zip(vals, col_w): pdf.cell(w, 7, v, 1, 0,'C', fill=True)
            pdf.ln()
        pdf.set_font("Arial",'B',8); pdf.set_fill_color(200,220,255)
        pdf.cell(sum(col_w[:6]), 7, "TOTAL", 1, 0,'R', fill=True)
        pdf.cell(col_w[6], 7, f"Rs.{total:,.0f}", 1, 0,'R', fill=True)
        pdf.cell(sum(col_w[7:]), 7, "", 1, 1,'C', fill=True)
        pdf.ln(4)

    for status, rows in rows_all.items():
        draw_table(status, rows)

    buf = io.BytesIO(); pdf.output(buf); buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"Cheques_{filt}_{date.today()}.pdf",
                     mimetype='application/pdf')

@app.route('/pdf/daily-summary')
@login_required
def pdf_daily_summary():
    today     = str(date.today())
    conn      = get_db()
    b_today   = conn.execute("SELECT COUNT(*), COALESCE(SUM(bill_amt),0) FROM bills WHERE inv_date=?", (today,)).fetchone()
    b_pay     = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payment_history WHERE pay_date=?", (today,)).fetchone()[0]
    b_pend    = conn.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM bills WHERE balance>0").fetchone()
    chq_data  = {}
    for s, dc in [('received','received_date'),('banked','banked_date'),('returned','returned_date')]:
        chq_data[s] = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cheques WHERE status=? AND {dc}=?", (s,today)).fetchone()
    ca_recv = conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cheques WHERE status='received'").fetchone()
    ca_ret  = conn.execute("SELECT COUNT(*), COALESCE(SUM(returned_balance),SUM(amount)) FROM cheques WHERE status='returned'").fetchone()
    all_pend= conn.execute("SELECT inv_date, balance FROM bills WHERE balance>0").fetchall()
    conn.close()

    buckets = {'0-30 Days':0,'31-60 Days':0,'61-90 Days':0,'90+ Days':0}
    for row in all_pend:
        try:
            age = (date.today() - datetime.strptime(row['inv_date'],'%Y-%m-%d').date()).days
            if age<=30: buckets['0-30 Days']+=row['balance']
            elif age<=60: buckets['31-60 Days']+=row['balance']
            elif age<=90: buckets['61-90 Days']+=row['balance']
            else: buckets['90+ Days']+=row['balance']
        except: pass

    pdf = FPDF(); pdf.add_page(); pdf.set_margins(10,10,10)
    _pdf_header(pdf, f"DAILY SUMMARY REPORT - {today}")

    def section(title, color):
        pdf.set_fill_color(*color); pdf.set_text_color(255,255,255)
        pdf.set_font("Arial",'B',10)
        pdf.cell(190, 8, f"  {title}", 0, 1,'L', fill=True)
        pdf.set_text_color(0,0,0); pdf.ln(1)

    def row2(label, value, bold=False):
        pdf.set_font("Arial", 'B' if bold else '', 9)
        pdf.cell(110, 7, label, 0, 0,'L')
        pdf.set_font("Arial",'B',9)
        pdf.cell(80, 7, str(value), 0, 1,'R')

    section("BILL SUMMARY", (44,80,130))
    row2("Today New Bills", f"Count: {b_today[0]}  |  Rs. {b_today[1]:,.2f}")
    row2("Today Payments Collected", f"Rs. {b_pay:,.2f}")
    row2("Total Pending Bills", f"Count: {b_pend[0]}  |  Rs. {b_pend[1]:,.2f}", True)
    pdf.ln(3)

    section("AGING SUMMARY", (100,60,130))
    for k, v in buckets.items():
        row2(k, f"Rs. {v:,.2f}")
    pdf.ln(3)

    section("CHEQUE SUMMARY", (20,100,80))
    row2("Today Received", f"Count: {chq_data['received'][0]}  |  Rs. {chq_data['received'][1]:,.2f}")
    row2("Today Banked",   f"Count: {chq_data['banked'][0]}  |  Rs. {chq_data['banked'][1]:,.2f}")
    row2("Today Returned", f"Count: {chq_data['returned'][0]}  |  Rs. {chq_data['returned'][1]:,.2f}")
    row2("All Pending Cheques",  f"Count: {ca_recv[0]}  |  Rs. {ca_recv[1]:,.2f}", True)
    row2("All Returned Cheques", f"Count: {ca_ret[0]}  |  Rs. {ca_ret[1]:,.2f}", True)

    buf = io.BytesIO(); pdf.output(buf); buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"Daily_Summary_{today}.pdf",
                     mimetype='application/pdf')

# ─── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
