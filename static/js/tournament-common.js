/*
 * Stage 11 shared tournament UI helpers.
 *
 * Used by the tournament list, the create/edit wizard and the tournament
 * workspace. All user-supplied text is rendered through escapeHtml, so
 * descriptions and terms are always displayed as plain text.
 */
(() => {

    "use strict";


    const STATUS_LABELS = {
        draft: "Draft",
        registration_open: "Registration open",
        registration_closed: "Registration closed",
        scheduled: "Scheduled",
        live: "Live",
        active: "Active (legacy)",
        completed: "Completed",
        suspended: "Suspended",
        cancelled: "Cancelled",
        archived: "Archived",
        pending: "Pending",
        approved: "Approved",
        rejected: "Rejected",
        withdrawn: "Withdrawn",
    };

    const LIFECYCLE_PATH = [
        "draft",
        "registration_open",
        "registration_closed",
        "scheduled",
        "live",
        "completed",
        "archived",
    ];

    // Statuses where competition configuration can no longer change.
    const CONFIG_LOCKED = new Set(["scheduled", "live", "completed", "cancelled", "archived"]);
    const RULES_LOCKED = new Set(["live", "completed", "cancelled", "archived"]);
    const FINAL = new Set(["completed", "cancelled", "archived"]);


    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }


    function statusLabel(status) {
        return STATUS_LABELS[status] || String(status || "").replaceAll("_", " ");
    }


    function statusBadge(status, label) {
        return `<span class="status-badge status-${escapeHtml(status)}">${escapeHtml(label || statusLabel(status))}</span>`;
    }


    function initials(name) {
        const words = String(name || "?").trim().split(/\s+/).filter(Boolean);
        return ((words[0]?.[0] || "?") + (words[1]?.[0] || "")).toUpperCase();
    }


    // Logo uploads need object storage (not configured yet); this is the
    // documented fallback mark.
    function logoMark(name, small = false) {
        return `<span class="tournament-logo${small ? " small" : ""}" aria-hidden="true">${escapeHtml(initials(name))}</span>`;
    }


    function formatDate(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(`${value}T00:00:00`);
        return Number.isNaN(date.getTime())
            ? value
            : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    }


    function formatDateTime(value, timeZone) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        try {
            return date.toLocaleString(undefined, {
                day: "numeric",
                month: "short",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                timeZone: timeZone || undefined,
                timeZoneName: timeZone ? "short" : undefined,
            });
        } catch {
            return date.toLocaleString();
        }
    }


    // <input type="datetime-local"> works in the browser's zone; the API
    // requires timezone-aware values, so convert both ways.
    function toLocalInput(iso) {
        if (!iso) {
            return "";
        }
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        const offset = date.getTimezoneOffset() * 60000;
        return new Date(date.getTime() - offset).toISOString().slice(0, 16);
    }


    function fromLocalInput(value) {
        return value ? new Date(value).toISOString() : null;
    }


    function errorText(error) {
        return error?.message || "Something went wrong.";
    }


    function isForbidden(error) {
        return error?.status === 403;
    }


    // =========================
    // FORM FIELD DEFINITIONS
    // =========================

    const CATEGORY_OPTIONS = ["International", "Domestic", "Franchise", "Club", "School", "University", "Corporate", "Indoor", "Gully", "Community"];
    const SCOPE_OPTIONS = ["International", "National", "Regional", "Provincial", "City", "District", "School", "Community"];
    const TIMEZONE_OPTIONS = [
        "UTC", "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka", "Asia/Colombo", "Asia/Kabul", "Asia/Dubai",
        "Europe/London", "Africa/Johannesburg", "Australia/Sydney", "Pacific/Auckland", "America/Barbados",
    ];

    const BASIC_FIELDS = [
        { name: "name", label: "Tournament name", type: "text", required: true, max: 160, wide: true },
        { name: "season", label: "Season / edition", type: "text", max: 40, placeholder: "2026 or Edition 7" },
        { name: "organizer", label: "Organizer", type: "text", max: 160 },
        { name: "slug", label: "URL slug", type: "text", max: 180, placeholder: "Generated from name and season", hint: "Letters, numbers and dashes" },
        { name: "start_date", label: "Start date", type: "date" },
        { name: "end_date", label: "End date", type: "date" },
        { name: "description", label: "Description", type: "textarea", wide: true, hint: "Shown as plain text; HTML is never rendered." },
    ];

    const IDENTITY_FIELDS = [
        { section: "Identity" },
        { name: "code", label: "Tournament code", type: "text", max: 40, placeholder: "e.g. PSL26", hint: "Unique short code" },
        { name: "category", label: "Category", type: "text", max: 80, list: CATEGORY_OPTIONS },
        { name: "geographic_scope", label: "Geographic scope", type: "text", max: 80, list: SCOPE_OPTIONS },
        { name: "location", label: "Location", type: "text", max: 160, placeholder: "City, country" },
        { name: "timezone", label: "Time zone", type: "text", max: 80, list: TIMEZONE_OPTIONS, fallback: "UTC", required: true, hint: "IANA name, e.g. Asia/Karachi" },
        { section: "Branding" },
        { name: "sponsor", label: "Title sponsor", type: "text", max: 160 },
        { name: "trophy_name", label: "Trophy name", type: "text", max: 160 },
        { name: "website", label: "Website", type: "url", max: 500, placeholder: "https://" },
        { section: "Contacts" },
        { name: "contact_email", label: "Contact email", type: "email", max: 254 },
        { name: "contact_phone", label: "Contact phone", type: "tel", max: 40 },
        { name: "terms", label: "Terms & conditions", type: "textarea", wide: true },
    ];

    const PARTICIPATION_FIELDS = [
        { section: "Team entry" },
        { name: "minimum_teams", label: "Minimum teams", type: "number", min: 2, fallback: 2, required: true },
        { name: "maximum_teams", label: "Maximum teams", type: "number", min: 2, placeholder: "No limit" },
        { name: "expected_teams", label: "Expected teams", type: "number", min: 2 },
        { name: "reserve_team_limit", label: "Reserve teams", type: "number", min: 0, fallback: 0, required: true, hint: "Waiting list once the draw is full" },
        {
            name: "registration_mode", label: "Registration", type: "select", fallback: "open", required: true,
            options: [["open", "Open — teams can register"], ["invitational", "Invitational — organizer invites"]],
        },
        { name: "entry_requires_approval", label: "Entries require organizer approval", type: "checkbox" },
        { section: "Windows and deadlines" },
        { name: "registration_opens_at", label: "Registration opens", type: "datetime" },
        { name: "registration_closes_at", label: "Registration closes", type: "datetime" },
        { name: "roster_lock_at", label: "Roster lock deadline", type: "datetime" },
        { name: "replacement_cutoff_at", label: "Replacement cutoff", type: "datetime" },
        { section: "Venue" },
        { name: "primary_venue_id", label: "Primary venue", type: "select", options: [], wide: true, hint: "Automatically added to the permitted venues" },
    ];


    function fieldValue(def, values) {
        const value = values?.[def.name];
        if (value === null || value === undefined) {
            return def.fallback ?? "";
        }
        return def.type === "datetime" ? toLocalInput(value) : value;
    }


    function renderFields(defs, values = {}, overrides = {}) {
        return defs.map((def) => {
            if (def.section) {
                return `<p class="form-section-title">${escapeHtml(def.section)}</p>`;
            }

            const value = fieldValue(def, values);
            const required = def.required ? " required" : "";
            const label = `<span>${escapeHtml(def.label)}${def.required ? " <em>*</em>" : ""}</span>`;
            const hint = def.hint ? `<small class="field-hint">${escapeHtml(def.hint)}</small>` : "";
            const wide = def.wide || def.type === "textarea" ? " form-field-wide" : "";
            let control;

            if (def.type === "checkbox") {
                return `
                    <div class="form-field${wide}">
                        <span>&nbsp;</span>
                        <label class="checkbox-field">
                            <input type="checkbox" name="${def.name}" ${value === true ? "checked" : ""}>
                            ${escapeHtml(def.label)}
                        </label>
                    </div>`;
            }

            if (def.type === "textarea") {
                control = `<textarea name="${def.name}" rows="4">${escapeHtml(value)}</textarea>`;
            } else if (def.type === "select") {
                const options = overrides[def.name] || def.options || [];
                const blank = def.required ? "" : `<option value="">— None —</option>`;
                control = `<select name="${def.name}"${required}>${blank}${options.map(([optionValue, optionLabel]) => `
                    <option value="${escapeHtml(optionValue)}" ${String(optionValue) === String(value) ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`).join("")}
                </select>`;
            } else {
                const type = def.type === "datetime" ? "datetime-local" : def.type;
                const attributes = [
                    def.max && def.type !== "number" ? `maxlength="${def.max}"` : "",
                    def.min !== undefined ? `min="${def.min}"` : "",
                    def.placeholder ? `placeholder="${escapeHtml(def.placeholder)}"` : "",
                    def.list ? `list="list-${def.name}"` : "",
                ].join(" ");
                const datalist = def.list
                    ? `<datalist id="list-${def.name}">${def.list.map((item) => `<option value="${escapeHtml(item)}">`).join("")}</datalist>`
                    : "";
                control = `<input name="${def.name}" type="${type}" value="${escapeHtml(value)}" ${attributes}${required}>${datalist}`;
            }

            return `<label class="form-field${wide}">${label}${control}${hint}</label>`;
        }).join("");
    }


    function readFields(form, defs) {
        const payload = {};

        defs.filter((def) => def.name).forEach((def) => {
            const input = form.elements[def.name];
            if (!input) {
                return;
            }

            let value;
            if (def.type === "checkbox") {
                value = input.checked;
            } else if (def.type === "number") {
                value = input.value === "" ? null : Number(input.value);
            } else if (def.type === "datetime") {
                value = fromLocalInput(input.value);
            } else {
                value = input.value.trim() === "" ? null : input.value.trim();
            }

            if (value === null && def.fallback !== undefined) {
                value = def.fallback;
            }

            payload[def.name] = value;
        });

        return payload;
    }


    // =========================
    // RULES EDITOR
    // =========================

    const FORMAT_OPTIONS = [
        ["t20", "T20"],
        ["odi", "ODI (50 overs)"],
        ["t10", "T10"],
        ["hundred", "Hundred-style (custom)"],
        ["indoor", "Indoor"],
        ["gully", "Gully / street"],
        ["custom", "Custom"],
    ];

    const STRUCTURE_OPTIONS = [
        ["single_round_robin", "Single round-robin (league)"],
        ["double_round_robin", "Double round-robin"],
        ["knockout", "Knockout"],
        ["groups_knockout", "Group stage, then knockout"],
        ["hybrid", "Manually configured hybrid"],
    ];

    const TIE_BREAKERS = [
        ["points", "Points"],
        ["wins", "Wins"],
        ["net_run_rate", "Net run rate"],
        ["head_to_head", "Head-to-head"],
        ["wickets", "Wickets"],
        ["drawing_of_lots", "Drawing of lots (always last)"],
    ];

    const OUTCOMES = [
        ["win", "Win"],
        ["tie", "Tie"],
        ["no_result", "No result"],
        ["draw", "Draw"],
        ["forfeit", "Forfeit / walkover"],
        ["abandoned", "Abandoned"],
        ["postponed", "Postponed"],
    ];

    // The explicit capability matrix: what the Stage 3–10 scoring engine
    // can honour. `active` says whether the current rules use the feature.
    const CAPABILITIES = [
        { label: "Custom overs per innings", supported: true, active: () => true },
        { label: "Custom players per side", supported: true, active: () => true },
        { label: "Points table & tie-breaker definitions", supported: true, active: () => true, note: "Standings are computed in Stage 13" },
        { label: "Win / tie outcomes", supported: true, active: (r) => r.allowed_outcomes.some((o) => o === "win" || o === "tie") },
        { label: "Non-6-ball overs", supported: false, active: (r) => r.balls_per_over !== 6 },
        { label: "Multiple innings per team", supported: false, active: (r) => r.innings_per_team !== 1 },
        { label: "Starting with fewer than a full side", supported: false, active: (r) => r.minimum_players_to_start !== r.players_per_side },
        { label: "Hundred-style sets & bowler allocation", supported: false, active: (r) => r.format_code === "hundred" },
        { label: "Indoor cricket scoring", supported: false, active: (r) => r.format_code === "indoor" },
        { label: "Super over / tie-break", supported: false, active: (r) => r.super_over_enabled },
        { label: "DLS / target adjustment", supported: false, active: (r) => r.dls_enabled },
        { label: "Impact player substitutions", supported: false, active: (r) => r.impact_player_enabled },
        { label: "Reduced-overs adjustment", supported: false, active: (r) => r.reduced_overs_enabled },
        { label: "Powerplay enforcement", supported: false, active: (r) => r.powerplay_segments.length > 0 },
        { label: "Per-match rule overrides", supported: false, active: (r) => r.allow_match_overrides },
        { label: "Outcomes beyond win / tie", supported: false, active: (r) => r.allowed_outcomes.some((o) => o !== "win" && o !== "tie") },
        { label: "Overseas-player limits", supported: false, active: (r) => r.overseas_player_limit !== null },
        { label: "Best-of-N finals", supported: false, active: (r) => r.best_of_finals > 1 },
        { label: "Bonus points", supported: false, active: (r) => r.points.bonus_points_enabled },
    ];


    function numberField(name, label, value, { min = 0, hint = "", placeholder = "" } = {}) {
        return `
            <label class="form-field">
                <span>${escapeHtml(label)}</span>
                <input type="number" data-rule="${name}" min="${min}" value="${value ?? ""}" placeholder="${escapeHtml(placeholder)}">
                ${hint ? `<small class="field-hint">${escapeHtml(hint)}</small>` : ""}
            </label>`;
    }


    function toggle(name, label, checked) {
        return `
            <label class="checkbox-field">
                <input type="checkbox" data-rule="${name}" ${checked ? "checked" : ""}>
                ${escapeHtml(label)}
            </label>`;
    }


    /**
     * Mounts the rules & format editor.
     *
     * options.rules       initial TournamentRules object (or null for T20 preset)
     * options.disabled    render read-only
     * options.capability  element that receives the capability matrix
     */
    function mountRulesEditor(container, options = {}) {
        let rules = null;
        let validationTimer = null;
        let lastValidation = { valid: false, errors: [] };
        let tieOrder = [];

        const capability = options.capability;

        async function init() {
            const initial = options.rules || await API.tournament.preset("t20");
            setRules(initial);
        }

        function setRules(next) {
            rules = structuredClone(next);
            tieOrder = [
                ...rules.tie_breakers,
                ...TIE_BREAKERS.map(([value]) => value).filter((value) => !rules.tie_breakers.includes(value)),
            ];
            render();
            scheduleValidation(0);
        }

        function render() {
            const r = rules;
            const disabled = options.disabled ? "disabled" : "";
            const showGroups = r.structure === "groups_knockout" || r.structure === "hybrid";

            container.innerHTML = `
                <div class="rules-editor">
                    <fieldset ${disabled}>
                        <legend>Format preset & competition structure</legend>
                        <div class="form-grid">
                            <label class="form-field">
                                <span>Format</span>
                                <select data-rule="format_code">
                                    ${FORMAT_OPTIONS.map(([v, l]) => `<option value="${v}" ${v === r.format_code ? "selected" : ""}>${l}</option>`).join("")}
                                </select>
                                <button class="button button-secondary button-small" type="button" data-action="apply-preset">
                                    Load preset defaults for this format
                                </button>
                            </label>
                            <label class="form-field">
                                <span>Competition structure</span>
                                <select data-rule="structure">
                                    ${STRUCTURE_OPTIONS.map(([v, l]) => `<option value="${v}" ${v === r.structure ? "selected" : ""}>${l}</option>`).join("")}
                                </select>
                            </label>
                            ${showGroups ? numberField("teams_per_group", "Teams per group", r.teams_per_group, { min: 2, hint: "Required for group stage formats" }) : ""}
                            ${numberField("best_of_finals", "Finals series (best of N)", r.best_of_finals, { min: 1, hint: "Odd number; 1 = single final" })}
                        </div>
                    </fieldset>

                    <fieldset ${disabled}>
                        <legend>Match format</legend>
                        <div class="form-grid">
                            ${numberField("overs_per_innings", "Overs per innings", r.overs_per_innings, { min: 1 })}
                            ${numberField("balls_per_over", "Legal balls per over", r.balls_per_over, { min: 1, hint: "Normally 6" })}
                            ${numberField("innings_per_team", "Innings per team", r.innings_per_team, { min: 1 })}
                            ${numberField("players_per_side", "Players per side", r.players_per_side, { min: 2 })}
                            ${numberField("minimum_players_to_start", "Minimum players to start", r.minimum_players_to_start, { min: 2 })}
                            <label class="form-field">
                                <span>Bowler quota policy</span>
                                <input type="text" value="Scoring engine default" disabled>
                            </label>
                            ${numberField("mandatory_break_minutes", "Innings break (minutes)", r.mandatory_break_minutes)}
                            ${numberField("innings_time_minutes", "Innings time allowance (minutes)", r.innings_time_minutes, { min: 1, placeholder: "No limit" })}
                            ${numberField("timeout_minutes", "Strategic timeout (minutes)", r.timeout_minutes)}
                        </div>
                    </fieldset>

                    <fieldset ${disabled}>
                        <legend>Squad rules</legend>
                        <div class="form-grid">
                            ${numberField("minimum_roster_size", "Minimum squad size", r.minimum_roster_size, { min: 2 })}
                            ${numberField("maximum_roster_size", "Maximum squad size", r.maximum_roster_size, { min: 2 })}
                            ${numberField("overseas_player_limit", "Overseas players per XI", r.overseas_player_limit, { placeholder: "No limit" })}
                        </div>
                    </fieldset>

                    <fieldset ${disabled}>
                        <legend>Points</legend>
                        <div class="form-grid">
                            ${["win", "tie", "no_result", "draw", "loss", "forfeit"].map((key) => numberField(`points.${key}`, `${key.replace("_", " ")} points`.replace(/^./, (c) => c.toUpperCase()), r.points[key])).join("")}
                        </div>
                        <div style="margin-top:12px">${toggle("points.bonus_points_enabled", "Bonus points", r.points.bonus_points_enabled)}</div>
                    </fieldset>

                    <fieldset ${disabled}>
                        <legend>Tie-break priority</legend>
                        <ol class="tie-breaker-list">
                            ${tieOrder.map((value, index) => {
                                const on = r.tie_breakers.includes(value);
                                const label = TIE_BREAKERS.find(([v]) => v === value)?.[1] || value;
                                return `
                                    <li class="${on ? "" : "off"}">
                                        <input type="checkbox" data-tie="${value}" ${on ? "checked" : ""}>
                                        <span>${escapeHtml(label)}</span>
                                        <span class="order-buttons">
                                            <button class="icon-button" type="button" data-move="${index}" data-direction="-1" ${index === 0 ? "disabled" : ""} aria-label="Move up">↑</button>
                                            <button class="icon-button" type="button" data-move="${index}" data-direction="1" ${index === tieOrder.length - 1 ? "disabled" : ""} aria-label="Move down">↓</button>
                                        </span>
                                    </li>`;
                            }).join("")}
                        </ol>
                    </fieldset>

                    <fieldset ${disabled}>
                        <legend>Outcomes & special rules</legend>
                        <p class="field-hint" style="margin:0 0 10px">Options marked unsupported in the capability check block activation until the scoring engine supports them.</p>
                        <div class="toggle-grid">
                            ${OUTCOMES.map(([v, l]) => `
                                <label class="checkbox-field">
                                    <input type="checkbox" data-outcome="${v}" ${r.allowed_outcomes.includes(v) ? "checked" : ""}>
                                    Outcome: ${escapeHtml(l)}
                                </label>`).join("")}
                        </div>
                        <div class="toggle-grid" style="margin-top:14px">
                            ${toggle("super_over_enabled", "Super over tie-break", r.super_over_enabled)}
                            ${toggle("dls_enabled", "DLS target adjustment", r.dls_enabled)}
                            ${toggle("impact_player_enabled", "Impact player", r.impact_player_enabled)}
                            ${toggle("reduced_overs_enabled", "Reduced-overs games", r.reduced_overs_enabled)}
                            ${toggle("allow_match_overrides", "Approved per-match overrides", r.allow_match_overrides)}
                        </div>
                        <div style="margin-top:16px">
                            <p class="form-section-title" style="margin-bottom:8px">Powerplay segments</p>
                            ${r.powerplay_segments.map((segment, index) => `
                                <div class="powerplay-row">
                                    <label class="form-field"><span>From over</span><input type="number" min="1" data-pp="${index}" data-pp-key="from_over" value="${segment.from_over ?? ""}"></label>
                                    <label class="form-field"><span>To over</span><input type="number" min="1" data-pp="${index}" data-pp-key="to_over" value="${segment.to_over ?? ""}"></label>
                                    <button class="button button-secondary button-small" type="button" data-pp-remove="${index}">Remove</button>
                                </div>`).join("")}
                            <button class="button button-secondary button-small" type="button" data-action="add-powerplay">+ Add powerplay</button>
                        </div>
                    </fieldset>
                </div>`;
        }

        function readValue(name) {
            const input = container.querySelector(`[data-rule="${CSS.escape(name)}"]`);
            if (!input) {
                return undefined;
            }
            if (input.type === "checkbox") {
                return input.checked;
            }
            if (input.type === "number") {
                return input.value === "" ? null : Number(input.value);
            }
            return input.value;
        }

        function collect() {
            const next = structuredClone(rules);

            container.querySelectorAll("[data-rule]").forEach((input) => {
                const name = input.dataset.rule;
                const value = readValue(name);
                if (name.startsWith("points.")) {
                    next.points[name.slice(7)] = value ?? 0;
                } else {
                    next[name] = value;
                }
            });

            if (next.structure !== "groups_knockout" && next.structure !== "hybrid") {
                next.teams_per_group = null;
            }

            next.tie_breakers = tieOrder.filter((value) =>
                container.querySelector(`[data-tie="${value}"]`)?.checked);
            next.allowed_outcomes = OUTCOMES.map(([value]) => value).filter((value) =>
                container.querySelector(`[data-outcome="${value}"]`)?.checked);
            next.powerplay_segments = next.powerplay_segments.map((segment, index) => {
                const from = container.querySelector(`[data-pp="${index}"][data-pp-key="from_over"]`)?.value;
                const to = container.querySelector(`[data-pp="${index}"][data-pp-key="to_over"]`)?.value;
                return { from_over: from ? Number(from) : null, to_over: to ? Number(to) : null };
            });
            next.bowler_quota_policy = "engine_default";

            rules = next;
            return next;
        }

        function renderCapability(result) {
            if (!capability) {
                return;
            }
            const r = rules;
            const header = result.schemaError
                ? `<div class="notice notice-danger"><strong>Rules are inconsistent</strong><br>${escapeHtml(result.schemaError)}</div>`
                : result.valid
                    ? `<div class="notice notice-success"><strong>Ready to activate.</strong> Every selected rule is supported by the scoring engine.</div>`
                    : `<div class="notice notice-danger"><strong>Cannot be activated yet</strong><ul>${result.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul></div>`;

            capability.innerHTML = `
                ${header}
                <ul class="capability-list" style="margin-top:12px">
                    ${CAPABILITIES.map((item) => {
                        let state = "cap-off";
                        let text = "Off";
                        try {
                            if (item.active(r)) {
                                state = item.supported ? "cap-ok" : "cap-blocked";
                                text = item.supported ? "Supported" : "Not supported";
                            } else if (item.supported) {
                                text = "Available";
                            } else {
                                text = "Off";
                            }
                        } catch {
                            // Partially edited value; leave as off.
                        }
                        return `<li><span>${escapeHtml(item.label)}${item.note ? `<br><small class="field-hint">${escapeHtml(item.note)}</small>` : ""}</span><span class="cap-state ${state}">${text}</span></li>`;
                    }).join("")}
                </ul>`;
        }

        async function validate() {
            const current = collect();
            try {
                const result = await API.tournament.validateRules(current);
                lastValidation = { ...result, schemaError: null };
            } catch (error) {
                lastValidation = { valid: false, errors: [], schemaError: errorText(error) };
            }
            renderCapability(lastValidation);
            options.onValidated?.(lastValidation);
            return lastValidation;
        }

        function scheduleValidation(delay = 350) {
            window.clearTimeout(validationTimer);
            validationTimer = window.setTimeout(validate, delay);
        }

        container.addEventListener("input", () => scheduleValidation());
        container.addEventListener("change", (event) => {
            const target = event.target;
            if (target.matches('[data-rule="structure"]') || target.matches("[data-tie]")) {
                collect();
                render();
            }
            scheduleValidation();
        });

        container.addEventListener("click", async (event) => {
            const button = event.target.closest("button");
            if (!button || options.disabled) {
                return;
            }

            if (button.dataset.action === "apply-preset") {
                const formatCode = readValue("format_code");
                try {
                    setRules(await API.tournament.preset(formatCode));
                    showToast(`Loaded ${formatCode.toUpperCase()} preset — review before saving.`, "info");
                } catch (error) {
                    showToast(errorText(error), "error");
                }
                return;
            }

            if (button.dataset.action === "add-powerplay") {
                collect();
                rules.powerplay_segments.push({ from_over: 1, to_over: 6 });
                render();
                scheduleValidation();
                return;
            }

            if (button.dataset.ppRemove !== undefined) {
                collect();
                rules.powerplay_segments.splice(Number(button.dataset.ppRemove), 1);
                render();
                scheduleValidation();
                return;
            }

            if (button.dataset.move !== undefined) {
                collect();
                const index = Number(button.dataset.move);
                const target = index + Number(button.dataset.direction);
                [tieOrder[index], tieOrder[target]] = [tieOrder[target], tieOrder[index]];
                collect();
                render();
                scheduleValidation();
            }
        });

        const ready = init();

        return {
            ready,
            getRules: () => collect(),
            setRules,
            validate,
            get lastValidation() {
                return lastValidation;
            },
        };
    }


    // =========================
    // ORGANIZER TOKEN
    // =========================

    function bindOrganizerButton(button) {
        if (!button) {
            return;
        }

        const refresh = () => {
            button.textContent = API.organizerToken() ? "Organizer token ✓" : "Organizer token";
        };

        button.addEventListener("click", () => {
            const value = window.prompt(
                "Organizer token for this browser session.\n" +
                "Required when the server sets ORGANIZER_API_TOKEN. Leave blank to clear.",
                API.organizerToken(),
            );
            if (value === null) {
                return;
            }
            API.setOrganizerToken(value.trim());
            refresh();
            showToast(value.trim() ? "Organizer token saved for this session." : "Organizer token cleared.", "info");
        });

        refresh();
    }


    window.TournamentUI = {
        STATUS_LABELS,
        LIFECYCLE_PATH,
        CONFIG_LOCKED,
        RULES_LOCKED,
        FINAL,
        BASIC_FIELDS,
        IDENTITY_FIELDS,
        PARTICIPATION_FIELDS,
        FORMAT_OPTIONS,
        STRUCTURE_OPTIONS,
        escapeHtml,
        statusLabel,
        statusBadge,
        logoMark,
        formatDate,
        formatDateTime,
        toLocalInput,
        fromLocalInput,
        errorText,
        isForbidden,
        renderFields,
        readFields,
        mountRulesEditor,
        bindOrganizerButton,
    };

})();
