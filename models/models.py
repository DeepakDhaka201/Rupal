from datetime import datetime
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash

from models import db


class UserStatus(Enum):
    ACTIVE = 'ACTIVE'
    SUSPENDED = 'SUSPENDED'
    PENDING = 'PENDING'


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    name = db.Column(db.String(20), unique=True, nullable=False)
    wallet_balance = db.Column(db.Float, default=0.0)
    wallet_pin_hash = db.Column(db.String(256))
    referral_code = db.Column(db.String(10), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_admin = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum(UserStatus), default=UserStatus.ACTIVE)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_deposit_check = db.Column(db.DateTime)

    def set_wallet_pin(self, pin):
        self.wallet_pin_hash = generate_password_hash(pin)

    def check_wallet_pin(self, pin):
        return check_password_hash(self.wallet_pin_hash, pin)


# models/wallet.py
class WalletStatus(Enum):
    AVAILABLE = 'AVAILABLE'
    IN_USE = 'IN_USE'
    DISABLED = 'DISABLED'


class PooledWallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.Enum(WalletStatus), default=WalletStatus.AVAILABLE)
    last_used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    total_assignments = db.Column(db.Integer, default=0)
    last_checked_at = db.Column(db.DateTime)
    total_deposits = db.Column(db.Integer, default=0)
    total_deposit_amount = db.Column(db.Float, default=0.0)


class WalletAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey('pooled_wallet.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    wallet = db.relationship('PooledWallet', backref='assignments')
    user = db.relationship('User', backref='wallet_assignments')


# models/transaction.py
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


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rupal_id = db.Column(db.String(10), nullable=False)
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
    payment_mode = db.Column(db.String(20))

    payment_reference = db.Column(db.String(50))
    payment_proof = db.Column(db.String(200))
    wallet_assignment_id = db.Column(db.Integer, db.ForeignKey('wallet_assignment.id'))
    claim_id = db.Column(db.Integer, db.ForeignKey('claim.id'))

    # Timestamps and metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.String(500))
    admin_notes = db.Column(db.String(500))

    # Relationships
    user = db.relationship('User', backref='transactions')
    bank_account = db.relationship('BankAccount', backref='transactions')
    wallet_assignment = db.relationship('WalletAssignment', backref='transactions')
    claim = db.relationship('Claim', backref='transactions')


# models/bank.py
class BankAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    account_number = db.Column(db.String(20), nullable=False)
    ifsc_code = db.Column(db.String(11), nullable=False)
    account_holder = db.Column(db.String(100), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(100), nullable=False)
    is_verified = db.Column(db.Boolean, default=True)
    is_primary = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    user = db.relationship('User', backref='bank_accounts', foreign_keys=[user_id])
    verifier = db.relationship('User', foreign_keys=[verified_by])


# models/referral.py
class ReferralCommission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False)
    buy_commission_percent = db.Column(db.Float, nullable=False)
    sell_commission_percent = db.Column(db.Float, nullable=False)
    min_amount_usdt = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))


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
    purpose = db.Column(db.String(20), nullable=False)  # LOGIN, SIGNUP, WITHDRAWAL
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False)


class PaymentMode(Enum):
    ONLINE_TRANSFER = "Online Bank Transfer"
    CASH_DEPOSIT = "Cash Deposit via CDM"
    CASH_DELIVERY = "Cash Delivery"

    @classmethod
    def from_value(cls, payment_mode_val):
        print(payment_mode_val)
        if "Online Bank Transfer" == payment_mode_val:
            return PaymentMode.ONLINE_TRANSFER
        elif "Cash Deposit via CDM" == payment_mode_val:
            return PaymentMode.CASH_DEPOSIT
        elif "Cash Delivery" == payment_mode_val:
            return PaymentMode.CASH_DELIVERY
        else:
            raise ValueError('Invalid payment mode')


class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(10), nullable=False)  # BUY/SELL
    payment_mode = db.Column(db.Enum(PaymentMode), nullable=False)
    min_amount_inr = db.Column(db.Float, nullable=False)  # INR amount
    max_amount_inr = db.Column(db.Float, nullable=False)  # INR amount
    rate = db.Column(db.Float, nullable=False)  # Rate for this slab
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('transaction_type', 'payment_mode', 'min_amount_inr', 'max_amount_inr', name='unique_slab'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_type': self.transaction_type,
            'payment_mode': self.payment_mode.value,
            'min_amount': self.min_amount_inr,
            'max_amount': self.max_amount_inr,
            'rate': self.rate
        }


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50), nullable=False)
    ifsc_code = db.Column(db.String(20), nullable=False)
    account_holder = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    amount_inr = db.Column(db.Float, nullable=False)

    # Claim tracking
    claimed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    claimed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='AVAILABLE')  # AVAILABLE, CLAIMED, EXPIRED

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_claim_status', 'status', 'claimed_by'),
        db.Index('idx_active_claims', 'claimed_by', 'status', 'expires_at')
    )