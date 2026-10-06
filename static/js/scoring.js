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


        // =========================
        // STAGE 5 - EXTRAS
        // =========================

        extrasPanel:
            document.getElementById(
                "extras-panel"
            ),

        extraType:
            document.getElementById(
                "extra-type"
            ),

        extraRuns:
            document.getElementById(
                "extra-runs"
            ),

        extraRunsLabel:
            document.getElementById(
                "extra-runs-label"
            ),

        extraHelp:
            document.getElementById(
                "extra-help"
            ),

        recordExtra:
            document.getElementById(
                "record-extra"
            ),


        // =========================
        // STAGE 5 - WICKETS
        // =========================

        wicketPanel:
            document.getElementById(
                "wicket-panel"
            ),

        wicketType:
            document.getElementById(
                "wicket-type"
            ),

        dismissedPlayer:
            document.getElementById(
                "dismissed-player"
            ),

        wicketFielder:
            document.getElementById(
                "wicket-fielder"
            ),

        nextBatter:
            document.getElementById(
                "next-batter"
            ),

        wicketRuns:
            document.getElementById(
                "wicket-runs"
            ),

        wicketExtraType:
            document.getElementById(
                "wicket-extra-type"
            ),

        wicketExtraRuns:
            document.getElementById(
                "wicket-extra-runs"
            ),

        wicketEndField:
            document.getElementById(
                "wicket-end-field"
            ),

        wicketEnd:
            document.getElementById(
                "wicket-end"
            ),

        wicketHelp:
            document.getElementById(
                "wicket-help"
            ),

        recordWicket:
            document.getElementById(
                "record-wicket"
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


    function humanWicketType(value) {

        return String(
            value || "wicket"
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


    function teamPlayers(teamId) {

        if (
            !state.match
            || !Array.isArray(
                state.match.players
            )
        ) {
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


    function battingPlayers() {

        if (!state.scoring) {
            return [];
        }


        return teamPlayers(
            state
                .scoring
                .batting_team
                .id
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


    function ordinal(value) {

        const remainder100 =
            value % 100;


        if (
            remainder100 >= 11
            && remainder100 <= 13
        ) {

            return `${value}th`;

        }


        const suffix =
            {
                1: "st",
                2: "nd",
                3: "rd",
            }[value % 10]
            || "th";


        return `${value}${suffix}`;

    }


    function numericOptions(
        values,
        selectedValue
    ) {

        return values
            .map(
                (value) => `
                    <option
                        value="${value}"
                        ${
                            Number(
                                selectedValue
                            )
                            === Number(
                                value
                            )
                                ? "selected"
                                : ""
                        }
                    >
                        ${value}
                    </option>
                `
            )
            .join("");

    }


    function playerOptions(
        players,
        placeholder,
        selectedId = ""
    ) {

        return (
            `<option value="">${escapeHtml(
                placeholder
            )}</option>`
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
                .join("")
        );

    }


    function plainPlayerOptions(
        players,
        placeholder,
        selectedId = ""
    ) {

        return (
            `<option value="">${escapeHtml(
                placeholder
            )}</option>`
            +
            players
                .map(
                    (player) => `
                        <option
                            value="${player.id}"
                            ${
                                player.id
                                === selectedId
                                    ? "selected"
                                    : ""
                            }
                        >
                            ${escapeHtml(
                                player.full_name
                                || player.short_name
                                || "Player"
                            )}
                        </option>
                    `
                )
                .join("")
        );

    }


    function deliveryLabel(delivery) {

        const hasWicket =
            Boolean(
                delivery.wicket_type
            );


        let label = "";


        if (
            Number(
                delivery.wide_runs
                || 0
            ) > 0
        ) {

            label =
                `${delivery.wide_runs}WD`;

        }
        else if (
            Number(
                delivery.no_ball_runs
                || 0
            ) > 0
        ) {

            const batterRuns =
                Number(
                    delivery.batter_runs
                    || 0
                );


            label =
                batterRuns > 0
                    ? `NB+${batterRuns}`
                    : "NB";

        }
        else if (
            Number(
                delivery.bye_runs
                || 0
            ) > 0
        ) {

            label =
                `${delivery.bye_runs}B`;

        }
        else if (
            Number(
                delivery.leg_bye_runs
                || 0
            ) > 0
        ) {

            label =
                `${delivery.leg_bye_runs}LB`;

        }
        else {

            label =
                String(
                    delivery.batter_runs
                    ?? delivery.total_runs
                    ?? 0
                );

        }


        if (hasWicket) {

            if (
                Number(
                    delivery.total_runs
                    || 0
                ) === 0
                && !delivery.wide_runs
                && !delivery.no_ball_runs
                && !delivery.bye_runs
                && !delivery.leg_bye_runs
            ) {

                return "W";

            }


            return `${label}+W`;

        }


        return label;

    }


    function renderRecentDeliveries(
        scoring
    ) {

        if (
            !scoring
            || !scoring
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


        const latestRecorded =
            [
                ...scoring
                    .recent_deliveries
            ]
                .reverse()
                .find(
                    (delivery) =>
                        delivery.status
                        === "recorded"
                );


        elements
            .recentBalls
            .innerHTML =
            scoring
                .recent_deliveries
                .map(
                    (delivery) => {

                        const isVoid =
                            delivery.status
                            === "void";


                        const canUndo =
                            !state.busy
                            && !isVoid
                            && latestRecorded
                            && latestRecorded.id
                                === delivery.id;


                        const wicketText =
                            delivery.wicket_type
                                ? (
                                    `
                                    <span class="muted">
                                        ${escapeHtml(
                                            humanWicketType(
                                                delivery
                                                    .wicket_type
                                            )
                                        )}
                                    </span>
                                    `
                                )
                                : "";


                        const correctionText =
                            isVoid
                            && delivery
                                .correction_reason
                                ? (
                                    `
                                    <span class="muted">
                                        ${escapeHtml(
                                            delivery
                                                .correction_reason
                                        )}
                                    </span>
                                    `
                                )
                                : "";


                        const undoButton =
                            canUndo
                                ? (
                                    `
                                    <button
                                        class="
                                            button
                                            button-secondary
                                            button-small
                                        "
                                        type="button"
                                        data-undo-delivery="${delivery.id}"
                                    >
                                        Undo
                                    </button>
                                    `
                                )
                                : "";


                        return `
                            <div
                                class="
                                    recent-ball-chip
                                    ${
                                        isVoid
                                            ? "is-void"
                                            : ""
                                    }
                                "
                            >

                                <small>
                                    ${delivery.over_number}.${delivery.ball_number}
                                    · #${delivery.sequence}
                                </small>


                                <strong>
                                    ${escapeHtml(
                                        deliveryLabel(
                                            delivery
                                        )
                                    )}
                                </strong>


                                ${wicketText}


                                ${
                                    isVoid
                                        ? (
                                            `
                                            <span class="muted">
                                                VOID
                                            </span>
                                            `
                                        )
                                        : ""
                                }


                                ${correctionText}


                                ${undoButton}

                            </div>
                        `;

                    }
                )
                .join("");

    }


    function renderExtraControls(
        resetSelection = false
    ) {

        if (
            !elements.extraType
            || !elements.extraRuns
        ) {

            return;

        }


        const type =
            elements.extraType.value;


        const previousValue =
            resetSelection
                ? null
                : Number(
                    elements
                        .extraRuns
                        .value
                );


        let values = [];

        let defaultValue = 1;

        let label =
            "Runs";

        let help =
            "";


        if (
            type === "wide"
        ) {

            values = [
                1,
                2,
                3,
                4,
                5,
                6,
            ];


            defaultValue = 1;


            label =
                "Total wide runs";


            help =
                "Enter the total wide runs, "
                + "including the automatic "
                + "one-run wide.";

        }
        else if (
            type === "no_ball"
        ) {

            values = [
                0,
                1,
                2,
                3,
                4,
                6,
            ];


            defaultValue = 0;


            label =
                "Batter runs";


            help =
                "The no-ball penalty is added "
                + "automatically. Select only "
                + "the batter runs from the ball.";

        }
        else if (
            type === "bye"
        ) {

            values = [
                1,
                2,
                3,
                4,
                5,
                6,
            ];


            defaultValue = 1;


            label =
                "Bye runs";


            help =
                "Byes count as extras, but the "
                + "delivery remains a legal ball.";

        }
        else {

            values = [
                1,
                2,
                3,
                4,
                5,
                6,
            ];


            defaultValue = 1;


            label =
                "Leg bye runs";


            help =
                "Leg byes count as extras, but "
                + "the delivery remains a legal ball.";

        }


        const selected =
            values.includes(
                previousValue
            )
                ? previousValue
                : defaultValue;


        elements
            .extraRuns
            .innerHTML =
            numericOptions(
                values,
                selected
            );


        if (
            elements.extraRunsLabel
        ) {

            elements
                .extraRunsLabel
                .textContent =
                label;

        }


        if (
            elements.extraHelp
        ) {

            elements
                .extraHelp
                .textContent =
                help;

        }


        const locked =
            state.busy
            || scoringLocked(
                state.scoring
            );


        elements
            .extraType
            .disabled =
            locked;


        elements
            .extraRuns
            .disabled =
            locked;


        if (
            elements.recordExtra
        ) {

            elements
                .recordExtra
                .disabled =
                locked;

        }

    }


    function renderWicketExtraControls(
        resetSelection = false
    ) {

        if (
            !elements.wicketExtraType
            || !elements.wicketExtraRuns
            || !elements.wicketRuns
        ) {

            return;

        }


        const type =
            elements
                .wicketExtraType
                .value;


        const previousExtraRuns =
            resetSelection
                ? null
                : Number(
                    elements
                        .wicketExtraRuns
                        .value
                );


        let extraValues = [
            0
        ];

        let defaultExtraRuns = 0;

        let extraRunsDisabled =
            true;

        let batterRunsDisabled =
            false;


        if (
            type === "wide"
            || type === "bye"
            || type === "leg_bye"
        ) {

            extraValues = [
                1,
                2,
                3,
                4,
                5,
                6,
            ];


            defaultExtraRuns = 1;

            extraRunsDisabled =
                false;

            batterRunsDisabled =
                true;


            elements
                .wicketRuns
                .value =
                "0";

        }
        else if (
            type === "no_ball"
        ) {

            // One no-ball penalty run
            // is added by the backend.
            extraValues = [
                0
            ];


            defaultExtraRuns = 0;

            extraRunsDisabled =
                true;

            batterRunsDisabled =
                false;

        }


        const selectedExtraRuns =
            extraValues.includes(
                previousExtraRuns
            )
                ? previousExtraRuns
                : defaultExtraRuns;


        elements
            .wicketExtraRuns
            .innerHTML =
            numericOptions(
                extraValues,
                selectedExtraRuns
            );


        const locked =
            state.busy
            || scoringLocked(
                state.scoring
            );


        elements
            .wicketExtraRuns
            .disabled =
            locked
            || extraRunsDisabled;


        elements
            .wicketRuns
            .disabled =
            locked
            || batterRunsDisabled;

    }


    function renderWicketControls(
        scoring
    ) {

        if (
            !elements.wicketPanel
            || !elements.wicketType
        ) {

            return;

        }


        const currentDismissed =
            elements
                .dismissedPlayer
                ?.value
            || "";


        const currentFielder =
            elements
                .wicketFielder
                ?.value
            || "";


        const currentNextBatter =
            elements
                .nextBatter
                ?.value
            || "";


        const currentBatters = [
            scoring.striker,
            scoring.non_striker,
        ]
            .filter(
                Boolean
            );


        if (
            elements.dismissedPlayer
        ) {

            elements
                .dismissedPlayer
                .innerHTML =
                plainPlayerOptions(
                    currentBatters,
                    "Select dismissed player",
                    currentDismissed
                );

        }


        if (
            elements.wicketFielder
        ) {

            elements
                .wicketFielder
                .innerHTML =
                playerOptions(
                    bowlingPlayers(),
                    "No fielder",
                    currentFielder
                );

        }


        const dismissedIds =
            new Set(
                scoring
                    .dismissed_player_ids
                    || []
            );


        const activeIds =
            new Set(
                [
                    scoring.striker?.id,
                    scoring.non_striker?.id,
                ]
                    .filter(
                        Boolean
                    )
            );


        const availableBatters =
            battingPlayers()
                .filter(
                    (item) =>
                        !dismissedIds.has(
                            item.player.id
                        )
                        && !activeIds.has(
                            item.player.id
                        )
                );


        const finalWicket =
            Number(
                scoring.wickets
            ) + 1
            >= Number(
                scoring.max_wickets
            );


        if (
            elements.nextBatter
        ) {

            if (
                finalWicket
            ) {

                elements
                    .nextBatter
                    .innerHTML =
                    `
                    <option value="">
                        No next batter — final wicket
                    </option>
                    `;

            }
            else {

                elements
                    .nextBatter
                    .innerHTML =
                    playerOptions(
                        availableBatters,
                        "Select next batter",
                        currentNextBatter
                    );

            }

        }


        const isRunOut =
            elements
                .wicketType
                .value
            === "run_out";


        if (
            elements.wicketEndField
        ) {

            elements
                .wicketEndField
                .classList
                .toggle(
                    "hidden",
                    !isRunOut
                );

        }


        if (
            !isRunOut
            && elements.wicketEnd
        ) {

            elements
                .wicketEnd
                .value =
                "";

        }


        const locked =
            state.busy
            || scoringLocked(
                scoring
            );


        elements
            .wicketType
            .disabled =
            locked;


        if (
            elements.dismissedPlayer
        ) {

            elements
                .dismissedPlayer
                .disabled =
                locked;

        }


        if (
            elements.wicketFielder
        ) {

            elements
                .wicketFielder
                .disabled =
                locked;

        }


        if (
            elements.nextBatter
        ) {

            elements
                .nextBatter
                .disabled =
                locked
                || finalWicket;

        }


        if (
            elements.wicketExtraType
        ) {

            elements
                .wicketExtraType
                .disabled =
                locked;

        }


        if (
            elements.wicketEnd
        ) {

            elements
                .wicketEnd
                .disabled =
                locked
                || !isRunOut;

        }


        if (
            elements.recordWicket
        ) {

            elements
                .recordWicket
                .disabled =
                locked;

        }


        renderWicketExtraControls();

    }


    function renderStage5Controls(
        scoring
    ) {

        if (
            !scoring
        ) {

            return;

        }


        renderExtraControls();


        renderWicketControls(
            scoring
        );

    }


    function renderBowlerControl() {

        const scoring =
            state.scoring;


        if (
            !scoring
        ) {

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


        const players =
            bowlingPlayers()
                .filter(
                    (item) =>
                        item.player.id
                        !== scoring
                            .previous_over_bowler_id
                );


        if (
            canChange
        ) {

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
                        + `${playerName(
                            scoring.current_bowler
                        )} `
                        + "bowled it, so select "
                        + "a different bowler "
                        + "to continue."
                    )
                    : (
                        `${playerName(
                            scoring.current_bowler
                        )} `
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


    function renderNextInnings(
        scoring
    ) {

        const show =
            scoring
                .can_start_next_innings;


        elements
            .nextInningsPanel
            .classList
            .toggle(
                "hidden",
                !show
            );


        elements
            .startNextInnings
            .disabled =
            state.busy;


        if (
            !show
        ) {

            state.nextInningsFor =
                null;


            return;

        }


        elements
            .nextInningsTitle
            .textContent =
            `Start ${ordinal(
                scoring.next_innings_number
            )} innings · `
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


        let chase =
            "";


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


        elements
            .chase
            .textContent =
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
                        `${ordinal(
                            item.innings_number
                        )} inns: `
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


        elements
            .endInnings
            .disabled =
            state.busy;


        renderNextInnings(
            scoring
        );

    }


    function renderRunControls(
        scoring
    ) {

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


        elements
            .title
            .textContent =
            matchTitle
            || "Live Scoring Console";


        elements
            .subtitle
            .textContent =
            `${scoring.batting_team.short_name} batting`
            +
            " · "
            +
            `${scoring.bowling_team.short_name} bowling`
            +
            " · "
            +
            `${scoring.balls_per_over} balls/over`;


        elements
            .status
            .textContent =
            humanStatus(
                scoring.match_status
            );


        elements
            .status
            .className =
            `status-badge status-${scoring.match_status}`;


        elements
            .battingTeam
            .textContent =
            `${ordinal(
                scoring.innings_number
            )} innings · `
            + scoring
                .batting_team
                .name;


        elements
            .runs
            .textContent =
            scoring.total_runs;


        elements
            .wickets
            .textContent =
            scoring.wickets;


        elements
            .overs
            .textContent =
            scoring.overs;


        elements
            .crr
            .textContent =
            Number(
                scoring.current_run_rate
            )
                .toFixed(2);


        elements
            .nextBall
            .textContent =
            scoring.innings_complete
                ? "—"
                : (
                    `${scoring.next_over_number}.`
                    + `${scoring.next_ball_number}`
                );


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
            "Each scoring event is committed "
            + "as one backend transaction.";


        if (
            scoring.match_status
            === "completed"
        ) {

            lockNote =
                "The match is complete. "
                + "The latest delivery can still "
                + "be corrected if necessary.";

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
                    : (
                        "Innings complete."
                    );

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


        renderStage5Controls(
            scoring
        );


        renderRunControls(
            scoring
        );

    }


    function setBusy(value) {

        state.busy =
            value;


        root.classList.toggle(
            "is-saving",
            value
        );


        if (
            !state.scoring
        ) {

            return;

        }


        renderRunControls(
            state.scoring
        );


        renderBowlerControl();


        renderStage5Controls(
            state.scoring
        );


        renderRecentDeliveries(
            state.scoring
        );


        elements
            .startNextInnings
            .disabled =
            value;


        elements
            .endInnings
            .disabled =
            value;

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
        catch (
            error
        ) {

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

        if (
            state.busy
            || scoringLocked(
                state.scoring
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
                    .scoringRecordDelivery(
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
        catch (
            error
        ) {

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


    async function recordExtra() {

        if (
            state.busy
            || scoringLocked(
                state.scoring
            )
        ) {

            return;

        }


        const type =
            elements
                .extraType
                .value;


        const runs =
            Number(
                elements
                    .extraRuns
                    .value
            );


        const payload = {
            runs: 0,
        };


        let toastMessage =
            "Extra recorded.";


        if (
            type === "wide"
        ) {

            if (
                runs < 1
            ) {

                showError(
                    "A wide must add at "
                    + "least one wide run."
                );


                return;

            }


            payload.wide_runs =
                runs;


            toastMessage =
                `${runs} wide run${
                    runs === 1
                        ? ""
                        : "s"
                } recorded.`;

        }
        else if (
            type === "no_ball"
        ) {

            payload.no_ball =
                true;


            payload.runs =
                runs;


            toastMessage =
                "No-ball recorded.";

        }
        else if (
            type === "bye"
        ) {

            if (
                runs < 1
            ) {

                showError(
                    "A bye event must add "
                    + "at least one bye run."
                );


                return;

            }


            payload.bye_runs =
                runs;


            toastMessage =
                `${runs} bye run${
                    runs === 1
                        ? ""
                        : "s"
                } recorded.`;

        }
        else if (
            type === "leg_bye"
        ) {

            if (
                runs < 1
            ) {

                showError(
                    "A leg-bye event must add "
                    + "at least one leg-bye run."
                );


                return;

            }


            payload.leg_bye_runs =
                runs;


            toastMessage =
                `${runs} leg-bye run${
                    runs === 1
                        ? ""
                        : "s"
                } recorded.`;

        }


        clearError();


        setBusy(
            true
        );


        try {

            const scoring =
                await window.API
                    .scoringRecordDelivery(
                        matchId,
                        payload
                    );


            render(
                scoring
            );


            renderExtraControls(
                true
            );


            window.showToast(
                toastMessage
            );

        }
        catch (
            error
        ) {

            showError(
                error.message
                ||
                "Extra could not "
                + "be recorded."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    function wicketValidationMessage(
        wicketType,
        extraType,
        batterRuns,
        extraRuns
    ) {

        if (
            extraType === "no_ball"
            && ![
                "run_out",
                "obstructing_field",
            ].includes(
                wicketType
            )
        ) {

            return (
                "On a no-ball, this "
                + "dismissal type is not "
                + "allowed by the Stage 5 "
                + "scoring rules."
            );

        }


        if (
            extraType === "wide"
            && ![
                "run_out",
                "stumped",
                "hit_wicket",
                "obstructing_field",
            ].includes(
                wicketType
            )
        ) {

            return (
                "This dismissal type is "
                + "not valid on a wide."
            );

        }


        let runningRuns =
            batterRuns;


        if (
            extraType === "wide"
        ) {

            runningRuns =
                Math.max(
                    extraRuns - 1,
                    0
                );

        }
        else if (
            extraType === "bye"
            || extraType === "leg_bye"
        ) {

            runningRuns =
                extraRuns;

        }


        if (
            runningRuns > 0
            && ![
                "run_out",
                "obstructing_field",
            ].includes(
                wicketType
            )
        ) {

            return (
                "Runs on a wicket delivery "
                + "are supported only for "
                + "run out or obstructing "
                + "the field."
            );

        }


        return "";

    }


    async function recordWicket() {

        if (
            state.busy
            || scoringLocked(
                state.scoring
            )
        ) {

            return;

        }


        const wicketType =
            elements
                .wicketType
                .value;


        const dismissedPlayerId =
            elements
                .dismissedPlayer
                .value;


        const fielderId =
            elements
                .wicketFielder
                .value;


        const nextBatterId =
            elements
                .nextBatter
                .value;


        const batterRuns =
            Number(
                elements
                    .wicketRuns
                    .value
            );


        const extraType =
            elements
                .wicketExtraType
                .value;


        const extraRuns =
            Number(
                elements
                    .wicketExtraRuns
                    .value
            );


        const wicketEnd =
            elements
                .wicketEnd
                .value;


        if (
            !dismissedPlayerId
        ) {

            showError(
                "Select the dismissed "
                + "player."
            );


            return;

        }


        const finalWicket =
            Number(
                state.scoring.wickets
            ) + 1
            >= Number(
                state.scoring.max_wickets
            );


        if (
            !finalWicket
            && !nextBatterId
        ) {

            showError(
                "Select the next batter."
            );


            return;

        }


        if (
            [
                "wide",
                "bye",
                "leg_bye",
            ].includes(
                extraType
            )
            && extraRuns < 1
        ) {

            showError(
                "Enter at least one "
                + "extra run."
            );


            return;

        }


        const validationError =
            wicketValidationMessage(
                wicketType,
                extraType,
                batterRuns,
                extraRuns
            );


        if (
            validationError
        ) {

            showError(
                validationError
            );


            return;

        }


        const wicket = {

            wicket_type:
                wicketType,

            dismissed_player_id:
                dismissedPlayerId,
        };


        if (
            fielderId
        ) {

            wicket.fielder_id =
                fielderId;

        }


        if (
            !finalWicket
            && nextBatterId
        ) {

            wicket.next_batter_id =
                nextBatterId;

        }


        if (
            wicketType === "run_out"
            && wicketEnd
        ) {

            wicket.wicket_end =
                wicketEnd;

        }


        const payload = {

            runs:
                batterRuns,

            wicket:
                wicket,
        };


        if (
            extraType === "wide"
        ) {

            payload.runs =
                0;


            payload.wide_runs =
                extraRuns;

        }
        else if (
            extraType === "no_ball"
        ) {

            payload.no_ball =
                true;

        }
        else if (
            extraType === "bye"
        ) {

            payload.runs =
                0;


            payload.bye_runs =
                extraRuns;

        }
        else if (
            extraType === "leg_bye"
        ) {

            payload.runs =
                0;


            payload.leg_bye_runs =
                extraRuns;

        }


        clearError();


        setBusy(
            true
        );


        try {

            const scoring =
                await window.API
                    .scoringRecordDelivery(
                        matchId,
                        payload
                    );


            render(
                scoring
            );


            resetWicketForm();


            window.showToast(
                "Wicket recorded."
            );

        }
        catch (
            error
        ) {

            showError(
                error.message
                ||
                "Wicket could not "
                + "be recorded."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    function resetWicketForm() {

        if (
            !elements.wicketType
        ) {

            return;

        }


        elements
            .wicketType
            .value =
            "bowled";


        elements
            .dismissedPlayer
            .value =
            "";


        elements
            .wicketFielder
            .value =
            "";


        elements
            .nextBatter
            .value =
            "";


        elements
            .wicketRuns
            .value =
            "0";


        elements
            .wicketExtraType
            .value =
            "none";


        elements
            .wicketEnd
            .value =
            "";


        renderWicketExtraControls(
            true
        );


        if (
            state.scoring
        ) {

            renderWicketControls(
                state.scoring
            );

        }

    }


    async function undoDelivery(
        deliveryId
    ) {

        if (
            state.busy
            || !deliveryId
        ) {

            return;

        }


        const reasonInput =
            window.prompt(
                "Reason for undo/correction:"
            );


        if (
            reasonInput === null
        ) {

            return;

        }


        const reason =
            reasonInput.trim();


        if (
            reason.length < 3
        ) {

            showError(
                "Correction reason must "
                + "be at least 3 characters."
            );


            return;

        }


        const confirmed =
            window.confirm(
                "Undo the latest official "
                + "delivery? The delivery will "
                + "remain in history as VOID."
            );


        if (
            !confirmed
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
                    .scoringUndoDelivery(
                        matchId,
                        deliveryId,
                        {
                            reason:
                                reason,
                        }
                    );


            render(
                scoring
            );


            window.showToast(
                "Delivery voided and "
                + "scoring state rebuilt."
            );

        }
        catch (
            error
        ) {

            showError(
                error.message
                ||
                "Delivery could not "
                + "be undone."
            );

        }
        finally {

            setBusy(
                false
            );

        }

    }


    async function saveBowler() {

        if (
            state.busy
        ) {

            return;

        }


        const bowlerId =
            elements
                .nextBowler
                .value;


        if (
            !bowlerId
        ) {

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
        catch (
            error
        ) {

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

        if (
            state.busy
        ) {

            return;

        }


        if (
            !window.confirm(
                "End this innings now? "
                + "This innings-end action "
                + "cannot be undone."
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
        catch (
            error
        ) {

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

        if (
            state.busy
        ) {

            return;

        }


        const payload = {

            striker_id:
                elements
                    .nextStriker
                    .value,

            non_striker_id:
                elements
                    .nextNonStriker
                    .value,

            opening_bowler_id:
                elements
                    .nextOpeningBowler
                    .value,
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
                `${ordinal(
                    scoring.innings_number
                )} innings started.`
            );

        }
        catch (
            error
        ) {

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


    // =========================
    // EXISTING EVENT HANDLERS
    // =========================

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


                if (
                    !button
                ) {

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


    // =========================
    // STAGE 5 EXTRA EVENTS
    // =========================

    if (
        elements.extraType
    ) {

        elements
            .extraType
            .addEventListener(
                "change",
                () => {

                    renderExtraControls(
                        true
                    );

                }
            );

    }


    if (
        elements.recordExtra
    ) {

        elements
            .recordExtra
            .addEventListener(
                "click",
                recordExtra
            );

    }


    // =========================
    // STAGE 5 WICKET EVENTS
    // =========================

    if (
        elements.wicketType
    ) {

        elements
            .wicketType
            .addEventListener(
                "change",
                () => {

                    if (
                        state.scoring
                    ) {

                        renderWicketControls(
                            state.scoring
                        );

                    }

                }
            );

    }


    if (
        elements.wicketExtraType
    ) {

        elements
            .wicketExtraType
            .addEventListener(
                "change",
                () => {

                    renderWicketExtraControls(
                        true
                    );

                }
            );

    }


    if (
        elements.recordWicket
    ) {

        elements
            .recordWicket
            .addEventListener(
                "click",
                recordWicket
            );

    }


    // =========================
    // STAGE 5 UNDO EVENT
    // =========================

    elements
        .recentBalls
        .addEventListener(
            "click",
            (event) => {

                const button =
                    event.target.closest(
                        "[data-undo-delivery]"
                    );


                if (
                    !button
                ) {

                    return;

                }


                undoDelivery(
                    button
                        .dataset
                        .undoDelivery
                );

            }
        );


    if (
        window.MatchLive
    ) {

        window.MatchLive.connect(

            matchId,

            (
                event
            ) => {

                if (
                    event.scoring
                ) {

                    render(
                        event.scoring
                    );

                }

            }

        );

    }


    load();

})();
