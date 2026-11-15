const {test} = require('node:test');
const assert = require('node:assert/strict');
const F = require('../dashboard-core.js');
const farm = () => ({location:{lat:43.55,lon:-80.25},soilTexture:'loam',currentRotation:[{crop:'soybean'},{crop:'winter_wheat'},{crop:'corn'}],mustGrow:['corn'],avoid:[],equipment:{specified:true,available:['planter','combine']},irrigation:{availability:'yes'},drainage:'yes',priorities:{water:3,nitrogen:3,soilCover:3,weatherRisk:3}});
test('request preserves sequence and mandatory constraints without silently filtering',()=>{
 const r=F.request(farm());assert.deepEqual(r.current_rotation,['soybean','winter_wheat','corn']);assert.deepEqual(r.must_include,['corn']);assert.deepEqual(r.equipment,['planter','combine']);assert.equal(Object.hasOwn(r,'irrigation'),false);assert.equal(Object.hasOwn(r,'tile_drainage'),false);assert.deepEqual(r.priorities,{water:.25,nitrogen:.25,soil_cover:.25,weather_risk:.25});
});
test('unsupported crops and excessive rotations are rejected, never truncated',()=>{
 const f=farm();f.currentRotation.push({crop:'cereal_rye'});assert.throws(()=>F.request(f),/silently/);f.currentRotation=Array(5).fill({crop:'corn'});assert.throws(()=>F.request(f));
});
test('unsupported soil is not silently mapped',()=>{const f=farm();f.soilTexture='sandy';assert.throws(()=>F.request(f),/supported soil/);});
test('missing numbers stay unavailable, valid zero stays zero',()=>{assert.equal(F.format(null),'—');assert.equal(F.format(undefined),'—');assert.equal(F.format(NaN),'—');assert.equal(F.format(0),'0');assert.equal(F.format(.0125),'0.013');assert.equal(F.delta(null,5),null);assert.equal(F.delta(0,5),-5);});
test('absolute differences show unfavorable signs and handle zero baseline',()=>{assert.equal(F.change(F.delta(5,0),'mm'),'+5 mm vs current');assert.equal(F.change(F.delta(0,5),'mm'),'−5 mm vs current');assert.equal(F.change(F.delta(0,0),'mm'),'0 mm vs current');});
test('priorities require finite nonnegative inputs and positive total',()=>{const f=farm();f.priorities.water=NaN;assert.throws(()=>F.request(f));f.priorities={water:0,nitrogen:0,soilCover:0,weatherRisk:0};assert.throws(()=>F.request(f));});
test('time machine uses supplied model outcomes and range without inventing unavailable future',()=>{
 const entry={};const response={baseline:entry,time_machine:{historical_2005_2014:{status:'available',metrics:{water_use_mm:0}},historical_2015_2024:{status:'available',metrics:{water_use_mm:20}},future_2031_2050:{status:'insufficient_data',metrics:null}}};
 assert.deepEqual(F.periodRows(entry,response,'water_use_mm').map(r=>r.value),[0,20,null]);response.time_machine.future_2031_2050={status:'available',metrics:{water_use_mm:30},model_range:{water_use_mm:{min:25,max:45}}};assert.deepEqual(F.periodRows(entry,response,'water_use_mm')[2].range,{min:25,max:45});
});
test('candidate periods are read from that candidate, not the baseline',()=>{
 const candidate={time_machine:{historical_2005_2014:{status:'available',metrics:{water_use_mm:12}}}};assert.equal(F.periodRows(candidate,{baseline:{}},'water_use_mm')[0].value,12);
});
test('calendar timing is an approximate month label, not a future date',()=>{assert.equal(F.weekTiming(30).month,'Jul');assert.match(F.weekTiming(30).label,/Jul/);assert.equal(F.weekTiming(19).month,'May');});
test('default future calendar uses the returned model median without recomputing it',()=>{
 const rows=[{crop:'corn',calendar_week:30,eligible_seasons:20,frequency_pct:{water:25,heat:0,combined:0}}];
 const blind={runs:[{weekly_vulnerabilities:rows}],recurring_vulnerabilities:{historical:rows},emerging_vulnerabilities:[{crop:'corn',calendar_week:30,eligible_seasons:20,status:'available',exposures:{water:{future_median_frequency_pct:37.5},heat:{future_median_frequency_pct:5},combined:{future_median_frequency_pct:2.5}}}]};
 assert.equal(F.weeklyView(blind,0),rows);const median=F.weeklyView(blind,-1)[0];assert.deepEqual(median.frequency_pct,{water:37.5,heat:5,combined:2.5});assert.equal(median.mean_water_depletion_intensity,null);assert.equal(median.eligible_seasons,20);
});
test('unavailable median windows are not replaced with zero frequency',()=>{
 const blind={runs:[],emerging_vulnerabilities:[{crop:'corn',calendar_week:30,status:'insufficient_data',exposures:null}]};assert.equal(F.weeklyView(blind,-1)[0].frequency_pct.water,null);
});

