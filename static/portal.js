document.addEventListener('DOMContentLoaded', () => {
    const viewport = document.getElementById('portalViewport');
    const doorBtn = document.getElementById('portalDoorBtn');
    const curtain = document.getElementById('portalCurtain');

    if (!viewport || !doorBtn) return;

    const targetUrl = viewport.dataset.targetUrl || '/home';
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let isTransitioning = false;

    function enterAdiwiyataHome() {
        if (isTransitioning) return;
        isTransitioning = true;

        if (prefersReducedMotion) {
            window.location.href = targetUrl;
            return;
        }

        viewport.classList.add('is-entering');

        setTimeout(() => {
            if (curtain) curtain.classList.add('active');
        }, 720);

        setTimeout(() => {
            window.location.href = targetUrl;
        }, 1220);
    }

    doorBtn.addEventListener('click', enterAdiwiyataHome);

    doorBtn.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            enterAdiwiyataHome();
        }
    });
});