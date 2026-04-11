from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Quote(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    insurance_type = db.Column(db.String(100))
    message = db.Column(db.Text)

    rating = db.Column(db.Integer, default=5)