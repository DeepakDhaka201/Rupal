from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

from models.models import db, PooledWallet, WalletAssignment, Transaction, TransactionStatus, User, Claim, Setting
from datetime import datetime, timedelta
from transaction.utils import TransactionUtil
import requests


class DepositMonitor:
    def __init__(self):
        self.tron_api_url = current_app.config['TRON_API_URL']
        self.usdt_contract = current_app.config['USDT_CONTRACT_ADDRESS']

    def monitor_active_assignments(self):
        try:
            current_app.logger.info(f"Checking wallets")
            # Get both active and expired assignments
            assignments = (WalletAssignment.query
                           .filter(WalletAssignment.is_active == True)
                           .with_for_update()
                           .all())

            current_app.logger.info(f"Found assignment to check : {assignments}")

            for assignment in assignments:
                self._check_assignment(assignment)

                # If assignment is expired, do one final check with grace period
                if datetime.utcnow() > assignment.expires_at:
                    self._handle_expired_assignment(assignment)

        except Exception as e:
            print(e)
            current_app.logger.error(f"Monitor error: {str(e)}")

    def _check_assignment(self, assignment):
        try:
            # Get blockchain transactions
            blockchain_txns = self._get_blockchain_transactions(
                assignment.wallet.address,
                assignment.assigned_at
            )

            current_app.logger.info(f"Blockchain Transactions Fetched : {blockchain_txns}")

            for txn in blockchain_txns:
                # Skip if transaction already processed
                if Transaction.query.filter_by(blockchain_txn_id=txn['hash']).first():
                    current_app.logger.info(f"Blockchain Transaction already processed : {txn}")
                    continue

                # Verify transaction
                if not self._verify_transaction(txn, assignment):
                    current_app.logger.info(f"Blockchain Transaction not verified : {txn}")
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
        current_app.logger.info(f"Blockchain Transaction Detected : {txn}")
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
        current_app.logger.info(f"Assignment Expired, Verifying with Tron : {assignment}")

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
                if assignment.assigned_at <= txn_timestamp <= assignment.expires_at:
                    if not Transaction.query.filter_by(blockchain_txn_id=txn['hash']).first():
                        if self._verify_transaction(txn, assignment):
                            self._process_transaction(assignment, txn)
                            return

            # No valid transaction found, release the wallet
            current_app.logger.info(f"No valid transaction found, release the wallet : {assignment}")
            assignment.is_active = False
            assignment.wallet.status = 'AVAILABLE'
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Handle expired assignment error: {str(e)}")


def cleanup_expired_claims():
    try:
        with db.session.begin_nested():
            current_app.logger.info(f"Checking claims")
            print("Checking Claims")
            # Find and lock expired claims
            expiry_time_delta = int(Setting.get_value("claim.expiry_time_delta", 2))

            expired_claims = (Claim.query
                              .filter(Claim.status == 'CLAIMED')
                              .with_for_update()
                              .all())

            for claim in expired_claims:
                if claim.expires_at + timedelta(minutes=expiry_time_delta) <= datetime.utcnow():
                    print(f"Found expired claim: {claim}")
                    claim.status = 'AVAILABLE'
                    claim.claimed_by = None
                    claim.claimed_at = None
                    claim.expires_at = None

                    # Update associated transaction if exists
                    transaction = Transaction.query.filter_by(claim_id=claim.id,
                                                              status=TransactionStatus.PENDING).first()
                    print(f"Found associated transaction: {transaction}")
                    if transaction and transaction.status == TransactionStatus.PENDING:
                        print("Updating transaction status")
                        transaction.status = TransactionStatus.CANCELLED
                        transaction.error_message = 'Claim expired'


            db.session.commit()

    except Exception as e:
        db.session.rollback()
        print(e)
        current_app.logger.error(f"Claim cleanup error: {str(e)}")


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


def setup_claim_monitoring(app):
    """Setup wallet monitoring tasks"""
    scheduler = BackgroundScheduler()
    monitor = DepositMonitor()

    # Check for deposits every minute
    scheduler.add_job(
        cleanup_expired_claims,
        'interval',
        seconds=30
    )

    scheduler.start()
    return scheduler
