# admin/routes/users.py
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for

from auth.utils import admin_required
from models.models import db, User, UserStatus, Transaction, TransactionType, TransactionStatus
from sqlalchemy import desc
from datetime import datetime

from transaction.utils import TransactionUtil

admin_users_bp = Blueprint('admin_users', __name__)


@admin_users_bp.route('/users')
@admin_required
def users_list(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status')

    query = User.query

    if search:
        query = query.filter(
            (User.mobile.like(f'%{search}%')) |
            (User.name.like(f'%{search}%'))
        )

    if status:
        query = query.filter(User.status == UserStatus(status))

    users = query.order_by(desc(User.created_at)).paginate(
        page=page, per_page=per_page
    )

    return render_template('admin/users/list.html',
                           users=users,
                           search=search,
                           status=status,
                           UserStatus=UserStatus
                           )


@admin_users_bp.route('/users/<int:user_id>')
@admin_required
def user_detail(current_user, user_id):
    user = User.query.get_or_404(user_id)
    transactions = Transaction.query.filter_by(user_id=user_id) \
        .order_by(desc(Transaction.created_at)).limit(10).all()

    stats = {
        'total_transactions': Transaction.query.filter_by(user_id=user_id).count(),
        'total_buy_amount': db.session.query(db.func.sum(Transaction.amount_usdt)) \
                                .filter_by(user_id=user_id, transaction_type='BUY', status='COMPLETED').scalar() or 0,
        'total_sell_amount': db.session.query(db.func.sum(Transaction.amount_usdt)) \
                                 .filter_by(user_id=user_id, transaction_type='SELL', status='COMPLETED').scalar() or 0
    }

    return render_template('admin/users/details.html',
                           user=user,
                           transactions=transactions,
                           stats=stats
                           )


@admin_users_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_user_status(current_user, user_id):
    user = User.query.get_or_404(user_id)

    if user.status == UserStatus.ACTIVE:
        user.status = UserStatus.SUSPENDED
        message = f'User {user.mobile} has been suspended'
    else:
        user.status = UserStatus.ACTIVE
        message = f'User {user.mobile} has been activated'

    db.session.commit()
    flash(message, 'success')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': message})
    return redirect(url_for('admin_users.users_list'))


# admin/user_routes.py
@admin_users_bp.route('/<int:user_id>/balance', methods=['POST'])
@admin_required
def update_balance(current_user, user_id):
    try:
        user = User.query.get_or_404(user_id)
        operation = request.form.get('operation')  # 'add' or 'subtract'
        amount = float(request.form.get('amount', 0))
        reason = request.form.get('reason')

        if not amount or amount <= 0:
            flash('Invalid amount', 'error')
            return redirect(url_for('admin_users.user_detail', user_id=user_id))

        if operation == 'add':
            user.wallet_balance += amount
            action = 'added to'
        elif operation == 'subtract':
            if user.wallet_balance < amount:
                flash('Insufficient balance', 'error')
                return redirect(url_for('admin_users.user_detail', user_id=user_id))
            user.wallet_balance -= amount
            action = 'subtracted from'
        else:
            flash('Invalid operation', 'error')
            return redirect(url_for('admin_users.user_detail', user_id=user_id))

        # Log the balance update
        admin_note = f"Balance {action} by admin. Reason: {reason}"
        transaction = Transaction(
            user_id=user.id,
            rupal_id=TransactionUtil.generate_transaction_ref(),
            transaction_type=TransactionType.ADMIN_ADJUSTMENT,
            amount_usdt=amount,
            status=TransactionStatus.COMPLETED,
            admin_notes=admin_note,
            completed_at=datetime.utcnow()
        )

        db.session.add(transaction)
        db.session.commit()

        flash(f'{amount} USDT {action} wallet balance successfully', 'success')
        return redirect(url_for('admin_users.user_detail', user_id=user_id))

    except ValueError:
        flash('Invalid amount format', 'error')
        return redirect(url_for('admin_users.user_detail', user_id=user_id))
    except Exception as e:
        db.session.rollback()
        print(e)
        flash('Failed to update balance', 'error')
        return redirect(url_for('admin_users.user_detail', user_id=user_id))