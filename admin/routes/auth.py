# auth/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify

from auth.utils import generate_otp, send_sms_otp
from models.models import db, User, OTP
from datetime import datetime

admin_auth_bp = Blueprint('admin_auth', __name__)


@admin_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        otp = request.form.get('otp')

        if not mobile or not otp:
            flash('Both mobile and OTP are required', 'error')
            return redirect(url_for('auth.login'))

        # Verify OTP
        otp_record = OTP.query.filter_by(
            mobile=mobile,
            otp=otp,
            purpose='LOGIN',
            is_verified=False
        ).first()

        if not otp_record:
            flash('Invalid OTP', 'error')
            return redirect(url_for('auth.login'))

        # Get user
        user = User.query.filter_by(mobile=mobile, is_admin=True).first()
        if not user or not user.is_admin:
            flash('Unauthorized access', 'error')
            return redirect(url_for('auth.login'))

        # Update user and OTP
        user.last_login = datetime.utcnow()
        otp_record.is_verified = True
        session['user_id'] = user.id
        session['is_admin'] = True

        db.session.commit()

        return redirect(url_for('admin_users.users'))

    return render_template('auth/login.html')


@admin_auth_bp.route('/send-otp', methods=['POST'])
def send_otp():
    mobile = request.form.get('mobile')
    if not mobile:
        return jsonify({'error': 'Mobile number is required'}), 400

    # Check if admin user exists
    user = User.query.filter_by(mobile=mobile, is_admin=True).first()
    if not user:
        return jsonify({'error': 'Unauthorized access'}), 403

    # Generate and save OTP
    otp = generate_otp()  # Your OTP generation function
    new_otp = OTP(
        mobile=mobile,
        otp=otp,
        purpose='LOGIN'
    )

    db.session.add(new_otp)
    db.session.commit()

    # Send OTP (implement your SMS sending logic)
    send_sms_otp(mobile, otp)  # Your SMS sending function

    return jsonify({'message': 'OTP sent successfully'})


@admin_auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin_auth.login'))
