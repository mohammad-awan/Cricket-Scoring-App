(() => {

    "use strict";


    const root =
        document.getElementById(
            "match-setup-page"
        );


    if (!root) {
        return;
    }


    const matchId = root.dataset.matchId;


    const elements = {

        pageError:
            document.getElementById(
                "page-error"
            ),

        title:
            document.getElementById(
                "match-title"
            ),

        subtitle:
            document.getElementById(
                "match-subtitle"
            ),

        statusBadge:
            document.getElementById(
                "match-status-badge"
            ),

        /*
         * Stage 4
         *
         * This anchor exists in the
         * updated match_setup.html.
         *
         * It remains hidden while the
         * match is Draft and appears
         * once the match becomes
         * Ready or Live.
         */
        openScoring:
            document.getElementById(
                "open-scoring"
            ),

        readinessList:
            document.getElementById(
                "readiness-list"
            ),

        markReady:
            document.getElementById(
                "mark-ready"
            ),

        tossSummary:
            document.getElementById(
                "toss-summary"
            ),

        tossWinnerOptions:
            document.getElementById(
                "toss-winner-options"
            ),

        tossDecisionOptions:
            document.getElementById(
                "toss-decision-options"
            ),

        saveToss:
            document.getElementById(
                "save-toss"
            ),

        playingTeamAPanel:
            document.getElementById(
                "playing-team-a-panel"
            ),

        playingTeamBPanel:
            document.getElementById(
                "playing-team-b-panel"
            ),

        openingInningsBody:
            document.getElementById(
                "opening-innings-body"
            ),

        matchDetailsBody:
            document.getElementById(
                "match-details-body"
            ),

    };


    const state = {

        match: null,

        squads: {},

        selections: {},

        /*
         * Active venues for the match
         * details editor.
         *
         * Loaded only once.
         */
        venues: null,

        /*
         * Prevents duplicate submissions
         * when requests are still running.
         */
        saving: false,

    };


    function escapeHtml(value) {

        return String(
            value ?? ""
        )
            .replaceAll(
                "&",
                "&amp;"
            )
            .replaceAll(
                "<",
                "&lt;"
            )
            .replaceAll(
                ">",
                "&gt;"
            )
            .replaceAll(
                '"',
                "&quot;"
            )
            .replaceAll(
                "'",
                "&#039;"
            );

    }


    function humanStatus(value) {

        return String(
            value || "unknown"
        )
            .replaceAll(
                "_",
                " "
            )
            .replace(
                /\b\w/g,
                (letter) =>
                    letter.toUpperCase()
            );

    }


    function showPageError(message) {

        elements.pageError.textContent =
            message;

        elements.pageError.classList.remove(
            "hidden"
        );

    }


    function clearPageError() {

        elements.pageError.classList.add(
            "hidden"
        );

        elements.pageError.textContent =
            "";

    }


    function formatOvers(match) {

        if (
            match.total_overs === null
            ||
            match.total_overs === undefined
        ) {

            return "Unlimited overs";

        }

        return (
            `${match.total_overs} overs`
            +
            " · "
            +
            `${match.balls_per_over} balls/over`
        );

    }


    function isDraft(match) {

        return (
            match.status === "draft"
        );

    }


    function initSelectionsFromMatch(
        match
    ) {

        [
            match.team_a.id,
            match.team_b.id,
        ].forEach(
            (teamId) => {

                const existing =
                    match.players

                        .filter(
                            (item) =>
                                item.team_id
                                === teamId
                        )

                        .sort(
                            (a, b) =>
                                (
                                    a.batting_order
                                    || 0
                                )
                                -
                                (
                                    b.batting_order
                                    || 0
                                )
                        );


                const captain =
                    existing.find(
                        (item) =>
                            item.is_captain
                    );


                const keeper =
                    existing.find(
                        (item) =>
                            item.is_wicket_keeper
                    );


                state.selections[
                    teamId
                ] = {

                    order:
                        existing.map(
                            (item) =>
                                item.player.id
                        ),

                    captainId:
                        captain
                            ? captain.player.id
                            : null,

                    keeperId:
                        keeper
                            ? keeper.player.id
                            : null,

                };

            }
        );

    }


    function renderHeader(match) {

        elements.title.textContent =
            match.title
            ||
            (
                `${match.team_a.short_name}`
                +
                " vs "
                +
                `${match.team_b.short_name}`
            );


        elements.subtitle.textContent =
            (
                `${humanStatus(match.match_type)}`
                +
                " · "
                +
                `${match.players_per_side} players per side`
                +
                " · "
                +
                `${formatOvers(match)}`
            );


        elements.statusBadge.textContent =
            humanStatus(
                match.status
            );


        elements.statusBadge.className =
            (
                "status-badge "
                +
                `status-${match.status}`
            );


        /*
         * =========================
         * STAGE 4
         * =========================
         *
         * Do not allow access to
         * scoring while Stage 3 is
         * incomplete.
         *
         * READY:
         * Stage 3 completed successfully.
         *
         * LIVE:
         * At least one official delivery
         * has already been recorded.
         */
        if (elements.openScoring) {

            const scoringAvailable =
                [
                    "ready",
                    "live",
                ].includes(
                    match.status
                );


            elements
                .openScoring
                .classList
                .toggle(
                    "hidden",
                    !scoringAvailable
                );

        }

    }


    function renderReadiness(match) {

        const items = [

            {
                key:
                    "details_complete",

                label:
                    "Venue and date/time set",
            },

            {
                key:
                    "toss_complete",

                label:
                    "Toss recorded",
            },

            {
                key:
                    "team_a_players_complete",

                label:
                    (
                        `${match.team_a.short_name}`
                        +
                        " playing team "
                        +
                        `(${match.players_per_side})`
                    ),
            },

            {
                key:
                    "team_b_players_complete",

                label:
                    (
                        `${match.team_b.short_name}`
                        +
                        " playing team "
                        +
                        `(${match.players_per_side})`
                    ),
            },

            {
                key:
                    "opening_innings_complete",

                label:
                    "Opening innings set",
            },

        ];


        elements.readinessList.innerHTML =
            items

                .map(
                    (item) => {

                        const done =
                            Boolean(
                                match
                                    .readiness[
                                    item.key
                                ]
                            );


                        return `
                            <li
                                class="
                                    readiness-item
                                    ${done ? "done" : ""}
                                "
                            >
                                <span
                                    class="readiness-mark"
                                >
                                    ${done ? "✓" : "•"}
                                </span>

                                <span>
                                    ${escapeHtml(item.label)}
                                </span>
                            </li>
                        `;

                    }
                )

                .join("");


        elements.markReady.disabled =
            (
                !match.readiness.ready
                ||
                match.status !== "draft"
            );


        elements.markReady.textContent =
            (
                match.status === "ready"
                ||
                (
                    match.readiness.ready
                    &&
                    match.status !== "draft"
                )
            )
                ? "Match is ready"
                : "Mark ready";

    }


    function renderToss(match) {

        const locked =
            (
                match.innings.length > 0
                ||
                !isDraft(match)
            );


        if (match.toss_winner) {

            elements.tossSummary.textContent =
                (
                    `${match.toss_winner.short_name}`
                    +
                    " won the toss and chose to "
                    +
                    `${match.toss_decision}.`
                );

        } else {

            elements.tossSummary.textContent =
                "Toss has not been recorded yet.";

        }


        elements.tossWinnerOptions.innerHTML =
            [
                match.team_a,
                match.team_b,
            ]

                .map(
                    (team) => {

                        const checked =
                            (
                                match.toss_winner
                                &&
                                match.toss_winner.id
                                === team.id
                            )
                                ? "checked"
                                : "";


                        return `
                            <label class="toss-option">

                                <input
                                    type="radio"
                                    name="toss-winner"
                                    value="${team.id}"
                                    ${checked}
                                    ${locked ? "disabled" : ""}
                                >

                                <span>
                                    ${escapeHtml(team.name)}
                                </span>

                            </label>
                        `;

                    }
                )

                .join("");


        elements
            .tossDecisionOptions
            .querySelectorAll(
                "input[name='toss-decision']"
            )
            .forEach(
                (input) => {

                    input.checked =
                        (
                            match.toss_decision
                            === input.value
                        );


                    input.disabled =
                        locked;

                }
            );


        elements.saveToss.disabled =
            locked;


        elements.saveToss.textContent =
            locked
                ? "Toss locked"
                : "Save toss";

    }


    function squadCountLabel(
        count,
        required
    ) {

        return (
            `${count} / ${required}`
            +
            " players selected"
        );

    }


    function renderPlayingTeamPanel(
        panelElement,
        match,
        team
    ) {

        const squad =
            state.squads[
                team.id
            ] || [];


        const selection =
            state.selections[
                team.id
            ]
            || {
                order: [],
                captainId: null,
                keeperId: null,
            };


        const locked =
            (
                match.innings.length > 0
                ||
                !isDraft(match)
            );


        const required =
            match.players_per_side;


        const selectedSet =
            new Set(
                selection.order
            );


        const squadRows =
            squad

                .map(
                    (entry) => {

                        const checked =
                            selectedSet.has(
                                entry.player.id
                            );


                        const position =
                            selection.order.indexOf(
                                entry.player.id
                            );


                        return `
                            <li class="squad-row">

                                <label class="checkbox-field">

                                    <input
                                        type="checkbox"
                                        data-role="squad-checkbox"
                                        data-player-id="${entry.player.id}"
                                        ${checked ? "checked" : ""}
                                        ${locked ? "disabled" : ""}
                                    >

                                    <span>
                                        ${escapeHtml(
                                            entry.player.full_name
                                        )}
                                    </span>

                                </label>


                                <span class="squad-role">
                                    ${escapeHtml(
                                        humanStatus(
                                            entry.role
                                        )
                                    )}
                                </span>


                                ${
                                    checked
                                        ? `
                                            <span class="order-badge">
                                                #${position + 1}
                                            </span>
                                        `
                                        : ""
                                }

                            </li>
                        `;

                    }
                )

                .join("");


        const orderedSelected =
            selection.order

                .map(
                    (playerId) =>
                        squad.find(
                            (entry) =>
                                entry.player.id
                                === playerId
                        )
                )

                .filter(
                    Boolean
                );


        const battingOrderRows =
            orderedSelected

                .map(
                    (
                        entry,
                        index
                    ) => `
                        <li class="batting-order-row">

                            <span class="order-badge">
                                ${index + 1}
                            </span>


                            <span>
                                ${escapeHtml(
                                    entry.player.full_name
                                )}
                            </span>


                            ${
                                locked
                                    ? ""
                                    : `
                                        <span class="batting-order-actions">

                                            <button
                                                type="button"
                                                data-role="move-up"
                                                data-player-id="${entry.player.id}"
                                                ${
                                                    index === 0
                                                        ? "disabled"
                                                        : ""
                                                }
                                            >
                                                ↑
                                            </button>


                                            <button
                                                type="button"
                                                data-role="move-down"
                                                data-player-id="${entry.player.id}"
                                                ${
                                                    index
                                                    ===
                                                    orderedSelected.length - 1
                                                        ? "disabled"
                                                        : ""
                                                }
                                            >
                                                ↓
                                            </button>

                                        </span>
                                    `
                            }

                        </li>
                    `
                )

                .join("");


        const playerOptionsHtml =
            (selectedId) => {

                return (
                    `<option value="">None</option>`
                    +
                    orderedSelected

                        .map(
                            (entry) => {

                                return `
                                    <option
                                        value="${entry.player.id}"
                                        ${
                                            entry.player.id
                                            === selectedId
                                                ? "selected"
                                                : ""
                                        }
                                    >
                                        ${escapeHtml(
                                            entry.player.full_name
                                        )}
                                    </option>
                                `;

                            }
                        )

                        .join("")
                );

            };


        const canSave =
            (
                selection.order.length
                === required
                &&
                !locked
            );


        panelElement.innerHTML = `

            <div class="panel-header">

                <div>

                    <p class="eyebrow">
                        ${
                            team === match.team_a
                                ? "Step 2a"
                                : "Step 2b"
                        }
                    </p>

                    <h2>
                        ${escapeHtml(team.name)}
                        playing team
                    </h2>

                </div>


                <span class="muted">
                    ${escapeHtml(
                        squadCountLabel(
                            selection.order.length,
                            required
                        )
                    )}
                </span>

            </div>


            <div
                class="
                    panel-body
                    playing-team-body
                "
            >

                ${
                    squad.length === 0

                        ? `
                            <p class="muted">

                                No active squad players
                                for this team yet.

                                Add at least
                                ${required}
                                players on the

                                <a href="/master-data/teams">
                                    Teams
                                </a>

                                page using the
                                <strong>Squad</strong>
                                button.

                            </p>
                        `

                        : `
                            <div class="playing-team-columns">

                                <div>

                                    <p class="panel-subtitle">
                                        Active squad
                                    </p>

                                    <ul class="squad-list">
                                        ${squadRows}
                                    </ul>

                                </div>


                                <div>

                                    <p class="panel-subtitle">
                                        Batting order
                                    </p>


                                    <ul class="batting-order-list">

                                        ${
                                            battingOrderRows
                                            ||
                                            `
                                                <li class="muted">
                                                    No players
                                                    selected yet.
                                                </li>
                                            `
                                        }

                                    </ul>


                                    <label class="form-field">

                                        <span>
                                            Captain
                                        </span>

                                        <select
                                            data-role="captain-select"
                                            ${locked ? "disabled" : ""}
                                        >
                                            ${
                                                playerOptionsHtml(
                                                    selection.captainId
                                                )
                                            }
                                        </select>

                                    </label>


                                    <label class="form-field">

                                        <span>
                                            Wicket-keeper
                                        </span>

                                        <select
                                            data-role="keeper-select"
                                            ${locked ? "disabled" : ""}
                                        >
                                            ${
                                                playerOptionsHtml(
                                                    selection.keeperId
                                                )
                                            }
                                        </select>

                                    </label>

                                </div>

                            </div>


                            <button
                                class="
                                    button
                                    button-primary
                                    button-small
                                "
                                data-role="save-playing-team"
                                type="button"
                                ${canSave ? "" : "disabled"}
                            >
                                Save playing team
                            </button>
                        `
                }

            </div>
        `;


        panelElement.dataset.teamId =
            team.id;

    }


    function battingBowlingTeamIds(
        match
    ) {

        if (
            !match.toss_winner
            ||
            !match.toss_decision
        ) {

            return null;

        }


        const otherTeamId =
            (
                match.toss_winner.id
                === match.team_a.id
            )
                ? match.team_b.id
                : match.team_a.id;


        return (
            match.toss_decision === "bat"
        )
            ? {
                battingId:
                    match.toss_winner.id,

                bowlingId:
                    otherTeamId,
            }
            : {
                battingId:
                    otherTeamId,

                bowlingId:
                    match.toss_winner.id,
            };

    }


    function renderOpeningInnings(
        match
    ) {

        const readyForInnings =
            (
                match
                    .readiness
                    .toss_complete

                &&

                match
                    .readiness
                    .team_a_players_complete

                &&

                match
                    .readiness
                    .team_b_players_complete
            );


        if (!readyForInnings) {

            elements.openingInningsBody.innerHTML =
                `
                    <p class="muted">
                        Complete the toss and
                        both playing teams first.
                    </p>
                `;


            return;

        }


        const teamIds =
            battingBowlingTeamIds(
                match
            );


        if (!teamIds) {
            return;
        }


        const battingTeam =
            (
                match.team_a.id
                === teamIds.battingId
            )
                ? match.team_a
                : match.team_b;


        const bowlingTeam =
            (
                match.team_a.id
                === teamIds.bowlingId
            )
                ? match.team_a
                : match.team_b;


        const battingPlayers =
            match.players.filter(
                (item) =>
                    item.team_id
                    === teamIds.battingId
            );


        const bowlingPlayers =
            match.players.filter(
                (item) =>
                    item.team_id
                    === teamIds.bowlingId
            );


        const firstInnings =
            match.innings.find(
                (item) =>
                    item.innings_number
                    === 1
            );


        const locked =
            !isDraft(match);


        const battingOptions =
            (selectedId) => {

                return (
                    `<option value="">Select player</option>`
                    +
                    battingPlayers

                        .map(
                            (item) => {

                                return `
                                    <option
                                        value="${item.player.id}"
                                        ${
                                            item.player.id
                                            === selectedId
                                                ? "selected"
                                                : ""
                                        }
                                    >
                                        ${escapeHtml(
                                            item.player.full_name
                                        )}
                                    </option>
                                `;

                            }
                        )

                        .join("")
                );

            };


        const bowlingOptions =
            (selectedId) => {

                return (
                    `<option value="">Select player</option>`
                    +
                    bowlingPlayers

                        .map(
                            (item) => {

                                return `
                                    <option
                                        value="${item.player.id}"
                                        ${
                                            item.player.id
                                            === selectedId
                                                ? "selected"
                                                : ""
                                        }
                                    >
                                        ${escapeHtml(
                                            item.player.full_name
                                        )}
                                    </option>
                                `;

                            }
                        )

                        .join("")
                );

            };


        elements.openingInningsBody.innerHTML =
            `
                <p class="muted">

                    ${escapeHtml(battingTeam.name)}
                    bat first,

                    ${escapeHtml(bowlingTeam.name)}
                    bowl first.

                </p>


                <div class="form-grid">


                    <label class="form-field">

                        <span>
                            Striker
                        </span>

                        <select
                            data-role="striker-select"
                            ${locked ? "disabled" : ""}
                        >
                            ${
                                battingOptions(
                                    firstInnings
                                        ? (
                                            firstInnings.striker
                                            &&
                                            firstInnings.striker.id
                                        )
                                        : null
                                )
                            }
                        </select>

                    </label>


                    <label class="form-field">

                        <span>
                            Non-striker
                        </span>

                        <select
                            data-role="non-striker-select"
                            ${locked ? "disabled" : ""}
                        >
                            ${
                                battingOptions(
                                    firstInnings
                                        ? (
                                            firstInnings.non_striker
                                            &&
                                            firstInnings.non_striker.id
                                        )
                                        : null
                                )
                            }
                        </select>

                    </label>


                    <label class="form-field">

                        <span>
                            Opening bowler
                        </span>

                        <select
                            data-role="bowler-select"
                            ${locked ? "disabled" : ""}
                        >
                            ${
                                bowlingOptions(
                                    firstInnings
                                        ? (
                                            firstInnings.current_bowler
                                            &&
                                            firstInnings.current_bowler.id
                                        )
                                        : null
                                )
                            }
                        </select>

                    </label>


                </div>


                <button
                    class="
                        button
                        button-primary
                        button-small
                    "
                    data-role="save-opening-innings"
                    type="button"
                    ${locked ? "disabled" : ""}
                >
                    Save opening innings
                </button>
            `;

    }


    function toDateTimeLocal(
        isoValue
    ) {

        if (!isoValue) {
            return "";
        }


        const date =
            new Date(
                isoValue
            );


        const local =
            new Date(
                date.getTime()
                -
                date.getTimezoneOffset()
                * 60000
            );


        return local
            .toISOString()
            .slice(
                0,
                16
            );

    }


    function renderMatchDetails(
        match
    ) {

        const locked =
            !isDraft(match);


        const venues =
            state.venues || [];


        /*
         * Keep the current venue
         * selectable even if it has
         * since become inactive.
         */
        const venueOptions = [
            ...venues,
        ];


        if (
            match.venue
            &&
            !venues.some(
                (venue) =>
                    venue.id
                    === match.venue.id
            )
        ) {

            venueOptions.unshift(
                match.venue
            );

        }


        elements.matchDetailsBody.innerHTML =
            `
                <div class="form-grid">


                    <label class="form-field">

                        <span>
                            Venue
                        </span>

                        <select
                            data-role="details-venue"
                            ${locked ? "disabled" : ""}
                        >

                            <option value="">
                                No venue yet
                            </option>

                            ${
                                venueOptions

                                    .map(
                                        (venue) => {

                                            const selected =
                                                (
                                                    match.venue
                                                    &&
                                                    match.venue.id
                                                    === venue.id
                                                )
                                                    ? "selected"
                                                    : "";


                                            const city =
                                                venue.city
                                                    ? (
                                                        " · "
                                                        +
                                                        escapeHtml(
                                                            venue.city
                                                        )
                                                    )
                                                    : "";


                                            return `
                                                <option
                                                    value="${venue.id}"
                                                    ${selected}
                                                >
                                                    ${escapeHtml(
                                                        venue.name
                                                    )}${city}
                                                </option>
                                            `;

                                        }
                                    )

                                    .join("")
                            }

                        </select>

                    </label>


                    <label class="form-field">

                        <span>
                            Date &amp; time
                        </span>

                        <input
                            type="datetime-local"
                            data-role="details-scheduled"
                            value="${toDateTimeLocal(match.scheduled_at)}"
                            ${locked ? "disabled" : ""}
                        >

                    </label>


                    <label class="form-field">

                        <span>
                            Overs per innings
                            <em>
                                (blank = unlimited)
                            </em>
                        </span>

                        <input
                            type="number"
                            min="1"
                            data-role="details-overs"
                            value="${match.total_overs ?? ""}"
                            ${locked ? "disabled" : ""}
                        >

                    </label>


                </div>


                <button
                    class="
                        button
                        button-primary
                        button-small
                    "
                    data-role="save-details"
                    type="button"
                    ${locked ? "disabled" : ""}
                >
                    ${
                        locked
                            ? "Details locked"
                            : "Save details"
                    }
                </button>
            `;

    }


    function renderAll() {

        const match =
            state.match;


        renderHeader(
            match
        );


        renderReadiness(
            match
        );


        renderMatchDetails(
            match
        );


        renderToss(
            match
        );


        renderPlayingTeamPanel(
            elements.playingTeamAPanel,
            match,
            match.team_a
        );


        renderPlayingTeamPanel(
            elements.playingTeamBPanel,
            match,
            match.team_b
        );


        renderOpeningInnings(
            match
        );

    }


    async function loadSquads(
        match
    ) {

        const [
            squadA,
            squadB,
        ] = await Promise.all(
            [

                window.API.matchSquad(
                    matchId,
                    match.team_a.id
                ),

                window.API.matchSquad(
                    matchId,
                    match.team_b.id
                ),

            ]
        );


        state.squads[
            match.team_a.id
        ] = squadA;


        state.squads[
            match.team_b.id
        ] = squadB;

    }


    async function loadVenues() {

        try {

            const venues =
                await window.API.listAll(
                    "venues"
                );


            state.venues =
                venues.filter(
                    (item) =>
                        (
                            item.status
                            === "active"
                        )
                        &&
                        !item.archived_at
                );

        } catch (error) {

            state.venues = [];

        }

    }


    /*
     * Ignore further clicks until
     * the current save finishes.
     *
     * This prevents a slow request
     * from submitting the same setup
     * operation more than once.
     */
    async function whileSaving(
        action
    ) {

        if (state.saving) {
            return;
        }


        state.saving = true;


        root.classList.add(
            "is-saving"
        );


        try {

            await action();

        } finally {

            state.saving = false;


            root.classList.remove(
                "is-saving"
            );

        }

    }


    /*
     * Setup save endpoints return the
     * complete match object.
     *
     * We therefore render directly
     * from the response instead of
     * performing another GET.
     */
    function applyMatch(
        match,
        {
            preserveSelections = false,
        } = {}
    ) {

        state.match =
            match;


        if (!preserveSelections) {

            initSelectionsFromMatch(
                match
            );

        }


        renderAll();

    }


    async function loadMatch(
        {
            preserveSelections = false,
        } = {}
    ) {

        clearPageError();


        try {

            const match =
                await window.API.matchGet(
                    matchId
                );


            state.match =
                match;


            await Promise.all(
                [

                    loadSquads(
                        match
                    ),

                    state.venues === null
                        ? loadVenues()
                        : Promise.resolve(),

                ]
            );


            if (!preserveSelections) {

                initSelectionsFromMatch(
                    match
                );

            }


            renderAll();

        } catch (error) {

            showPageError(
                error.message
                ||
                "Could not load match setup."
            );

        }

    }


    function toggleSquadSelection(
        teamId,
        playerId
    ) {

        const selection =
            state.selections[
                teamId
            ];


        const index =
            selection.order.indexOf(
                playerId
            );


        if (index === -1) {

            const required =
                state
                    .match
                    .players_per_side;


            if (
                selection.order.length
                >= required
            ) {

                window.showToast(
                    (
                        `Only ${required}`
                        +
                        " players can be selected "
                        +
                        "for this team."
                    ),
                    "error"
                );


                return;

            }


            selection.order.push(
                playerId
            );

        } else {

            selection.order.splice(
                index,
                1
            );


            if (
                selection.captainId
                === playerId
            ) {

                selection.captainId =
                    null;

            }


            if (
                selection.keeperId
                === playerId
            ) {

                selection.keeperId =
                    null;

            }

        }

    }


    function moveSelection(
        teamId,
        playerId,
        direction
    ) {

        const selection =
            state.selections[
                teamId
            ];


        const index =
            selection.order.indexOf(
                playerId
            );


        const swapWith =
            index + direction;


        if (
            index === -1
            ||
            swapWith < 0
            ||
            swapWith
            >= selection.order.length
        ) {

            return;

        }


        [
            selection.order[index],
            selection.order[swapWith],

        ] = [

            selection.order[swapWith],
            selection.order[index],

        ];

    }


    async function savePlayingTeam(
        teamId
    ) {

        const selection =
            state.selections[
                teamId
            ];


        const players =
            selection.order.map(
                (
                    playerId,
                    index
                ) => ({

                    player_id:
                        playerId,

                    batting_order:
                        index + 1,

                    is_captain:
                        (
                            playerId
                            === selection.captainId
                        ),

                    is_wicket_keeper:
                        (
                            playerId
                            === selection.keeperId
                        ),

                })
            );


        try {

            const updated =
                await window.API
                    .matchSetPlayingTeam(
                        matchId,
                        teamId,
                        {
                            players,
                        }
                    );


            window.showToast(
                "Playing team saved."
            );


            applyMatch(
                updated
            );

        } catch (error) {

            window.showToast(
                error.message
                ||
                "Playing team could not be saved.",
                "error"
            );

        }

    }


    async function saveMatchDetails() {

        const body =
            elements.matchDetailsBody;


        const venueElement =
            body.querySelector(
                "[data-role='details-venue']"
            );


        const scheduledElement =
            body.querySelector(
                "[data-role='details-scheduled']"
            );


        const oversElement =
            body.querySelector(
                "[data-role='details-overs']"
            );


        if (
            !venueElement
            ||
            !scheduledElement
            ||
            !oversElement
        ) {

            return;

        }


        const venueId =
            venueElement.value;


        const scheduled =
            scheduledElement.value;


        const overs =
            oversElement.value;


        try {

            const updated =
                await window.API
                    .matchUpdate(
                        matchId,
                        {

                            venue_id:
                                venueId || null,

                            scheduled_at:
                                scheduled
                                    ? new Date(
                                        scheduled
                                    ).toISOString()
                                    : null,

                            total_overs:
                                overs
                                    ? Number(
                                        overs
                                    )
                                    : null,

                        }
                    );


            window.showToast(
                "Match details saved."
            );


            applyMatch(
                updated,
                {
                    preserveSelections:
                        true,
                }
            );

        } catch (error) {

            window.showToast(
                error.message
                ||
                "Match details could not be saved.",
                "error"
            );

        }

    }


    async function saveToss() {

        const winnerInput =
            elements
                .tossWinnerOptions
                .querySelector(
                    "input[name='toss-winner']:checked"
                );


        const decisionInput =
            elements
                .tossDecisionOptions
                .querySelector(
                    "input[name='toss-decision']:checked"
                );


        if (
            !winnerInput
            ||
            !decisionInput
        ) {

            window.showToast(
                "Select the toss winner and decision.",
                "error"
            );


            return;

        }


        try {

            const updated =
                await window.API
                    .matchSetToss(
                        matchId,
                        {

                            winner_team_id:
                                winnerInput.value,

                            decision:
                                decisionInput.value,

                        }
                    );


            window.showToast(
                "Toss saved."
            );


            applyMatch(
                updated
            );

        } catch (error) {

            window.showToast(
                error.message
                ||
                "Toss could not be saved.",
                "error"
            );

        }

    }


    async function saveOpeningInnings() {

        const strikerSelect =
            elements
                .openingInningsBody
                .querySelector(
                    "[data-role='striker-select']"
                );


        const nonStrikerSelect =
            elements
                .openingInningsBody
                .querySelector(
                    "[data-role='non-striker-select']"
                );


        const bowlerSelect =
            elements
                .openingInningsBody
                .querySelector(
                    "[data-role='bowler-select']"
                );


        if (
            !strikerSelect
            ||
            !nonStrikerSelect
            ||
            !bowlerSelect
        ) {

            return;

        }


        if (
            !strikerSelect.value
            ||
            !nonStrikerSelect.value
            ||
            !bowlerSelect.value
        ) {

            window.showToast(
                (
                    "Select the striker, "
                    +
                    "non-striker and "
                    +
                    "opening bowler."
                ),
                "error"
            );


            return;

        }


        if (
            strikerSelect.value
            === nonStrikerSelect.value
        ) {

            window.showToast(
                (
                    "Striker and non-striker "
                    +
                    "must be different players."
                ),
                "error"
            );


            return;

        }


        try {

            const updated =
                await window.API
                    .matchSetupInnings(
                        matchId,
                        {

                            striker_id:
                                strikerSelect.value,

                            non_striker_id:
                                nonStrikerSelect.value,

                            opening_bowler_id:
                                bowlerSelect.value,

                        }
                    );


            window.showToast(
                "Opening innings saved."
            );


            applyMatch(
                updated
            );

        } catch (error) {

            window.showToast(
                error.message
                ||
                "Opening innings could not be saved.",
                "error"
            );

        }

    }


    async function markReady() {

        try {

            const updated =
                await window.API
                    .matchMarkReady(
                        matchId
                    );


            window.showToast(
                "Match is ready."
            );


            /*
             * applyMatch() invokes
             * renderHeader().
             *
             * Since the returned match
             * now has status = ready,
             * renderHeader() immediately
             * reveals the Stage 4
             * Open scoring button.
             */
            applyMatch(
                updated
            );

        } catch (error) {

            window.showToast(
                error.message
                ||
                "Match could not be marked ready.",
                "error"
            );

        }

    }


    /*
     * =========================
     * MAIN BUTTON EVENTS
     * =========================
     */

    elements
        .saveToss
        .addEventListener(
            "click",
            () =>
                whileSaving(
                    saveToss
                )
        );


    elements
        .markReady
        .addEventListener(
            "click",
            () =>
                whileSaving(
                    markReady
                )
        );


    function attachPlayingTeamPanelEvents(
        panelElement
    ) {

        panelElement.addEventListener(
            "change",
            (event) => {

                const teamId =
                    panelElement
                        .dataset
                        .teamId;


                const checkbox =
                    event.target.closest(
                        "[data-role='squad-checkbox']"
                    );


                if (checkbox) {

                    toggleSquadSelection(
                        teamId,
                        checkbox
                            .dataset
                            .playerId
                    );


                    renderPlayingTeamPanel(
                        panelElement,

                        state.match,

                        state.match.team_a.id
                        === teamId
                            ? state.match.team_a
                            : state.match.team_b
                    );


                    return;

                }


                const captainSelect =
                    event.target.closest(
                        "[data-role='captain-select']"
                    );


                if (captainSelect) {

                    state
                        .selections[
                            teamId
                        ]
                        .captainId =
                        (
                            captainSelect.value
                            || null
                        );


                    return;

                }


                const keeperSelect =
                    event.target.closest(
                        "[data-role='keeper-select']"
                    );


                if (keeperSelect) {

                    state
                        .selections[
                            teamId
                        ]
                        .keeperId =
                        (
                            keeperSelect.value
                            || null
                        );

                }

            }
        );


        panelElement.addEventListener(
            "click",
            (event) => {

                const teamId =
                    panelElement
                        .dataset
                        .teamId;


                const moveUp =
                    event.target.closest(
                        "[data-role='move-up']"
                    );


                const moveDown =
                    event.target.closest(
                        "[data-role='move-down']"
                    );


                const save =
                    event.target.closest(
                        "[data-role='save-playing-team']"
                    );


                if (moveUp) {

                    moveSelection(
                        teamId,
                        moveUp
                            .dataset
                            .playerId,
                        -1
                    );


                    renderPlayingTeamPanel(
                        panelElement,

                        state.match,

                        state.match.team_a.id
                        === teamId
                            ? state.match.team_a
                            : state.match.team_b
                    );


                } else if (moveDown) {

                    moveSelection(
                        teamId,
                        moveDown
                            .dataset
                            .playerId,
                        1
                    );


                    renderPlayingTeamPanel(
                        panelElement,

                        state.match,

                        state.match.team_a.id
                        === teamId
                            ? state.match.team_a
                            : state.match.team_b
                    );


                } else if (save) {

                    whileSaving(
                        () =>
                            savePlayingTeam(
                                teamId
                            )
                    );

                }

            }
        );

    }


    attachPlayingTeamPanelEvents(
        elements.playingTeamAPanel
    );


    attachPlayingTeamPanelEvents(
        elements.playingTeamBPanel
    );


    elements
        .matchDetailsBody
        .addEventListener(
            "click",
            (event) => {

                if (
                    event.target.closest(
                        "[data-role='save-details']"
                    )
                ) {

                    whileSaving(
                        saveMatchDetails
                    );

                }

            }
        );


    elements
        .openingInningsBody
        .addEventListener(
            "click",
            (event) => {

                if (
                    event.target.closest(
                        "[data-role='save-opening-innings']"
                    )
                ) {

                    whileSaving(
                        saveOpeningInnings
                    );

                }

            }
        );


    /*
     * Initial Stage 3 setup load.
     *
     * If this match is already READY
     * or LIVE, renderHeader() will also
     * expose the Stage 4 scoring button.
     */
    loadMatch();

})();