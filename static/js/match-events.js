(() => {
    'use strict';
    const root = document.querySelector('#live-scoring-page, #live-viewer-page');
    if (!root) return;
    const banner = document.createElement('aside');
    banner.className = 'broadcast-event';
    banner.hidden = true;
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    banner.setAttribute('aria-atomic', 'true');
    banner.innerHTML = '<div class="event-art" aria-hidden="true"><span class="event-ring"></span><span class="event-ball"></span><span class="event-wickets"><i></i><i></i><i></i><b></b></span></div><div class="event-copy"><span class="event-kicker">LIVE • BALL CONFIRMED</span><strong class="event-title"></strong><span class="event-subtitle"></span></div><span class="event-number" aria-hidden="true"></span><span class="event-lifetime" aria-hidden="true"></span>';
    root.appendChild(banner);
    const seen = new Set();
    let timer;
    function classify(d) {
        if (d.wicket_type) return ['wicket', 'WICKET', 'OUT!', 'W'];
        if (d.wide_runs > 0) return ['wide', 'WIDE BALL', 'EXTRA RUN' + (d.wide_runs > 1 ? 'S • ' + d.wide_runs : ''), 'WD'];
        if (d.no_ball_runs > 0) return ['no-ball', 'NO BALL', 'EXTRA RUN' + (d.batter_runs ? ' • ' + d.batter_runs + ' OFF THE BAT' : ''), 'NB'];
        if (d.bye_runs > 0 || d.leg_bye_runs > 0) return ['extras', d.leg_bye_runs ? 'LEG BYES' : 'BYES', d.total_runs + ' EXTRA RUN' + (d.total_runs === 1 ? '' : 'S'), '+' + d.total_runs];
        if (d.batter_runs === 6) return ['six', 'SIX!', 'MAXIMUM!', '6'];
        if (d.batter_runs === 4) return ['four', 'FOUR!', 'BOUNDARY!', '4'];
        if (d.total_runs === 1) return ['single', 'SINGLE', '1 RUN', '1'];
        if (d.total_runs === 0) return ['dot', 'DOT BALL', 'NO RUN', '0'];
        return ['runs', d.total_runs + ' RUNS', 'KEEP THE SCORE MOVING', String(d.total_runs)];
    }
    function accept(scoring, type = 'delivery_recorded') {
        // Corrections cancel celebrations. Snapshots and reconnects never replay history.
        if (type === 'delivery_corrected') { clearTimeout(timer); banner.hidden = true; return; }
        if (type !== 'delivery_recorded' || !scoring) return;
        const delivery = (scoring.recent_deliveries || []).reduce((latest, d) => !latest || d.sequence > latest.sequence ? d : latest, null);
        if (!delivery || delivery.status !== 'recorded' || !delivery.id || seen.has(delivery.id)) return;
        seen.add(delivery.id);
        if (seen.size > 256) seen.delete(seen.values().next().value);
        const [kind, title, subtitle, number] = classify(delivery);
        clearTimeout(timer);
        banner.hidden = true;
        banner.className = 'broadcast-event event-' + kind;
        banner.querySelector('.event-title').textContent = title;
        banner.querySelector('.event-subtitle').textContent = subtitle;
        banner.querySelector('.event-number').textContent = number;
        banner.querySelector('.event-kicker').textContent = 'LIVE • ' + delivery.over_number + '.' + delivery.ball_number + ' • BALL CONFIRMED';
        // Restart finite CSS effects when consecutive deliveries have the same outcome.
        void banner.offsetWidth;
        banner.hidden = false;
        timer = setTimeout(() => { banner.hidden = true; }, ['six', 'four', 'wicket'].includes(kind) ? 3200 : 2000);
    }
    window.MatchEvents = { accept };
    window.addEventListener('pagehide', () => { clearTimeout(timer); banner.hidden = true; });
})();
