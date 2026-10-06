(() => {

    "use strict";


    const BASE_DELAY_MS =
        800;


    const MAX_DELAY_MS =
        10000;


    function socketUrl(
        matchId
    ) {

        const protocol =
            window.location.protocol
            === "https:"

                ? "wss"

                : "ws";


        return (

            `${protocol}://`
            + `${window.location.host}`
            + `/matches/${matchId}/live`

        );

    }


    function setIndicator(
        status,
        label
    ) {

        document
            .querySelectorAll(
                "[data-live-connection-status]"
            )
            .forEach(
                (
                    element
                ) => {

                    element
                        .dataset
                        .status =
                        status;


                    element
                        .textContent =
                        label;

                }
            );

    }


    function connect(
        matchId,
        onEvent
    ) {

        let socket =
            null;


        let stopped =
            false;


        let retryCount =
            0;


        let retryTimer =
            null;


        let pingTimer =
            null;


        function clearPing() {

            if (
                pingTimer
                !== null
            ) {

                window.clearInterval(
                    pingTimer
                );


                pingTimer =
                    null;

            }

        }


        function scheduleReconnect() {

            if (
                stopped
            ) {

                return;

            }


            retryCount +=
                1;


            const delay =
                Math.min(

                    BASE_DELAY_MS
                    * (
                        2
                        ** (
                            retryCount
                            - 1
                        )
                    ),

                    MAX_DELAY_MS
                );


            setIndicator(
                "reconnecting",
                "Reconnecting…"
            );


            retryTimer =
                window.setTimeout(

                    open,

                    delay

                );

        }


        function open() {

            if (
                stopped
            ) {

                return;

            }


            setIndicator(

                retryCount === 0
                    ? "connecting"
                    : "reconnecting",

                retryCount === 0
                    ? "Connecting…"
                    : "Reconnecting…"

            );


            socket =
                new WebSocket(
                    socketUrl(
                        matchId
                    )
                );


            socket.addEventListener(
                "open",
                () => {

                    retryCount =
                        0;


                    setIndicator(
                        "live",
                        "Live"
                    );


                    clearPing();


                    pingTimer =
                        window.setInterval(

                            () => {

                                if (
                                    socket
                                    &&
                                    socket
                                        .readyState
                                    ===
                                    WebSocket.OPEN
                                ) {

                                    socket.send(
                                        "ping"
                                    );

                                }

                            },

                            20000

                        );

                }
            );


            socket.addEventListener(
                "message",
                (
                    message
                ) => {

                    if (
                        message.data
                        === "pong"
                    ) {

                        return;

                    }


                    try {

                        const event =
                            JSON.parse(
                                message.data
                            );


                        onEvent(
                            event
                        );

                    }

                    catch (
                        error
                    ) {

                        console.error(
                            (
                                "Invalid "
                                + "live match event"
                            ),
                            error
                        );

                    }

                }
            );


            socket.addEventListener(
                "close",
                () => {

                    clearPing();


                    scheduleReconnect();

                }
            );


            socket.addEventListener(
                "error",
                () => {

                    if (
                        socket
                    ) {

                        socket.close();

                    }

                }
            );

        }


        open();


        return () => {

            stopped =
                true;


            if (
                retryTimer
                !== null
            ) {

                window.clearTimeout(
                    retryTimer
                );

            }


            clearPing();


            if (
                socket
            ) {

                socket.close();

            }


            setIndicator(
                "offline",
                "Offline"
            );

        };

    }


    window.MatchLive = {
        connect,
    };

})();