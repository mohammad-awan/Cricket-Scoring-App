(() => {

    "use strict";


    const root =
        document.getElementById(
            "matches-page"
        );


    if (!root) {
        return;
    }


    const elements = {

        add:
            document.getElementById("add-match"),

        search:
            document.getElementById("search-input"),

        statusFilter:
            document.getElementById("status-filter"),

        refresh:
            document.getElementById("refresh-list"),

        body:
            document.getElementById("table-body"),

        loading:
            document.getElementById("table-loading"),

        empty:
            document.getElementById("table-empty"),

        summary:
            document.getElementById("pagination-summary"),

        previous:
            document.getElementById("previous-page"),

        next:
            document.getElementById("next-page"),

        indicator:
            document.getElementById("page-indicator"),

        modal:
            document.getElementById("match-modal"),

        closeModal:
            document.getElementById("close-modal"),

        cancelModal:
            document.getElementById("cancel-modal"),

        form:
            document.getElementById("match-form"),

        formError:
            document.getElementById("form-error"),

        save:
            document.getElementById("save-match"),

        teamA:
            document.getElementById("team-a-select"),

        teamB:
            document.getElementById("team-b-select"),

        venue:
            document.getElementById("venue-select"),

        tournament:
            document.getElementById("tournament-select"),

    };


    const state = {

        page: 1,
        pageSize: 10,
        search: "",
        status: "",
        pages: 0,
        total: 0,
        loadSequence: 0,
        referenceDataLoaded: false,

    };


    const COLUMN_COUNT = 8;


    function escapeHtml(value) {

        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");

    }


    function humanStatus(value) {

        return String(value || "unknown")
            .replaceAll("_", " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());

    }


    function formatOvers(match) {

        if (match.total_overs === null || match.total_overs === undefined) {
            return "Unlimited";
        }

        return `${match.total_overs} ov · ${match.balls_per_over}/over`;

    }


    function formatDate(value) {

        if (!value) {
            return "Not scheduled";
        }

        try {

            return new Date(value).toLocaleString();

        } catch (error) {

            return value;

        }

    }


    function populateSelect(select, items, { placeholder, label } = {}) {

        const options = [];

        if (placeholder) {
            options.push(`<option value="">${escapeHtml(placeholder)}</option>`);
        }

        items.forEach((item) => {

            options.push(
                `<option value="${item.id}">${escapeHtml(label(item))}</option>`
            );

        });

        select.innerHTML = options.join("");

    }


    async function loadReferenceData() {

        if (state.referenceDataLoaded) {
            return;
        }

        try {

            const [teams, venues, tournaments] = await Promise.all([
                window.API.list("teams", { page_size: 100 }),
                window.API.list("venues", { page_size: 100 }),
                window.API.list("tournaments", { page_size: 100 }),
            ]);

            const activeTeams = (teams.items || []).filter(
                (item) => item.status === "active"
            );

            const activeVenues = (venues.items || []).filter(
                (item) => item.status === "active"
            );

            populateSelect(elements.teamA, activeTeams, {
                placeholder: "Select team A",
                label: (item) => `${item.name} (${item.code})`,
            });

            populateSelect(elements.teamB, activeTeams, {
                placeholder: "Select team B",
                label: (item) => `${item.name} (${item.code})`,
            });

            populateSelect(elements.venue, activeVenues, {
                placeholder: "No venue yet",
                label: (item) => `${item.name} — ${item.city}`,
            });

            elements.tournament.innerHTML =
                `<option value="">No tournament</option>` +
                (tournaments.items || [])
                    .map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`)
                    .join("");

            state.referenceDataLoaded = true;

        } catch (error) {

            window.showToast(
                `Could not load teams/venues/tournaments: ${error.message}`,
                "error"
            );

        }

    }


    function renderRows(items) {

        if (!items.length) {

            elements.body.innerHTML = "";
            elements.empty.classList.remove("hidden");
            return;

        }

        elements.empty.classList.add("hidden");

        elements.body.innerHTML = items
            .map((match) => {

                const canSetup =
                    match.status === "draft" || match.status === "ready";

                return `
                    <tr>

                        <td>
                            <strong>${escapeHtml(match.title || "Untitled match")}</strong>
                            <br>
                            <span class="muted">
                                ${escapeHtml(match.team_a.short_name)}
                                vs
                                ${escapeHtml(match.team_b.short_name)}
                            </span>
                        </td>

                        <td>${escapeHtml(humanStatus(match.match_type))}</td>

                        <td>${match.players_per_side}</td>

                        <td>${escapeHtml(formatOvers(match))}</td>

                        <td>${match.venue ? escapeHtml(match.venue.name) : '<span class="muted">—</span>'}</td>

                        <td>${escapeHtml(formatDate(match.scheduled_at))}</td>

                        <td>
                            <span class="status-badge status-${match.status}">
                                ${escapeHtml(humanStatus(match.status))}
                            </span>
                        </td>

                        <td class="row-actions">
                            <a
                                class="table-action"
                                href="/match-setup/${match.id}"
                            >
                                ${canSetup ? "Setup" : "View"}
                            </a>
                        </td>

                    </tr>
                `;

            })
            .join("");

    }


    function updatePagination() {

        const visiblePage = state.pages === 0 ? 0 : state.page;

        elements.summary.textContent =
            `${state.total.toLocaleString()} ${state.total === 1 ? "match" : "matches"}`;

        elements.indicator.textContent = `Page ${visiblePage} of ${state.pages}`;

        elements.previous.disabled = state.page <= 1 || state.pages === 0;
        elements.next.disabled = state.pages === 0 || state.page >= state.pages;

    }


    async function loadMatches() {

        const sequence = ++state.loadSequence;

        elements.loading.classList.remove("hidden");
        elements.empty.classList.add("hidden");
        elements.body.innerHTML = "";

        try {

            const result = await window.API.matchesList({
                page: state.page,
                page_size: state.pageSize,
                search: state.search || null,
                match_status: state.status || null,
            });

            if (sequence !== state.loadSequence) {
                return;
            }

            state.total = result.total;
            state.pages = result.pages;

            if (state.pages > 0 && state.page > state.pages) {
                state.page = state.pages;
                await loadMatches();
                return;
            }

            renderRows(result.items || []);
            updatePagination();

        } catch (error) {

            if (sequence !== state.loadSequence) {
                return;
            }

            elements.body.innerHTML = `
                <tr>
                    <td class="table-error" colspan="${COLUMN_COUNT}">
                        ${escapeHtml(error.message)}
                    </td>
                </tr>
            `;

            state.total = 0;
            state.pages = 0;
            updatePagination();

        } finally {

            if (sequence === state.loadSequence) {
                elements.loading.classList.add("hidden");
            }

        }

    }


    function openModal() {

        elements.form.reset();
        elements.formError.classList.add("hidden");
        elements.formError.textContent = "";

        elements.modal.classList.remove("hidden");
        document.body.classList.add("modal-open");

        loadReferenceData();

    }


    function closeModal() {

        elements.modal.classList.add("hidden");
        document.body.classList.remove("modal-open");

    }


    function buildPayload() {

        const form = elements.form;

        const title = form.elements.title.value.trim();
        const totalOvers = form.elements.total_overs.value;
        const scheduledAt = form.elements.scheduled_at.value;
        const tournamentId = form.elements.tournament_id.value;
        const venueId = form.elements.venue_id.value;

        return {
            title: title || null,
            team_a_id: form.elements.team_a_id.value,
            team_b_id: form.elements.team_b_id.value,
            venue_id: venueId || null,
            tournament_id: tournamentId || null,
            match_type: form.elements.match_type.value,
            players_per_side: Number(form.elements.players_per_side.value),
            total_overs: totalOvers === "" ? null : Number(totalOvers),
            balls_per_over: Number(form.elements.balls_per_over.value),
            innings_per_team: Number(form.elements.innings_per_team.value),
            scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        };

    }


    async function submitForm(event) {

        event.preventDefault();

        if (!elements.form.reportValidity()) {
            return;
        }

        elements.save.disabled = true;
        elements.formError.classList.add("hidden");

        try {

            const payload = buildPayload();
            const created = await window.API.matchCreate(payload);

            window.showToast("Match created. Continue with toss and playing teams.");
            closeModal();

            window.location.href = `/match-setup/${created.id}`;

        } catch (error) {

            elements.formError.textContent = error.message;
            elements.formError.classList.remove("hidden");

        } finally {

            elements.save.disabled = false;

        }

    }


    let searchTimer = null;


    elements.search.addEventListener("input", () => {

        window.clearTimeout(searchTimer);

        searchTimer = window.setTimeout(() => {

            state.search = elements.search.value.trim();
            state.page = 1;
            loadMatches();

        }, 300);

    });


    elements.statusFilter.addEventListener("change", () => {

        state.status = elements.statusFilter.value;
        state.page = 1;
        loadMatches();

    });


    elements.refresh.addEventListener("click", loadMatches);

    elements.add.addEventListener("click", openModal);
    elements.closeModal.addEventListener("click", closeModal);
    elements.cancelModal.addEventListener("click", closeModal);
    elements.form.addEventListener("submit", submitForm);


    elements.modal.addEventListener("click", (event) => {

        if (event.target === elements.modal) {
            closeModal();
        }

    });


    document.addEventListener("keydown", (event) => {

        if (event.key === "Escape" && !elements.modal.classList.contains("hidden")) {
            closeModal();
        }

    });


    elements.previous.addEventListener("click", () => {

        if (state.page <= 1) {
            return;
        }

        state.page -= 1;
        loadMatches();

    });


    elements.next.addEventListener("click", () => {

        if (state.page >= state.pages) {
            return;
        }

        state.page += 1;
        loadMatches();

    });


    loadMatches();

})();
