(() => {
    "use strict";

    function parseCsv(text) {
        const rows = []; let row = [], value = "", quoted = false;
        text = text.replace(/^\uFEFF/, "");
        for (let index = 0; index < text.length; index++) {
            const char = text[index];
            if (char === '"') {
                if (quoted && text[index + 1] === '"') { value += '"'; index++; }
                else quoted = !quoted;
            } else if (!quoted && (char === "," || char === "\n")) {
                row.push(value.replace(/\r$/, "")); value = "";
                if (char === "\n") { if (row.some(cell => cell.trim())) rows.push(row); row = []; }
            } else value += char;
        }
        if (quoted) throw new Error("CSV contains an unclosed quoted field.");
        row.push(value.replace(/\r$/, ""));
        if (row.some(cell => cell.trim())) rows.push(row);
        return rows;
    }

    function csvCell(value) {
        let text = String(value ?? "");
        if (/^[=+@\-\t\r]/.test(text)) text = "'" + text;
        return '"' + text.replaceAll('"', '""') + '"';
    }

    function filterFixtures(rows, { team = "", round = "", status = "" } = {}) {
        return rows.filter(row => (!team || row.home_team_id === team || row.away_team_id === team) &&
            (!round || String(row.round_number) === round) && (!status || (row.match_status === "completed" ? "completed" : row.status) === status));
    }

    window.FixtureBuilderHelpers = { parseCsv, csvCell, filterFixtures };
    const root = document.getElementById("fixture-builder");
    if (!root) return;

    const API = window.API, F = API.fixtures, UI = window.TournamentUI, esc = UI.escapeHtml;
    const el = id => document.getElementById(id);
    const state = { id: root.dataset.tournamentId, tournament: null, rules: null, teams: [], venues: [], memberships: [], groups: [],
        runs: [], run: null, report: null, view: "list", page: 1, pageSize: 25, wizard: null, edit: null };
    const team = id => state.memberships.find(member => member.team_id === id)?.display_name || state.teams.find(item => item.id === id)?.name || "Unknown team";
    const venue = id => state.venues.find(item => item.id === id)?.name || "Venue not set";
    const zone = () => state.tournament.timezone || "UTC";
    const dateTime = value => value ? UI.formatDateTime(value, zone()) : "Time not set";
    const selectedRows = () => filterFixtures(state.report?.fixtures || [], { team: el("fixture-team-filter").value, round: el("fixture-round-filter").value, status: el("fixture-status-filter").value });
    const versions = () => Object.fromEntries((state.report?.fixtures || []).map(row => [row.id, row.version]));
    const option = (value, label, current) => `<option value="${esc(value)}" ${String(value) === String(current) ? "selected" : ""}>${esc(label)}</option>`;
    const field = (name, label, value = "", type = "text", extra = "") => `<label class="form-field"><span>${esc(label)}</span><input name="${name}" type="${type}" value="${esc(value ?? "")}" ${extra}></label>`;
    const select = (name, label, options, current) => `<label class="form-field"><span>${esc(label)}</span><select name="${name}">${options.map(([value, text]) => option(value, text, current)).join("")}</select></label>`;
    const teamOptions = () => [["", "Choose team"], ...state.memberships.map(member => [member.team_id, team(member.team_id)])];
    const venueOptions = () => [["", "Choose venue"], ...state.venues.map(item => [item.id, item.name])];

    function sourceLabel(source) {
        if (!source) return "Opponent not set";
        const parts = source.split(":");
        if (parts[0] === "group") return `Group ${parts.slice(1, -1).join(":")} · ${parts.at(-1) === "1" ? "winner" : `place ${parts.at(-1)}`}`;
        return `${parts[0] === "loser" ? "Loser" : "Winner"} of fixture ${parts[1]}`;
    }
    const opponent = (row, side) => row[`${side}_team_id`] ? team(row[`${side}_team_id`]) : sourceLabel(row[`${side}_source`]);

    function error(target, message) { target.textContent = message || ""; target.classList.toggle("hidden", !message); }
    async function busy(button, operation, errorTarget = el("fixture-error")) {
        const wasDisabled = button?.disabled;
        if (button) button.disabled = true;
        error(errorTarget, "");
        try { return await operation(); }
        catch (failure) { error(errorTarget, failure.status === 409 ? `${UI.errorText(failure)} Reload the saved plan to see the latest version.` : UI.errorText(failure)); }
        finally { if (button) button.disabled = wasDisabled; }
    }
    function download(name, contents) {
        const url = URL.createObjectURL(new Blob([contents], { type: "text/csv;charset=utf-8" }));
        const link = document.createElement("a"); link.href = url; link.download = name;
        document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    async function load(runId = state.run?.id) {
        const workspace = await F.workspace(state.id, runId || undefined);
        state.runs = workspace.runs; state.run = workspace.selected_run; state.report = workspace.report || null;
        state.page = 1;
        el("fixture-run").innerHTML = state.runs.length ? state.runs.map(run => option(run.id,
            `${UI.statusLabel(run.method)} · ${UI.statusLabel(run.status)} · ${UI.formatDateTime(run.created_at, zone())}`, state.run?.id)).join("") : '<option value="">No saved plans</option>';
        const previousTeam = el("fixture-team-filter").value;
        el("fixture-team-filter").innerHTML = option("", "All teams", previousTeam) + state.memberships.map(member => option(member.team_id, team(member.team_id), previousTeam)).join("");
        el("fixture-round-filter").innerHTML = '<option value="">All rounds</option>' + [...new Set((state.report?.fixtures || []).map(row => row.round_number))].sort((a, b) => a - b).map(number => option(number, `Round ${number}`, "")).join("");
        render();
    }

    function render() {
        const rows = state.report?.fixtures || [], summary = state.report?.summary || {};
        const published = state.run?.status === "published";
        el("fixture-plan-status").innerHTML = state.run ? UI.statusBadge(state.run.status) : "";
        el("fixture-validate").disabled = !state.run;
        el("fixture-progress").disabled = !published;
        el("fixture-regenerate").disabled = !rows.length || !rows.some(row => !row.immutable && !["cancelled", "completed"].includes(row.status));
        el("fixture-publish").disabled = !state.run || published || !state.report?.valid || !rows.length;
        el("fixture-metrics").innerHTML = [[summary.matches || 0, "Fixtures"], [summary.rounds || 0, "Rounds"],
            [`${summary.scheduled || 0}/${summary.matches || 0}`, "Allocated"], [summary.minimum_rest_minutes == null ? "—" : `${Math.round(summary.minimum_rest_minutes)} min`, "Shortest rest gap"]]
            .map(([value, label]) => `<div class="fixture-metric"><strong>${esc(value)}</strong><span>${label}</span></div>`).join("");
        const violations = state.report?.violations || [];
        el("fixture-conflicts").innerHTML = !state.run ? '<p class="fixture-help">Create a plan to see feasibility checks.</p>' :
            `<div class="fixture-health ${state.report.valid ? "good" : "error"}"><strong>${state.report.valid ? "Ready for confirmation" : `${violations.length} conflict${violations.length === 1 ? "" : "s"} to resolve`}</strong><br>Checked against rest, venue conflicts, blackouts and the competition window.</div>` +
            violations.slice(0, 30).map(item => `<div class="fixture-health error">${item.fixture_number ? `<strong>Fixture ${item.fixture_number}</strong><br>` : ""}${esc(item.message)}</div>`).join("") +
            (violations.length > 30 ? `<p>${violations.length - 30} more conflicts. Use the filters and validate again after editing.</p>` : "");
        el("fixture-workload").innerHTML = Object.entries(summary.team_counts || {}).map(([id, count]) => `<div class="fixture-workload-row"><span>${esc(team(id))}</span><strong>${count} games</strong></div>`).join("") || '<p class="fixture-help">No assignments yet.</p>';
        const config = state.run?.configuration || {};
        el("fixture-audit-summary").innerHTML = Object.entries(summary.venue_utilization || {}).map(([id, count]) => `<div class="fixture-workload-row"><span>${esc(venue(id))}</span><strong>${count}</strong></div>`).join("") +
            (state.run ? `<p><strong>Algorithm</strong><br>${esc(state.run.algorithm_version)}<br><strong>Seed</strong><br>${state.run.seed ?? "Registration / supplied order"}<br><strong>Timezone</strong><br>${esc(zone())}<br><strong>Balance score</strong><br>${summary.penalty_score ?? "—"}</p><p class="fixture-help">${esc(state.report.limitations?.[0] || "")}</p>` : "") +
            (config.snapshot?.byes?.length ? `<details><summary>${config.snapshot.byes.length} byes</summary>${config.snapshot.byes.map(bye => `<p>R${bye.round_number} · ${esc(bye.team_id ? team(bye.team_id) : sourceLabel(bye.source))}</p>`).join("")}</details>` : "");
        renderView();
    }

    function fixtureCard(row) {
        const immutable = row.immutable || ["completed", "cancelled"].includes(row.status);
        return `<article class="fixture-card" data-fixture-id="${esc(row.id)}">
            <div class="fixture-card-head"><span>#${row.fixture_number} · Round ${row.round_number}${row.group ? ` · Group ${esc(row.group)}` : ""}${row.leg > 1 ? ` · Leg ${row.leg}` : ""}</span><span>${row.immutable ? "Pinned · " : ""}${UI.statusBadge(row.match_status === "completed" ? "completed" : row.status)}</span></div>
            <h3>${esc(opponent(row, "home"))}<span>vs</span>${esc(opponent(row, "away"))}</h3>
            <div class="fixture-card-details"><span>${esc(dateTime(row.scheduled_at))}</span><span>· ${esc(venue(row.venue_id))}</span></div>
            <div class="fixture-card-actions">${!immutable ? `<button class="table-action" type="button" data-fixture-action="edit">${row.status === "draft" ? "Edit" : "Reschedule"}</button>${row.status === "draft" ? '<button class="table-action" type="button" data-fixture-action="swap">Swap allocation</button>' : ""}<button class="table-action" type="button" data-fixture-action="postpone">Postpone</button><button class="table-action table-action-danger" type="button" data-fixture-action="cancel">Cancel</button>` : ""}
            ${!immutable && state.run?.configuration?.reviews?.[row.id] ? '<button class="table-action" type="button" data-fixture-action="review">Review official opponents</button>' : ""}
            ${!["completed", "cancelled"].includes(row.status) && !["ready", "live", "innings_break", "completed"].includes(row.match_status) ? `<button class="table-action" type="button" data-fixture-action="${row.is_locked ? "unlock" : "lock"}">${row.is_locked ? "Unlock" : "Lock"}</button>` : ""}
            ${row.match_id ? `<a class="table-action" href="/match-setup/${esc(row.match_id)}">Open match →</a>` : ""}<button class="table-action" type="button" data-fixture-action="history">History</button></div>
            <details><summary>Why this fixture?</summary><p>${esc(row.explanation)}${row.home_source || row.away_source ? `<br>${esc(sourceLabel(row.home_source))} / ${esc(sourceLabel(row.away_source))}. A completed official result is required to advance.` : ""}</p></details>
        </article>`;
    }

    function renderView() {
        const rows = selectedRows(), start = (state.page - 1) * state.pageSize, pageRows = rows.slice(start, start + state.pageSize);
        el("fixture-previous").disabled = state.page === 1;
        el("fixture-next").disabled = start + state.pageSize >= rows.length || ["matrix", "bracket"].includes(state.view);
        el("fixture-page-summary").textContent = ["matrix", "bracket"].includes(state.view) ? `${rows.length} filtered fixtures` : `${rows.length ? start + 1 : 0}–${Math.min(start + state.pageSize, rows.length)} of ${rows.length} fixtures`;
        if (!rows.length) { el("fixture-view").innerHTML = `<div class="fixture-empty"><strong>${state.run ? "No fixtures match these filters" : "Your next competition starts here"}</strong>${state.run ? "Adjust the team, round or status filter." : "Create a manual draw or generate a reproducible schedule."}</div>`; return; }
        if (state.view === "list") el("fixture-view").innerHTML = pageRows.map(fixtureCard).join("");
        if (state.view === "calendar") {
            const days = new Map();
            pageRows.slice().sort((a, b) => String(a.scheduled_at || "z").localeCompare(String(b.scheduled_at || "z"))).forEach(row => {
                const day = row.scheduled_at ? new Intl.DateTimeFormat("en-CA", { timeZone: zone(), dateStyle: "full" }).format(new Date(row.scheduled_at)) : "Awaiting allocation";
                if (!days.has(day)) days.set(day, []); days.get(day).push(row);
            });
            el("fixture-view").innerHTML = [...days].map(([day, games]) => `<section class="fixture-calendar-day"><h3>${esc(day)}</h3>${games.map(row => `<div class="fixture-calendar-event"><strong>${row.scheduled_at ? esc(new Intl.DateTimeFormat(undefined, { timeZone: zone(), hour: "2-digit", minute: "2-digit" }).format(new Date(row.scheduled_at))) : "TBD"}</strong><div>${esc(opponent(row, "home"))} vs ${esc(opponent(row, "away"))}<small>#${row.fixture_number} · ${esc(venue(row.venue_id))} · R${row.round_number}</small></div></div>`).join("")}</section>`).join("");
        }
        if (state.view === "matrix") {
            const ids = [...new Set(rows.flatMap(row => [row.home_team_id, row.away_team_id]).filter(Boolean))];
            el("fixture-view").innerHTML = `<div class="table-wrap"><table class="fixture-matrix"><thead><tr><th>Opponents</th>${ids.map(id => `<th>${esc(team(id))}</th>`).join("")}</tr></thead><tbody>${ids.map(home => `<tr><th>${esc(team(home))}</th>${ids.map(away => `<td>${home === away ? "—" : rows.filter(row => (row.home_team_id === home && row.away_team_id === away) || (row.home_team_id === away && row.away_team_id === home)).map(row => `<span title="Round ${row.round_number}">#${row.fixture_number}</span>`).join(", ") || "·"}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
        }
        if (state.view === "bracket") {
            const groups = state.run?.configuration?.snapshot?.groups || {};
            const knockout = rows.filter(row => row.stage === "knockout");
            el("fixture-view").innerHTML = (Object.keys(groups).length ? `<div class="fixture-groups">${Object.entries(groups).map(([name, ids]) => `<section class="fixture-group"><h3>Group ${esc(name)}</h3>${ids.map(id => `<p>${esc(team(id))}</p>`).join("")}</section>`).join("")}</div><p class="fixture-help" style="padding:0 20px">Group advancement awaits official Stage 13 rankings. No estimated ranking is used.</p>` : "") +
                (knockout.length ? `<div class="fixture-bracket">${[...new Set(knockout.map(row => row.round_number))].sort((a, b) => a - b).map(round => `<section class="fixture-bracket-round"><h3>${knockout.filter(row => row.round_number === round).length === 1 && round === Math.max(...knockout.map(row => row.round_number)) ? "Final" : `Round ${round}`}</h3>${knockout.filter(row => row.round_number === round).map(row => `<article class="fixture-bracket-match"><small>#${row.fixture_number} · ${esc(dateTime(row.scheduled_at))}</small><div>${esc(opponent(row, "home"))}</div><div>${esc(opponent(row, "away"))}</div></article>`).join("")}</section>`).join("")}</div>` : '<p class="fixture-help" style="padding:20px">This plan has no knockout stage.</p>');
        }
    }

    function defaults() {
        return { method: "round_robin", format: "round_robin", team_ids: state.memberships.map(member => member.team_id), legs: 1, seed: 42,
            group_count: 2, groups: {}, seed_pots: [], advance_per_group: 2, pairings: [], overs: state.rules?.rules?.overs_per_innings ?? null, venue_ids: state.venues.map(item => item.id),
            start_date: state.tournament.start_date || "", end_date: state.tournament.end_date || "", final_date: null, timezone: zone(),
            weekdays: [0, 1, 2, 3, 4, 5, 6], times: ["10:00", "14:00"], duration_minutes: 180, minimum_rest_minutes: 60, blackouts: [], auto_schedule: true };
    }

    function openWizard() {
        state.wizard = { step: 0, config: defaults(), preview: null, requestId: crypto.randomUUID() };
        renderWizard(); el("fixture-wizard").showModal();
    }

    function drawFields() {
        const c = state.wizard.config;
        const registeredGroups = Object.fromEntries(state.groups.map(group => [group.id, group.name]));
        return `<div class="form-grid">${select("method", "Planning method", [["round_robin", "Balanced / circle method"], ["random", "Seeded random draw"], ["manual", "Manual fixture editor"]], c.method)}
            ${select("format", "Competition format", [["round_robin", "Round robin"], ["knockout", "Knockout"], ["groups", "Group round robins"], ["hybrid", "Groups + knockout"]], c.format)}
            ${select("legs", "Round-robin legs", [[1, "Single leg"], [2, "Home and away"]], c.legs)}${field("seed", "Random seed", c.seed, "number", 'min="0" max="2147483647"')}
            ${field("group_count", "Number of groups", c.group_count, "number", 'min="2" max="16"')}${field("advance_per_group", "Qualifiers per group", c.advance_per_group, "number", 'min="1" max="4"')}</div>
            <div style="margin-top:16px">${field("overs", "Overs per innings (blank uses tournament defaults)", c.overs, "number", `min="1" ${state.rules ? "readonly" : ""}`)}<p class="fixture-help">Match format and playing-side rules come from <a href="/competitions/${state.id}/rules">competition rules</a>. Published matches must satisfy those rules.</p></div>
            <h3 class="fixture-wizard-section">Choose teams <span class="fixture-help">${c.team_ids.length} selected</span></h3>
            <p class="fixture-help">Only approved, active, non-reserve entries are listed. Order controls seeding; optional group names and pot numbers control group allocation. Leave group names blank for an automatic draw.</p>
            <div class="fixture-team-choices">${state.memberships.map((member, index) => {
                const group = Object.entries(c.groups).find(([, ids]) => ids.includes(member.team_id))?.[0] || "";
                const pot = c.seed_pots.findIndex(ids => ids.includes(member.team_id));
                return `<div class="fixture-team-choice"><label><input type="checkbox" name="chosen_team" value="${esc(member.team_id)}" ${c.team_ids.includes(member.team_id) ? "checked" : ""}>${esc(team(member.team_id))}</label><div class="form-grid" style="gap:6px;padding:8px">${field(`order_${member.team_id}`, "Seed order", c.team_ids.indexOf(member.team_id) >= 0 ? c.team_ids.indexOf(member.team_id) + 1 : index + 1, "number", 'min="1"')}${field(`group_${member.team_id}`, "Group (optional)", group, "text", 'maxlength="40"')}${field(`pot_${member.team_id}`, "Seed pot (optional)", pot >= 0 ? pot + 1 : "", "number", 'min="1" max="128"')}</div>${member.group_id ? `<small class="fixture-help">Registered group: ${esc(registeredGroups[member.group_id] || "Unassigned")}</small>` : ""}</div>`;
            }).join("")}</div>${state.memberships.length < 2 ? '<p class="notice notice-warning">Approve at least two teams in the tournament workspace first.</p>' : ""}
            <p class="fixture-help">Historical ratings are optional and are not calculated here. Supplied seed order and recorded random seeds keep the draw reproducible.</p>
            ${c.method === "manual" ? `<h3 class="fixture-wizard-section">Manual fixture editor</h3><p class="fixture-help">Add opponents, rounds and optional allocations. Incomplete draws can be saved as drafts; publication requires every configured pairing. Times below use your device timezone (${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}).</p><div class="action-row"><button type="button" class="button button-secondary button-small" id="manual-add">+ Add fixture</button><label class="button button-secondary button-small">Import CSV<input type="file" id="manual-import" accept=".csv,text/csv" class="sr-only"></label><button type="button" class="table-action" id="manual-template">CSV template</button></div><div class="table-wrap"><table class="fixture-manual-table"><thead><tr><th>Round</th><th>Home</th><th>Away</th><th>Leg</th><th>Venue</th><th>Start</th><th>End</th><th></th></tr></thead><tbody id="manual-rows">${manualRows()}</tbody></table></div>` : ""}`;
    }

    function manualRows() {
        return state.wizard.config.pairings.map((row, index) => `<tr data-manual-row="${index}"><td><input aria-label="Round" data-manual="round_number" type="number" min="1" value="${row.round_number}" required></td><td><select aria-label="Home team" data-manual="home_team_id" required>${teamOptions().map(([id, name]) => option(id, name, row.home_team_id)).join("")}</select></td><td><select aria-label="Away team" data-manual="away_team_id" required>${teamOptions().map(([id, name]) => option(id, name, row.away_team_id)).join("")}</select></td><td><input aria-label="Leg" data-manual="leg" type="number" min="1" max="2" value="${row.leg || 1}" required></td><td><select aria-label="Venue" data-manual="venue_id">${venueOptions().map(([id, name]) => option(id, name, row.venue_id)).join("")}</select></td><td><input aria-label="Start time" data-manual="scheduled_at" type="datetime-local" value="${UI.toLocalInput(row.scheduled_at)}"></td><td><input aria-label="End time" data-manual="ends_at" type="datetime-local" value="${UI.toLocalInput(row.ends_at)}"></td><td><button type="button" class="table-action" data-manual-remove="${index}">Remove</button></td></tr>`).join("");
    }

    function scheduleFields(config) {
        return `<div class="form-grid">${field("start_date", "First playable date", config.start_date, "date", "required")}${field("end_date", "Last playable date", config.end_date, "date", "required")}
            ${field("final_date", "Desired final date (optional)", config.final_date, "date")}${field("times", `Start times (${zone()})`, config.times.map(value => value.slice(0, 5)).join(", "), "text", 'placeholder="10:00, 14:00" required')}
            ${field("duration_minutes", "Match duration (minutes)", config.duration_minutes, "number", 'min="1" max="1440" required')}${field("minimum_rest_minutes", "Minimum rest (minutes)", config.minimum_rest_minutes, "number", 'min="0" max="43200" required')}</div>
            <h3 class="fixture-wizard-section">Playable weekdays</h3><div class="action-row">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((name, index) => `<label class="checkbox-field"><input name="weekday" type="checkbox" value="${index}" ${config.weekdays.includes(index) ? "checked" : ""}>${name}</label>`).join("")}</div>
            <h3 class="fixture-wizard-section">Available venues</h3><div class="fixture-team-choices">${state.venues.map(item => `<label><input name="chosen_venue" type="checkbox" value="${esc(item.id)}" ${config.venue_ids.includes(item.id) ? "checked" : ""}>${esc(item.name)}</label>`).join("")}</div>
            ${!state.venues.length ? `<p class="notice notice-warning">Assign active venues in the <a href="/competitions/${state.id}/venues">tournament venue list</a>.</p>` : ""}
            <h3 class="fixture-wizard-section">Blackouts &amp; availability</h3><p class="fixture-help">Existing venue availability and other published matches are checked automatically. Add exclusions below; select a team, a venue, or all fixtures. Input times use your device timezone.</p>
            <div id="blackout-rows">${config.blackouts.map((entry, index) => blackoutRow(entry, index)).join("")}</div><button type="button" class="button button-secondary button-small" id="blackout-add">+ Add blackout</button>
            <p class="fixture-help">The competition timezone is ${esc(zone())}. Dates and weekdays follow that timezone, including daylight-saving changes. A capacity conflict will be reported if the supplied times cannot fit the draw.</p>`;
    }

    function blackoutRow(entry, index) {
        const target = entry.team_id ? `team:${entry.team_id}` : entry.venue_id ? `venue:${entry.venue_id}` : "all";
        return `<div class="form-grid" data-blackout="${index}" style="margin-bottom:15px">${select("blackout_target", "Applies to", [["all", "All fixtures"], ...state.memberships.map(member => [`team:${member.team_id}`, team(member.team_id)]), ...state.venues.map(item => [`venue:${item.id}`, item.name])], target)}${field("blackout_start", "From (device time)", UI.toLocalInput(entry.start_at), "datetime-local", "required")}${field("blackout_end", "Until (device time)", UI.toLocalInput(entry.end_at), "datetime-local", "required")}<button type="button" class="table-action" data-blackout-remove="${index}">Remove blackout</button></div>`;
    }

    function collectManual() {
        if (!el("manual-rows")) return;
        state.wizard.config.pairings = [...el("manual-rows").querySelectorAll("tr")].map((row, index) => {
            const values = Object.fromEntries([...row.querySelectorAll("[data-manual]")].map(control => [control.dataset.manual, control.value]));
            return { ...state.wizard.config.pairings[index], ...values, round_number: Number(values.round_number), leg: Number(values.leg), venue_id: values.venue_id || null,
                scheduled_at: UI.fromLocalInput(values.scheduled_at), ends_at: UI.fromLocalInput(values.ends_at) };
        });
    }

    function collectDraw() {
        const form = el("fixture-wizard-form"), c = state.wizard.config, value = name => form.elements.namedItem(name)?.value;
        c.method = value("method"); c.format = value("format"); c.legs = Number(value("legs"));
        c.overs = value("overs") ? Number(value("overs")) : null;
        c.seed = c.method === "random" ? Number(value("seed")) : null;
        if (c.method === "random" && value("seed") === "") throw new Error("Choose and record a random seed.");
        c.group_count = Number(value("group_count")); c.advance_per_group = Number(value("advance_per_group"));
        c.team_ids = [...form.querySelectorAll('[name="chosen_team"]:checked')].map(control => control.value)
            .sort((a, b) => Number(value(`order_${a}`)) - Number(value(`order_${b}`)));
        if (c.team_ids.length < 2) throw new Error("Select at least two approved teams.");
        c.groups = {}; const pots = {};
        for (const id of c.team_ids) {
            const group = value(`group_${id}`).trim(), pot = value(`pot_${id}`);
            if (group) (c.groups[group] ||= []).push(id);
            if (pot) (pots[pot] ||= []).push(id);
        }
        c.seed_pots = Object.keys(pots).sort((a, b) => Number(a) - Number(b)).map(key => pots[key]);
        if (!["groups", "hybrid"].includes(c.format)) { c.groups = {}; c.seed_pots = []; }
        collectManual();
        if (c.method === "manual" && c.format !== "round_robin") throw new Error("The manual editor uses round-robin pairings. Choose Round robin as the format.");
    }

    function collectSchedule(form, config) {
        const value = name => form.elements.namedItem(name).value;
        const c = { ...config, start_date: value("start_date") || null, end_date: value("end_date") || null, final_date: value("final_date") || null,
            times: value("times").split(",").map(time => time.trim()).filter(Boolean),
            duration_minutes: Number(value("duration_minutes")), minimum_rest_minutes: Number(value("minimum_rest_minutes")),
            weekdays: [...form.querySelectorAll('[name="weekday"]:checked')].map(control => Number(control.value)),
            venue_ids: [...form.querySelectorAll('[name="chosen_venue"]:checked')].map(control => control.value),
            timezone: zone(), auto_schedule: config.method !== "manual" };
        if (!c.weekdays.length || !c.venue_ids.length) throw new Error("Choose at least one weekday and one venue.");
        if (!c.times.length || c.times.some(time => !/^([01]\d|2[0-3]):[0-5]\d$/.test(time))) throw new Error("Enter start times as HH:MM, separated by commas.");
        c.blackouts = [...form.querySelectorAll("[data-blackout]")].map(row => {
            const target = row.querySelector('[name="blackout_target"]').value;
            return { start_at: UI.fromLocalInput(row.querySelector('[name="blackout_start"]').value), end_at: UI.fromLocalInput(row.querySelector('[name="blackout_end"]').value),
                team_id: target.startsWith("team:") ? target.slice(5) : null, venue_id: target.startsWith("venue:") ? target.slice(6) : null };
        });
        return c;
    }

    function renderWizard() {
        const wizard = state.wizard;
        error(el("fixture-wizard-error"), "");
        document.querySelectorAll("[data-wizard-step]").forEach(button => { button.classList.toggle("active", Number(button.dataset.wizardStep) === wizard.step); button.disabled = Number(button.dataset.wizardStep) > wizard.step; });
        el("wizard-back").hidden = wizard.step === 0;
        el("wizard-next").hidden = wizard.step === 2; el("wizard-save").hidden = wizard.step !== 2;
        el("wizard-next").textContent = wizard.step === 1 ? "Generate preview" : "Continue";
        const result = wizard.preview;
        el("fixture-wizard-body").innerHTML = wizard.step === 0 ? drawFields() : wizard.step === 1 ? scheduleFields(wizard.config) :
            `<div class="fixture-preview-summary"><strong>${result.summary.matches} fixtures · ${result.summary.rounds} rounds · ${result.summary.scheduled} allocated</strong><p>${result.valid ? "All feasibility checks passed." : `${result.violations.length} issues found. You can save a draft and resolve them before publication.`}</p><p>${esc(result.algorithm_version)} · seed ${result.seed ?? "not used"} · ${esc(zone())}</p></div>
            ${result.violations.slice(0, 12).map(item => `<div class="fixture-health error">${item.fixture_number ? `#${item.fixture_number}: ` : ""}${esc(item.message)}</div>`).join("")}
            <p class="fixture-help">Saving preserves a draft. Confirm &amp; publish in the workspace creates the playable Match records.</p>
            <div class="table-wrap"><table class="data-table"><thead><tr><th># / round</th><th>Draw</th><th>Start</th><th>Venue</th></tr></thead><tbody>${result.fixtures.slice(0, 40).map(row => `<tr><td>${row.fixture_number} / R${row.round_number}</td><td>${esc(opponent(row, "home"))} vs ${esc(opponent(row, "away"))}</td><td>${esc(dateTime(row.scheduled_at))}</td><td>${esc(venue(row.venue_id))}</td></tr>`).join("")}</tbody></table></div>${result.fixtures.length > 40 ? '<p class="fixture-help">First 40 shown. All fixtures are available after saving the draft.</p>' : ""}`;
    }

    async function importManual(file) {
        if (file.size > 2 * 1024 * 1024) throw new Error("CSV imports must be smaller than 2 MB.");
        const rows = parseCsv(await file.text()), headers = rows.shift()?.map(value => value.trim().toLowerCase());
        if (!headers || !["round", "home", "away"].every(name => headers.includes(name))) throw new Error("CSV needs round, home and away headers.");
        const resolve = (text, choices) => {
            if (!text?.trim()) return null;
            const matches = choices.filter(item => [item.id, item.name, item.code].some(value => String(value || "").toLowerCase() === text.trim().toLowerCase()));
            if (matches.length !== 1) throw new Error(`Unknown or ambiguous name/code: ${text}`);
            return matches[0].id;
        };
        const approved = new Set(state.memberships.map(member => member.team_id));
        const imported = rows.map((row, index) => {
            const item = Object.fromEntries(headers.map((name, column) => [name, row[column] || ""]));
            const at = text => { if (!text) return null; if (!/(Z|[+-]\d{2}:\d{2})$/i.test(text) || Number.isNaN(Date.parse(text))) throw new Error(`Row ${index + 2}: use ISO datetimes with timezone offsets.`); return new Date(text).toISOString(); };
            return { round_number: Number(item.round), leg: Number(item.leg || 1), home_team_id: resolve(item.home, state.teams.filter(team => approved.has(team.id))),
                away_team_id: resolve(item.away, state.teams.filter(team => approved.has(team.id))), venue_id: resolve(item.venue, state.venues), scheduled_at: at(item.start), ends_at: at(item.end), notes: item.notes || null };
        });
        if (imported.length > 5000) throw new Error("Import at most 5,000 fixtures at a time.");
        state.wizard.config.pairings = imported;
        renderWizard();
    }

    function openEditor(row, mode = "edit") {
        state.edit = { row, mode };
        error(el("fixture-editor-error"), "");
        const title = mode === "edit" ? (row.status === "draft" ? "Edit fixture" : "Reschedule fixture") : UI.statusLabel(mode);
        el("fixture-editor-title").textContent = row ? `${title} #${row.fixture_number}` : title;
        el("fixture-editor-save").hidden = mode === "history";
        el("fixture-editor-save").textContent = mode === "publish" ? "Confirm & publish" : mode === "regenerate" ? "Reschedule unplayed" : "Save changes";
        let body = "";
        if (mode === "publish") body = `<p>Publish ${state.report.fixtures.length} fixtures? Playable fixtures will create Match records in one transaction. Unresolved bracket slots wait for official results.</p><p class="fixture-help">Review the calendar, opponent matrix and conflict panel before confirming.</p>`;
        else if (mode === "regenerate") body = `<p class="fixture-help">Keep pairings and all pinned fixtures. Reassign dates and venues for unplayed, unlocked fixtures; any collision cancels the operation.</p>${scheduleFields(state.run.configuration?.planning || defaults())}`;
        else if (mode === "history") body = '<p class="fixture-help">Loading fixture audit…</p>';
        else if (mode === "swap") body = select("swap_id", "Swap dates and venues with", state.report.fixtures.filter(item => item.id !== row.id && !item.immutable && item.status === "draft" && !item.match_id).map(item => [item.id, `#${item.fixture_number} · ${opponent(item, "home")} vs ${opponent(item, "away")}`]), "");
        else if (["cancel", "postpone", "lock", "unlock", "review"].includes(mode)) body = `<p>${esc(title)} this fixture? ${mode === "review" ? "Apply the current finalized official winners to this unstarted match. Unresolved results and matches with setup already started remain protected." : mode === "cancel" ? "Its linked draft match will be marked abandoned." : mode === "postpone" ? "The current allocation will be released. Reschedule it when a new slot is available." : "Locked fixtures are pinned during partial regeneration."}</p>`;
        else body = `<p class="fixture-help">${esc(opponent(row, "home"))} vs ${esc(opponent(row, "away"))}. Start and end inputs use your device timezone (${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}); the calendar displays ${esc(zone())}.</p><div class="form-grid">${row.status === "draft" && !row.home_source ? select("home_team_id", "Home team", teamOptions(), row.home_team_id) : ""}${row.status === "draft" && !row.away_source ? select("away_team_id", "Away team", teamOptions(), row.away_team_id) : ""}${select("venue_id", "Venue", venueOptions(), row.venue_id)}${field("scheduled_at", "Start (device time)", UI.toLocalInput(row.scheduled_at), "datetime-local")}${field("ends_at", "End (device time)", UI.toLocalInput(row.ends_at), "datetime-local")}${field("notes", "Notes", row.notes, "text", 'maxlength="2000"')}</div>`;
        if (mode !== "history") body += `<div style="margin-top:18px">${field("reason", "Reason for this change", mode === "publish" ? "Organizer confirmed fixture publication" : "", "text", 'required maxlength="1000"')}</div>`;
        el("fixture-editor-body").innerHTML = body;
        el("fixture-editor").showModal();
        if (mode === "history") busy(null, async () => {
            const history = await F.history(row.id);
            el("fixture-editor-body").innerHTML = history.length ? history.map(event => `<div class="fixture-health"><strong>${esc(UI.statusLabel(event.action))}</strong><p>${esc(event.reason || "")}</p><small>${esc(dateTime(event.created_at))}</small></div>`).join("") : '<p class="fixture-help">No audit events yet.</p>';
        }, el("fixture-editor-error"));
    }

    el("fixture-wizard-form").addEventListener("submit", event => {
        event.preventDefault();
        busy(el("wizard-next"), async () => {
            if (state.wizard.step === 0) { collectDraw(); state.wizard.step = 1; renderWizard(); }
            else if (state.wizard.step === 1) {
                state.wizard.config = collectSchedule(event.currentTarget, state.wizard.config);
                state.wizard.preview = await F.preview(state.id, state.wizard.config);
                state.wizard.requestId = crypto.randomUUID(); state.wizard.step = 2; renderWizard();
            }
        }, el("fixture-wizard-error"));
    });
    el("wizard-save").addEventListener("click", event => busy(event.currentTarget, async () => {
        const result = await F.save(state.id, { ...state.wizard.config, request_id: state.wizard.requestId });
        el("fixture-wizard").close(); await load(result.generation_run_id); showToast("Fixture draft saved.");
    }, el("fixture-wizard-error")));
    el("wizard-back").addEventListener("click", () => {
        if (state.wizard.step === 1) {
            try { state.wizard.config = collectSchedule(el("fixture-wizard-form"), state.wizard.config); }
            catch { /* Back remains available while inputs are incomplete. */ }
        }
        state.wizard.step = Math.max(0, state.wizard.step - 1); renderWizard();
    });
    document.querySelectorAll("[data-wizard-step]").forEach(button => button.addEventListener("click", () => {
        if (Number(button.dataset.wizardStep) < state.wizard.step) { state.wizard.step = Number(button.dataset.wizardStep); renderWizard(); }
    }));
    document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
    el("fixture-wizard-body").addEventListener("change", event => {
        if (event.target.id === "manual-import" && event.target.files[0]) busy(null, () => importManual(event.target.files[0]), el("fixture-wizard-error"));
        if (event.target.name === "method") {
            try { collectDraw(); } catch { state.wizard.config.method = event.target.value; }
            renderWizard();
        }
    });
    function blackoutControls(event, form, config) {
        if (event.target.id !== "blackout-add" && !event.target.dataset.blackoutRemove) return false;
        // Preserve incomplete rows as well when adding/removing exclusions.
        const next = [...form.querySelectorAll("[data-blackout]")].map(row => {
            const target = row.querySelector('[name="blackout_target"]').value;
            return { start_at: UI.fromLocalInput(row.querySelector('[name="blackout_start"]').value), end_at: UI.fromLocalInput(row.querySelector('[name="blackout_end"]').value),
                team_id: target.startsWith("team:") ? target.slice(5) : null, venue_id: target.startsWith("venue:") ? target.slice(6) : null };
        });
        if (event.target.id === "blackout-add") next.push({ start_at: null, end_at: null, team_id: null, venue_id: null });
        else next.splice(Number(event.target.dataset.blackoutRemove), 1);
        config.blackouts = next;
        form.querySelector("#blackout-rows").innerHTML = next.map(blackoutRow).join("");
        return true;
    }
    el("fixture-wizard-body").addEventListener("click", event => {
        if (state.wizard.step === 1 && blackoutControls(event, el("fixture-wizard-form"), state.wizard.config)) return;
        if (event.target.id === "manual-template") download("manual-fixtures-template.csv", "round,home,away,leg,venue,start,end,notes\n");
        if (event.target.id === "manual-add" || event.target.dataset.manualRemove !== undefined) {
            collectManual();
            if (event.target.id === "manual-add") state.wizard.config.pairings.push({ round_number: 1, home_team_id: "", away_team_id: "", leg: 1, venue_id: null, scheduled_at: null, ends_at: null });
            else state.wizard.config.pairings.splice(Number(event.target.dataset.manualRemove), 1);
            el("manual-rows").innerHTML = manualRows();
        }
    });
    el("fixture-editor-body").addEventListener("click", event => {
        if (state.edit?.mode === "regenerate") blackoutControls(event, el("fixture-editor-form"), state.edit.config ||= structuredClone(state.run.configuration?.planning || defaults()));
    });
    el("fixture-editor-form").addEventListener("submit", event => {
        event.preventDefault(); const form = event.currentTarget;
        busy(el("fixture-editor-save"), async () => {
            const { row, mode } = state.edit, reason = form.elements.namedItem("reason").value.trim();
            if (!reason) throw new Error("Enter a reason for this change.");
            if (mode === "publish") await F.publish(state.run.id, { expected_versions: versions(), reason });
            else if (mode === "regenerate") await F.regenerate(state.run.id, { expected_versions: versions(), configuration: collectSchedule(form, state.edit.config || state.run.configuration?.planning || defaults()) });
            else if (mode === "swap") {
                const other = state.report.fixtures.find(item => item.id === form.elements.namedItem("swap_id")?.value);
                if (!other) throw new Error("Choose another editable draft fixture.");
                await F.edit(state.run.id, { reason, changes: [[row, other], [other, row]].map(([target, source]) => ({ fixture_id: target.id, expected_version: target.version, venue_id: source.venue_id, scheduled_at: source.scheduled_at, ends_at: source.ends_at })) });
            } else if (mode === "edit") {
                const changes = {};
                for (const name of ["home_team_id", "away_team_id", "venue_id", "scheduled_at", "ends_at", "notes"]) {
                    const control = form.elements.namedItem(name);
                    if (!control) continue;
                    const value = name.endsWith("_at") ? UI.fromLocalInput(control.value) : control.value.trim() || null;
                    const previous = row[name] ?? null;
                    if ((name.endsWith("_at") && value && previous ? Date.parse(value) !== Date.parse(previous) : value !== previous)) changes[name] = value;
                }
                if (!Object.keys(changes).length) throw new Error("There are no changes to save.");
                if (row.status === "draft") await F.edit(state.run.id, { reason, changes: [{ fixture_id: row.id, expected_version: row.version, ...changes }] });
                else await F.action(row.id, { action: "reschedule", expected_version: row.version, reason, venue_id: form.elements.namedItem("venue_id").value || null,
                    scheduled_at: UI.fromLocalInput(form.elements.namedItem("scheduled_at").value), ends_at: UI.fromLocalInput(form.elements.namedItem("ends_at").value) });
            } else await F.action(row.id, { action: mode, expected_version: row.version, reason });
            el("fixture-editor").close(); await load(); showToast(mode === "publish" ? "Fixtures published and playable matches linked." : "Fixture plan updated.");
        }, el("fixture-editor-error"));
    });
    el("fixture-view").addEventListener("click", event => {
        const button = event.target.closest("[data-fixture-action]");
        if (!button) return;
        const row = state.report.fixtures.find(item => item.id === button.closest("[data-fixture-id]").dataset.fixtureId);
        openEditor(row, button.dataset.fixtureAction);
    });
    el("fixture-run").addEventListener("change", event => busy(null, () => load(event.target.value)));
    el("new-fixture-plan").addEventListener("click", openWizard);
    el("fixture-publish").addEventListener("click", () => openEditor(null, "publish"));
    el("fixture-regenerate").addEventListener("click", () => openEditor(null, "regenerate"));
    el("fixture-validate").addEventListener("click", event => busy(event.currentTarget, async () => { state.report = await F.validate(state.run.id); render(); }));
    el("fixture-progress").addEventListener("click", event => busy(event.currentTarget, async () => {
        const result = await F.progress(state.run.id); await load(); showToast(result.changed_count ? "Official results applied to the bracket." : "Bracket checked. Unresolved sources remain blocked.");
    }));
    ["fixture-team-filter", "fixture-round-filter", "fixture-status-filter"].forEach(id => el(id).addEventListener("change", () => { state.page = 1; renderView(); }));
    document.querySelectorAll("[data-fixture-view]").forEach(button => button.addEventListener("click", () => {
        state.view = button.dataset.fixtureView; state.page = 1;
        document.querySelectorAll("[data-fixture-view]").forEach(item => item.setAttribute("aria-selected", String(item === button)));
        renderView();
    }));
    el("fixture-previous").addEventListener("click", () => { state.page = Math.max(1, state.page - 1); renderView(); });
    el("fixture-next").addEventListener("click", () => { state.page++; renderView(); });
    el("fixture-export").addEventListener("click", () => download("fixtures.csv", [["number", "round", "home", "away", "venue", "start", "end", "status"],
        ...selectedRows().map(row => [row.fixture_number, row.round_number, opponent(row, "home"), opponent(row, "away"), venue(row.venue_id), row.scheduled_at, row.ends_at, row.status])].map(row => row.map(csvCell).join(",")).join("\r\n")));

    async function init() {
        try {
            const [tournament, teams, memberships, venues, assigned, groups, rules] = await Promise.all([
                API.tournament.get(state.id), API.listAll("teams"), API.tournament.teams(state.id), API.listAll("venues"), API.tournament.venues(state.id), API.tournament.groups(state.id),
                API.tournament.currentRules(state.id).catch(() => null),
            ]);
            state.tournament = tournament; state.teams = teams; state.rules = rules;
            state.memberships = memberships.filter(member => member.registration_status === "approved" && !member.is_reserve && teams.some(team => team.id === member.team_id && team.status === "active"))
                .sort((a, b) => (a.seed ?? Infinity) - (b.seed ?? Infinity) || a.team_id.localeCompare(b.team_id));
            const permitted = new Set(assigned.map(item => item.venue_id));
            state.venues = venues.filter(item => permitted.has(item.id) && item.status === "active"); state.groups = groups;
            el("fixture-tournament").textContent = tournament.name;
            document.title = `${tournament.name} · Fixture Builder`;
            await load(); el("fixture-workspace").hidden = false;
            el("new-fixture-plan").disabled = ["completed", "cancelled", "archived"].includes(tournament.status);
        } catch (failure) { error(el("fixture-error"), UI.errorText(failure)); }
        finally { el("fixture-loading").hidden = true; }
    }
    init();
})();
