(() => {

    "use strict";


    const resources = [
        "teams",
        "players",
        "venues",
        "tournaments",
    ];


    async function loadTotals() {

        await Promise.all(

            resources.map(
                async (resource) => {

                    const target =
                        document.getElementById(
                            `${resource}-total`
                        );


                    if (!target) {
                        return;
                    }


                    try {

                        const result =
                            await window.API.list(
                                resource,
                                {
                                    page: 1,

                                    page_size: 1,

                                    include_archived:
                                        false,
                                }
                            );


                        target.textContent =
                            String(
                                result.total
                            );

                    }

                    catch (error) {

                        target.textContent =
                            "!";

                        target.title =
                            error.message;

                    }

                }
            )

        );

    }


    async function loadHealth() {

        const api =
            document.getElementById(
                "api-health"
            );

        const database =
            document.getElementById(
                "database-health"
            );

        const detail =
            document.getElementById(
                "health-detail"
            );


        api.className =
            "status-badge status-loading";

        database.className =
            "status-badge status-loading";


        api.textContent =
            "Checking…";

        database.textContent =
            "Checking…";


        try {

            const result =
                await window.API.health();


            const apiOkay =
                result.api?.status === "ok";

            const databaseOkay =
                result.database?.status ===
                "ok";


            api.textContent =
                apiOkay
                    ? "Healthy"
                    : result.api?.status ||
                      "Unknown";


            database.textContent =
                databaseOkay
                    ? "Healthy"
                    : result.database?.status ||
                      "Unknown";


            api.className =
                `status-badge ${
                    apiOkay
                        ? "status-active"
                        : "status-danger"
                }`;


            database.className =
                `status-badge ${
                    databaseOkay
                        ? "status-active"
                        : "status-danger"
                }`;


            detail.textContent =
                result.database?.detail ||
                "Health check completed.";

        }

        catch (error) {

            api.textContent =
                "Unavailable";

            database.textContent =
                "Unavailable";


            api.className =
                "status-badge status-danger";

            database.className =
                "status-badge status-danger";


            detail.textContent =
                error.message;

        }

    }


    document
        .getElementById(
            "refresh-health"
        )
        ?.addEventListener(
            "click",
            loadHealth
        );


    loadTotals();

    loadHealth();

})();