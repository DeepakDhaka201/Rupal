import os
from datetime import timedelta


class Config:
    # Basic Flask Config
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///crypto_platform.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT Config
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)

    # OTP Config
    OTP_LENGTH = 6
    OTP_VALIDITY_MINUTES = 10
    SMS_API_KEY = os.getenv('SMS_API_KEY')

    # Transaction Limits
    MIN_BUY_INR = 1000
    MAX_BUY_INR = 1000000
    MIN_SELL_USDT = 10
    MAX_SELL_USDT = 10000
    MIN_WITHDRAWAL_USDT = 10
    MAX_WITHDRAWAL_USDT = 10000

    # Blockchain Config
    TRON_API_URL = os.getenv('TRON_API_URL', 'https://api.trongrid.io')
    USDT_CONTRACT_ADDRESS = os.getenv('USDT_CONTRACT_ADDRESS')
    PLATFORM_WALLET_ADDRESS = os.getenv('PLATFORM_WALLET_ADDRESS')
    MIN_CONFIRMATIONS = 1

    # Wallet Pool Config
    WALLET_ASSIGNMENT_DURATION = 30  # minutes
    CLEANUP_INTERVAL = 5  # minutes

    # Referral Config
    MAX_REFERRAL_LEVELS = 5
    DEFAULT_BUY_COMMISSION = 1.0  # percentage
    DEFAULT_SELL_COMMISSION = 0.5  # percentage

    STATIC_FOLDER = 'static'
    QR_CODE_PATH = 'qrcodes'
    UPLOAD_DIR = 'uploads'

    BANK_ACCOUNT_NAME = "Yadhah"
    BANK_ACCOUNT_NUMBER = "1234567789"
    BANK_IFSC_CODE = "DBI93838"
    BANK_NAME = "DBI"
