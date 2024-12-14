# admin/wallet_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from models.models import db, PooledWallet, WalletAssignment, WalletStatus, User
from datetime import datetime

wallet_bp = Blueprint('wallet', __name__, url_prefix='/admin/wallets')


@wallet_bp.route('/')
def list_wallets():
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)

    query = PooledWallet.query
    if status:
        query = query.filter_by(status=WalletStatus[status])

    wallets = query.order_by(PooledWallet.created_at.desc()).paginate(page=page, per_page=20)

    # Get current assignments for wallets
    active_assignments = {
        assignment.wallet_id: assignment
        for assignment in WalletAssignment.query.filter_by(is_active=True).all()
    }

    return render_template('admin/wallets/list.html',
                           wallets=wallets,
                           active_assignments=active_assignments,
                           WalletStatus=WalletStatus)


@wallet_bp.route('/add', methods=['GET', 'POST'])
def add_wallet():
    if request.method == 'POST':
        address = request.form.get('address')

        if not address:
            flash('Address is required', 'error')
            return redirect(url_for('admin.wallet.add_wallet'))

        # Check if wallet already exists
        existing_wallet = PooledWallet.query.filter_by(address=address).first()
        if existing_wallet:
            flash('Wallet address already exists', 'error')
            return redirect(url_for('admin.wallet.add_wallet'))

        wallet = PooledWallet(
            address=address,
            status=WalletStatus.AVAILABLE,
            created_by=343
        )

        db.session.add(wallet)
        db.session.commit()

        flash('Wallet added successfully', 'success')
        return redirect(url_for('admin.wallet.list_wallets'))

    return render_template('admin/wallets/add.html')


@wallet_bp.route('/<int:wallet_id>/status', methods=['POST'])
def update_status(wallet_id):
    wallet = PooledWallet.query.get_or_404(wallet_id)
    status = request.form.get('status')

    if not status or status not in WalletStatus.__members__:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    wallet.status = WalletStatus[status]
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Wallet status updated to {status}'
    })


@wallet_bp.route('/<int:wallet_id>/assignments')
def view_assignments(wallet_id):
    wallet = PooledWallet.query.get_or_404(wallet_id)
    page = request.args.get('page', 1, type=int)

    assignments = WalletAssignment.query.filter_by(
        wallet_id=wallet_id
    ).order_by(
        WalletAssignment.assigned_at.desc()
    ).paginate(page=page, per_page=20)

    return render_template('admin/wallets/assignments.html',
                           wallet=wallet,
                           assignments=assignments)