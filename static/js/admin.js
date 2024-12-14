/* static/js/admin.js */
function confirmAction(message) {
    return confirm(message || 'Are you sure you want to perform this action?');
}

function handleAjaxError(error) {
    console.error('Ajax error:', error);
    alert('An error occurred. Please try again.');
}

$(document).ready(function() {
    // Initialize tooltips
    $('[data-bs-toggle="tooltip"]').tooltip();

    // Handle ajax form submissions
    $('.ajax-form').on('submit', function(e) {
        e.preventDefault();
        let form = $(this);

        $.ajax({
            url: form.attr('action'),
            method: form.attr('method'),
            data: form.serialize(),
            success: function(response) {
                if (response.success) {
                    location.reload();
                } else {
                    alert(response.message || 'Operation failed');
                }
            },
            error: handleAjaxError
        });
    });
});