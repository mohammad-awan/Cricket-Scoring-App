(() => {

    "use strict";

    const root = document.getElementById("tournaments-page");

    if (!root) {
        return;
    }

    const UI = window.TournamentUI;
    const PAGE_SIZE = 20;

    const elements = {
        stats: document.getElementById("tournament-stats"),
        search: document.getElementById("search-input"),
        status: document.getElementById("status-filter"),
        archived: document.getElementById("include-archived"),
        refresh: document.getElementById("refresh-list"),
        body: document.getElementById("table-body"),
        loading: document.getElementById("table-loading"),
        empty: document.getElementById("table-empty"),
        summary: document.getElementById("pagination-summary"),
        previous: document.getElementById("previous-page"),
        next: document.getElementById("next-page"),
        indicator: document.getElementById("page-indicator"),
    };

    const state = {
        all: [],
        page: 1,
    };


    function filtered() {
        const term = elements.search.value.trim().toLowerCase();
        const status = elements.status.value;

        return state.all.filter((item) => {
            if (status && item.status !== status) {
                return false;
            }
            if (!term) {
                return true;
            }
            return [item.name, item.season, item.organizer, item.slug]
                .some((value) => String(value || "").toLowerCase().includes(term));
        });
    }


    function renderStats() {
        const count = (status) => state.all.filter((item) => item.status === status).length;
        const cards = [
            ["Tournaments", state.all.filter((item) => item.status !== "archived").length, "C"],
            ["Open for entries", count("registration_open"), "R"],
            ["Scheduled / live", count("scheduled") + count("live"), "L"],
            ["Drafts", count("draft"), "D"],
        ];

        elements.stats.innerHTML = cards.map(([label, value, icon]) => `
            <article class="stat-card">
                <div class="stat-icon">${icon}</div>
                <div>
                    <span>${UI.escapeHtml(label)}</span>
                    <strong>${value}</strong>
                </div>
            </article>`).join("");
    }


    function renderTable() {
        const rows = filtered();
        const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
        state.page = Math.min(state.page, pages);
        const pageRows = rows.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);

        elements.loading.classList.add("hidden");
        elements.empty.classList.toggle("hidden", rows.length > 0);

        elements.body.innerHTML = pageRows.map((item) => {
            const dates = item.start_date || item.end_date
                ? `${UI.formatDate(item.start_date)} – ${UI.formatDate(item.end_date)}`
                : "Dates not set";

            return `
                <tr>
                    <td>
                        <a class="name-cell" href="/competitions/${item.id}">
                            ${UI.logoMark(item.name, true)}
                            <span>
                                <strong>${UI.escapeHtml(item.name)}</strong>
                                <small>${UI.escapeHtml(item.season || "No season")} · ${UI.escapeHtml(item.slug)}</small>
                            </span>
                        </a>
                    </td>
                    <td>${UI.escapeHtml(item.organizer || "—")}</td>
                    <td>${UI.escapeHtml(dates)}</td>
                    <td>${UI.statusBadge(item.status)}</td>
                    <td>
                        <div class="row-actions">
                            <a class="table-action" href="/competitions/${item.id}">Open</a>
                            ${item.status === "archived" ? "" : `<a class="table-action" href="/competitions/${item.id}/edit">Edit</a>`}
                        </div>
                    </td>
                </tr>`;
        }).join("");

        elements.summary.textContent = `${rows.length} tournament${rows.length === 1 ? "" : "s"}`;
        elements.indicator.textContent = `Page ${state.page} of ${pages}`;
        elements.previous.disabled = state.page <= 1;
        elements.next.disabled = state.page >= pages;
    }


    async function load() {
        elements.loading.classList.remove("hidden");
        elements.loading.textContent = "Loading tournaments...";
        elements.body.innerHTML = "";

        try {
            state.all = await API.listAll("tournaments", {
                include_archived: elements.archived.checked || undefined,
            });
            renderStats();
            renderTable();
        } catch (error) {
            elements.loading.textContent = UI.errorText(error);
        }
    }


    let searchTimer = null;

    elements.search.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => {
            state.page = 1;
            renderTable();
        }, 200);
    });

    elements.status.addEventListener("change", () => {
        if (elements.status.value === "archived") {
            elements.archived.checked = true;
            load();
            return;
        }
        state.page = 1;
        renderTable();
    });

    elements.archived.addEventListener("change", load);
    elements.refresh.addEventListener("click", load);
    elements.previous.addEventListener("click", () => {
        state.page -= 1;
        renderTable();
    });
    elements.next.addEventListener("click", () => {
        state.page += 1;
        renderTable();
    });

    load();

})();
