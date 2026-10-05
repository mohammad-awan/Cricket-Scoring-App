(() => {

    "use strict";


    const page =
        document.getElementById(
            "scorecard-page"
        );


    if (!page) {
        return;
    }


    const matchId =
        page.dataset.matchId;


    const elements = {

        title:
            document.getElementById(
                "scorecard-title"
            ),

        subtitle:
            document.getElementById(
                "scorecard-subtitle"
            ),

        status:
            document.getElementById(
                "scorecard-status"
            ),

        error:
            document.getElementById(
                "scorecard-error"
            ),

        lifecycle:
            document.getElementById(
                "lifecycle-label"
            ),

        target:
            document.getElementById(
                "target-value"
            ),

        runsRequired:
            document.getElementById(
                "runs-required-value"
            ),

        ballsRemaining:
            document.getElementById(
                "balls-remaining-value"
            ),

        requiredRate:
            document.getElementById(
                "required-rr-value"
            ),

        result:
            document.getElementById(
                "match-result"
            ),

        innings:
            document.getElementById(
                "innings-scorecards"
            ),

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
                "\"",
                "&quot;"
            )
            .replaceAll(
                "'",
                "&#039;"
            );

    }


    function displayValue(value) {

        if (
            value === null ||
            value === undefined
        ) {

            return "—";
        }


        return String(
            value
        );

    }


    function battingRows(rows) {

        return rows
            .map(
                (row) => `

                    <tr>

                        <td
                            class="scorecard-player"
                        >
                            ${escapeHtml(
                                row.player.full_name
                            )}
                        </td>


                        <td
                            class="scorecard-dismissal"
                        >
                            ${escapeHtml(
                                row.dismissal
                            )}
                        </td>


                        <td>
                            ${row.runs}
                        </td>


                        <td>
                            ${row.balls}
                        </td>


                        <td>
                            ${row.fours}
                        </td>


                        <td>
                            ${row.sixes}
                        </td>


                        <td>
                            ${Number(
                                row.strike_rate
                            ).toFixed(2)}
                        </td>

                    </tr>

                `
            )
            .join("");

    }


    function bowlingRows(rows) {

        if (!rows.length) {

            return `

                <tr>

                    <td colspan="8">
                        No bowling figures yet.
                    </td>

                </tr>

            `;
        }


        return rows
            .map(
                (row) => `

                    <tr>

                        <td
                            class="scorecard-player"
                        >
                            ${escapeHtml(
                                row.player.full_name
                            )}
                        </td>


                        <td>
                            ${escapeHtml(
                                row.overs
                            )}
                        </td>


                        <td>
                            ${row.maidens}
                        </td>


                        <td>
                            ${row.runs_conceded}
                        </td>


                        <td>
                            ${row.wickets}
                        </td>


                        <td>
                            ${row.wides}
                        </td>


                        <td>
                            ${row.no_balls}
                        </td>


                        <td>
                            ${Number(
                                row.economy
                            ).toFixed(2)}
                        </td>

                    </tr>

                `
            )
            .join("");

    }


    function partnershipRows(rows) {

        if (!rows.length) {

            return `

                <p class="muted">
                    No partnership data yet.
                </p>

            `;
        }


        return `

            <div class="partnership-list">

                ${rows
                    .map(
                        (row) => `

                            <div
                                class="partnership-row"
                            >

                                <span>

                                    ${escapeHtml(
                                        row
                                            .batter_one
                                            .full_name
                                    )}

                                    &amp;

                                    ${escapeHtml(
                                        row
                                            .batter_two
                                            .full_name
                                    )}

                                </span>


                                <span>

                                    ${row.runs}
                                    runs ·

                                    ${row.legal_balls}
                                    balls

                                </span>

                            </div>

                        `
                    )
                    .join("")}

            </div>

        `;

    }


    function inningsCard(card) {

        const extras =
            card.extras;


        return `

            <section
                class="panel innings-card"
            >

                <div
                    class="innings-card-header"
                >

                    <div>

                        <p class="eyebrow">

                            Innings
                            ${card.innings_number}

                        </p>


                        <h2>

                            ${escapeHtml(
                                card
                                    .batting_team
                                    .name
                            )}

                        </h2>

                    </div>


                    <div
                        class="innings-total"
                    >

                        <strong>

                            ${card.total_runs}
                            /
                            ${card.wickets}

                        </strong>


                        <span>

                            ${escapeHtml(
                                card.overs
                            )}
                            overs ·

                            RR
                            ${Number(
                                card.run_rate
                            ).toFixed(2)}

                        </span>

                    </div>

                </div>


                <div
                    class="scorecard-section"
                >

                    <h3>
                        Batting
                    </h3>


                    <div
                        class="scorecard-table-wrap"
                    >

                        <table
                            class="scorecard-table"
                        >

                            <thead>

                                <tr>

                                    <th>
                                        Batter
                                    </th>

                                    <th>
                                        Dismissal
                                    </th>

                                    <th>
                                        R
                                    </th>

                                    <th>
                                        B
                                    </th>

                                    <th>
                                        4s
                                    </th>

                                    <th>
                                        6s
                                    </th>

                                    <th>
                                        SR
                                    </th>

                                </tr>

                            </thead>


                            <tbody>

                                ${battingRows(
                                    card.batting
                                )}

                            </tbody>

                        </table>

                    </div>

                </div>


                <div
                    class="scorecard-section"
                >

                    <div
                        class="scorecard-meta-row"
                    >

                        <span>

                            <strong>
                                Extras:
                            </strong>

                            ${extras.total}

                        </span>


                        <span>
                            Wd
                            ${extras.wides}
                        </span>


                        <span>
                            Nb
                            ${extras.no_balls}
                        </span>


                        <span>
                            B
                            ${extras.byes}
                        </span>


                        <span>
                            Lb
                            ${extras.leg_byes}
                        </span>

                    </div>

                </div>


                <div
                    class="scorecard-section"
                >

                    <h3>
                        Bowling
                    </h3>


                    <div
                        class="scorecard-table-wrap"
                    >

                        <table
                            class="scorecard-table"
                        >

                            <thead>

                                <tr>

                                    <th>
                                        Bowler
                                    </th>

                                    <th>
                                        O
                                    </th>

                                    <th>
                                        M
                                    </th>

                                    <th>
                                        R
                                    </th>

                                    <th>
                                        W
                                    </th>

                                    <th>
                                        Wd
                                    </th>

                                    <th>
                                        Nb
                                    </th>

                                    <th>
                                        Econ
                                    </th>

                                </tr>

                            </thead>


                            <tbody>

                                ${bowlingRows(
                                    card.bowling
                                )}

                            </tbody>

                        </table>

                    </div>

                </div>


                <div
                    class="scorecard-section"
                >

                    <h3>
                        Partnerships
                    </h3>


                    ${partnershipRows(
                        card.partnerships
                    )}

                </div>

            </section>

        `;

    }


    function render(data) {

        const lifecycle =
            data.lifecycle;


        const chase =
            lifecycle.chase;


        const result =
            lifecycle.result;


        elements.title.textContent =
            data.title ||
            "Full Scorecard";


        elements.subtitle.textContent =
            `${data.team_a.name} ` +
            `vs ` +
            `${data.team_b.name}`;


        elements.status.textContent =
            lifecycle.state_label;


        elements.lifecycle.textContent =
            lifecycle.state_label;


        elements.target.textContent =
            displayValue(
                chase.target
            );


        elements.runsRequired.textContent =
            displayValue(
                chase.runs_required
            );


        elements.ballsRemaining.textContent =
            displayValue(
                chase.balls_remaining
            );


        elements.requiredRate.textContent =
            (
                chase.required_run_rate
                === null
            )
                ? "—"

                : Number(
                    chase.required_run_rate
                ).toFixed(2);


        if (result.summary) {

            elements.result.textContent =
                result.summary;


            elements.result
                .classList
                .remove(
                    "hidden"
                );

        }
        else {

            elements.result
                .classList
                .add(
                    "hidden"
                );

        }


        elements.innings.innerHTML =
            data.innings
                .map(
                    inningsCard
                )
                .join("");

    }


    async function load() {

        elements.error
            .classList
            .add(
                "hidden"
            );


        try {

            const data =
                await window.API
                    .scorecardGet(
                        matchId
                    );


            render(
                data
            );

        }
        catch (error) {

            elements.error.textContent =
                error.message ||
                (
                    "Scorecard could "
                    + "not be loaded."
                );


            elements.error
                .classList
                .remove(
                    "hidden"
                );

        }

    }


    load();

})();