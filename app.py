import os
from io import BytesIO
import uuid
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
from flask_mail import Mail
from werkzeug.security import check_password_hash, generate_password_hash
import mysql.connector

from models import db, Quote
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.environ.get("CLOUDINARY_API_KEY"),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET")
)

app = Flask(__name__)

# ---------------- BASIC CONFIG ----------------

app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key")
app.config['SESSION_PERMANENT'] = False

# ---------------- DATABASE CONFIG ----------------

DB_HOST     = os.environ.get("DB_HOST",     "127.0.0.1")
DB_PORT     = os.environ.get("DB_PORT",     " 25189")
DB_USER     = os.environ.get("DB_USER",     "crmuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "1234")
DB_NAME     = os.environ.get("DB_NAME",     "insurance_crm")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?connect_timeout=30"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

UPLOAD_FOLDER = "static/uploads/policies"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- EMAIL CONFIG ----------------

app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 587
app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME", "your_email@gmail.com")
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD", "your_app_password")
app.config['MAIL_USE_TLS']  = True

mail = Mail(app)

# ---------------- DB HELPER ----------------

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        connection_timeout=30
    )

# ---------------- DECIMAL HELPER ----------------

def clean_decimal(value):
    """Safely convert a value to float, returning None if empty or invalid."""
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")

# ---------------- QUOTE ----------------

@app.route("/quote", methods=["GET", "POST"])
def quote():
    if request.method == "POST":
        name      = request.form["name"]
        email     = request.form["email"]
        phone     = request.form["phone"]
        insurance = request.form["insurance_type"]
        message   = request.form["message"]
        rating    = int(request.form.get("rating") or 0)

        new_quote = Quote(
            name=name,
            email=email,
            phone=phone,
            insurance_type=insurance,
            message=message,
            rating=rating
        )
        db.session.add(new_quote)
        db.session.commit()

        return redirect("/")

    return render_template("quote.html")

# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"]    = "admin"
            return redirect(url_for("admin_dashboard"))

        return render_template("login.html", error="Invalid login")

    return render_template("login.html")

# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT name, email FROM users WHERE id=%s", (session["user_id"],))
    user = cur.fetchone()
    conn.close()

    return render_template("admin_dashboard.html", user=user)

# ---------------- DASHBOARD PAGE ----------------

@app.route("/dashboard_page")
def dashboard_page():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT name, email FROM users WHERE id=%s", (session["user_id"],))
    user = cur.fetchone()
    conn.close()

    return render_template("pages/dashboard.html", user=user)

@app.route("/dashboard_data")
def dashboard_data():
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    # --- Summary counts ---
    cur.execute("SELECT COUNT(DISTINCT cust_name) AS total FROM policies")
    total_customers = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) AS total FROM policies")
    total_policies = cur.fetchone()["total"]

    cur.execute("""
        SELECT SUM(gross_premium) AS total
        FROM policies
        WHERE DATE(expire_date) = CURDATE()
    """)
    today = cur.fetchone()["total"] or 0

    cur.execute("""
        SELECT SUM(gross_premium) AS total
        FROM policies
        WHERE MONTH(expire_date) = MONTH(CURDATE())
          AND YEAR(expire_date)  = YEAR(CURDATE())
    """)
    month = cur.fetchone()["total"] or 0

    # --- Monthly revenue for current year ---
    cur.execute("""
        SELECT MONTH(expire_date) AS month,
               SUM(gross_premium) AS revenue
        FROM policies
        WHERE YEAR(expire_date) = YEAR(CURDATE())
        GROUP BY MONTH(expire_date)
    """)
    result = cur.fetchall()

    month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]
    month_values = [0] * 12
    for r in result:
        month_values[r["month"] - 1] = float(r["revenue"])

    # --- Insurance-wise monthly revenue ---
    cur.execute("""
        SELECT policy_type,
               MONTH(expire_date) AS month,
               SUM(gross_premium) AS revenue
        FROM policies
        WHERE YEAR(expire_date) = YEAR(CURDATE())
        GROUP BY policy_type, MONTH(expire_date)
        ORDER BY policy_type, month
    """)
    rows = cur.fetchall()

    insurance_data = {}
    for r in rows:
        policy      = r["policy_type"]
        month_index = r["month"] - 1
        revenue     = float(r["revenue"])
        if policy not in insurance_data:
            insurance_data[policy] = [0] * 12
        insurance_data[policy][month_index] = revenue

    # --- Upcoming renewals (next 7 days) ---
    cur.execute("""
        SELECT cust_name AS name,
               policy_type,
               expire_date
        FROM policies
        WHERE expire_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
        ORDER BY expire_date
    """)
    ren = cur.fetchall()
    renewals = [
        {"name": r["name"], "policy": r["policy_type"], "date": str(r["expire_date"])}
        for r in ren
    ]

    # --- Top 5 agents ---
    cur.execute("""
        SELECT ref_name AS agent_name,
               COUNT(*) AS policies,
               SUM(gross_premium) AS revenue
        FROM policies
        GROUP BY ref_name
        ORDER BY revenue DESC
        LIMIT 5
    """)
    ag = cur.fetchall()
    agents = [
        {"name": a["agent_name"], "policies": a["policies"], "revenue": float(a["revenue"] or 0)}
        for a in ag
    ]

    conn.close()

    return jsonify({
        "total_customers": total_customers,
        "total_policies":  total_policies,
        "today":           float(today),
        "month":           float(month),
        "insurance_monthly": insurance_data,
        "month_labels":    month_labels,
        "month_values":    month_values,
        "renewals":        renewals,
        "agents":          agents
    })

