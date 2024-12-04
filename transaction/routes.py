from flask import Blueprint, request, jsonify, current_app
from models.models import db, Transaction, TransactionStatus, TransactionType, User, BankAccount, WalletAssignment
from services.wallet_pool import WalletPoolService
from transaction.utils import TransactionUtil
from auth.utils import token_required
from datetime import datetime, timedelta

transaction_bp = Blueprint('transaction', __name__)


# Buy Flow APIs
@transaction_bp.route('/buy/initiate', methods=['POST'])
@token_required
def initiate_buy(current_user):
    """
    Initiate a buy order
    Request: {
        "amount_inr": 10000
    }
    """
    try:
        data = request.get_json()
        if not data or 'amount_inr' not in data:
            return jsonify({'error': 'Amount is required'}), 400

        amount_inr = float(data['amount_inr'])

        # Validate amount
        if amount_inr < current_app.config['MIN_BUY_INR']:
            return jsonify({'error': f'Minimum buy amount is {current_app.config["MIN_BUY_INR"]} INR'}), 400

        # Get current rate and calculate USDT amount
        rate = TransactionUtil.get_current_rate('buy')
        amount_usdt = amount_inr / rate

        # Create transaction
        transaction = Transaction(
            user_id=current_user.id,
            transaction_type=TransactionType.BUY,
            amount_inr=amount_inr,
            amount_usdt=amount_usdt,
            exchange_rate=rate,
            status=TransactionStatus.PENDING,
            payment_reference=TransactionUtil.generate_payment_reference()
        )

        db.session.add(transaction)
        db.session.commit()

        return jsonify({
            'transaction': {
                'id': transaction.id,
                'amount_inr': amount_inr,
                'amount_usdt': amount_usdt,
                'rate': rate,
                'payment_reference': transaction.payment_reference,
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
        if not transaction_id or 'payment_proof' not in request.files:
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

        # Update transaction
        transaction.payment_proof = proof_path
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
@transaction_bp.route('/sell/initiate', methods=['POST'])
@token_required
def initiate_sell(current_user):
    """
    Initiate a sell order
    Request: {
        "amount_usdt": 100,
        "bank_account_id": 1
    }
    """
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['amount_usdt', 'bank_account_id']):
            return jsonify({'error': 'All fields are required'}), 400

        amount_usdt = float(data['amount_usdt'])

        # Validate amount and balance
        if amount_usdt < current_app.config['MIN_SELL_USDT']:
            return jsonify({'error': f'Minimum sell amount is {current_app.config["MIN_SELL_USDT"]} USDT'}), 400

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

        # Calculate INR amount
        rate = TransactionUtil.get_current_rate('sell')
        amount_inr = amount_usdt * rate

        # Create transaction and deduct balance
        transaction = Transaction(
            user_id=current_user.id,
            transaction_type=TransactionType.SELL,
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
                'rate': rate,
                'status': transaction.status.value
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Sell initiate error: {str(e)}")
        return jsonify({'error': 'Failed to initiate sell'}), 500


@transaction_bp.route('/deposit/get-address', methods=['POST'])
@token_required
def get_deposit_address(current_user):
    """
    Get deposit address
    Request: {
        "amount_usdt": 100 (optional)
    }
    """
    try:
        # Get available wallet from pool
        wallet = WalletPoolService.get_available_wallet()
        if not wallet:
            return jsonify({'error': 'No deposit addresses available'}), 503

        # Create assignment
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        assignment = WalletAssignment(
            wallet_id=wallet.id,
            user_id=current_user.id,
            expires_at=expires_at
        )

        # Create transaction if amount specified
        transaction_id = None
        if 'amount_usdt' in request.get_json():
            amount_usdt = float(request.get_json()['amount_usdt'])
            transaction = Transaction(
                user_id=current_user.id,
                transaction_type=TransactionType.DEPOSIT,
                amount_usdt=amount_usdt,
                status=TransactionStatus.PENDING,
                to_address=wallet.address
            )
            db.session.add(transaction)
            transaction_id = transaction.id

        db.session.add(assignment)
        db.session.commit()

        return jsonify({
            'wallet': {
                'address': wallet.address,
                'expires_at': expires_at.isoformat()
            },
            'qr_data': f'tron:{wallet.address}',
            'transaction_id': transaction_id
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Get deposit address error: {str(e)}")
        return jsonify({'error': 'Failed to get deposit address'}), 500

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

        if current_user.wallet_balance < total_amount:
            return jsonify({'error': 'Insufficient balance'}), 400

        if not TransactionUtil.validate_tron_address(data['address']):
            return jsonify({'error': 'Invalid TRON address'}), 400

        if amount_usdt < current_app.config['MIN_WITHDRAWAL_USDT']:
            return jsonify({
                'error': f'Minimum withdrawal amount is {current_app.config["MIN_WITHDRAWAL_USDT"]} USDT'
            }), 400

        # Create transaction and deduct balance
        transaction = Transaction(
            user_id=current_user.id,
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
        page = int(request.args.get('page', 1))
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

        return jsonify({
            'transactions': [{
                'id': tx.id,
                'type': tx.transaction_type.value,
                'amount_usdt': tx.amount_usdt,
                'amount_inr': tx.amount_inr,
                'status': tx.status.value,
                'created_at': tx.created_at.isoformat(),
                'completed_at': tx.completed_at.isoformat() if tx.completed_at else None,
                'blockchain_txn_id': tx.blockchain_txn_id,
                'exchange_rate': tx.exchange_rate,
                'fee_usdt': tx.fee_usdt
            } for tx in transactions.items],
            'pagination': {
                'total_pages': transactions.pages,
                'current_page': transactions.page,
                'total_items': transactions.total,
                'has_next': transactions.has_next,
                'has_prev': transactions.has_prev
            }
        }), 200

    except Exception as e:
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