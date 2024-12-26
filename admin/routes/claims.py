# admin/routes/claims.py
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for

from auth.utils import admin_required
from models.models import db, Claim, Transaction
from sqlalchemy import desc
from datetime import datetime, timedelta

admin_claims_bp = Blueprint('admin_claims', __name__)


@admin_claims_bp.route('/claims')
@admin_required
def claims_list(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status = request.args.get('status')
    search = request.args.get('search', '')  # Search by bank name or account number

    query = Claim.query

    if status:
        query = query.filter(Claim.status == status)
    if search:
        query = query.filter(
            (Claim.bank_name.ilike(f'%{search}%')) |
            (Claim.account_number.ilike(f'%{search}%')) |
            (Claim.account_holder.ilike(f'%{search}%'))
        )

    claims = query.order_by(desc(Claim.created_at)).paginate(
        page=page, per_page=per_page
    )

    return render_template('admin/claims/list.html',
                           claims=claims,
                           search=search,
                           status=status
                           )


@admin_claims_bp.route('/claims/add', methods=['GET', 'POST'])
def add_claim(current_user):
    if request.method == 'POST':
        try:
            claim = Claim(
                bank_name=request.form['bank_name'],
                account_number=request.form['account_number'],
                ifsc_code=request.form['ifsc_code'],
                account_holder=request.form['account_holder'],
                amount_inr=float(request.form['amount_inr']),
                is_active=True,
                status='AVAILABLE'
            )
            db.session.add(claim)
            db.session.commit()

            flash('Claim added successfully', 'success')
            return redirect(url_for('admin_claims.claims_list'))

        except Exception as e:
            db.session.rollback()
            flash(f'Failed to add claim: {str(e)}', 'error')

    return render_template('admin/claims/add.html')


@admin_claims_bp.route('/claims/<int:claim_id>/edit', methods=['GET', 'POST'])
def edit_claim(current_user, claim_id):
    claim = Claim.query.get_or_404(claim_id)

    if request.method == 'POST':
        try:
            # Only allow editing if claim is not in use
            if claim.status not in ['CLAIMED', 'COMPLETED']:
                claim.bank_name = request.form['bank_name']
                claim.account_number = request.form['account_number']
                claim.ifsc_code = request.form['ifsc_code']
                claim.account_holder = request.form['account_holder']
                claim.amount_inr = float(request.form['amount_inr'])
                db.session.commit()
                flash('Claim updated successfully', 'success')
                return redirect(url_for('admin_claims.claims_list'))
            else:
                flash('Cannot edit claim in current status', 'error')

        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update claim: {str(e)}', 'error')

    return render_template('admin/claims/edit.html', claim=claim)


@admin_claims_bp.route('/claims/<int:claim_id>/update-status', methods=['POST'])
def update_claim_status(current_user, claim_id):
    claim = Claim.query.get_or_404(claim_id)
    new_status = request.form.get('is_active', '').lower() == 'true'

    try:
        # Only allow status update if claim is not in use
        if claim.status not in ['CLAIMED', 'COMPLETED']:
            claim.is_active = new_status
            if not new_status:
                claim.status = 'DISABLED'
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Cannot update status of claim in current state'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@admin_claims_bp.route('/claims/<int:claim_id>/details')
def claim_details(current_user, claim_id):
    claim = Claim.query.get_or_404(claim_id)

    # Get associated transactions
    transactions = Transaction.query.filter_by(
        claim_id=claim_id
    ).order_by(Transaction.created_at.desc()).all()

    return render_template('admin/claims/details.html',
                           claim=claim,
                           transactions=transactions
                           )