(() => {

    "use strict";


    const root =
        document.getElementById(
            "master-data-page"
        );


    if (!root) {
        return;
    }


    const configs = {

        teams: {

            imageField: "logo_url",
            sourceField: "logo_source_url",
            imageKind: "logo",

            singular: "Team",

            plural: "Teams",

            subtitle:
                "Manage cricket teams used by squads and future match setup.",

            searchPlaceholder:
                "Search by team name, short name, code or country…",


            fields: [

                {
                    name: "name",
                    label: "Team name",
                    type: "text",
                    required: true,
                    maxLength: 120,
                    placeholder: "Pakistan",
                },

                {
                    name: "short_name",
                    label: "Short name",
                    type: "text",
                    required: true,
                    maxLength: 50,
                    placeholder: "Pakistan",
                },

                {
                    name: "code",
                    label: "Code",
                    type: "text",
                    required: true,
                    maxLength: 20,
                    placeholder: "PAK",
                },

                {
                    name: "country",
                    label: "Country",
                    type: "text",
                    maxLength: 80,
                    placeholder: "Pakistan",
                },

                {
                    name: "logo_url",
                    label: "Logo URL",
                    type: "text",
                    url: true,
                    maxLength: 2048,
                    placeholder: "https://example.com/team-logo.png",
                },

                {
                    name: "logo_source_url",
                    label: "Logo source URL",
                    type: "text",
                    url: true,
                    maxLength: 2048,
                    placeholder: "https://example.com/original-source",
                },

            ],


            columns: [

                {
                    key: "name",
                    label: "Team",
                },

                {
                    key: "short_name",
                    label: "Short name",
                },

                {
                    key: "code",
                    label: "Code",
                },

                {
                    key: "country",
                    label: "Country",
                },

                {
                    key: "status",
                    label: "Status",
                    status: true,
                },

            ],

        },


        players: {

            imageField: "photo_url",
            sourceField: "photo_source_url",
            imageKind: "player",

            singular: "Player",

            plural: "Players",

            subtitle:
                "Manage player identities before squad and playing-XI assignment.",

            searchPlaceholder:
                "Search by player name, nationality or external ID…",


            fields: [

                {
                    name: "full_name",
                    label: "Full name",
                    type: "text",
                    required: true,
                    maxLength: 160,
                    placeholder: "Babar Azam",
                },

                {
                    name: "short_name",
                    label: "Short name",
                    type: "text",
                    maxLength: 80,
                    placeholder: "Babar",
                },

                {
                    name: "jersey_number",
                    label: "Jersey number",
                    type: "number",
                    min: 0,
                    max: 999,
                    placeholder: "56",
                },

                {
                    name: "date_of_birth",
                    label: "Date of birth",
                    type: "date",
                },

                {
                    name: "nationality",
                    label: "Nationality",
                    type: "text",
                    maxLength: 80,
                    placeholder: "Pakistan",
                },

                {
                    name: "sex",
                    label: "Sex",
                    type: "select",

                    options: [
                        ["", "Not set"],
                        ["male", "Male"],
                        ["female", "Female"],
                    ],
                },

                {
                    name: "batting_hand",
                    label: "Batting hand",
                    type: "select",

                    options: [
                        ["", "Not set"],
                        ["right", "Right-handed"],
                        ["left", "Left-handed"],
                    ],
                },

                {
                    name: "bowling_arm",
                    label: "Bowling arm",
                    type: "select",

                    options: [
                        ["", "Not set"],
                        ["right", "Right arm"],
                        ["left", "Left arm"],
                        ["none", "Does not bowl"],
                    ],
                },

                {
                    name: "bowling_style",
                    label: "Bowling style",
                    type: "select",

                    options: [
                        ["", "Not set"],
                        ["fast", "Fast"],
                        ["fast_medium", "Fast-medium"],
                        ["medium_fast", "Medium-fast"],
                        ["medium", "Medium"],
                        ["off_break", "Off break"],
                        ["leg_break", "Leg break"],
                        ["orthodox", "Orthodox"],
                        ["wrist_spin", "Wrist spin"],
                        ["mystery_spin", "Mystery spin"],
                        ["other", "Other"],
                    ],
                },

                {
                    name: "external_id",
                    label: "External ID",
                    type: "text",
                    maxLength: 80,
                    placeholder:
                        "Optional provider ID",
                },

                {
                    name: "photo_url",
                    label: "Photo URL",
                    type: "text",
                    url: true,
                    maxLength: 2048,
                    placeholder: "https://example.com/player.jpg",
                },

                {
                    name: "photo_source_url",
                    label: "Photo source URL",
                    type: "text",
                    url: true,
                    maxLength: 2048,
                    placeholder: "https://example.com/original-source",
                },

            ],


            columns: [

                {
                    key: "full_name",
                    label: "Player",
                },

                {
                    key: "short_name",
                    label: "Short name",
                },

                {
                    key: "jersey_number",
                    label: "Jersey number",
                    format: "number",
                },

                {
                    key: "date_of_birth",
                    label: "Date of birth",
                },

                {
                    key: "nationality",
                    label: "Nationality",
                },

                {
                    key: "status",
                    label: "Status",
                    status: true,
                },

            ],

        },


        venues: {

            imageField: "image_url",
            imageKind: "venue",

            singular: "Venue",

            plural: "Venues",

            subtitle:
                "Manage grounds and stadiums used by match setup.",

            searchPlaceholder:
                "Search by venue, city or country…",


            fields: [

                {
                    name: "name",
                    label: "Venue name",
                    type: "text",
                    required: true,
                    maxLength: 160,
                    placeholder:
                        "Gaddafi Stadium",
                },

                {
                    name: "city",
                    label: "City",
                    type: "text",
                    required: true,
                    maxLength: 100,
                    placeholder: "Lahore",
                },

                {
                    name: "country",
                    label: "Country",
                    type: "text",
                    maxLength: 80,
                    placeholder: "Pakistan",
                },

                {
                    name: "address",
                    label: "Location",
                    type: "textarea",
                    wide: true,
                    placeholder:
                        "Place name or full address, e.g. Gaddafi Stadium, Lahore, Pakistan",
                },

                {
                    name: "capacity",
                    label: "Capacity",
                    type: "number",
                    min: 0,
                    placeholder: "27000",
                },

                {
                    name: "latitude",
                    type: "hidden",
                    numeric: true,
                },

                {
                    name: "longitude",
                    type: "hidden",
                    numeric: true,
                },

                {
                    name: "image_url",
                    label: "Venue image URL",
                    type: "text",
                    url: true,
                    maxLength: 2048,
                    wide: true,
                    placeholder: "https://example.com/stadium.jpg",
                },

            ],


            columns: [

                {
                    key: "name",
                    label: "Venue",
                },

                {
                    key: "city",
                    label: "City",
                },

                {
                    key: "country",
                    label: "Country",
                },

                {
                    key: "capacity",
                    label: "Capacity",
                    format: "number",
                },

                {
                    key: "coordinates",
                    label: "Location",
                    format: "coordinates",
                },

                {
                    key: "status",
                    label: "Status",
                    status: true,
                },

            ],

        },


        tournaments: {

            singular:
                "Tournament",

            plural:
                "Tournaments",

            subtitle:
                "Manage competition metadata used by matches in later stages.",

            searchPlaceholder:
                "Search by tournament, slug, season or organizer…",


            fields: [

                {
                    name: "name",
                    label:
                        "Tournament name",
                    type: "text",
                    required: true,
                    maxLength: 160,
                    placeholder:
                        "Pakistan Super League",
                },

                {
                    name: "slug",
                    label: "Slug",
                    type: "text",
                    maxLength: 180,
                    placeholder:
                        "Leave blank to auto-generate",
                },

                {
                    name: "season",
                    label: "Season",
                    type: "text",
                    maxLength: 40,
                    placeholder: "2026",
                },

                {
                    name: "organizer",
                    label: "Organizer",
                    type: "text",
                    maxLength: 160,
                    placeholder: "PCB",
                },

                {
                    name: "start_date",
                    label: "Start date",
                    type: "date",
                },

                {
                    name: "end_date",
                    label: "End date",
                    type: "date",
                },

                {
                    name: "description",
                    label: "Description",
                    type: "textarea",
                    wide: true,
                    placeholder:
                        "Optional tournament description",
                },

            ],


            columns: [

                {
                    key: "name",
                    label: "Tournament",
                },

                {
                    key: "season",
                    label: "Season",
                },

                {
                    key: "organizer",
                    label: "Organizer",
                },

                {
                    key: "start_date",
                    label: "Start",
                },

                {
                    key: "end_date",
                    label: "End",
                },

                {
                    key: "status",
                    label: "Status",
                    status: true,
                },

            ],

        },

    };


    const resource =
        root.dataset.resource;


    const config =
        configs[resource];


    if (!config) {

        root.innerHTML = `
            <div class="panel">
                <h1>
                    Unknown resource
                </h1>
            </div>
        `;

        return;

    }


    const elements = {

        title:
            document.getElementById(
                "resource-title"
            ),

        subtitle:
            document.getElementById(
                "resource-subtitle"
            ),

        add:
            document.getElementById(
                "add-record"
            ),

        search:
            document.getElementById(
                "search-input"
            ),

        includeArchived:
            document.getElementById(
                "include-archived"
            ),

        refresh:
            document.getElementById(
                "refresh-list"
            ),

        head:
            document.getElementById(
                "table-head"
            ),

        body:
            document.getElementById(
                "table-body"
            ),

        loading:
            document.getElementById(
                "table-loading"
            ),

        empty:
            document.getElementById(
                "table-empty"
            ),

        summary:
            document.getElementById(
                "pagination-summary"
            ),

        previous:
            document.getElementById(
                "previous-page"
            ),

        next:
            document.getElementById(
                "next-page"
            ),

        indicator:
            document.getElementById(
                "page-indicator"
            ),

        modal:
            document.getElementById(
                "record-modal"
            ),

        closeModal:
            document.getElementById(
                "close-modal"
            ),

        cancelModal:
            document.getElementById(
                "cancel-modal"
            ),

        form:
            document.getElementById(
                "record-form"
            ),

        formFields:
            document.getElementById(
                "form-fields"
            ),

        formError:
            document.getElementById(
                "form-error"
            ),

        modalTitle:
            document.getElementById(
                "modal-title"
            ),

        modalEyebrow:
            document.getElementById(
                "modal-eyebrow"
            ),

        save:
            document.getElementById(
                "save-record"
            ),

    };


    const state = {

        page: 1,

        pageSize: 10,

        search: "",

        includeArchived: false,

        pages: 0,

        total: 0,

        records: new Map(),

        editing: null,

        uploadingImage: false,
        imageUploadSequence: 0,

        loadSequence: 0,

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


    function formatValue(
        record,
        column
    ) {

        const value =
            record[column.key];

        if (config.imageField && column === config.columns[0]) {
            return `<div class="record-identity">
                ${window.ProfileAssets.image(record[config.imageField], value, config.imageKind)}
                <div><span>${escapeHtml(value)}</span>
                    ${window.ProfileAssets.sourceLink(record[config.sourceField])}
                </div>
            </div>`;
        }

        if (column.format === "coordinates") {
            const map = window.ProfileAssets.map(record.address, record.latitude, record.longitude);
            if (!map) {
                return '<span class="muted">Not set</span>';
            }
            return `${record.address ? `<span class="venue-location-label">${escapeHtml(record.address)}</span>` : ""}${map}`;
        }


        if (column.status) {

            const status =
                escapeHtml(
                    value || "unknown"
                );


            return `
                <span
                    class="
                        status-badge
                        status-${status}
                    "
                >
                    ${escapeHtml(
                        humanStatus(value)
                    )}
                </span>
            `;

        }


        if (
            column.format === "number" &&
            value !== null &&
            value !== undefined
        ) {

            return escapeHtml(
                Number(value)
                    .toLocaleString()
            );

        }


        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {

            return `
                <span class="muted">
                    —
                </span>
            `;

        }


        return escapeHtml(value);

    }


    function renderHeader() {

        elements.title.textContent =
            config.plural;


        elements.subtitle.textContent =
            config.subtitle;


        elements.add.textContent =
            `+ Add ${
                config.singular.toLowerCase()
            }`;


        elements.search.placeholder =
            config.searchPlaceholder;


        elements.head.innerHTML = [

            ...config.columns.map(
                (column) => (
                    `<th>${
                        escapeHtml(
                            column.label
                        )
                    }</th>`
                )
            ),

            `
                <th class="actions-column">
                    Actions
                </th>
            `,

        ].join("");

    }


    function renderRows(items) {

        state.records =
            new Map(
                items.map(
                    (record) => [
                        record.id,
                        record,
                    ]
                )
            );


        if (!items.length) {

            elements.body.innerHTML =
                "";

            elements.empty
                .classList
                .remove("hidden");

            return;

        }


        elements.empty
            .classList
            .add("hidden");


        elements.body.innerHTML =
            items
                .map(
                    (record) => {

                        const archived =
                            record.status ===
                            "archived";


                        const cells =
                            config.columns
                                .map(
                                    (column) =>
                                        `<td>${
                                            formatValue(
                                                record,
                                                column
                                            )
                                        }</td>`
                                )
                                .join("");


                        return `
                            <tr>

                                ${cells}

                                <td class="row-actions">

                                    ${
                                        resource === "teams"
                                            ? `<button
                                                class="table-action"
                                                type="button"
                                                data-action="squad"
                                                data-id="${record.id}"
                                            >
                                                Squad
                                            </button>`
                                            : ""
                                    }

                                    ${
                                        resource === "players"
                                            ? `<button
                                                class="table-action"
                                                type="button"
                                                data-action="profile"
                                                data-id="${record.id}"
                                            >
                                                Profile
                                            </button>`
                                            : ""
                                    }

                                    <button
                                        class="table-action"
                                        type="button"
                                        data-action="edit"
                                        data-id="${record.id}"
                                        ${
                                            archived
                                                ? "disabled"
                                                : ""
                                        }
                                    >
                                        Edit
                                    </button>


                                    <button
                                        class="
                                            table-action
                                            table-action-danger
                                        "
                                        type="button"
                                        data-action="archive"
                                        data-id="${record.id}"
                                        ${
                                            archived
                                                ? "disabled"
                                                : ""
                                        }
                                    >
                                        Archive
                                    </button>

                                </td>

                            </tr>
                        `;

                    }
                )
                .join("");

    }


    function updatePagination() {

        const visiblePage =
            state.pages === 0
                ? 0
                : state.page;


        elements.summary.textContent =
            `${state.total.toLocaleString()} ` +
            `${
                state.total === 1
                    ? config.singular.toLowerCase()
                    : config.plural.toLowerCase()
            }`;


        elements.indicator.textContent =
            `Page ${visiblePage} ` +
            `of ${state.pages}`;


        elements.previous.disabled =
            state.page <= 1 ||
            state.pages === 0;


        elements.next.disabled =
            state.pages === 0 ||
            state.page >= state.pages;

    }


    async function loadRecords() {

        const sequence =
            ++state.loadSequence;


        elements.loading
            .classList
            .remove("hidden");


        elements.empty
            .classList
            .add("hidden");


        elements.body.innerHTML =
            "";


        try {

            const result =
                await window.API.list(
                    resource,
                    {
                        page:
                            state.page,

                        page_size:
                            state.pageSize,

                        search:
                            state.search ||
                            null,

                        include_archived:
                            state.includeArchived,
                    }
                );


            if (
                sequence !==
                state.loadSequence
            ) {
                return;
            }


            state.total =
                result.total;

            state.pages =
                result.pages;


            if (
                state.pages > 0 &&
                state.page >
                    state.pages
            ) {

                state.page =
                    state.pages;

                await loadRecords();

                return;

            }


            renderRows(
                result.items || []
            );


            updatePagination();

        }

        catch (error) {

            if (
                sequence !==
                state.loadSequence
            ) {
                return;
            }


            elements.body.innerHTML = `
                <tr>

                    <td
                        class="table-error"
                        colspan="${
                            config.columns.length +
                            1
                        }"
                    >
                        ${escapeHtml(
                            error.message
                        )}
                    </td>

                </tr>
            `;


            state.total = 0;

            state.pages = 0;


            updatePagination();

        }

        finally {

            if (
                sequence ===
                state.loadSequence
            ) {

                elements.loading
                    .classList
                    .add("hidden");

            }

        }

    }


    function fieldHtml(field) {

        if (field.type === "hidden") {
            return `<input type="hidden" name="${field.name}">`;
        }

        const required =
            field.required
                ? "required"
                : "";


        const maxLength =
            field.maxLength
                ? `maxlength="${field.maxLength}"`
                : "";


        const min =
            field.min !== undefined
                ? `min="${field.min}"`
                : "";

        const max = field.max !== undefined ? `max="${field.max}"` : "";
        const step = field.step !== undefined ? `step="${field.step}"` : "";
        const hintId = `${field.name}-hint`;
        const hint = field.hint || (field.url ? "Use https:// or a path starting with /. Leave blank to remove." : "");

        const placeholder =
            field.placeholder
                ? `placeholder="${
                    escapeHtml(
                        field.placeholder
                    )
                }"`
                : "";


        const wide =
            field.wide
                ? " form-field-wide"
                : "";


        if (
            field.type ===
            "select"
        ) {

            const options =
                (
                    field.options
                    || []
                )
                    .map(
                        ([value, label]) => `
                            <option
                                value="${escapeHtml(
                                    value
                                )}"
                            >
                                ${escapeHtml(
                                    label
                                )}
                            </option>
                        `
                    )
                    .join("");


            return `
                <label
                    class="
                        form-field
                        ${wide}
                    "
                >

                    <span>
                        ${escapeHtml(
                            field.label
                        )}

                        ${
                            field.required
                                ? "<em>*</em>"
                                : ""
                        }
                    </span>

                    <select
                        name="${field.name}"
                        ${required}
                    >
                        ${options}
                    </select>

                </label>
            `;

        }


        if (
            field.type ===
            "textarea"
        ) {

            return `
                <label
                    class="
                        form-field
                        ${wide}
                    "
                >

                    <span>
                        ${escapeHtml(
                            field.label
                        )}

                        ${
                            field.required
                                ? "<em>*</em>"
                                : ""
                        }
                    </span>

                    <textarea
                        name="${field.name}"
                        rows="4"
                        ${maxLength}
                        ${placeholder}
                        ${required}
                    ></textarea>

                </label>
            `;

        }


        return `
            <label
                class="
                    form-field
                    ${wide}
                "
            >

                <span>

                    ${escapeHtml(
                        field.label
                    )}

                    ${
                        field.required
                            ? "<em>*</em>"
                            : ""
                    }

                </span>

                <input
                    name="${field.name}"
                    type="${field.type}"
                    ${maxLength}
                    ${min}
                    ${max}
                    ${step}
                    ${field.url ? 'inputmode="url"' : ""}
                    ${hint ? `aria-describedby="${hintId}"` : ""}
                    ${placeholder}
                    ${required}
                >

                ${hint ? `<small class="field-hint" id="${hintId}">${escapeHtml(hint)}</small>` : ""}

            </label>
        `;

    }


    function buildForm() {

        elements.formFields.innerHTML =
            config.fields
                .map(fieldHtml)
                .join("") + (resource === "venues"
                    ? '<div class="form-field-wide venue-location-preview"><button type="button" class="button button-secondary button-small" id="preview-venue-location">Show location on map</button><div id="venue-map-preview"></div></div>' : "") + (config.imageField
                    ? `<label class="form-field form-field-wide"><span>${resource === "teams" ? "Team logo" : resource === "players" ? "Player photo" : "Venue picture"} from your computer</span>
                        <input type="file" id="profile-image-upload" accept="image/png,image/jpeg,image/webp">
                        <small class="field-hint">Choose a PNG, JPEG or WebP image (up to 5 MB), or use the image URL above.</small>
                        <small id="profile-upload-status" role="status" aria-live="polite"></small></label>
                        <div class="record-image-preview form-field-wide" id="record-image-preview" aria-live="polite"></div>`
                    : "");

    }

    function updateImagePreview() {
        if (!config.imageField) return;
        const imageUrl = elements.form.elements.namedItem(config.imageField).value;
        const sourceUrl = config.sourceField
            ? elements.form.elements.namedItem(config.sourceField).value : null;
        const name = elements.form.elements.namedItem(config.fields[0].name).value;
        document.getElementById("record-image-preview").innerHTML = `
            ${window.ProfileAssets.image(imageUrl, name || config.singular, config.imageKind)}
            <div><span>Image preview</span>${window.ProfileAssets.sourceLink(sourceUrl)}</div>`;
    }

    function updateVenueMap() {
        if (resource !== "venues") return;
        const address = elements.form.elements.namedItem("address").value.trim();
        const latitude = elements.form.elements.namedItem("latitude").value;
        const longitude = elements.form.elements.namedItem("longitude").value;
        const preview = window.ProfileAssets.map(address,
            latitude === "" ? null : Number(latitude), longitude === "" ? null : Number(longitude));
        document.getElementById("venue-map-preview").innerHTML = preview ||
            '<p class="field-hint">Enter a place name or full address in Location to see it on the map.</p>';
    }

    async function uploadImage(file) {
        if (!file) return;
        const sequence = ++state.imageUploadSequence;
        state.uploadingImage = true;
        elements.save.disabled = true;
        const status = document.getElementById("profile-upload-status");
        status.textContent = "Uploading image…";
        try {
            if (file.size > 5 * 1024 * 1024) throw new Error("Choose an image of 5 MB or smaller.");
            const uploaded = await window.API.uploadProfileImage(resource, file);
            if (sequence !== state.imageUploadSequence) return;
            elements.form.elements.namedItem(config.imageField).value = uploaded.url;
            updateImagePreview();
            status.textContent = "Image uploaded. Save the record to apply it.";
        } catch (error) {
            if (sequence !== state.imageUploadSequence) return;
            status.textContent = "";
            document.getElementById("profile-image-upload").value = "";
            elements.formError.textContent = error.message;
            elements.formError.classList.remove("hidden");
        } finally {
            if (sequence === state.imageUploadSequence) {
                state.uploadingImage = false;
                elements.save.disabled = false;
            }
        }
    }


    function setFormValue(
        field,
        value
    ) {

        const control =
            elements.form.elements
                .namedItem(
                    field.name
                );


        if (!control) {
            return;
        }


        control.value =
            value ?? "";

    }


    function openModal(
        record = null
    ) {

        state.editing =
            record;


        elements.form.reset();

        state.imageUploadSequence++;
        state.uploadingImage = false;
        elements.save.disabled = false;
        if (config.imageField) document.getElementById("profile-upload-status").textContent = "";


        elements.formError
            .classList
            .add("hidden");


        elements.formError
            .textContent = "";


        elements.modalTitle
            .textContent =
                record
                    ? `Edit ${
                        config.singular
                            .toLowerCase()
                    }`
                    : `Add ${
                        config.singular
                            .toLowerCase()
                    }`;


        elements.modalEyebrow
            .textContent =
                config.plural;


        elements.save
            .textContent =
                record
                    ? "Save changes"
                    : `Create ${
                        config.singular
                            .toLowerCase()
                    }`;


        if (record) {

            config.fields.forEach(
                (field) =>
                    setFormValue(
                        field,
                        record[
                            field.name
                        ]
                    )
            );

        }


        updateImagePreview();
        updateVenueMap();

        elements.modal
            .classList
            .remove("hidden");


        document.body
            .classList
            .add("modal-open");


        elements.form
            .querySelector(
                "input, textarea"
            )
            ?.focus();

    }


    function closeModal() {

        state.imageUploadSequence++;
        state.uploadingImage = false;

        elements.modal
            .classList
            .add("hidden");


        document.body
            .classList
            .remove("modal-open");


        state.editing =
            null;

    }


    function normalizeFieldValue(
        field,
        value
    ) {

        if (
            field.type === "number" || field.numeric
        ) {

            return value === ""
                ? null
                : Number(value);

        }


        if (
            field.type ===
            "date"
        ) {

            return value || null;

        }


        const trimmed =
            value.trim();


        if (
            !field.required &&
            trimmed === ""
        ) {

            return null;

        }


        return trimmed;

    }


    function formPayload() {

        const payload = {};


        config.fields.forEach(
            (field) => {

                const control =
                    elements.form
                        .elements
                        .namedItem(
                            field.name
                        );


                payload[
                    field.name
                ] =
                    normalizeFieldValue(
                        field,
                        control.value
                    );

            }
        );


        config.fields.filter((field) => field.url).forEach((field) => {
            if (payload[field.name] && !window.ProfileAssets.safeUrl(payload[field.name])) {
                throw new Error(`${field.label}: use an http(s) URL or a path starting with /.`);
            }
        });

        if (resource === "venues" && state.editing && payload.address !== (state.editing.address ?? null)) {
            // A new named location replaces the old point; retain coordinates
            // internally only while their original location is unchanged.
            payload.latitude = null;
            payload.longitude = null;
        }

        if (resource === "venues" && (payload.latitude === null) !== (payload.longitude === null)) {
            throw new Error("Set both latitude and longitude, or leave both blank.");
        }

        return payload;

    }


    function updatePayload(
        record,
        payload
    ) {

        const changed = {};


        config.fields.forEach(
            (field) => {

                const nextValue =
                    payload[
                        field.name
                    ];


                const currentValue =
                    record[
                        field.name
                    ] ?? null;


                if (
                    nextValue !==
                    currentValue
                ) {

                    changed[
                        field.name
                    ] =
                        nextValue;

                }

            }
        );


        // The API requires both coordinate keys even when only one value changes.
        if (resource === "venues" && ("latitude" in changed || "longitude" in changed)) {
            changed.latitude = payload.latitude;
            changed.longitude = payload.longitude;
        }

        return changed;

    }


    async function submitForm(
        event
    ) {

        event.preventDefault();

        if (state.uploadingImage) return;


        if (
            !elements.form
                .reportValidity()
        ) {
            return;
        }


        elements.save.disabled =
            true;


        elements.formError
            .classList
            .add("hidden");


        try {

            const payload =
                formPayload();


            if (state.editing) {

                const changed =
                    updatePayload(
                        state.editing,
                        payload
                    );


                if (
                    !Object.keys(
                        changed
                    ).length
                ) {

                    window.showToast(
                        "No changes to save.",
                        "info"
                    );

                    return;

                }


                await window.API.update(
                    resource,
                    state.editing.id,
                    changed
                );


                window.showToast(
                    `${config.singular} updated.`
                );

            }

            else {

                await window.API.create(
                    resource,
                    payload
                );


                window.showToast(
                    `${config.singular} created.`
                );

            }


            closeModal();

            await loadRecords();

        }

        catch (error) {

            elements.formError
                .textContent =
                    error.message;


            elements.formError
                .classList
                .remove("hidden");

        }

        finally {

            elements.save.disabled =
                false;

        }

    }


    async function archiveRecord(
        record
    ) {

        const label =
            record.name ||
            record.full_name ||
            record.slug ||
            config.singular;


        const confirmed =
            window.confirm(
                `Archive ${label}? ` +
                "The record will remain " +
                "in the database and audit history."
            );


        if (!confirmed) {
            return;
        }


        try {

            await window.API.archive(
                resource,
                record.id
            );


            window.showToast(
                `${config.singular} archived.`
            );


            await loadRecords();

        }

        catch (error) {

            window.showToast(
                error.message,
                "error"
            );

        }

    }


    let searchTimer =
        null;


    elements.search
        .addEventListener(
            "input",
            () => {

                window.clearTimeout(
                    searchTimer
                );


                searchTimer =
                    window.setTimeout(
                        () => {

                            state.search =
                                elements
                                    .search
                                    .value
                                    .trim();


                            state.page =
                                1;


                            loadRecords();

                        },
                        300
                    );

            }
        );


    elements.includeArchived
        .addEventListener(
            "change",
            () => {

                state.includeArchived =
                    elements
                        .includeArchived
                        .checked;


                state.page =
                    1;


                loadRecords();

            }
        );


    elements.refresh
        .addEventListener(
            "click",
            loadRecords
        );


    elements.add
        .addEventListener(
            "click",
            () => openModal()
        );


    elements.closeModal
        .addEventListener(
            "click",
            closeModal
        );


    elements.cancelModal
        .addEventListener(
            "click",
            closeModal
        );


    elements.form.addEventListener("input", updateImagePreview);
    elements.form.addEventListener("change", (event) => {
        if (event.target.id === "profile-image-upload") uploadImage(event.target.files?.[0]);
        if (resource === "venues" && event.target.name === "address") {
            elements.form.elements.namedItem("latitude").value = "";
            elements.form.elements.namedItem("longitude").value = "";
            updateVenueMap();
        }
    });
    elements.form.addEventListener("click", (event) => {
        if (event.target.id === "preview-venue-location") updateVenueMap();
    });

    elements.form
        .addEventListener(
            "submit",
            submitForm
        );


    elements.modal
        .addEventListener(
            "click",
            (event) => {

                if (
                    event.target ===
                    elements.modal
                ) {
                    closeModal();
                }

            }
        );


    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key ===
                    "Escape" &&

                !elements.modal
                    .classList
                    .contains(
                        "hidden"
                    )
            ) {

                closeModal();

            }

        }
    );


    elements.body
        .addEventListener(
            "click",
            (event) => {

                const button =
                    event.target.closest(
                        "button[data-action]"
                    );


                if (!button) {
                    return;
                }


                const record =
                    state.records.get(
                        button.dataset.id
                    );


                if (!record) {
                    return;
                }


                if (
                    button.dataset.action ===
                    "squad"
                ) {

                    window.openTeamSquad(
                        record
                    );

                }

                else if (
                    button.dataset.action ===
                    "profile"
                ) {

                    window.location.href =
                        `/player-profile/${record.id}`;

                }

                else if (
                    button.dataset.action ===
                    "edit"
                ) {

                    openModal(
                        record
                    );

                }

                else if (
                    button.dataset.action ===
                    "archive"
                ) {

                    archiveRecord(
                        record
                    );

                }

            }
        );


    elements.previous
        .addEventListener(
            "click",
            () => {

                if (
                    state.page <= 1
                ) {
                    return;
                }


                state.page -= 1;

                loadRecords();

            }
        );


    elements.next
        .addEventListener(
            "click",
            () => {

                if (
                    state.page >=
                    state.pages
                ) {
                    return;
                }


                state.page += 1;

                loadRecords();

            }
        );


    renderHeader();

    buildForm();

    loadRecords();

})();
