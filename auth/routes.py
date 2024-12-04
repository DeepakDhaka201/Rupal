import re
from flask import Blueprint, request, jsonify, current_app
from models import db
from models.models import User, OTP, UserStatus
from .utils import generate_otp, generate_referral_code, send_sms_otp, create_access_token, token_required
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/send-otp', methods=['POST'])
def send_otp():
    """
    Send OTP for both login and signup
    ---
    Request:
    {
        "mobile": "1234567890"
    }
    Response: {
        "message": "OTP sent successfully",
        "mobile": "1234567890",
        "validity_minutes": 10,
        "user_exists": true/false
    }
    """
    try:
        data = request.get_json()
        if not data or 'mobile' not in data:
            return jsonify({'error': 'Mobile number is required'}), 400

        mobile = data['mobile']

        # Validate mobile number format
        if not re.match(r'^\d{10}$', mobile):
            return jsonify({'error': 'Invalid mobile number format'}), 400

        # Check if user exists
        user = User.query.filter_by(mobile=mobile).first()
        user_exists = bool(user)

        # Generate and save OTP
        otp = generate_otp()
        new_otp = OTP(
            mobile=mobile,
            otp=otp,
            purpose='AUTH'  # Single purpose for both login/signup
        )

        # Invalidate previous unused OTPs
        OTP.query.filter_by(
            mobile=mobile,
            is_verified=False
        ).update({
            'is_verified': True
        })

        db.session.add(new_otp)
        db.session.commit()

        # Send OTP
        if not send_sms_otp(mobile, otp):
            return jsonify({'error': 'Failed to send OTP'}), 500

        return jsonify({
            'message': 'OTP sent successfully',
            'mobile': mobile,
            'validity_minutes': current_app.config['OTP_VALIDITY_MINUTES'],
            'user_exists': user_exists
        }), 200

    except Exception as e:
        current_app.logger.error(f"Send OTP error: {str(e)}")
        return jsonify({'error': 'Failed to process request'}), 500


@auth_bp.route('/authenticate', methods=['POST'])
def authenticate():
    """
    Authenticate user (handles both login and signup)
    ---
    Request:
    {
        "mobile": "1234567890",
        "name": "Rai" // Required for signup
        "otp": "123456",
        "wallet_pin": "1234",  // Required for signup
        "referral_code": "ABC123"  // Optional, for signup
    }
    """
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['mobile', 'otp']):
            return jsonify({'error': 'Mobile and OTP are required'}), 400

        # Verify OTP
        otp_record = OTP.query.filter_by(
            mobile=data['mobile'],
            otp=data['otp'],
            purpose='AUTH',
            is_verified=False
        ).order_by(OTP.created_at.desc()).first()

        if not otp_record:
            return jsonify({'error': 'Invalid OTP'}), 400

        # Check OTP expiry
        expiry_time = otp_record.created_at + timedelta(
            minutes=current_app.config['OTP_VALIDITY_MINUTES']
        )
        if datetime.utcnow() > expiry_time:
            otp_record.error_message = 'OTP expired'
            db.session.commit()
            return jsonify({
                'error': 'OTP has expired',
                'code': 'OTP_EXPIRED'
            }), 400

        # Check if user exists
        user = User.query.filter_by(mobile=data['mobile']).first()

        if user:
            # Login flow
            if user.status != UserStatus.ACTIVE:
                return jsonify({
                    'error': 'Account is not active',
                    'status': user.status.value
                }), 403

            user.last_login = datetime.utcnow()
        else:
            # Signup flow
            if 'wallet_pin' not in data:
                return jsonify({'error': 'Wallet PIN is required for signup'}), 400

            if 'name' not in data:
                return jsonify({'error': 'Name is required for signup'}), 400

            user = User(
                mobile=data['mobile'],
                name=data['name'],
                status=UserStatus.ACTIVE,
                referral_code=generate_referral_code()
            )
            user.set_wallet_pin(data['wallet_pin'])

            # Handle referral
            if 'referral_code' in data:
                referrer = User.query.filter_by(
                    referral_code=data['referral_code']
                ).first()
                if referrer:
                    user.referred_by = referrer.id

            db.session.add(user)

        # Mark OTP as verified and commit changes
        otp_record.is_verified = True
        db.session.commit()

        # Generate token
        token = create_access_token(user.id)

        return jsonify({
            'message': 'Authentication successful',
            'is_new_user': not bool(user.last_login),
            'token': token,
            'user': {
                'id': user.id,
                'name': user.name,
                'mobile': user.mobile,
                'wallet_balance': user.wallet_balance,
                'referral_code': user.referral_code,
                'status': user.status.value,
                'is_admin': user.is_admin
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Authentication error: {str(e)}")
        return jsonify({'error': 'Authentication failed'}), 500
