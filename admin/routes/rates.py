from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from models.models import db, ExchangeRate, PaymentMode
from sqlalchemy import desc
from datetime import datetime

admin_rates_bp = Blueprint('admin_rates', __name__)


@admin_rates_bp.route('/rates')
def rates_list():
    # Get rates grouped by transaction type and payment mode
    buy_rates = ExchangeRate.query.filter_by(
        transaction_type='BUY',
        is_active=True
    ).order_by(
        ExchangeRate.payment_mode,
        ExchangeRate.min_amount_inr
    ).all()

    sell_rates = ExchangeRate.query.filter_by(
        transaction_type='SELL',
        is_active=True
    ).order_by(
        ExchangeRate.payment_mode,
        ExchangeRate.min_amount_inr
    ).all()

    return render_template('admin/rates/list.html',
                           buy_rates=buy_rates,
                           sell_rates=sell_rates,
                           payment_modes=PaymentMode
                           )


@admin_rates_bp.route('/rates/add', methods=['GET', 'POST'])
def add_rate():
    if request.method == 'POST':
        try:
            # Check for overlapping slabs
            existing_rate = ExchangeRate.query.filter(
                ExchangeRate.transaction_type == request.form['transaction_type'],
                ExchangeRate.payment_mode == PaymentMode.from_value(request.form['payment_mode']),
                ExchangeRate.min_amount_inr <= float(request.form['max_amount_inr']),
                ExchangeRate.max_amount_inr >= float(request.form['min_amount_inr']),
                ExchangeRate.is_active == True
            ).first()

            if existing_rate:
                flash('An overlapping rate slab already exists', 'error')
                return redirect(url_for('admin_rates.add_rate'))

            rate = ExchangeRate(
                transaction_type=request.form['transaction_type'],
                payment_mode=PaymentMode.from_value(request.form['payment_mode']),
                min_amount_inr=float(request.form['min_amount_inr']),
                max_amount_inr=float(request.form['max_amount_inr']),
                rate=float(request.form['rate']),
                is_active=True
            )
            db.session.add(rate)
            db.session.commit()

            flash('Rate added successfully', 'success')
            return redirect(url_for('admin_rates.rates_list'))

        except Exception as e:
            db.session.rollback()
            flash(f'Failed to add rate: {str(e)}', 'error')

    return render_template('admin/rates/add.html',
                           payment_modes=PaymentMode
                           )


@admin_rates_bp.route('/rates/<int:rate_id>/edit', methods=['GET', 'POST'])
def edit_rate(rate_id):
    rate = ExchangeRate.query.get_or_404(rate_id)

    if request.method == 'POST':
        try:
            # Check for overlapping slabs excluding current rate
            existing_rate = ExchangeRate.query.filter(
                ExchangeRate.id != rate_id,
                ExchangeRate.transaction_type == request.form['transaction_type'],
                ExchangeRate.payment_mode == PaymentMode.from_value(request.form['payment_mode']),
                ExchangeRate.min_amount_inr <= float(request.form['max_amount_inr']),
                ExchangeRate.max_amount_inr >= float(request.form['min_amount_inr']),
                ExchangeRate.is_active == True
            ).first()

            if existing_rate:
                flash('An overlapping rate slab already exists', 'error')
                return redirect(url_for('admin_rates.edit_rate', rate_id=rate_id))

            rate.transaction_type = request.form['transaction_type']
            rate.payment_mode = PaymentMode.from_value(request.form['payment_mode'])
            rate.min_amount_inr = float(request.form['min_amount_inr'])
            rate.max_amount_inr = float(request.form['max_amount_inr'])
            rate.rate = float(request.form['rate'])
            db.session.commit()

            flash('Rate updated successfully', 'success')
            return redirect(url_for('admin_rates.rates_list'))

        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update rate: {str(e)}', 'error')

    return render_template('admin/rates/edit.html',
                           rate=rate,
                           payment_modes=PaymentMode
                           )


@admin_rates_bp.route('/rates/<int:rate_id>/toggle', methods=['POST'])
def toggle_rate(rate_id):
    rate = ExchangeRate.query.get_or_404(rate_id)

    try:
        rate.is_active = not rate.is_active
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})