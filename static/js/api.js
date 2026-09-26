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
                    body: JSON.stringify(data),
                }
            );

        },


        matchGet(matchId) {

            return request(
                `/matches/${matchId}`
            );

        },


        matchUpdate(matchId, data) {

            return request(
                `/matches/${matchId}`,
                {
                    method: "PATCH",
                    body: JSON.stringify(data),
                }
            );

        },


        matchSetToss(matchId, data) {

            return request(
                `/matches/${matchId}/toss`,
                {
                    method: "PUT",
                    body: JSON.stringify(data),
                }
            );

        },


        matchSquad(matchId, teamId) {

            return request(
                `/matches/${matchId}/squads/${teamId}`
            );

        },


        matchSetPlayingTeam(matchId, teamId, data) {

            return request(
                `/matches/${matchId}/playing-team/${teamId}`,
                {
                    method: "PUT",
                    body: JSON.stringify(data),
                }
            );

        },


        matchSetupInnings(matchId, data) {

            return request(
                `/matches/${matchId}/opening-innings`,
                {
                    method: "PUT",
                    body: JSON.stringify(data),
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


        scoringGet(matchId) {

            return request(
                `/matches/${matchId}/scoring`
            );

        },


        scoringRecord(matchId, data) {

            return request(
                `/matches/${matchId}/scoring/deliveries`,
                {
                    method: "POST",
                    body: JSON.stringify(data),
                }
            );

        },


        scoringRecordDelivery(matchId, data) {

            return this.scoringRecord(
                matchId,
                data
            );

        },


        scoringChangeBowler(matchId, data) {

            return request(
                `/matches/${matchId}/scoring/bowler`,
                {
                    method: "PUT",
                    body: JSON.stringify(data),
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


        scoringStartNextInnings(matchId, data) {

            return request(
                `/matches/${matchId}/scoring/innings`,
                {
                    method: "POST",
                    body: JSON.stringify(data),
                }
            );

        },


        teamSquad(teamId) {

            return request(
                `/teams/${teamId}/squad`
            );

        },


        teamSquadAdd(teamId, data) {

            return request(
                `/teams/${teamId}/squad`,
                {
                    method: "POST",
                    body: JSON.stringify(data),
                }
            );

        },


        teamSquadRemove(teamId, playerId) {

            return request(
                `/teams/${teamId}/squad/${playerId}/deactivate`,
                {
                    method: "POST",
                }
            );

        },


        async listAll(resource, params = {}) {

            const items = [];
            let page = 1;
            let pages = 1;

            do {

                const result = await this.list(
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