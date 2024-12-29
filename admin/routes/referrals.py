# admin/referral_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify

from auth.utils import admin_required
from models.models import db, User, ReferralCommission, ReferralEarning, Transaction
from sqlalchemy import func
from datetime import datetime, timedelta

referral_admin_bp = Blueprint('admin_referral', __name__, url_prefix='/admin/referrals')


@referral_admin_bp.route('/')
@admin_required
def dashboard(current_user):
    # Get overall statistics
    total_earnings = db.session.query(
        func.sum(ReferralEarning.amount_usdt)
    ).scalar() or 0

    # Get commission rates
    commission_rates = ReferralCommission.query.order_by(ReferralCommission.level).all()

    # Get recent earnings
    recent_earnings = ReferralEarning.query.order_by(
        ReferralEarning.created_at.desc()
    ).limit(10).all()

    # Get top referrers
    top_referrers = db.session.query(
        User,
        func.count(User.id).label('referral_count'),
        func.sum(ReferralEarning.amount_usdt).label('total_earnings')
    ).join(
        ReferralEarning,
        User.id == ReferralEarning.user_id
    ).group_by(User.id).order_by(
        func.sum(ReferralEarning.amount_usdt).desc()
    ).limit(5).all()

    return render_template('admin/referrals/dashboard.html',
                           total_earnings=total_earnings,
                           commission_rates=commission_rates,
                           recent_earnings=recent_earnings,
                           top_referrers=top_referrers)


@referral_admin_bp.route('/commissions')
@admin_required
def commission_rates(current_user):
    rates = ReferralCommission.query.order_by(ReferralCommission.level).all()
    return render_template('admin/referrals/comission_rates.html', rates=rates)


@referral_admin_bp.route('/commissions/add', methods=['POST'])
@admin_required
def add_commission(current_user):
    try:
        level = int(request.form.get('level'))
        buy_commission = float(request.form.get('buy_commission'))
        sell_commission = float(request.form.get('sell_commission'))
        min_amount = float(request.form.get('min_amount', 0))

        # Check if level already exists
        existing = ReferralCommission.query.filter_by(level=level).first()
        if existing:
            flash('Commission level already exists', 'error')
            return redirect(url_for('admin_referral.commission_rates'))

        commission = ReferralCommission(
            level=level,
            buy_commission_percent=buy_commission,
            sell_commission_percent=sell_commission,
            min_amount_usdt=min_amount,
            created_by=343
        )

        db.session.add(commission)
        db.session.commit()

        flash('Commission rate added successfully', 'success')
        return redirect(url_for('admin_referral.commission_rates'))

    except ValueError:
        flash('Invalid values provided', 'error')
        return redirect(url_for('admin_referral.commission_rates'))


@referral_admin_bp.route('/commissions/<int:commission_id>/edit', methods=['POST'])
@admin_required
def edit_commission(current_user, commission_id):
    commission = ReferralCommission.query.get_or_404(commission_id)

    try:
        commission.buy_commission_percent = float(request.form.get('buy_commission'))
        commission.sell_commission_percent = float(request.form.get('sell_commission'))
        commission.min_amount_usdt = float(request.form.get('min_amount', 0))
        commission.is_active = bool(request.form.get('is_active'))

        db.session.commit()
        return jsonify({'success': True})

    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid values provided'}), 400


@referral_admin_bp.route('/earnings')
@admin_required
def earnings(current_user):
    page = request.args.get('page', 1, type=int)
    user_id = request.args.get('user_id', type=int)
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    query = ReferralEarning.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if from_date:
        query = query.filter(ReferralEarning.created_at >= datetime.strptime(from_date, '%Y-%m-%d'))
    if to_date:
        query = query.filter(ReferralEarning.created_at < datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))

    earnings = query.order_by(ReferralEarning.created_at.desc()).paginate(page=page, per_page=20)

    return render_template('admin/referrals/earnings.html',
                           earnings=earnings)


@referral_admin_bp.route('/tree/<int:user_id>')
@admin_required
def referral_tree(current_user, user_id):
    user = User.query.get_or_404(user_id)

    # Get direct referrals
    direct_referrals = User.query.filter_by(referred_by=user_id).all()

    # Get earnings data
    earnings_data = db.session.query(
        User.id,
        func.sum(ReferralEarning.amount_usdt).label('total_earnings')
    ).join(
        ReferralEarning,
        User.id == ReferralEarning.user_id
    ).filter(
        User.id.in_([r.id for r in direct_referrals])
    ).group_by(User.id).all()

    earnings_map = {user_id: total for user_id, total in earnings_data}

    return render_template('admin/referrals/tree.html',
                           user=user,
                           referrals=direct_referrals,
                           earnings_map=earnings_map)