@app.route("/agents_by_month")
def agents_by_month():
    month = request.args.get("month")
    
    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    if month and month != "all":
        cur.execute("""
            SELECT ref_name AS agent_name,
                   COUNT(*) AS policies,
                   SUM(gross_premium) AS revenue
            FROM policies
            WHERE MONTH(expire_date) = %s
            AND YEAR(expire_date) = YEAR(CURDATE())
            GROUP BY ref_name
            ORDER BY revenue DESC
            LIMIT 5
        """, (month,))
    else:
        cur.execute("""
            SELECT ref_name AS agent_name,
                   COUNT(*) AS policies,
                   SUM(gross_premium) AS revenue
            FROM policies
            GROUP BY ref_name
            ORDER BY revenue DESC
            LIMIT 5
        """)

    agents = cur.fetchall()
    conn.close()

    return jsonify([
        {"name": a["agent_name"], "policies": a["policies"], "revenue": float(a["revenue"] or 0)}
        for a in agents
    ])

# ---------------- CUSTOMERS ----------------

@app.route("/customers")
def customers():
    if session.get("role") != "admin":
        return redirect(url_for("home"))
    return render_template("admin_dashboard.html")

@app.route("/customers_search")
def customers_search():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id,
               sr_no, month, cust_name, insurer, policy_type,
               department, source, expire_date,
               commissionable_premium, net_od_premium, tp_premium,
               pbst_np, gross_premium, ncb, policy_number,
               make, model_variant, vehicle_category,
               passengers_gvw, vehicle_no, cc, fuel,
               rto_name, ref_name, policy_pdf, mail, phone
        FROM policies
        ORDER BY cust_name
    """)
    customers = cur.fetchall()
    conn.close()

    return render_template("pages/customers_search.html", customers=customers)

# ---------------- NEW CUSTOMER ----------------

@app.route("/new_customer", methods=["GET", "POST"])
def new_customer():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    if request.method == "POST":
        expire_date = request.form.get("expire_date") or None

        # PDF Upload
        # PDF Upload to Cloudinary
        file     = request.files.get("policy_pdf")
        filename = None
        if file and file.filename != "":
            upload_result = cloudinary.uploader.upload(
                file,
                resource_type="auto",
                folder="nsure_policies",
                format="pdf",
                use_filename=True,
                unique_filename=True
            )
            filename = upload_result["secure_url"].replace("/image/upload/", "/raw/upload/")

        conn          = get_db_connection()
        cur           = conn.cursor()
        policy_number = request.form["policy_number"]

        # Duplicate check
        cur.execute("SELECT id FROM policies WHERE policy_number=%s", (policy_number,))
        if cur.fetchone():
            conn.close()
            return f"❌ Duplicate Policy Number: {policy_number}"

        cur.execute("""
            INSERT INTO policies (
                sr_no, month, cust_name, insurer, policy_type,
                department, source, expire_date,
                commissionable_premium, net_od_premium, tp_premium,
                pbst_np, gross_premium, ncb, policy_number,
                make, model_variant, vehicle_category,
                passengers_gvw, vehicle_no, cc, fuel,
                rto_name, ref_name, policy_pdf, mail, phone
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
        """, (
            request.form["sr_no"],
            request.form["month"],
            request.form["cust_name"],
            request.form["insurer"],
            request.form["policy_type"],
            request.form["department"],
            request.form["source"],
            expire_date,
            clean_decimal(request.form.get("commissionable_premium")),
            clean_decimal(request.form.get("net_od_premium")),
            clean_decimal(request.form.get("tp_premium")),
            clean_decimal(request.form.get("pbst_np")),
            clean_decimal(request.form.get("gross_premium")),
            clean_decimal(request.form.get("ncb")),
            policy_number,
            request.form["make"],
            request.form["model_variant"],
            request.form["vehicle_category"],
            request.form["passengers_gvw"],
            request.form["vehicle_no"],
            clean_decimal(request.form.get("cc")),
            request.form["fuel"],
            request.form["rto_name"],
            request.form["ref_name"],
            filename,
            request.form["mail"],
            request.form["phone"]
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("admin_dashboard"))

    return render_template("pages/new_customer.html")

# ---------------- DELETE PDF ----------------

@app.route("/delete_pdf/<int:id>")
def delete_pdf(id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT policy_pdf FROM policies WHERE id=%s", (id,))
    file = cur.fetchone()

    if file and file["policy_pdf"]:
        path = os.path.join(app.config["UPLOAD_FOLDER"], file["policy_pdf"])
        if os.path.exists(path):
            os.remove(path)

    cur.execute("UPDATE policies SET policy_pdf=NULL WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))

# ---------------- IMPORT EXCEL ----------------

@app.route("/import_excel", methods=["POST"])
def import_excel():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    file = request.files["file"]
    df   = pd.read_excel(file)

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("/", "_", regex=False)
        .str.replace("(", "",  regex=False)
        .str.replace(")", "",  regex=False)
    )
    df = df.fillna("")

    conn       = get_db_connection()
    cur        = conn.cursor()
    duplicates = []

    for index, row in df.iterrows():
        policy_number = str(row.get("policy_number", "")).strip()

        cur.execute("SELECT id FROM policies WHERE policy_number=%s", (policy_number,))
        if cur.fetchone():
            duplicates.append(row.get("sr_no", index + 1))
            continue

        sr_no = row.get("sr_no")
        if sr_no == "":
            sr_no = None
        else:
            try:
                sr_no = int(sr_no)
            except (ValueError, TypeError):
                sr_no = None

        expire_date = row.get("expire_date")
        if expire_date != "" and pd.notna(expire_date):
            try:
                expire_date = pd.to_datetime(expire_date).date()
            except Exception:
                expire_date = None
        else:
            expire_date = None

        cur.execute("""
            INSERT INTO policies (
                sr_no, month, cust_name, insurer, policy_type,
                department, source, expire_date,
                commissionable_premium, net_od_premium, tp_premium,
                pbst_np, gross_premium, ncb, policy_number,
                make, model_variant, vehicle_category,
                passengers_gvw, vehicle_no, cc, fuel,
                rto_name, ref_name, policy_pdf, mail, phone
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
        """, (
            sr_no,
            row.get("month", ""),
            row.get("cust_name", ""),
            row.get("insurer", ""),
            row.get("policy_type", ""),
            row.get("department", ""),
            row.get("source", ""),
            expire_date,
            clean_decimal(row.get("commissionable_premium")),
            clean_decimal(row.get("net_od_premium")),
            clean_decimal(row.get("tp_premium")),
            clean_decimal(row.get("pbst_np")),
            clean_decimal(row.get("gross_premium")),
            clean_decimal(row.get("ncb")),
            policy_number,
            row.get("make", ""),
            row.get("model_variant", ""),
            row.get("vehicle_category", ""),
            row.get("passengers_gvw", ""),
            row.get("vehicle_no", ""),
            clean_decimal(row.get("cc")),
            row.get("fuel", ""),
            row.get("rtoname", ""),
            row.get("ref_name", ""),
            row.get("policy_pdf", ""),
            row.get("email", ""),
            row.get("phone", "")
        ))

    conn.commit()
    conn.close()

    if duplicates:
        return f"⚠️ Duplicate Policy Numbers found at Sr No: {duplicates}"
    return "✅ Import Successful (No duplicates)"

# ---------------- EXPORT EXCEL ----------------

@app.route("/export_excel")
def export_excel():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    agent       = request.args.get("agent")
    month       = request.args.get("month")
    exp_month   = request.args.get("exp_month")
    year        = request.args.get("year")
    policy_type = request.args.get("policy_type")

    conn   = get_db_connection()
    query  = """
        SELECT sr_no, month, cust_name, insurer, policy_type,
               department, source, expire_date,
               commissionable_premium, net_od_premium, tp_premium,
               pbst_np, gross_premium, ncb, policy_number,
               make, model_variant, vehicle_category,
               passengers_gvw, vehicle_no, cc, fuel,
               rto_name, ref_name, policy_pdf, mail, phone
        FROM policies
        WHERE 1=1
    """
    params = []

    if agent:
        query += " AND ref_name = %s"
        params.append(agent)
    if policy_type:
        query += " AND policy_type = %s"
        params.append(policy_type)
    if month:
        query += " AND month = %s"
        params.append(month)
    if exp_month:
        query += " AND MONTH(expire_date) = %s"
        params.append(exp_month)
    if year:
        query += " AND YEAR(expire_date) = %s"
        params.append(year)

    df = pd.read_sql(query, conn, params=params)
    conn.close()

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        download_name="filtered_customers.xlsx",
        as_attachment=True
    )

# ---------------- EDIT CUSTOMER ----------------

@app.route("/edit_customer/<int:id>", methods=["GET", "POST"])
def edit_customer(id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    if request.method == "POST":
        file = request.files.get("policy_pdf")

        cur.execute("SELECT policy_pdf FROM policies WHERE id=%s", (id,))
        old      = cur.fetchone()
        filename = old["policy_pdf"]

        if file and file.filename != "":
            upload_result = cloudinary.uploader.upload(
                file,
                resource_type="auto",
                folder="nsure_policies",
                format="pdf",
                use_filename=True,
                unique_filename=True
            )
            filename = upload_result["secure_url"].replace("/image/upload/", "/raw/upload/")
        expire_date = request.form.get("expire_date") or None

        cur.execute("""
            UPDATE policies SET
                sr_no=%s, month=%s, cust_name=%s, insurer=%s,
                policy_type=%s, department=%s, source=%s, expire_date=%s,
                commissionable_premium=%s, net_od_premium=%s, tp_premium=%s,
                pbst_np=%s, gross_premium=%s, ncb=%s, policy_number=%s,
                make=%s, model_variant=%s, vehicle_category=%s,
                passengers_gvw=%s, vehicle_no=%s, cc=%s, fuel=%s,
                rto_name=%s, ref_name=%s, policy_pdf=%s, mail=%s, phone=%s
            WHERE id=%s
        """, (
            request.form["sr_no"],
            request.form["month"],
            request.form["cust_name"],
            request.form["insurer"],
            request.form["policy_type"],
            request.form["department"],
            request.form["source"],
            expire_date,
            clean_decimal(request.form.get("commissionable_premium")),
            clean_decimal(request.form.get("net_od_premium")),
            clean_decimal(request.form.get("tp_premium")),
            clean_decimal(request.form.get("pbst_np")),
            clean_decimal(request.form.get("gross_premium")),
            clean_decimal(request.form.get("ncb")),
            request.form["policy_number"],
            request.form["make"],
            request.form["model_variant"],
            request.form["vehicle_category"],
            request.form["passengers_gvw"],
            request.form["vehicle_no"],
            clean_decimal(request.form.get("cc")),
            request.form["fuel"],
            request.form["rto_name"],
            request.form["ref_name"],
            filename,
            request.form["mail"],
            request.form["phone"],
            id
        ))

        conn.commit()
        conn.close()
        return redirect(url_for("admin_dashboard"))

    cur.execute("SELECT * FROM policies WHERE id=%s", (id,))
    customer = cur.fetchone()
    conn.close()

    return render_template("pages/edit_customer.html", customer=customer)

# ---------------- UPDATE CUSTOMER ----------------

@app.route("/update_customer/<int:id>", methods=["POST"])
def update_customer(id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    data = request.form
    conn = get_db_connection()
    cur  = conn.cursor()

    expire_date = data.get("expire_date") or None

    cur.execute("""
        UPDATE policies SET
            sr_no=%s, month=%s, cust_name=%s, insurer=%s,
            policy_type=%s, department=%s, source=%s, expire_date=%s,
            commissionable_premium=%s, net_od_premium=%s, tp_premium=%s,
            pbst_np=%s, gross_premium=%s, ncb=%s, policy_number=%s,
            make=%s, model_variant=%s, vehicle_category=%s,
            passengers_gvw=%s, vehicle_no=%s, cc=%s, fuel=%s,
            rto_name=%s, ref_name=%s, mail=%s, phone=%s
        WHERE id=%s
    """, (
        data["sr_no"], data["month"], data["cust_name"], data["insurer"],
        data["policy_type"], data["department"], data["source"], expire_date,
        clean_decimal(data.get("commissionable_premium")),
        clean_decimal(data.get("net_od_premium")),
        clean_decimal(data.get("tp_premium")),
        clean_decimal(data.get("pbst_np")),
        clean_decimal(data.get("gross_premium")),
        clean_decimal(data.get("ncb")), data["policy_number"],
        data["make"], data["model_variant"], data["vehicle_category"],
        data["passengers_gvw"], data["vehicle_no"],
        clean_decimal(data.get("cc")),
        data["fuel"], data["rto_name"], data["ref_name"],
        data["mail"], data["phone"],
        id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("customers_search"))

# ---------------- DELETE CUSTOMER ----------------

@app.route("/delete_customer/<int:id>")
def delete_customer(id):
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM policies WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))

# ---------------- INSURANCES PAGE ----------------

@app.route("/insurances")
def insurances():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT policy_type,
               COUNT(*) AS policies,
               SUM(gross_premium) AS revenue
        FROM policies
        GROUP BY policy_type
    """)
    summary = cur.fetchall()

    cur.execute("""
        SELECT sr_no, month, cust_name, insurer, policy_type,
               department, source, expire_date,
               commissionable_premium, net_od_premium, tp_premium,
               pbst_np, gross_premium, ncb, policy_number,
               make, model_variant, vehicle_category,
               passengers_gvw, vehicle_no, cc, fuel,
               rto_name, ref_name, policy_pdf, mail, phone
        FROM policies
    """)
    policies = cur.fetchall()
    conn.close()

    return render_template("pages/insurances.html", summary=summary, policies=policies)

# ---------------- RENEWALS ----------------

@app.route("/renewals")
def renewals_page():
    if session.get("role") != "admin":
        return redirect(url_for("home"))
    return render_template("pages/renewals.html")

@app.route("/get_renewals")
def get_renewals():
    days        = request.args.get("days")
    policy_type = request.args.get("policy_type")

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    query  = "SELECT *, DATEDIFF(expire_date, CURDATE()) AS days_left FROM policies WHERE 1=1"
    params = []

    if days == "today":
        query += " AND DATEDIFF(expire_date, CURDATE()) = 0"
    elif days == "urgent":
        query += " AND DATEDIFF(expire_date, CURDATE()) BETWEEN 0 AND 2"
    elif days == "overdue":
        query += " AND DATEDIFF(expire_date, CURDATE()) < 0"
    elif days and days != "all":
        query += " AND DATEDIFF(expire_date, CURDATE()) BETWEEN 0 AND %s"
        params.append(int(days))
    else:
        query += " AND expire_date >= CURDATE()"

    if policy_type == "Vehicle":
        query += " AND policy_type IN ('Car', 'Bike', 'Scooty', 'Motor', 'Two Wheeler', 'Four Wheeler', 'Commercial Vehicle')"
    elif policy_type:
        query += " AND policy_type = %s"
        params.append(policy_type)
    cur.execute(query, params)
    renewals = cur.fetchall()
    conn.close()

    for r in renewals:
        if isinstance(r["expire_date"], str):
            r["expire_date"] = datetime.strptime(r["expire_date"], "%Y-%m-%d")
        r["expire_date"] = r["expire_date"].strftime("%Y-%m-%d")

    return jsonify(renewals)


# ---------------- SEND BULK EMAIL ----------------

@app.route("/send_bulk_email")
def send_bulk_email():
    if session.get("role") != "admin":
        return redirect(url_for("home"))

    days = request.args.get("days")

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    if days == "today":
        cur.execute("""
            SELECT * FROM policies
            WHERE DATEDIFF(expire_date, CURDATE()) = 0
        """)
    elif days == "urgent":
        cur.execute("""
            SELECT * FROM policies
            WHERE DATEDIFF(expire_date, CURDATE()) BETWEEN 0 AND 2
        """)
    else:
        cur.execute("""
            SELECT * FROM policies
            WHERE expire_date >= CURDATE()
        """)

    customers = cur.fetchall()
    conn.close()

    sender = os.environ.get("MAIL_USERNAME", "your_email@gmail.com")
    pw     = os.environ.get("MAIL_PASSWORD", "your_app_password")
    sent   = 0

    for c in customers:
        if not c["mail"]:
            continue
        try:
            msg = MIMEText(
                f"Dear {c['cust_name']},\n\n"
                f"Your policy expires on {c['expire_date']}. Please renew it.\n\n- NSure"
            )
            msg["Subject"] = "Policy Renewal Reminder"
            msg["From"]    = sender
            msg["To"]      = c["mail"]

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender, pw)
            server.send_message(msg)
            server.quit()
            sent += 1

        except Exception as e:
            print("Email error:", e)

    return jsonify({"sent": sent})

