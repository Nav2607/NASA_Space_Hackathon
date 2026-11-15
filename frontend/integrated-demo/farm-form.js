/* Existing farm workflow adapted to the actual backend's supported inputs. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const crops = [['corn','Corn'],['soybean','Soybean'],['winter_wheat','Winter wheat']];
  let selectedLocation = null;
  let rotation = ['corn', 'soybean'];
  const form = $('farmerForm');
  const checked = name => [...form.querySelectorAll(`input[name="${name}"]:checked`)].map(x => x.value);
  const changed = () => window.dispatchEvent(new Event('agronaut:inputs-changed'));
  function renderRotation() {
    $('rotationRows').replaceChildren();
    rotation.forEach((crop, index) => {
      const row = document.createElement('div'); row.className = 'rotation-input';
      const label = document.createElement('label'); label.htmlFor = `rotation-${index}`; label.textContent = `Year ${index + 1}`;
      const select = document.createElement('select'); select.id = label.htmlFor;
      crops.forEach(([id, name]) => select.add(new Option(name, id)));
      const covers=document.createElement('optgroup');covers.label='Cover crops · not modeled yet';
      for(const [id,name] of [['red_clover','Red clover'],['cereal_rye','Cereal rye']]){const option=new Option(name+' — unavailable',id);option.disabled=true;covers.append(option);}
      select.append(covers);select.value = crop;
      select.addEventListener('change', () => { rotation[index] = select.value; });
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'link-danger';
      remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove rotation year ${index + 1}`); remove.disabled = rotation.length === 1;
      remove.addEventListener('click', () => { rotation.splice(index, 1); renderRotation(); changed(); });
      row.append(label, select, remove); $('rotationRows').append(row);
    });
    $('addCrop').disabled = rotation.length >= 4;
    $('rotationInfo').textContent = `${rotation.length}-year repeating cash-crop sequence · all starting phases tested`;
  }
  for (const [host, name] of [['mustGrowOptions','mustGrow'],['avoidOptions','avoid']]) {
    for (const [id, text] of crops) {
      const label = document.createElement('label'), input = document.createElement('input');
      input.type = 'checkbox'; input.name = name; input.value = id;
      label.append(input, document.createTextNode(` ${text}`)); $(host).append(label);
    }
  }
  $('addCrop').addEventListener('click', () => { if (rotation.length < 4) { rotation.push('winter_wheat'); renderRotation(); changed(); } });
  for (const key of ['water','nitrogen','soil','weather']) {
    $(`${key}Priority`).addEventListener('input', () => { $(`${key}Value`).textContent = `${$(`${key}Priority`).value} / 5`; });
  }
  form.addEventListener('input', changed); form.addEventListener('change', changed);
  window.addEventListener('agronaut:location-changed', e => {
    selectedLocation = e.detail; $('compareButton').disabled = false; $('compareButton').textContent = 'Compare my rotation →';
  });
  window.addEventListener('agronaut:location-cleared', () => {
    selectedLocation = null; $('compareButton').disabled = true; $('compareButton').textContent = 'Choose a location first';
  });
  form.addEventListener('submit', e => {
    e.preventDefault();
    const mustGrow = checked('mustGrow'), avoid = checked('avoid');
    const errors = [];
    if (!selectedLocation) errors.push('Choose a supported location first.');
    if (mustGrow.some(c => avoid.includes(c))) errors.push('A crop cannot be both required and avoided.');
    const box = $('formMessage'); box.replaceChildren();
    if (errors.length) {
      box.className = 'form-message form-error'; box.textContent = errors.join(' '); $('advancedOptions').open = true; box.focus(); return;
    }
    box.className = 'form-message form-success'; box.textContent = 'Comparing your unchanged crop sequence with feasible alternatives.';
    const farmData = {
      location: {...selectedLocation}, soilTexture: $('soil').value,
      currentRotation: rotation.map((crop, i) => ({crop, sequence: i + 1})), mustGrow, avoid,
      equipment: {specified: true, available: checked('equipment')},
      priorities: {water: Number($('waterPriority').value), nitrogen: Number($('nitrogenPriority').value),
        soilCover: Number($('soilPriority').value), weatherRisk: Number($('weatherPriority').value)}
    };
    window.agronautFarmData = farmData;
    window.dispatchEvent(new CustomEvent('agronaut:compare', {detail: farmData}));
  });
  renderRotation();
})();
