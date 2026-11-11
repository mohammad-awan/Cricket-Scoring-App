(() => {
    'use strict';
    const toggle = document.getElementById('nav-toggle');
    const nav = document.getElementById('top-navigation');
    const loading = document.getElementById('page-loading');
    const setBallContext = path => {
        loading.classList.toggle('white-ball', /match|scor|competitions|tournament/.test(path));
    };
    setBallContext(location.pathname);
    let pending = 0;
    let timer;
    let navigating = false;
    const setMenu = open => {
        toggle.setAttribute('aria-expanded', String(open));
        nav.classList.toggle('is-open', open);
    };
    toggle.addEventListener('click', () => setMenu(toggle.getAttribute('aria-expanded') !== 'true'));
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && nav.classList.contains('is-open')) {
            setMenu(false);
            toggle.focus();
        }
    });
    document.addEventListener('click', event => {
        if (!event.target.closest('.club-header')) setMenu(false);
        const link = event.target.closest('a[href]');
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
        const url = new URL(link.href, location.href);
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) || (url.pathname === location.pathname && url.search === location.search)) return;
        setBallContext(url.pathname);
        navigating = true;
        document.getElementById('page-loading-label').textContent = url.pathname.startsWith('/player-profile') ? 'Opening player profile' : 'Taking the field';
        loading.hidden = false;
        // If navigation is cancelled or the server stalls, never trap the interface.
        setTimeout(() => { navigating = false; if (!pending) loading.hidden = true; }, 12000);
    });
    window.CricketUI = {
        begin() {
            pending++;
            if (pending === 1) timer = setTimeout(() => { loading.hidden = false; }, 220);
            let finished = false;
            return () => {
                if (finished) return;
                finished = true;
                pending--;
                if (!pending) { clearTimeout(timer); if (!navigating) loading.hidden = true; }
            };
        }
    };
    // Covers initial document assets as well as asynchronous API loading.
    const finishInitial = window.CricketUI.begin();
    if (document.readyState === 'complete') finishInitial();
    else window.addEventListener('load', finishInitial, { once: true });
    window.addEventListener('pageshow', () => { navigating = false; if (!pending) loading.hidden = true; });
    window.matchMedia('(min-width: 701px)').addEventListener('change', event => { if (event.matches) setMenu(false); });
})();
