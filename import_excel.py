import pandas as pd
import mysql.connector

# Read Excel file
df = pd.read_excel("book123.xlsx")

# Clean column names (remove spaces)
df.columns = df.columns.str.strip()

conn = mysql.connector.connect(
    host="127.0.0.1",
    user="crmuser",
    password="1234",
    database="insurance_crm"
)

cur = conn.cursor()


for index, row in df.iterrows():

    # ✅ FIX DATE HERE
    expire_date = row["Expire Date"]

    if pd.notna(expire_date) and expire_date != "":
        try:
            expire_date = pd.to_datetime(expire_date, dayfirst=True).strftime("%Y-%m-%d")
        except:
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
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        row["Sr No"],
        row["Month"],
        row["CustName"],
        row["Insurer"],
        row["Policy Type"],
        row["Department"],
        row["Source"],
        expire_date,  # ✅ FIXED HERE
        row["Commissionable Premium"],
        row["Net/OD Premium"],
        row["TPPremium"],
        row["PBST(NP)"],
        row["Gross Premium"],
        row["NCB"],
        row["PolicyNo"],
        row["Make"],
        row["Model/Variant"],
        row["GCV/PCV/Misc."],
        row["No.Passengers/GVW"],
        row["Vehicle_No."],
        row["CC"],
        row["Fuel"],
        row["RTOName"],
        row["REF NAME"],
        row["Policy_pdf"],
        row["Mail"],
        row["Phone"]
    ))

conn.commit()
conn.close()

print("✅ All Excel Data Imported Successfully")