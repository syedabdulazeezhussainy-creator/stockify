// Small UI enhancements
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("button:not(.menu-btn)").forEach(btn => {
        btn.addEventListener("click", () => {
            btn.style.transform = "scale(0.95)";
            setTimeout(() => btn.style.transform = "scale(1)", 150);
        });
    });

    // Auto-hide flash messages after 3 seconds
    setTimeout(() => {
        document.querySelectorAll('.flash-messages .alert').forEach(alert => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        });
    }, 3000);
});