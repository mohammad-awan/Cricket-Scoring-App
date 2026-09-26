(() => {

    "use strict";


    const root =
        document.getElementById(
            "live-scoring-page"
        );


    if (!root) {
        return;
    }


    const matchId =
        root.dataset.matchId;


    const elements = {

        error:
            document.getElementById(
                "scoring-error"
            ),

        title:
            document.getElementById(
                "scoring-title"
            ),

        subtitle:
            document.getElementById(
                "scoring-subtitle"
            ),

        status:
            document.getElementById(
                "scoring-status"
            ),

        battingTeam:
            document.getElementById(
                "batting-team-label"
            ),

        runs:
            document.getElementById(
                "score-runs"
            ),

        wickets:
            document.getElementById(
                "score-wickets"
            ),

        overs:
            document.getElementById(
                "score-overs"
            ),

        crr:
            document.getElementById(
                "score-crr"
            ),

        nextBall:
            document.getElementById(
                "next-ball"
            ),

        sequence:
            document.getElementById(
                "next-sequence"
            ),

        striker:
            document.getElementById(
                "current-striker"
            ),

        nonStriker:
            document.getElementById(
                "current-non-striker"
            ),

        bowler:
            document.getElementById(
                "current-bowler"
            ),

        runControls:
            document.getElementById(
                "run-controls"
            ),

        lockNote:
            document.getElementById(
                "scoring-lock-note"
            ),

        nextBowler:
            document.getElementById(
                "next-bowler-select"
            ),

        saveBowler:
            document.getElementById(
                "save-bowler"
            ),

        bowlerHelp:
            document.getElementById(
                "bowler-help"
            ),

        recentBalls:
            document.getElementById(
                "recent-balls"
            ),

        cacheStatus:
            document.getElementById(
                "cache-status"
            ),

        resultBanner:
            document.getElementById(
                "result-banner"
            ),

        chase:
            document.getElementById(
                "score-chase"
            ),

        inningsHistory:
            document.getElementById(
                "innings-history"
            ),

        endInnings:
            document.getElementById(
                "end-innings"
            ),

        bowlerPanel:
            document.getElementById(
                "bowler-panel"
            ),

        nextInningsPanel:
            document.getElementById(
                "next-innings-panel"
            ),

        nextInningsTitle:
            document.getElementById(
                "next-innings-title"
            ),

        nextStriker:
            document.getElementById(
                "next-striker"
            ),

        nextNonStriker:
            document.getElementById(
                "next-non-striker"
            ),

        nextOpeningBowler:
            document.getElementById(
                "next-opening-bowler"
            ),

        startNextInnings:
            document.getElementById(
                "start-next-innings"
            ),
    };


    const state = {

        scoring: null,

        match: null,

        busy: false,

        // Innings number the break form
        // was last populated for, so a
        // re-render keeps the selections.
        nextInningsFor: null,
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


    function playerName(player) {

        return (
            player?.short_name
            || player?.full_name
            || "—"
        );

    }


    function showError(message) {

        elements.error.textContent =
            message;

        elements.error.classList.remove(
            "hidden"
        );

    }


    function clearError() {

        elements.error.textContent =
            "";

        elements.error.classList.add(
            "hidden"
        );

    }


    function setBusy(value) {

        state.busy = value;

        root.classList.toggle(
            "is-saving",
            value
        );


        elements
            .runControls
            .querySelectorAll(
                "button"
            )
            .forEach(
                (button) => {

                    button.disabled =
                        value
                        || scoringLocked(
                            state.scoring
                        );

                }
            );


        elements
            .startNextInnings
            .disabled =
            value;


        elements
            .endInnings
            .disabled =
            value;


        if (!value) {
            renderBowlerControl();
        }

    }


    // No ball can be recorded once the
    // innings is over, or until a new
    // bowler replaces last over's bowler.
    function scoringLocked(scoring) {

        if (!scoring) {
            return true;
        }


        return (
            scoring.innings_complete
            || scoring.bowler_change_required
            || scoring.match_status
                === "completed"
        );

    }


    function bowlingPlayers() {

        if (!state.scoring) {
            return [];
        }


        return teamPlayers(
            state
                .scoring
                .bowling_team
                .id
        );

    }


    function teamPlayers(teamId) {

        if (!state.match) {
            return [];
        }


        return state
            .match
            .players
            .filter(
                (item) =>
                    item.team_id
                    === teamId
            )
            .sort(
                (a, b) =>
                    (
                        a.batting_order
                        || 999
                    )
                    -
                    (
                        b.batting_order
                        || 999
                    )
            );

    }


    function renderRecentDeliveries(
        scoring
    ) {

        if (
            !scoring
                .recent_deliveries
                .length
        ) {

            elements
                .recentBalls
                .innerHTML =
                `
                <span class="muted">
                    No deliveries yet.
                </span>
                `;

            return;
        }


        elements
            .recentBalls
            .innerHTML = scoring
            .recent_deliveries
            .map(
                (delivery) => `
                    <div
                        class="
                            recent-ball-chip
                        "
                    >
                        <small>
                            ${delivery.over_number}.${delivery.ball_number}
                        </small>

                        <strong>
                            ${delivery.total_runs}
                        </strong>
                    </div>
                `
            )
            .join("");

    }


    function renderBowlerControl() {

        const scoring =
            state.scoring;


        if (!scoring) {
            return;
        }


        const canChange =
            scoring.at_over_boundary
            && !scoring.innings_complete
            && !state.busy;


        elements
            .bowlerPanel
            .classList
            .toggle(
                "bowler-required",
                scoring.bowler_change_required
            );


        // Last over's bowler cannot bowl
        // the next over, so leave them out.
        const players =
            bowlingPlayers()
                .filter(
                    (item) =>
                        item.player.id
                        !== scoring
                            .previous_over_bowler_id
                );


        if (canChange) {

            // Pre-select only a bowler the
            // scorer has already chosen for
            // this over; never last over's.
            const selectedId =
                scoring.bowler_change_required
                    ? ""
                    : scoring.current_bowler.id;


            elements
                .nextBowler
                .innerHTML =
                `
                <option value="">
                    Select next bowler
                </option>
                `
                +
                players
                    .map(
                        (item) => `
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
                        `
                    )
                    .join("");


            elements
                .nextBowler
                .disabled =
                false;


            elements
                .saveBowler
                .disabled =
                false;


            elements
                .bowlerHelp
                .textContent =
                scoring.bowler_change_required
                    ? (
                        "Over complete. "
                        + `${playerName(scoring.current_bowler)} `
                        + "bowled it, so select "
                        + "a different bowler "
                        + "to continue."
                    )
                    : (
                        `${playerName(scoring.current_bowler)} `
                        + "will bowl the next over. "
                        + "You can still change "
                        + "before the first ball."
                    );


            return;
        }


        elements
            .nextBowler
            .innerHTML =
            `
            <option
                value="${scoring.current_bowler.id}"
            >
                ${escapeHtml(
                    playerName(
                        scoring
                            .current_bowler
                    )
                )}
            </option>
            `;


        elements
            .nextBowler
            .disabled =
            true;


        elements
            .saveBowler
            .disabled =
            true;


        elements
            .bowlerHelp
            .textContent =
            scoring.innings_complete
                ? (
                    "Innings complete."
                )
                : (
                    "Bowler can only "
                    + "be changed "
                    + "between overs."
                );

    }


    function ordinal(value) {

        const suffix =
            { 1: "st", 2: "nd", 3: "rd" }[value]
            || "th";


        return `${value}${suffix}`;

    }


    function renderInningsContext(
        scoring
    ) {

        const summary =
            scoring.result_summary;


        elements
            .resultBanner
            .textContent =
            summary
                ? `Result: ${summary}`
                : "";


        elements
            .resultBanner
            .classList
            .toggle(
                "hidden",
                !summary
            );


        let chase = "";

        if (
            scoring.target !== null
            && !scoring.innings_complete
        ) {

            chase =
                `Target ${scoring.target}`
                + ` · need ${scoring.runs_required}`;


            if (
                scoring.balls_remaining
                !== null
            ) {

                chase +=
                    ` from ${scoring.balls_remaining}`
                    + ` ball${
                        scoring.balls_remaining === 1
                            ? ""
                            : "s"
                    }`;

            }

        }
        else if (
            scoring.target !== null
        ) {

            chase =
                `Target ${scoring.target}`;

        }


        elements.chase.textContent =
            chase;


        elements
            .chase
            .classList
            .toggle(
                "hidden",
                !chase
            );


        const previous =
            scoring
                .innings
                .filter(
                    (item) =>
                        item.innings_number
                        !== scoring.innings_number
                )
                .map(
                    (item) =>
                        `${ordinal(item.innings_number)} inns: `
                        + `${item.batting_team.short_name} `
                        + `${item.total_runs}/${item.wickets}`
                        + ` (${item.overs})`
                )
                .join(" · ");


        elements
            .inningsHistory
            .textContent =
            previous;


        elements
            .inningsHistory
            .classList
            .toggle(
                "hidden",
                !previous
            );


        elements
            .endInnings
            .classList
            .toggle(
                "hidden",
                !scoring.can_end_innings
            );


        renderNextInnings(
            scoring
        );

    }


    function playerOptions(
        players,
        placeholder
    ) {

        return (
            `<option value="">${placeholder}</option>`
            +
            players
                .map(
                    (item) => `
                        <option value="${item.player.id}">
                            ${escapeHtml(
                                item.player.full_name
                            )}
                        </option>
                    `
                )
                .join("")
        );

    }


    function renderNextInnings(
        scoring
    ) {

        const show =
            scoring.can_start_next_innings;


        elements
            .nextInningsPanel
            .classList
            .toggle(
                "hidden",
                !show
            );


        if (!show) {

            state.nextInningsFor =
                null;

            return;
        }


        elements
            .nextInningsTitle
            .textContent =
            `Start ${ordinal(scoring.next_innings_number)} innings · `
            + `${scoring.next_batting_team.name} batting`;


        if (
            state.nextInningsFor
            === scoring.next_innings_number
        ) {
            return;
        }


        const batters =
            teamPlayers(
                scoring
                    .next_batting_team
                    .id
            );


        const bowlers =
            teamPlayers(
                scoring
                    .next_bowling_team
                    .id
            );


        elements
            .nextStriker
            .innerHTML =
            playerOptions(
                batters,
                "Select striker"
            );


        elements
            .nextNonStriker
            .innerHTML =
            playerOptions(
                batters,
                "Select non-striker"
            );


        elements
            .nextOpeningBowler
            .innerHTML =
            playerOptions(
                bowlers,
                "Select opening bowler"
            );


        state.nextInningsFor =
            scoring.next_innings_number;

    }


    function render(scoring) {

        state.scoring =
            scoring;


        const matchTitle =
            state.match?.title
            ||
            (
                `${state.match?.team_a?.short_name || ""}`
                +
                " vs "
                +
                `${state.match?.team_b?.short_name || ""}`
            );


        elements.title.textContent =
            matchTitle
            || "Live Scoring Console";


        elements.subtitle.textContent =
            `${scoring.batting_team.short_name} batting`
            +
            " · "
            +
            `${scoring.bowling_team.short_name} bowling`
            +
            " · "
            +
            `${scoring.balls_per_over} balls/over`;


        elements.status.textContent =
            humanStatus(
                scoring.match_status
            );


        elements.status.className =
            `status-badge status-${scoring.match_status}`;


        elements
            .battingTeam
            .textContent =
            `${ordinal(scoring.innings_number)} innings · `
            + scoring
                .batting_team
                .name;


        elements.runs.textContent =
            scoring.total_runs;


        elements.wickets.textContent =
            scoring.wickets;


        elements.overs.textContent =
            scoring.overs;


        elements.crr.textContent =
            Number(
                scoring.current_run_rate
            )
            .toFixed(2);


        elements
            .nextBall
            .textContent =
            scoring.innings_complete
                ? "—"
                : `${scoring.next_over_number}.${scoring.next_ball_number}`;


        elements
            .sequence
            .textContent =
            scoring.next_sequence;


        elements
            .striker
            .textContent =
            `${
                playerName(
                    scoring.striker
                )
            } *`;


        elements
            .nonStriker
            .textContent =
            playerName(
                scoring.non_striker
            );


        elements
            .bowler
            .textContent =
            playerName(
                scoring.current_bowler
            );


        elements
            .cacheStatus
            .textContent =
            scoring
                .cache_matches_history
                ? "History = cache"
                : "History rebuilt";


        elements
            .cacheStatus
            .className =
            scoring
                .cache_matches_history
                ? (
                    "cache-pill "
                    + "cache-ok"
                )
                : (
                    "cache-pill "
                    + "cache-warning"
                );


        let lockNote =
            "Each run button "
            + "creates one legal "
            + "delivery in one "
            + "backend transaction.";

        if (
            scoring.match_status
            === "completed"
        ) {
            lockNote =
                "The match is complete.";
        }
        else if (
            scoring.innings_complete
        ) {
            lockNote =
                scoring.can_start_next_innings
                    ? (
                        "Innings complete. "
                        + "Set the openers below "
                        + "to start the next innings."
                    )
                    : "Innings complete.";
        }
        else if (
            scoring.bowler_change_required
        ) {
            lockNote =
                "Over complete. Set the "
                + "next bowler before "
                + "recording the next ball.";
        }


        elements
            .lockNote
            .textContent =
            lockNote;


        renderRecentDeliveries(
            scoring
        );


        renderBowlerControl();


        renderInningsContext(
            scoring
        );


        elements
            .runControls
            .querySelectorAll(
                "button"
            )
            .forEach(
                (button) => {

                    button.disabled =
                        state.busy
                        || scoringLocked(
                            scoring
                        );

                }
            );

    }


    async function load() {

        clearError();


        try {

            const [
                match,
                scoring,
            ] = await Promise.all(
                [
                    window.API
                        .matchGet(
                            matchId
                        ),

                    window.API
                        .scoringGet(
                            matchId
                        ),
                ]
            );


            state.match =
                match;


            render(
                scoring
            );

        }
        catch (error) {

            showError(
                error.message
                ||
                "Could not load "
                + "scoring state."
            );

        }

    }


    async function recordRuns(
        runs
    ) {

        if (state.busy) {
            return;
        }


        clearError();

        setBusy(
            true
        );


        try {

            const scoring =
                await window.API
                    .scoringRecord(
                        matchId,
                        {
                            runs:
                                runs,
                        }
                    );


            render(
                scoring
            );


            window.showToast(
                `${runs} run${
                    runs === 1
                        ? ""
                        : "s"
                } recorded.`
            );

        }
        catch (error) {

            showError(
                error.message
                ||
                "Delivery could "
                + "not be recorded."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    async function saveBowler() {

        if (state.busy) {
            return;
        }


        const bowlerId =
            elements
                .nextBowler
                .value;


        if (!bowlerId) {

            showError(
                "Select a bowler first."
            );

            return;
        }


        clearError();

        setBusy(
            true
        );


        try {

            const scoring =
                await window.API
                    .scoringChangeBowler(
                        matchId,
                        {
                            bowler_id:
                                bowlerId,
                        }
                    );


            render(
                scoring
            );


            window.showToast(
                "Bowler updated."
            );

        }
        catch (error) {

            showError(
                error.message
                ||
                "Bowler could not "
                + "be changed."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    async function endInnings() {

        if (state.busy) {
            return;
        }


        if (
            !window.confirm(
                "End this innings now? "
                + "This cannot be undone."
            )
        ) {
            return;
        }


        clearError();

        setBusy(
            true
        );


        try {

            const scoring =
                await window.API
                    .scoringEndInnings(
                        matchId
                    );


            render(
                scoring
            );


            window.showToast(
                "Innings ended."
            );

        }
        catch (error) {

            showError(
                error.message
                ||
                "Innings could not "
                + "be ended."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    async function startNextInnings() {

        if (state.busy) {
            return;
        }


        const payload = {

            striker_id:
                elements.nextStriker.value,

            non_striker_id:
                elements.nextNonStriker.value,

            opening_bowler_id:
                elements.nextOpeningBowler.value,
        };


        if (
            !payload.striker_id
            || !payload.non_striker_id
            || !payload.opening_bowler_id
        ) {

            showError(
                "Select the striker, "
                + "non-striker and "
                + "opening bowler."
            );

            return;
        }


        if (
            payload.striker_id
            === payload.non_striker_id
        ) {

            showError(
                "Striker and non-striker "
                + "must be different players."
            );

            return;
        }


        clearError();

        setBusy(
            true
        );


        try {

            const scoring =
                await window.API
                    .scoringStartNextInnings(
                        matchId,
                        payload
                    );


            render(
                scoring
            );


            window.showToast(
                `${ordinal(scoring.innings_number)} `
                + "innings started."
            );

        }
        catch (error) {

            showError(
                error.message
                ||
                "Innings could not "
                + "be started."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    elements
        .endInnings
        .addEventListener(
            "click",
            endInnings
        );


    elements
        .startNextInnings
        .addEventListener(
            "click",
            startNextInnings
        );


    elements
        .runControls
        .addEventListener(
            "click",
            (event) => {

                const button =
                    event.target.closest(
                        "[data-runs]"
                    );


                if (!button) {
                    return;
                }


                recordRuns(
                    Number(
                        button
                            .dataset
                            .runs
                    )
                );

            }
        );


    elements
        .saveBowler
        .addEventListener(
            "click",
            saveBowler
        );


    load();

})();