from flask import Blueprint, request, jsonify, current_app
from models.models import db, BankAccount
from auth.utils import token_required
import re

bank_bp = Blueprint('bank', __name__)


@bank_bp.route('/accounts', methods=['GET'])
@token_required
def get_accounts(current_user):
    """Get user's bank accounts"""
    try:
        accounts = BankAccount.query.filter_by(
            user_id=current_user.id
        ).order_by(BankAccount.is_primary.desc()).all()

        return jsonify({
            'accounts': [{
                'id': account.id,
                'bank_name': account.bank_name,
                'account_holder': account.account_holder,
                'account_number': account.account_number,
                'ifsc_code': account.ifsc_code,
                'is_verified': account.is_verified,
                'is_primary': account.is_primary
            } for account in accounts]
        }), 200

    except Exception as e:
        current_app.logger.error(f"Get bank accounts error: {str(e)}")
        return jsonify({'error': 'Failed to fetch bank accounts'}), 500


@bank_bp.route('/accounts', methods=['POST'])
@token_required
def add_account(current_user):
    """
    Add new bank account
    Request: {
        "bank_name": "Bank Name",
        "account_holder": "Account Holder Name",
        "account_number": "Account Number",
        "ifsc_code": "IFSC Code",
        "set_primary": boolean (optional)
    }
    """
    try:
        data = request.get_json()
        required_fields = ['bank_name', 'account_holder', 'account_number', 'ifsc_code']
        if not data or not all(field in data for field in required_fields):
            return jsonify({'error': 'All fields are required'}), 400

        # Validate IFSC code format
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', data['ifsc_code']):
            return jsonify({'error': 'Invalid IFSC code format'}), 400

        # Check if account already exists
        existing_account = BankAccount.query.filter_by(
            user_id=current_user.id,
            account_number=data['account_number'],
            ifsc_code=data['ifsc_code']
        ).first()

        if existing_account:
            return jsonify({'error': 'Account already exists'}), 400

        # Create new account
        account = BankAccount(
            user_id=current_user.id,
            bank_name=data['bank_name'],
            account_holder=data['account_holder'],
            account_number=data['account_number'],
            ifsc_code=data['ifsc_code'].upper()
        )

        # Handle primary account setting
        if data.get('set_primary'):
            # Remove primary flag from other accounts
            BankAccount.query.filter_by(
                user_id=current_user.id,
                is_primary=True
            ).update({'is_primary': False})
            account.is_primary = True

        db.session.add(account)
        db.session.commit()

        return jsonify({
            'message': 'Bank account added successfully',
            'account': {
                'id': account.id,
                'bank_name': account.bank_name,
                'account_number': account.account_number,
                'ifsc_code': account.ifsc_code,
                'is_primary': account.is_primary
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Add bank account error: {str(e)}")
        return jsonify({'error': 'Failed to add bank account'}), 500


@bank_bp.route('/accounts/<int:account_id>', methods=['DELETE'])
@token_required
def delete_account(current_user, account_id):
    """Delete bank account"""
    try:
        account = BankAccount.query.filter_by(
            id=account_id,
            user_id=current_user.id
        ).first_or_404()

        db.session.delete(account)
        db.session.commit()

        return jsonify({
            'message': 'Bank account deleted successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Delete bank account error: {str(e)}")
        return jsonify({'error': 'Failed to delete bank account'}), 500


@bank_bp.route('/accounts/<int:account_id>/primary', methods=['POST'])
@token_required
def set_primary_account(current_user, account_id):
    """Set account as primary"""
    try:
        account = BankAccount.query.filter_by(
            id=account_id,
            user_id=current_user.id
        ).first_or_404()

        # Remove primary flag from other accounts
        BankAccount.query.filter_by(
            user_id=current_user.id,
            is_primary=True
        ).update({'is_primary': False})

        account.is_primary = True
        db.session.commit()

        return jsonify({
            'message': 'Primary account updated successfully',
            'account': {
                'id': account.id,
                'bank_name': account.bank_name,
                'account_number': account.account_number
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Set primary account error: {str(e)}")
        return jsonify({'error': 'Failed to update primary account'}), 500
