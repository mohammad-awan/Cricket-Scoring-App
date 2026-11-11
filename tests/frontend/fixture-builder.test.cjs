const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const context = { window: {}, document: { getElementById: () => null } };
vm.runInNewContext(fs.readFileSync('static/js/fixture-builder.js', 'utf8'), context);
const { parseCsv, csvCell, filterFixtures } = context.window.FixtureBuilderHelpers;

test('manual CSV reads quoted commas, escaped quotes, multiline notes and BOM', () => {
    const rows = parseCsv('\uFEFFround,home,away,notes\r\n1,"Falcons, XI",Kings,"He said ""play""\nTomorrow"\r\n');
    assert.equal(rows.length, 2);
    assert.equal(rows[1][1], 'Falcons, XI');
    assert.equal(rows[1][3], 'He said "play"\nTomorrow');
    assert.throws(() => parseCsv('1,"unfinished'), /unclosed/);
});

test('exports quote names and prevent spreadsheet formulas', () => {
    assert.equal(csvCell('Falcons "A"'), '"Falcons ""A"""');
    assert.equal(csvCell('=HYPERLINK("bad")'), '"\'=HYPERLINK(""bad"")"');
});

test('filters respect either team, numeric rounds, and official completed status', () => {
    const rows = [
        { home_team_id: 'a', away_team_id: 'b', round_number: 1, status: 'published', match_status: 'completed' },
        { home_team_id: 'c', away_team_id: 'a', round_number: 2, status: 'draft' },
    ];
    assert.equal(filterFixtures(rows, { team: 'a' }).length, 2);
    assert.equal(filterFixtures(rows, { team: 'b', round: '1', status: 'completed' }).length, 1);
    assert.equal(filterFixtures(rows, { status: 'draft' }).length, 1);
    assert.equal(filterFixtures(rows, { team: 'missing' }).length, 0);
});
