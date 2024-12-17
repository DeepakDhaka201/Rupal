import traceback
from datetime import datetime, timedelta
from enum import Enum

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func, cast, Float

from auth.utils import token_required
from models.models import db, Transaction, TransactionStatus, TransactionType, BankAccount, WalletAssignment, \
    PooledWallet, ExchangeRate, PaymentMode, Claim
from transaction.utils import TransactionUtil

transaction_bp = Blueprint('transaction', __name__)


@transaction_bp.route('/dashboard', methods=['GET'])
@token_required
def get_dashboard(current_user):
    """
    Get dashboard data including active transactions and rates
    """
    try:
        # 1. Get Active Buy Transactions
        transaction_records = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionType.BUY.name,
            Transaction.status == TransactionStatus.PENDING.name
        ).all()

        active_transactions = []
        for transaction in transaction_records:
            claim = Claim.query.get(transaction.claim_id).first()
            if claim:
                active_transactions.append({
                    'id': transaction.id,
                    'rupal_id': transaction.rupal_id,
                    'amount_inr': transaction.amount_inr,
                    'amount_usdt': transaction.amount_usdt,
                    'payment_mode': Transaction[transaction.payment_mode].value,
                    'rate': transaction.rate,
                    'payment_reference': transaction.payment_reference,
                    'created_at': TransactionUtil.format_created_at_to_ist(transaction.created_at),
                    'claim': {
                        'id': claim.id,
                        'status': claim.status,
                        'expire_after': int((claim.expires_at - datetime.utcnow()).total_seconds()) * 1000,
                        'account_name': claim.account_holder,
                        'account_number': claim.account_number,
                        'ifsc_code': claim.ifsc_code,
                        'bank_name': claim.bank_name
                    }
                })

        # 2. Get All Rates
        rates = ExchangeRate.query.filter(
            ExchangeRate.is_active == True
        ).order_by(
            ExchangeRate.transaction_type,
            ExchangeRate.payment_mode,
            ExchangeRate.min_amount_inr
        ).all()

        rates_response = {
            'buy': {},
            'sell': {},
            'payment_modes': {
                'buy': [],
                'sell': []
            }
        }

        last_updated = None

        # Process rates
        for rate in rates:
            tx_type = rate.transaction_type.lower()
            payment_mode = rate.payment_mode.value

            if payment_mode not in rates_response[tx_type]:
                rates_response[tx_type][payment_mode] = []
                rates_response['payment_modes'][tx_type].append(payment_mode)

            rates_response[tx_type][payment_mode].append({
                "min_amount": rate.min_amount_inr,
                "max_amount": rate.max_amount_inr,
                "rate": rate.rate,
                "slab_id": rate.id
            })

            if not last_updated or rate.updated_at > last_updated:
                last_updated = rate.updated_at

        # Ensure consistent payment modes
        for tx_type in ['buy', 'sell']:
            for payment_mode in PaymentMode:
                if payment_mode.value not in rates_response[tx_type]:
                    rates_response[tx_type][payment_mode.value] = []

        formatted_time = TransactionUtil.format_created_at_to_ist(last_updated) if last_updated else "-"

        # Combine everything into final response
        return jsonify({
            'wallet_usdt': current_user.wallet_balance,
            'active_transactions': {
                'transactions': active_transactions,
                'showActive': len(active_transactions) > 0,
            },
            'rates': {
                'buy': {
                    'rates': rates_response['buy'],
                    'online_rates': rates_response['buy'].get(PaymentMode.ONLINE_TRANSFER.value, []),
                    'deposit_rates': rates_response['buy'].get(PaymentMode.CASH_DEPOSIT.value, []),
                    'payment_modes': rates_response['payment_modes']['buy']
                },
                'sell': {
                    'rates': rates_response['sell'],
                    'online_rates': rates_response['sell'].get(PaymentMode.ONLINE_TRANSFER.value, []),
                    'deposit_rates': rates_response['sell'].get(PaymentMode.CASH_DEPOSIT.value, []),
                    'payment_modes': rates_response['payment_modes']['sell']
                },
                'updated_at': formatted_time
            }
        }), 200

    except Exception as e:
        print(traceback.format_exc())
        current_app.logger.error(f"Dashboard error: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard data'}), 500


@transaction_bp.route('/rates/all', methods=['GET'])
@token_required
def get_all_rates(current_user):
    """
    Get all buy and sell rates grouped by payment mode
    Response: {
        "buy": {
            "ONLINE_TRANSFER": [...],
            "CASH_DEPOSIT": [...],
        },
        "sell": {
            "ONLINE_TRANSFER": [...],
            "CASH_DEPOSIT": [...],
        },
        "payment_modes": {
            "buy": [...],
            "sell": [...]
        }
    }
    """
    try:
        # Get all active rates
        rates = ExchangeRate.query.filter(
            ExchangeRate.is_active == True
        ).order_by(
            ExchangeRate.transaction_type,
            ExchangeRate.payment_mode,
            ExchangeRate.min_amount_inr
        ).all()

        # Prepare response structure
        response = {
            'buy': {},
            'sell': {},
            'payment_modes': {
                'buy': [],
                'sell': []
            }
        }

        last_updated = None

        # Group rates by transaction type and payment mode
        for rate in rates:
            tx_type = rate.transaction_type.lower()
            payment_mode = rate.payment_mode.value

            # Initialize payment mode group if not exists
            if payment_mode not in response[tx_type]:
                response[tx_type][payment_mode] = []
                response['payment_modes'][tx_type].append(payment_mode)

            # Add rate to appropriate group
            response[tx_type][payment_mode].append({
                "min_amount": rate.min_amount_inr,
                "max_amount": rate.max_amount_inr,
                "rate": rate.rate,
                "slab_id": rate.id
            })

            if not last_updated or rate.updated_at > last_updated:
                last_updated = rate.updated_at

        # Ensure consistent payment modes
        for tx_type in ['buy', 'sell']:
            for payment_mode in PaymentMode:
                if payment_mode.value not in response[tx_type]:
                    response[tx_type][payment_mode.value] = []

        formatted_time = TransactionUtil.format_created_at_to_ist(last_updated) if last_updated else "-"

        # Format final response
        return jsonify({
            'buy': {
                'rates': response['buy'],
                'online_rates': response['buy'].get(PaymentMode.ONLINE_TRANSFER.value, []),
                'deposit_rates': response['buy'].get(PaymentMode.CASH_DEPOSIT.value, []),
                'payment_modes': response['payment_modes']['buy']
            },
            'sell': {
                'rates': response['sell'],
                'online_rates': response['sell'].get(PaymentMode.ONLINE_TRANSFER.value, []),
                'deposit_rates': response['sell'].get(PaymentMode.CASH_DEPOSIT.value, []),
                'payment_modes': response['payment_modes']['sell']
            },
            "updated_at": formatted_time
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get rates error: {str(e)}")
        return jsonify({'error': 'Failed to get rates'}), 500


@transaction_bp.route('/rates', methods=['GET'])
@token_required
def get_rates(current_user):
    """
    Get all rates grouped by payment mode for a transaction type
    Query params:
    - type: BUY/SELL

    Response: {
        "ONLINE_TRANSFER": [
            {
                "min_amount": 1000,
                "max_amount": 50000,
                "rate": 85.5
            },
            {
                "min_amount": 50001,
                "max_amount": 100000,
                "rate": 85.2
            }
        ],
        "UPI": [
            {
                "min_amount": 1000,
                "max_amount": 25000,
                "rate": 85.7
            }
        ]
    }
    """
    try:
        tx_type = request.args.get('type', '').upper()
        if not tx_type or tx_type not in ['BUY', 'SELL']:
            return jsonify({'error': 'Valid transaction type (BUY/SELL) is required'}), 400

        # Get all active rates for the transaction type
        rates = ExchangeRate.query.filter(
            ExchangeRate.transaction_type == tx_type,
            ExchangeRate.is_active == True
        ).order_by(
            ExchangeRate.payment_mode,
            ExchangeRate.min_amount_inr
        ).all()

        # Group by payment mode
        grouped_rates = {}
        for rate in rates:
            payment_mode = rate.payment_mode.value
            if payment_mode not in grouped_rates:
                grouped_rates[payment_mode] = []

            grouped_rates[payment_mode].append({
                "min_amount": rate.min_amount_inr,
                "max_amount": rate.max_amount_inr,
                "rate": rate.rate,
                "slab_id": rate.id
            })

        payment_modes = []
        if tx_type == TransactionType.SELL.value:
            payment_modes.append(PaymentMode.ONLINE_TRANSFER.value)
        payment_modes.append(PaymentMode.CASH_DEPOSIT.value)
        payment_modes.append(PaymentMode.CASH_DELIVERY.value)

        data = {
            "rates": grouped_rates,
            "online_rates": grouped_rates[PaymentMode.ONLINE_TRANSFER.value] if grouped_rates[
                PaymentMode.ONLINE_TRANSFER.value] else [],
            "deposit_rates": grouped_rates[PaymentMode.CASH_DEPOSIT.value] if grouped_rates[
                PaymentMode.CASH_DEPOSIT.value] else [],
            "payment_modes": payment_modes
        }

        return jsonify(data), 200

    except Exception as e:
        current_app.logger.error(f"Get rates error: {str(e)}")
        return jsonify({'error': 'Failed to get rates'}), 500


# Buy Flow APIs

@transaction_bp.route('/buy/calculate-rate', methods=['POST'])
@token_required
def calculate_rate(current_user):
    """
    Calculate rate and converted amount
    Request: {
        "amount_inr": float
        "payment_mode": string
    }
    """
    try:
        data = request.get_json()

        payment_mode = data['payment_mode'] if data and data['payment_mode'] else 'Cash Deposit via CDM'
        amount_inr = float(data['amount_inr']) if data and data['amount_inr'] else 0.00

        rate = TransactionUtil.get_current_rate('buy', payment_mode, amount_inr)

        response = {
            'rate': rate,
            'payment_mode': payment_mode,
            'min_inr': current_app.config['MIN_BUY_INR'],
            'max_inr': current_app.config['MAX_BUY_INR']
        }

        amount_usdt = round(amount_inr / rate, 2)
        response.update({
            'amount_inr': amount_inr,
            'amount_usdt': amount_usdt
        })

        return jsonify(response), 200

    except ValueError:
        return jsonify({'error': 'Invalid amount format'}), 400
    except Exception as e:
        current_app.logger.error(f"Rate calculation error: {str(e)}")
        return jsonify({'error': 'Failed to calculate rate'}), 500


@transaction_bp.route('/buy/old/initiate', methods=['POST'])
@token_required
def initiate_buy(current_user):
    """
    Initiate a buy order
    Request: {
        "amount_inr": 10000,
        "payment_mode": "",
        "claim_id": "2"
    }
    """
    try:
        data = request.get_json()
        if not data or 'amount_inr' not in data:
            return jsonify({'error': 'Amount is required'}), 400

        if 'payment_mode' not in data:
            return jsonify({'error': 'Payment mode is required'}), 400

        if 'claim_id' not in data:
            return jsonify({'error': 'Kindly claim an option to continue'}), 400

        amount_inr = float(data['amount_inr'])
        payment_mode_val = data['payment_mode']
        payment_mode = PaymentMode.from_value(payment_mode_val).name

        # Validate amount
        if amount_inr < current_app.config['MIN_BUY_INR']:
            return jsonify({'error': f'Minimum buy amount is {current_app.config["MIN_BUY_INR"]} INR'}), 400

        # Get current rate and calculate USDT amount
        rate = TransactionUtil.get_current_rate(TransactionType.BUY.value,
                                                payment_mode=payment_mode,
                                                amount_inr=amount_inr)
        amount_usdt = amount_inr / rate

        # Create transaction
        transaction = Transaction(
            user_id=current_user.id,
            rupal_id=TransactionUtil.generate_transaction_ref(),
            transaction_type=TransactionType.BUY,
            payment_mode=payment_mode,
            amount_inr=round(amount_inr, 2),
            amount_usdt=round(amount_usdt, 2),
            exchange_rate=rate,
            status=TransactionStatus.PENDING,
            payment_reference=TransactionUtil.generate_payment_reference()
        )

        db.session.add(transaction)
        db.session.commit()

        return jsonify({
            'transaction': {
                'id': transaction.id,
                'rupal_id': transaction.rupal_id,
                'amount_inr': amount_inr,
                'amount_usdt': round(amount_usdt, 2),
                'payment_mode': payment_mode_val,
                'rate': rate,
                'payment_reference': transaction.payment_reference,
                'created_at': TransactionUtil.format_created_at_to_ist(transaction.created_at),
                'bank_details': {
                    'account_name': current_app.config['BANK_ACCOUNT_NAME'],
                    'account_number': current_app.config['BANK_ACCOUNT_NUMBER'],
                    'ifsc_code': current_app.config['BANK_IFSC_CODE'],
                    'bank_name': current_app.config['BANK_NAME']
                }
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Buy initiate error: {str(e)}")
        return jsonify({'error': 'Failed to initiate buy'}), 500


@transaction_bp.route('/buy/initiate', methods=['POST'])
@token_required
def initiate_buy2(current_user):
    """
    Initiate a buy order
    Request: {
        "payment_mode": "",
        "claim_id": "2"
    }
    """
    try:
        with db.session.begin_nested():  # Create savepoint for rollback
            data = request.get_json()
            if not data:
                db.session.rollback()
                return jsonify({'error': 'Payload is required'}), 400

            if 'payment_mode' not in data:
                db.session.rollback()
                return jsonify({'error': 'Payment mode is required'}), 400

            if 'claim_id' not in data:
                db.session.rollback()
                return jsonify({'error': 'Kindly claim an option to continue'}), 400

            payment_mode_val = data['payment_mode']
            payment_mode = PaymentMode.from_value(payment_mode_val).name

            # Lock and verify claim
            claim = (Claim.query
                     .filter_by(id=data['claim_id'])
                     .with_for_update()
                     .first())

            if not claim:
                db.session.rollback()
                return jsonify({'error': 'Invalid claim'}), 404

            if claim.status != 'AVAILABLE':
                db.session.rollback()
                return jsonify({'error': 'Invalid claim status'}), 400

            if datetime.utcnow() > claim.expires_at:
                db.session.rollback()
                return jsonify({'error': 'Claim has expired'}), 400

            amount_inr = claim.amount_inr

            # Validate amount
            if amount_inr < current_app.config['MIN_BUY_INR']:
                db.session.rollback()
                return jsonify({'error': f'Minimum buy amount is {current_app.config["MIN_BUY_INR"]} INR'}), 400

            # Get current rate and calculate USDT amount
            rate = TransactionUtil.get_current_rate(
                TransactionType.BUY.value,
                payment_mode=payment_mode,
                amount_inr=amount_inr
            )
            amount_usdt = amount_inr / rate

            claim.status = 'CLAIMED'
            claim.claimed_by = current_user.id
            claim.claimed_at = datetime.utcnow()
            claim.expires_at = datetime.utcnow() + timedelta(minutes=30)

            # Create transaction
            transaction = Transaction(
                user_id=current_user.id,
                rupal_id=TransactionUtil.generate_transaction_ref(),
                transaction_type=TransactionType.BUY,
                payment_mode=payment_mode,
                amount_inr=round(amount_inr, 2),
                amount_usdt=round(amount_usdt, 2),
                exchange_rate=rate,
                status=TransactionStatus.PENDING,
                payment_reference=TransactionUtil.generate_payment_reference(),
                claim_id=claim.id
            )

            db.session.add(transaction)
            db.session.commit()

            return jsonify({
                'transaction': {
                    'id': transaction.id,
                    'rupal_id': transaction.rupal_id,
                    'amount_inr': amount_inr,
                    'amount_usdt': round(amount_usdt, 2),
                    'payment_mode': payment_mode_val,
                    'rate': rate,
                    'payment_reference': transaction.payment_reference,
                    'created_at': TransactionUtil.format_created_at_to_ist(transaction.created_at),
                    'claim': {
                        'id': claim.id,
                        'status': claim.status,
                        'expire_after': int((claim.expires_at - datetime.utcnow()).total_seconds()) * 1000,
                        'account_name': claim.account_holder,
                        'account_number': claim.account_number,
                        'ifsc_code': claim.ifsc_code,
                        'bank_name': claim.bank_name
                    }
                }
            }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Buy initiate error: {str(e)}")
        return jsonify({'error': 'Failed to initiate buy'}), 500


@transaction_bp.route('/buy/active', methods=['GET'])
@token_required
def active_buy_transactions(current_user):
    try:
        transaction_records = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionType.BUY.name,
            Transaction.status == TransactionStatus.PENDING.name
        ).all()
        transactions = []
        for transaction in transaction_records:
            claim = Claim.query.get(transaction.claim_id).first()
            transactions.append({
                'id': transaction.id,
                'rupal_id': transaction.rupal_id,
                'amount_inr': transaction.amount_inr,
                'amount_usdt': transaction.amount_usdt,
                'payment_mode': Transaction[transaction.payment_mode].value,
                'rate': transaction.rate,
                'payment_reference': transaction.payment_reference,
                'created_at': TransactionUtil.format_created_at_to_ist(transaction.created_at),
                'claim': {
                    'id': claim.id,
                    'status': claim.status,
                    'expire_after': int((claim.expires_at - datetime.utcnow()).total_seconds()) * 1000,
                    'account_name': claim.account_holder,
                    'account_number': claim.account_number,
                    'ifsc_code': claim.ifsc_code,
                    'bank_name': claim.bank_name
                }
            })
        return jsonify({"transactions": transactions, "showActive": True if len(transactions) > 0 else None, "wallet_usdt": current_user.wallet_balance}), 200
    except Exception as e:
        print(traceback.format_exc())
        current_app.logger.error(f"Get buy active orders error: {str(e)}")
        return jsonify({'error': 'Failed to fetch active transactions'}), 500


@transaction_bp.route('/buy/cancel', methods=['POST'])
@token_required
def cancel_buy_transaction(current_user):
    try:
        with db.session.begin_nested():
            data = request.get_json()
            if not data and not data['transaction_id']:
                return jsonify({'error': 'Transaction ID is required'}), 400

            transaction_id = int(data['transaction_id'])
            transaction = Transaction.query.get(transaction_id).first()

            if not transaction:
                return jsonify({'error': 'Transaction not found'}), 400

            if current_user.id != transaction.user_id:
                return jsonify({'error': 'Unauthorized access'}), 401

            if transaction.status == TransactionStatus.CANCELLED.name:
                return jsonify({'error': 'Transaction is already cancelled'}), 400

            claim = Claim.query.get(transaction.claim_id).first()

            claim.claimed_by = None
            claim.claimed_at = None
            claim.expires_at = None
            claim.status = 'AVAILABLE'

            transaction.status = TransactionStatus.CANCELLED.name
            transaction.error_message = 'Claim Expired'
            db.session.commit()
            return jsonify({"message": "Your order is cancelled successfully."})
    except Exception as e:
        print(traceback.format_exc())
        current_app.logger.error(f"Error while cancelling buy transaction: {str(e)}")
        return jsonify({'error': 'Failed to fetch active transactions'}), 500


@transaction_bp.route('/buy/confirm', methods=['POST'])
@token_required
def confirm_buy(current_user):
    """
    Confirm buy order with payment proof
    Request: multipart/form-data
        - transaction_id: ID of the transaction
        - payment_proof: Payment screenshot/proof
    """
    try:
        transaction_id = request.form.get('transaction_id')
        ref_number = request.form.get('ref_number')
        if not transaction_id or 'payment_proof' not in request.files or not ref_number:
            return jsonify({'error': 'All fields are required'}), 400

        transaction = Transaction.query.filter_by(
            id=transaction_id,
            user_id=current_user.id,
            transaction_type=TransactionType.BUY,
            status=TransactionStatus.PENDING
        ).first()

        if not transaction:
            return jsonify({'error': 'Invalid transaction'}), 404

        # Save payment proof
        payment_proof = request.files['payment_proof']
        proof_path = TransactionUtil.save_payment_proof(payment_proof, transaction_id)
        if not proof_path:
            return jsonify({'error': 'Failed to save payment proof'}), 500

        claim = Claim.query.get(transaction.claim_id).first()
        claim.is_active = False

        # Update transaction
        transaction.payment_proof = proof_path
        transaction.payment_reference = ref_number
        transaction.status = TransactionStatus.PROCESSING

        db.session.commit()

        return jsonify({
            'message': 'Payment confirmed successfully',
            'transaction': {
                'id': transaction.id,
                'status': transaction.status.value
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Buy confirm error: {str(e)}")
        return jsonify({'error': 'Failed to confirm payment'}), 500


# Sell Flow APIs
@transaction_bp.route('/sell/calculate-rate', methods=['POST'])
@token_required
def sell_calculate_rate(current_user):
    """
    Calculate rate and converted amount
    Request: {
        "amount_inr": float
        "payment_mode": string
    }

    """
    try:
        data = request.get_json()

        # Get current rate
        payment_mode = data['payment_mode'] if data and data['payment_mode'] else 'Online Bank Transfer'
        amount_inr = float(data['amount_inr']) if data and data['amount_inr'] else 0.00

        rate = TransactionUtil.get_current_rate('sell', payment_mode, amount_inr)

        response = {
            'rate': rate,
            'payment_mode': payment_mode,
            'min_inr': current_app.config['MIN_SELL_INR'],
            'max_inr': current_app.config['MAX_SELL_INR']
        }

        amount_usdt = round(amount_inr / rate, 2)
        response.update({
            'amount_inr': amount_inr,
            'amount_usdt': amount_usdt
        })

        return jsonify(response), 200
    except ValueError:
        return jsonify({'error': 'Invalid amount format'}), 400
    except Exception as e:
        print(traceback.print_exc())
        current_app.logger.error(f"Rate calculation error: {str(e)}")
        return jsonify({'error': 'Failed to calculate rate'}), 500


@transaction_bp.route('/sell/initiate', methods=['POST'])
@token_required
def initiate_sell(current_user):
    """
    Initiate a sell order
    Request: {
        "amount_inr": 1000,
        "bank_account_id": 1,
        "payment_mode": "online"
    }
    """
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['amount_inr', 'bank_account_id', 'payment_mode']):
            return jsonify({'error': 'All fields are required'}), 400

        amount_inr = float(data['amount_inr'])
        payment_mode_val = data['payment_mode']

        payment_mode = PaymentMode.from_value(payment_mode_val).name

        # Validate amount and balance
        if amount_inr < current_app.config['MIN_SELL_INR']:
            return jsonify({'error': f'Minimum sell amount is {current_app.config["MIN_SELL_INR"]} INR'}), 400

        rate = TransactionUtil.get_current_rate(TransactionType.SELL.value,
                                                payment_mode=payment_mode,
                                                amount_inr=amount_inr)
        amount_usdt = round(amount_inr / rate, 2)

        if current_user.wallet_balance < amount_usdt:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Verify bank account
        bank_account = BankAccount.query.filter_by(
            id=data['bank_account_id'],
            user_id=current_user.id,
            is_verified=True
        ).first()

        if not bank_account:
            return jsonify({'error': 'Invalid or unverified bank account'}), 400

        # Create transaction and deduct balance
        transaction = Transaction(
            user_id=current_user.id,
            transaction_type=TransactionType.SELL,
            payment_mode=payment_mode,
            amount_usdt=amount_usdt,
            amount_inr=amount_inr,
            exchange_rate=rate,
            status=TransactionStatus.PROCESSING,
            bank_account_id=bank_account.id
        )

        current_user.wallet_balance -= amount_usdt

        db.session.add(transaction)
        db.session.commit()

        return jsonify({
            'transaction': {
                'id': transaction.id,
                'amount_usdt': amount_usdt,
                'amount_inr': amount_inr,
                'rupal_id': transaction.rupal_id,
                'rate': rate,
                'payment_mode': payment_mode_val,
                'status': transaction.status.value,
                'display_status': TransactionUtil.get_status_display(transaction.status.value),
                'created_at': TransactionUtil.format_created_at_to_ist(transaction.created_at),
                'bank_details': {
                    'bank_name': bank_account.bank_name,
                    'account_holder': bank_account.account_holder,
                    'account_number': bank_account.account_number,
                    'ifsc_code': bank_account.ifsc_code
                }
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Sell initiate error: {str(e)}")
        return jsonify({'error': 'Failed to initiate sell'}), 500


@transaction_bp.route('/deposit/get-address', methods=['POST'])
@token_required
def initiate_deposit(current_user):
    try:
        with db.session.begin_nested():
            # Check existing active assignment with lock
            active_assignment = (WalletAssignment.query
                                 .filter(
                WalletAssignment.user_id == current_user.id,
                WalletAssignment.is_active == True,
                WalletAssignment.expires_at > datetime.utcnow()
            ).with_for_update().first())

            if active_assignment:
                remaining_time = (active_assignment.expires_at - datetime.utcnow()).total_seconds()
                if remaining_time > 120:  # More than 2 minutes
                    return jsonify({
                        'assignment_id': active_assignment.id,
                        'address': active_assignment.wallet.address,
                        'qr_url': TransactionUtil.generate_address_qr(active_assignment.wallet.address),
                        'expires_at': int(active_assignment.expires_at.timestamp() * 1000),
                        'expire_after': int(remaining_time * 1000)
                    }), 200

            # Get available wallet with lock
            wallet = (PooledWallet.query
                      .filter_by(status='AVAILABLE')
                      .with_for_update(skip_locked=True)
                      .order_by(PooledWallet.last_used_at.asc())
                      .first())

            if not wallet:
                return jsonify({'error': 'No deposit addresses available'}), 503

            # Create new assignment
            expires_at = datetime.utcnow() + timedelta(minutes=30)
            assignment = WalletAssignment(
                wallet_id=wallet.id,
                user_id=current_user.id,
                assigned_at=datetime.utcnow(),
                expires_at=expires_at,
                is_active=True
            )
            db.session.add(assignment)
            db.session.flush()

            # Update wallet status
            wallet.status = 'IN_USE'
            wallet.last_used_at = datetime.utcnow()

            db.session.commit()

            return jsonify({
                'assignment_id': assignment.id,
                'address': wallet.address,
                'qr_url': TransactionUtil.generate_address_qr(assignment.wallet.address),
                'expires_at': int(expires_at.timestamp() * 1000),
                'expire_after': int(timedelta(minutes=20).total_seconds() * 1000)
            }), 200

    except Exception as e:
        current_app.logger.error(f"Deposit initiation error: {str(e)}")
        return jsonify({'error': 'Failed to initiate deposit'}), 500


@transaction_bp.route('/deposit/check-transaction', methods=['GET'])
@token_required
def check_deposit_status(current_user):
    try:
        assignment_id = request.args.get('assignment_id')

        if not assignment_id:
            return {"error": "assignment_id is required"}, 400

        # Get assignment with lock
        assignment = (WalletAssignment.query
                      .filter_by(
            id=assignment_id,
            user_id=current_user.id
        )
                      .with_for_update()
                      .first_or_404())

        # Get associated transaction if exists
        transaction = Transaction.query.filter_by(
            wallet_assignment_id=assignment.id,
            status='COMPLETED'
        ).first()

        response = {
            'address': assignment.wallet.address,
            'is_active': assignment.is_active,
            'transaction_detected': bool(transaction),
            'transaction': {
                "rupal_id": transaction.rupal_id,
                "status": transaction.status,
                "title": TransactionUtil.get_transaction_title(transaction.transaction_type.value),
                "display_status": TransactionUtil.get_status_display(transaction.status.value),
                "amount_usdt": transaction.amount_usdt,
                "display_amount": TransactionUtil.get_transaction_amount_display(transaction.transaction_type,
                                                                                 transaction.amount_usdt),
                "created_at": TransactionUtil.format_created_at_to_ist(transaction.created_at),
                "txn_hash": transaction.blockchain_txn_id
            } if transaction else None
        }

        if assignment.is_active:
            now = datetime.utcnow()
            if now < assignment.expires_at:
                response.update({
                    'expires_at': int(assignment.expires_at.timestamp() * 1000),
                    'expire_after': int((assignment.expires_at - now).total_seconds() * 1000)
                })

        if transaction:
            response.update({
                'amount_usdt': transaction.amount_usdt,
                'blockchain_txn_id': transaction.blockchain_txn_id
            })

        return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f"Check status error: {str(e)}")
        return jsonify({'error': 'Failed to check status'}), 500


# Withdraw Flow APIs
@transaction_bp.route('/withdraw/initiate', methods=['POST'])
@token_required
def initiate_withdraw(current_user):
    """
    Initiate withdrawal
    Request: {
        "amount_usdt": 100,
        "address": "TRx...",
        "wallet_pin": "1234"
    }
    """
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['amount_usdt', 'address', 'wallet_pin']):
            return jsonify({'error': 'All fields are required'}), 400

        amount_usdt = float(data['amount_usdt'])
        fee = current_app.config['WITHDRAWAL_FEE']
        total_amount = amount_usdt + fee

        # Validations
        if not current_user.check_wallet_pin(data['wallet_pin']):
            return jsonify({'error': 'Invalid wallet PIN'}), 400

        if not TransactionUtil.validate_tron_address(data['address']):
            return jsonify({'error': 'Invalid TRON address'}), 400

        if current_user.wallet_balance < total_amount:
            return jsonify({'error': 'Insufficient balance'}), 400

        if amount_usdt < current_app.config['MIN_WITHDRAWAL_USDT']:
            return jsonify({
                'error': f'Minimum withdrawal amount is {current_app.config["MIN_WITHDRAWAL_USDT"]} USDT'
            }), 400

        # Create transaction and deduct balance
        transaction = Transaction(
            user_id=current_user.id,
            rupal_id=TransactionUtil.generate_transaction_ref(),
            transaction_type=TransactionType.WITHDRAW,
            amount_usdt=amount_usdt,
            fee_usdt=fee,
            to_address=data['address'],
            status=TransactionStatus.PENDING
        )

        current_user.wallet_balance -= total_amount

        db.session.add(transaction)
        db.session.commit()

        return jsonify({
            'transaction': {
                'id': transaction.id,
                'rupal_id': transaction.rupal_id,
                'amount_usdt': amount_usdt,
                'fee': fee,
                'total_amount': total_amount,
                'status': transaction.status.value,
                'address': data['address']
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Withdraw initiate error: {str(e)}")
        return jsonify({'error': 'Failed to initiate withdrawal'}), 500


# Common Transaction APIs
@transaction_bp.route('/transactions', methods=['GET'])
@token_required
def get_transactions(current_user):
    """
    Get user transactions with filters
    Query params:
    - type: DEPOSIT/WITHDRAW/BUY/SELL
    - status: PENDING/PROCESSING/COMPLETED/FAILED
    - from_date: YYYY-MM-DD
    - to_date: YYYY-MM-DD
    - page: int
    - per_page: int
    """
    try:
        print("Inside Transactions")
        print(request.args.get('page'))
        page = int(request.args.get('page'))
        if page:
            page += 1
        else:
            page = 1

        per_page = int(request.args.get('per_page', 20))
        tx_type = request.args.get('type')
        status = request.args.get('status')
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')

        # Build query
        query = Transaction.query.filter_by(user_id=current_user.id)

        if tx_type:
            query = query.filter_by(transaction_type=TransactionType[tx_type])
        if status:
            query = query.filter_by(status=TransactionStatus[status])
        if from_date:
            query = query.filter(Transaction.created_at >= datetime.strptime(from_date, '%Y-%m-%d'))
        if to_date:
            query = query.filter(Transaction.created_at < datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1))

        # Execute query with pagination
        transactions = query.order_by(Transaction.created_at.desc()).paginate(
            page=page, per_page=per_page
        )

        data = []
        for tx in transactions.items:
            transaction = {
                'id': tx.id,
                'rupal_id': tx.rupal_id,
                'title': TransactionUtil.get_transaction_title(tx.transaction_type.value),
                'icon': TransactionUtil.get_transaction_icon(tx.transaction_type.value),
                'type': tx.transaction_type.value,
                'amount_usdt': tx.amount_usdt,
                'amount_display': TransactionUtil.get_transaction_amount_display(tx.transaction_type.value,
                                                                                 tx.amount_usdt),
                'amount_inr': tx.amount_inr,
                'status': tx.status.value,
                'display_status': TransactionUtil.get_status_display(tx.status.value),
                'created_at': TransactionUtil.format_created_at_to_ist(tx.created_at),
                'completed_at': tx.completed_at.isoformat() if tx.completed_at else None,
                'blockchain_txn_id': tx.blockchain_txn_id,
                'payment_mode': tx.payment_mode,
                'exchange_rate': tx.exchange_rate,
                'fee_usdt': tx.fee_usdt,
                'bank_details': {
                    'bank_name': tx.bank_account.bank_name,
                    'account_holder': tx.bank_account.account_holder,
                    'account_number': tx.bank_account.account_number,
                    'ifsc_code': tx.bank_account.ifsc_code
                } if tx.bank_account else None
            }

            if tx.transaction_type == TransactionType.BUY.value and tx.claim:
                transaction['bank_details'] = {
                    'bank_name': tx.claim.bank_name,
                    'account_holder': tx.claim.account_holder,
                    'account_number': tx.claim.account_number,
                    'ifsc_code': tx.bank_account.ifsc_code
                }

            data.append(transaction)

        return jsonify({
            'transactions': data,
            'pagination': {
                'total_pages': transactions.pages,
                'current_page': transactions.page + 1 if int(request.args.get('page', 1)) == 0 else transactions.page,
                'total_items': transactions.total,
                'has_next': transactions.has_next,
                'has_prev': transactions.has_prev
            }
        }), 200

    except Exception as e:
        print(traceback.format_exc())
        current_app.logger.error(f"Get transactions error: {str(e)}")
        return jsonify({'error': 'Failed to fetch transactions'}), 500


@transaction_bp.route('/transaction/<int:transaction_id>', methods=['GET'])
@token_required
def get_transaction_details(current_user, transaction_id):
    """Get detailed transaction information"""
    try:
        transaction = Transaction.query.filter_by(
            id=transaction_id,
            user_id=current_user.id
        ).first_or_404()

        return jsonify({
            'transaction': {
                'id': transaction.id,
                'type': transaction.transaction_type.value,
                'amount_usdt': transaction.amount_usdt,
                'amount_inr': transaction.amount_inr,
                'status': transaction.status.value,
                'created_at': transaction.created_at.isoformat(),
                'completed_at': transaction.completed_at.isoformat() if transaction.completed_at else None,
                'blockchain_txn_id': transaction.blockchain_txn_id,
                'exchange_rate': transaction.exchange_rate,
                'fee_usdt': transaction.fee_usdt,
                'bank_account': {
                    'account_number': transaction.bank_account.account_number,
                    'ifsc_code': transaction.bank_account.ifsc_code,
                    'bank_name': transaction.bank_account.bank_name
                } if transaction.bank_account else None,
                'addresses': {
                    'from': transaction.from_address,
                    'to': transaction.to_address
                } if (transaction.from_address or transaction.to_address) else None
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get transaction details error: {str(e)}")
        return jsonify({'error': 'Failed to fetch transaction details'}), 500


class SortPattern(Enum):
    AMOUNT_ASC = 1
    AMOUNT_DESC = 2
    RECOMMENDED = 3


@transaction_bp.route('/claims', methods=['GET'])
@token_required
def get_available_claims(current_user):
    """
    Get available claims with sorting and filtering
    Query params:
    - sort: 1 (Amount ASC), 2 (Amount DESC), 3 (Recommended)
    - bank_name: string (optional)
    - amount_inr: float (optional, for recommended sorting)
    """
    try:
        sort_pattern = int(request.args.get('sort', SortPattern.RECOMMENDED.value))
        bank_name = request.args.get('bank_name')
        recommended_amount = float(request.args.get('amount_inr', 0))

        # Base query for available claims
        query = Claim.query.filter(
            Claim.is_active == True,
            Claim.status == 'AVAILABLE'
        )

        # Apply bank name filter if provided
        if bank_name:
            query = query.filter(Claim.bank_name == bank_name)

        # Apply sorting
        if sort_pattern == SortPattern.AMOUNT_ASC.value:
            query = query.order_by(Claim.amount_inr.asc())
        elif sort_pattern == SortPattern.AMOUNT_DESC.value:
            query = query.order_by(Claim.amount_inr.desc())
        elif sort_pattern == SortPattern.RECOMMENDED.value and recommended_amount > 0:
            # Calculate absolute difference from recommended amount
            # Use case to handle recommended amount being closer to claim amount
            difference = func.abs(cast(Claim.amount_inr, Float) - recommended_amount)
            query = query.order_by(difference.asc())

        # Execute query
        claims = query.all()

        # Get unique bank names from active claims
        bank_names = db.session.query(
            Claim.bank_name
        ).filter(
            Claim.is_active == True,
            Claim.status == 'AVAILABLE'
        ).distinct().all()

        return jsonify({
            'claims': [{
                'id': claim.id,
                'bank_name': claim.bank_name,
                'account_number': claim.account_number,  # Mask account number
                'ifsc_code': claim.ifsc_code,
                'account_holder': claim.account_holder,
                'amount_inr': claim.amount_inr,
                'status': claim.status,
                'created_at': claim.created_at.isoformat()
            } for claim in claims],
            'bank_names': [name[0] for name in bank_names],
            'sort_options': ["3", "2", "1"],  # 1 (Amount Asc), 2 (Amount Desc), 3 (Recommended)
            'sort_names': ["Recommended", "Amount Desc", "Amount Asc"]
        }), 200

    except ValueError:
        return jsonify({'error': 'Invalid sort pattern or amount'}), 400
    except Exception as e:
        current_app.logger.error(f"Get claims error: {str(e)}")
        return jsonify({'error': 'Failed to fetch claims'}), 500
