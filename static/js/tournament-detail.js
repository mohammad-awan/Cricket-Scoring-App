(() => {

    "use strict";

    const root = document.getElementById("tournament-detail");

    if (!root) {
        return;
    }

    const UI = window.TournamentUI;
    const esc = UI.escapeHtml;
    const TEAM_PAGE_SIZE = 25;

    const TRANSITION_LABELS = {
        registration_open: "Open registration",
        registration_closed: "Close registration",
        scheduled: "Mark as scheduled",
        live: "Start tournament",
        completed: "Complete tournament",
        suspended: "Suspend",
        cancelled: "Cancel tournament",
        archived: "Archive",
    };

    const ROLE_OPTIONS = [
        ["batter", "Batter"],
        ["bowler", "Bowler"],
        ["all_rounder", "All-rounder"],
        ["wicket_keeper", "Wicket-keeper"],
    ];

    const state = {
        id: root.dataset.tournamentId,
        section: root.dataset.section || "overview",
        tournament: null,
        transitions: null,
        rules: null,
        teams: new Map(),
        venues: new Map(),
        memberships: [],
        groups: [],
        assets: [],
        series: [],
        teamFilter: { search: "", status: "", page: 1 },
        editor: null,
    };

    const sectionRoot = document.getElementById("section-root");
    const hero = document.getElementById("tournament-hero");


    // =========================
    // HELPERS
    // =========================

    const configLocked = () => UI.CONFIG_LOCKED.has(state.tournament.status);
    const rulesLocked = () => UI.RULES_LOCKED.has(state.tournament.status);
    const isFinal = () => UI.FINAL.has(state.tournament.status);


    function panel(title, subtitle, body, { actions = "", className = "" } = {}) {
        return `
            <section class="panel ${className}">
                <div class="panel-header t-panel-header">
                    <div>
                        <h2>${esc(title)}</h2>
                        ${subtitle ? `<p>${subtitle}</p>` : ""}
                    </div>
                    ${actions ? `<div class="action-row">${actions}</div>` : ""}
                </div>
                <div class="panel-body">${body}</div>
            </section>`;
    }


    function notice(kind, html) {
        return `<div class="notice notice-${kind}">${html}</div>`;
    }


    function listNotice(kind, title, items) {
        return notice(kind, `<strong>${esc(title)}</strong><ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`);
    }


    function teamName(membership) {
        const team = state.teams.get(membership.team_id);
        return membership.display_name || team?.name || "Unknown team";
    }


    function reportError(error) {
        const message = UI.errorText(error);
        showToast(
            UI.isForbidden(error) ? `${message} — set the organizer token in the header.` : message,
            "error",
        );
    }


    async function run(button, action, successMessage) {
        if (button) {
            button.disabled = true;
        }
        try {
            const result = await action();
            if (successMessage) {
                showToast(successMessage);
            }
            return result;
        } catch (error) {
            reportError(error);
            return undefined;
        } finally {
            if (button?.isConnected) {
                button.disabled = false;
            }
        }
    }


    // Reusable confirm / reason dialog. Resolves to the reason ("" when no
    // reason field) or null when cancelled.
    const dialog = {
        modal: document.getElementById("action-modal"),
        form: document.getElementById("action-form"),
        title: document.getElementById("action-title"),
        message: document.getElementById("action-message"),
        reasonField: document.getElementById("action-reason-field"),
        reasonLabel: document.getElementById("action-reason-label"),
        reason: document.getElementById("action-reason"),
        choiceField: document.getElementById("action-choice-field"),
        choiceLabel: document.getElementById("action-choice-label"),
        choice: document.getElementById("action-choice"),
        confirm: document.getElementById("action-confirm"),
        resolve: null,
    };

    // Value of the optional dropdown from the last confirmed dialog.
    let lastChoice = "";


    function ask({ title, message = "", reason = false, reasonRequired = false, reasonLabel = "Reason", confirmLabel = "Confirm", danger = false, choices = null, choiceLabel = "Choose" }) {
        dialog.title.textContent = title;
        dialog.message.textContent = message;
        dialog.choiceField.classList.toggle("hidden", !choices);
        dialog.choiceLabel.textContent = choiceLabel;
        dialog.choice.innerHTML = (choices || [])
            .map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`)
            .join("");
        dialog.reasonField.classList.toggle("hidden", !reason);
        dialog.reasonLabel.textContent = reasonRequired ? `${reasonLabel} (required)` : reasonLabel;
        dialog.reason.value = "";
        dialog.reason.required = reasonRequired;
        dialog.confirm.textContent = confirmLabel;
        dialog.confirm.className = `button ${danger ? "button-danger" : "button-primary"}`;
        dialog.modal.classList.remove("hidden");
        document.body.classList.add("modal-open");
        (reason ? dialog.reason : dialog.confirm).focus();

        return new Promise((resolve) => {
            dialog.resolve = resolve;
        });
    }


    function closeDialog(value) {
        dialog.modal.classList.add("hidden");
        document.body.classList.remove("modal-open");
        dialog.resolve?.(value);
        dialog.resolve = null;
    }


    dialog.form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!dialog.form.reportValidity()) {
            return;
        }
        lastChoice = dialog.choice.value;
        closeDialog(dialog.reason.value.trim());
    });

    dialog.modal.addEventListener("click", (event) => {
        if (event.target === dialog.modal || event.target.closest('[data-dialog="cancel"]')) {
            closeDialog(null);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !dialog.modal.classList.contains("hidden")) {
            closeDialog(null);
        }
    });


    // =========================
    // CORE DATA
    // =========================

    async function loadCore() {
        const [tournament, transitions, rules, assets] = await Promise.all([
            API.tournament.get(state.id),
            API.tournament.transitions(state.id),
            API.tournament.currentRules(state.id),
            API.tournament.assets(state.id).catch(() => []),
        ]);
        state.tournament = tournament;
        state.transitions = transitions;
        state.rules = rules;
        state.assets = assets;
        document.title = `${tournament.name} | Cricket Intelligence Platform`;
        renderHero();
    }


    async function loadReferenceData() {
        const [teams, venues, series] = await Promise.all([
            API.listAll("teams").catch(() => []),
            API.listAll("venues", { include_archived: true }).catch(() => []),
            API.tournamentSeries.list().then((page) => page.items).catch(() => []),
        ]);
        state.teams = new Map(teams.map((team) => [team.id, team]));
        state.venues = new Map(venues.map((venue) => [venue.id, venue]));
        state.series = series;
    }


    async function loadMemberships() {
        const [memberships, groups] = await Promise.all([
            API.tournament.teams(state.id),
            API.tournament.groups(state.id),
        ]);
        state.memberships = memberships;
        state.groups = groups;
    }


    function renderHero() {
        const t = state.tournament;
        const meta = [
            t.season,
            t.organizer,
            t.start_date ? `${UI.formatDate(t.start_date)} – ${UI.formatDate(t.end_date)}` : null,
            t.location,
        ].filter(Boolean);

        const cover = UI.assetUrl(state.assets, "cover");
        hero.classList.toggle("has-cover", Boolean(cover));
        hero.style.setProperty("--hero-cover", cover ? `url("${encodeURI(cover)}")` : "none");

        hero.innerHTML = `
            ${UI.logoMark(t.name, false, UI.assetUrl(state.assets, "logo"))}
            <div class="tournament-hero-main">
                <p class="eyebrow">${esc(t.code || t.category || "Tournament")}</p>
                <h1>${esc(t.name)}</h1>
                <div class="tournament-hero-meta">
                    ${UI.statusBadge(t.status)}
                    ${UI.statusBadge(t.is_published ? "published" : "unpublished", t.is_published ? "Published" : "Not published")}
                    ${meta.map((item) => `<span>${esc(item)}</span>`).join("<span>·</span>")}
                </div>
            </div>
            <div class="tournament-hero-actions">
                <button class="button button-secondary button-small" id="organizer-token" type="button">Organizer token</button>
                ${t.status === "archived" ? "" : `<a class="button button-secondary button-small" href="/competitions/${t.id}/edit">Open wizard</a>`}
            </div>`;

        UI.bindOrganizerButton(document.getElementById("organizer-token"));
    }


    // =========================
    // OVERVIEW
    // =========================

    async function renderOverview() {
        const t = state.tournament;
        const [readiness, audit, deductions, editions] = await Promise.all([
            API.tournament.readiness(state.id),
            API.tournament.audit(state.id).catch((error) => error),
            API.tournament.deductions(state.id).catch(() => []),
            t.series_id ? API.tournamentSeries.editions(t.series_id).catch(() => []) : Promise.resolve([]),
            loadMemberships(),
        ]);
        const series = state.series.find((item) => item.id === t.series_id);

        const currentIndex = UI.LIFECYCLE_PATH.indexOf(t.status);
        const track = UI.LIFECYCLE_PATH.map((status, index) => {
            const cls = status === t.status ? "current" : currentIndex > index ? "passed" : "";
            return `<li class="${cls}">${esc(UI.statusLabel(status))}</li>`;
        }).join("");
        const offPath = currentIndex === -1
            ? notice("warning", `Current status: <strong>${esc(UI.statusLabel(t.status))}</strong>`)
            : "";

        const transitionButtons = state.transitions.allowed.map((target) => {
            const danger = target === "cancelled" || target === "suspended";
            const label = target === "registration_open" && t.status === "registration_closed"
                ? "Reopen registration"
                : TRANSITION_LABELS[target] || UI.statusLabel(target);
            return `<button class="button ${danger ? "button-secondary" : "button-primary"} button-small" type="button" data-transition="${target}">${esc(label)}</button>`;
        }).join("") || `<span class="muted">No further transitions.</span>`;

        const canPublish = !["cancelled", "archived"].includes(t.status);

        const facts = [
            ["Time zone", t.timezone],
            ["Category", t.category],
            ["Geographic scope", t.geographic_scope],
            ["Sponsor", t.sponsor],
            ["Trophy", t.trophy_name],
            ["Registration", `${t.registration_mode === "open" ? "Open" : "Invitational"}${t.entry_requires_approval ? ", approval required" : ""}`],
            ["Registration window", t.registration_opens_at || t.registration_closes_at
                ? `${UI.formatDateTime(t.registration_opens_at, t.timezone)} → ${UI.formatDateTime(t.registration_closes_at, t.timezone)}`
                : "Not set"],
            ["Team limits", `${t.minimum_teams} – ${t.maximum_teams ?? "no limit"} (+${t.reserve_team_limit} reserve)`],
            ["Roster lock", UI.formatDateTime(t.roster_lock_at, t.timezone)],
            ["Primary venue", state.venues.get(t.primary_venue_id)?.name || "—"],
            ["Series", series ? `${series.name}${t.edition_number ? ` — edition ${t.edition_number}` : ""}` : null],
            ["Website", t.website],
            ["Contact", [t.contact_email, t.contact_phone].filter(Boolean).join(" · ")],
        ];

        const rulesSummary = state.rules
            ? (() => {
                const r = state.rules.rules;
                return `
                    <dl class="facts-grid">
                        <div><dt>Version</dt><dd>v${state.rules.version}</dd></div>
                        <div><dt>Format</dt><dd>${esc(r.format_code.toUpperCase())}</dd></div>
                        <div><dt>Structure</dt><dd>${esc(r.structure.replaceAll("_", " "))}</dd></div>
                        <div><dt>Overs</dt><dd>${r.overs_per_innings} × ${r.balls_per_over}-ball</dd></div>
                        <div><dt>Players per side</dt><dd>${r.players_per_side}</dd></div>
                        <div><dt>Squad size</dt><dd>${r.minimum_roster_size} – ${r.maximum_roster_size}</dd></div>
                        <div><dt>Points (W/T/NR)</dt><dd>${r.points.win} / ${r.points.tie} / ${r.points.no_result}</dd></div>
                    </dl>`;
            })()
            : notice("warning", `No rules configured. <a href="/competitions/${state.id}/rules"><strong>Configure rules →</strong></a>`);

        const auditBody = audit instanceof Error
            ? notice("info", UI.isForbidden(audit) ? "The audit trail is visible to organizers only — set the organizer token." : esc(UI.errorText(audit)))
            : audit.length
                ? `<ul class="plain-list">${audit.map((event) => `
                    <li>
                        <span><strong>${esc(event.event_type.replaceAll("_", " "))}</strong>
                        <small>${esc(Object.entries(event.details || {}).filter(([, v]) => v !== null && typeof v !== "object").map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`).join(" · "))}</small></span>
                        <span class="audit-time">${esc(UI.formatDateTime(event.created_at))}</span>
                    </li>`).join("")}</ul>`
                : `<p class="muted" style="margin:0">No audit events yet.</p>`;

        sectionRoot.innerHTML = `
            <div class="t-grid-sidebar">
                <div class="t-stack">
                    ${panel("Lifecycle", "Every transition is validated and recorded in the audit trail.", `
                        <ol class="lifecycle-track">${track}</ol>
                        ${offPath}
                        <div class="action-row">${transitionButtons}</div>
                    `, {
                        actions: canPublish
                            ? `<button class="button button-secondary button-small" type="button" data-action="toggle-publish">${t.is_published ? "Unpublish" : "Publish"}</button>`
                            : "",
                    })}
                    ${panel("Competition rules", "", rulesSummary, {
                        actions: `<a class="button button-secondary button-small" href="/competitions/${state.id}/rules">Manage rules</a>`,
                    })}
                    ${panel("Details", "", `
                        ${t.description ? `<p style="margin:0 0 16px;white-space:pre-line">${esc(t.description)}</p>` : ""}
                        <dl class="facts-grid">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v || "—")}</dd></div>`).join("")}</dl>
                    `, { actions: `<a class="button button-secondary button-small" href="/competitions/${state.id}/identity">Edit</a>` })}
                </div>
                <div class="t-stack">
                    ${panel("Readiness", `${readiness.approved_teams} approved · ${readiness.registered_teams} registered`, `
                        <div class="t-stack">
                            ${readiness.errors.length ? listNotice("danger", "Blocking scheduling", readiness.errors) : notice("success", "Ready to be scheduled.")}
                            ${readiness.warnings.length ? listNotice("warning", "Warnings", readiness.warnings) : ""}
                        </div>
                    `)}
                    ${deductionsPanel(deductions)}
                    ${editions.length > 1 ? panel("Other editions", esc(series?.name || ""), `
                        <ul class="plain-list">${editions.filter((item) => item.id !== t.id).map((item) => `
                            <li><span><a href="/competitions/${item.id}"><strong>${esc(item.name)}</strong></a>
                            <small>${esc([item.edition_number ? `Edition ${item.edition_number}` : null, item.season].filter(Boolean).join(" · "))}</small></span>
                            ${UI.statusBadge(item.status)}</li>`).join("")}</ul>
                    `) : ""}
                    ${panel("Audit trail", "Latest 50 events", auditBody)}
                </div>
            </div>`;
    }


    function deductionsPanel(deductions) {
        const t = state.tournament;
        const approved = state.memberships.filter((m) => m.registration_status === "approved");
        const canDeduct = !["draft", "cancelled", "archived"].includes(t.status) && approved.length > 0;
        const active = deductions.filter((item) => !item.revoked_at);
        const membershipName = (id) => {
            const membership = state.memberships.find((m) => m.id === id);
            return membership ? teamName(membership) : "Unknown team";
        };

        const list = deductions.length
            ? `<ul class="plain-list">${deductions.map((item) => `
                <li class="${item.revoked_at ? "revoked" : ""}">
                    <span>
                        <strong>−${item.points} · ${esc(membershipName(item.tournament_team_id))}</strong>
                        <small>${esc(item.reason)}</small>
                        ${item.revoked_at ? `<small>Revoked: ${esc(item.revoked_reason)}</small>` : ""}
                    </span>
                    ${item.revoked_at
                        ? UI.statusBadge("withdrawn", "Revoked")
                        : t.status === "archived" ? "" : `<button class="table-action table-action-danger" type="button" data-revoke-deduction="${item.id}">Revoke</button>`}
                </li>`).join("")}</ul>`
            : `<p class="muted" style="margin:0">No deductions.</p>`;

        const form = canDeduct ? `
            <form class="t-stack" data-form="deduction" style="margin-top:14px" novalidate>
                <div class="form-grid">
                    <label class="form-field form-field-wide"><span>Team <em>*</em></span>
                        <select name="tournament_team_id" required>
                            <option value="">Select a team…</option>
                            ${approved.map((m) => `<option value="${m.id}">${esc(teamName(m))}</option>`).join("")}
                        </select>
                    </label>
                    <label class="form-field"><span>Points <em>*</em></span><input name="points" type="number" min="1" max="1000" required></label>
                    <label class="form-field form-field-wide"><span>Reason <em>*</em></span><textarea name="reason" rows="2" minlength="3" maxlength="1000" required placeholder="e.g. Slow over rate v Team B"></textarea></label>
                </div>
                <div><button class="button button-secondary button-small" type="submit">Deduct points</button></div>
            </form>` : "";

        return panel(
            "Point deductions",
            `${active.length} active · revoked entries stay on record`,
            list + form,
        );
    }


    async function handleTransition(button, target) {
        const required = state.transitions.reason_required.includes(target);
        const label = TRANSITION_LABELS[target] || UI.statusLabel(target);
        const messages = {
            scheduled: "Configuration and rosters lock once the tournament is scheduled. Rule changes after this create a new version.",
            live: "Rules lock once the tournament is live.",
            cancelled: "Cancelled tournaments can only be archived afterwards.",
            archived: "Archived tournaments are read-only.",
        };

        const reason = await ask({
            title: `${label}?`,
            message: messages[target] || `Move from ${UI.statusLabel(state.tournament.status)} to ${UI.statusLabel(target)}.`,
            reason: true,
            reasonRequired: required,
            confirmLabel: label,
            danger: target === "cancelled" || target === "archived",
        });
        if (reason === null) {
            return;
        }

        const result = await run(
            button,
            () => API.tournament.transition(state.id, { target_status: target, reason: reason || null }),
            `Tournament is now ${UI.statusLabel(target).toLowerCase()}.`,
        );
        if (result) {
            await refresh();
        }
    }


    // =========================
    // IDENTITY & BRANDING
    // =========================

    function renderIdentity() {
        const t = state.tournament;
        const locked = configLocked();

        sectionRoot.innerHTML = `
            <div class="t-grid-sidebar">
                <div class="t-stack">
                    <form class="panel" data-form="basics" novalidate>
                        <div class="panel-header t-panel-header"><div><h2>Basics</h2><p>Name, edition, dates and description.</p></div></div>
                        <div class="panel-body"><div class="form-grid">${UI.renderFields(UI.BASIC_FIELDS, t)}</div></div>
                        <div class="wizard-footer"><span></span><button class="button button-primary" type="submit">Save basics</button></div>
                    </form>
                    <form class="panel" data-form="identity" novalidate>
                        <div class="panel-header t-panel-header"><div><h2>Identity, branding & contacts</h2><p>${locked ? "Locked once the tournament is scheduled." : "Code, category, scope, sponsorship and contacts."}</p></div></div>
                        <div class="panel-body">
                            <fieldset style="border:0;margin:0;padding:0" ${locked ? "disabled" : ""}>
                                <div class="form-grid">${UI.renderFields(UI.IDENTITY_FIELDS, t, { series_id: UI.seriesOptions(state.series) })}</div>
                            </fieldset>
                        </div>
                        <div class="wizard-footer"><span></span><button class="button button-primary" type="submit" ${locked ? "disabled" : ""}>Save identity</button></div>
                    </form>
                </div>
                <aside class="t-stack">
                    ${panel("Logo & cover", "Uploaded images replace the monogram", `<div data-role="branding"></div>`)}
                    ${locked ? "" : panel("Series", "Group editions of a recurring competition", `<button class="button button-secondary button-small" type="button" data-action="new-series">+ New series</button>`)}
                    ${panel("Display safety", "", `<p class="muted" style="margin:0">Descriptions and terms are stripped of HTML on the server and always displayed as plain text. Websites must be http(s) links.</p>`)}
                </aside>
            </div>`;

        UI.mountBrandingPanel(sectionRoot.querySelector('[data-role="branding"]'), {
            tournamentId: state.id,
            name: t.name,
            assets: state.assets,
            disabled: t.status === "archived",
            onChange: (assets) => {
                state.assets = assets;
                renderHero();
            },
        });
    }


    async function addSeries() {
        const created = await UI.promptNewSeries();
        if (!created) {
            return;
        }
        state.series = [...state.series, created].sort((a, b) => a.name.localeCompare(b.name));
        const select = sectionRoot.querySelector('select[name="series_id"]');
        if (select) {
            select.add(new Option(created.name, created.id, true, true));
        }
    }


    async function submitIdentityForm(form) {
        const submit = form.querySelector('[type="submit"]');
        if (!form.reportValidity()) {
            return;
        }

        if (form.dataset.form === "basics") {
            const payload = UI.readFields(form, UI.BASIC_FIELDS);
            if (!payload.slug) {
                delete payload.slug;
            }
            if (await run(submit, () => API.tournament.updateBasics(state.id, payload), "Basics saved.")) {
                await refresh();
            }
            return;
        }

        if (await run(submit, () => API.tournament.configure(state.id, UI.readFields(form, UI.IDENTITY_FIELDS)), "Identity saved.")) {
            await refresh();
        }
    }


    // =========================
    // RULES & FORMAT
    // =========================

    async function renderRules() {
        const locked = rulesLocked();
        const versions = await API.tournament.rules(state.id);

        const versionRows = versions.length
            ? `<div class="table-wrap"><table class="data-table" style="min-width:600px">
                <thead><tr><th>Version</th><th>Format</th><th>Structure</th><th>Checksum</th><th>Created</th><th></th></tr></thead>
                <tbody>${versions.map((item) => `
                    <tr>
                        <td><strong>v${item.version}</strong>${item.version === state.rules?.version ? ` ${UI.statusBadge("approved", "Current")}` : ""}</td>
                        <td>${esc(item.format_code.toUpperCase())}</td>
                        <td>${esc(item.competition_structure.replaceAll("_", " "))}</td>
                        <td class="mono">${esc(item.checksum.slice(0, 12))}…</td>
                        <td>${esc(UI.formatDateTime(item.created_at))}</td>
                        <td>${locked ? "" : `<button class="table-action" type="button" data-load-version="${item.version}">Load into editor</button>`}</td>
                    </tr>`).join("")}
                </tbody></table></div>`
            : `<p class="muted" style="margin:0">No versions yet. Save the editor to create version 1.</p>`;

        sectionRoot.innerHTML = `
            <div class="t-stack">
                ${locked ? notice("warning", "Rules are locked because the tournament is live or closed. Existing versions remain viewable.") : ""}
                <div class="t-grid-sidebar">
                    ${panel("Rules & format editor", state.rules
                        ? `Editing from version ${state.rules.version}. Saving creates a new immutable version; Ready and Live matches keep the snapshot they locked.`
                        : "Pick a format preset, then adjust. Presets only initialise editable values.",
                        `<div data-role="rules-editor"></div>`,
                        { actions: locked ? "" : `<button class="button button-primary button-small" type="button" data-action="save-rules">Save as new version</button>` })}
                    <aside class="panel sticky-panel">
                        <div class="panel-header t-panel-header"><div><h2>Capability check</h2><p>Live validation against the scoring engine</p></div></div>
                        <div class="panel-body" data-role="capability">Checking…</div>
                    </aside>
                </div>
                ${panel("Version history", "Every saved version is immutable; the database rejects in-place edits.", versionRows)}
                ${state.rules && !isFinal() ? panel("Apply to unstarted fixtures", "New versions never change Ready or Live matches. Choose explicitly whether draft fixtures adopt the current format.", `
                    <div class="t-stack">
                        <div class="action-row">
                            <button class="button button-secondary button-small" type="button" data-action="propagate-preview">Preview affected fixtures</button>
                            <button class="button button-primary button-small" type="button" data-action="propagate-apply">Apply version ${state.rules.version} to draft fixtures</button>
                        </div>
                        <div data-role="propagation-result"></div>
                    </div>
                `) : ""}
            </div>`;

        state.editor = UI.mountRulesEditor(sectionRoot.querySelector('[data-role="rules-editor"]'), {
            rules: state.rules?.rules || null,
            disabled: locked,
            capability: sectionRoot.querySelector('[data-role="capability"]'),
        });
        state.versions = versions;
    }


    async function saveRules(button) {
        const before = state.rules?.version;
        const saved = await run(button, () => API.tournament.createRules(state.id, state.editor.getRules()));
        if (!saved) {
            return;
        }
        showToast(saved.version === before ? "Rules unchanged — no new version needed." : `Saved rules version ${saved.version}.`, saved.version === before ? "info" : "success");
        await refresh();
    }


    async function propagate(button, apply) {
        if (apply) {
            const confirmed = await ask({
                title: `Apply version ${state.rules.version}?`,
                message: "Draft fixtures without a locked rule snapshot will adopt this version's overs, balls per over, innings and players per side. Fixtures with selected playing teams keep their side size.",
                confirmLabel: "Apply to drafts",
            });
            if (confirmed === null) {
                return;
            }
        }

        const result = await run(button, () => API.tournament.propagate(state.id, {
            apply_to_unstarted: apply,
            expected_previous_version: state.rules.version,
        }));
        if (!result) {
            return;
        }

        const box = sectionRoot.querySelector('[data-role="propagation-result"]');
        const updated = result.updated_match_ids.length;
        const skipped = result.skipped_match_ids.length;
        box.innerHTML = updated || skipped
            ? notice(apply ? "success" : "info", `
                <strong>${apply ? "Applied" : "Preview"}:</strong>
                ${updated} fixture${updated === 1 ? "" : "s"} ${apply ? "updated" : "would change"}${skipped ? `, ${skipped} skipped (locked or playing teams already selected)` : ""}.
                ${result.updated_match_ids.map((id) => `<br><a class="mono" href="/match-setup/${id}">${esc(id)}</a>`).join("")}`)
            : notice("success", "All draft fixtures already match the current version.");
    }


    // =========================
    // TEAM REGISTRATION
    // =========================

    function filteredMemberships() {
        const term = state.teamFilter.search.toLowerCase();
        return state.memberships.filter((item) => {
            if (state.teamFilter.status === "reserve") {
                if (!item.is_reserve) {
                    return false;
                }
            } else if (state.teamFilter.status && item.registration_status !== state.teamFilter.status) {
                return false;
            }
            if (!term) {
                return true;
            }
            const team = state.teams.get(item.team_id);
            return [item.display_name, team?.name, team?.short_name, item.manager_name]
                .some((value) => String(value || "").toLowerCase().includes(term));
        });
    }


    function replacedName(membershipId) {
        const membership = state.memberships.find((m) => m.id === membershipId);
        return membership ? teamName(membership) : "a withdrawn team";
    }


    async function promoteReserve(button, membershipId) {
        const t = state.tournament;
        const replacedIds = new Set(state.memberships.map((m) => m.replaces_membership_id).filter(Boolean));
        const withdrawn = state.memberships.filter((m) => m.registration_status === "withdrawn" && !replacedIds.has(m.id));
        const cutoff = t.replacement_cutoff_at
            ? ` Replacements close ${UI.formatDateTime(t.replacement_cutoff_at, t.timezone)}.`
            : "";

        const reason = await ask({
            title: "Promote reserve team?",
            message: `The team moves into the main draw if there is space.${cutoff}`,
            choices: withdrawn.length
                ? [["", "Not replacing a specific team"], ...withdrawn.map((m) => [m.id, `Replaces ${teamName(m)}`])]
                : null,
            choiceLabel: "Replacement for",
            reason: true,
            confirmLabel: "Promote",
        });
        if (reason === null) {
            return;
        }

        const payload = {
            replaces_membership_id: withdrawn.length && lastChoice ? lastChoice : null,
            reason: reason || null,
        };
        if (await run(button, () => API.tournament.promote(state.id, membershipId, payload), "Reserve team promoted.")) {
            await renderTeams();
        }
    }


    function teamTableHtml() {
        const rows = filteredMemberships();
        const pages = Math.max(1, Math.ceil(rows.length / TEAM_PAGE_SIZE));
        state.teamFilter.page = Math.min(state.teamFilter.page, pages);
        const page = rows.slice((state.teamFilter.page - 1) * TEAM_PAGE_SIZE, state.teamFilter.page * TEAM_PAGE_SIZE);
        const status = state.tournament.status;
        const canDecide = status === "registration_open" || status === "registration_closed";
        const groupsEditable = !configLocked() && state.groups.length > 0;

        const body = page.map((item) => {
            const team = state.teams.get(item.team_id);
            const active = item.registration_status === "pending" || item.registration_status === "approved";
            const group = state.groups.find((g) => g.id === item.group_id);

            const groupCell = groupsEditable && active
                ? `<select class="inline-select" data-group-for="${item.id}">
                        <option value="">No group</option>
                        ${state.groups.map((g) => `<option value="${g.id}" ${g.id === item.group_id ? "selected" : ""}>${esc(g.name)}</option>`).join("")}
                   </select>`
                : esc(group?.name || "—");

            const actions = [
                canDecide && item.registration_status === "pending"
                    ? `<button class="table-action" type="button" data-decide="${item.id}" data-approve="true">Approve</button>
                       <button class="table-action table-action-danger" type="button" data-decide="${item.id}" data-approve="false">Reject</button>`
                    : "",
                active && item.is_reserve && !configLocked()
                    ? `<button class="table-action" type="button" data-promote="${item.id}">Promote</button>`
                    : "",
                active ? `<a class="table-action" href="/competitions/${state.id}/squads?team=${item.id}">Squad</a>` : "",
                active && !configLocked()
                    ? `<button class="table-action table-action-danger" type="button" data-withdraw="${item.id}">Withdraw</button>`
                    : "",
            ].join("");

            return `
                <tr>
                    <td>
                        <span class="name-cell">
                            <span><strong>${esc(teamName(item))}</strong>
                            <small>${esc(team && item.display_name && item.display_name !== team.name ? team.name : team?.short_name || "")}${item.manager_name ? ` · Manager: ${esc(item.manager_name)}` : ""}</small></span>
                        </span>
                    </td>
                    <td>${item.seed ?? "—"}</td>
                    <td>${UI.statusBadge(item.registration_status)} ${item.is_reserve ? UI.statusBadge("reserve", "Reserve") : ""}${item.replaces_membership_id ? `<br><small class="muted">Replaces ${esc(replacedName(item.replaces_membership_id))}</small>` : ""}</td>
                    <td>${groupCell}</td>
                    <td>${item.captain_player_id ? "✓" : "—"}</td>
                    <td><div class="row-actions">${actions || "—"}</div></td>
                </tr>`;
        }).join("");

        return `
            <div class="toolbar">
                <label class="search-box"><span class="sr-only">Search teams</span>
                    <input type="search" data-role="team-search" placeholder="Search teams…" value="${esc(state.teamFilter.search)}" autocomplete="off">
                </label>
                <select class="status-filter" data-role="team-status" aria-label="Registration status">
                    ${[["", "All registrations"], ["pending", "Pending"], ["approved", "Approved"], ["reserve", "Reserve"], ["rejected", "Rejected"], ["withdrawn", "Withdrawn"]]
                        .map(([v, l]) => `<option value="${v}" ${v === state.teamFilter.status ? "selected" : ""}>${l}</option>`).join("")}
                </select>
            </div>
            <div class="table-wrap">
                <table class="data-table">
                    <thead><tr><th>Team</th><th>Seed</th><th>Status</th><th>Group</th><th>Captain</th><th class="actions-column">Actions</th></tr></thead>
                    <tbody>${body}</tbody>
                </table>
                ${rows.length ? "" : `<div class="table-state">No registrations match.</div>`}
            </div>
            <div class="pagination-bar">
                <span>${rows.length} registration${rows.length === 1 ? "" : "s"}</span>
                <div class="pagination-actions">
                    <button class="button button-secondary button-small" type="button" data-team-page="-1" ${state.teamFilter.page <= 1 ? "disabled" : ""}>Previous</button>
                    <span>Page ${state.teamFilter.page} of ${pages}</span>
                    <button class="button button-secondary button-small" type="button" data-team-page="1" ${state.teamFilter.page >= pages ? "disabled" : ""}>Next</button>
                </div>
            </div>`;
    }


    async function renderTeams() {
        await loadMemberships();

        const t = state.tournament;
        const active = state.memberships.filter((m) => m.registration_status === "pending" || m.registration_status === "approved");
        const approvedMain = active.filter((m) => m.registration_status === "approved" && !m.is_reserve);
        const activeTeamIds = new Set(active.map((m) => m.team_id));
        const availableTeams = [...state.teams.values()]
            .filter((team) => team.status === "active" && !activeTeamIds.has(team.id))
            .sort((a, b) => a.name.localeCompare(b.name));

        const canRegister = t.status === "registration_open" && t.registration_mode === "open";
        const canInvite = ["draft", "registration_open", "registration_closed"].includes(t.status);
        const registrationNote = t.status !== "registration_open"
            ? `Public registration is ${t.status === "draft" ? "not open yet" : "closed"}.${canInvite ? " Organizers can still invite teams." : ""}`
            : t.registration_mode === "invitational"
                ? "This tournament is invitational: only organizer invitations are accepted."
                : `Registration is open${t.registration_closes_at ? ` until ${UI.formatDateTime(t.registration_closes_at, t.timezone)}` : ""}.`;

        const groupCounts = new Map();
        active.forEach((m) => {
            if (m.group_id) {
                groupCounts.set(m.group_id, (groupCounts.get(m.group_id) || 0) + 1);
            }
        });
        const teamsPerGroup = state.rules?.rules.teams_per_group;

        sectionRoot.innerHTML = `
            <div class="t-stack">
                <div class="chip-row">
                    <span class="chip"><strong>${active.length}</strong> registered</span>
                    <span class="chip"><strong>${approvedMain.length}</strong> approved</span>
                    <span class="chip"><strong>${active.filter((m) => m.registration_status === "pending").length}</strong> pending</span>
                    <span class="chip"><strong>${active.filter((m) => m.is_reserve).length}</strong> / ${t.reserve_team_limit} reserve</span>
                    <span class="chip">limits <strong>${t.minimum_teams}–${t.maximum_teams ?? "∞"}</strong></span>
                </div>

                <div class="t-grid-sidebar">
                    ${panel("Registered teams", "", teamTableHtml(), { className: "master-panel" })}
                    <div class="t-stack">
                        <form class="panel" data-form="register" novalidate>
                            <div class="panel-header t-panel-header"><div><h2>Add a team</h2><p>${esc(registrationNote)}</p></div></div>
                            <div class="panel-body">
                                <div class="form-grid">
                                    <label class="form-field form-field-wide"><span>Team <em>*</em></span>
                                        <select name="team_id" required>
                                            <option value="">Select a team…</option>
                                            ${availableTeams.map((team) => `<option value="${team.id}">${esc(team.name)}</option>`).join("")}
                                        </select>
                                    </label>
                                    <label class="form-field form-field-wide"><span>Display alias</span>
                                        <input name="display_name" maxlength="160" placeholder="Defaults to the team name">
                                    </label>
                                    <label class="form-field"><span>Seed</span><input name="seed" type="number" min="1"></label>
                                    <label class="form-field"><span>Manager</span><input name="manager_name" maxlength="160"></label>
                                    <label class="checkbox-field form-field-wide"><input type="checkbox" name="is_reserve"> Enter as reserve team</label>
                                </div>
                            </div>
                            <div class="wizard-footer">
                                <button class="button button-secondary" type="submit" data-mode="register" ${canRegister ? "" : "disabled"}>Submit registration</button>
                                <button class="button button-primary" type="submit" data-mode="invite" ${canInvite ? "" : "disabled"}>Invite & approve</button>
                            </div>
                        </form>

                        ${panel("Groups", teamsPerGroup ? `Up to ${teamsPerGroup} teams per group` : "Optional pools for group-stage formats", `
                            ${state.groups.length
                                ? `<ul class="plain-list">${state.groups.map((g) => `
                                    <li><span><strong>${esc(g.name)}</strong><small>${groupCounts.get(g.id) || 0} team${groupCounts.get(g.id) === 1 ? "" : "s"}</small></span>
                                    ${configLocked() ? "" : `<button class="table-action table-action-danger" type="button" data-delete-group="${g.id}">Delete</button>`}</li>`).join("")}</ul>`
                                : `<p class="muted" style="margin:0 0 12px">No groups yet.</p>`}
                            ${configLocked() ? "" : `
                                <form class="powerplay-row" data-form="group" style="margin-top:12px" novalidate>
                                    <label class="form-field"><span>New group</span><input name="name" maxlength="100" placeholder="Group A" required></label>
                                    <label class="form-field" style="max-width:90px"><span>Order</span><input name="sort_order" type="number" min="0" value="${state.groups.length}"></label>
                                    <button class="button button-secondary button-small" type="submit">Add</button>
                                </form>`}
                        `)}
                    </div>
                </div>
            </div>`;
    }


    function refreshTeamTable() {
        const container = sectionRoot.querySelector(".master-panel .panel-body");
        if (container) {
            const focusSearch = document.activeElement?.dataset.role === "team-search";
            container.innerHTML = teamTableHtml();
            if (focusSearch) {
                const input = container.querySelector('[data-role="team-search"]');
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            }
        }
    }


    async function submitRegistration(form, mode, button) {
        if (!form.reportValidity()) {
            return;
        }
        const payload = {
            team_id: form.elements.team_id.value,
            display_name: form.elements.display_name.value.trim() || null,
            seed: form.elements.seed.value ? Number(form.elements.seed.value) : null,
            manager_name: form.elements.manager_name.value.trim() || null,
            is_reserve: form.elements.is_reserve.checked,
        };
        const action = mode === "invite" ? API.tournament.invite : API.tournament.register;
        const result = await run(button, () => action(state.id, payload));
        if (result) {
            showToast(result.is_reserve
                ? "Team added to the reserve list."
                : `Team ${result.registration_status === "approved" ? "approved" : "registered — awaiting approval"}.`);
            await renderTeams();
        }
    }


    // =========================
    // SQUADS & ELIGIBILITY
    // =========================

    async function renderSquads() {
        await loadMemberships();

        const active = state.memberships.filter((m) => m.registration_status === "pending" || m.registration_status === "approved");
        if (!active.length) {
            sectionRoot.innerHTML = notice("info", `No active registrations yet. <a href="/competitions/${state.id}/teams"><strong>Register teams →</strong></a>`);
            return;
        }

        const requested = new URLSearchParams(window.location.search).get("team");
        const membership = active.find((m) => m.id === requested)
            || active.find((m) => m.registration_status === "approved")
            || active[0];

        const [roster, squad, candidates] = await Promise.all([
            API.tournament.roster(state.id, membership.id),
            API.teamSquad(membership.team_id).catch(() => []),
            API.tournament.rosterCandidates(state.id, membership.id).catch(() => []),
        ]);

        const names = new Map(squad.map((item) => [item.player.id, item.player.full_name]));
        const missing = roster.filter((entry) => !names.has(entry.player_id));
        await Promise.all(missing.map(async (entry) => {
            try {
                const player = await API.get("players", entry.player_id);
                names.set(entry.player_id, player.full_name);
            } catch {
                names.set(entry.player_id, "Unknown player");
            }
        }));

        const t = state.tournament;
        const r = state.rules?.rules;
        const eligibleCount = candidates.filter((item) => item.eligible).length;
        const ineligible = candidates.filter((item) => !item.eligible);
        const lockPassed = t.roster_lock_at && new Date(t.roster_lock_at) <= new Date();
        const editable = !configLocked() && !lockPassed;
        const availableCount = roster.filter((entry) => entry.is_available).length;
        const full = r && roster.length >= r.maximum_roster_size;

        const rows = roster.map((entry) => {
            const isCaptain = membership.captain_player_id === entry.player_id;
            return `
                <tr>
                    <td><strong>${esc(names.get(entry.player_id))}</strong></td>
                    <td>${esc(ROLE_OPTIONS.find(([v]) => v === entry.role)?.[1] || entry.role)}</td>
                    <td>${entry.is_available ? UI.statusBadge("approved", "Available") : UI.statusBadge("withdrawn", "Unavailable")}</td>
                    <td>${isCaptain ? UI.statusBadge("approved", "Captain") : (entry.is_available && !isFinal() ? `<button class="table-action" type="button" data-captain="${entry.player_id}">Make captain</button>` : "—")}</td>
                    <td>${entry.locked_at ? UI.statusBadge("locked", "Locked") : "Open"}</td>
                    <td><div class="row-actions">
                        ${isFinal() ? "" : `<button class="table-action" type="button" data-availability="${entry.player_id}" data-available="${entry.is_available}">${entry.is_available ? "Mark unavailable" : "Mark available"}</button>`}
                        ${editable && !entry.locked_at ? `<button class="table-action table-action-danger" type="button" data-remove-player="${entry.player_id}">Remove</button>` : ""}
                    </div></td>
                </tr>`;
        }).join("");

        const policy = r?.eligibility || {};
        const eligibility = {
            ageActive: policy.minimum_age != null || policy.maximum_age != null,
            ageText: policy.minimum_age != null || policy.maximum_age != null
                ? ` (${policy.minimum_age ?? "any"}–${policy.maximum_age ?? "any"})`
                : "",
            sexActive: Boolean(policy.sex && policy.sex !== "open"),
            sexText: policy.sex && policy.sex !== "open" ? ` (${policy.sex === "female" ? "women's" : "men's"})` : "",
            overseasActive: r?.overseas_player_limit != null,
            overseasText: r?.overseas_player_limit != null
                ? ` (max ${r.overseas_player_limit}; home: ${policy.home_nationality})`
                : "",
        };

        const sizeWarnings = [];
        if (r) {
            if (roster.length < r.minimum_roster_size) {
                sizeWarnings.push(`Squad needs at least ${r.minimum_roster_size} players (${roster.length} now).`);
            }
            if (availableCount < r.players_per_side) {
                sizeWarnings.push(`Only ${availableCount} available players; a playing XI needs ${r.players_per_side}.`);
            }
            if (!membership.captain_player_id) {
                sizeWarnings.push("No tournament captain named.");
            }
        }

        sectionRoot.innerHTML = `
            <div class="t-stack">
                <div class="toolbar" style="padding:0;border:0">
                    <label class="form-field" style="min-width:280px">
                        <span>Team</span>
                        <select data-role="squad-team">
                            ${active.map((m) => `<option value="${m.id}" ${m.id === membership.id ? "selected" : ""}>${esc(teamName(m))}${m.registration_status === "pending" ? " (pending)" : ""}</option>`).join("")}
                        </select>
                    </label>
                    ${isFinal() ? "" : `<button class="button button-secondary" type="button" data-action="lock-rosters" style="align-self:end">Lock all rosters now</button>`}
                </div>

                <div class="chip-row">
                    <span class="chip"><strong>${roster.length}</strong> / ${r ? `${r.minimum_roster_size}–${r.maximum_roster_size}` : "?"} squad</span>
                    <span class="chip"><strong>${availableCount}</strong> available</span>
                    <span class="chip">XI of <strong>${r?.players_per_side ?? "?"}</strong></span>
                    <span class="chip">roster lock <strong>${esc(t.roster_lock_at ? UI.formatDateTime(t.roster_lock_at, t.timezone) : "not set")}</strong></span>
                    <span class="chip">replacement cutoff <strong>${esc(t.replacement_cutoff_at ? UI.formatDateTime(t.replacement_cutoff_at, t.timezone) : "not set")}</strong></span>
                </div>

                ${!r ? notice("warning", `Configure <a href="/competitions/${state.id}/rules"><strong>tournament rules</strong></a> before building squads.`) : ""}
                ${sizeWarnings.length ? listNotice("warning", "Squad not yet match-ready", sizeWarnings) : ""}
                ${!editable && !isFinal() ? notice("info", "Rosters are locked. Availability can still change for injuries or absences.") : ""}

                <div class="t-grid-sidebar">
                    ${panel(`${teamName(membership)} — tournament squad`, "Separate from the club's global squad; changes here never alter team membership.", `
                        <div class="table-wrap"><table class="data-table" style="min-width:640px">
                            <thead><tr><th>Player</th><th>Role</th><th>Availability</th><th>Captain</th><th>Lock</th><th>Actions</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                        ${roster.length ? "" : `<div class="table-state">No players in this tournament squad yet.</div>`}</div>
                    `)}
                    <div class="t-stack">
                        ${editable && r ? `
                        <form class="panel" data-form="roster-add" data-membership="${membership.id}" novalidate>
                            <div class="panel-header t-panel-header"><div><h2>Add player</h2><p>From ${esc(teamName(membership))}'s active squad</p></div></div>
                            <div class="panel-body"><div class="form-grid">
                                <label class="form-field form-field-wide"><span>Player <em>*</em></span>
                                    <select name="player_id" required ${full ? "disabled" : ""}>
                                        <option value="">${full ? "Squad is full" : eligibleCount ? "Select a player…" : "No eligible squad players left"}</option>
                                        ${candidates.map((item) => `<option value="${item.player_id}" data-role="${item.role}" ${item.eligible ? "" : "disabled"} title="${esc(item.reasons.join("; "))}">${esc(item.full_name)}${item.squad_number ? ` #${item.squad_number}` : ""}${item.eligible ? "" : ` — not eligible: ${esc(item.reasons.join("; "))}`}</option>`).join("")}
                                    </select>
                                </label>
                                ${ineligible.length ? `
                                <div class="form-field-wide">
                                    <p class="form-section-title" style="margin:4px 0 6px">Not eligible (${ineligible.length})</p>
                                    <ul class="plain-list ineligible-list">${ineligible.map((item) => `
                                        <li><span><strong>${esc(item.full_name)}</strong>${item.reasons.map((reason) => `<small>${esc(reason)}</small>`).join("")}</span></li>`).join("")}
                                    </ul>
                                </div>` : ""}
                                <label class="form-field form-field-wide"><span>Tournament role</span>
                                    <select name="role">${ROLE_OPTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
                                </label>
                            </div></div>
                            <div class="wizard-footer"><span></span><button class="button button-primary" type="submit" ${full ? "disabled" : ""}>Add to squad</button></div>
                        </form>` : ""}
                        ${panel("Eligibility checks", "", `
                            <ul class="plain-list">
                                <li><span>Active member of the team's global squad</span>${UI.statusBadge("approved", "Enforced")}</li>
                                <li><span>One team per player in this tournament</span>${UI.statusBadge("approved", "Enforced")}</li>
                                <li><span>Squad size limits from rules</span>${UI.statusBadge("approved", "Enforced")}</li>
                                <li><span>Match XI drawn only from available squad</span>${UI.statusBadge("approved", "Enforced")}</li>
                                <li><span>Age limits${eligibility.ageText}</span>${eligibility.ageActive ? UI.statusBadge("approved", "Enforced") : UI.statusBadge("off", "Not set")}</li>
                                <li><span>Sex eligibility${eligibility.sexText}</span>${eligibility.sexActive ? UI.statusBadge("approved", "Enforced") : UI.statusBadge("off", "Open")}</li>
                                <li><span>Overseas players per XI${eligibility.overseasText}</span>${eligibility.overseasActive ? UI.statusBadge("approved", "Enforced") : UI.statusBadge("off", "Not set")}</li>
                            </ul>
                        `)}
                    </div>
                </div>
            </div>`;

        state.squadMembership = membership;
    }


    // =========================
    // VENUES
    // =========================

    async function renderVenues() {
        const links = await API.tournament.venues(state.id);
        const t = state.tournament;
        const locked = configLocked();
        const permitted = new Set(links.map((link) => link.venue_id));
        const candidates = [...state.venues.values()]
            .filter((venue) => venue.status === "active" && !permitted.has(venue.id))
            .sort((a, b) => a.name.localeCompare(b.name));

        const rows = links.map((link) => {
            const venue = state.venues.get(link.venue_id);
            const primary = t.primary_venue_id === link.venue_id;
            return `
                <tr>
                    <td><strong>${esc(venue?.name || "Unknown venue")}</strong> ${primary ? UI.statusBadge("approved", "Primary") : ""}</td>
                    <td>${esc(venue?.city || "—")}</td>
                    <td>${esc(venue?.country || "—")}</td>
                    <td>${venue?.capacity ?? "—"}</td>
                    <td><div class="row-actions">
                        ${locked ? "—" : `
                            ${primary ? "" : `<button class="table-action" type="button" data-primary-venue="${link.venue_id}">Make primary</button>`}
                            ${primary ? "" : `<button class="table-action table-action-danger" type="button" data-remove-venue="${link.venue_id}">Remove</button>`}`}
                    </div></td>
                </tr>`;
        }).join("");

        sectionRoot.innerHTML = `
            <div class="t-stack">
                ${locked ? notice("warning", "Venues are locked once the tournament is scheduled.") : ""}
                ${links.length ? "" : notice("info", "No permitted venues yet. Until you add one, fixtures may use any active venue.")}
                <div class="t-grid-sidebar">
                    ${panel("Permitted venues", "Fixtures in this tournament may only be played at these venues.", `
                        <div class="table-wrap"><table class="data-table" style="min-width:600px">
                            <thead><tr><th>Venue</th><th>City</th><th>Country</th><th>Capacity</th><th>Actions</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table></div>
                    `)}
                    ${locked ? "" : `
                    <form class="panel" data-form="venue-add" novalidate>
                        <div class="panel-header t-panel-header"><div><h2>Add venue</h2><p>Active venues from master data</p></div></div>
                        <div class="panel-body">
                            <label class="form-field"><span>Venue <em>*</em></span>
                                <select name="venue_id" required>
                                    <option value="">${candidates.length ? "Select a venue…" : "All active venues added"}</option>
                                    ${candidates.map((venue) => `<option value="${venue.id}">${esc(venue.name)} — ${esc(venue.city)}</option>`).join("")}
                                </select>
                            </label>
                            <label class="checkbox-field" style="margin-top:12px"><input type="checkbox" name="primary"> Make this the primary venue</label>
                        </div>
                        <div class="wizard-footer"><span></span><button class="button button-primary" type="submit">Add venue</button></div>
                    </form>`}
                </div>
            </div>`;
    }


    // =========================
    // EVENTS
    // =========================

    sectionRoot.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.target;
        const submitter = event.submitter;

        switch (form.dataset.form) {
            case "basics":
            case "identity":
                await submitIdentityForm(form);
                break;

            case "register":
                await submitRegistration(form, submitter?.dataset.mode || "invite", submitter);
                break;

            case "group": {
                if (!form.reportValidity()) {
                    return;
                }
                const created = await run(submitter, () => API.tournament.createGroup(state.id, {
                    name: form.elements.name.value.trim(),
                    sort_order: Number(form.elements.sort_order.value || 0),
                }), "Group saved.");
                if (created) {
                    await renderTeams();
                }
                break;
            }

            case "roster-add": {
                if (!form.reportValidity()) {
                    return;
                }
                const added = await run(submitter, () => API.tournament.rosterAdd(state.id, form.dataset.membership, {
                    player_id: form.elements.player_id.value,
                    role: form.elements.role.value,
                }), "Player added to the tournament squad.");
                if (added) {
                    await renderSquads();
                }
                break;
            }

            case "deduction": {
                if (!form.reportValidity()) {
                    return;
                }
                const saved = await run(submitter, () => API.tournament.deduct(state.id, {
                    tournament_team_id: form.elements.tournament_team_id.value,
                    points: Number(form.elements.points.value),
                    reason: form.elements.reason.value.trim(),
                }), "Points deducted and recorded in the audit trail.");
                if (saved) {
                    await renderOverview();
                }
                break;
            }

            case "venue-add": {
                if (!form.reportValidity()) {
                    return;
                }
                const venueId = form.elements.venue_id.value;
                const makePrimary = form.elements.primary.checked;
                const added = await run(submitter, async () => {
                    await API.tournament.addVenue(state.id, venueId);
                    if (makePrimary) {
                        await API.tournament.configure(state.id, { primary_venue_id: venueId });
                    }
                    return true;
                }, "Venue added.");
                if (added) {
                    await refresh();
                }
                break;
            }

            default:
                break;
        }
    });


    sectionRoot.addEventListener("change", async (event) => {
        const target = event.target;

        if (target.dataset.role === "team-status") {
            state.teamFilter.status = target.value;
            state.teamFilter.page = 1;
            refreshTeamTable();
            return;
        }

        if (target.dataset.groupFor) {
            target.disabled = true;
            const saved = await run(null, () => API.tournament.assignGroup(state.id, target.dataset.groupFor, target.value || null), "Group updated.");
            if (saved) {
                await renderTeams();
            } else {
                target.disabled = false;
                await renderTeams();
            }
            return;
        }

        if (target.dataset.role === "squad-team") {
            const url = new URL(window.location.href);
            url.searchParams.set("team", target.value);
            window.history.replaceState(null, "", url);
            await renderSquads();
            return;
        }

        if (target.name === "player_id" && target.closest('[data-form="roster-add"]')) {
            const role = target.selectedOptions[0]?.dataset.role;
            if (role) {
                target.form.elements.role.value = role;
            }
        }
    });


    let searchTimer = null;

    sectionRoot.addEventListener("input", (event) => {
        if (event.target.dataset.role === "team-search") {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(() => {
                state.teamFilter.search = event.target.value.trim();
                state.teamFilter.page = 1;
                refreshTeamTable();
            }, 200);
        }
    });


    sectionRoot.addEventListener("click", async (event) => {
        const button = event.target.closest("button");
        if (!button || button.type === "submit") {
            return;
        }
        const data = button.dataset;

        if (data.transition) {
            await handleTransition(button, data.transition);
        } else if (data.action === "toggle-publish") {
            const publish = !state.tournament.is_published;
            if (await run(button, () => API.tournament.publish(state.id, publish), publish ? "Tournament published." : "Tournament unpublished.")) {
                await refresh();
            }
        } else if (data.action === "new-series") {
            await addSeries();
        } else if (data.promote) {
            await promoteReserve(button, data.promote);
        } else if (data.revokeDeduction) {
            const reason = await ask({ title: "Revoke deduction?", message: "The deduction stays on record as revoked and no longer counts.", reason: true, reasonRequired: true, confirmLabel: "Revoke", danger: true });
            if (reason !== null && await run(button, () => API.tournament.revokeDeduction(state.id, data.revokeDeduction, reason), "Deduction revoked.")) {
                await renderOverview();
            }
        } else if (data.action === "save-rules") {
            await saveRules(button);
        } else if (data.loadVersion) {
            const version = state.versions.find((item) => String(item.version) === data.loadVersion);
            state.editor.setRules(version.rules);
            showToast(`Loaded version ${version.version} into the editor. Save to make it current.`, "info");
        } else if (data.action === "propagate-preview") {
            await propagate(button, false);
        } else if (data.action === "propagate-apply") {
            await propagate(button, true);
        } else if (data.teamPage) {
            state.teamFilter.page += Number(data.teamPage);
            refreshTeamTable();
        } else if (data.decide) {
            const approve = data.approve === "true";
            const reason = approve
                ? ""
                : await ask({ title: "Reject registration?", message: "The team is told why its entry was rejected.", reason: true, reasonRequired: true, confirmLabel: "Reject", danger: true });
            if (reason === null) {
                return;
            }
            if (await run(button, () => API.tournament.decide(state.id, data.decide, { approve, reason: reason || null }), approve ? "Registration approved." : "Registration rejected.")) {
                await renderTeams();
            }
        } else if (data.withdraw) {
            const reason = await ask({ title: "Withdraw team?", message: "The team leaves the competition and its group. It can be re-invited later.", reason: true, reasonRequired: true, confirmLabel: "Withdraw", danger: true });
            if (reason !== null && await run(button, () => API.tournament.withdraw(state.id, data.withdraw, reason), "Team withdrawn.")) {
                await renderTeams();
            }
        } else if (data.deleteGroup) {
            if (await run(button, () => API.tournament.deleteGroup(state.id, data.deleteGroup), "Group deleted.")) {
                await renderTeams();
            }
        } else if (data.captain) {
            if (await run(button, () => API.tournament.setCaptain(state.id, state.squadMembership.id, data.captain), "Captain updated.")) {
                await renderSquads();
            }
        } else if (data.availability) {
            const makeAvailable = data.available !== "true";
            const reason = makeAvailable
                ? ""
                : await ask({ title: "Mark player unavailable?", message: "Unavailable players cannot be picked in a match XI.", reason: true, reasonLabel: "Reason (injury, absence…)", confirmLabel: "Mark unavailable" });
            if (reason === null) {
                return;
            }
            if (await run(button, () => API.tournament.rosterAvailability(state.id, state.squadMembership.id, data.availability, { is_available: makeAvailable, reason: reason || null }), "Availability updated.")) {
                await renderSquads();
            }
        } else if (data.removePlayer) {
            const confirmed = await ask({ title: "Remove player from squad?", message: "This only affects the tournament squad, not the team's global squad.", confirmLabel: "Remove", danger: true });
            if (confirmed !== null && await run(button, () => API.tournament.rosterRemove(state.id, state.squadMembership.id, data.removePlayer), "Player removed.")) {
                await renderSquads();
            }
        } else if (data.action === "lock-rosters") {
            const reason = await ask({ title: "Lock all rosters now?", message: "Locked squad entries can no longer be removed. Availability can still change.", reason: true, confirmLabel: "Lock rosters" });
            if (reason !== null) {
                const result = await run(button, () => API.tournament.lockRosters(state.id, reason));
                if (result) {
                    showToast(`Locked ${result.locked_entries} roster entr${result.locked_entries === 1 ? "y" : "ies"}.`);
                    await refresh();
                }
            }
        } else if (data.primaryVenue) {
            if (await run(button, () => API.tournament.configure(state.id, { primary_venue_id: data.primaryVenue }), "Primary venue updated.")) {
                await refresh();
            }
        } else if (data.removeVenue) {
            const confirmed = await ask({ title: "Remove venue?", message: "Venues used by a tournament fixture cannot be removed.", confirmLabel: "Remove", danger: true });
            if (confirmed !== null && await run(button, () => API.tournament.removeVenue(state.id, data.removeVenue), "Venue removed.")) {
                await renderVenues();
            }
        }
    });


    // =========================
    // BOOT
    // =========================

    const SECTIONS = {
        overview: renderOverview,
        identity: renderIdentity,
        rules: renderRules,
        teams: renderTeams,
        squads: renderSquads,
        venues: renderVenues,
    };


    async function renderSection() {
        try {
            await SECTIONS[state.section]();
        } catch (error) {
            sectionRoot.innerHTML = notice("danger", esc(UI.errorText(error)));
        }
    }


    async function refresh() {
        await loadCore();
        await renderSection();
    }


    async function init() {
        sectionRoot.innerHTML = `<section class="panel"><div class="panel-body">Loading…</div></section>`;
        try {
            await Promise.all([loadCore(), loadReferenceData()]);
        } catch (error) {
            hero.innerHTML = `<div class="tournament-hero-main">${notice("danger", esc(UI.errorText(error)))}</div>`;
            sectionRoot.innerHTML = "";
            return;
        }
        await renderSection();
    }


    init();

})();
