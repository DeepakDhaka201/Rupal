# admin/routes/users.py
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from models.models import db, User, UserStatus, Transaction
from sqlalchemy import desc
from datetime import datetime

admin_users_bp = Blueprint('admin_users', __name__)


@admin_users_bp.route('/users')
def users_list():
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
def user_detail(user_id):
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

    return render_template('admin/users/detail.html',
                           user=user,
                           transactions=transactions,
                           stats=stats
                           )


@admin_users_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
def toggle_user_status(user_id):
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