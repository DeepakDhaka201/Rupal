import random
import string
from functools import wraps
from flask import request, jsonify, current_app
import jwt
from datetime import datetime, timedelta
import requests

from models import db
from models.models import UserStatus, User, OTP


def generate_otp():
    """Generate 6 digit OTP"""
    return ''.join(random.choices(string.digits, k=6))


def generate_referral_code():
    """Generate unique 8 character referral code"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not User.query.filter_by(referral_code=code).first():
            return code


def send_sms_otp(mobile, otp):
    """Send OTP via SMS"""
    try:

        message = "Verify+Mobile,+No.+Your+OTP+is+{}+To+Login+in+App+ARNAV".format(otp)

        url = "http://sms.smslab.in/api/sendhttp.php"
        params = {
            "authkey": "393055AeJCj8aMhr836419c96fP1",
            "mobiles": "91" + mobile,
            "message": message,
            "sender": "ARVIPT",
            "route": 4,
            "country": 91,
            "DLT_TE_ID": "1307167958154244221"
        }

        response = requests.get(url, params=params)
        return response.ok
    except Exception as e:
        current_app.logger.error(f"SMS send error: {str(e)}")
        return False


def create_access_token(user_id):
    """Create JWT token"""
    expiry = datetime.utcnow() + timedelta(days=1)
    return jwt.encode(
        {
            'user_id': user_id,
            'exp': expiry,
            'iat': datetime.utcnow()
        },
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')

        if auth_header:
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            data = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
            if current_user.status != UserStatus.ACTIVE:
                return jsonify({'error': 'Account is not active'}), 403
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(current_user, *args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')

        if auth_header:
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            data = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
            current_user = User.query.get(data['user_id'])
            if not current_user or not current_user.is_admin:
                return jsonify({'error': 'Admin access required'}), 403
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(current_user, *args, **kwargs)

    return decorated


def cleanup_expired_otps():
    """Cleanup expired OTPs"""
    try:
        expiry_time = datetime.utcnow() - timedelta(
            minutes=current_app.config['OTP_VALIDITY_MINUTES']
        )

        # Mark expired OTPs
        expired_otps = OTP.query.filter(
            OTP.created_at < expiry_time,
            OTP.is_verified == False
        ).all()

        for otp in expired_otps:
            otp.is_verified = True
            otp.error_message = 'Expired'

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"OTP cleanup error: {str(e)}")
