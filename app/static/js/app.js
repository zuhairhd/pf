// Sidebar toggle
document.addEventListener('DOMContentLoaded', function() {
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
            document.cookie = `sidebar_collapsed=${sidebar.classList.contains('collapsed')}; path=/; max-age=2592000`;
        });
    }
    
    // Mobile sidebar
    if (window.innerWidth <= 768) {
        sidebar.classList.remove('collapsed');
    }
});

// Theme toggle
function toggleTheme() {
    const body = document.body;
    const isDark = body.classList.toggle('dark-theme');
    document.cookie = `theme=${isDark ? 'dark' : 'light'}; path=/; max-age=2592000`;
}

// Notification count update
function updateNotificationCount(count) {
    const badge = document.getElementById('notification-count');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'block' : 'none';
    }
}

// HTMX config
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Add auth token to HTMX requests
    const token = localStorage.getItem('access_token');
    if (token) {
        evt.detail.headers['Authorization'] = 'Bearer ' + token;
    }
});

// Form validation helpers
function validatePassword(password) {
    const minLength = 8;
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasNumber = /\d/.test(password);
    const hasSpecial = /[!@#$%^&*]/.test(password);
    
    return password.length >= minLength && hasUpper && hasLower && hasNumber;
}

// Currency formatter
function formatCurrency(amount, currency = 'OMR') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 3,
        maximumFractionDigits: 3,
    }).format(amount);
}

// Date formatter
function formatDate(date) {
    return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}
