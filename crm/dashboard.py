from flask import Blueprint, render_template, session, redirect
import mysql.connector
from datetime import date

dashboard_bp = Blueprint("dashboard", __name__)

def get_db_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="insurance_crm"
    )

@dashboard_bp.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    if session["role"] == "admin":

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # TOTAL CUSTOMERS
        cursor.execute("SELECT COUNT(*) AS total FROM customers")
        total_customers = cursor.fetchone()["total"]

        # TOTAL POLICIES
        cursor.execute("SELECT COUNT(*) AS total FROM policies")
        total_policies = cursor.fetchone()["total"]

        # TODAY REVENUE
        cursor.execute("""
        SELECT SUM(gross_premium) AS total
        FROM policies
        WHERE DATE(created_at) = CURDATE()
        """)
        daily_revenue = cursor.fetchone()["total"] or 0

        # MONTHLY REVENUE
        cursor.execute("""
        SELECT SUM(gross_premium) AS total
        FROM policies
        WHERE MONTH(created_at)=MONTH(CURDATE())
        AND YEAR(created_at)=YEAR(CURDATE())
        """)
        monthly_revenue = cursor.fetchone()["total"] or 0

        # DAILY CHART
        cursor.execute("""
        SELECT DATE(created_at) as day, SUM(gross_premium) as total
        FROM policies
        GROUP BY day
        ORDER BY day
        LIMIT 7
        """)
        daily_rows = cursor.fetchall()

        daily_labels = [str(r["day"]) for r in daily_rows]
        daily_data = [float(r["total"]) for r in daily_rows]

        # WEEKLY CHART
        cursor.execute("""
        SELECT WEEK(created_at) as week, SUM(gross_premium) as total
        FROM policies
        GROUP BY week
        ORDER BY week
        LIMIT 7
        """)
        weekly_rows = cursor.fetchall()

        weekly_labels = [f"Week {r['week']}" for r in weekly_rows]
        weekly_data = [float(r["total"]) for r in weekly_rows]

        # MONTHLY CHART
        cursor.execute("""
        SELECT MONTH(created_at) as month, SUM(gross_premium) as total
        FROM policies
        GROUP BY month
        ORDER BY month
        """)
        monthly_rows = cursor.fetchall()

        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

        monthly_labels = [month_names[r["month"]-1] for r in monthly_rows]
        monthly_data = [float(r["total"]) for r in monthly_rows]

        # YEARLY CHART
        cursor.execute("""
        SELECT YEAR(created_at) as year, SUM(gross_premium) as total
        FROM policies
        GROUP BY year
        ORDER BY year
        """)
        yearly_rows = cursor.fetchall()

        yearly_labels = [str(r["year"]) for r in yearly_rows]
        yearly_data = [float(r["total"]) for r in yearly_rows]

        conn.close()

        return render_template(
            "admin_dashboard.html",

            total_customers=total_customers,
            total_policies=total_policies,
            daily_revenue=daily_revenue,
            monthly_revenue=monthly_revenue,

            daily_labels=daily_labels,
            daily_data=daily_data,

            weekly_labels=weekly_labels,
            weekly_data=weekly_data,

            monthly_labels=monthly_labels,
            monthly_data=monthly_data,

            yearly_labels=yearly_labels,
            yearly_data=yearly_data
        )