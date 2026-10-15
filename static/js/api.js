(() => {

    "use strict";


    function validationMessage(detail) {

        if (typeof detail === "string") {

            return detail;

        }


        if (Array.isArray(detail)) {

            return detail
                .map((item) => {

                    const location =

                        Array.isArray(item.loc)

                            ? item.loc
                                .filter(
                                    (part) =>
                                        part !== "body"
                                )
                                .join(" → ")

                            : "field";


                    return (

                        `${location}: ` +

                        `${item.msg || "Invalid value"}`

                    );

                })
                .join("\n");

        }


        return "The request could not be completed.";

    }


    async function request(

        path,

        options = {}

    ) {

        const response = await fetch(

            path,

            {

                ...options,


                headers: {

                    "Content-Type":
                        "application/json",


                    ...(options.headers || {}),

                },

            }

        );


        let payload = null;


        const contentType =

            response.headers.get(
                "content-type"
            ) || "";


        if (

            contentType.includes(
                "application/json"
            )

        ) {

            payload = await response.json();

        }


        if (!response.ok) {

            const error = new Error(

                validationMessage(
                    payload?.detail
                )

            );


            error.status =
                response.status;


            error.payload =
                payload;


            throw error;

        }


        return payload;

    }


    function queryString(params) {

        const query =
            new URLSearchParams();


        Object.entries(params)
            .forEach(

                ([key, value]) => {

                    if (

                        value === undefined ||

                        value === null ||

                        value === ""

                    ) {

                        return;

                    }


                    query.set(

                        key,

                        String(value)

                    );

                }

            );


        return query.toString();

    }


    window.API = {


        health() {

            return request(

                "/health"

            );

        },


        list(

            resource,

            params = {}

        ) {

            const query =
                queryString(params);


            return request(

                `/${resource}` +

                `${query ? `?${query}` : ""}`

            );

        },


        get(

            resource,

            id

        ) {

            return request(

                `/${resource}/${id}`

            );

        },


        create(

            resource,

            data

        ) {

            return request(

                `/${resource}`,

                {

                    method: "POST",


                    body:

                        JSON.stringify(
                            data
                        ),

                }

            );

        },


        update(

            resource,

            id,

            data

        ) {

            return request(

                `/${resource}/${id}`,

                {

                    method: "PATCH",


                    body:

                        JSON.stringify(
                            data
                        ),

                }

            );

        },


        archive(

            resource,

            id

        ) {

            return request(

                `/${resource}/${id}/archive`,

                {

                    method: "POST",

                }

            );

        },


        // =========================
        // MATCHES
        // =========================

        matchesList(params = {}) {

            const query =
                queryString(params);


            return request(

                `/matches` +

                `${query ? `?${query}` : ""}`

            );

        },


        matchCreate(data) {

            return request(

                "/matches",

                {

                    method: "POST",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        matchGet(matchId) {

            return request(

                `/matches/${matchId}`

            );

        },


        matchUpdate(

            matchId,

            data

        ) {

            return request(

                `/matches/${matchId}`,

                {

                    method: "PATCH",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        matchSetToss(

            matchId,

            data

        ) {

            return request(

                `/matches/${matchId}/toss`,

                {

                    method: "PUT",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        matchSquad(

            matchId,

            teamId

        ) {

            return request(

                `/matches/${matchId}/squads/${teamId}`

            );

        },


        matchSetPlayingTeam(

            matchId,

            teamId,

            data

        ) {

            return request(

                `/matches/${matchId}/playing-team/${teamId}`,

                {

                    method: "PUT",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        matchSetupInnings(

            matchId,

            data

        ) {

            return request(

                `/matches/${matchId}/opening-innings`,

                {

                    method: "PUT",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        matchMarkReady(matchId) {

            return request(

                `/matches/${matchId}/ready`,

                {

                    method: "POST",

                }

            );

        },


        // =========================
        // SCORING
        // =========================

        scoringGet(matchId) {

            return request(

                `/matches/${matchId}/scoring`

            );

        },


        scoringRecord(

            matchId,

            data,

            options = {}

        ) {

            return request(

                `/matches/${matchId}/scoring/deliveries`,

                {

                    ...options,

                    method: "POST",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        scoringRecordDelivery(

            matchId,

            data,

            options = {}

        ) {

            return this.scoringRecord(

                matchId,

                data,

                options

            );

        },


        scoringUndoDelivery(

            matchId,

            deliveryId,

            data

        ) {

            return request(

                `/matches/${matchId}/scoring/deliveries/${deliveryId}/undo`,

                {

                    method: "POST",


                    body:

                        JSON.stringify(
                            data
                        ),

                }

            );

        },


        scoringChangeBowler(

            matchId,

            data

        ) {

            return request(

                `/matches/${matchId}/scoring/bowler`,

                {

                    method: "PUT",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        scoringEndInnings(matchId) {

            return request(

                `/matches/${matchId}/scoring/innings/end`,

                {

                    method: "POST",

                }

            );

        },


        scoringStartNextInnings(

            matchId,

            data

        ) {

            return request(

                `/matches/${matchId}/scoring/innings`,

                {

                    method: "POST",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        // =========================
        // STAGE 10
        // RETIREMENTS & LIVE ORDER
        // =========================

        scoringRetire(matchId, data) {

            return request(

                `/matches/${matchId}/scoring/retirements`,

                {

                    method: "POST",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        scoringUndoRetirement(

            matchId,

            retirementId,

            data

        ) {

            return request(

                `/matches/${matchId}/scoring/retirements/${retirementId}/undo`,

                {

                    method: "POST",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        scoringBattingOrderGet(matchId) {

            return request(

                `/matches/${matchId}/scoring/batting-order`

            );

        },


        scoringBattingOrderUpdate(

            matchId,

            data

        ) {

            return request(

                `/matches/${matchId}/scoring/batting-order`,

                {

                    method: "PATCH",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        // =========================
        // STAGE 6
        // SCORECARD
        // =========================

        scorecardGet(matchId) {

            return request(

                `/matches/${matchId}/scorecard`

            );

        },


        // =========================
        // TEAM SQUADS
        // =========================

        teamSquad(teamId) {

            return request(

                `/teams/${teamId}/squad`

            );

        },


        teamSquadAdd(

            teamId,

            data

        ) {

            return request(

                `/teams/${teamId}/squad`,

                {

                    method: "POST",

                    body:
                        JSON.stringify(data),

                }

            );

        },


        teamSquadRemove(

            teamId,

            playerId

        ) {

            return request(

                `/teams/${teamId}/squad/${playerId}/deactivate`,

                {

                    method: "POST",

                }

            );

        },


        // =========================
        // STAGE 9 - PLAYER PROFILE
        // =========================

        playerProfile(playerId) {

            return request(

                `/players/${playerId}/profile`

            );

        },


        playerMatchHistory(

            playerId,

            params = {}

        ) {

            const query =
                queryString(params);


            return request(

                `/players/${playerId}/match-history` +

                `${query ? `?${query}` : ""}`

            );

        },


        // =========================
        // STAGE 11 - TOURNAMENTS
        // =========================

        tournament: {

            get: (id) => request(`/tournaments/${id}/details`),

            create: (data) => request("/tournaments", { method: "POST", body: JSON.stringify(data) }),

            updateBasics: (id, data) => request(`/tournaments/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

            configure: (id, data) => request(`/tournaments/${id}/configuration`, { method: "PATCH", body: JSON.stringify(data) }),

            readiness: (id) => request(`/tournaments/${id}/readiness`),

            transitions: (id) => request(`/tournaments/${id}/transitions`),

            transition: (id, data) => request(`/tournaments/${id}/transitions`, { method: "POST", body: JSON.stringify(data) }),

            publish: (id, publish) => request(`/tournaments/${id}/publication`, { method: "POST", body: JSON.stringify({ publish }) }),

            audit: (id) => request(`/tournaments/${id}/audit?limit=50`),

            preset: (formatCode) => request(`/tournaments/presets/${formatCode}`),

            validateRules: (rules) => request("/tournaments/rules/validate", { method: "POST", body: JSON.stringify({ rules }) }),

            rules: (id) => request(`/tournaments/${id}/rules`),

            createRules: (id, rules) => request(`/tournaments/${id}/rules`, { method: "POST", body: JSON.stringify({ rules }) }),

            propagate: (id, data) => request(`/tournaments/${id}/rules/propagate`, { method: "POST", body: JSON.stringify(data) }),

            async currentRules(id) {

                try {

                    return await request(`/tournaments/${id}/rules/current`);

                } catch (error) {

                    if (error.status === 404) {

                        return null;

                    }

                    throw error;

                }

            },

            // The endpoint is paginated; this collects every page for the
            // workspace, which filters and pages the table client-side.
            async teams(id, status) {
                const items = [];
                let page = 1;
                let pages = 1;
                do {
                    const result = await request(`/tournaments/${id}/teams?${queryString({ registration_status: status, page, page_size: 100 })}`);
                    items.push(...result.items);
                    pages = result.pages || 1;
                    page += 1;
                } while (page <= pages);
                return items;
            },

            teamsPage: (id, params = {}) => request(`/tournaments/${id}/teams?${queryString(params)}`),

            promote: (id, membershipId, data) => request(`/tournaments/${id}/teams/${membershipId}/promotion`, { method: "POST", body: JSON.stringify(data) }),

            deductions: (id) => request(`/tournaments/${id}/deductions`),

            deduct: (id, data) => request(`/tournaments/${id}/deductions`, { method: "POST", body: JSON.stringify(data) }),

            revokeDeduction: (id, deductionId, reason) => request(`/tournaments/${id}/deductions/${deductionId}/revocation`, { method: "POST", body: JSON.stringify({ reason }) }),

            assets: (id) => request(`/tournaments/${id}/assets`),

            // Raw-body upload; the server verifies the real image type.
            uploadAsset: (id, kind, file) => request(`/tournaments/${id}/assets/${kind}`, {
                method: "PUT",
                body: file,
                headers: {
                    "Content-Type": file.type || "application/octet-stream",
                    "X-Filename": encodeURIComponent(file.name || ""),
                },
            }),

            clearAsset: (id, kind) => request(`/tournaments/${id}/assets/${kind}`, { method: "DELETE" }),

            register: (id, data) => request(`/tournaments/${id}/teams`, { method: "POST", body: JSON.stringify(data) }),

            invite: (id, data) => request(`/tournaments/${id}/teams/invitations`, { method: "POST", body: JSON.stringify(data) }),

            decide: (id, membershipId, data) => request(`/tournaments/${id}/teams/${membershipId}/decision`, { method: "POST", body: JSON.stringify(data) }),

            withdraw: (id, membershipId, reason) => request(`/tournaments/${id}/teams/${membershipId}/withdrawal`, { method: "POST", body: JSON.stringify({ reason }) }),

            assignGroup: (id, membershipId, groupId) => request(`/tournaments/${id}/teams/${membershipId}/group`, { method: "PUT", body: JSON.stringify({ group_id: groupId }) }),

            setCaptain: (id, membershipId, playerId) => request(`/tournaments/${id}/teams/${membershipId}/captain`, { method: "PUT", body: JSON.stringify({ player_id: playerId }) }),

            roster: (id, membershipId) => request(`/tournaments/${id}/teams/${membershipId}/roster`),

            rosterCandidates: (id, membershipId) => request(`/tournaments/${id}/teams/${membershipId}/roster/candidates`),

            rosterAdd: (id, membershipId, data) => request(`/tournaments/${id}/teams/${membershipId}/roster`, { method: "POST", body: JSON.stringify(data) }),

            rosterRemove: (id, membershipId, playerId) => request(`/tournaments/${id}/teams/${membershipId}/roster/${playerId}`, { method: "DELETE" }),

            rosterAvailability: (id, membershipId, playerId, data) => request(`/tournaments/${id}/teams/${membershipId}/roster/${playerId}/availability`, { method: "PATCH", body: JSON.stringify(data) }),

            lockRosters: (id, reason) => request(`/tournaments/${id}/rosters/lock`, { method: "POST", body: JSON.stringify({ reason: reason || null }) }),

            groups: (id) => request(`/tournaments/${id}/groups`),

            createGroup: (id, data) => request(`/tournaments/${id}/groups`, { method: "POST", body: JSON.stringify(data) }),

            deleteGroup: (id, groupId) => request(`/tournaments/${id}/groups/${groupId}`, { method: "DELETE" }),

            venues: (id) => request(`/tournaments/${id}/venues`),

            addVenue: (id, venueId) => request(`/tournaments/${id}/venues`, { method: "POST", body: JSON.stringify({ venue_id: venueId }) }),

            removeVenue: (id, venueId) => request(`/tournaments/${id}/venues/${venueId}`, { method: "DELETE" }),

        },


        tournamentSeries: {

            list: (params = {}) => request(`/tournament-series?${queryString({ page_size: 100, ...params })}`),

            create: (data) => request("/tournament-series", { method: "POST", body: JSON.stringify(data) }),

            editions: (seriesId) => request(`/tournament-series/${seriesId}/editions`),

        },


        // =========================
        // PAGINATION HELPER
        // =========================

        async listAll(

            resource,

            params = {}

        ) {

            const items = [];


            let page = 1;

            let pages = 1;


            do {

                const result =

                    await this.list(

                        resource,

                        {

                            ...params,

                            page,

                            page_size: 100,

                        }

                    );


                items.push(

                    ...(result.items || [])

                );


                pages =
                    result.pages || 1;


                page += 1;


            } while (page <= pages);


            return items;

        },

    };


    // =========================
    // TOAST NOTIFICATIONS
    // =========================

    window.showToast =

        function showToast(

            message,

            type = "success"

        ) {

            const container =

                document.getElementById(
                    "toast-container"
                );


            if (!container) {

                return;

            }


            const toast =

                document.createElement(
                    "div"
                );


            toast.className =

                `toast toast-${type}`;


            toast.textContent =
                message;


            container.appendChild(
                toast
            );


            requestAnimationFrame(

                () => {

                    toast.classList.add(
                        "visible"
                    );

                }

            );


            window.setTimeout(

                () => {

                    toast.classList.remove(
                        "visible"
                    );


                    window.setTimeout(

                        () => toast.remove(),

                        220

                    );

                },

                3200

            );

        };


})();
