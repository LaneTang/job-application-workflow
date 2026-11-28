const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../assets/dashboard.html'), 'utf8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(code);
const context = {submittedStates: new Set(['submitted','rejected','withdrawn','offer','accepted','declined','invited','assessment','interviewing'])};
vm.createContext(context);
vm.runInContext(code.slice(code.indexOf('    function applicationCategory'), code.indexOf('    function sortTime')), context);
const cases = [
 [{state:'waiting_for_user',questions:[{required:true,answer:'',status:'awaiting_answer'}]}, 'pending'],
 [{state:'waiting_for_user',questions:[{required:true,answer:'Yes',status:'answered'}]}, 'wrong'],
 [{state:'waiting_for_user',questions:[{required:false,answer:''}]}, 'wrong'],
 [{state:'blocked',questions:[{required:true,answer:''}]}, 'wrong'],
 [{state:'filling',application_issue:{kind:'verification'}}, 'wrong'],
 [{state:'submitted',application_issue:{kind:'verification'}}, 'submitted'],
 [{state:'queued',pending_question_count:0}, 'wrong'],
 [{state:'needs_review',pending_question_count:0}, 'wrong'],
 [{state:'ready_for_review',ready_to_go:true}, 'ready'],
 [{state:'submitted'}, 'submitted'],
 [{state:'rejected',recruiting:{ghost:true}}, 'rejected'],
 [{state:'submitted',recruiting:{ghost:true}}, 'ghost'],
 [{state:'invited'}, 'invited'],
 [{state:'interviewing',recruiting_events:[{kind:'interview_completed',date:'2026-01-01',round:1}]}, 'done'],
 [{state:'invited',recruiting_events:[{kind:'interview_invited',date:'2026-01-02',round:2}]}, 'round'],
 [{state:'interviewing',recruiting_events:[{kind:'interview_completed',date:'2026-01-02',round:3}]}, 'round'],
 [{state:'offer'}, 'offered'],
 [{state:'assessment'}, 'submitted'],
];
const filters = [...html.matchAll(/data-filter="([^"]+)"/g)].map(m=>m[1]);
for (const [job, expected] of cases) {
 assert.equal(context.applicationCategory(job), expected);
 assert.equal(filters.filter(f=>f!=='all' && context.matches(job,f)).length,1);
}
assert.equal(/\p{Script=Han}/u.test(html),false,'UI strings must be English');
console.log('Dashboard syntax, English UI and exclusive filters passed.');
