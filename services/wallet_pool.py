from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

from models.models import db, PooledWallet, WalletAssignment, Transaction, TransactionStatus, User
from datetime import datetime, timedelta
from transaction.utils import TransactionUtil
import requests


class DepositMonitor:
    def __init__(self):
        self.tron_api_url = current_app.config['TRON_API_URL']
        self.usdt_contract = current_app.config['USDT_CONTRACT_ADDRESS']

    def monitor_active_assignments(self):
        try:
            # Get both active and expired assignments
            assignments = (WalletAssignment.query
                           .filter(
                                WalletAssignment.is_active == True
                             )
                           .with_for_update()
                           .all())

            for assignment in assignments:
                self._check_assignment(assignment)

                # If assignment is expired, do one final check with grace period
                if datetime.utcnow() > assignment.expires_at:
                    self._handle_expired_assignment(assignment)

        except Exception as e:
            current_app.logger.error(f"Monitor error: {str(e)}")

    def _check_assignment(self, assignment):
        try:
            # Get blockchain transactions
            blockchain_txns = self._get_blockchain_transactions(
                assignment.wallet.address,
                assignment.assigned_at
            )

            for txn in blockchain_txns:
                # Skip if transaction already processed
                if Transaction.query.filter_by(blockchain_txn_id=txn['hash']).first():
                    continue

                # Verify transaction
                if not self._verify_transaction(txn, assignment):
                    continue

                # Create transaction and credit user
                self._process_transaction(assignment, txn)
                return

            # Check if assignment expired
            if datetime.utcnow() > assignment.expires_at:
                assignment.is_active = False
                assignment.wallet.status = 'AVAILABLE'
                db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Check assignment error: {str(e)}")

    def _verify_transaction(self, txn, assignment):
        try:
            # Check basic transaction validity
            if txn.get('confirmations', 0) < current_app.config['MIN_CONFIRMATIONS']:
                return False

            if txn.get('contract_address') != self.usdt_contract:
                return False

            # Verify transaction timestamp against assignment
            txn_timestamp = datetime.fromtimestamp(txn['timestamp'] / 1000)
            if txn_timestamp < assignment.assigned_at:
                return False

            if txn_timestamp > assignment.expires_at:
                return False

            return True

        except Exception as e:
            current_app.logger.error(f"Verify transaction error: {str(e)}")
            return False

    def _process_transaction(self, assignment, txn):
        try:
            amount_usdt = float(txn['value']) / 1e6

            transaction = Transaction(
                user_id=assignment.user_id,
                wallet_assignment_id=assignment.id,
                transaction_type='DEPOSIT',
                status='COMPLETED',
                amount_usdt=round(amount_usdt, 2),
                blockchain_txn_id=txn['hash'],
                created_at=datetime.utcnow()
            )
            db.session.add(transaction)

            # Credit user
            user = User.query.get(assignment.user_id)
            user.wallet_balance += amount_usdt

            # Mark assignment and wallet as completed
            assignment.is_active = False
            assignment.wallet.status = 'AVAILABLE'

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Process transaction error: {str(e)}")

    def _get_blockchain_transactions(self, address, start_time):
        try:
            response = requests.get(
                f"{self.tron_api_url}/v1/accounts/{address}/transactions/trc20",
                params={
                    'only_to': True,
                    'min_timestamp': int(start_time.timestamp() * 1000),
                    'contract_address': self.usdt_contract
                }
            )

            if response.ok:
                return response.json().get('data', [])
            return []

        except Exception as e:
            current_app.logger.error(f"Get blockchain transactions error: {str(e)}")
            return []

    def _handle_expired_assignment(self, assignment):
        """Handle expired assignment with final check"""
        try:
            # One final check with grace period
            grace_period = datetime.utcnow() + timedelta(minutes=5)
            blockchain_txns = self._get_blockchain_transactions(
                assignment.wallet.address,
                assignment.assigned_at
            )

            # Check transactions one last time
            for txn in blockchain_txns:
                txn_timestamp = datetime.fromtimestamp(txn['timestamp'] / 1000)

                # Only process if transaction was made during assignment period
                if (txn_timestamp >= assignment.assigned_at and
                        txn_timestamp <= assignment.expires_at):

                    if not Transaction.query.filter_by(blockchain_txn_id=txn['hash']).first():
                        if self._verify_transaction(txn, assignment):
                            self._process_transaction(assignment, txn)
                            return

            # No valid transaction found, release the wallet
            assignment.is_active = False
            assignment.wallet.status = 'AVAILABLE'
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Handle expired assignment error: {str(e)}")


# scheduler/tasks.py
def setup_wallet_monitoring(app):
    """Setup wallet monitoring tasks"""
    scheduler = BackgroundScheduler()
    monitor = DepositMonitor()

    # Check for deposits every minute
    scheduler.add_job(
        monitor.monitor_active_assignments,
        'interval',
        seconds=2
    )

    scheduler.start()
    return scheduler
