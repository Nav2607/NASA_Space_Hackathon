/* TerraShift integrated form — compact sidebar, explicit assumptions. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const CROPS = [
    ['corn','Corn'],['soybean','Soybean'],['winter_wheat','Winter wheat'],
    ['red_clover','Red clover (cover)'],['cereal_rye','Cereal rye (cover)']
  ];
  const cropName = val => CROPS.find(([k]) => k === val)?.[1] || val;
  const currentYear = new Date().getFullYear();
  let location = null;
  let nextId = 1;
  let rotation = [];
  let history = [];
  let nextHistoryId = 1;
  const form = $('farmerForm');

  function radio(name){return document.querySelector(`input[name="${name}"]:checked`)?.value || 'unknown';}
  function checks(name){return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value);}
  function nonnegNumber(id){
    const raw=$(id).value.trim(); if(raw==='')return null;
    const val=Number(raw);return Number.isFinite(val)&&val>=0?val:null;
  }
  function field(text,input){
    const wrap=document.createElement('div');wrap.className='form-field';
    const label=document.createElement('label');label.textContent=text;label.htmlFor=input.id;
    wrap.append(label,input);return wrap;
  }
  function selectCrop(id,value,callback){
    const select=document.createElement('select');select.id=id;
    CROPS.forEach(([k,l])=>select.add(new Option(l,k)));
    select.value=value;select.addEventListener('change',()=>callback(select.value));return select;
  }
  function cropChoices(container,name){
    CROPS.forEach(([value,label])=>{
      const holder=document.createElement('label');const input=document.createElement('input');
      input.type='checkbox';input.name=name;input.value=value;
      holder.append(input,document.createTextNode(' '+label));$(container).append(holder);
    });
  }
  cropChoices('mustGrowOptions','mustGrow');cropChoices('avoidOptions','avoid');
  function rotationAdd(){
    if(rotation.length>=12)return;
    rotation.push({id:nextId++,crop:rotation.length===0?'corn':rotation.length===1?'soybean':'winter_wheat',yearIndex:Math.min(rotation.length,3),start:'',end:''});
    renderRotation();
  }
  function renderRotation(){
    const host=$('rotationRows');host.replaceChildren();
    rotation.forEach((r,i)=>{
      const card=document.createElement('div');card.className='compact-crop-card';
      const head=document.createElement('div');head.className='compact-crop-header';
      const label=document.createElement('strong');label.textContent=`Crop ${i+1}`;
      const del=document.createElement('button');del.type='button';del.textContent='Remove';del.className='link-danger';del.disabled=rotation.length===1;
      del.addEventListener('click',()=>{rotation=rotation.filter(x=>x.id!==r.id);renderRotation();});head.append(label,del);
      const top=document.createElement('div');top.className='compact-row';
      top.append(field('Crop',selectCrop(`rot-crop-${r.id}`,r.crop,v=>{r.crop=v;})));
      const year=document.createElement('select');year.id=`rot-year-${r.id}`;
      for(let j=0;j<4;j++)year.add(new Option(`Year ${j+1}`,String(j)));
      year.value=String(r.yearIndex);year.addEventListener('change',()=>r.yearIndex=Number(year.value));
      top.append(field('Growing year',year));
      const dates=document.createElement('div');dates.className='compact-row';
      for(const [key,text] of [['start','Planting date *'],['end','Harvest / end date *']]){
        const input=document.createElement('input');input.type='date';input.id=`rot-${key}-${r.id}`;
        input.required=true;
        input.value=r[key];
        input.addEventListener('input',()=>r[key]=input.value);
        dates.append(field(text,input));
      }
      const note=document.createElement('div');note.className='farm-helper note-dates';
      note.textContent='Enter the dates you expect to plant and harvest. Approximate dates are okay, but both fields are required. Winter wheat may cross into the next year.';
      card.append(head,top,dates,note);host.append(card);
    });
    $('addCrop').disabled=rotation.length>=12;
    $('rotationInfo').textContent=`${rotation.length} crop entries · up to 4 growing years · same-year crops and cover crops can overlap`;
  }
  $('addCrop').addEventListener('click',rotationAdd);rotationAdd();
  function historyAdd(){
    if(history.length>=10)return;
    history.push({id:nextHistoryId++,crop:'corn',year:currentYear-1});renderHistory();
  }
  function renderHistory(){
    $('historyRows').replaceChildren();
    history.forEach(r=>{
      const card=document.createElement('div');card.className='compact-history';
      const year=document.createElement('input');year.type='number';year.min='1900';year.max=String(currentYear);year.id=`hist-${r.id}`;year.value=r.year;
      year.addEventListener('input',()=>r.year=year.value);
      const crop=selectCrop(`hist-crop-${r.id}`,r.crop,v=>r.crop=v);
      const del=document.createElement('button');del.type='button';del.className='link-danger';del.textContent='×';del.setAttribute('aria-label','Remove past crop');
      del.addEventListener('click',()=>{history=history.filter(x=>x.id!==r.id);renderHistory();});
      card.append(field('Year',year),field('Crop',crop),del);$('historyRows').append(card);
    });
    $('addHistory').disabled=history.length>=10;
  }
  $('addHistory').addEventListener('click',historyAdd);
  function displayIrrigation(){
    const enabled=radio('irrigation')==='yes';$('irrigationDetails').hidden=!enabled;
    $('capacityGroup').hidden=!(enabled&&$('waterLimit').value==='known');
  }
  document.querySelectorAll('input[name="irrigation"]').forEach(x=>x.addEventListener('change',displayIrrigation));
  $('waterLimit').addEventListener('change',displayIrrigation);displayIrrigation();
  for(const [toggle,group] of [['enableBudget','budgetGroup']]){
    $(toggle).addEventListener('change',()=>$(group).hidden=!$(toggle).checked);
  }
  const sliderLabels=['water','soil','weather'];
  for(const s of sliderLabels){const inp=$(`${s}Priority`),out=$(`${s}Value`);
    inp.addEventListener('input',()=>out.textContent=`${inp.value} / 5`);}
  window.addEventListener('terrashift:location-changed',e=>{
    location=e.detail;
    $('compareButton').disabled=false;$('compareButton').textContent='Compare rotation options ↗';
  });
  window.addEventListener('terrashift:location-cleared',()=>{
    location=null;$('compareButton').disabled=true;$('compareButton').textContent='Choose a field first →';
  });
  function validDate(s){if(!/^\d{4}-\d\d-\d\d$/.test(s))return null;const d=new Date(`${s}T00:00:00Z`);return Number.isFinite(+d)&&d.toISOString().slice(0,10)===s?d:null;}
  function errorsForForm(){
    const errors=[];const firstYear=Number($('rotationStartYear').value);
    if(!Number.isInteger(firstYear)||firstYear<2000||firstYear>2100)errors.push('Choose a first planning year between 2000 and 2100.');
    if(!location)errors.push('Choose your farm location on the map first.');
    rotation.forEach((r,i)=>{
      const a=validDate(r.start),b=validDate(r.end);
      if(!a||!b){errors.push(`Crop ${i+1}: planting and harvest dates are required.`);return;}
      if(b<=a)errors.push(`Crop ${i+1}: harvest must come after planting.`);
      if(Number.isInteger(firstYear)&&firstYear>=2000&&firstYear<=2100){
        const y=firstYear+r.yearIndex;
        if(a.getUTCFullYear()!==y)errors.push(`Crop ${i+1}: planting year must match Year ${r.yearIndex+1} (${y}).`);
        if(a<new Date(Date.UTC(firstYear,0,1))||b>=new Date(Date.UTC(firstYear+4,0,1)))errors.push(`Crop ${i+1}: crop dates must stay within ${firstYear}–${firstYear+3}.`);
      }
    });
    const overlap=checks('mustGrow').filter(x=>checks('avoid').includes(x));
    if(overlap.length)errors.push(`${overlap.map(cropName).join(', ')} cannot be both required and avoided.`);
    if(radio('irrigation')==='yes'&&$('waterLimit').value==='known'&&nonnegNumber('capacity')===null)errors.push('Enter your known irrigation limit or choose “I don’t know my limit”.');
    if($('enableBudget').checked&&nonnegNumber('budget')===null)errors.push('Enter a valid budget.');
    const years=new Set();
    history.forEach((r,i)=>{const n=Number(r.year);if(!Number.isInteger(n)||n<1900||n>currentYear)errors.push(`Past crop ${i+1}: enter a valid year.`);if(years.has(n))errors.push(`Past crop history year ${n} is repeated.`);years.add(n);});
    return errors;
  }
  function message(errors){
    const box=$('formMessage');box.replaceChildren();box.className=errors.length?'form-message form-error':'form-message form-success';
    if(errors.length){const title=document.createElement('strong');title.textContent='Please review these inputs:';const ul=document.createElement('ul');errors.forEach(x=>{const li=document.createElement('li');li.textContent=x;ul.append(li);});box.append(title,ul);}
    else box.textContent='Inputs checked. Running the simulation…';
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  form.addEventListener('submit',e=>{
    e.preventDefault();const errors=errorsForForm();message(errors);
    if(errors.length){if(errors.some(x=>/required|avoided|budget/i.test(x)))$('advancedOptions').open=true;if(errors.some(x=>x.startsWith('Past'))) $('historyDetails').open=true;return;}
    const firstYear=Number($('rotationStartYear').value);
    const known=radio('irrigation')==='yes'&&$('waterLimit').value==='known';
    const unit=$('capacityUnit').value;const amount=known?nonnegNumber('capacity'):null;
    const currentRotation=rotation.map((r,i)=>({
      sequence:i+1,growingYear:firstYear+r.yearIndex,crop:r.crop,
      dateSource:'farmer_provided',
      plantingDate:r.start,
      harvestDate:r.end
    }));
    const farmData={
      location:{...location},soilTexture:$('soil').value,drainage:$('drainage').value,slope:$('slope').value,
      irrigation:{availability:radio('irrigation'),limitStatus:radio('irrigation')==='yes'?$('waterLimit').value:'not_applicable',capacityKnown:known,capacityMm:amount===null?null:unit==='m3_per_ha_per_season'?amount/10:amount,originalAmount:amount,originalUnit:known?unit:null},
      planning:{firstYear,horizonYears:4,needsCalendarResolution:false},
      currentRotation,cropHistory:history.map(x=>({year:Number(x.year),crop:x.crop,source:'farmer_reported'})),
      mustGrow:checks('mustGrow'),avoid:checks('avoid'),equipment:{specified:false,available:[]},
      constraints:{nitrogenLimitKgHaYear:null,budgetCadHaYear:$('enableBudget').checked?nonnegNumber('budget'):null},
      priorities:{water:Number($('waterPriority').value),nitrogen:3,soilCover:Number($('soilPriority').value),weatherRisk:Number($('weatherPriority').value)}
    };
    window.terraShiftFarmData=farmData;
    console.log('TerraShift farmer input',farmData);
    window.dispatchEvent(new CustomEvent('terrashift:compare',{detail:farmData}));
  });
})();
