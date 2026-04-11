# Insurance CRM Business Application

A web-based Customer Relationship Management (CRM) system designed for insurance businesses to manage customers, policies, quotes, and renewals efficiently.

## 🚀 Features

- User authentication (login system)
- Admin dashboard with analytics
- Customer management (add, edit, search)
- Insurance policy tracking
- Quote request handling
- Renewal tracking
- Review & feedback system
- Excel data import support

## 🛠️ Tech Stack

- Backend: Flask (Python)
- Database: SQL (via SQLAlchemy)
- Frontend: HTML, CSS, Jinja Templates
- Other Tools: Excel integration (openpyxl/pandas)

## 📂 Project Structure
INSURANCE_CRM_BUSINESS/
│── app.py # Main application entry point
│── config.py # Configuration settings
│── models.py # Database models
│── import_excel.py # Excel data import logic
│── requirements.txt # Dependencies
│
├── auth/ # Authentication module
├── crm/ # CRM modules (customers, dashboard)
├── database/ # SQL schema
├── static/ # Images and static files
├── templates/ # HTML templates


## ⚙️ Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/insurance-crm.git
cd insurance-crm
Create virtual environment:
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
Install dependencies:
pip install -r requirements.txt
Setup database:
Run the SQL file inside database/schema.sql
Or configure using SQLAlchemy
Run the application:
python app.py
Open in browser:
http://127.0.0.1:5000/
