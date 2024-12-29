from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from admin.routes.auth import admin_auth_bp
from admin.routes.claims import admin_claims_bp
from admin.routes.rates import admin_rates_bp
from admin.routes.referrals import referral_admin_bp
from admin.routes.settings import settings_bp
from admin.routes.transactions import admin_transactions_bp
from admin.routes.users import admin_users_bp
from admin.routes.wallet_routes import wallet_bp
from config import Config
from models import db
import logging
from logging.handlers import RotatingFileHandler
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

from services.wallet_pool import cleanup_expired_claims, DepositMonitor


def setup_logging(app):
    """Configure application logging"""
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')

        file_handler = RotatingFileHandler(
            'logs/crypto_platform.log',
            maxBytes=10240,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Crypto Platform startup')


def setup_schedulers(app):
    """Initialize and configure all schedulers"""
    schedulers = []

    # Wallet monitoring scheduler
    wallet_scheduler = BackgroundScheduler(timezone='UTC')
    monitor = DepositMonitor()

    def monitor_with_context():
        with app.app_context():
            monitor.monitor_active_assignments()

    wallet_scheduler.add_job(
        monitor_with_context,
        'interval',
        seconds=5,
        max_instances=1
    )

    # Claims monitoring scheduler
    def cleanup_with_context():
        with app.app_context():
            cleanup_expired_claims()

    claims_scheduler = BackgroundScheduler(timezone='UTC')
    claims_scheduler.add_job(
        cleanup_with_context,
        'interval',
        seconds=5,
        max_instances=1
    )

    # Start schedulers
    for scheduler in [wallet_scheduler, claims_scheduler]:
        scheduler.start()
        schedulers.append(scheduler)

    # Register shutdown handlers
    def cleanup_schedulers():
        for scheduler in schedulers:
            scheduler.shutdown()

    atexit.register(cleanup_schedulers)
    return schedulers


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    CORS(app)

    # Register blueprints
    from auth.routes import auth_bp
    from dasboard.routes import dashboard_bp
    from referral.routes import referral_bp
    from transaction.routes import transaction_bp
    from bank.routes import bank_bp
    from user.routes import user_bp

    app.url_map.strict_slashes = False

    # API routes
    api_blueprints = [
        (auth_bp, '/api/v1/auth'),
        (dashboard_bp, '/api/v1/dashboard'),
        (transaction_bp, '/api/v1/transaction'),
        (bank_bp, '/api/v1/bank'),
        (referral_bp, '/api/v1/referral'),
        (user_bp, '/api/v1/user')
    ]

    # Admin routes
    admin_blueprints = [
        (admin_auth_bp, '/admin_auth'),
        (admin_users_bp, '/admin_users'),
        (admin_transactions_bp, '/admin_transactions'),
        (admin_claims_bp, '/admin_claims'),
        (admin_rates_bp, '/admin_rates'),
        (referral_admin_bp, '/admin/referrals'),
        (wallet_bp, '/admin/wallets'),
        (settings_bp, '/admin/settings')
    ]

    # Register all blueprints
    for blueprint, url_prefix in api_blueprints + admin_blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)

    # Setup Jinja filters
    app.jinja_env.filters['datetime'] = lambda value, format='%Y-%m-%d %H:%M': \
        value.strftime(format) if value else ''

    # Setup logging
    setup_logging(app)

    # Initialize schedulers
    with app.app_context():
        app.schedulers = setup_schedulers(app)
        db.create_all()

    @app.after_request
    def after_request(response):
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,PUT,POST,DELETE,OPTIONS'
        })
        return response

    return app


def main():
    app = create_app()
    port = int(os.environ.get('PORT', 6010))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    if not debug:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port, debug=True)


if __name__ == '__main__':
    main()