test('recommendation uses the existing balanced label, not an invented score',()=>{assert.equal(F.recommendedIndex({options:[{score:.9,labels:['lowest_water']},{score:.8,labels:['balanced']}]}),2);});
test('highest returned score is a fallback and empty options do not imply a recommendation',()=>{assert.equal(F.recommendedIndex({options:[{score:.4},{score:.7}]}),2);assert.equal(F.recommendedIndex({options:[]}),null);assert.equal(F.recommendedIndex({options:[{}]}),null);});
test('corn followed by wheat is retained in the request and calendar conflict is explained as model limitation',()=>{const f=farm();f.currentRotation=[{crop:'corn'},{crop:'winter_wheat'}];assert.deepEqual(F.request(f).current_rotation,['corn','winter_wheat']);assert.match(F.baselineNotice('winter_wheat planting window cannot follow corn harvest'),/model.*fixed/i);assert.match(F.baselineNotice('winter_wheat planting window cannot follow corn harvest'),/not a blanket rule/);});
function dailyFixture(first=1995,last=2005){
 const rows=[];for(let t=Date.UTC(first,0,1);t<=Date.UTC(last,11,31);t+=86400000){const d=new Date(t);rows.push({date:d.toISOString().slice(0,10),crop:'corn',storage_mm:80,unmet_demand_mm:0,water_stress:false,heat_exposure:false,stress_type:'no_blind_spot'});}return rows;
}
test('rotation illustration preserves duplicate crop positions, year order and raw daily quantities',()=>{
 const days=dailyFixture(),view=F.cycleView(days,['corn','corn','soybean']);assert.deepEqual(view.steps.map(s=>s.crop),['corn','corn','soybean']);assert.deepEqual(view.steps.map(s=>s.year),[1,2,3]);assert.equal(view.startYear,1998);assert.equal(view.endYear,2000);assert.equal(view.days.length,1096);assert.equal(view.days[0],days.find(d=>d.date==='1998-01-01'));assert.equal(view.steps[1].start,365);assert.equal(view.steps[2].start,730);
});
test('cycle illustration rotates in the engine phase order without rearranging crops',()=>{assert.deepEqual(F.cycleView(dailyFixture(),['corn','corn','soybean'],1).steps.map(s=>s.crop),['corn','soybean','corn']);});
test('first winter wheat includes the previous autumn; crop band crosses the calendar year',()=>{
 const days=dailyFixture();for(const day of days){if(day.date>='1996-10-01'&&day.date<='1997-07-25')day.crop='winter_wheat';else if(day.date>='1998-10-01'&&day.date<='1999-07-25')day.crop='winter_wheat';}
 const view=F.cycleView(days,['winter_wheat','corn']);assert.equal(view.start,'1996-10-01');assert.deepEqual(view.steps.map(s=>s.crop),['winter_wheat','corn']);assert.equal(view.days[view.bands[0].end-1].date,'1997-07-25');assert.equal(view.startYear,1997);
});
test('timeline missing daily data stays unavailable rather than becoming zero',()=>{const days=dailyFixture();days.find(d=>d.date==='1998-07-10').storage_mm=null;assert.throws(()=>F.cycleView(days,['corn','corn','soybean']),/Missing or invalid/);});
test('display bands use existing daily flags, preserve combined days, and never join over clear days',()=>{
 const days=[{water_stress:true,heat_exposure:false,stress_type:'water_stress'},{water_stress:true,heat_exposure:true,stress_type:'combined_heat_water'},{water_stress:false,heat_exposure:false,stress_type:'no_blind_spot'},{water_stress:true,heat_exposure:false,stress_type:'water_stress'}];
 assert.deepEqual(F.flagBands(days,'water'),[{start:0,end:2},{start:3,end:4}]);assert.deepEqual(F.flagBands(days,'heat'),[{start:1,end:2}]);assert.deepEqual(F.flagBands(days,'combined'),[{start:1,end:2}]);
});
