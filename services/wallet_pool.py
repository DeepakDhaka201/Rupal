from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

from models.models import db, PooledWallet, WalletAssignment, Transaction, TransactionStatus, User
from datetime import datetime, timedelta
from transaction.utils import TransactionUtil
import requests


class WalletPoolMonitor:
    def __init__(self):
        self.tron_api_url = current_app.config['TRON_API_URL']
        self.usdt_contract = current_app.config['USDT_CONTRACT_ADDRESS']
        self.min_confirmations = current_app.config['MIN_CONFIRMATIONS']

    def cleanup_expired_assignments(self):
        """Cleanup expired wallet assignments"""
        try:
            expired_assignments = WalletAssignment.query.filter(
                WalletAssignment.expires_at <= datetime.utcnow(),
                WalletAssignment.is_active == True
            ).all()

            for assignment in expired_assignments:
                assignment.is_active = False
                assignment.wallet.status = 'AVAILABLE'

            db.session.commit()
            current_app.logger.info(f"Cleaned up {len(expired_assignments)} expired assignments")

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Assignment cleanup error: {str(e)}")

    def monitor_wallet_deposits(self):
        """Monitor all active wallet assignments for deposits"""
        try:
            active_assignments = WalletAssignment.query.filter_by(
                is_active=True
            ).join(PooledWallet).all()

            for assignment in active_assignments:
                self._check_wallet_deposits(assignment)

        except Exception as e:
            current_app.logger.error(f"Wallet monitoring error: {str(e)}")

    def _check_wallet_deposits(self, assignment):
        """Check deposits for a specific wallet assignment"""
        try:
            wallet = assignment.wallet
            last_check = wallet.last_checked_at or assignment.assigned_at

            # Get transactions from TRON API
            transactions = self._get_wallet_transactions(
                wallet.address,
                last_check.timestamp()
            )

            for txn in transactions:
                self._process_transaction(txn, assignment)

            # Update last check time
            wallet.last_checked_at = datetime.utcnow()
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Deposit check error for wallet {assignment.wallet.address}: {str(e)}")

    def _get_wallet_transactions(self, address, min_timestamp):
        """Get transactions for a wallet address"""
        try:
            response = requests.get(
                f"{self.tron_api_url}/v1/accounts/{address}/transactions/trc20",
                params={
                    'only_to': True,
                    'min_timestamp': int(min_timestamp * 1000),
                    'contract_address': self.usdt_contract
                }
            )

            if response.ok:
                return response.json().get('data', [])
            return []

        except Exception as e:
            current_app.logger.error(f"Get transactions error: {str(e)}")
            return []

    def _process_transaction(self, txn_data, assignment):
        """Process a single transaction"""
        try:
            # Skip if already processed
            if Transaction.query.filter_by(
                    blockchain_txn_id=txn_data['hash']
            ).first():
                return

            # Verify transaction
            is_valid, error, _ = TransactionUtil.verify_trc20_transaction(
                txn_data['hash']
            )

            if not is_valid:
                current_app.logger.warning(
                    f"Invalid transaction {txn_data['hash']}: {error}"
                )
                return

            amount_usdt = float(txn_data['value']) / 1e6  # Convert from smallest unit

            # Create transaction record
            transaction = Transaction(
                user_id=assignment.user_id,
                transaction_type='DEPOSIT',
                amount_usdt=amount_usdt,
                status=TransactionStatus.COMPLETED,
                blockchain_txn_id=txn_data['hash'],
                from_address=txn_data['from_address'],
                to_address=assignment.wallet.address,
                completed_at=datetime.utcnow()
            )

            # Update user's wallet balance
            user = User.query.get(assignment.user_id)
            user.wallet_balance += amount_usdt

            # Update wallet statistics
            wallet = assignment.wallet
            wallet.total_deposits += 1
            wallet.total_deposit_amount += amount_usdt

            db.session.add(transaction)
            db.session.commit()

            current_app.logger.info(
                f"Processed deposit: {amount_usdt} USDT for user {user.id}"
            )

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Transaction processing error: {str(e)}")


# wallet_pool/service.py
class WalletPoolService:
    @staticmethod
    def get_available_wallet():
        """Get least recently used available wallet"""
        return (PooledWallet.query
                .filter_by(status='AVAILABLE')
                .order_by(
            PooledWallet.last_used_at.asc(),
            PooledWallet.total_assignments.asc()
        )
                .first())

    @staticmethod
    def assign_wallet(user_id, duration_minutes=30):
        """Assign a wallet to user"""
        wallet = WalletPoolService.get_available_wallet()
        if not wallet:
            return None

        try:
            assignment = WalletAssignment(
                wallet_id=wallet.id,
                user_id=user_id,
                expires_at=datetime.utcnow() + timedelta(minutes=duration_minutes)
            )

            wallet.status = 'IN_USE'
            wallet.last_used_at = datetime.utcnow()
            wallet.total_assignments += 1

            db.session.add(assignment)
            db.session.commit()

            return wallet

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Wallet assignment error: {str(e)}")
            return None


# scheduler/tasks.py
def setup_wallet_monitoring(app):
    """Setup wallet monitoring tasks"""
    scheduler = BackgroundScheduler()
    monitor = WalletPoolMonitor()

    # Check for deposits every minute
    scheduler.add_job(
        monitor.monitor_wallet_deposits,
        'interval',
        minutes=1
    )

    # Cleanup expired assignments every 5 minutes
    scheduler.add_job(
        monitor.cleanup_expired_assignments,
        'interval',
        minutes=5
    )

    scheduler.start()
    return scheduler