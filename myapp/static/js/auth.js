/* Auth page interactions: tab toggle + password visibility */
document.addEventListener('DOMContentLoaded', function () {

    /* ---------- Sign Up / Log In toggle ---------- */
    var toggleBtns = document.querySelectorAll('.auth-toggle-btn');
    var panels = {
        signup: document.getElementById('panel-signup'),
        login: document.getElementById('panel-login')
    };

    function activateTab(tab) {
        toggleBtns.forEach(function (btn) {
            var isActive = btn.dataset.tab === tab;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        Object.keys(panels).forEach(function (key) {
            if (panels[key]) {
                panels[key].classList.toggle('is-active', key === tab);
            }
        });
    }

    toggleBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            activateTab(btn.dataset.tab);
        });
    });

    /* ---------- Password visibility toggle ---------- */
    document.querySelectorAll('[data-toggle-password]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var field = btn.closest('.auth-field');
            var input = field ? field.querySelector('input') : null;
            if (!input) return;

            var showing = input.type === 'text';
            input.type = showing ? 'password' : 'text';

            var icon = btn.querySelector('i');
            if (icon) {
                icon.classList.toggle('bi-eye-slash', showing);
                icon.classList.toggle('bi-eye', !showing);
            }
            btn.classList.toggle('is-visible', !showing);
            btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
        });
    });
});
