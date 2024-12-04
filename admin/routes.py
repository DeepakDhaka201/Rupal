from flask import Blueprint, request, jsonify, current_app
from models.models import (
    db, User, Transaction, BankAccount, PooledWallet,
    TransactionStatus, UserStatus, ReferralCommission
)
from auth.utils import admin_required
from transaction.utils import TransactionUtil
from sqlalchemy import func
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)


# Transaction Management
@admin_bp.route('/transactions', methods=['GET'])
@admin_required
def get_transactions():
    """
    Get all transactions with filters
    Query params:
        - type: BUY/SELL/DEPOSIT/WITHDRAW
        - status: PENDING/PROCESSING/COMPLETED/FAILED
        - from_date: YYYY-MM-DD
        - to_date: YYYY-MM-DD
        - user_id: int
        - page: int
        - per_page: int
    """
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # Build query
        query = Transaction.query

        # Apply filters
        if request.args.get('type'):
            query = query.filter_by(transaction_type=request.args.get('type'))
        if request.args.get('status'):
            query = query.filter_by(status=request.args.get('status'))
        if request.args.get('user_id'):
            query = query.filter_by(user_id=int(request.args.get('user_id')))
        if request.args.get('from_date'):
            query = query.filter(Transaction.created_at >= datetime.strptime(request.args.get('from_date'), '%Y-%m-%d'))
        if request.args.get('to_date'):
            query = query.filter(
                Transaction.created_at < datetime.strptime(request.args.get('to_date'), '%Y-%m-%d') + timedelta(days=1))

        transactions = query.order_by(Transaction.created_at.desc()).paginate(
            page=page, per_page=per_page
        )

        return jsonify({
            'transactions': [{
                'id': tx.id,
                'user_id': tx.user_id,
                'user_mobile': tx.user.mobile,
                'type': tx.transaction_type.value,
                'amount_usdt': tx.amount_usdt,
                'amount_inr': tx.amount_inr,
                'status': tx.status.value,
                'created_at': tx.created_at.isoformat(),
                'completed_at': tx.completed_at.isoformat() if tx.completed_at else None,
                'blockchain_txn_id': tx.blockchain_txn_id,
                'bank_account': {
                    'bank_name': tx.bank_account.bank_name,
                    'account_number': tx.bank_account.account_number
                } if tx.bank_account else None
            } for tx in transactions.items],
            'pagination': {
                'total_pages': transactions.pages,
                'current_page': page,
                'total_items': transactions.total
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Admin get transactions error: {str(e)}")
        return jsonify({'error': 'Failed to fetch transactions'}), 500


@admin_bp.route('/transactions/<int:transaction_id>/process', methods=['POST'])
@admin_required
def process_transaction(transaction_id):
    """
    Process transaction (approve/reject)
    Request: {
        "action": "APPROVE" | "REJECT",
        "reason": "Optional reason for rejection",
        "blockchain_txn_id": "Required for withdrawal approval"
    }
    """
    try:
        data = request.get_json()
        if not data or 'action' not in data:
            return jsonify({'error': 'Action is required'}), 400

        transaction = Transaction.query.get_or_404(transaction_id)
        action = data['action'].upper()

        if action not in ['APPROVE', 'REJECT']:
            return jsonify({'error': 'Invalid action'}), 400

        if action == 'APPROVE':
            if transaction.transaction_type == 'WITHDRAW' and 'blockchain_txn_id' not in data:
                return jsonify({'error': 'Blockchain transaction ID required for withdrawal'}), 400

            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.utcnow()

            if transaction.transaction_type == 'BUY':
                # Credit USDT to user's wallet
                user = User.query.get(transaction.user_id)
                user.wallet_balance += transaction.amount_usdt
                TransactionUtil.process_referral_commission(transaction)

            elif transaction.transaction_type == 'WITHDRAW':
                transaction.blockchain_txn_id = data['blockchain_txn_id']

        else:  # REJECT
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = data.get('reason', 'Rejected by admin')

            if transaction.transaction_type in ['SELL', 'WITHDRAW']:
                # Refund amount to user's wallet
                user = User.query.get(transaction.user_id)
                refund_amount = transaction.amount_usdt
                if transaction.transaction_type == 'WITHDRAW':
                    refund_amount += transaction.fee_usdt
                user.wallet_balance += refund_amount

        db.session.commit()

        return jsonify({
            'message': f'Transaction {action.lower()}d successfully',
            'transaction': {
                'id': transaction.id,
                'status': transaction.status.value
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Process transaction error: {str(e)}")
        return jsonify({'error': 'Failed to process transaction'}), 500


# User Management
@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users with filters"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status = request.args.get('status')
        search = request.args.get('search')  # Search by mobile

        query = User.query

        if status:
            query = query.filter_by(status=UserStatus[status])
        if search:
            query = query.filter(User.mobile.like(f'%{search}%'))

        users = query.paginate(page=page, per_page=per_page)

        return jsonify({
            'users': [{
                'id': user.id,
                'mobile': user.mobile,
                'wallet_balance': user.wallet_balance,
                'status': user.status.value,
                'created_at': user.created_at.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
                'referral_code': user.referral_code,
                'referred_by': user.referred_by
            } for user in users.items],
            'pagination': {
                'total_pages': users.pages,
                'current_page': page,
                'total_items': users.total
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get users error: {str(e)}")
        return jsonify({'error': 'Failed to fetch users'}), 500


@admin_bp.route('/users/<int:user_id>/status', methods=['POST'])
@admin_required
def update_user_status(user_id):
    """
    Update user status
    Request: {
        "status": "ACTIVE" | "SUSPENDED",
        "reason": "Optional reason"
    }
    """
    try:
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400

        user = User.query.get_or_404(user_id)
        new_status = UserStatus[data['status']]

        user.status = new_status
        db.session.commit()

        return jsonify({
            'message': 'User status updated successfully',
            'user': {
                'id': user.id,
                'status': user.status.value
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Update user status error: {str(e)}")
        return jsonify({'error': 'Failed to update user status'}), 500


# Bank Account Management
@admin_bp.route('/bank-accounts/verify', methods=['POST'])
@admin_required
def verify_bank_account():
    """
    Verify bank account
    Request: {
        "account_id": 1,
        "status": true/false,
        "reason": "Optional reason for rejection"
    }
    """
    try:
        data = request.get_json()
        if not data or 'account_id' not in data or 'status' not in data:
            return jsonify({'error': 'Account ID and status are required'}), 400

        account = BankAccount.query.get_or_404(data['account_id'])
        account.is_verified = data['status']
        account.verified_at = datetime.utcnow() if data['status'] else None
        account.verification_notes = data.get('reason')

        db.session.commit()

        return jsonify({
            'message': 'Bank account verification updated',
            'account': {
                'id': account.id,
                'is_verified': account.is_verified
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Bank account verification error: {str(e)}")
        return jsonify({'error': 'Failed to update verification status'}), 500


# Wallet Pool Management
@admin_bp.route('/wallet-pool/add', methods=['POST'])
@admin_required
def add_pool_wallet():
    """
    Add new wallet to pool
    Request: {
        "address": "TRx..."
    }
    """
    try:
        data = request.get_json()
        if not data or 'address' not in data:
            return jsonify({'error': 'Address is required'}), 400

        if not TransactionUtil.validate_tron_address(data['address']):
            return jsonify({'error': 'Invalid TRON address'}), 400

        existing_wallet = PooledWallet.query.filter_by(address=data['address']).first()
        if existing_wallet:
            return jsonify({'error': 'Address already exists in pool'}), 400

        wallet = PooledWallet(
            address=data['address'],
            status='AVAILABLE',
            created_by=request.user.id
        )

        db.session.add(wallet)
        db.session.commit()

        return jsonify({
            'message': 'Wallet added to pool successfully',
            'wallet': {
                'id': wallet.id,
                'address': wallet.address
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Add pool wallet error: {str(e)}")
        return jsonify({'error': 'Failed to add wallet to pool'}), 500


# Dashboard and Analytics
@admin_bp.route('/dashboard/summary', methods=['GET'])
@admin_required
def get_admin_dashboard():
    """Get admin dashboard summary"""
    try:
        # Get today's stats
        today = datetime.utcnow().replace(hour=0, minute=0, second=0)

        stats = {
            'users': {
                'total': User.query.count(),
                'active': User.query.filter_by(status=UserStatus.ACTIVE).count(),
                'today': User.query.filter(User.created_at >= today).count()
            },
            'transactions': {
                'pending': Transaction.query.filter_by(status=TransactionStatus.PENDING).count(),
                'processing': Transaction.query.filter_by(status=TransactionStatus.PROCESSING).count(),
                'today': Transaction.query.filter(Transaction.created_at >= today).count()
            },
            'volume': {
                'buy': db.session.query(func.sum(Transaction.amount_usdt))
                       .filter(Transaction.transaction_type == 'BUY',
                               Transaction.status == TransactionStatus.COMPLETED).scalar() or 0,
                'sell': db.session.query(func.sum(Transaction.amount_usdt))
                        .filter(Transaction.transaction_type == 'SELL',
                                Transaction.status == TransactionStatus.COMPLETED).scalar() or 0
            }
        }

        return jsonify(stats), 200

    except Exception as e:
        current_app.logger.error(f"Admin dashboard error: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard summary'}), 500


# Commission Management
@admin_bp.route('/commission/settings', methods=['GET', 'POST'])
@admin_required
def manage_commission_settings():
    """Manage referral commission settings"""
    if request.method == 'GET':
        try:
            settings = ReferralCommission.query.order_by(ReferralCommission.level).all()
            return jsonify({
                'settings': [{
                    'id': setting.id,
                    'level': setting.level,
                    'buy_commission_percent': setting.buy_commission_percent,
                    'sell_commission_percent': setting.sell_commission_percent,
                    'min_amount_usdt': setting.min_amount_usdt,
                    'is_active': setting.is_active
                } for setting in settings]
            }), 200

        except Exception as e:
            current_app.logger.error(f"Get commission settings error: {str(e)}")
            return jsonify({'error': 'Failed to fetch commission settings'}), 500

    else:  # POST
        try:
            data = request.get_json()
            if not data or not all(k in data for k in [
                'level', 'buy_commission_percent', 'sell_commission_percent'
            ]):
                return jsonify({'error': 'Required fields missing'}), 400

            setting = ReferralCommission.query.filter_by(level=data['level']).first()
            if not setting:
                setting = ReferralCommission(level=data['level'])

            setting.buy_commission_percent = data['buy_commission_percent']
            setting.sell_commission_percent = data['sell_commission_percent']
            setting.min_amount_usdt = data.get('min_amount_usdt', 0)
            setting.is_active = data.get('is_active', True)

            db.session.add(setting)
            db.session.commit()

            return jsonify({
                'message': 'Commission settings updated successfully',
                'setting': {
                    'id': setting.id,
                    'level': setting.level,
                    'buy_commission_percent': setting.buy_commission_percent,
                    'sell_commission_percent': setting.sell_commission_percent
                }
            }), 200

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Update commission settings error: {str(e)}")
            return jsonify({'error': 'Failed to update commission settings'}), 500