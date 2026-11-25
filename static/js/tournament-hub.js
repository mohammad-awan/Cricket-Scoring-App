/* Stage 13 tournament screens: Fixtures & Live, Groups & Tables, Bracket,
   Player Statistics, Leaderboards, Awards, Records, Organizer Operations
   and Reports. Mounted by tournament-detail.js through window.TournamentHub. */
(() => {

    "use strict";

    const AWARD_TITLES = {
        batter_of_tournament: "Batter of the Tournament",
        bowler_of_tournament: "Bowler of the Tournament",
        player_of_tournament: "Player of the Tournament",
        emerging_player: "Emerging Player",
        best_fielder: "Best Fielder",
        most_sixes: "Most Sixes",
        best_economy: "Best Economy",
    };

    const QUALIFICATION_LABELS = {
        qualified: "Qualified",
        eliminated: "Eliminated",
        in_contention: "In contention",
        awaiting_adjudication: "Awaiting adjudication",
    };

    let socket = null;
    let socketTournament = null;
    let refreshTimer = null;

    function ctxHelpers(ctx) {
        const { esc } = ctx;

        const num = (value, digits = 2) => (value === null || value === undefined ? "–" : Number(value).toFixed(digits));
        const nrr = (value) => (value === null || value === undefined ? "–" : `${value >= 0 ? "+" : ""}${Number(value).toFixed(3)}`);
        const when = (value) => (value ? ctx.UI.formatDateTime(value, ctx.state.tournament?.timezone) : "Unscheduled");

        function table(headers, rows, { minWidth = 640, empty = "Nothing to show yet." } = {}) {
            if (!rows.length) {
                return `<p class="muted">${esc(empty)}</p>`;
            }
            return `<div class="table-wrap"><table class="data-table" style="min-width:${minWidth}px">
                <thead><tr>${headers.map((header) => `<th>${esc(header)}</th>`).join("")}</tr></thead>
                <tbody>${rows.map((cells) => `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
            </table></div>`;
        }

        function links(row) {
            const l = row.links || {};
            if (!row.match_id) {
                return `<span class="muted">No match yet</span>`;
            }
            const items = [];
            if (["live", "innings_break"].includes(row.match_status)) {
                items.push(`<a class="table-action" href="${esc(l.live_viewer)}">Watch live</a>`);
                items.push(`<a class="table-action" href="${esc(l.live_scoring)}">Score</a>`);
            } else if (["draft", "ready"].includes(row.match_status)) {
                items.push(`<a class="table-action" href="${esc(l.match_setup)}">Match setup</a>`);
            } else if (row.match_status === "completed") {
                items.push(`<a class="table-action" href="${esc(l.corrections)}">Corrections</a>`);
            }
            items.push(`<a class="table-action" href="${esc(l.scorecard)}">Scorecard</a>`);
            return items.join(" ");
        }

        function fixtureLine(row) {
            const innings = (row.innings || []).map((item) => `${esc(item.team_name)} ${esc(item.score)} (${esc(item.overs)})`).join(" · ");
            return `<strong>${esc(row.home_team_name || "TBD")}</strong> v <strong>${esc(row.away_team_name || "TBD")}</strong>
                ${innings ? `<div class="muted">${innings}</div>` : ""}
                ${row.result ? `<div>${esc(row.result)}</div>` : ""}`;
        }

        function playerLink(row) {
            return `<button class="table-action" type="button" data-hub-player="${esc(row.player_id)}">${esc(row.player_name)}</button>`;
        }

        function teamsOf(row) {
            return (row.teams || []).map((team) => esc(team.team_name)).join(", ");
        }

        return { num, nrr, when, table, links, fixtureLine, playerLink, teamsOf };
    }

    function connectEvents(ctx) {
        if (socket && socketTournament === ctx.state.id) {
            return;
        }
        try {
            socket?.close();
            const protocol = window.location.protocol === "https:" ? "wss" : "ws";
            socket = new WebSocket(`${protocol}://${window.location.host}/tournaments/${ctx.state.id}/live/ws`);
            socketTournament = ctx.state.id;
            socket.addEventListener("message", (message) => {
                let data = null;
                try {
                    data = JSON.parse(message.data);
                } catch {
                    return;
                }
                if (!data || data.event_type === "connected") {
                    return;
                }
                window.clearTimeout(refreshTimer);
                refreshTimer = window.setTimeout(() => ctx.rerender(), 800);
            });
        } catch {
            socket = null;
        }
    }


    // =========================
    // FIXTURES & LIVE
    // =========================

    async function renderLive(ctx) {
        const { esc, panel, notice } = ctx;
        const h = ctxHelpers(ctx);
        const [live, calendar] = await Promise.all([
            API.tournamentHub.live(ctx.state.id),
            API.tournamentHub.calendar(ctx.state.id),
        ]);
        connectEvents(ctx);

        const liveBody = live.live.length
            ? h.table(["#", "Match", "Venue", "Status", ""], live.live.map((row) => [
                esc(row.fixture_number), h.fixtureLine(row), esc(row.venue_name || "–"),
                ctx.UI.statusBadge(row.match_status), h.links(row),
            ]))
            : notice("info", "No match is live right now.");

        const days = calendar.days.map((day) => panel(
            ctx.UI.formatDate(day.date),
            `${day.fixtures.length} fixture${day.fixtures.length === 1 ? "" : "s"}`,
            h.table(["#", "Time", "Stage", "Match", "Venue", "Status", ""], day.fixtures.map((row) => [
                esc(row.fixture_number), esc(h.when(row.scheduled_at)),
                esc(row.group_name ? `Group ${row.group_name}` : row.stage), h.fixtureLine(row),
                esc(row.venue_name || "–"),
                ctx.UI.statusBadge(row.match_status || row.fixture_status, row.outcome !== "pending" ? row.outcome.replace("_", " ") : undefined),
                h.links(row),
            ]), { minWidth: 860 }),
        )).join("");

        const unscheduled = calendar.unscheduled.length
            ? panel("Unscheduled", "Awaiting venue/time or bracket teams", h.table(["#", "Match", "Status", ""],
                calendar.unscheduled.map((row) => [esc(row.fixture_number), h.fixtureLine(row), ctx.UI.statusBadge(row.fixture_status), h.links(row)])))
            : "";

        ctx.root.innerHTML = panel("Live now", `Updates automatically from committed match state · times in ${esc(calendar.timezone)}`, liveBody)
            + (days || panel("Schedule", "", notice("info", "No published fixtures yet. Publish fixtures in the Fixtures builder.")))
            + unscheduled;
    }


    // =========================
    // GROUPS & TABLES
    // =========================

    function permutations(items) {
        if (items.length <= 1) {
            return [items];
        }
        return items.flatMap((item, index) => permutations([...items.slice(0, index), ...items.slice(index + 1)]).map((rest) => [item, ...rest]));
    }

    async function renderTables(ctx) {
        const { esc, panel, notice } = ctx;
        const h = ctxHelpers(ctx);
        const [tables, standings] = await Promise.all([
            API.tournamentHub.groupTables(ctx.state.id),
            API.tournamentHub.standings(ctx.state.id),
        ]);
        connectEvents(ctx);
        ctx.state.hubTables = tables;

        const groups = tables.groups.map((group) => {
            const unresolved = group.standings.filter((row) => row.ranking_unresolved);
            const ranks = [...new Set(unresolved.map((row) => row.rank))];
            const actions = ranks.map((rank) => `<button class="button button-secondary button-small" type="button"
                data-hub-adjudicate="${esc(group.group_key)}" data-rank="${rank}">Adjudicate tie at #${rank}</button>`).join("");
            const body = h.table(
                ["#", "Team", "P", "W", "L", "T", "NR", "A", "Pts", "For", "Against", "NRR", "Form", "Status"],
                group.standings.map((row) => [
                    `${esc(row.rank)}${row.ranking_unresolved ? " =" : ""}${row.adjudicated ? ` <span class="chip" title="${esc(row.adjudication?.reason || "")}">adjudicated</span>` : ""}`,
                    `<strong>${esc(row.team_name)}</strong>${row.deductions ? ` <span class="muted">(−${esc(row.deductions)})</span>` : ""}${row.bonus_points ? ` <span class="muted">(+${esc(row.bonus_points)})</span>` : ""}`,
                    esc(row.played), esc(row.won), esc(row.lost), esc(row.tied), esc(row.no_result), esc(row.abandoned),
                    `<strong>${esc(row.points)}</strong>`,
                    `${esc(row.runs_for)}/${esc(row.overs_faced)}`, `${esc(row.runs_against)}/${esc(row.overs_bowled)}`,
                    esc(h.nrr(row.net_run_rate)), esc((row.form || []).join(" ")),
                    `<span class="chip">${esc(QUALIFICATION_LABELS[row.qualification_status] || row.qualification_status)}</span>`,
                ]),
                { minWidth: 980 },
            );
            const fixtures = group.fixtures.length
                ? `<details style="margin-top:12px"><summary>Group fixtures (${group.fixtures.length})</summary>${h.table(["#", "Match", "Status", ""],
                    group.fixtures.map((row) => [esc(row.fixture_number), h.fixtureLine(row), ctx.UI.statusBadge(row.match_status || row.fixture_status), h.links(row)]))}</details>`
                : "";
            return panel(
                group.group_name === "League" ? "Points table" : `Group ${group.group_name}`,
                `${esc(group.status.replace(/_/g, " "))} · top ${esc(tables.top_k)} qualify · ${esc(group.remaining_fixtures)} fixture(s) remaining`,
                body + fixtures,
                { actions },
            );
        }).join("");

        const slots = tables.knockout_slots.length
            ? panel("Seeded knockout slots", "Filled only when the group position is final", h.table(["Fixture", "Side", "Source", "Resolved team", "Status"],
                tables.knockout_slots.map((slot) => [esc(slot.fixture_number), esc(slot.side), esc(slot.source),
                    esc(slot.resolved_team_id ? (ctx.state.teams.get(slot.resolved_team_id)?.name || slot.resolved_team_id) : "–"),
                    `${ctx.UI.statusBadge(slot.status)} <span class="muted">${esc(slot.message)}</span>`])))
            : "";

        const conventions = `<details><summary>Ranking policy (rules v${esc(standings.ruleset_version)})</summary>
            <p><strong>Tie-breakers:</strong> ${esc(standings.tie_breakers.join(" → "))}</p>
            <ul>${Object.entries(standings.conventions).map(([key, value]) => `<li><strong>${esc(key.replace(/_/g, " "))}:</strong> ${esc(value)}</li>`).join("")}</ul>
            ${standings.warnings.length ? ctx.listNotice("warning", "Warnings", standings.warnings) : ""}
        </details>`;

        ctx.root.innerHTML = (groups || panel("Tables", "", notice("info", "No approved teams yet.")))
            + slots + panel("Policy", "", conventions);
    }


    // =========================
    // BRACKET
    // =========================

    async function renderBracket(ctx) {
        const { esc, panel, notice } = ctx;
        const h = ctxHelpers(ctx);
        const bracket = await API.tournamentHub.bracket(ctx.state.id);
        connectEvents(ctx);

        if (!bracket.rounds.length) {
            ctx.root.innerHTML = panel("Bracket", "", notice("info", "This tournament has no knockout fixtures."));
            return;
        }

        const columns = bracket.rounds.map((round) => `
            <div style="flex:1 1 220px;min-width:220px">
                <h3 style="margin:0 0 10px">${esc(round.name)}</h3>
                ${round.fixtures.map((row) => `
                    <div class="panel" style="padding:10px;margin-bottom:10px">
                        <div class="muted">#${esc(row.fixture_number)} · ${esc(h.when(row.scheduled_at))}</div>
                        <div ${row.advancing_team_id === row.home_team_id && row.home_team_id ? 'style="font-weight:700"' : ""}>${esc(row.home_team_name || "TBD")}</div>
                        <div ${row.advancing_team_id === row.away_team_id && row.away_team_id ? 'style="font-weight:700"' : ""}>${esc(row.away_team_name || "TBD")}</div>
                        ${row.result ? `<div class="muted">${esc(row.result)}</div>` : ""}
                        ${row.review_required ? notice("warning", esc(row.review_required)) : ""}
                        <div style="margin-top:6px">${h.links(row)}</div>
                    </div>`).join("")}
            </div>`).join("");

        const review = bracket.dependency_review.dependencies;
        ctx.root.innerHTML = panel(
            "Bracket",
            "Slots advance only from finalized official results",
            `<div style="display:flex;gap:16px;overflow-x:auto;align-items:flex-start">${columns}</div>`,
            { actions: `<button class="button button-primary button-small" type="button" data-hub-action="resolve-bracket">Recompute bracket</button>` },
        ) + panel("Dependency review", `${bracket.dependency_review.unresolved_count} unresolved`,
            h.table(["Target fixture", "Side", "Rule", "Status"], review.map((item) => [
                esc(item.target_fixture_id), esc(item.target_side), esc(item.advancement), ctx.UI.statusBadge(item.status),
            ])));
    }


    // =========================
    // PLAYER STATISTICS & LEADERBOARDS
    // =========================

    function battingTable(ctx, rows) {
        const { esc } = ctx;
        const h = ctxHelpers(ctx);
        return h.table(["#", "Player", "Teams", "M", "Inns", "NO", "Runs", "Balls", "HS", "Avg", "SR", "4s", "6s", "50", "100", "Form"],
            rows.map((row, index) => [esc(index + 1), h.playerLink(row), h.teamsOf(row), esc(row.matches), esc(row.innings), esc(row.not_outs),
                `<strong>${esc(row.runs)}</strong>`, esc(row.balls), esc(row.highest_score_display), esc(h.num(row.average)), esc(h.num(row.strike_rate)),
                esc(row.fours), esc(row.sixes), esc(row.fifties), esc(row.hundreds), esc(row.recent_form.join(", "))]),
            { minWidth: 1100 });
    }

    function bowlingTable(ctx, rows) {
        const { esc } = ctx;
        const h = ctxHelpers(ctx);
        return h.table(["#", "Player", "Teams", "M", "Inns", "Overs", "Mdns", "Runs", "Wkts", "Best", "Econ", "Avg", "SR", "4w", "5w"],
            rows.map((row, index) => [esc(index + 1), h.playerLink(row), h.teamsOf(row), esc(row.matches), esc(row.innings), esc(row.overs),
                esc(row.maidens), esc(row.runs_conceded), `<strong>${esc(row.wickets)}</strong>`, esc(row.best_figures_display),
                esc(h.num(row.economy)), esc(h.num(row.average)), esc(h.num(row.strike_rate)), esc(row.four_wicket_hauls), esc(row.five_wicket_hauls)]),
            { minWidth: 1050 });
    }

    function fieldingTable(ctx, rows) {
        const { esc } = ctx;
        const h = ctxHelpers(ctx);
        return h.table(["#", "Player", "Teams", "M", "Catches", "Stumpings", "Run outs", "Total"],
            rows.map((row, index) => [esc(index + 1), h.playerLink(row), h.teamsOf(row), esc(row.matches), esc(row.catches),
                esc(row.stumpings), esc(row.run_outs), `<strong>${esc(row.total_dismissals)}</strong>`]));
    }

    function filterBar(ctx, filters, { team = true } = {}) {
        const { esc } = ctx;
        const teams = ctx.state.memberships.length
            ? ctx.state.memberships.map((m) => [m.team_id, m.display_name || ctx.state.teams.get(m.team_id)?.name || "Team"])
            : [...ctx.state.teams.entries()].map(([id, t]) => [id, t.name]);
        return `<form class="action-row" data-hub-filters style="flex-wrap:wrap;gap:12px;margin-bottom:12px">
            ${team ? `<label class="form-field"><span>Team</span><select name="team_id"><option value="">All teams</option>
                ${teams.map(([id, name]) => `<option value="${esc(id)}" ${filters.team_id === id ? "selected" : ""}>${esc(name)}</option>`).join("")}</select></label>` : ""}
            <label class="form-field"><span>Min innings (batting)</span><input type="number" min="0" name="min_innings" value="${esc(filters.min_innings || 0)}"></label>
            <label class="form-field"><span>Min legal balls (bowling)</span><input type="number" min="0" name="min_balls" value="${esc(filters.min_balls || 0)}"></label>
            <label class="form-field"><span>Qualified only</span><input type="checkbox" name="qualified_only" ${filters.qualified_only ? "checked" : ""}></label>
            <button class="button button-secondary button-small" type="submit">Apply</button>
        </form>`;
    }

    async function renderLeaderboards(ctx) {
        const { esc, panel } = ctx;
        const filters = ctx.state.hubFilters || {};
        const data = await API.tournamentHub.leaderboards(ctx.state.id, { ...filters, team_id: undefined, qualified_only: filters.qualified_only || undefined });
        const s = data.dismissal_summary;
        ctx.root.innerHTML = panel("Leaderboard filters", "Configurable qualification; ties broken deterministically", filterBar(ctx, filters, { team: false }))
            + panel("Most runs (Orange Cap)", `Ties: ${esc(data.tie_rules.batting.join(", "))}`, battingTable(ctx, data.batting.slice(0, 25)),
                { actions: `<a class="button button-secondary button-small" href="/tournaments/${esc(ctx.state.id)}/leaderboards/export?category=batting">CSV</a>` })
            + panel("Most wickets (Purple Cap)", `Ties: ${esc(data.tie_rules.bowling.join(", "))}`, bowlingTable(ctx, data.bowling.slice(0, 25)),
                { actions: `<a class="button button-secondary button-small" href="/tournaments/${esc(ctx.state.id)}/leaderboards/export?category=bowling">CSV</a>` })
            + panel("Fielding", esc(data.data_requirements.fielding), fieldingTable(ctx, data.fielding.slice(0, 25)),
                { actions: `<a class="button button-secondary button-small" href="/tournaments/${esc(ctx.state.id)}/leaderboards/export?category=fielding">CSV</a>` })
            + panel("Dismissals", "Credited bowler wickets are distinguished from all dismissals",
                `<div class="chip-row">${Object.entries(s).map(([key, value]) => `<span class="chip">${esc(key.replace(/_/g, " "))} <strong>${esc(value)}</strong></span>`).join("")}</div>`)
            + `<div id="hub-player-profile"></div>`;
    }

    async function renderStatistics(ctx) {
        const { esc, panel } = ctx;
        const h = ctxHelpers(ctx);
        const filters = ctx.state.hubFilters || {};
        const [data, teams] = await Promise.all([
            API.tournamentHub.leaderboards(ctx.state.id, { ...filters, qualified_only: filters.qualified_only || undefined }),
            API.tournamentHub.teamStats(ctx.state.id),
        ]);
        ctx.root.innerHTML = panel("Player statistics", "From official completed matches; team view uses each player's team in that match", filterBar(ctx, filters))
            + `<div id="hub-player-profile"></div>`
            + panel("Batting", "", battingTable(ctx, data.batting))
            + panel("Bowling", esc(data.data_requirements.maidens), bowlingTable(ctx, data.bowling))
            + panel("Fielding", esc(data.data_requirements.fielding), fieldingTable(ctx, data.fielding))
            + panel("Team aggregates", "Match-by-match form in the last column", h.table(
                ["Team", "M", "W", "L", "T", "NR", "Runs", "RR", "Wkts lost", "Conceded", "Econ", "Wkts taken", "Extras conceded", "High", "Low", "Form"],
                teams.teams.map((row) => [`<strong>${esc(row.team_name)}</strong>`, esc(row.matches), esc(row.won), esc(row.lost), esc(row.tied), esc(row.no_result),
                    esc(row.runs_scored), esc(h.num(row.run_rate)), esc(row.wickets_lost), esc(row.runs_conceded), esc(h.num(row.economy)), esc(row.wickets_taken),
                    esc(row.extras_conceded), esc(row.highest_total ?? "–"), esc(row.lowest_total ?? "–"),
                    row.form.map((item) => `<a href="${esc(item.scorecard_url)}" title="v ${esc(item.opponent_name)}: ${esc(item.score_for || "")} / ${esc(item.score_against || "")}">${esc(item.result)}</a>`).join(" ")]),
                { minWidth: 1200 }));
    }

    async function showPlayer(ctx, playerId) {
        const { esc, panel } = ctx;
        const h = ctxHelpers(ctx);
        const target = document.getElementById("hub-player-profile");
        if (!target) {
            return;
        }
        const profile = await API.tournamentHub.playerStats(ctx.state.id, playerId);
        const b = profile.batting;
        const w = profile.bowling;
        const f = profile.fielding;
        const summary = `<div class="chip-row">
            ${b ? `<span class="chip">Runs <strong>${esc(b.runs)}</strong></span><span class="chip">Avg <strong>${esc(h.num(b.average))}</strong></span><span class="chip">SR <strong>${esc(h.num(b.strike_rate))}</strong></span><span class="chip">HS <strong>${esc(b.highest_score_display)}</strong></span>` : ""}
            ${w ? `<span class="chip">Wkts <strong>${esc(w.wickets)}</strong></span><span class="chip">Econ <strong>${esc(h.num(w.economy))}</strong></span><span class="chip">Best <strong>${esc(w.best_figures_display)}</strong></span>` : ""}
            ${f ? `<span class="chip">Ct <strong>${esc(f.catches)}</strong></span><span class="chip">St <strong>${esc(f.stumpings)}</strong></span><span class="chip">RO <strong>${esc(f.run_outs)}</strong></span>` : ""}
        </div>`;
        target.innerHTML = panel(profile.player_name || "Player", `<a href="/player-profile/${esc(playerId)}">Career profile</a>`,
            summary + h.table(["Team", "Opponent", "Result", "Batting", "Bowling", "Ct", "St", "RO", ""], profile.matches.map((row) => [
                esc(row.team_name), esc(row.opponent_name), esc(row.result || "–"), esc(row.batting || "–"), esc(row.bowling || "–"),
                esc(row.catches), esc(row.stumpings), esc(row.run_outs), `<a class="table-action" href="${esc(row.scorecard_url)}">Scorecard</a>`,
            ])));
        target.scrollIntoView({ behavior: "smooth", block: "start" });
    }


    // =========================
    // AWARDS
    // =========================

    async function renderAwards(ctx) {
        const { esc, panel, notice } = ctx;
        const h = ctxHelpers(ctx);
        const [candidates, confirmed, publication, settings, results] = await Promise.all([
            API.tournamentHub.awardCandidates(ctx.state.id),
            API.tournamentHub.confirmedAwards(ctx.state.id),
            API.tournamentHub.awardPublication(ctx.state.id),
            API.tournamentHub.awardSettings(ctx.state.id),
            API.tournamentHub.results(ctx.state.id),
        ]);
        ctx.state.hubAwards = { candidates, confirmed, settings, results };
        const confirmedByCode = new Map(confirmed.map((award) => [award.award_code, award]));
        const frozen = publication.published || ctx.isFinal();

        const cards = candidates.awards.map((award) => {
            const current = confirmedByCode.get(award.award_code);
            const rows = award.candidates.map((row, index) => [
                esc(index + 1), h.playerLink(row), h.teamsOf(row),
                esc(row.award_score ?? row.runs ?? row.wickets ?? row.total_dismissals ?? ""),
                esc(award.award_code === "best_economy" ? h.num(row.economy) : award.award_code === "most_sixes" ? row.sixes : ""),
                frozen || current ? "" : `<button class="table-action" type="button" data-hub-confirm="${esc(award.award_code)}" data-player="${esc(row.player_id)}"
                    data-leader="${index === 0 && award.leader_unambiguous ? "1" : ""}">${index === 0 && award.leader_unambiguous ? "Confirm leader" : "Select"}</button>`,
            ]);
            const status = current
                ? notice("success", `<strong>Confirmed:</strong> ${esc(current.evidence?.computed_leader && current.player_id === current.evidence.computed_leader.player_id ? current.evidence.computed_leader.player_name : (candidates.awards.flatMap((a) => a.candidates).find((c) => c.player_id === current.player_id)?.player_name || current.player_id))}
                    · ${esc(current.selection_method)}${current.override ? " · organizer override" : ""} — ${esc(current.reason)}
                    ${frozen ? "" : `<button class="table-action table-action-danger" type="button" data-hub-revoke="${esc(award.award_code)}">Revoke</button>`}`)
                : "";
            const extra = award.award_code === "emerging_player" && !award.eligibility_configured
                ? notice("warning", "Configure emerging player eligibility (age or birth date) in award settings.") : "";
            return panel(award.title, esc(award.basis), status + extra + h.table(["#", "Player", "Teams", "Score / metric", "", ""], rows, { minWidth: 560 }));
        }).join("");

        const pomCounts = candidates.player_of_match_aggregates;
        const pomAwards = confirmed.filter((award) => award.category === "player_of_match");
        const pomByMatch = new Map(pomAwards.map((award) => [award.evidence?.match_id, award]));
        const completed = results.results.filter((row) => row.match_status === "completed");
        const pom = panel("Player of the Match", "Organizer-selected per match; aggregates count confirmed awards",
            h.table(["#", "Match", "Player of the Match", ""], completed.map((row) => {
                const award = pomByMatch.get(row.match_id);
                return [esc(row.fixture_number), h.fixtureLine(row), esc(award ? (pomCounts.find((p) => p.player_id === award.player_id)?.player_name || award.player_id) : "–"),
                    frozen ? "" : award
                        ? `<button class="table-action table-action-danger" type="button" data-hub-revoke="${esc(award.award_code)}">Revoke</button>`
                        : `<button class="table-action" type="button" data-hub-pom="${esc(row.match_id)}" data-home="${esc(row.home_team_id)}" data-away="${esc(row.away_team_id)}">Select</button>`];
            }))
            + `<h3>Most Player of the Match awards</h3>` + h.table(["Player", "Awards"], pomCounts.map((row) => [esc(row.player_name), esc(row.awards)])));

        const manual = confirmed.filter((award) => award.category === "organizer_defined");
        const manualPanel = panel("Organizer-selected awards", "Honorary awards chosen by the organizer, kept separate from computed rankings",
            h.table(["Award", "Recipient", "Reason", ""], manual.map((award) => [esc(award.title), esc(award.player_id || award.team_id), esc(award.reason),
                frozen ? "" : `<button class="table-action table-action-danger" type="button" data-hub-revoke="${esc(award.award_code)}">Revoke</button>`]))
            + (frozen ? "" : `<button class="button button-secondary button-small" type="button" data-hub-action="manual-award">Add organizer award</button>`));

        const w = settings.weights;
        const settingsPanel = panel("Award settings", "Transparent weights and eligibility; changes are audited", `
            <form data-hub-settings class="action-row" style="flex-wrap:wrap;gap:12px">
                ${["runs", "batting_efficiency", "wickets", "economy", "fielding"].map((key) => `<label class="form-field"><span>Weight: ${esc(key.replace("_", " "))}</span><input type="number" step="0.05" min="0" name="w_${key}" value="${esc(w[key])}"></label>`).join("")}
                <label class="form-field"><span>Min matches (PoT)</span><input type="number" min="1" name="w_minimum_matches" value="${esc(w.minimum_matches)}"></label>
                <label class="form-field"><span>Min balls faced (SR)</span><input type="number" min="0" name="w_min_batting_balls" value="${esc(w.min_batting_balls)}"></label>
                <label class="form-field"><span>Min balls bowled (economy)</span><input type="number" min="0" name="w_min_bowling_balls" value="${esc(w.min_bowling_balls)}"></label>
                <label class="form-field"><span>Best economy min balls</span><input type="number" min="0" name="min_economy_balls" value="${esc(settings.min_economy_balls)}"></label>
                <label class="form-field"><span>Batting min innings</span><input type="number" min="0" name="batting_min_innings" value="${esc(settings.batting_min_innings)}"></label>
                <label class="form-field"><span>Emerging: max age</span><input type="number" min="5" max="60" name="max_age" value="${esc(settings.emerging.max_age ?? "")}"></label>
                <label class="form-field"><span>Emerging: born on/after</span><input type="date" name="born_on_or_after" value="${esc(settings.emerging.born_on_or_after ?? "")}"></label>
                <label class="form-field"><span>Committee voting</span><input type="checkbox" name="voting_enabled" ${settings.voting_enabled ? "checked" : ""}></label>
                <label class="form-field" style="min-width:260px"><span>Committee members (comma separated)</span><input type="text" name="committee" value="${esc(settings.committee.join(", "))}"></label>
                ${frozen ? "" : `<button class="button button-secondary button-small" type="submit">Save settings</button>`}
            </form>`);

        const actions = ctx.isFinal()
            ? ""
            : publication.published
                ? `<button class="button button-secondary button-small" type="button" data-hub-action="unpublish-awards">Unpublish to edit</button>`
                : `<button class="button button-primary button-small" type="button" data-hub-action="publish-awards">Publish &amp; freeze awards</button>`;

        ctx.root.innerHTML = panel("Awards", publication.published
            ? `Published ${esc(ctx.UI.formatDateTime(publication.published_at))} — frozen`
            : "Computed candidates are evidence only; every award is confirmed by an organizer", notice("info", esc(candidates.note)), { actions })
            + `<div id="hub-player-profile"></div>` + cards + pom + manualPanel + settingsPanel;
    }

    async function readSettings(form) {
        const data = new FormData(form);
        const value = (name) => data.get(name);
        const number = (name) => (value(name) === "" || value(name) === null ? null : Number(value(name)));
        return {
            weights: {
                runs: number("w_runs"), batting_efficiency: number("w_batting_efficiency"), wickets: number("w_wickets"),
                economy: number("w_economy"), fielding: number("w_fielding"), minimum_matches: number("w_minimum_matches"),
                min_batting_balls: number("w_min_batting_balls"), min_bowling_balls: number("w_min_bowling_balls"),
            },
            emerging: { max_age: number("max_age"), born_on_or_after: value("born_on_or_after") || null },
            batting_min_innings: number("batting_min_innings"),
            min_economy_balls: number("min_economy_balls"),
            voting_enabled: data.get("voting_enabled") === "on",
            committee: String(value("committee") || "").split(",").map((item) => item.trim()).filter(Boolean),
        };
    }


    // =========================
    // RECORDS
    // =========================

    async function renderRecords(ctx) {
        const { esc, panel } = ctx;
        const h = ctxHelpers(ctx);
        const r = await API.tournamentHub.records(ctx.state.id, 10);
        const scoreRows = (rows) => rows.map((row) => [`<strong>${esc(row.team_name)}</strong>`, esc(row.score), `v ${esc(row.opponent_name)}`, `<a class="table-action" href="${esc(row.scorecard_url)}">Scorecard</a>`]);
        ctx.root.innerHTML =
            panel("Highest team totals", "", h.table(["Team", "Score", "Opponent", ""], scoreRows(r.highest_totals)))
            + panel("Lowest completed totals", "All out or full overs", h.table(["Team", "Score", "Opponent", ""], scoreRows(r.lowest_completed_totals)))
            + panel("Highest individual scores", "", h.table(["Player", "Score", "Team", "Opponent"], r.highest_individual_scores.map((row) => [h.playerLink(row), esc(row.display), esc(row.team_name), esc(row.opponent_name)])))
            + panel("Best bowling figures", "", h.table(["Player", "Figures", "Team", "Opponent"], r.best_bowling_figures.map((row) => [h.playerLink(row), esc(row.display), esc(row.team_name), esc(row.opponent_name)])))
            + panel("Top partnerships", esc(r.data_requirements.partnerships), h.table(["Runs", "Balls", "Wicket", "Batters", "Team"], r.top_partnerships.map((row) => [`<strong>${esc(row.runs)}</strong>`, esc(row.balls), esc(row.wicket), esc(row.players.map((p) => p.player_name).join(" & ")), esc(row.team_name)])))
            + panel("Successful chases", "", h.table(["Team", "Target", "Score", "Balls left", ""], r.successful_chases.map((row) => [esc(row.team_name), esc(row.target), esc(row.score), esc(row.balls_remaining ?? "–"), `<a class="table-action" href="${esc(row.scorecard_url)}">Scorecard</a>`])))
            + panel("Biggest wins by runs", "", h.table(["Winner", "Margin", ""], r.biggest_wins_by_runs.map((row) => [esc(row.winner_name), `${esc(row.margin_runs)} runs`, `<a class="table-action" href="${esc(row.scorecard_url)}">Scorecard</a>`])))
            + panel("Biggest wins by wickets", "", h.table(["Winner", "Margin", "Balls left", ""], r.biggest_wins_by_wickets.map((row) => [esc(row.team_name), `${esc(row.margin_wickets)} wickets`, esc(row.balls_remaining ?? "–"), `<a class="table-action" href="${esc(row.scorecard_url)}">Scorecard</a>`])))
            + panel("Most sixes", "", h.table(["Player", "Sixes", "Runs"], r.most_sixes.map((row) => [h.playerLink(row), esc(row.sixes), esc(row.runs)])))
            + `<div id="hub-player-profile"></div>`;
    }


    // =========================
    // ORGANIZER OPERATIONS
    // =========================

    async function renderOperations(ctx) {
        const { esc, panel, notice } = ctx;
        const h = ctxHelpers(ctx);
        const [board, readiness, bonuses, standings] = await Promise.all([
            API.tournamentHub.operations(ctx.state.id),
            API.tournamentHub.readiness(ctx.state.id),
            API.tournamentHub.bonuses(ctx.state.id).catch(() => []),
            API.tournamentHub.standings(ctx.state.id).catch(() => null),
        ]);
        connectEvents(ctx);
        ctx.state.hubBoard = board;

        const alerts = board.alerts.length
            ? board.alerts.map((item) => notice(item.severity === "info" ? "info" : item.severity, `<strong>${esc(item.message)}</strong> — ${esc(item.action)}
                ${item.links?.scorecard ? ` <a href="${esc(item.links.scorecard)}">scorecard</a>` : ""}`)).join("")
            : notice("success", "No organizer intervention required.");

        const pending = Object.values(board.fixtures_by_status).flat()
            .filter((row) => ["pending", "abandoned", "tie", "no_result"].includes(row.outcome) || row.disposition)
            .sort((a, b) => a.fixture_number - b.fixture_number);
        const dispositions = h.table(["#", "Match", "Stage", "Outcome", "Disposition", ""], pending.map((row) => [
            esc(row.fixture_number), h.fixtureLine(row), esc(row.stage), esc(row.outcome),
            esc(row.disposition ? `${row.disposition.outcome} — ${row.disposition.reason}` : "–"),
            ctx.isFinal() ? "" : row.disposition
                ? `<button class="table-action table-action-danger" type="button" data-hub-undispose="${esc(row.fixture_id)}">Revoke</button>`
                : `<button class="table-action" type="button" data-hub-dispose="${esc(row.fixture_id)}">Record disposition</button>`,
        ]), { minWidth: 900, empty: "Every fixture has an official result." });

        const readinessRows = h.table(["#", "Match", "Readiness", "Issues", ""], board.match_readiness.map((row) => [
            esc(row.fixture_number), h.fixtureLine(row), ctx.UI.statusBadge(row.readiness), esc(row.issues.join("; ") || "–"), h.links(row),
        ]), { empty: "No upcoming matches awaiting setup." });

        const teamNames = new Map((standings?.tables || []).flatMap((table) => table.standings.map((row) => [row.team_id, row.team_name])));
        const bonusPanel = panel("Bonus points", standings?.points_policy?.bonus_points_enabled ? "Audited organizer adjustments" : "Disabled by the competition rules",
            h.table(["Team", "Points", "Reason", ""], bonuses.map((item) => [esc(teamNames.get(item.team_id) || item.team_id), esc(item.points), esc(item.reason),
                ctx.isFinal() ? "" : `<button class="table-action table-action-danger" type="button" data-hub-unbonus="${esc(item.bonus_id)}">Revoke</button>`]))
            + (standings?.points_policy?.bonus_points_enabled && !ctx.isFinal() ? `<button class="button button-secondary button-small" type="button" data-hub-action="add-bonus">Add bonus</button>` : ""));

        const finalizeActions = ctx.state.tournament.status === "completed"
            ? `<button class="button button-secondary button-small" type="button" data-hub-action="reopen">Reopen tournament</button>`
            : readiness.ready_to_finalize
                ? `<button class="button button-primary button-small" type="button" data-hub-action="finalize">Finalize &amp; freeze champion</button>`
                : "";
        const closeout = panel("Tournament completion", readiness.ready_to_finalize ? "Ready to finalize" : "Validation before an official champion is frozen",
            (readiness.champion ? notice("info", `Champion by ${esc(readiness.champion.method.replace(/_/g, " "))}: <strong>${esc(teamNames.get(readiness.champion.champion_team_id) || ctx.state.teams.get(readiness.champion.champion_team_id)?.name || readiness.champion.champion_team_id)}</strong>`) : "")
            + (readiness.blockers.length ? ctx.listNotice("danger", "Blockers", readiness.blockers) : notice("success", "All completion checks passed."))
            + (readiness.warnings.length ? ctx.listNotice("warning", "Warnings", readiness.warnings) : "")
            + `<details><summary>Reopening policy</summary><ul>${readiness.reopening_policy.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></details>`,
            { actions: finalizeActions });

        ctx.root.innerHTML =
            panel("Operations board", `Generated ${esc(ctx.UI.formatDateTime(board.generated_at))}`,
                `<div class="chip-row">${Object.entries(board.summary).map(([key, value]) => `<span class="chip">${esc(key.replace(/_/g, " "))} <strong>${esc(value)}</strong></span>`).join("")}</div>
                 <div class="chip-row" style="margin-top:8px">${Object.entries(board.venue_assignment.by_venue).map(([key, value]) => `<span class="chip">${esc(key)} <strong>${esc(value)}</strong></span>`).join("")}</div>`)
            + panel("Alerts", `${board.alerts.length} item(s)`, alerts)
            + panel("Results & dispositions", "Walkover, no result, abandoned, cancelled or knockout advancement — each with an audited reason", dispositions)
            + panel("Match readiness", "Linked to the existing match setup workflow", readinessRows)
            + bonusPanel + closeout;
    }


    // =========================
    // REPORTS
    // =========================

    async function renderReports(ctx) {
        const { esc, panel, notice } = ctx;
        const id = esc(ctx.state.id);
        const t = ctx.state.tournament;
        const [record, history] = await Promise.all([
            API.tournamentHub.officialRecord(ctx.state.id).catch(() => null),
            t.series_id ? API.tournamentSeries.history(t.series_id).catch(() => []) : Promise.resolve([]),
        ]);
        const exports = [
            ["Fixtures (CSV)", `/tournaments/${id}/export/fixtures.csv`],
            ["Standings (CSV)", `/tournaments/${id}/export/standings.csv`],
            ["Scorecard links (CSV)", `/tournaments/${id}/export/scorecards.csv`],
            ["Squad list (CSV)", `/tournaments/${id}/export/squads.csv`],
            ["Team records (CSV)", `/tournaments/${id}/report/team-records.csv`],
            ["Batting leaderboard (CSV)", `/tournaments/${id}/leaderboards/export?category=batting`],
            ["Bowling leaderboard (CSV)", `/tournaments/${id}/leaderboards/export?category=bowling`],
            ["Tournament summary (JSON)", `/tournaments/${id}/report`],
            ["Printable report", `/tournaments/${id}/report/print`],
        ];
        const official = record
            ? notice(record.is_frozen ? "success" : "warning", `<strong>Official record revision ${esc(record.revision)}</strong> — champion ${esc(record.snapshot?.champion_team_name || record.champion_team_id)}
                · finalized ${esc(ctx.UI.formatDateTime(record.finalized_at))}${record.is_frozen ? "" : ` · reopened: ${esc(record.reopen_reason)}`}`)
            : notice("info", "This tournament has not been finalized yet.");
        const editions = history.length
            ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Edition</th><th>Season</th><th>Status</th><th>Champion</th><th>Awards</th></tr></thead><tbody>
                ${history.map((row) => `<tr><td><a href="/competitions/${esc(row.tournament_id)}/reports">${esc(row.name)}</a></td><td>${esc(row.season || "–")}</td>
                <td>${ctx.UI.statusBadge(row.status)}</td><td>${esc(row.champion_team_name || "–")}</td>
                <td>${esc(row.awards.map((award) => `${award.title}: ${award.player_name || award.team_name || "–"}`).join("; ") || "–")}</td></tr>`).join("")}
              </tbody></table></div>`
            : `<p class="muted">Not part of a recurring series.</p>`;
        ctx.root.innerHTML = panel("Exports & reports", "Generated from official results", `<div class="action-row" style="flex-wrap:wrap">
                ${exports.map(([label, href]) => `<a class="button button-secondary button-small" href="${href}" ${href.endsWith("print") ? 'target="_blank" rel="noopener"' : ""}>${esc(label)}</a>`).join("")}
            </div>`)
            + panel("Official record", "Frozen championship snapshot (reproducible after transfers, renames and rule changes)", official)
            + panel("Historical editions", "Archived champions and awards across the series", editions);
    }


    // =========================
    // EVENTS
    // =========================

    async function handleClick(ctx, event) {
        const button = event.target.closest("button, a");
        if (!button || !ctx.root.contains(button)) {
            return false;
        }
        const data = button.dataset;
        const id = ctx.state.id;

        if (data.hubPlayer) {
            await ctx.run(null, () => showPlayer(ctx, data.hubPlayer));
            return true;
        }

        if (data.hubAction === "resolve-bracket") {
            if (await ctx.run(button, () => API.tournamentHub.resolveBracket(id), "Bracket recomputed.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubAdjudicate) {
            const group = ctx.state.hubTables.groups.find((item) => item.group_key === data.hubAdjudicate);
            const tied = group.standings.filter((row) => String(row.rank) === data.rank);
            const orders = permutations(tied).slice(0, 24);
            const reason = await ctx.ask({
                title: "Adjudicate tied placement",
                message: "Records an official placement for teams the configured tie-breakers cannot separate. It is void automatically if results change.",
                choices: orders.map((order, index) => [String(index), order.map((row) => row.team_name).join(" > ")]),
                choiceLabel: "Official order", reason: true, reasonRequired: true, confirmLabel: "Record adjudication",
            });
            if (reason) {
                const order = orders[Number(ctx.getChoice())];
                if (await ctx.run(button, () => API.tournamentHub.adjudicate(id, { group_key: group.group_key, team_ids: order.map((row) => row.team_id), reason }), "Placement adjudicated.")) {
                    await ctx.rerender();
                }
            }
            return true;
        }

        if (data.hubDispose) {
            const row = Object.values(ctx.state.hubBoard.fixtures_by_status).flat().find((item) => item.fixture_id === data.hubDispose);
            const knockout = row.stage !== "league" && row.stage !== "group";
            const options = [
                ["walkover:home", `Walkover — ${row.home_team_name} awarded`],
                ["walkover:away", `Walkover — ${row.away_team_name} awarded`],
                ["no_result", "No result"],
                ["abandoned", "Abandoned"],
                ["cancelled", "Cancelled (excluded)"],
            ];
            if (knockout) {
                options.push(["knockout_advancement:home", `${row.home_team_name} advances (tie/abandoned knockout)`]);
                options.push(["knockout_advancement:away", `${row.away_team_name} advances (tie/abandoned knockout)`]);
            }
            const reason = await ctx.ask({ title: `Fixture ${row.fixture_number} disposition`, message: "Official, audited and reversible with a reason.",
                choices: options, choiceLabel: "Outcome", reason: true, reasonRequired: true, confirmLabel: "Record" });
            if (reason) {
                const [outcome, side] = ctx.getChoice().split(":");
                const winner = side === "home" ? row.home_team_id : side === "away" ? row.away_team_id : null;
                if (await ctx.run(button, () => API.tournamentHub.disposition(id, row.fixture_id, { outcome, winner_team_id: winner, reason }), "Disposition recorded.")) {
                    await ctx.rerender();
                }
            }
            return true;
        }

        if (data.hubUndispose) {
            const reason = await ctx.ask({ title: "Revoke disposition?", reason: true, reasonRequired: true, confirmLabel: "Revoke", danger: true });
            if (reason && await ctx.run(button, () => API.tournamentHub.revokeDisposition(id, data.hubUndispose, reason), "Disposition revoked.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubAction === "add-bonus") {
            const teams = (ctx.state.memberships || []).filter((m) => m.registration_status === "approved" && !m.is_reserve);
            const reason = await ctx.ask({ title: "Award bonus points", choices: teams.map((m) => [m.team_id, m.display_name || ctx.state.teams.get(m.team_id)?.name || m.team_id]),
                choiceLabel: "Team", reason: true, reasonRequired: true, reasonLabel: "Reason (points are set to 1; repeat for more)", confirmLabel: "Add 1 point" });
            if (reason && await ctx.run(button, () => API.tournamentHub.addBonus(id, { team_id: ctx.getChoice(), points: 1, reason }), "Bonus recorded.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubUnbonus) {
            const reason = await ctx.ask({ title: "Revoke bonus?", reason: true, reasonRequired: true, confirmLabel: "Revoke", danger: true });
            if (reason && await ctx.run(button, () => API.tournamentHub.revokeBonus(id, data.hubUnbonus, reason), "Bonus revoked.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubConfirm) {
            const leader = data.leader === "1";
            const reason = await ctx.ask({
                title: `Confirm ${AWARD_TITLES[data.hubConfirm] || data.hubConfirm}`,
                message: leader ? "Confirms the unambiguous computed leader." : "Selecting anyone other than the computed leader is recorded as an organizer override; explain why.",
                reason: true, reasonRequired: true, reasonLabel: leader ? "Reason" : "Explanation", confirmLabel: "Confirm award",
            });
            if (reason && await ctx.run(button, () => API.tournamentHub.confirmAward(id, data.hubConfirm, {
                player_id: data.player, reason, basis: leader ? "statistical_leader" : "organizer_selection",
            }), "Award confirmed.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubRevoke) {
            const reason = await ctx.ask({ title: "Revoke award?", reason: true, reasonRequired: true, confirmLabel: "Revoke", danger: true });
            if (reason && await ctx.run(button, () => API.tournamentHub.revokeAward(id, data.hubRevoke, reason), "Award revoked.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubPom) {
            const board = await API.tournamentHub.leaderboards(id);
            const players = new Map();
            [...board.batting, ...board.bowling, ...board.fielding].forEach((row) => {
                if (row.teams.some((team) => [data.home, data.away].includes(team.team_id))) {
                    players.set(row.player_id, `${row.player_name} (${row.teams.map((team) => team.team_name).join(", ")})`);
                }
            });
            const reason = await ctx.ask({ title: "Player of the Match", choices: [...players.entries()], choiceLabel: "Player",
                reason: true, reasonRequired: true, confirmLabel: "Confirm" });
            if (reason && await ctx.run(button, () => API.tournamentHub.playerOfMatch(id, data.hubPom, { player_id: ctx.getChoice(), reason }), "Player of the Match confirmed.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubAction === "manual-award") {
            const code = window.prompt("Award code for this organizer award (e.g. fair_play, best_captain):");
            if (!code) {
                return true;
            }
            const teams = (ctx.state.memberships || []).filter((m) => m.registration_status === "approved" && !m.is_reserve);
            const reason = await ctx.ask({ title: `Organizer award: ${code}`, message: "Team recipient. Player awards can be confirmed from the candidate lists.",
                choices: teams.map((m) => [m.team_id, m.display_name || ctx.state.teams.get(m.team_id)?.name || m.team_id]), choiceLabel: "Team",
                reason: true, reasonRequired: true, confirmLabel: "Confirm award" });
            if (reason && await ctx.run(button, () => API.tournamentHub.confirmAward(id, code.trim().toLowerCase().replace(/\s+/g, "_"), { team_id: ctx.getChoice(), reason }), "Award confirmed.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubAction === "publish-awards" || data.hubAction === "unpublish-awards") {
            const publish = data.hubAction === "publish-awards";
            const reason = await ctx.ask({ title: publish ? "Publish and freeze awards?" : "Unpublish awards?",
                message: publish ? "Published awards are frozen and required for finalization." : "Awards become editable again and must be republished.",
                reason: true, reasonRequired: true, confirmLabel: publish ? "Publish" : "Unpublish" });
            if (reason && await ctx.run(button, () => (publish ? API.tournamentHub.publishAwards(id, reason) : API.tournamentHub.unpublishAwards(id, reason)),
                publish ? "Awards published." : "Awards unpublished.")) {
                await ctx.rerender();
            }
            return true;
        }

        if (data.hubAction === "finalize") {
            const confirmed = await ctx.ask({ title: "Finalize tournament?", message: "Freezes the official champion, standings, statistics and awards. Reopening requires a reason.", confirmLabel: "Finalize" });
            if (confirmed !== null && await ctx.run(button, () => API.tournamentHub.finalize(id), "Tournament finalized.")) {
                await ctx.refresh();
            }
            return true;
        }

        if (data.hubAction === "reopen") {
            const reason = await ctx.ask({ title: "Reopen tournament?", message: "Unfreezes the closeout and unpublishes awards. The previous snapshot stays in the decision log.",
                reason: true, reasonRequired: true, confirmLabel: "Reopen", danger: true });
            if (reason && await ctx.run(button, () => API.tournamentHub.reopen(id, reason), "Tournament reopened.")) {
                await ctx.refresh();
            }
            return true;
        }

        return false;
    }

    async function handleSubmit(ctx, event) {
        const form = event.target;
        if (form.matches("[data-hub-filters]")) {
            event.preventDefault();
            const data = new FormData(form);
            ctx.state.hubFilters = {
                team_id: data.get("team_id") || undefined,
                min_innings: data.get("min_innings") || undefined,
                min_balls: data.get("min_balls") || undefined,
                qualified_only: data.get("qualified_only") === "on",
            };
            await ctx.rerender();
            return true;
        }
        if (form.matches("[data-hub-settings]")) {
            event.preventDefault();
            const reason = await ctx.ask({ title: "Save award settings?", reason: true, reasonRequired: true, confirmLabel: "Save" });
            if (reason) {
                const settings = { ...ctx.state.hubAwards.settings, ...(await readSettings(form)) };
                if (await ctx.run(null, () => API.tournamentHub.saveAwardSettings(ctx.state.id, settings, reason), "Award settings saved.")) {
                    await ctx.rerender();
                }
            }
            return true;
        }
        return false;
    }

    window.TournamentHub = {
        sections: {
            live: renderLive,
            tables: renderTables,
            bracket: renderBracket,
            statistics: renderStatistics,
            leaderboards: renderLeaderboards,
            awards: renderAwards,
            records: renderRecords,
            operations: renderOperations,
            reports: renderReports,
        },
        handleClick,
        handleSubmit,
    };

})();
