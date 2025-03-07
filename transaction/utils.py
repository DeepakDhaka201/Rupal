import os
import re
import string
import random
import uuid

import pytz
import qrcode
import requests
from datetime import datetime, timedelta
from flask import current_app, url_for
from sqlalchemy import and_

from werkzeug.utils import secure_filename

from models import db
from models.models import User, ReferralCommission, TransactionType, ReferralEarning, PaymentMode, ExchangeRate, Setting


class TransactionUtil:

    @staticmethod
    def get_transaction_title(transaction_type):
        """
        Get simple display title for transaction type
        """
        titles = {
            'DEPOSIT': 'USDT Received',
            'WITHDRAW': 'USDT Sent',
            'BUY': 'USDT Purchased',
            'SELL': 'USDT Sold',
            'ADMIN_ADD': 'USDT Added',
            'ADMIN_SUB': 'USDT Deducted'
        }

        colors = {
            'DEPOSIT': '#2ECC71',
            'WITHDRAW': '#E74C3C',
            'BUY': '#2ECC71',
            'SELL': '#E74C3C',
            'ADMIN_ADD': '#2ECC71',
            'ADMIN_SUB': '#E74C3C'
        }

        return {
            "text": titles.get(transaction_type, 'Unknown Transaction'),
            "color": colors.get(transaction_type, '#95A5A6')
        }

    @staticmethod
    def get_current_rate(transaction_type='BUY', payment_mode='CASH_DEPOSIT', amount_inr=0.0):
        """
           Find applicable exchange rate based on type, payment mode and amount
           Args:
               transaction_type: BUY/SELL
               payment_mode: ONLINE_TRANSFER/CASH_DEPOSIT
               amount_inr: Amount in INR

           Returns:
               ExchangeRate object if found

           Raises:
               ValueError: If no matching rate found or invalid inputs
           """
        try:
            # Validate inputs
            if transaction_type not in ['BUY', 'SELL']:
                raise ValueError('Invalid transaction type')

            try:
                payment_mode = PaymentMode[payment_mode.upper()]
            except ValueError:
                raise ValueError('Invalid payment mode')

            if not isinstance(amount_inr, (int, float)) or amount_inr <= 0:
                raise ValueError('Invalid amount')

            # Find matching rate
            rate = ExchangeRate.query.filter(
                and_(
                    ExchangeRate.transaction_type == transaction_type,
                    ExchangeRate.payment_mode == payment_mode,
                    ExchangeRate.min_amount_inr <= amount_inr,
                    ExchangeRate.max_amount_inr >= amount_inr,
                    ExchangeRate.is_active == True
                )
            ).first()

            if not rate:
                raise ValueError(
                    f'No rate found for {transaction_type} with {payment_mode.value} for amount {amount_inr}')

            return rate

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f'Error finding rate: {str(e)}')

    @staticmethod
    def validate_tron_address(address):
        """Validate TRON address format"""
        if not address:
            return False
        if not address.startswith('T'):
            return False
        if len(address) != 34:
            return False
        try:
            return bool(re.match(r'^T[A-Za-z0-9]{33}$', address))
        except:
            return False

    @staticmethod
    def verify_trc20_transaction(txn_hash, expected_amount=None, to_address=None):
        """
        Verify TRC20 transaction details
        Returns: (is_valid, error_message, transaction_data)
        """
        try:
            api_url = f"{current_app.config['TRON_API_URL']}/v1/transactions/{txn_hash}"
            response = requests.get(api_url)

            if not response.ok:
                return False, "Unable to verify transaction", None

            txn_data = response.json()

            # Validate confirmation count
            if txn_data.get('confirmations', 0) < current_app.config['MIN_CONFIRMATIONS']:
                return False, "Insufficient confirmations", None

            # Validate transaction type
            if txn_data.get('type') != 'TRC20':
                return False, "Invalid transaction type", None

            # Validate contract (USDT)
            if txn_data.get('contract_address') != current_app.config['USDT_CONTRACT_ADDRESS']:
                return False, "Invalid token contract", None

            # Validate amount if provided
            if expected_amount:
                actual_amount = float(txn_data['value']) / 1e6  # Convert from smallest unit
                if abs(actual_amount - expected_amount) > 0.01:  # Allow small difference
                    return False, "Amount mismatch", None

            # Validate recipient if provided
            if to_address and txn_data.get('to_address') != to_address:
                return False, "Invalid recipient address", None

            # Check if transaction is recent
            txn_time = datetime.fromtimestamp(txn_data['timestamp'] / 1000)
            if datetime.utcnow() - txn_time > timedelta(hours=24):
                return False, "Transaction too old", None

            return True, None, txn_data

        except Exception as e:
            current_app.logger.error(f"Transaction verification error: {str(e)}")
            return False, str(e), None

    @staticmethod
    def generate_payment_reference():
        """Generate unique payment reference for bank transfers"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"PAY-{timestamp}-{random_str}"

    @staticmethod
    def generate_transaction_ref():
        """Generate unique payment reference in the format PO########"""
        # Generate 8 random characters (uppercase letters or digits)
        random_str = ''.join(random.choices(string.digits, k=8))
        return f"PO{random_str}"

    @staticmethod
    def validate_bank_transfer_amount(amount_inr):
        """Validate bank transfer amount"""
        min_amount = current_app.config['MIN_TRANSFER_INR']
        max_amount = current_app.config['MAX_TRANSFER_INR']

        if amount_inr < min_amount:
            return False, f"Minimum transfer amount is ₹{min_amount}"
        if amount_inr > max_amount:
            return False, f"Maximum transfer amount is ₹{max_amount}"

        return True, None

    @staticmethod
    def calculate_network_fee(transaction_type):
        """Calculate network fee based on transaction type"""
        base_fees = {
            'WITHDRAW': 1,  # 1 USDT
            'DEPOSIT': 0,
            'BUY': 0,
            'SELL': 0
        }
        return base_fees.get(transaction_type, 0)

    @staticmethod
    def save_payment_proof(file, transaction_id):
        """Save payment proof file"""
        try:
            if file and file.filename:
                # Generate unique filename
                timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                filename = secure_filename(f"{transaction_id}_{timestamp}_{file.filename}")

                # Save file
                file_path = os.path.join(current_app.config['UPLOAD_DIR'], filename)
                file.save(file_path)

                return filename
            return None
        except Exception as e:
            current_app.logger.error(f"File save error: {str(e)}")
            return None

    @staticmethod
    def get_transaction_amount_display(transaction_type, amount):
        """
        Format amount display based on transaction type
        Returns amount with + or - prefix and USDT symbol (₮)
        Example: +₮300.00 or -₮300.00
        """
        try:
            # Format amount to 2 decimal places
            formatted_amount = "{:.2f}".format(float(amount))

            # Determine if amount should be positive or negative
            if transaction_type in ['BUY', 'DEPOSIT', 'ADMIN_ADD']:
                return f"+₮{formatted_amount}"
            elif transaction_type in ['SELL', 'WITHDRAW', 'ADMIN_SUB']:
                return f"-₮{formatted_amount}"
            else:
                return f"₮{formatted_amount}"
        except:
            return "₮0.00"

    @staticmethod
    def get_status_display(status):
        """
        Get readable status and associated color
        Returns dict with status text and color
        """
        status_map = {
            'PENDING': {
                'text': 'Pending',
                'color': '#FFA500'  # Orange
            },
            'PROCESSING': {
                'text': 'Processing',
                'color': '#3498DB'  # Blue
            },
            'COMPLETED': {
                'text': 'Completed',
                'color': '#2ECC71'  # Green
            },
            'FAILED': {
                'text': 'Failed',
                'color': '#E74C3C'  # Red
            },
            'CANCELLED': {
                'text': 'Cancelled',
                'color': '#95A5A6'  # Grey
            }
        }

        return status_map.get(status, {
            'text': 'Unknown',
            'color': '#95A5A6'  # Grey
        })

    @staticmethod
    def process_referral_commission(transaction):
        """Process referral commission for transaction"""
        try:
            user = User.query.get(transaction.user_id)
            if not user.referred_by:
                return

            current_level = 1
            current_referrer_id = user.referred_by

            while (current_referrer_id and
                   current_level <= current_app.config['MAX_REFERRAL_LEVELS']):

                referrer = User.query.get(current_referrer_id)
                if not referrer:
                    break

                # Get commission rate for current level
                commission = ReferralCommission.query.filter_by(
                    level=current_level,
                    is_active=True
                ).first()

                if commission:
                    if transaction.transaction_type == TransactionType.BUY:
                        commission_percent = commission.buy_commission_percent
                    else:  # SELL
                        commission_percent = commission.sell_commission_percent

                    commission_amount = (transaction.amount_usdt * commission_percent) / 100

                    # Create commission earning record
                    earning = ReferralEarning(
                        user_id=referrer.id,
                        transaction_id=transaction.id,
                        referral_level=current_level,
                        amount_usdt=commission_amount,
                        commission_percent=commission_percent
                    )

                    # Update referrer's wallet balance
                    referrer.wallet_balance += commission_amount

                    db.session.add(earning)

                # Move to next level
                current_level += 1
                current_referrer_id = referrer.referred_by

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Commission processing error: {str(e)}")

    @staticmethod
    def generate_address_qr(address, size=300):
        """
        Generate QR code image for USDT address
        Returns URL path of saved QR image
        """
        try:
            # Generate unique filename
            filename = f"qr_{address}.png"

            # Create uploads directory if it doesn't exist
            upload_dir = os.path.join(current_app.static_folder, 'qrcodes')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            domain = Setting.get_value('domain', "https://payon.website")
            file_path = os.path.join(upload_dir, filename)

            if os.path.exists(file_path):
                qr_url = domain + url_for('static', filename=f'qrcodes/{filename}')
                return qr_url

            # Create QR code instance
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )

            # Add USDT address data
            qr_data = f"tron:{address}"
            qr.add_data(qr_data)
            qr.make(fit=True)

            # Create QR code image with logo
            qr_image = qr.make_image(fill_color="black", back_color="white")

            # Resize if needed
            qr_image = qr_image.resize((size, size))

            # Save image
            qr_image.save(file_path)

            # Generate URL
            qr_url = domain + url_for('static', filename=f'qrcodes/{filename}')

            return qr_url

        except Exception as e:
            current_app.logger.error(f"QR generation error: {str(e)}")
            return None

    @staticmethod
    def format_created_at_to_ist(created_at):
        # Define the IST timezone
        ist_timezone = pytz.timezone("Asia/Kolkata")

        # Add UTC timezone info to the naive datetime
        utc_time = created_at.replace(tzinfo=pytz.utc)

        # Convert UTC time to IST
        ist_time = utc_time.astimezone(ist_timezone)

        # Format as '12:24 PM, 20 Dec'
        formatted_time = ist_time.strftime("%d %b, %H:%M")

        return formatted_time

    @staticmethod
    def get_transaction_icon(transaction_type):
        pass
