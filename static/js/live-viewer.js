(() => {

    "use strict";


    const root =
        document.getElementById(
            "live-viewer-page"
        );


    if (
        !root
    ) {

        return;

    }


    const matchId =
        root.dataset.matchId;


    const elements = {

        subtitle:
            document.getElementById(
                "viewer-subtitle"
            ),

        error:
            document.getElementById(
                "viewer-error"
            ),

        battingTeam:
            document.getElementById(
                "viewer-batting-team"
            ),

        runs:
            document.getElementById(
                "viewer-runs"
            ),

        wickets:
            document.getElementById(
                "viewer-wickets"
            ),

        overs:
            document.getElementById(
                "viewer-overs"
            ),

        crr:
            document.getElementById(
                "viewer-crr"
            ),

        target:
            document.getElementById(
                "viewer-target"
            ),

        runsRequired:
            document.getElementById(
                "viewer-runs-required"
            ),

        ballsRemaining:
            document.getElementById(
                "viewer-balls-remaining"
            ),

        chase:
            document.getElementById(
                "viewer-chase"
            ),

        striker:
            document.getElementById(
                "viewer-striker"
            ),

        nonStriker:
            document.getElementById(
                "viewer-non-striker"
            ),

        bowler:
            document.getElementById(
                "viewer-bowler"
            ),

        lastBall:
            document.getElementById(
                "viewer-last-ball"
            ),

        eventLabel:
            document.getElementById(
                "viewer-event-label"
            ),

        result:
            document.getElementById(
                "viewer-result"
            ),
    };


    function valueOrDash(
        value
    ) {

        if (
            value === null
            ||
            value === undefined
        ) {

            return "—";

        }


        return String(
            value
        );

    }


    function lastDeliveryLabel(
        scoring
    ) {

        const delivery =
            scoring
                .recent_deliveries
                ?.[0];


        if (
            !delivery
        ) {

            return (
                "No delivery yet"
            );

        }


        if (
            delivery.status
            === "void"
        ) {

            return (
                `${delivery.over_number}.`
                + `${delivery.ball_number}`
                + " · VOID"
            );

        }


        if (
            delivery.wicket_type
        ) {

            return (
                `${delivery.over_number}.`
                + `${delivery.ball_number}`
                + " · WICKET"
            );

        }


        if (
            delivery.wide_runs
            > 0
        ) {

            return (
                `${delivery.over_number}.`
                + `${delivery.ball_number}`
                + ` · ${delivery.wide_runs}`
                + " WD"
            );

        }


        if (
            delivery.no_ball_runs
            > 0
        ) {

            return (
                `${delivery.over_number}.`
                + `${delivery.ball_number}`
                + ` · ${delivery.total_runs}`
                + " NB"
            );

        }


        return (

            `${delivery.over_number}.`
            + `${delivery.ball_number}`
            + ` · ${delivery.total_runs}`
            + (
                delivery.total_runs === 1
                    ? " run"
                    : " runs"
            )

        );

    }


    function render(
        event
    ) {

        const scoring =
            event.scoring;


        elements
            .error
            .classList
            .add(
                "hidden"
            );


        elements
            .subtitle
            .textContent =

            (
                `Innings `
                + `${scoring.innings_number}`
                + ` · `
                + `${scoring.match_status}`
            );


        elements
            .battingTeam
            .textContent =

            scoring
                .batting_team
                .name;


        elements
            .runs
            .textContent =

            scoring
                .total_runs;


        elements
            .wickets
            .textContent =

            scoring
                .wickets;


        elements
            .overs
            .textContent =

            scoring
                .overs;


        elements
            .crr
            .textContent =

            Number(
                scoring
                    .current_run_rate
            )
                .toFixed(
                    2
                );


        elements
            .target
            .textContent =

            valueOrDash(
                scoring.target
            );


        elements
            .runsRequired
            .textContent =

            valueOrDash(
                scoring
                    .runs_required
            );


        elements
            .ballsRemaining
            .textContent =

            valueOrDash(
                scoring
                    .balls_remaining
            );


        elements
            .striker
            .textContent =

            scoring
                .striker
                .full_name;


        elements
            .nonStriker
            .textContent =

            scoring
                .non_striker
                .full_name;


        elements
            .bowler
            .textContent =

            scoring
                .current_bowler
                .full_name;


        elements
            .lastBall
            .textContent =

            lastDeliveryLabel(
                scoring
            );


        elements
            .eventLabel
            .textContent =

            event.event_type
            === "snapshot"

                ? (
                    "Fresh database "
                    + "snapshot"
                )

                : (
                    "Live update · "
                    + event
                        .event_type
                        .replaceAll(
                            "_",
                            " "
                        )
                );


        if (
            scoring.target
            !== null
        ) {

            elements
                .chase
                .textContent =

                (
                    `Target `
                    + `${scoring.target}`
                    +
                    (
                        scoring
                            .runs_required
                        !== null

                            ? (
                                ` · Need `
                                + `${scoring.runs_required}`
                            )

                            : ""
                    )
                );

        }

        else {

            elements
                .chase
                .textContent =
                "";

        }


        if (
            scoring.result_summary
        ) {

            elements
                .result
                .textContent =

                scoring
                    .result_summary;


            elements
                .result
                .classList
                .remove(
                    "hidden"
                );

        }

        else {

            elements
                .result
                .classList
                .add(
                    "hidden"
                );

        }

    }


    if (
        !window.MatchLive
    ) {

        elements
            .error
            .textContent =

            (
                "Realtime client "
                + "could not be loaded."
            );


        elements
            .error
            .classList
            .remove(
                "hidden"
            );


        return;

    }


    window.MatchLive.connect(
        matchId,
        render
    );

})();