document.addEventListener('DOMContentLoaded', () => {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // 1. Sticky Navbar Scroll Effect & Mobile Drawer
    const navbar = document.getElementById('siteNavbar');
    const mobileToggle = document.getElementById('navMobileToggle');
    const navMenu = document.getElementById('navMenu');

    function handleNavbarScroll() {
        if (!navbar) return;
        if (window.scrollY > 28) {
            navbar.classList.add('is-scrolled');
        } else {
            navbar.classList.remove('is-scrolled');
        }
    }

    window.addEventListener('scroll', handleNavbarScroll, { passive: true });
    handleNavbarScroll();

    if (mobileToggle && navMenu) {
        mobileToggle.addEventListener('click', () => {
            const isOpen = navMenu.classList.toggle('open');
            mobileToggle.setAttribute('aria-expanded', String(isOpen));
        });

        navMenu.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navMenu.classList.remove('open');
                mobileToggle.setAttribute('aria-expanded', 'false');
            });
        });
    }

    // 2. Scroll-Triggered Reveal (IntersectionObserver + Fallback)
    const revealEls = document.querySelectorAll('.reveal-on-scroll');
    if ('IntersectionObserver' in window && !prefersReducedMotion) {
        const revealObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-visible');
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.14, rootMargin: '0px 0px -40px 0px' }
        );
        revealEls.forEach(el => revealObserver.observe(el));
    } else {
        revealEls.forEach(el => el.classList.add('is-visible'));
    }

    // 3. Animated Numerical Counters untuk Statistik SQLite
    const counterEls = document.querySelectorAll('[data-counter]');

    function animateCounter(el) {
        const target = parseInt(el.dataset.counter || '0', 10);
        if (isNaN(target) || target <= 0 || prefersReducedMotion) {
            el.textContent = String(Math.max(0, target || 0));
            return;
        }

        const duration = 1200;
        const startTime = performance.now();

        function step(now) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(eased * target);
            el.textContent = current.toLocaleString('id-ID');

            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                el.textContent = target.toLocaleString('id-ID');
            }
        }

        requestAnimationFrame(step);
    }

    if ('IntersectionObserver' in window && !prefersReducedMotion) {
        const counterObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        animateCounter(entry.target);
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.3 }
        );
        counterEls.forEach(el => counterObserver.observe(el));
    } else {
        counterEls.forEach(el => animateCounter(el));
    }

    // 4. Parallax Ringan pada Desktop (Nonaktif otomatis di mobile & reduced-motion)
    const parallaxEls = document.querySelectorAll('[data-parallax-speed]');
    if (parallaxEls.length > 0 && !prefersReducedMotion) {
        let ticking = false;

        function updateParallax() {
            if (window.innerWidth < 960) {
                parallaxEls.forEach(el => {
                    el.style.transform = '';
                });
                ticking = false;
                return;
            }

            const scrollY = window.scrollY;
            parallaxEls.forEach(el => {
                const speed = parseFloat(el.dataset.parallaxSpeed || '0');
                const offset = Math.round(scrollY * speed);
                el.style.transform = `translate3d(0, ${offset}px, 0)`;
            });
            ticking = false;
        }

        window.addEventListener(
            'scroll',
            () => {
                if (!ticking) {
                    requestAnimationFrame(updateParallax);
                    ticking = true;
                }
            },
            { passive: true }
        );
    }
});