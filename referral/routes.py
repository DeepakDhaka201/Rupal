from flask import Blueprint, request, jsonify, current_app
from models.models import (
    db, User, ReferralCommission, ReferralEarning,
    Transaction, TransactionStatus
)
from auth.utils import token_required
from datetime import datetime
from sqlalchemy import func

from transaction.utils import TransactionUtil

referral_bp = Blueprint('referral', __name__)

@referral_bp.route('/info', methods=['GET'])
@token_required
def get_referral_info(current_user):
    """Get user's referral information and earnings"""
    try:
        # Get direct referrals
        direct_referrals = User.query.filter_by(
            referred_by=current_user.id
        ).order_by(User.created_at.desc()).all()

        # Get total earnings
        total_earnings = db.session.query(
            func.sum(ReferralEarning.amount_usdt)
        ).filter_by(user_id=current_user.id).scalar() or 0

        # Get recent earnings
        recent_earnings = ReferralEarning.query.filter_by(
            user_id=current_user.id
        ).order_by(
            ReferralEarning.created_at.desc()
        ).limit(25).all()

        # Get commission rates
        commission_rates = ReferralCommission.query.filter_by(
            is_active=True
        ).order_by(ReferralCommission.level).all()

        rate = commission_rates[0] if commission_rates and len(commission_rates) > 0 else None

        return jsonify({
            'referral_code': current_user.referral_code,
            'total_referrals': len(direct_referrals),
            'total_earnings': round(float(total_earnings), 2),
            'recent_earnings': [{
                'id': earning.id,
                'amount_usdt': earning.amount_usdt,
                'commission_percent': earning.commission_percent,
                'level': earning.referral_level,
                'transaction_type': earning.transaction.transaction_type.value,
                'created_at': TransactionUtil.format_created_at_to_ist(earning.created_at),
            } for earning in recent_earnings],
            'referrals': [{
                'mobile': user.mobile,
                'name': user.name,
                'joined_at': TransactionUtil.format_created_at_to_ist(user.created_at),
                'status': user.status.value
            } for user in direct_referrals],
            'buy_commission': rate.buy_commission_percent if rate else 0.00,
            'sell_commission': rate.sell_commission_percent if rate else 0.00,
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get referral info error: {str(e)}")
        return jsonify({'error': 'Failed to fetch referral information'}), 500

@referral_bp.route('/earnings', methods=['GET'])
@token_required
def get_earnings(current_user):
    """
    Get detailed earnings history
    Query params:
    - page: int
    - per_page: int
    - from_date: YYYY-MM-DD
    - to_date: YYYY-MM-DD
    """
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        query = ReferralEarning.query.filter_by(user_id=current_user.id)

        if request.args.get('from_date'):
            query = query.filter(ReferralEarning.created_at >=
                               datetime.strptime(request.args.get('from_date'), '%Y-%m-%d'))
        if request.args.get('to_date'):
            query = query.filter(ReferralEarning.created_at <
                               datetime.strptime(request.args.get('to_date'), '%Y-%m-%d'))

        earnings = query.order_by(
            ReferralEarning.created_at.desc()
        ).paginate(page=page, per_page=per_page)

        return jsonify({
            'earnings': [{
                'id': earning.id,
                'amount_usdt': earning.amount_usdt,
                'commission_percent': earning.commission_percent,
                'level': earning.referral_level,
                'transaction_type': earning.transaction.transaction_type.value,
                'created_at': earning.created_at.isoformat()
            } for earning in earnings.items],
            'pagination': {
                'total_pages': earnings.pages,
                'current_page': page,
                'total_items': earnings.total
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get earnings error: {str(e)}")
        return jsonify({'error': 'Failed to fetch earnings'}), 500