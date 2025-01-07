from flask import current_app

from models.models import User


def get_referral_tree(user_id, level=1, max_levels=None):
    """Get complete referral tree for visualization"""
    if max_levels and level > max_levels:
        return []

    referrals = User.query.filter_by(referred_by=user_id).all()
    tree = []

    for referral in referrals:
        sub_tree = get_referral_tree(
            referral.id,
            level + 1,
            max_levels or current_app.config['MAX_REFERRAL_LEVELS']
        )
        tree.append({
            'user': referral,
            'level': level,
            'children': sub_tree
        })

    return tree
