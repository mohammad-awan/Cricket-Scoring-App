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
                    name: "external_id",
                    label: "External ID",
                    type: "text",
                    maxLength: 80,
                    placeholder:
                        "Optional provider ID",
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
                    label: "Address",
                    type: "textarea",
                    wide: true,
                    placeholder:
                        "Optional venue address",
                },

                {
                    name: "capacity",
                    label: "Capacity",
                    type: "number",
                    min: 0,
                    placeholder: "27000",
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
                    ${placeholder}
                    ${required}
                >

            </label>
        `;

    }


    function buildForm() {

        elements.formFields.innerHTML =
            config.fields
                .map(fieldHtml)
                .join("");

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
            field.type ===
            "number"
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


        return changed;

    }


    async function submitForm(
        event
    ) {

        event.preventDefault();


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