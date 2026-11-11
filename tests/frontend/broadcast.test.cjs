// Run with: node tests/frontend/broadcast.test.cjs
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const all=[],parts={};let opens=0;
function node(){return {className:'',hidden:false,innerHTML:'',textContent:'',open:false,dataset:{matchId:'m'},style:{setProperty(){}},setAttribute(){},append(){},after(){},replaceChildren(){},focus(){},addEventListener(){},querySelector(k){return parts[k] ||= node()},showModal(){this.open=true;opens++},close(){this.open=false}}}
const root=node();root.querySelector=()=>node();const ctx={document:{querySelector:()=>root,createElement(){const el=node();all.push(el);return el},body:{append(){}},activeElement:node()},window:{},matchMedia:()=>({matches:true}),setTimeout:()=>1,clearTimeout(){},console};
vm.runInNewContext(fs.readFileSync('static/js/broadcast.js','utf8'),ctx);
const team={id:'a',name:'Falcons <club>',code:'FAL'},other={id:'b',name:'Kings',code:'KIN'};
const card={match_id:'m',team_a:team,team_b:other,status:'completed',innings:[],lifecycle:{state_label:'Completed',chase:{},result:{completed:true,winner_team:team,summary:'Falcons won by 6 wickets'}}};
ctx.window.BroadcastUI.accept(card);assert.equal(opens,1);assert.equal(parts['.victory-team'].textContent,team.name);assert.equal(parts['.victory-margin'].textContent,card.lifecycle.result.summary);assert.ok(all[0].innerHTML.includes('Falcons &lt;club&gt;'));
ctx.window.BroadcastUI.accept(card);assert.equal(opens,1,'duplicate result does not reopen');
parts['.victory-done'].onclick();all[1].onclick();assert.equal(opens,2,'replay opens celebration');parts['.victory-done'].onclick();assert.equal(all[2].open,false);
card.lifecycle.result={completed:true,winner_team:null,summary:'Match tied'};ctx.window.BroadcastUI.accept(card);assert.equal(all[1].hidden,true,'tie has no winner celebration');
const innings={innings_number:1,status:'completed',batting_team:team,total_runs:185,wickets:4,overs:'20.0',run_rate:9.25,batting:[{player:{id:'p',full_name:'<script>'},dismissal:'not out',runs:45,balls:30,fours:4,sixes:2,strike_rate:150}],bowling:[],extras:{total:4,wides:4,no_balls:0,byes:0,leg_byes:0},partnerships:[]};const html=ctx.window.BroadcastUI.innings(innings);assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('185/4'));assert.ok(!html.includes('<table'));
console.log('PASS: confirmed victory, result deduplication, replay, close, tie suppression, escaped names and card-based innings.');
