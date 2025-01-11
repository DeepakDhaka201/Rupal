from flask import Blueprint, request, jsonify, current_app
from models.models import db, Transaction, User, BankAccount, TransactionType, TransactionStatus
from auth.utils import token_required
from sqlalchemy import func
from datetime import datetime, timedelta

from models.models import ReferralEarning
from transaction.utils import TransactionUtil

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/summary', methods=['GET'])
@token_required
def get_dashboard_summary(current_user):
    """
    Get dashboard summary including wallet balance, recent transactions,
    and transaction summaries
    """
    try:
        version = int(request.form.get("version", 0))
        print(version)

        return jsonify({
            'wallet_balance': current_user.wallet_balance,
            'user': {
                "id": current_user.id,
                "name": current_user.name,
                "mobile": current_user.mobile,
                "status": current_user.status.value
            },
            "new_version": "1.0.0",
            "current_version": "1.0.0",

            "force_update": True
        }), 200

    except Exception as e:
        current_app.logger.error(f"Dashboard summary error: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard summary'}), 500


@dashboard_bp.route('/analytics', methods=['GET'])
@token_required
def get_analytics(current_user):
    """
    Get detailed analytics
    Query params:
    - period: day/week/month/year (default: month)
    """
    try:
        period = request.args.get('period', 'month')

        # Calculate date range
        now = datetime.utcnow()
        if period == 'day':
            start_date = now - timedelta(days=1)
            interval = 'hour'
        elif period == 'week':
            start_date = now - timedelta(days=7)
            interval = 'day'
        elif period == 'year':
            start_date = now - timedelta(days=365)
            interval = 'month'
        else:  # month
            start_date = now - timedelta(days=30)
            interval = 'day'

        # Get volume analytics
        volume_data = db.session.query(
            func.date_trunc(interval, Transaction.created_at).label('date'),
            TransactionType,
            func.sum(Transaction.amount_usdt).label('volume')
        ).filter(
            Transaction.user_id == current_user.id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.created_at >= start_date
        ).group_by(
            'date',
            TransactionType
        ).all()

        # Format analytics data
        analytics = {}
        for date, tx_type, volume in volume_data:
            date_str = date.strftime('%Y-%m-%d %H:00' if interval == 'hour' else '%Y-%m-%d')
            if date_str not in analytics:
                analytics[date_str] = {
                    'buy': 0,
                    'sell': 0,
                    'deposit': 0,
                    'withdraw': 0
                }
            analytics[date_str][tx_type.value.lower()] = float(volume or 0)

        return jsonify({
            'period': period,
            'interval': interval,
            'data': [{
                'date': date,
                **volumes
            } for date, volumes in analytics.items()]
        }), 200

    except Exception as e:
        current_app.logger.error(f"Analytics error: {str(e)}")
        return jsonify({'error': 'Failed to fetch analytics'}), 500


@dashboard_bp.route('/referrals', methods=['GET'])
@token_required
def get_referral_summary(current_user):
    """Get referral summary and earnings"""
    try:
        # Get referred users
        referred_users = User.query.filter_by(
            referred_by=current_user.id
        ).all()

        # Get referral earnings
        earnings = db.session.query(
            func.sum(ReferralEarning.amount_usdt),
            func.count(ReferralEarning.id)
        ).filter_by(
            user_id=current_user.id
        ).first()

        # Get recent earnings
        recent_earnings = ReferralEarning.query.filter_by(
            user_id=current_user.id
        ).order_by(
            ReferralEarning.created_at.desc()
        ).limit(5).all()

        return jsonify({
            'referral_code': current_user.referral_code,
            'total_referrals': len(referred_users),
            'total_earnings': float(earnings[0] or 0),
            'total_transactions': earnings[1],
            'referred_users': [{
                'mobile': user.mobile,
                'joined_at': user.created_at.isoformat(),
                'status': user.status.value
            } for user in referred_users],
            'recent_earnings': [{
                'amount_usdt': earning.amount_usdt,
                'level': earning.referral_level,
                'created_at': earning.created_at.isoformat()
            } for earning in recent_earnings]
        }), 200

    except Exception as e:
        current_app.logger.error(f"Referral summary error: {str(e)}")
        return jsonify({'error': 'Failed to fetch referral summary'}), 500


@dashboard_bp.route('/pending-actions', methods=['GET'])
@token_required
def get_pending_actions(current_user):
    """Get pending actions requiring user attention"""
    try:
        # Get pending transactions
        pending_transactions = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.status.in_([
                TransactionStatus.PENDING,
                TransactionStatus.PROCESSING
            ])
        ).order_by(Transaction.created_at.desc()).all()

        # Get unverified bank accounts
        unverified_accounts = BankAccount.query.filter_by(
            user_id=current_user.id,
            is_verified=False
        ).all()

        return jsonify({
            'pending_transactions': [{
                'id': tx.id,
                'type': tx.transaction_type.value,
                'amount_usdt': tx.amount_usdt,
                'status': tx.status.value,
                'created_at': tx.created_at.isoformat()
            } for tx in pending_transactions],
            'unverified_accounts': [{
                'id': account.id,
                'bank_name': account.bank_name,
                'account_number': f"XXXX{account.account_number[-4:]}"
            } for account in unverified_accounts]
        }), 200

    except Exception as e:
        current_app.logger.error(f"Pending actions error: {str(e)}")
        return jsonify({'error': 'Failed to fetch pending actions'}), 500
