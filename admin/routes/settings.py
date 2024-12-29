# admin/settings_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify

from auth.utils import admin_required
from models.models import db, Setting
from datetime import datetime
import json

settings_bp = Blueprint('settings', __name__, url_prefix='/admin/settings')


@settings_bp.route('/')
@admin_required
def list_settings(user):
    settings = Setting.query.order_by(Setting.key).all()
    return render_template('admin/settings/list.html', settings=settings)


@settings_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add_setting(current_user):
    if request.method == 'POST':
        key = request.form.get('key')
        value = request.form.get('value')
        description = request.form.get('description')
        type = request.form.get('type', 'text')
        is_public = request.form.get('is_public') == 'on'

        if not key or not value:
            flash('Key and value are required', 'error')
            return redirect(url_for('settings.add_setting'))

        # Check if key already exists
        if Setting.query.filter_by(key=key).first():
            flash('Setting key already exists', 'error')
            return redirect(url_for('settings.add_setting'))

        # Validate value based on type
        try:
            if type == 'number':
                float(value)
            elif type == 'json':
                json.loads(value)
            elif type == 'boolean':
                value = str(value.lower() == 'true').lower()
        except:
            flash('Invalid value for selected type', 'error')
            return redirect(url_for('settings.add_setting'))

        setting = Setting(
            key=key,
            value=value,
            description=description,
            type=type,
            is_public=is_public,
            updated_by=current_user.id
        )

        db.session.add(setting)
        db.session.commit()

        flash('Setting added successfully', 'success')
        return redirect(url_for('settings.list_settings'))

    return render_template('admin/settings/add.html')


@settings_bp.route('/<int:setting_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_setting(current_user, setting_id):
    setting = Setting.query.get_or_404(setting_id)

    if request.method == 'POST':
        value = request.form.get('value')
        description = request.form.get('description')
        is_public = request.form.get('is_public') == 'on'

        if not value:
            flash('Value is required', 'error')
            return redirect(url_for('settings.edit_setting', setting_id=setting_id))

        # Validate value based on type
        try:
            if setting.type == 'number':
                float(value)
            elif setting.type == 'json':
                json.loads(value)
            elif setting.type == 'boolean':
                value = str(value.lower() == 'true').lower()
        except:
            flash('Invalid value for setting type', 'error')
            return redirect(url_for('settings.edit_setting', setting_id=setting_id))

        setting.value = value
        setting.description = description
        setting.is_public = is_public
        setting.updated_by = current_user.id
        db.session.commit()

        flash('Setting updated successfully', 'success')
        return redirect(url_for('settings.list_settings'))

    return render_template('admin/settings/edit.html', setting=setting)


@settings_bp.route('/<int:setting_id>/delete', methods=['POST'])
def delete_setting(setting_id):
    setting = Setting.query.get_or_404(setting_id)

    db.session.delete(setting)
    db.session.commit()

    flash('Setting deleted successfully', 'success')
    return redirect(url_for('settings.list_settings'))