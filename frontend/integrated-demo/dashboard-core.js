/* Pure API adapters and display helpers; no simulation or vulnerability calculations. */
(function(root) {
  'use strict';
  const crops = {corn:'Corn', soybean:'Soybean', winter_wheat:'Winter wheat'};
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const format = (value, digits = 1) => finite(value) ? value.toLocaleString('en-CA', {maximumFractionDigits: value !== 0 && Math.abs(value) < 0.1 && digits > 0 ? Math.max(3,digits) : digits}) : '—';
  const delta = (value, baseline) => finite(value) && finite(baseline) ? value - baseline : null;
  const change = (value, unit) => !finite(value) ? 'Comparison unavailable' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${format(Math.abs(value))} ${unit} vs current`;
  const sequence = entry => (entry.rotation || []).map(y => crops[y.crop] || y.crop).join(' → ');
  function request(farm) {
    const rotation = farm.currentRotation.map(row => row.crop);
    if (rotation.length < 1 || rotation.length > 4 || rotation.some(c => !Object.hasOwn(crops,c))) throw new Error('Use 1–4 supported cash crops. Unsupported crops cannot be silently removed.');
    if (!['loam','sandy_loam','clay_loam','clay'].includes(farm.soilTexture)) throw new Error('Choose one of the supported soil textures.');
    const weights = {water:farm.priorities.water, nitrogen:farm.priorities.nitrogen, soil_cover:farm.priorities.soilCover, weather_risk:farm.priorities.weatherRisk};
    if (Object.values(weights).some(v => !finite(v) || v < 0)) throw new Error('Priorities must be finite nonnegative values.');
    const total = Object.values(weights).reduce((a,b) => a+b, 0);
    if (!total) throw new Error('Choose at least one comparison priority.');
    return {lat:farm.location.lat, lon:farm.location.lon, soil:farm.soilTexture,
      current_rotation:rotation, must_include:[...farm.mustGrow], avoid:[...farm.avoid],
      equipment:farm.equipment.specified ? [...farm.equipment.available] : null,
      priorities:Object.fromEntries(Object.entries(weights).map(([key,v])=>[key,v/total]))};
  }
  function periodRows(entry, response, key) {
    const machine = entry === response.baseline ? response.time_machine : entry.time_machine;
    if (!machine) return [];
    return [['historical_2005_2014','2005–2014'],['historical_2015_2024','2015–2024'],['future_2031_2050','2031–2050 sensitivity']].map(([id,label]) => {
      const run = machine[id];
      return {label, value:run?.status === 'available' ? run.metrics?.[key] : null,
        range:run?.status === 'available' ? run.model_range?.[key] : null};
    });
  }
  function weekTiming(week) {
    // Calendar labels only, not projected event dates. Thursday of an ISO week
    // in a fixed reference calendar gives an approximate month/part of month.
    const jan4 = new Date(Date.UTC(2001,0,4));
    const monday = new Date(+jan4 - ((jan4.getUTCDay()+6)%7)*86400000);
    const date = new Date(+monday + ((week-1)*7+3)*86400000);
    const month = date.toLocaleString('en-CA',{month:'short',timeZone:'UTC'});
    const part = date.getUTCDate() <= 10 ? 'Early' : date.getUTCDate() <= 20 ? 'Mid' : 'Late';
    return {month, label:`${part} ${month}`, week};
  }
  function weeklyView(blind, model) {
    if(model >= 0) return blind.runs[model]?.weekly_vulnerabilities || [];
    const reference = new Map((blind.recurring_vulnerabilities?.historical || []).map(row=>[`${row.crop}:${row.calendar_week}`,row]));
    return (blind.emerging_vulnerabilities || []).map(row=>({
      crop:row.crop, calendar_week:row.calendar_week,
      eligible_seasons:row.eligible_seasons ?? reference.get(`${row.crop}:${row.calendar_week}`)?.eligible_seasons,
      frequency_pct:Object.fromEntries(['water','heat','combined'].map(key=>[key,row.status === 'available' ? row.exposures?.[key]?.future_median_frequency_pct : null])),
      mean_water_depletion_intensity:null, mean_daily_unmet_demand_mm:null, mean_heat_exceedance_c:null,
      model_median:true
    }));
  }
  function cycleView(daily, rotation, phase=0, cycle=1) {
    if(!daily?.length||!rotation?.length)throw new Error('Rotation timeline data is unavailable.');
    const first=Number(daily[0].date.slice(0,4)),last=Number(daily.at(-1).date.slice(0,4)),length=rotation.length;
    const cycleNumbers=[];
    // Skip the boundary cycle so the first winter crop can include its autumn start.
    for(let n=1;first+n*length+length-1<=last;n++)cycleNumbers.push(n);
    if(!cycleNumbers.length)throw new Error('Not enough complete years for a full rotation illustration.');
    if(!cycleNumbers.includes(cycle))cycle=cycleNumbers[0];
    const startYear=first+cycle*length,endYear=startYear+length-1;
    const ordered=rotation.map((_,i)=>rotation[(phase+i)%length]);
    let start=`${startYear}-01-01`;
    if(ordered[0]==='winter_wheat') {
      const autumn=daily.find(day=>day.date>=`${startYear-1}-08-01`&&day.date<start&&day.crop==='winter_wheat');
      if(!autumn)throw new Error('The first wheat season is incomplete in this illustration.');
      start=autumn.date;
    }
    const end=`${endYear}-12-31`,days=daily.filter(day=>day.date>=start&&day.date<=end);
    if(!days.length||days[0].date!==start||days.at(-1).date!==end)throw new Error('Incomplete rotation illustration.');
    days.forEach((day,index)=>{
      if(!finite(day.storage_mm)||!finite(day.unmet_demand_mm)||day.storage_mm<0||day.unmet_demand_mm<0)throw new Error('Missing or invalid daily water diagnostics.');
      if(typeof day.water_stress!=='boolean'||typeof day.heat_exposure!=='boolean'||!['no_blind_spot','water_stress','heat_exposure','combined_heat_water'].includes(day.stress_type))throw new Error('Missing daily stress diagnostics.');
      if(index&&Date.parse(day.date)-Date.parse(days[index-1].date)!==86400000)throw new Error('Missing daily dates in the rotation illustration.');
    });
    const steps=ordered.map((crop,index)=>({crop,year:index+1,harvestYear:startYear+index,
      start:index===0?0:days.findIndex(day=>day.date===`${startYear+index}-01-01`),
      end:days.findIndex(day=>day.date===`${startYear+index}-12-31`)+1}));
    const bands=[];
    days.forEach((day,index)=>{const previous=bands.at(-1);if(previous&&previous.crop===day.crop)previous.end=index+1;else bands.push({crop:day.crop,start:index,end:index+1});});
    return {days,steps,bands,startYear,endYear,cycle,cycleNumbers,start,end};
  }
  function flagBands(days,kind) {
    const result=[];
    days.forEach((day,index)=>{
      const flag=kind==='water'?day.water_stress:kind==='heat'?day.heat_exposure:day.stress_type==='combined_heat_water';
      if(!flag)return;
      const last=result.at(-1);if(last&&last.end===index)last.end=index+1;else result.push({start:index,end:index+1});
    });
    return result;
  }
  function recommendedIndex(response) {
    const options=response.options || [];
    const balanced=options.findIndex(entry=>entry.labels?.includes('balanced') || entry.label==='balanced');
    if(balanced>=0)return balanced+1;
    let best=-1;
    options.forEach((entry,index)=>{if(finite(entry.score)&&(best<0||entry.score>options[best].score))best=index;});
    return best<0?null:best+1;
  }
  function baselineNotice(reason) {
    if(/planting window|overlapping cash|calendar/i.test(reason||''))return 'Your rotation has been kept as entered. The model’s fixed harvest and planting dates overlap for this sequence, so it cannot calculate a fair comparison. This is a limitation of the prototype calendar, not a blanket rule that your rotation is unsuitable.';
    return reason || 'The current rotation cannot be evaluated with the available model inputs.';
  }
  const api = {crops, finite, format, delta, change, sequence, request, periodRows, weekTiming, weeklyView, recommendedIndex, baselineNotice, cycleView, flagBands};
  root.Agronaut = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
