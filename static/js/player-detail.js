(() => {

    "use strict";


    const root =
        document.getElementById(
            "player-profile-page"
        );


    if (!root) {
        return;
    }


    const playerId =
        root.dataset.playerId;


    const historyState = {

        page: 1,

        pageSize: 8,

        pages: 0,

        total: 0,

    };


    const elements = {

        name:
            document.getElementById(
                "player-name"
            ),

        subtitle:
            document.getElementById(
                "player-subtitle"
            ),

        error:
            document.getElementById(
                "profile-error"
            ),

        avatar:
            document.getElementById(
                "player-avatar"
            ),

        heroTeams:
            document.getElementById(
                "player-hero-teams"
            ),

        heroMatches:
            document.getElementById(
                "hero-matches"
            ),

        heroRuns:
            document.getElementById(
                "hero-runs"
            ),

        heroWickets:
            document.getElementById(
                "hero-wickets"
            ),

        battingHighlights:
            document.getElementById(
                "batting-highlights"
            ),

        bowlingHighlights:
            document.getElementById(
                "bowling-highlights"
            ),

        age:
            document.getElementById(
                "player-age"
            ),

        nationality:
            document.getElementById(
                "player-nationality"
            ),

        battingStyle:
            document.getElementById(
                "player-batting-style"
            ),

        bowlingStyle:
            document.getElementById(
                "player-bowling-style"
            ),

        status:
            document.getElementById(
                "player-status"
            ),

        externalId:
            document.getElementById(
                "player-external-id"
            ),

        teams:
            document.getElementById(
                "active-teams"
            ),

        battingStats:
            document.getElementById(
                "batting-stats"
            ),

        bowlingStats:
            document.getElementById(
                "bowling-stats"
            ),

        battingForm:
            document.getElementById(
                "batting-form"
            ),

        bowlingForm:
            document.getElementById(
                "bowling-form"
            ),

        history:
            document.getElementById(
                "history-list"
            ),

        summary:
            document.getElementById(
                "history-summary"
            ),

        page:
            document.getElementById(
                "history-page"
            ),

        previous:
            document.getElementById(
                "history-previous"
            ),

        next:
            document.getElementById(
                "history-next"
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
                '"',
                "&quot;"
            )
            .replaceAll(
                "'",
                "&#039;"
            );

    }


    function humanize(value) {

        if (!value) {
            return "—";
        }


        return String(value)

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


    function formatDate(value) {

        if (!value) {

            return "Date not set";

        }


        return new Intl
            .DateTimeFormat(
                undefined,
                {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                }
            )
            .format(
                new Date(value)
            );

    }


    function display(value) {

        return (
            value === null
            || value === undefined
            || value === ""
        )
            ? "—"
            : value;

    }


    function initials(name) {

        const parts =
            String(name || "")
                .trim()
                .split(/\s+/)
                .filter(Boolean);


        if (!parts.length) {
            return "··";
        }


        return (
            parts[0][0] +
            (
                parts.length > 1
                    ? parts[parts.length - 1][0]
                    : ""
            )
        ).toUpperCase();

    }


    function stat(
        label,
        value
    ) {

        return `
            <div class="profile-stat-item">

                <span>
                    ${escapeHtml(label)}
                </span>

                <strong>
                    ${escapeHtml(
                        display(value)
                    )}
                </strong>

            </div>
        `;

    }


    function highlight(
        label,
        value
    ) {

        return `
            <div class="profile-highlight">

                <strong>
                    ${escapeHtml(
                        display(value)
                    )}
                </strong>

                <span>
                    ${escapeHtml(label)}
                </span>

            </div>
        `;

    }


    function renderIdentity(
        profile
    ) {

        const player =
            profile.player;


        document.title =
            `${player.full_name} | Cricket Intelligence Platform`;


        elements.name.textContent =
            player.full_name;


        elements.avatar.textContent =
            initials(
                player.full_name
            );


        elements.subtitle.textContent =

            [
                player.short_name
                    ? `"${player.short_name}"`
                    : null,

                player.nationality,

                player.age
                    ? `${player.age} years`
                    : null,
            ]
                .filter(Boolean)
                .join(" · ")

            || "Complete player career profile";


        elements.age.textContent =
            display(player.age);


        elements.nationality.textContent =
            display(player.nationality);


        elements.battingStyle.textContent =
            display(
                player.batting_style_display
            );


        elements.bowlingStyle.textContent =
            display(
                player.bowling_style_display
            );


        elements.status.textContent =
            humanize(
                player.status
            );


        elements.status.dataset.status =
            player.status || "";


        elements.externalId.textContent =
            display(player.external_id);

    }


    function renderTeams(
        teams
    ) {

        elements.heroTeams.textContent =

            teams
                .map(
                    (team) =>
                        team.team_short_name
                        || team.team_name
                )
                .join(" · ");


        if (!teams.length) {

            elements.teams.innerHTML = `
                <div class="profile-empty">
                    <span>👥</span>
                    Not part of any active team yet.
                </div>
            `;

            return;

        }


        elements.teams.innerHTML =

            teams.map(

                (team) => `

                    <article class="profile-team-card">

                        <span class="profile-team-badge">
                            ${escapeHtml(
                                (
                                    team.team_short_name
                                    || team.team_name
                                ).slice(0, 4)
                            )}
                        </span>

                        <div>

                            <strong>
                                ${escapeHtml(
                                    team.team_name
                                )}
                            </strong>

                            <span>
                                ${escapeHtml(
                                    humanize(
                                        team.role
                                    )
                                )}
                                ${
                                    team.joined_on
                                        ? ` · Since ${escapeHtml(
                                            formatDate(
                                                team.joined_on
                                            )
                                        )}`
                                        : ""
                                }
                            </span>

                        </div>

                        ${
                            team.squad_number

                                ? `
                                    <span class="profile-squad-number">
                                        #${escapeHtml(
                                            team.squad_number
                                        )}
                                    </span>
                                `

                                : ""
                        }

                    </article>

                `

            ).join("");

    }


    function formChip(
        main,
        detail,
        tone
    ) {

        return `
            <span class="profile-form-chip ${tone}">

                <strong>
                    ${escapeHtml(main)}
                </strong>

                <small>
                    ${escapeHtml(detail)}
                </small>

            </span>
        `;

    }


    function emptyForm(text) {

        return `
            <span class="profile-form-empty">
                ${escapeHtml(text)}
            </span>
        `;

    }


    function renderCareer(
        profile
    ) {

        const batting =
            profile.career.batting;


        const bowling =
            profile.career.bowling;


        elements.heroMatches.textContent =
            Math.max(
                batting.matches,
                bowling.matches
            );


        elements.heroRuns.textContent =
            batting.runs;


        elements.heroWickets.textContent =
            bowling.wickets;


        const highestScore =

            batting.innings

                ? (
                    `${batting.highest_score}` +

                    (
                        batting
                            .highest_score_not_out
                            ? "*"
                            : ""
                    )
                )

                : null;


        elements.battingHighlights.innerHTML = [

            highlight(
                "Runs",
                batting.runs
            ),

            highlight(
                "Average",
                batting.average
            ),

            highlight(
                "Strike rate",
                batting.strike_rate
            ),

        ].join("");


        elements.battingStats.innerHTML = [

            stat(
                "Matches",
                batting.matches
            ),

            stat(
                "Innings",
                batting.innings
            ),

            stat(
                "Not outs",
                batting.not_outs
            ),

            stat(
                "Highest",
                highestScore
            ),

            stat(
                "Balls faced",
                batting.balls_faced
            ),

            stat(
                "Fours",
                batting.fours
            ),

            stat(
                "Sixes",
                batting.sixes
            ),

            stat(
                "Dismissals",
                batting.dismissals
            ),

        ].join("");


        elements.bowlingHighlights.innerHTML = [

            highlight(
                "Wickets",
                bowling.wickets
            ),

            highlight(
                "Economy",
                bowling.economy
            ),

            highlight(
                "Best",
                bowling.best_figures
            ),

        ].join("");


        elements.bowlingStats.innerHTML = [

            stat(
                "Matches",
                bowling.matches
            ),

            stat(
                "Innings",
                bowling.innings
            ),

            stat(
                "Overs",
                bowling.overs
            ),

            stat(
                "Balls",
                bowling.balls_bowled
            ),

            stat(
                "Runs conceded",
                bowling.runs_conceded
            ),

            stat(
                "Average",
                bowling.average
            ),

            stat(
                "Strike rate",
                bowling.strike_rate
            ),

        ].join("");


        elements.battingForm.innerHTML =

            batting.recent_form.length

                ? batting.recent_form.map(

                    (item) => formChip(

                        `${item.runs}${item.not_out ? "*" : ""}`,

                        `${item.balls_faced}b`,

                        item.runs >= 50
                            ? "is-great"
                            : item.runs >= 25
                                ? "is-good"
                                : ""

                    )

                ).join("")

                : emptyForm(
                    "No batting innings yet."
                );


        elements.bowlingForm.innerHTML =

            bowling.recent_form.length

                ? bowling.recent_form.map(

                    (item) => formChip(

                        `${item.wickets}/${item.runs_conceded}`,

                        `${item.balls_bowled}b`,

                        item.wickets >= 3
                            ? "is-great"
                            : item.wickets >= 1
                                ? "is-good"
                                : ""

                    )

                ).join("")

                : emptyForm(
                    "No bowling innings yet."
                );

    }


    function battingText(
        figures
    ) {

        if (!figures.length) {

            return "Did not bat";

        }


        return figures.map(

            (item) => (

                `${item.runs}` +

                (
                    item.not_out
                        ? "*"
                        : ""
                ) +

                ` (${item.balls_faced})`
            )

        ).join(
            " & "
        );

    }


    function bowlingText(
        figures
    ) {

        if (!figures.length) {

            return "Did not bowl";

        }


        return figures.map(

            (item) => (

                `${item.wickets}/` +
                `${item.runs_conceded}` +
                ` (${item.overs} ov)`

            )

        ).join(
            " & "
        );

    }


    function dateParts(value) {

        if (!value) {

            return {
                day: "—",
                month: "TBD",
                year: "",
            };

        }


        const date =
            new Date(value);


        return {

            day:
                date.getDate(),

            month:
                new Intl
                    .DateTimeFormat(
                        undefined,
                        { month: "short" }
                    )
                    .format(date),

            year:
                date.getFullYear(),

        };

    }


    function renderHistory(
        items
    ) {

        if (!items.length) {

            elements.history.innerHTML = `
                <div class="profile-empty">
                    <span>🏟️</span>
                    No match history yet. Matches will appear here once
                    this player is selected in a playing XI.
                </div>
            `;

            return;

        }


        elements.history.innerHTML =

            items.map(

                (item) => {

                    const date =
                        dateParts(
                            item.match_date
                        );


                    return `

                        <article class="profile-history-card">

                            <div class="profile-history-date">
                                <strong>${escapeHtml(date.day)}</strong>
                                <span>${escapeHtml(date.month)}</span>
                                <small>${escapeHtml(date.year)}</small>
                            </div>


                            <div class="profile-history-main">

                                <strong>
                                    ${escapeHtml(
                                        item.player_team_name
                                    )}
                                    <em>vs</em>
                                    ${escapeHtml(
                                        item.opponent_team_name
                                    )}
                                </strong>

                                <span>
                                    ${escapeHtml(
                                        item.title
                                        || "Match"
                                    )}
                                </span>

                            </div>


                            <div class="profile-history-figures">

                                <div class="${item.batting.length ? "" : "is-empty"}">
                                    <span>Bat</span>
                                    <strong>
                                        ${escapeHtml(
                                            battingText(
                                                item.batting
                                            )
                                        )}
                                    </strong>
                                </div>

                                <div class="${item.bowling.length ? "" : "is-empty"}">
                                    <span>Bowl</span>
                                    <strong>
                                        ${escapeHtml(
                                            bowlingText(
                                                item.bowling
                                            )
                                        )}
                                    </strong>
                                </div>

                            </div>

                        </article>
                    `;

                }

            ).join("");

    }


    function updateHistoryPagination() {

        const visiblePage =

            historyState.pages
                ? historyState.page
                : 0;


        elements.summary.textContent =

            `${historyState.total} ` +

            (
                historyState.total === 1
                    ? "match"
                    : "matches"
            );


        elements.page.textContent =

            `Page ${visiblePage} ` +
            `of ${historyState.pages}`;


        elements.previous.disabled =

            historyState.page <= 1
            ||
            !historyState.pages;


        elements.next.disabled =

            !historyState.pages

            ||

            historyState.page
            >= historyState.pages;

    }


    async function loadHistory() {

        try {

            const result =

                await window.API
                    .playerMatchHistory(

                        playerId,

                        {
                            page:
                                historyState.page,

                            page_size:
                                historyState.pageSize,
                        }

                    );


            historyState.pages =
                result.pages;


            historyState.total =
                result.total;


            renderHistory(
                result.items || []
            );


            updateHistoryPagination();

        }

        catch (error) {

            elements.history.innerHTML = `

                <div class="form-error">

                    ${
                        escapeHtml(
                            error.message
                        )
                    }

                </div>
            `;

        }

    }


    async function loadProfile() {

        try {

            const profile =

                await window.API
                    .playerProfile(
                        playerId
                    );


            renderIdentity(
                profile
            );


            renderTeams(
                profile.active_teams
                || []
            );


            renderCareer(
                profile
            );


            elements.error
                .classList
                .add(
                    "hidden"
                );

        }

        catch (error) {

            elements.error.textContent =
                error.message;


            elements.error
                .classList
                .remove(
                    "hidden"
                );

        }

    }


    elements.previous
        .addEventListener(

            "click",

            () => {

                if (
                    historyState.page
                    > 1
                ) {

                    historyState.page -= 1;

                    loadHistory();

                }

            }

        );


    elements.next
        .addEventListener(

            "click",

            () => {

                if (
                    historyState.page
                    <
                    historyState.pages
                ) {

                    historyState.page += 1;

                    loadHistory();

                }

            }

        );


    loadProfile();

    loadHistory();

})();