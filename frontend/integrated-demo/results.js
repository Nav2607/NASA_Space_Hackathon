/* TerraShift climate screening — actual NASA POWER data only, no invented outputs. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const CROP_WINDOWS={
    corn:{start:[5,10],end:[10,15],kc:.90,label:'Corn'},
    soybean:{start:[5,20],end:[10,5],kc:.85,label:'Soybean'},
    winter_wheat:{start:[10,1],end:[7,20],kc:.90,label:'Winter wheat',crossYear:true},
    red_clover:{start:[4,20],end:[9,30],kc:.80,label:'Red clover'},
    cereal_rye:{start:[10,8],end:[5,1],kc:.80,label:'Cereal rye',crossYear:true}
  };
  const SOURCE_START=2012,SOURCE_END=2025;
  const powerURL='https://power.larc.nasa.gov/api/temporal/daily/point';
  let selected=null,weather=null,activeScenario='typical',busy=false;
  const fmt=n=>Math.round(n).toLocaleString('en-CA');
  const avg=values=>values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
  const monday=date=>Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),date.getUTCDate());
  const dataToUTC=(y,m,d)=>Date.UTC(y,m-1,d);
  const fmtDiff=n=>n>0?`+${Math.round(n)}%`:`${Math.round(n)}%`;
  function status(text,error=false){$('results-message').textContent=text;$('results-message').className=error?'results-message error':'results-message';}
  function show(){ $('results').hidden=false;$('results').scrollIntoView({behavior:'smooth',block:'start'}); }
  function setBusy(on){busy=on;$('compareButton').disabled=on;$('results-state').textContent=on?'Loading climate data…':'Historical climate screening';}
  function dailyFromPOWER(payload){
    const obj=payload?.properties?.parameter;
    const prec=obj?.PRECTOTCORR,hi=obj?.T2M_MAX,lo=obj?.T2M_MIN;
    if(!prec||!hi||!lo)throw new Error('NASA POWER returned an unexpected daily data format.');
    const result={};
    for(const key of Object.keys(prec)){
      const p=Number(prec[key]),tmax=Number(hi[key]),tmin=Number(lo[key]);
      if(!Number.isFinite(p)||!Number.isFinite(tmax)||!Number.isFinite(tmin)||p<0||p===-999||tmax<=-900||tmin<=-900)continue;
      const date=Date.UTC(Number(key.slice(0,4)),Number(key.slice(4,6))-1,Number(key.slice(6,8)));
      result[date]={p,tmax,tmin};
    }
    return result;
  }
  async function fetchBlock(lat,lon,start,end){
    const qs=new URLSearchParams({parameters:'PRECTOTCORR,T2M_MAX,T2M_MIN',community:'AG',longitude:String(lon),latitude:String(lat),start:String(start)+'0101',end:String(end)+'1231',format:'JSON'});
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
    try{
      const response=await fetch(powerURL+'?'+qs,{signal:controller.signal});
      if(!response.ok)throw new Error(`NASA POWER request failed (${response.status}).`);
      return dailyFromPOWER(await response.json());
    } finally{clearTimeout(timer);}
  }
  async function loadWeather(lat,lon){
    const key=`${lat.toFixed(2)},${lon.toFixed(2)}`;
    if(weather?.key===key)return weather.data;
    status('Requesting NASA POWER daily rainfall and temperatures for your selected region. This can take a moment.');
    const [a,b]=await Promise.all([fetchBlock(lat,lon,2012,2018),fetchBlock(lat,lon,2019,2025)]);
    const merged={...a,...b};
    if(Object.keys(merged).length<4500)throw new Error('Not enough complete daily weather records were returned for this location.');
    weather={key,data:merged};return merged;
  }
  function ra(latitude,dayOfYear){
    const lat=latitude*Math.PI/180;
    const dr=1+.033*Math.cos(2*Math.PI*dayOfYear/365);
    const delta=.409*Math.sin(2*Math.PI*dayOfYear/365-1.39);
    const ws=Math.acos(Math.max(-1,Math.min(1,-Math.tan(lat)*Math.tan(delta))));
    return 24*60/Math.PI*.0820*dr*(ws*Math.sin(lat)*Math.sin(delta)+Math.cos(lat)*Math.cos(delta)*Math.sin(ws));
  }
  // FAO-56 Hargreaves reference-ET approximation (requires Tmin,Tmax,latitude), not full Penman-Monteith.
  function et0(date,tmin,tmax,lat){
    const year=date.getUTCFullYear();
    const day=Math.floor((monday(date)-Date.UTC(year,0,1))/86400000)+1;
    return Math.max(0,.0023*( (tmin+tmax)/2+17.8 )*Math.sqrt(Math.max(0,tmax-tmin))*ra(lat,day)*.408);
  }
  function materializePlan(input){
    // Keep users' year assignments. For a short pattern, repeat it to fill four years.
    const positions=input.currentRotation.map(r=>({
      ...r,offset:r.growingYear-input.planning.firstYear
    })).filter(x=>x.offset>=0&&x.offset<4);
    if(!positions.length)return [];
    const lastYear=Math.max(...positions.map(x=>x.offset));
    const cycle=lastYear+1;
    const result=[];
    for(let offset=0;offset<4;offset++){
      const from=positions.filter(x=>x.offset===offset%cycle);
      from.forEach(p=>result.push({...p,offset,sequence:result.length+1,repeatOf:p.sequence}));
    }
    return result;
  }
  function alternativePlans(input){
    const baseline=materializePlan(input);
    const baselineMain=baseline.filter(r=>!['red_clover','cereal_rye'].includes(r.crop));
    const mainOptions=[
      {id:'diverse',title:'Add winter wheat',crops:['corn','soybean','winter_wheat','soybean']},
      {id:'soyfirst',title:'Soybean–wheat rotation',crops:['soybean','winter_wheat','corn','soybean']},
      {id:'wheatfocus',title:'Wheat in the cycle',crops:['corn','winter_wheat','soybean','winter_wheat']}
    ];
    const base={id:'baseline',title:'Your usual rotation',entries:baseline,baseline:true};
    const allowed=arr=>input.mustGrow.every(x=>arr.some(r=>r.crop===x))&&!arr.some(r=>input.avoid.includes(r.crop));
    const used=new Set([baseline.map(x=>x.crop+'@'+x.offset).join('|')]);
    const alternatives=[];
    for(const opt of mainOptions){
      const entries=opt.crops.map((crop,offset)=>({crop,offset,dateSource:'provisional_calendar',plantingDate:null,harvestDate:null,sequence:offset+1}));
      const sig=entries.map(x=>x.crop+'@'+x.offset).join('|');
      if(used.has(sig)||!allowed(entries))continue;
      used.add(sig);alternatives.push({...opt,entries});
    }
    // Every alternative must satisfy the declared crop preferences. Baseline is displayed regardless.
    return [base,...alternatives.slice(0,3)];
  }
  function getCropSpan(entry,simulationStart,inputYear){
    const model=CROP_WINDOWS[entry.crop];if(!model)return null;
    const y=simulationStart+entry.offset;
    if(entry.dateSource==='farmer_provided'&&entry.plantingDate&&entry.harvestDate){
      const sp=new Date(entry.plantingDate+'T00:00:00Z'),ep=new Date(entry.harvestDate+'T00:00:00Z');
      const start=dataToUTC(y,sp.getUTCMonth()+1,sp.getUTCDate());
      const end=dataToUTC(y+ep.getUTCFullYear()-sp.getUTCFullYear(),ep.getUTCMonth()+1,ep.getUTCDate());
      return {start,end,source:'farmer'};
    }
    return {start:dataToUTC(y,...model.start),end:dataToUTC(y+(model.crossYear?1:0),...model.end),source:'provisional'};
  }
  function dryWindows(data){
    const scores=[];
    for(let y=SOURCE_START;y<=SOURCE_END-4;y++){
      let rain=0,n=0;
      for(let t=dataToUTC(y,4,1);t<=dataToUTC(y,9,30);t+=86400000){const d=data[t];if(d){rain+=d.p;n++;}}
      if(n>=175)scores.push({y,rain});
    }
    return scores;
  }
  function assess(input,plan,data,years){
    const results=[];
    for(const startYear of years){
      let demand=0,rain=0,shortfall=0,heat=0,coveredDays=new Set(),totalDays=0;
      for(const entry of plan.entries){
        const span=getCropSpan(entry,startYear,input.planning.firstYear);
        if(!span)continue;
        const crop=CROP_WINDOWS[entry.crop];
        let goodDays=0;
        for(let t=span.start;t<=span.end;t+=86400000){
          const w=data[t];if(!w)continue;
          const date=new Date(t);
          const cropET=et0(date,w.tmin,w.tmax,input.location.lat)*crop.kc;
          demand+=cropET;rain+=w.p;
          // Unmet climate-demand indicator, not irrigation need or observed soil water balance.
          shortfall+=Math.max(0,cropET-w.p);
          heat+=Number(w.tmax>=32);
          coveredDays.add(t);goodDays++;
        }
        totalDays+=goodDays;
      }
      if(totalDays>=200)results.push({demand,rain,shortfall,heat,scheduled:coveredDays.size});
    }
    return results.length?{
      n:results.length,demand:avg(results.map(x=>x.demand)),rain:avg(results.map(x=>x.rain)),shortfall:avg(results.map(x=>x.shortfall)),
      heat:avg(results.map(x=>x.heat)),scheduled:avg(results.map(x=>x.scheduled))
    }:null;
  }
  // Farmer-first result interface. Existing NASA POWER calculation is retained.
  const styles = `
    #metrics-bar {display:none!important}
    .ts-summary{background:#eaf0e5;border:1px solid #d7e2d1;border-radius:20px;padding:24px;margin:18px 0 18px}
    .ts-kicker{color:#66816b;font-size:11px;font-weight:800;letter-spacing:1.3px;text-transform:uppercase;margin-bottom:9px}
    .ts-summary h3{color:#244b39;font-size:clamp(21px,3vw,29px);line-height:1.2;margin:0 0 9px;max-width:800px}
    .ts-summary p{margin:0;color:#52675a;font-size:14px;line-height:1.6;max-width:760px}
    .ts-summary .ts-disclaimer{font-size:12px;margin-top:10px;color:#637669}
    .ts-section-head{margin:22px 0 12px}
    .ts-section-head h3{margin:0 0 4px;font-size:20px;color:#254b38}
    .ts-section-head p{margin:0;color:#637466;font-size:13px}
    #comparison-cards.ts-layout{display:grid;grid-template-columns:1fr 1fr;gap:15px}
    .ts-card{background:#fff;border:1px solid #d9e2d4;border-radius:18px;padding:19px;min-width:0;display:flex;flex-direction:column;gap:12px}
    .ts-card.current{background:#faf8ef;border-color:#e2d8b9}
    .ts-card.featured{border:2px solid #83a48b;box-shadow:0 5px 18px rgba(35,75,55,.07)}
    .ts-card small{font-size:11px;color:#708174;letter-spacing:1px;text-transform:uppercase;font-weight:800}
    .ts-card h4{font-size:19px;color:#244b39;margin:0;line-height:1.3}
    .ts-chips{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
    .ts-chip{border-radius:8px;background:#edf2e9;color:#315a43;padding:7px 9px;font-size:11px;font-weight:750}
    .ts-arrow{color:#92a293;font-size:12px}
    .ts-number{font-size:31px;font-weight:850;letter-spacing:-1px;color:#284c3a;line-height:1.2}
    .ts-number-note{font-size:12px;color:#657568}
    .ts-difference{background:#eaf2e8;border-radius:9px;padding:10px 12px;font-size:13px;font-weight:800;color:#2c6243}
    .ts-difference.worse{background:#f9efe0;color:#986436}
    .ts-card p{font-size:13px;color:#52675a;line-height:1.6;margin:0}
    .ts-btn{display:block;min-height:43px;margin-top:auto;border:1px solid #71947a;border-radius:10px;background:#fff;color:#29543d;font-size:13px;font-weight:800;padding:10px 13px;cursor:pointer}
    .ts-btn:hover,.ts-btn[aria-expanded="true"]{background:#2a5b42;color:white}
    .ts-secondary{margin:18px 0 0;padding:0;border:0}
    .ts-secondary>summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:12px;align-items:center;border:1px solid #d7e2d4;border-radius:13px;background:#f6f7f0;color:#244d3e;font-weight:800;padding:15px 17px}
    .ts-secondary>summary::-webkit-details-marker{display:none}
    .ts-other-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px;padding-top:13px}
    .ts-other-card{border:1px solid #dae3d5;border-radius:14px;background:#fff;padding:16px;display:flex;flex-direction:column;gap:9px}
    .ts-other-card h4{margin:0;color:#284f3b;font-size:16px}
    .ts-other-card p{margin:0;font-size:12px;color:#647266;line-height:1.5}
    .ts-detail{margin-top:18px;border:1px solid #d9e3d5;border-radius:17px;background:#fafbf6;padding:18px}
    .ts-detail h3{font-size:18px;margin:0 0 8px;color:#244b39}
    .ts-detail p{font-size:13px;color:#586b5c;line-height:1.6;margin:0 0 12px}
    .ts-table{display:grid;grid-template-columns:1.5fr 1fr 1fr;gap:0}
    .ts-table div{padding:11px 8px;border-bottom:1px solid #e3e9df;font-size:12px}
    .ts-table div:nth-child(3n+2),.ts-table div:nth-child(3n){text-align:right;font-weight:750}
    .ts-table .ts-th{color:#637769;font-weight:800;border-bottom:2px solid #d3dfd0}
    .ts-figure{font-size:13px;color:#304e3c;font-weight:750}
    .ts-bars{display:grid;gap:11px;margin-top:12px}
    .ts-bar-row{display:grid;grid-template-columns:110px 1fr 65px;align-items:center;gap:10px;font-size:12px;color:#425c48}
    .ts-track{height:10px;background:#e5ebe0;border-radius:20px;overflow:hidden}
    .ts-fill{height:100%;background:#74987e;border-radius:20px}
    .ts-bar-row:first-child .ts-fill{background:#ccb47c}
    .ts-metric-switch{padding:10px;margin:12px 0 0;max-width:320px;min-height:42px;font-size:13px}
    .ts-no-alts{border:1px solid #e5d7b8;background:#faf5e8;border-radius:14px;padding:16px;color:#715e39;font-size:13px}
    .ts-muted{font-size:12px;color:#627365;line-height:1.5}
    @media(max-width:760px){#comparison-cards.ts-layout{grid-template-columns:1fr}.ts-other-grid{grid-template-columns:1fr}.ts-bar-row{grid-template-columns:88px 1fr 58px;gap:7px}}
  `;
  const style=document.createElement('style');style.textContent=styles;document.head.append(style);
  const node=(tag,className='',text='')=>{const el=document.createElement(tag);if(className)el.className=className;el.textContent=text;return el;};
  const percent=(a,b)=>b>0.01?(a/b-1)*100:null;
  const cropName=c=>CROP_WINDOWS[c]?.label||c;
  const seq=entries=>Array.from({length:4},(_,i)=>entries.filter(e=>e.offset===i).map(e=>cropName(e.crop)).join(' + ')||'Fallow');
  let focusedId=null;
  let lastRender=null;
  let selectedMetric='demand';
  const metricDefs={
    demand:{label:'Estimated crop water demand',unit:'mm',notes:'Atmospheric crop demand, not irrigation volume.'},
    shortfall:{label:'Same-day rain gap',unit:'mm',notes:'Sum of daily crop demand minus same-day rainfall when positive. This ignores soil water storage, so it is NOT irrigation need.'},
    rain:{label:'Rain during crop periods',unit:'mm',notes:'Rain that fell while crops were scheduled. More rainfall is not automatically better.'},
    heat:{label:'Hot days (≥32°C)',unit:'days',notes:'A simple exposure count, not crop damage or survival.'}
  };
  function cropChips(host,plan){
    seq(plan.entries).forEach((c,i)=>{
      if(i)host.append(node('span','ts-arrow','→'));
      host.append(node('span','ts-chip',`Y${i+1}: ${c}`));
    });
  }
  function changePhrase(amount,baseline){
    const p=percent(amount,baseline);
    if(p===null)return 'Not comparable as a percentage';
    if(Math.abs(p)<0.5)return 'About the same water demand';
    return `${Math.round(Math.abs(p))}% ${p<0?'less':'more'} estimated water demand`;
  }
  function selectCandidate(items){
    const alternatives=items.filter(p=>!p.baseline);
    // This is an illustrative ranking only within the water-demand screening metric.
    return alternatives.sort((a,b)=>a.scores.demand-b.scores.demand)[0]||null;
  }
  function clearGenerated(){
    ['ts-simple-intro','ts-other-options','ts-detail-panel','ts-section-title'].forEach(id=>$(id)?.remove());
  }
  function summary(best,base,n){
    const x=node('section','ts-summary');x.id='ts-simple-intro';
    x.append(node('div','ts-kicker','IN SHORT · HISTORICAL CLIMATE SCREENING'));
    if(best){
      x.append(node('h3','',`${best.title} is worth comparing.`));
      const p=percent(best.scores.demand,base.scores.demand);
      let text=p===null?'Compare the absolute values below.':p<-.5?`It shows about ${Math.round(-p)}% less estimated crop water demand than your current rotation.`:p>.5?`It shows about ${Math.round(p)}% more estimated crop water demand than your current rotation.`:'Its estimated crop water demand is similar to your current rotation.';
      x.append(node('p','',`${text} This is the lowest-demand option among ${n} preset alternatives in this screening—not necessarily the best crop plan for your farm.`));
    }else{
      x.append(node('h3','','Your current plan is ready to review.'));
      x.append(node('p','','No preset alternatives meet your crop preferences. Adjust required or avoided crops to see more options.'));
    }
    x.append(node('p','ts-disclaimer','These are modeled historical-weather comparisons, not yield or irrigation predictions.'));
    $('metrics-bar').before(x);
  }
  function card(plan,base,featured=false){
    const current=!!plan.baseline;
    const c=node('article','ts-card'+(current?' current':'')+(featured?' featured':''));
    c.append(node('small','',current?'YOUR FARM TODAY':'ONE OPTION TO CONSIDER'));
    c.append(node('h4','',current?'Your usual rotation':plan.title));
    const chips=node('div','ts-chips');cropChips(chips,plan);c.append(chips);
    c.append(node('div','ts-number',`${fmt(plan.scores.demand)} mm`));
    c.append(node('div','ts-number-note','Estimated water demand over the four-year crop sequence'));
    if(current){
      c.append(node('p','','Your starting point. Every alternative is compared under the same historical weather periods.'));
    }else{
      const delta=node('div','ts-difference',changePhrase(plan.scores.demand,base.scores.demand));
      if(plan.scores.demand>base.scores.demand)delta.classList.add('worse');
      c.append(delta);
      c.append(node('p','','Water is only one part of the decision. Crop timing, fertilizer, costs and equipment also matter.'));
      const btn=node('button','ts-btn',focusedId===plan.id?'Hide the details':'See the trade-offs');btn.type='button';btn.setAttribute('aria-expanded',String(focusedId===plan.id));
      btn.addEventListener('click',()=>{focusedId=focusedId===plan.id?null:plan.id;drawResults();});c.append(btn);
    }
    return c;
  }
  function otherOptions(items,base,featured){
    const others=items.filter(p=>!p.baseline&&p.id!==featured?.id);
    if(!others.length)return;
    const d=node('details','ts-secondary');d.id='ts-other-options';
    // Preserve the expanded state across redraws.
    d.open=!!window.__tsOtherOpen;
    d.addEventListener('toggle',()=>{window.__tsOtherOpen=d.open;});
    const summaryEl=node('summary','',`See ${others.length} other rotation option${others.length===1?'':'s'}  +`);d.append(summaryEl);
    const grid=node('div','ts-other-grid');
    others.forEach(p=>{
      const c=node('article','ts-other-card');c.append(node('h4','',p.title));
      const chips=node('div','ts-chips');cropChips(chips,p);c.append(chips);
      c.append(node('div','ts-figure',changePhrase(p.scores.demand,base.scores.demand)));
      const btn=node('button','ts-btn',focusedId===p.id?'Hide details':'See trade-offs');btn.type='button';
      btn.addEventListener('click',()=>{focusedId=focusedId===p.id?null:p.id;window.__tsOtherOpen=true;drawResults();});
      c.append(btn);grid.append(c);
    });
    d.append(grid);$('comparison-cards').after(d);
  }
  function detailPanel(items,base){
    const focus=items.find(p=>p.id===focusedId&&!p.baseline);if(!focus)return;
    const panel=node('section','ts-detail');panel.id='ts-detail-panel';
    panel.append(node('h3','',`What changes with ${focus.title}?`));
    panel.append(node('p','','These figures compare the same historical four-year weather sequences. They are not an estimate of profit or harvest success.'));
    const table=node('div','ts-table');
    [['Measure','Your plan','This option'],['Crop water demand','demand'],['Same-day rain gap*','shortfall'],['Hot days ≥32°C','heat'],['Rain during crop periods','rain']].forEach((r,i)=>{
      if(i===0){r.forEach(t=>table.append(node('div','ts-th',t)));return;}
      const [label,key]=r,unit=metricDefs[key].unit;
      table.append(node('div','',label),node('div','',`${fmt(base.scores[key])} ${unit}`),node('div','',`${fmt(focus.scores[key])} ${unit}`));
    });
    panel.append(table);
    panel.append(node('p','ts-muted','*The rain gap ignores stored soil moisture. It must not be interpreted as irrigation water needed.'));
    const metricSelect=node('select','ts-metric-switch');metricSelect.setAttribute('aria-label','Choose chart measure');
    Object.entries(metricDefs).forEach(([key,info])=>{const o=node('option','',info.label);o.value=key;metricSelect.append(o);});
    metricSelect.value=selectedMetric;
    const bars=node('div','ts-bars');
    function updateBars(){
      bars.replaceChildren();const k=metricSelect.value;selectedMetric=k;
      const max=Math.max(1,...items.map(p=>p.scores[k]));
      [base,focus].forEach(p=>{
        const row=node('div','ts-bar-row');row.append(node('div','',p.baseline?'Your plan':'Alternative'));
        const track=node('div','ts-track'),fill=node('div','ts-fill');fill.style.width=`${Math.max(0,p.scores[k]/max*100)}%`;
        track.append(fill);row.append(track,node('strong','',fmt(p.scores[k])));bars.append(row);
      });
      note.textContent=metricDefs[k].notes;
    }
    const note=node('p','ts-muted');metricSelect.addEventListener('change',updateBars);
    panel.append(metricSelect,bars,note);updateBars();
    ($('ts-other-options')||$('comparison-cards')).after(panel);
  }
  function drawResults(){
    if(!lastRender)return;
    const {items,base}=lastRender;
    clearGenerated();
    const featured=selectCandidate(items);
    summary(featured,base,Math.max(0,items.length-1));
    $('metrics-bar').replaceChildren();
    const head=node('div','ts-section-head');head.id='ts-section-title';
    head.append(node('h3','','Compare your choices'),node('p','','Start with your usual plan, then explore an alternative. Open more options only if you need them.'));
    $('comparison-cards').before(head);
    const host=$('comparison-cards');host.className='comparison-cards ts-layout';host.replaceChildren();
    host.append(card(base,base));
    if(featured)host.append(card(featured,base,true));
    else host.append(node('div','ts-no-alts','No alternatives match your selected crop preferences. Adjust Must-grow or Crops to avoid to see other choices.'));
    otherOptions(items,base,featured);
    detailPanel(items,base);
  }
  function render(input,data){
    const plans=alternativePlans(input), windows=dryWindows(data);
    if(windows.length<6)throw new Error('Not enough complete historical years for a comparison.');
    const dry=windows.slice().sort((a,b)=>a.rain-b.rain).slice(0,Math.max(2,Math.ceil(windows.length*.3)));
    const years=(activeScenario==='dry'?dry:windows).map(w=>w.y);
    const items=plans.map(p=>({...p,scores:assess(input,p,data,years)})).filter(p=>p.scores);
    const base=items.find(p=>p.baseline);
    if(!base)throw new Error('Your rotation could not be evaluated from the available daily data.');
    lastRender={items,base};focusedId=null;window.__tsOtherOpen=false;
    $('results-state').textContent=activeScenario==='dry'?'Drier historical periods':'Historical weather';
    $('results-subtitle').textContent=`${input.location.name} · ${years.length} historical four-year weather sequences`;
    $('source-years').textContent=`NASA POWER · ${SOURCE_START}–${SOURCE_END}`;
    drawResults();
    const caveats=[];
    if(input.planning.needsCalendarResolution)caveats.push('Typical planting dates are provisional examples, not locally validated dates.');
    if(input.constraints.budgetCadHaYear!==null)caveats.push('Budget limit has NOT been assessed.');
    if(input.constraints.nitrogenLimitKgHaYear!==null)caveats.push('Nitrogen limit has NOT been assessed.');
    if(input.equipment.specified)caveats.push('Equipment has NOT been assessed.');
    caveats.push('Crop yields, profitability, irrigation amounts and fertilizer savings are NOT predicted.');
    status(caveats.join(' '));
    const methods=$('methods-text');methods.replaceChildren();
    [
      'Source: NASA POWER daily gridded precipitation and minimum/maximum temperature, 2012–2025. NASA-derived regional data, not a farm measurement.',
      'Crop water demand is an illustrative Hargreaves reference ET estimate multiplied by fixed crop coefficients. It is not a stage-specific FAO-56 irrigation model.',
      'Same-day rain gap sums max(0, estimated demand minus same-day rainfall). Soil water carryover, infiltration and runoff are not modeled, so it cannot be used as irrigation need.',
      'Historical comparison uses four-year rolling weather sequences. Drier mode selects the lowest-rainfall sequences by first-year April–September precipitation; neither mode is a future forecast.',
      'Alternative rotations are preset examples, not optimization. Crop windows are provisional. Economic and nitrogen outcomes are not calculated.',
      '2050s mode is unavailable until NEX-GDDP-CMIP6 projection data has been processed and connected.'
    ].forEach(t=>methods.append(node('p','',t)));
  }
  function setScenario(type){
    activeScenario=type;
    $('weather-typical').classList.toggle('scenario-selected',type==='typical');
    $('weather-dry').classList.toggle('scenario-selected',type==='dry');
    if(selected&&weather){try{render(selected,weather.data);}catch(e){status(e.message,true);}}
  }
  $('weather-typical').addEventListener('click',()=>setScenario('typical'));
  $('weather-dry').addEventListener('click',()=>setScenario('dry'));
  window.addEventListener('terrashift:compare',async e=>{
    if(busy)return;
    selected=e.detail;focusedId=null;
    $('results').hidden=false;show();setBusy(true);
    try{const data=await loadWeather(selected.location.lat,selected.location.lon);render(selected,data);}
    catch(error){
      lastRender=null;clearGenerated();$('metrics-bar').replaceChildren();$('comparison-cards').replaceChildren();
      $('results-state').textContent='Weather unavailable';
      status(`Unable to complete comparison: ${error.message}. No example numbers have been substituted.`,true);
    } finally{setBusy(false);}
  });
})();
