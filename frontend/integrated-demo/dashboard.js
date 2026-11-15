/* Future-focused presentation; all scientific results and recommendation scores come from the existing API. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),F=window.FieldShift;
  const baseURL=(window.TERRASHIFT_CONFIG?.apiBase||'http://127.0.0.1:8000').replace(/\/$/,'');
  const state={body:null,data:null,climate:'future',selected:0,recommended:null,epoch:0,blindEpoch:0,model:0,phase:0,cycle:1,year:null,weeks:{},blind:null,blindBaseline:null,available:false};
  const cache=new Map(),controllers=new Set();
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  const button=(text,action,cls='button button-outline')=>{const n=el('button',cls,text);n.type='button';n.addEventListener('click',action);return n;};
  const note=text=>el('p','small-note',text);
  const details=(title,children)=>{const n=el('details','diagnostics');n.append(el('summary','',title),...children);return n;};
  const entries=()=>state.data?[state.data.baseline,...(state.data.options||[])]:[];
  const active=()=>entries()[state.selected]||state.data?.baseline;
  const cname=crop=>F.crops[crop]||crop;
  const stressName=kind=>({water_stress:'Water stress',heat_exposure:'Heat exposure',combined_heat_water:'Heat + water',no_blind_spot:'No exposure'})[kind]||kind;
  const labelText=label=>({lowest_water:'Lowest water need among alternatives',lowest_nitrogen:'Lowest nitrogen indicator among alternatives',best_soil_cover:'Most living-crop time among alternatives',lowest_dry_year_risk:'Lowest p90 shortfall among alternatives',balanced:'Weighted choice for your priorities',additional_alternative:'Additional feasible option'})[label]||'Feasible option';
  function message(text,error=false,id='results-message'){$(id).textContent=text;$(id).className=`results-message${error?' error':''}`;}
  function invalidate(){
    state.epoch++;state.blindEpoch++;state.body=null;state.data=null;state.blind=null;state.blindBaseline=null;state.available=false;
    controllers.forEach(c=>c.abort());controllers.clear();cache.clear();
    try{sessionStorage.removeItem('fieldshift-methodology');}catch{}
    if(!$('results').hidden){$('dashboard-content').hidden=true;$('results-state').textContent='Inputs changed';message('Compare again to update the recommendation for your new inputs.');}
    $('results').removeAttribute('aria-busy');$('blind-content').removeAttribute('aria-busy');$('compareButton').disabled=!window.TerraShiftSelectedLocation;
  }
  ['terrashift:inputs-changed','terrashift:location-changed','terrashift:location-cleared'].forEach(name=>window.addEventListener(name,invalidate));
  async function api(path,body){
    const key=path+JSON.stringify(body);if(cache.has(key))return cache.get(key);
    const controller=new AbortController();controllers.add(controller);const timer=setTimeout(()=>controller.abort(),90000);
    const pending=(async()=>{try{
      const r=await fetch(baseURL+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
      const data=await r.json();if(!r.ok){const d=data.detail;if(Array.isArray(d)&&d.some(x=>['lat','lon'].includes(x.loc?.[1])))throw new Error('This point is outside supported Southern Ontario coverage. Choose a supported point on the map.');throw new Error(typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg).join('; '):`API error ${r.status}`);}return data;
    }catch(error){cache.delete(key);if(error.name==='AbortError')throw new Error('Request cancelled or timed out. Please try again.');if(error instanceof TypeError)throw new Error('Cannot reach the local backend. No example results have been substituted.');throw error;}
    finally{clearTimeout(timer);controllers.delete(controller);}})();
    if(cache.size>=8)cache.delete(cache.keys().next().value);cache.set(key,pending);return pending;
  }
  function sequence(entry){const n=el('div','sequence');(entry.rotation||[]).forEach((r,i)=>{if(i)n.append(el('span','sequence-arrow','→'));n.append(el('span',`crop-chip crop-${r.crop}`,cname(r.crop)));});return n;}
  function publishContext(){
    const pick=state.recommended==null?null:entries()[state.recommended],future=state.data?.time_machine?.future_2031_2050;
    const context={version:3,available:state.available,anchor:state.data?.anchor?.id,period:'2031–2050',scenario:'SSP2-4.5',
      soil:state.body?.soil,capacity_mm:Object.values(future?.models||{})[0]?.capacity_mm,
      priorities:state.data?.inputs_used?.priority_weights||state.body?.priorities,
      current:{name:F.sequence(state.data?.baseline||{}),metrics:state.available?state.data.baseline.metrics:null},
      recommended:pick?{name:F.sequence(pick),metrics:pick.metrics,labels:pick.labels}:null,
      metadata:{models:Object.keys(future?.models||{}),grid_cell:future?.grid_cell,reference_period:future?.climate_model_reference_period},
      constraints:state.body?{must:state.body.must_include,avoid:state.body.avoid,equipment:state.body.equipment}:null};
    const snapshot=JSON.stringify(context);
    $('methodology-link').href='./methodology.html#'+new URLSearchParams({report:snapshot}).toString();
    try{sessionStorage.setItem('fieldshift-methodology',snapshot);}catch{}
  }
  function drawLeaderboard(){
    const host=$('comparison-cards');host.replaceChildren();
    const t=el('table','leaderboard'),head=el('thead'),hr=el('tr');
    for(const [title,unit] of [['',''],['Crop rotation',''],['Water need','mm / year'],['Water shortfall','mm / year'],['Water stress','days / year'],['Heat exposure','days / year'],['Nitrogen','indicator'],['Explore','']]){const th=el('th','',title);th.scope='col';if(unit)th.append(el('small','',unit));hr.append(th);}head.append(hr);t.append(head);
    const body=el('tbody');entries().forEach((entry,index)=>{
      const isPick=index===state.recommended,row=el('tr',`leaderboard-row${index===0?' baseline':''}${isPick?' recommended-row':''}${index===state.selected?' selected':''}`);row.dataset.rotationIndex=index;
      row.append(el('td','position',index===0?'—':String(index)));
      const rotation=el('th','rotation-name');rotation.scope='row';rotation.append(el('span','rotation-type',index===0?'ORIGINAL ROTATION':isPick?'RECOMMENDED FOR YOUR PRIORITIES':`OPTION ${index}`),sequence(entry));
      if(isPick)rotation.append(el('span','recommendation-badge','Algorithm’s pick'));
      else if(index)rotation.append(el('small','selection-reason',labelText(entry.label)));
      const mobileAction=button('See rotation ↓',()=>selectEntry(index),'mobile-row-action');mobileAction.disabled=!state.available;rotation.append(mobileAction);row.append(rotation);
      for(const key of ['potential_demand_mm','typical_year_shortfall_mm','critical_stress_days_typical','heat_stress_days_typical']){
        const value=state.available?entry.metrics?.[key]:null,diff=F.delta(value,state.available?state.data.baseline.metrics?.[key]:null),td=el('td','leader-number');td.append(el('strong','',F.format(value)));
        if(index)td.append(el('small',!F.finite(diff)||diff===0?'neutral':diff<0?'improvement':'tradeoff',!F.finite(diff)?'—':diff===0?'Same':`${diff>0?'+':'−'}${F.format(Math.abs(diff))}`));row.append(td);
      }
      const nitrogen=el('td'),level=state.available?entry.ratings?.nitrogen?.label:null;nitrogen.append(el('span',`nitrogen-badge nitrogen-${['low','medium','high'].includes(level)?level:'unknown'}`,level||'—'));row.append(nitrogen);
      const action=el('td'),b=button(index===state.selected?'Showing ↓':'Show ↓',()=>selectEntry(index),'button row-action');b.disabled=!state.available;action.append(b);row.append(action);body.append(row);
    });t.append(body);const wrap=el('div','leaderboard-scroll');wrap.append(t);host.append(wrap);
    const legend=el('div','leaderboard-key');legend.append(el('span','improvement','− Lower than original'),el('span','tradeoff','+ Higher than original'),el('span','neutral','Nitrogen: qualitative demand, not fertilizer savings.'));host.append(legend);
    const summary=$('recommendation-summary');summary.replaceChildren();
    if(state.recommended!=null){const pick=entries()[state.recommended],line=el('div','recommendation-line');line.append(el('strong','','Suggested alternative'),sequence(pick),el('span','','Selected for your priorities; review the favorable and unfavorable differences below.'));summary.append(line);}
    else if(state.available)summary.append(note('No recommended alternative meets the current constraints. Your original rotation remains the reference.'));
    host.append(details('Trade-offs and model limitations',[
      note('The green recommendation is the backend’s balanced choice (or highest returned score). It is not universally better; review unfavorable differences too. Lower crop water need alone is not proof of improvement.'),
      ...entries().map((entry,index)=>{const list=el('ul');[...(entry.tradeoffs||[]),...(entry.warnings||[])].forEach(text=>list.append(el('li','',text)));return details(index===0?'Original rotation':`Option ${index}: ${F.sequence(entry)}`,[note('Timing and pest/disease notes are prototype assumptions, not yield or field-impact predictions.'),list]);})
    ]));
  }
  function selectEntry(index){
    if(!state.available)return;state.selected=index;state.blindEpoch++;state.blind=null;state.blindBaseline=null;state.model=0;state.phase=0;state.cycle=1;state.year=null;state.weeks={};
    drawLeaderboard();$('analysis-rotation-name').textContent=F.sequence(active());publishContext();loadBlind();$('blind-spots').scrollIntoView({behavior:'smooth',block:'start'});
  }
  function table(headers,rows) {
    const wrap=el('div','table-scroll'), t=el('table','data-table'), head=el('thead'), tr=el('tr');
    headers.forEach(h=>{const th=el('th','',h);th.scope='col';tr.append(th);});head.append(tr);t.append(head);
    const body=el('tbody');rows.forEach(cells=>{const row=el('tr');cells.forEach(cell=>{const td=el('td');td.append(cell instanceof Node?cell:document.createTextNode(String(cell)));row.append(td);});body.append(row);});
    t.append(body);wrap.append(t);return wrap;
  }
  function drawRotationTimeline(bs,run) {
    const rotation=active().rotation.map(r=>r.crop),phase=run.phases[state.phase]||run.phases[0];
    const view=F.cycleView(phase.daily,rotation,phase.phase,state.cycle);state.cycle=view.cycle;
    const panel=el('div','rotation-timeline');panel.id='rotation-timeline';
    const path=el('div','rotation-path');path.setAttribute('aria-label','Crop rotation in chronological harvest-year order');
    view.steps.forEach((step,index)=>{
      if(index)path.append(el('span','carry-arrow','→'));
      const card=el('div',`rotation-step crop-${step.crop}`);card.append(el('span','step-year',`Year ${step.year}`),el('strong','',cname(step.crop)));path.append(card);
    });
    path.append(el('span','rotation-repeat','↻ Repeat'));panel.append(path,el('p','carry-caption','One soil-water store carries forward through every crop, season and year.'));
    const summary=el('div','rotation-stress-totals');
    for(const [key,title] of [['water','Water stress'],['heat','Heat exposure'],['combined','Both together']]){
      const n=el('div',`stress-total total-${key}`);n.append(el('span','',title),el('strong','',`${F.format(bs.summary?.annualized_days?.[key])} days/year`));
      const range=bs.model_range?.annualized_days?.[key];if(range)n.append(el('small','',`Models: ${F.format(range.min)}–${F.format(range.max)}`));summary.append(n);
    }
    panel.append(summary,note('Above: average sensitive-period stress days per year over the full weather record; the middle result across three models. All rotation starting positions are included.'));
    const heading=el('div','timeline-heading');heading.append(el('h4','','Follow one modeled rotation cycle'),el('span','timeline-model',run.model));panel.append(heading);
    panel.append(note(`Illustration uses ${view.start.slice(0,4)}–${view.endYear} reference weather adjusted using climate projections through 2050. These are not forecasts of particular future years.`));
    const ns='http://www.w3.org/2000/svg', svg=(tag,attrs={},text)=>{const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(text!=null)n.textContent=text;return n;};
    const width=Math.max(1080,rotation.length*320),left=125,right=22,plot=width-left-right,count=view.days.length;
    const x=index=>left+index/count*plot;
    const graph=svg('svg',{viewBox:`0 0 ${width} 525`,role:'img','aria-labelledby':'rotation-chart-title rotation-chart-desc'});
    graph.append(svg('title',{id:'rotation-chart-title'},'Continuous soil water, daily unmet demand and stress through the rotation'),svg('desc',{id:'rotation-chart-desc'},'Crop bands follow the model calendar. The blue line shows end-of-day stored water, brown bars show daily unmet demand, and the three bottom lanes mark water stress, heat exposure and both. Water carries across year boundaries.'));
    const future=state.selected===0?state.data.time_machine?.future_2031_2050:active().time_machine?.future_2031_2050;
    const capacity=future?.models?.[run.model]?.capacity_mm;
    const ymax=F.finite(capacity)&&capacity>0?capacity:Math.max(1,...view.days.map(d=>d.storage_mm));
    const top=154,base=285,h=base-top,y=value=>base-value/ymax*h;
    const months=view.days.map((day,index)=>({day,index})).filter(({day,index})=>index===0||day.date.slice(0,7)!==view.days[index-1].date.slice(0,7));
    for(const {day,index} of months){const month=Number(day.date.slice(5,7));graph.append(svg('line',{x1:x(index),x2:x(index),y1:106,y2:493,stroke:'#e4eadd','stroke-width':.7}));if(index===0||[1,4,7,10].includes(month))graph.append(svg('text',{x:x(index)+3,y:131,class:'chart-month'},new Date(day.date+'T00:00:00Z').toLocaleString('en-CA',{month:'short',timeZone:'UTC'})));}
    for(const step of view.steps){
      graph.append(svg('rect',{x:x(step.start)+1,y:9,width:x(step.end)-x(step.start)-2,height:40,rx:5,class:`year-block chart-crop-${step.crop}`}));
      graph.append(svg('text',{x:(x(step.start)+x(step.end))/2,y:34,'text-anchor':'middle',class:'chart-year'},`Year ${step.year} · ${cname(step.crop)}`));
      if(step.start>0)graph.append(svg('line',{x1:x(step.start),x2:x(step.start),y1:49,y2:493,stroke:'#98ad91','stroke-width':1.2,'stroke-dasharray':'4 4'}));
    }
    graph.append(svg('text',{x:6,y:85,class:'chart-label'},'Growing crop'));
    for(const band of view.bands){
      const rect=svg('rect',{x:x(band.start),y:65,width:Math.max(.6,x(band.end)-x(band.start)),height:31,class:`crop-band chart-crop-${band.crop||'off'}`});
      rect.append(svg('title',{},`${cname(band.crop)||'Between crops'} · reference dates ${view.days[band.start].date} to ${view.days[band.end-1].date}`));graph.append(rect);
      const span=x(band.end)-x(band.start);if(span>64)graph.append(svg('text',{x:(x(band.start)+x(band.end))/2,y:85,'text-anchor':'middle',class:'chart-crop-label'},band.crop?cname(band.crop):'Between crops'));
    }
    graph.append(svg('text',{x:6,y:182,class:'chart-label'},'Soil water'),svg('text',{x:6,y:199,class:'chart-unit'},'remaining · mm'));
    for(const value of [0,ymax/2,ymax]){graph.append(svg('line',{x1:left,x2:width-right,y1:y(value),y2:y(value),stroke:'#d7e1d0','stroke-width':1}),svg('text',{x:left-9,y:y(value)+4,'text-anchor':'end',class:'chart-tick'},F.format(value,0)));}
    const points=view.days.map((day,index)=>`${x(index).toFixed(2)},${y(day.storage_mm).toFixed(2)}`);
    graph.append(svg('path',{d:`M${x(0)},${base} L${points.join(' L')} L${x(count-1)},${base} Z`,class:'water-area'}));
    graph.append(svg('polyline',{points:points.join(' '),class:'water-line',fill:'none','stroke-width':1.6}));
    graph.append(svg('text',{x:6,y:333,class:'chart-label'},'Water shortfall'),svg('text',{x:6,y:350,class:'chart-unit'},'unmet · mm/day'));
    const peak=Math.max(1,...view.days.map(d=>d.unmet_demand_mm)),shortBase=382,shortTop=320;
    graph.append(svg('line',{x1:left,x2:width-right,y1:shortBase,y2:shortBase,stroke:'#d8e1d0'}));
    graph.append(svg('text',{x:left-9,y:shortBase+3,'text-anchor':'end',class:'chart-tick'},'0'));
    const actualPeak=Math.max(...view.days.map(d=>d.unmet_demand_mm));
    if(actualPeak>0)graph.append(svg('text',{x:left-9,y:shortTop+4,'text-anchor':'end',class:'chart-tick'},F.format(peak)));
    else graph.append(svg('text',{x:left+8,y:350,class:'chart-zero'},'No unmet demand in this example cycle'));
    view.days.forEach((day,index)=>{if(day.unmet_demand_mm>0){const bh=day.unmet_demand_mm/peak*(shortBase-shortTop),bar=svg('rect',{x:x(index),y:shortBase-bh,width:Math.max(.7,plot/count),height:bh,class:'shortfall-bar'});bar.append(svg('title',{},`${day.crop?cname(day.crop):'Between crops'} · reference date ${day.date} · unmet demand ${F.format(day.unmet_demand_mm,2)} mm`));graph.append(bar);}});
    [['water','Water stress',416],['heat','Heat exposure',446],['combined','Both together',476]].forEach(([kind,label,cy])=>{
      graph.append(svg('text',{x:6,y:cy+11,class:'chart-label'},label),svg('rect',{x:left,y:cy,width:plot,height:14,rx:2,class:'stress-lane'}));
      for(const band of F.flagBands(view.days,kind)){const r=svg('rect',{x:x(band.start),y:cy,width:Math.max(1,x(band.end)-x(band.start)),height:14,rx:1,class:`stress-mark mark-${kind}`});r.append(svg('title',{},`${label} · reference dates ${view.days[band.start].date} to ${view.days[band.end-1].date}`));graph.append(r);}
    });
    const wrap=el('div','timeline-chart-scroll');wrap.append(graph);panel.append(el('p','timeline-scroll-hint','Swipe sideways to follow the full rotation →'),wrap);
    panel.append(el('p','timeline-reading','Read left → right: the crop changes, but the soil-water line continues. Lower blue levels mean less stored water; brown bars show demand the model could not meet.'));
    panel.append(note('Year labels identify harvest years; winter wheat may begin the previous autumn. Crop bands follow the model’s approximate calendars. Stress marks apply only within assumed sensitive windows; an unmarked off-window day is not proof of no stress.'));
    const controls=el('div','control-row'),modelLabel=el('label','','Example climate model'),model=el('select');model.id='timeline-model';
    bs.runs.forEach((r,i)=>model.add(new Option(r.model,String(i))));model.value=String(state.model);model.addEventListener('change',()=>{state.model=Number(model.value);renderBlind();});modelLabel.append(model);controls.append(modelLabel);
    const phaseLabel=el('label','','Example starting crop'),pSelect=el('select');pSelect.id='timeline-phase';
    run.phases.forEach((p,i)=>pSelect.add(new Option(`Position ${p.phase+1}: ${cname(p.first_crop)}`,String(i))));pSelect.value=String(state.phase);pSelect.addEventListener('change',()=>{state.phase=Number(pSelect.value);state.cycle=1;renderBlind();});phaseLabel.append(pSelect);controls.append(phaseLabel);
    const cycleLabel=el('label','','Example reference-weather cycle'),cycle=el('select');cycle.id='timeline-cycle';
    view.cycleNumbers.forEach(n=>{const year=Number(phase.daily[0].date.slice(0,4))+n*rotation.length;cycle.add(new Option(`${year}–${year+rotation.length-1}`,String(n)));});cycle.value=String(view.cycle);cycle.addEventListener('change',()=>{state.cycle=Number(cycle.value);renderBlind();});cycleLabel.append(cycle);controls.append(cycleLabel);
    panel.append(details('Inspect another model or reference cycle',[
      controls,note('This chart shows one real model run, not an average weather sequence. The example is not used to rank rotations; rankings use the full climate period, independent models and all rotation starting positions.'),
      note('The crop-specific daily demand is calculated by the backend as Kc × ET0. That demand series is not exposed by the current daily API, so it is not reconstructed here. The chart uses the returned soil storage and unmet demand. The blue line is end-of-day storage; stress flags use the engine’s after-rain, before-ET threshold.')
    ]));return panel;
  }
  function drawEvents(bs,run) {
    const content=[],control=el('div','control-row');
    if(state.climate==='future')content.push(note(`Event records below are from ${run.model}; dates are historical sequence dates, not forecast dates.`));
    const pLabel=el('label','','First crop in the rotation'), pSelect=el('select');pSelect.id='blind-phase';
    run.phases.forEach((p,i)=>pSelect.add(new Option(`${p.phase+1}: starts with ${cname(p.first_crop)}`,String(i))));
    if(!run.phases[state.phase])state.phase=0;pSelect.value=String(state.phase);
    pSelect.addEventListener('change',()=>{state.phase=Number(pSelect.value);state.year=null;renderBlind();});pLabel.append(pSelect);control.append(pLabel);
    const phase=run.phases[state.phase];
    const years=[...new Set(phase.daily.map(d=>d.date.slice(0,4)))];
    if(!years.includes(state.year))state.year=years.at(-1);
    const yLabel=el('label','',state.climate==='future'?'Historical sequence year':'Year'), ySelect=el('select');ySelect.id='blind-year';
    years.forEach(y=>ySelect.add(new Option(y,y)));ySelect.value=state.year;ySelect.addEventListener('change',()=>{state.year=ySelect.value;renderBlind();});yLabel.append(ySelect);control.append(yLabel);content.push(control);
    const stats=phase.event_statistics;
    content.push(note(`Across this phase’s full period: longest same-crop/type event ${F.format(stats?.longest_event_duration_days)} days; average duration ${F.format(stats?.mean_event_duration_days)} days. Events split when stress type changes.`));
    const events=phase.events.filter(e=>e.start_date<=`${state.year}-12-31`&&e.end_date>=`${state.year}-01-01`);
    if(!events.length)content.push(note('No sensitive-window exposure events in this selected year. This does not imply no stress outside the estimated window.'));
    else {
      const rows=events.map(e=>{
        const daily=details('Daily diagnostics',[table(['Date','Crop','Rain mm','Tmax °C','Storage mm','Unmet mm','Intensity 0–1','Heat exceedance °C'],phase.daily.filter(d=>d.date>=e.start_date&&d.date<=e.end_date).map(d=>[d.date,cname(d.crop),F.format(d.precip_mm),F.format(d.tmax_c),F.format(d.storage_mm),F.format(d.unmet_demand_mm),F.format(d.water_depletion_intensity,2),F.format(d.heat_exceedance_c)]))]);
        return [`${e.start_date} → ${e.end_date}`,cname(e.crop),stressName(e.stress_type),e.duration_days,
          `${F.format(e.mean_water_depletion_intensity,2)} / ${F.format(e.max_water_depletion_intensity,2)}`,F.format(e.cumulative_unmet_demand_mm),F.format(e.cumulative_heat_exceedance_degree_days),F.format(e.max_temperature_c),daily];
      });content.push(table(['Sequence dates','Crop','Exposure','Days','Mean / max intensity','Unmet mm','Heat °C·days','Max °C','Inspect'],rows));
    }
    content.push(note('Depletion intensity is normalized water depletion beyond the engine’s existing threshold, not percent crop damage. Heat degree-days sum daily Tmax exceedance; they are not an hourly heat dose. Event dates remain historical sequence dates in future scenarios.'));
    return details('Consecutive events & daily diagnostics',content);
  }
  function renderBlind(){
    const bs=state.blind;if(!bs)return;const host=$('blind-content');
    const focused=host.contains(document.activeElement)?document.activeElement.id:null;
    const opened=new Set([...host.querySelectorAll('details[open]')].map(d=>d.querySelector('summary')?.textContent));
    host.replaceChildren();
    const run=bs.runs[state.model]||bs.runs[0];
    try{host.append(drawRotationTimeline(bs,run));}
    catch(error){host.append(note(`The rotation illustration is unavailable: ${error.message}`));}
    host.append(drawEvents(bs,run));
    host.querySelectorAll('details').forEach(d=>{if(opened.has(d.querySelector('summary')?.textContent))d.open=true;});if(focused)$(focused)?.focus({preventScroll:true});
  }
  async function loadBlind(){
    if(!state.available)return;const epoch=state.epoch,token=++state.blindEpoch,rotation=active().rotation.map(r=>r.crop);
    $('analysis-rotation-name').textContent=F.sequence(active());$('blind-content').replaceChildren();$('blind-content').setAttribute('aria-busy','true');message('Building the continuous rotation view…',false,'blind-status');
    try{
      const request={...state.body,climate_period:'future'};
      const bs=await api('/blind-spots',{...request,current_rotation:rotation});if(epoch!==state.epoch||token!==state.blindEpoch)return;
      if(bs.status!=='available')throw new Error(bs.reason||'Future calendar data unavailable.');
      state.blind=bs;renderBlind();message('',false,'blind-status');
    }catch(error){if(epoch===state.epoch&&token===state.blindEpoch){message(error.message,true,'blind-status');$('blind-status').append(button('Try again',loadBlind));}}
    finally{if(epoch===state.epoch&&token===state.blindEpoch)$('blind-content').removeAttribute('aria-busy');}
  }
  function draw(){
    const data=state.data;state.available=!!data.baseline?.metrics&&data.scores_available!==false&&data.scoring_period==='future_2031_2050';
    state.recommended=state.available?F.recommendedIndex(data):null;state.selected=state.recommended??0;
    $('dashboard-content').hidden=false;$('results-state').textContent=state.available?'Climate projections through 2050':'Comparison unavailable';
    $('results-subtitle').textContent=data.anchor?`${data.anchor.id.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())} regional data · ${F.format(data.anchor.distance_km)} km from your selected point`:'';
    drawLeaderboard();publishContext();
    if(!state.available){message(F.baselineNotice(data.reason),true);$('analysis-rotation-name').textContent=F.sequence(data.baseline||{});$('blind-content').replaceChildren(note('No calendars are shown because the model cannot fairly evaluate this input. Your crop sequence has not been changed.'));message('',false,'blind-status');return;}
    message(data.status==='insufficient_feasible_alternatives'?(data.reason||'Fewer alternatives meet your constraints; none were relaxed.'):'');loadBlind();
  }
  async function recommend(){
    const epoch=state.epoch;$('results').hidden=false;$('dashboard-content').hidden=true;$('results').setAttribute('aria-busy','true');$('results-state').textContent='Finding your future-climate options…';$('compareButton').disabled=true;
    message('Comparing feasible rotations under the three future climate models…');
    try{const data=await api('/recommend',{...state.body,climate_period:'future'});if(epoch!==state.epoch)return;state.data=data;draw();}
    catch(error){if(epoch===state.epoch){$('results-state').textContent='Unavailable';message(error.message,true);}}
    finally{if(epoch===state.epoch){$('results').removeAttribute('aria-busy');$('compareButton').disabled=false;}}
  }
  window.addEventListener('terrashift:compare',event=>{
    invalidate();try{state.body=F.request(event.detail);state.model=0;state.phase=0;state.cycle=1;state.weeks={};recommend();$('results').hidden=false;$('results').scrollIntoView({behavior:'smooth',block:'start'});}
    catch(error){$('results').hidden=false;message(error.message,true);}
  });
})();
