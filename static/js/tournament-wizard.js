(() => {

    "use strict";

    const root = document.getElementById("tournament-wizard");

    if (!root) {
        return;
    }

    const UI = window.TournamentUI;

    const STEPS = [
        { key: "basics", label: "Basics" },
        { key: "identity", label: "Identity & branding" },
        { key: "participation", label: "Participation" },
        { key: "rules", label: "Rules & format" },
        { key: "review", label: "Review" },
    ];

    const elements = {
        steps: document.getElementById("wizard-steps"),
        body: document.getElementById("wizard-body"),
        lock: document.getElementById("wizard-lock"),
        title: document.getElementById("wizard-title"),
    };

    const state = {
        id: root.dataset.tournamentId || null,
        tournament: null,
        rules: null,
        venues: [],
        series: [],
        assets: [],
        step: 0,
        editor: null,
    };


    function stepFromUrl() {
        const value = Number(new URLSearchParams(window.location.search).get("step"));
        return Number.isInteger(value) && value >= 1 && value <= STEPS.length ? value - 1 : 0;
    }


    function setUrl() {
        const base = state.id ? `/competitions/${state.id}/edit` : "/competitions/new";
        window.history.replaceState(null, "", `${base}?step=${state.step + 1}`);
    }


    function configLocked() {
        return state.tournament && UI.CONFIG_LOCKED.has(state.tournament.status);
    }


    function rulesLocked() {
        return state.tournament && UI.RULES_LOCKED.has(state.tournament.status);
    }


    function renderSteps() {
        elements.steps.innerHTML = STEPS.map((step, index) => {
            const classes = ["wizard-step"];
            if (index === state.step) {
                classes.push("active");
            } else if (state.id && index < state.step) {
                classes.push("done");
            }
            const enabled = index === 0 || Boolean(state.id);
            return `
                <li>
                    <button class="${classes.join(" ")}" type="button" data-step="${index}" ${enabled ? "" : "disabled"}>
                        <span class="wizard-step-number">${index + 1}</span>
                        ${UI.escapeHtml(step.label)}
                    </button>
                </li>`;
        }).join("");
    }


    function footer({ back = true, submitLabel = "Save & continue", submitDisabled = false } = {}) {
        return `
            <div class="form-error hidden" data-role="error" style="margin:0 22px 16px"></div>
            <div class="wizard-footer">
                ${back && state.step > 0 ? `<button class="button button-secondary" type="button" data-nav="back">Back</button>` : "<span></span>"}
                <div class="action-row">
                    ${state.id && state.step < STEPS.length - 1 ? `<button class="button button-secondary" type="button" data-nav="skip">Skip</button>` : ""}
                    <button class="button button-primary" type="submit" ${submitDisabled ? "disabled" : ""}>${UI.escapeHtml(submitLabel)}</button>
                </div>
            </div>`;
    }


    function formPanel(title, subtitle, fieldsHtml, options = {}) {
        return `
            <form class="panel" data-role="step-form" novalidate>
                <div class="panel-header t-panel-header">
                    <div>
                        <h2>${UI.escapeHtml(title)}</h2>
                        <p>${UI.escapeHtml(subtitle)}</p>
                    </div>
                </div>
                <div class="panel-body">
                    <fieldset style="border:0;margin:0;padding:0" ${options.disabled ? "disabled" : ""}>
                        <div class="form-grid">${fieldsHtml}</div>
                    </fieldset>
                </div>
                ${footer(options)}
            </form>`;
    }


    function showError(message) {
        const box = elements.body.querySelector('[data-role="error"]');
        if (!box) {
            showToast(message, "error");
            return;
        }
        box.textContent = message;
        box.classList.toggle("hidden", !message);
    }


    // =========================
    // STEPS
    // =========================

    function renderBasics() {
        elements.body.innerHTML = formPanel(
            "Basics",
            "Name, edition and dates. The slug is generated automatically if left blank.",
            UI.renderFields(UI.BASIC_FIELDS, state.tournament || {}),
            { back: false, submitLabel: state.id ? "Save & continue" : "Create draft & continue" },
        );
    }


    async function saveBasics(form) {
        if (!form.reportValidity()) {
            return false;
        }
        const payload = UI.readFields(form, UI.BASIC_FIELDS);

        if (state.id) {
            // A blank slug on update would regenerate it; keep the current one.
            if (!payload.slug) {
                delete payload.slug;
            }
            await API.tournament.updateBasics(state.id, payload);
        } else {
            const created = await API.create("tournaments", payload);
            state.id = created.id;
            showToast("Draft tournament created.");
        }
        return true;
    }


    function renderIdentity() {
        const tournament = state.tournament;
        elements.body.innerHTML = `
            <div class="t-grid-sidebar">
                ${formPanel(
                    "Identity & branding",
                    "Public identity, sponsorship and contact details.",
                    UI.renderFields(UI.IDENTITY_FIELDS, tournament, { series_id: UI.seriesOptions(state.series) }),
                    { disabled: configLocked(), submitDisabled: configLocked() },
                )}
                <aside class="t-stack">
                    <section class="panel">
                        <div class="panel-header t-panel-header"><div><h2>Logo & cover</h2><p>Uploaded images replace the monogram</p></div></div>
                        <div class="panel-body" data-role="branding"></div>
                    </section>
                    ${configLocked() ? "" : `
                    <section class="panel">
                        <div class="panel-header t-panel-header"><div><h2>Series</h2><p>Group editions of a recurring competition</p></div></div>
                        <div class="panel-body"><button class="button button-secondary button-small" type="button" data-action="new-series">+ New series</button></div>
                    </section>`}
                </aside>
            </div>`;

        UI.mountBrandingPanel(elements.body.querySelector('[data-role="branding"]'), {
            tournamentId: state.id,
            name: tournament.name,
            assets: state.assets,
            disabled: tournament.status === "archived",
            onChange: (assets) => {
                state.assets = assets;
            },
        });
    }


    async function addSeriesToForm() {
        const created = await UI.promptNewSeries();
        if (!created) {
            return;
        }
        state.series = [...state.series, created].sort((a, b) => a.name.localeCompare(b.name));
        const select = elements.body.querySelector('select[name="series_id"]');
        if (select) {
            select.add(new Option(created.name, created.id, true, true));
        }
    }


    function venueOptions() {
        return state.venues
            .filter((venue) => venue.status === "active" || venue.id === state.tournament?.primary_venue_id)
            .map((venue) => [venue.id, `${venue.name} — ${venue.city}`]);
    }


    function renderParticipation() {
        elements.body.innerHTML = formPanel(
            "Participation & eligibility",
            "Entrant limits, registration windows and roster deadlines. Times use your browser's time zone.",
            UI.renderFields(UI.PARTICIPATION_FIELDS, state.tournament, { primary_venue_id: venueOptions() }),
            { disabled: configLocked(), submitDisabled: configLocked() },
        );
    }


    async function saveConfiguration(form, defs) {
        if (configLocked()) {
            return true;
        }
        if (!form.reportValidity()) {
            return false;
        }
        await API.tournament.configure(state.id, UI.readFields(form, defs));
        return true;
    }


    function renderRules() {
        const locked = rulesLocked();
        const version = state.rules
            ? `Current: version ${state.rules.version} · ${UI.escapeHtml(state.rules.format_code.toUpperCase())}`
            : "No rules saved yet";

        elements.body.innerHTML = `
            <form class="t-grid-sidebar" data-role="step-form" novalidate>
                <section class="panel">
                    <div class="panel-header t-panel-header">
                        <div>
                            <h2>Rules & format</h2>
                            <p>${version}. Saving creates a new immutable version; Ready and Live matches keep their snapshot.</p>
                        </div>
                    </div>
                    <div class="panel-body" data-role="rules-editor"></div>
                    ${footer({ submitLabel: locked ? "Rules locked" : "Save rules version & continue", submitDisabled: locked })}
                </section>
                <aside class="panel sticky-panel">
                    <div class="panel-header t-panel-header"><div><h2>Capability check</h2><p>Live validation against the scoring engine</p></div></div>
                    <div class="panel-body" data-role="capability">Checking…</div>
                </aside>
            </form>`;

        state.editor = UI.mountRulesEditor(
            elements.body.querySelector('[data-role="rules-editor"]'),
            {
                rules: state.rules?.rules || null,
                disabled: locked,
                capability: elements.body.querySelector('[data-role="capability"]'),
            },
        );
    }


    async function saveRules() {
        if (rulesLocked()) {
            return true;
        }
        const saved = await API.tournament.createRules(state.id, state.editor.getRules());
        const isNew = !state.rules || saved.version !== state.rules.version;
        showToast(isNew ? `Saved rules version ${saved.version}.` : "Rules unchanged — no new version needed.", isNew ? "success" : "info");
        return true;
    }


    async function renderReview() {
        elements.body.innerHTML = `<section class="panel"><div class="panel-body">Loading review…</div></section>`;

        const [readiness, transitions] = await Promise.all([
            API.tournament.readiness(state.id),
            API.tournament.transitions(state.id),
        ]);

        const t = state.tournament;
        const canOpen = transitions.allowed.includes("registration_open");
        const facts = [
            ["Status", UI.statusLabel(t.status)],
            ["Season", t.season || "—"],
            ["Dates", `${UI.formatDate(t.start_date)} – ${UI.formatDate(t.end_date)}`],
            ["Time zone", t.timezone],
            ["Category", t.category || "—"],
            ["Scope", t.geographic_scope || "—"],
            ["Teams", `${t.minimum_teams} – ${t.maximum_teams ?? "no limit"}`],
            ["Registration", t.registration_mode === "open" ? "Open" : "Invitational"],
            ["Rules", state.rules ? `Version ${state.rules.version} (${state.rules.format_code.toUpperCase()}, ${state.rules.competition_structure.replaceAll("_", " ")})` : "Not configured"],
        ];

        elements.body.innerHTML = `
            <div class="t-grid-sidebar">
                <section class="panel">
                    <div class="panel-header t-panel-header"><div><h2>Review</h2><p>Summary of the competition definition</p></div></div>
                    <div class="panel-body">
                        <dl class="facts-grid">${facts.map(([k, v]) => `<div><dt>${UI.escapeHtml(k)}</dt><dd>${UI.escapeHtml(v)}</dd></div>`).join("")}</dl>
                    </div>
                    <div class="wizard-footer">
                        <button class="button button-secondary" type="button" data-nav="back">Back</button>
                        <div class="action-row">
                            ${canOpen ? `<button class="button button-secondary" type="button" data-action="open-registration">Open registration</button>` : ""}
                            <a class="button button-primary" href="/competitions/${state.id}">Go to tournament</a>
                        </div>
                    </div>
                </section>
                <aside class="panel">
                    <div class="panel-header t-panel-header"><div><h2>Scheduling readiness</h2><p>${readiness.approved_teams} approved of ${readiness.registered_teams} registered teams</p></div></div>
                    <div class="panel-body t-stack">
                        ${readiness.errors.length
                            ? `<div class="notice notice-warning"><strong>Before scheduling</strong><ul>${readiness.errors.map((e) => `<li>${UI.escapeHtml(e)}</li>`).join("")}</ul></div>`
                            : `<div class="notice notice-success">Ready to be scheduled.</div>`}
                        ${readiness.warnings.length
                            ? `<div class="notice notice-info"><ul>${readiness.warnings.map((w) => `<li>${UI.escapeHtml(w)}</li>`).join("")}</ul></div>`
                            : ""}
                        <p class="field-hint" style="margin:0">Team and roster items are completed after registration opens, from the tournament workspace.</p>
                    </div>
                </aside>
            </div>`;
    }


    // =========================
    // FLOW
    // =========================

    async function loadTournament() {
        if (!state.id) {
            return;
        }
        const [tournament, rules, assets] = await Promise.all([
            API.tournament.get(state.id),
            API.tournament.currentRules(state.id),
            API.tournament.assets(state.id).catch(() => []),
        ]);
        state.tournament = tournament;
        state.rules = rules;
        state.assets = assets;
        elements.title.textContent = `Edit ${tournament.name}`;

        const locked = configLocked();
        elements.lock.classList.toggle("hidden", !locked);
        if (locked) {
            elements.lock.textContent =
                `This tournament is ${UI.statusLabel(tournament.status).toLowerCase()}; competition configuration is locked. ` +
                (rulesLocked() ? "Rules are locked too." : "Rule revisions are still possible and create a new version.");
        }
    }


    async function render() {
        renderSteps();
        setUrl();

        try {
            switch (STEPS[state.step].key) {
                case "basics": renderBasics(); break;
                case "identity": renderIdentity(); break;
                case "participation": renderParticipation(); break;
                case "rules": renderRules(); break;
                default: await renderReview();
            }
        } catch (error) {
            elements.body.innerHTML = `<div class="notice notice-danger">${UI.escapeHtml(UI.errorText(error))}</div>`;
        }
    }


    async function go(step) {
        state.step = Math.max(0, Math.min(STEPS.length - 1, step));
        await render();
        window.scrollTo({ top: 0, behavior: "smooth" });
    }


    elements.steps.addEventListener("click", (event) => {
        const button = event.target.closest("[data-step]");
        if (button && !button.disabled) {
            go(Number(button.dataset.step));
        }
    });


    elements.body.addEventListener("click", async (event) => {
        const nav = event.target.closest("[data-nav]");
        if (nav) {
            go(state.step + (nav.dataset.nav === "back" ? -1 : 1));
            return;
        }

        if (event.target.closest('[data-action="new-series"]')) {
            await addSeriesToForm();
            return;
        }

        const action = event.target.closest('[data-action="open-registration"]');
        if (action) {
            action.disabled = true;
            try {
                await API.tournament.transition(state.id, { target_status: "registration_open" });
                showToast("Registration is now open.");
                window.location.href = `/competitions/${state.id}/teams`;
            } catch (error) {
                action.disabled = false;
                showToast(UI.errorText(error), "error");
            }
        }
    });


    elements.body.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.target;
        const submit = form.querySelector('[type="submit"]');
        submit.disabled = true;
        showError("");

        try {
            const key = STEPS[state.step].key;
            let ok = true;

            if (key === "basics") {
                ok = await saveBasics(form);
            } else if (key === "identity") {
                ok = await saveConfiguration(form, UI.IDENTITY_FIELDS);
            } else if (key === "participation") {
                ok = await saveConfiguration(form, UI.PARTICIPATION_FIELDS);
            } else if (key === "rules") {
                ok = await saveRules();
            }

            if (ok) {
                await loadTournament();
                await go(state.step + 1);
                return;
            }
        } catch (error) {
            showError(UI.isForbidden(error)
                ? `${UI.errorText(error)} — set the organizer token (top right).`
                : UI.errorText(error));
        }

        submit.disabled = false;
    });


    async function init() {
        UI.bindOrganizerButton(document.getElementById("organizer-token"));

        try {
            const [venues, series] = await Promise.all([
                API.listAll("venues").catch(() => []),
                API.tournamentSeries.list().then((page) => page.items).catch(() => []),
                loadTournament(),
            ]);
            state.venues = venues;
            state.series = series;
        } catch (error) {
            elements.body.innerHTML = `<div class="notice notice-danger">${UI.escapeHtml(UI.errorText(error))}</div>`;
            return;
        }

        await go(state.id ? stepFromUrl() : 0);
    }


    init();

})();
