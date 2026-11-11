(() => {
    "use strict";

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function safeUrl(value) {
        const text = String(value ?? "").trim();
        if (!/^https?:\/\//i.test(text) && !/^\/(?!\/)/.test(text)) return null;
        try {
            const url = new URL(text, window.location.href);
            return ["http:", "https:"].includes(url.protocol) ? url.href : null;
        } catch {
            return null;
        }
    }

    function image(url, name, kind) {
        const src = safeUrl(url);
        const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
        const initials = ((parts[0]?.[0] || "?") +
            (parts.length > 1 ? parts.at(-1)[0] : "")).toUpperCase();
        return `<span class="record-image record-image-${kind}" aria-hidden="true">
            <span>${escapeHtml(initials)}</span>
            ${src ? `<img src="${escapeHtml(src)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}
        </span>`;
    }

    function sourceLink(value) {
        const href = safeUrl(value);
        return href
            ? `<a class="record-source" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Image source</a>`
            : "";
    }

    function map(location, latitude, longitude) {
        const query = String(location || "").trim() ||
            (Number.isFinite(latitude) && Number.isFinite(longitude) ? `${latitude}, ${longitude}` : "");
        if (!query) return "";
        const encoded = encodeURIComponent(query);
        return `<div class="venue-map">
            <iframe title="${escapeHtml(query)} location map"
                src="https://maps.google.com/maps?q=${encoded}&amp;z=15&amp;output=embed"
                loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>
            <a href="https://www.google.com/maps/search/?api=1&amp;query=${encoded}"
                target="_blank" rel="noopener noreferrer">Open larger map</a>
        </div>`;
    }

    // Keep initials visible when a remote image is missing or blocks hotlinking.
    document.addEventListener("error", (event) => {
        if (event.target.matches?.(".record-image img")) event.target.remove();
    }, true);

    window.ProfileAssets = { safeUrl, image, sourceLink, map };
})();
