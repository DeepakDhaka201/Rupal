// static/js/referral-admin.js
const ReferralAdmin = {
    editCommission: function(id) {
        fetch(`/admin/referrals/commissions/${id}`)
            .then(response => response.json())
            .then(data => {
                const modalBody = document.querySelector('#editCommissionModal .modal-body');
                modalBody.innerHTML = this.getEditFormHTML(data);

                const form = document.getElementById('editCommissionForm');
                form.action = `/admin/referrals/commissions/${id}/edit`;

                const modal = new bootstrap.Modal(document.getElementById('editCommissionModal'));
                modal.show();
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Failed to load commission data');
            });
    },

    getEditFormHTML: function(data) {
        return `
            <div class="mb-3">
                <label class="form-label">Buy Commission (%)</label>
                <input type="number" name="buy_commission" class="form-control" required
                       step="0.01" min="0" max="100" value="${data.buy_commission_percent}">
            </div>
            <div class="mb-3">
                <label class="form-label">Sell Commission (%)</label>
                <input type="number" name="sell_commission" class="form-control" required
                       step="0.01" min="0" max="100" value="${data.sell_commission_percent}">
            </div>
            <div class="mb-3">
                <label class="form-label">Min Amount (USDT)</label>
                <input type="number" name="min_amount" class="form-control" required
                       step="0.01" min="0" value="${data.min_amount_usdt}">
            </div>
            <div class="mb-3">
                <div class="form-check">
                    <input type="checkbox" name="is_active" class="form-check-input"
                           id="is_active" ${data.is_active ? 'checked' : ''}>
                    <label class="form-check-label" for="is_active">Active</label>
                </div>
            </div>
        `;
    },

    init: function() {
        // Handle edit form submission
        document.getElementById('editCommissionForm').addEventListener('submit', function(e) {
            e.preventDefault();
            ReferralAdmin.submitEditForm(this);
        });

        // Handle add form submission
        document.getElementById('addCommissionForm').addEventListener('submit', function(e) {
            e.preventDefault();
            ReferralAdmin.submitAddForm(this);
        });
    },

    submitEditForm: function(form) {
        const formData = new FormData(form);
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert(data.message || 'Failed to update commission');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to update commission');
        });
    },

    submitAddForm: function(form) {
        const formData = new FormData(form);
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert(data.message || 'Failed to add commission');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to add commission');
        });
    }
};

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', function() {
    ReferralAdmin.init();
});