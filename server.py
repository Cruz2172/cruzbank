from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import random
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


# Fix #1: corrected typo login_manger -> login_manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")

def generate_account_number():
    return str(random.randint(1000000000, 9999999999))

db = SQLAlchemy(app)

class User(db.Model, UserMixin):
    id         = db.Column(db.Integer, primary_key=True)
    fullname   = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20), nullable=False)
    email      = db.Column(db.String(120), nullable=False, unique=True)
    password   = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    balance    = db.Column(db.Float, default=0.0)
    acc_no     = db.Column(db.String(10), unique=True, nullable=False, default=generate_account_number)

class Transaction(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type        = db.Column(db.String(10), nullable=False)
    account     = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(100), nullable=False)
    timestamp   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# Fix #2: decorator now uses correctly spelled login_manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        fullname = request.form.get("fullname")
        phone    = request.form.get("phone")
        email    = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))

        if User.query.filter_by(email=email).first():
            # Fix #4: was flash("...", 'danger') with mismatched quotes
            flash("Email already registered. Please log in.", 'danger')
            return redirect(url_for("login"))

        new_user = User(fullname=fullname, phone=phone, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration Successful!", 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", 'success')
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", 'danger')

    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    user         = current_user
    transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp.desc()).all()
    return render_template('dashboard.html', user=user, transactions=transactions)


@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    user = current_user
    if request.method == "POST":
        amount      = float(request.form.get("amount"))
        description = request.form.get("description") or "Deposit"

        if amount < 50:
            flash("Deposit amount must be at least ₦50.", 'danger')
            return redirect(url_for('deposit'))

        user.balance += amount
        txn = Transaction(user_id=user.id, type='deposit', account=amount, description=description)
        db.session.add(txn)
        db.session.commit()
        flash("Deposit successful!", 'success')
        return redirect(url_for('dashboard'))

    return render_template('deposit.html', user=user)


@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    user = current_user
    if request.method == "POST":
        amount      = float(request.form.get('amount'))
        description = request.form.get('description') or "Withdrawal"

        if amount < 50:
            flash("Withdrawal amount must be at least ₦50.", 'danger')
            return redirect(url_for('withdraw'))

        # Fix #3: added missing return so balance isn't deducted on insufficient funds
        if amount > user.balance:
            flash("Insufficient balance.", 'danger')
            return redirect(url_for('withdraw'))

        user.balance -= amount
        txn = Transaction(user_id=user.id, type='withdraw', account=amount, description=description)
        db.session.add(txn)
        db.session.commit()
        flash("Withdrawal successful!", 'success')
        return redirect(url_for('dashboard'))

    return render_template('withdraw.html', user=user)


@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    user = current_user
    if request.method == "POST":
        recipient_acc_no = request.form.get("recipient", "").strip()
        description      = request.form.get("description") or "Transfer"

        try:
            amount = float(request.form.get("amount"))
        except (TypeError, ValueError):
            flash("Please enter a valid amount.", 'danger')
            return redirect(url_for('transfer'))

        if amount < 50:
            flash("Transfer amount must be at least ₦50.", 'danger')
            return redirect(url_for('transfer'))

        if amount > user.balance:
            flash("Insufficient balance for this transfer.", 'danger')
            return redirect(url_for('transfer'))

        recipient = User.query.filter_by(acc_no=recipient_acc_no).first()
        if not recipient:
            flash("Recipient account number not found.", 'danger')
            return redirect(url_for('transfer'))

        if recipient.id == user.id:
            flash("You cannot transfer money to yourself.", 'danger')
            return redirect(url_for('transfer'))

        user.balance      -= amount
        recipient.balance += amount

        txn_sender    = Transaction(user_id=user.id, type='transfer_out', account=amount,
                                    description=f"Transfer to {recipient.fullname} ({recipient.acc_no}): {description}")
        txn_recipient = Transaction(user_id=recipient.id, type='transfer_in', account=amount,
                                    description=f"Transfer from {user.fullname} ({user.acc_no}): {description}")
        db.session.add(txn_sender)
        db.session.add(txn_recipient)
        db.session.commit()
        flash("Transfer successful!", 'success')
        return redirect(url_for('dashboard'))

    return render_template('transfer.html', user=user)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", 'info')
    return redirect(url_for('home'))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")