from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash

from models import db


class UserStatus(Enum):
    ACTIVE = 'ACTIVE'
    SUSPENDED = 'SUSPENDED'
    PENDING = 'PENDING'


class TransactionType(Enum):
    DEPOSIT = 'DEPOSIT'
    WITHDRAW = 'WITHDRAW'
    BUY = 'BUY'
    SELL = 'SELL'


class TransactionStatus(Enum):
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    wallet_balance = db.Column(db.Float, default=0.0)
    wallet_pin_hash = db.Column(db.String(256))
    referral_code = db.Column(db.String(10), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_admin = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum(UserStatus), default=UserStatus.ACTIVE)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_wallet_pin(self, pin):
        self.wallet_pin_hash = generate_password_hash(pin)

    def check_wallet_pin(self, pin):
        return check_password_hash(self.wallet_pin_hash, pin)


class BankAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    account_number = db.Column(db.String(20), nullable=False)
    ifsc_code = db.Column(db.String(11), nullable=False)
    account_holder = db.Column(db.String(100), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='bank_accounts')


class WithdrawalAddress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    address = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(50))
    network = db.Column(db.String(20), default='TRC20')
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='withdrawal_addresses')


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_type = db.Column(db.Enum(TransactionType), nullable=False)
    amount_usdt = db.Column(db.Float, nullable=False)
    amount_inr = db.Column(db.Float)
    exchange_rate = db.Column(db.Float)
    fee_usdt = db.Column(db.Float, default=0)
    status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.PENDING)

    # Blockchain details
    blockchain_txn_id = db.Column(db.String(100))
    from_address = db.Column(db.String(100))
    to_address = db.Column(db.String(100))

    # Bank transfer details
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_account.id'))
    payment_reference = db.Column(db.String(50))
    payment_proof = db.Column(db.String(200))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # Error handling
    error_message = db.Column(db.String(500))
    retry_count = db.Column(db.Integer, default=0)

    user = db.relationship('User', backref='transactions')
    bank_account = db.relationship('BankAccount')


class ReferralCommission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False)
    buy_commission_percent = db.Column(db.Float, nullable=False)
    sell_commission_percent = db.Column(db.Float, nullable=False)
    min_amount_usdt = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ReferralEarning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=False)
    referral_level = db.Column(db.Integer, nullable=False)
    amount_usdt = db.Column(db.Float, nullable=False)
    commission_percent = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='referral_earnings')
    transaction = db.relationship('Transaction', backref='referral_earnings')


class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(15), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False)