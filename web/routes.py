from flask import Blueprint, render_template

from models.models import Setting

web_bp = Blueprint('web', __name__)


@web_bp.route('/', methods=['GET'])
def index():
    return render_template('index.html',
                           apk_url=Setting.get_value('apk.url'),
                           telegram=Setting.get_value('support.telegram'),
                           login_url=Setting.get_value('web.login_url'),
                           signup_url=Setting.get_value('web.signup_url')
                           )
