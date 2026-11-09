// Run with: node tests/frontend/match-events.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const parts = {};
let banner, finish;
const root = { appendChild(node) { banner = node; } };
const context = {
 document: {
  querySelector: () => root,
  createElement: () => ({ hidden:true, className:'', setAttribute(){}, querySelector(key){return parts[key] ||= {textContent:''};}, offsetWidth:680 })
 },
 window: { addEventListener(){} },
 setTimeout(fn){finish=fn;return 1;}, clearTimeout(){}
};
vm.runInNewContext(fs.readFileSync('static/js/match-events.js', 'utf8'),context);
const accept = context.window.MatchEvents.accept;
let sequence=0;
function delivery(fields={}) { return {id:String(++sequence),sequence,status:'recorded',over_number:2,ball_number:3,batter_runs:1,total_runs:1,...fields}; }
function send(d,type) { accept({recent_deliveries:[d]},type); }
for(const [fields,kind,title] of [
 [{},'single','SINGLE'],[{batter_runs:4,total_runs:4},'four','FOUR!'],[{batter_runs:6,total_runs:6},'six','SIX!'],
 [{wicket_type:'bowled'},'wicket','WICKET'],[{wide_runs:1},'wide','WIDE BALL'],[{no_ball_runs:1,batter_runs:4},'no-ball','NO BALL'],
 [{bye_runs:4,total_runs:4,batter_runs:0},'extras','BYES'],[{batter_runs:0,total_runs:0},'dot','DOT BALL'],[{batter_runs:2,total_runs:2},'runs','2 RUNS']
]) { send(delivery(fields));assert.equal(banner.className,'broadcast-event event-'+kind);assert.equal(parts['.event-title'].textContent,title);assert.equal(banner.hidden,false);finish();assert.equal(banner.hidden,true); }
const ball=delivery();send(ball);finish();send(ball);assert.equal(banner.hidden,true,'duplicate response is ignored');
send(delivery(),'snapshot');assert.equal(banner.hidden,true,'snapshot does not replay');
send(delivery({status:'void'}));assert.equal(banner.hidden,true,'void delivery is ignored');
send(delivery());send(delivery(),'delivery_corrected');assert.equal(banner.hidden,true,'correction clears animation');
const old=delivery();const latest=delivery({batter_runs:6,total_runs:6});accept({recent_deliveries:[old,latest]});assert.equal(parts['.event-title'].textContent,'SIX!','latest sequence works in either order');
send(delivery({wicket_type:'run_out',wide_runs:1}));assert.equal(parts['.event-title'].textContent,'WICKET','wicket takes priority over extras');
console.log('PASS: nine event types, dismissal, deduplication, snapshot suppression, corrections, sequence ordering and wicket priority.');
