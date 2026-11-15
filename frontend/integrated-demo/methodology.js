/* Explain a small snapshot of the real API response; no simulations or new scoring. */
(() => {
  'use strict';
  const F=window.Agronaut,host=document.getElementById('analysis-snapshot');
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  let context=null;
  try{const hash=new URLSearchParams(location.hash.slice(1)).get('report');context=hash?JSON.parse(hash):JSON.parse(sessionStorage.getItem('agronaut-methodology')||'null');}catch{}
  if(!context||context.version!==3||!context.available){host.append(el('p','small-note','Open “How did we model this?” from a completed analysis to see its actual weights and comparison values here. No example results are substituted.'));return;}
  host.append(el('h3','',`Your analysis snapshot · ${context.anchor||'regional input'} · ${context.period}`));
  host.append(el('p','small-note',`Soil preset: ${(context.soil||'unavailable').replaceAll('_',' ')} · modeled available-water capacity ${F.format(context.capacity_mm)} mm at the fixed 1 m depth. These are model assumptions, not field measurements.`));
  const layout=el('div','snapshot-grid'),weights=el('article');weights.append(el('h4','','Your priority weights'));
  const names={water:'Water demand & shortfall',nitrogen:'Nitrogen demand indicator',soil_cover:'Time with a living crop',weather_risk:'Water & heat exposure'};
  for(const [key,value] of Object.entries(context.priorities||{})){
    if(!F.finite(value)||value<0||value>1)continue;
    const row=el('div','weight-row');row.append(el('span','',names[key]||key),el('strong','',`${F.format(value*100)}%`));const track=el('div','weight-track'),bar=el('div','weight-fill');bar.style.width=`${value*100}%`;track.append(bar);row.append(track);weights.append(row);
  }
  weights.append(el('p','small-note','These percentages are decision weights, not fertilizer savings or probabilities.'));layout.append(weights);
  const comparison=el('article');comparison.append(el('h4','','Actual modeled comparison'));
  if(!context.recommended){comparison.append(el('p','small-note','No supported alternative was recommended for these constraints.'));}
  else {
    comparison.append(el('p','small-note',`Original: ${context.current.name}`),el('p','small-note',`Suggested: ${context.recommended.name}`));
    for(const [key,title] of [['potential_demand_mm','Potential water demand'],['typical_year_shortfall_mm','Typical unmet demand']]){
      const values=[context.current.metrics?.[key],context.recommended.metrics?.[key]],max=Math.max(1,...values.filter(F.finite));
      comparison.append(el('h4','',`${title} · mm/year`));
      values.forEach((value,index)=>{const row=el('div','snapshot-bar-row');row.append(el('span','',index?'Suggested':'Original'),el('strong','',F.format(value)));const track=el('div','snapshot-track'),bar=el('div',index?'suggested-fill':'original-fill');if(F.finite(value))bar.style.width=`${Math.max(0,value)/max*100}%`;track.append(bar);row.append(track);comparison.append(row);});
    }
    comparison.append(el('p','small-note','Same future scoring period and metric definitions as the leaderboard. Unfavorable differences remain visible.'));
  }
  layout.append(comparison);host.append(layout);
  if(context.constraints){const c=context.constraints;host.append(el('p','small-note',`Mandatory crops: ${c.must?.join(', ')||'none'} · Avoided: ${c.avoid?.join(', ')||'none'} · Equipment: ${c.equipment?.join(', ')||'none selected'}`));}
})();
