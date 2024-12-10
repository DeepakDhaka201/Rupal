from flask import Blueprint, jsonify, current_app

from auth.utils import token_required

user_bp = Blueprint('user', __name__)


@user_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    try:
        return jsonify({
            'user': {
                'id': current_user.id,
                'name': current_user.name,
                'mobile': current_user.mobile,
                'wallet_balance': current_user.wallet_balance,
                'referral_code': current_user.referral_code,
                'created_at': int(current_user.created_at.timestamp() * 1000)
            },
            'support': {
                'email': current_app.config['SUPPORT_EMAIL'],
                'telegram': current_app.config['SUPPORT_TELEGRAM'],
                'hours': '10 AM - 6 PM IST'
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get profile error: {str(e)}")
        return jsonify({'error': 'Failed to get profile'}), 500
