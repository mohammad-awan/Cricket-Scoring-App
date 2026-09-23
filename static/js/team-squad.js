(() => {

    "use strict";


    const modal = document.getElementById("squad-modal");

    if (!modal) {
        return;
    }


    const elements = {

        title: document.getElementById("squad-modal-title"),
        addRow: document.getElementById("squad-add-row"),
        count: document.getElementById("squad-count"),
        list: document.getElementById("squad-list"),
        close: document.getElementById("close-squad-modal"),

    };


    const PLAYER_ROLES = [
        ["batter", "Batter"],
        ["bowler", "Bowler"],
        ["all_rounder", "All-rounder"],
        ["wicket_keeper", "Wicket-keeper"],
    ];


    const state = {

        team: null,
        squad: [],
        players: [],

    };


    function escapeHtml(value) {

        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");

    }


    function humanRole(value) {

        return String(value || "")
            .replaceAll("_", " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());

    }


    function render() {

        const squadIds = new Set(state.squad.map((entry) => entry.player.id));
        const addable = state.players.filter((player) => !squadIds.has(player.id));

        elements.addRow.innerHTML = addable.length === 0
            ? `<p class="muted">Every active player is already in this squad. Create more on the <a href="/master-data/players">Players</a> page.</p>`
            : `
                <div class="squad-add-form">
                    <label class="form-field">
                        <span>Player</span>
                        <select id="squad-player-select">
                            ${addable
                                .map((player) => `<option value="${player.id}">${escapeHtml(player.full_name)}</option>`)
                                .join("")}
                        </select>
                    </label>
                    <label class="form-field">
                        <span>Role</span>
                        <select id="squad-role-select">
                            ${PLAYER_ROLES
                                .map(([value, label]) => `<option value="${value}">${label}</option>`)
                                .join("")}
                        </select>
                    </label>
                    <button class="button button-primary" id="squad-add" type="button">
                        Add
                    </button>
                </div>
            `;

        const count = state.squad.length;
        elements.count.textContent = `${count} ${count === 1 ? "player" : "players"}`;

        elements.list.innerHTML = count === 0
            ? `<li class="squad-empty">No players in this squad yet. Add one above.</li>`
            : state.squad
                .map((entry) => `
                    <li class="squad-member">
                        <span class="squad-avatar">${escapeHtml(entry.player.full_name.charAt(0).toUpperCase())}</span>
                        <span class="squad-member-name">${escapeHtml(entry.player.full_name)}</span>
                        <span class="squad-role-pill">${escapeHtml(humanRole(entry.role))}</span>
                        <button type="button" class="squad-remove" data-player-id="${entry.player.id}">Remove</button>
                    </li>
                `)
                .join("");

    }


    async function refresh() {

        const [squad, players] = await Promise.all([
            window.API.teamSquad(state.team.id),
            window.API.listAll("players"),
        ]);

        state.squad = squad;
        state.players = players.filter(
            (player) => player.status === "active" && !player.archived_at
        );

        render();

    }


    function close() {

        modal.classList.add("hidden");
        document.body.classList.remove("modal-open");
        state.team = null;

    }


    window.openTeamSquad = async function openTeamSquad(team) {

        state.team = team;
        state.squad = [];
        state.players = [];

        elements.title.textContent = `${team.name} squad`;
        elements.addRow.innerHTML = `<p class="muted">Loading…</p>`;
        elements.list.innerHTML = "";

        modal.classList.remove("hidden");
        document.body.classList.add("modal-open");

        try {
            await refresh();
        } catch (error) {
            window.showToast(error.message, "error");
        }

    };


    elements.addRow.addEventListener("click", async (event) => {

        if (!event.target.closest("#squad-add")) {
            return;
        }

        const playerId = document.getElementById("squad-player-select").value;
        const role = document.getElementById("squad-role-select").value;

        try {

            await window.API.teamSquadAdd(state.team.id, { player_id: playerId, role });
            window.showToast("Player added to squad.");
            await refresh();

        } catch (error) {

            window.showToast(error.message, "error");

        }

    });


    elements.list.addEventListener("click", async (event) => {

        const button = event.target.closest(".squad-remove");

        if (!button) {
            return;
        }

        try {

            await window.API.teamSquadRemove(state.team.id, button.dataset.playerId);
            window.showToast("Player removed from squad.");
            await refresh();

        } catch (error) {

            window.showToast(error.message, "error");

        }

    });


    elements.close.addEventListener("click", close);

    modal.addEventListener("click", (event) => {

        if (event.target === modal) {
            close();
        }

    });

})();