# ---------------- REVIEWS ----------------

@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    if request.method == "POST":
        name    = request.form.get("name")
        email   = request.form.get("email")
        phone   = request.form.get("phone")
        message = request.form.get("message")
        rating  = int(request.form.get("rating") or 0)

        review = Quote(
            name=name,
            email=email,
            phone=phone,
            message=message,
            rating=rating
        )
        db.session.add(review)
        db.session.commit()

        return redirect("/reviews")

    all_reviews = Quote.query.all()
    avg_rating  = db.session.query(db.func.avg(Quote.rating)).scalar()
    avg_rating  = round(avg_rating, 1) if avg_rating else 0

    return render_template("pages/reviews.html", reviews=all_reviews, avg_rating=avg_rating)

# ---------------- SETTINGS ----------------

@app.route("/settings")
def settings():
    if session.get("role") != "admin":
        return redirect(url_for("home"))
    return render_template("pages/settings.html")

@app.route("/settings_profile")
def settings_profile():
    if session.get("role") != "admin":
        return redirect(url_for("home"))
    return render_template("pages/profile.html")

@app.route("/settings_password")
def settings_password():
    if session.get("role") != "admin":
        return redirect(url_for("home"))
    return render_template("pages/change_password.html")

@app.route("/change_password", methods=["POST"])
def change_password():
    user_id = session.get("user_id")
    new     = request.form["new_password"]
    confirm = request.form["confirm_password"]

    if new != confirm:
        return "❌ Passwords do not match"

    conn = get_db_connection()
    cur  = conn.cursor()

    try:
        new_hash = generate_password_hash(new)
        cur.execute("UPDATE users SET password=%s WHERE id=%s", (new_hash, user_id))
        conn.commit()
        return "✅ Password updated successfully"
    except Exception as e:
        conn.rollback()
        return str(e)
    finally:
        cur.close()
        conn.close()

@app.route("/update_profile", methods=["POST"])
def update_profile():
    user_id = session.get("user_id")
    name    = request.form["name"]
    email   = request.form["email"]

    conn = get_db_connection()
    cur  = conn.cursor()

    try:
        cur.execute(
            "UPDATE users SET name=%s, email=%s WHERE id=%s",
            (name, email, user_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
    finally:
        cur.close()
        conn.close()

    return redirect("/admin_dashboard")

# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---------------- RUN APP ----------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)