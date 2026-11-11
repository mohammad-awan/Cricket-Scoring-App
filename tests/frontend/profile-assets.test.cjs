// Run with: node --test tests/frontend/profile-assets.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');

async function page(resource, records = []) {
    const nodes = new Map(), controls = new Map(), creates = [], updates = [];
    function element(id) {
        if (nodes.has(id)) return nodes.get(id);
        const classes = new Set(['hidden']);
        const node = {
            dataset: { resource }, handlers: {}, value: '', textContent: '',
            classList: {
                add: (...names) => names.forEach(name => classes.add(name)),
                remove: name => classes.delete(name), contains: name => classes.has(name),
            },
            addEventListener(type, handler) { this.handlers[type] = handler; },
            querySelector() { return { focus() {} }; },
            elements: { namedItem: name => controls.get(name) },
            reset() { controls.forEach(control => { control.value = ''; }); },
            reportValidity() { return true; },
        };
        let html = '';
        Object.defineProperty(node, 'innerHTML', {
            get: () => html,
            set(value) {
                html = value;
                if (id === 'form-fields') {
                    for (const match of value.matchAll(/<(?:input|textarea|select)\s[^>]*name="([^"]+)"/g)) {
                        controls.set(match[1], { value: '' });
                    }
                }
            },
        });
        nodes.set(id, node);
        return node;
    }
    const document = {
        handlers: {}, getElementById: element, body: element('body'),
        addEventListener(type, handler) { this.handlers[type] = handler; },
    };
    const window = {
        location: { href: 'https://cricket.test/master-data/' + resource }, showToast() {},
        API: {
            async list() { return { items: records, page: 1, pages: 1, total: records.length }; },
            async create(type, payload) { creates.push(payload); records.push({ id: 'new', ...payload }); },
            async update(type, id, payload) {
                updates.push(payload);
                Object.assign(records.find(record => record.id === id), payload);
            },
        },
    };
    const context = vm.createContext({ window, document, URL });
    for (const script of ['profile-assets', 'master-data']) {
        vm.runInContext(fs.readFileSync(`static/js/${script}.js`, 'utf8'), context);
    }
    const flush = () => new Promise(resolve => setImmediate(resolve));
    await flush();
    return {
        window, document, element, controls, creates, updates, flush,
        fill(values) { Object.entries(values).forEach(([name, value]) => { controls.get(name).value = String(value); }); },
        add() { element('add-record').handlers.click(); },
        edit(id) {
            element('table-body').handlers.click({ target: { closest: () => ({ dataset: { action: 'edit', id } }) } });
        },
        async submit() { await element('record-form').handlers.submit({ preventDefault() {} }); },
    };
}

test('team logos and player photos persist, prefill on edit, and clear with null', async () => {
    for (const [resource, identity, imageField, sourceField] of [
        ['teams', { name: 'Pakistan', short_name: 'PAK', code: 'PAK' }, 'logo_url', 'logo_source_url'],
        ['players', { full_name: 'Babar Azam' }, 'photo_url', 'photo_source_url'],
    ]) {
        const app = await page(resource);
        app.add();
        app.fill({ ...identity, [imageField]: ' https://example.com/image.png ', [sourceField]: 'https://example.com/source' });
        app.element('record-form').handlers.input();
        assert.match(app.element('record-image-preview').innerHTML, /image\.png/);
        await app.submit();
        assert.equal(app.creates[0][imageField], 'https://example.com/image.png');
        assert.equal(app.creates[0][sourceField], 'https://example.com/source');
        assert.match(app.element('table-body').innerHTML, /Image source/);

        app.edit('new');
        assert.equal(app.controls.get(imageField).value, 'https://example.com/image.png');
        app.fill({ [imageField]: '', [sourceField]: '' });
        await app.submit();
        assert.equal(JSON.stringify(app.updates[0]), JSON.stringify({ [imageField]: null, [sourceField]: null }));
        assert.doesNotMatch(app.element('table-body').innerHTML, /<img|Image source/);
    }
});

test('venue edits send paired coordinates, preserve zero, and clear both', async () => {
    const app = await page('venues', [{ id: 'venue', name: 'Stadium', city: 'Lahore', capacity: null, latitude: 31.5, longitude: 74.3 }]);
    app.edit('venue');
    app.fill({ latitude: '0', image_url: '/static/stadium.jpg' });
    await app.submit();
    assert.equal(app.updates[0].latitude, 0);
    assert.equal(app.updates[0].longitude, 74.3);
    assert.equal(app.updates[0].image_url, '/static/stadium.jpg');
    assert.match(app.element('table-body').innerHTML, /query=0%2C%2074.3/);

    app.edit('venue');
    app.fill({ latitude: '' });
    await app.submit();
    assert.equal(app.updates.length, 1, 'incomplete pair must not reach the API');
    assert.match(app.element('form-error').textContent, /both latitude and longitude/);
    app.fill({ longitude: '', image_url: '' });
    await app.submit();
    assert.equal(app.updates[1].latitude, null);
    assert.equal(app.updates[1].longitude, null);
    assert.equal(app.updates[1].image_url, null);
    assert.doesNotMatch(app.element('table-body').innerHTML, /View map|<img/);
});

test('new venues submit numeric coordinates and image URL', async () => {
    const app = await page('venues');
    app.add();
    app.fill({ name: 'Stadium', city: 'Lahore', latitude: '0', longitude: '0', image_url: 'https://example.com/stadium.jpg' });
    await app.submit();
    assert.equal(app.creates[0].latitude, 0);
    assert.equal(app.creates[0].longitude, 0);
    assert.equal(app.creates[0].image_url, 'https://example.com/stadium.jpg');
});

test('unsafe URLs cannot be saved or rendered, and broken images retain initials', async () => {
    const app = await page('players');
    app.add();
    app.fill({ full_name: 'Babar Azam', photo_url: 'javascript:alert(1)' });
    await app.submit();
    assert.equal(app.creates.length, 0);
    assert.match(app.element('form-error').textContent, /http\(s\) URL/);
    const assets = app.window.ProfileAssets;
    for (const url of ['javascript:alert(1)', 'data:image/svg+xml,bad', '//example.com/photo']) {
        assert.equal(assets.safeUrl(url), null);
        assert.equal(assets.sourceLink(url), '');
        assert.doesNotMatch(assets.image(url, '<Babar> Azam', 'player'), /<img|<Babar>/);
    }
    assert.match(assets.image('/photo.jpg', 'Babar Azam', 'player'), /BA/);
    let removed = false;
    app.document.handlers.error({ target: { matches: () => true, remove() { removed = true; } } });
    assert.equal(removed, true);
});
