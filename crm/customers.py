from flask import Blueprint, render_template
customers_bp = Blueprint('customers', __name__)

@customers_bp.route('/customers')
def customers():
    return render_template('customers.html')
