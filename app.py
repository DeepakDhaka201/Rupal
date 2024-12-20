from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from admin.routes.claims import admin_claims_bp
from admin.routes.rates import admin_rates_bp
from admin.routes.referrals import referral_admin_bp
from admin.routes.transactions import admin_transactions_bp
from admin.routes.users import admin_users_bp
from admin.routes.wallet_routes import wallet_bp
from config import Config
from models import db
import logging
from logging.handlers import RotatingFileHandler
import os
# from apscheduler.schedulers.background import BackgroundScheduler
# from scheduler.tasks import cleanup_expired_assignments, check_wallet_transactions


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

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/api/v1/dashboard')
    app.register_blueprint(transaction_bp, url_prefix='/api/v1/transaction')
    app.register_blueprint(bank_bp, url_prefix='/api/v1/bank')
    app.register_blueprint(referral_bp, url_prefix='/api/v1/referral')
    app.register_blueprint(user_bp, url_prefix='/api/v1/user')

    app.register_blueprint(admin_users_bp, url_prefix='/admin_users')
    app.register_blueprint(admin_transactions_bp, url_prefix='/admin_transactions')
    app.register_blueprint(admin_claims_bp, url_prefix='/admin_claims')
    app.register_blueprint(admin_rates_bp, url_prefix='/admin_rates')
    app.register_blueprint(referral_admin_bp, url_prefix='/admin/referrals')
    app.register_blueprint(wallet_bp, url_prefix='/admin/wallets')

    def format_datetime(value, format='%Y-%m-%d %H:%M'):
        if value is None:
            return ''
        return value.strftime(format)

    app.jinja_env.filters['datetime'] = format_datetime

    # Set up logging
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

    # Initialize scheduler
    # scheduler = BackgroundScheduler()
    # scheduler.add_job(
    #     func=cleanup_expired_assignments,
    #     trigger="interval",
    #     minutes=app.config['CLEANUP_INTERVAL']
    # )
    # scheduler.add_job(
    #     func=check_wallet_transactions,
    #     trigger="interval",
    #     minutes=1
    # )
    # scheduler.start()

    # Create database tables
    with app.app_context():
        db.create_all()

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(port=6010, debug=True)
