# admin/routes/transactions.py
from flask import Blueprint, render_template, request, jsonify, flash

from auth.utils import admin_required
from models.models import db, Transaction, TransactionType, TransactionStatus, Claim, PaymentMode, ReferralCommission, \
    ReferralEarning
from sqlalchemy import desc
from datetime import datetime, timedelta

admin_transactions_bp = Blueprint('admin_transactions', __name__)


@admin_transactions_bp.route('/transactions')
@admin_required
def transactions_list(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Filters
    tx_type = request.args.get('type')
    status = request.args.get('status')
    search = request.args.get('search', '')  # Search by rupal_id or user mobile
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = Transaction.query.join(Transaction.user)

    if tx_type:
        query = query.filter(Transaction.transaction_type == TransactionType(tx_type))
    if status:
        query = query.filter(Transaction.status == TransactionStatus(status))
    if search:
        query = query.filter(
            (Transaction.rupal_id.like(f'%{search}%')) |
            (Transaction.user.has(mobile=search))
        )
    if date_from:
        query = query.filter(Transaction.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(Transaction.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))

    transactions = query.order_by(desc(Transaction.created_at)).paginate(
        page=page, per_page=per_page
    )

    return render_template('admin/transactions/list.html',
                           transactions=transactions,
                           TransactionType=TransactionType,
                           TransactionStatus=TransactionStatus,
                           search=search,
                           type=tx_type,
                           status=status,
                           date_from=date_from,
                           date_to=date_to
                           )


@admin_transactions_bp.route('/transactions/<int:transaction_id>')
@admin_required
def transaction_detail(current_user, transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    return render_template('admin/transactions/detail.html',
                           transaction=transaction,
                           PaymentMode=PaymentMode
                           )


# @admin_transactions_bp.route('/transactions/<int:transaction_id>/update-status', methods=['POST'])
# def update_transaction_status(transaction_id):
#     transaction = Transaction.query.get_or_404(transaction_id)
#     new_status = request.form.get('status')
#     admin_notes = request.form.get('admin_notes')
#
#     if new_status not in [status.value for status in TransactionStatus]:
#         return jsonify({'success': False, 'message': 'Invalid status'}), 400
#
#     try:
#         old_status = transaction.status
#         transaction.status = TransactionStatus(new_status)
#         transaction.admin_notes = admin_notes
#
#         if new_status == 'COMPLETED':
#             transaction.completed_at = datetime.utcnow()
#
#             # Handle claim if exists
#             if transaction.claim_id:
#                 claim = Claim.query.get(transaction.claim_id)
#                 claim.status = 'COMPLETED'
#
#             # Update user balance for buy transactions
#             if transaction.transaction_type == TransactionType.BUY:
#                 # update balance of refrees and create entry.
#                 transaction.user.wallet_balance += transaction.amount_usdt
#
#         elif new_status == 'CANCELLED':
#             # Refund for sell transactions
#             if transaction.transaction_type == TransactionType.SELL:
#                 transaction.user.wallet_balance += transaction.amount_usdt
#
#             # Release claim if exists
#             if transaction.claim_id:
#                 claim = Claim.query.get(transaction.claim_id)
#                 claim.status = 'AVAILABLE'
#                 claim.claimed_by = None
#                 claim.claimed_at = None
#                 claim.expires_at = None
#
#         db.session.commit()
#         flash(f'Transaction status updated to {new_status}', 'success')
#         return jsonify({'success': True})
#
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'success': False, 'message': str(e)}), 500


@admin_transactions_bp.route('/transactions/<int:transaction_id>/update-status', methods=['POST'])
def update_transaction_status(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    new_status = request.form.get('status')
    admin_notes = request.form.get('admin_notes')

    if new_status not in [status.value for status in TransactionStatus]:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    try:
        with db.session.begin_nested():  # Use nested transaction for atomicity
            old_status = transaction.status
            transaction.status = TransactionStatus(new_status)
            transaction.admin_notes = admin_notes

            if new_status == 'COMPLETED':
                transaction.completed_at = datetime.utcnow()

                # Handle claim if exists
                if transaction.claim_id:
                    claim = Claim.query.get(transaction.claim_id)
                    claim.status = 'COMPLETED'

                # Update user balance and process referral earnings for buy transactions
                if transaction.transaction_type == TransactionType.BUY:
                    transaction.user.wallet_balance += transaction.amount_usdt
                    process_referral_earnings(transaction, "buy")
                else:
                    process_referral_earnings(transaction, "sell")

            elif new_status == 'CANCELLED':
                # Refund for sell transactions
                if transaction.transaction_type == TransactionType.SELL:
                    transaction.user.wallet_balance += transaction.amount_usdt

                # Release claim if exists
                if transaction.claim_id:
                    claim = Claim.query.get(transaction.claim_id)
                    claim.status = 'AVAILABLE'
                    claim.claimed_by = None
                    claim.claimed_at = None
                    claim.expires_at = None

        db.session.commit()
        flash(f'Transaction status updated to {new_status}', 'success')
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


def process_referral_earnings(transaction, transaction_type):
    """Processes referral earnings for a given transaction."""
    user = transaction.user
    referral_levels = ReferralCommission.query.filter_by(is_active=True).order_by(ReferralCommission.level.asc()).all()

    if not user or not referral_levels:
        return

    current_referee = user.referrer  # Assuming `referrer` is a relationship or FK to the referring user
    level = 1

    while current_referee and level <= len(referral_levels):
        referral_commission = referral_levels[level - 1]

        if transaction.amount_usdt >= referral_commission.min_amount_usdt:
            commission_percent = (
                referral_commission.buy_commission_percent if transaction_type == "buy" else referral_commission.sell_commission_percent
            )
            commission_amount = (transaction.amount_usdt * commission_percent) / 100

            if commission_amount > 0:
                # Create ReferralEarning record
                referral_earning = ReferralEarning(
                    user_id=current_referee.id,
                    transaction_id=transaction.id,
                    referral_level=level,
                    amount_usdt=commission_amount,
                    commission_percent=commission_percent
                )
                db.session.add(referral_earning)

                # Update referrer's wallet balance
                current_referee.wallet_balance += commission_amount

        # Move up to the next referral level
        current_referee = current_referee.referrer
        level += 1
