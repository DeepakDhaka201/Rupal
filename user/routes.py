from flask import Blueprint, jsonify, current_app, request

from auth.utils import token_required
from models.models import Setting

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
                'email': Setting.get_value('support.email'),
                'telegram': Setting.get_value('support.telegram'),
                'hours': '10 AM - 6 PM IST'
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get profile error: {str(e)}")
        return jsonify({'error': 'Failed to get profile'}), 500


@user_bp.route('/config', methods=['POST'])
def get_config():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Payload is required'}), 400

        version = int(data.get('version', 0))

        response = {
            "new_version": "1.0.0",
            "current_version": "1.0.0",
            "force_update": True,
        }

        return jsonify(response), 200
    except Exception as e:
        current_app.logger.error(f"Update profile error: {str(e)}")
        return jsonify({'error': 'Failed to update profile'}), 500
