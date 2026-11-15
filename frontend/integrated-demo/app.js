/* TerraShift lightweight map — OpenFreeMap + MapLibre GL JS. No AAFC requests. */
(() => {
  'use strict';
  const cfg = window.TERRASHIFT_CONFIG || {};
  const $ = id => document.getElementById(id);
  const statusNode = $('map-status');
  const showStatus = (msg, err=false) => {
    if (!statusNode) return;
    statusNode.textContent = msg;
    statusNode.hidden = !msg;
    statusNode.style.color = err ? '#a24222' : '#244D3E';
  };
  // Anchor metadata supports map snapping; no alternate cached-location input.
  window.TerraShiftAnchorsPromise = fetch(`${(cfg.apiBase || 'http://127.0.0.1:8000').replace(/\/$/, '')}/anchors`)
    .then(r => { if (!r.ok) throw new Error('Location metadata unavailable'); return r.json(); })
    .then(data => Object.entries(data).map(([id,p])=>({id,name:id.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase()),lat:p.lat,lng:p.lon})))
    .catch(()=>[]);
  $('continue-button').addEventListener('click', () => { if(window.TerraShiftSelectedLocation) $('rotationRows').scrollIntoView({behavior:'smooth',block:'center'}); });
  $('print-button').addEventListener('click',()=>window.print());
  if (!window.maplibregl) {
    $('search-message').textContent='Online map unavailable. Check your connection and refresh to select your farm.';
    return;
  }
  const STYLES = {
    street: 'https://tiles.openfreemap.org/styles/liberty',
    light: 'https://tiles.openfreemap.org/styles/positron'
  };
  let map;
  try { map = new maplibregl.Map({
    container: 'map', style: STYLES.street, center: [-80.4,43.55], zoom: 7.6,
    minZoom: 5, maxZoom: 17, attributionControl: true,
    maxBounds: [[-93,41],[-73,57.5]]
  }); } catch (error) { showStatus('Interactive map unavailable. Check browser WebGL support and refresh.', true); return; }
  map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-left');
  map.addControl(new maplibregl.ScaleControl({unit:'metric'}), 'bottom-left');
  let selection = null;
  let marker = null;
  let anchors = [];
  let anchorMarkers = [];
  let clickRequest = 0;
  let searchController = null;
  const isInEnvelope=(lat,lon)=>lat>=41.55 && lat<=57 && lon>=-92 && lon<=-74;
  const fmtCoords=(lat,lon)=>`${Math.abs(lat).toFixed(4)}° ${lat<0?'S':'N'}, ${Math.abs(lon).toFixed(4)}° ${lon<0?'W':'E'}`;
  function distanceKm(a,b,c,d){
    const t=Math.PI/180, dLat=(c-a)*t, dLon=(d-b)*t;
    const x=Math.sin(dLat/2)**2+Math.cos(a*t)*Math.cos(c*t)*Math.sin(dLon/2)**2;
    return 12742*Math.asin(Math.min(1,Math.sqrt(x)));
  }
  function findAnchor(lat,lon){
    if(!anchors.length)return null;
    return anchors.map(anchor=>({anchor,distanceKm:distanceKm(lat,lon,anchor.lat,anchor.lng)})).sort((a,b)=>a.distanceKm-b.distanceKm)[0];
  }
  function selectLocation(lat,lon,name='Selected Ontario location',emit=true){
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||!isInEnvelope(lat,lon)){
      $('search-message').textContent='Please select a location within Ontario.';return;
    }
    const nearest=findAnchor(lat,lon);
    selection={lat,lon,name,anchorId:nearest?.anchor.id??null,anchorName:nearest?.anchor.name??null,distanceKm:nearest?.distanceKm??null};
    if(marker) marker.remove();
    const pin=document.createElement('div');
    pin.className='terrashift-selected-marker';
    pin.setAttribute('aria-label','Selected farm location');
    marker=new maplibregl.Marker({element:pin,anchor:'center'}).setLngLat([lon,lat]).addTo(map);
    $('location-name').replaceChildren();
    const dot=document.createElement('span');dot.className='location-indicator';dot.textContent='●';
    const label=document.createElement('span');label.id='location-name-text';label.textContent=name;
    $('location-name').append(dot,label);
    $('coordinates').textContent=fmtCoords(lat,lon);
    $('nearest-anchor').textContent=nearest?nearest.anchor.name:'NASA POWER regional grid';
    $('anchor-distance').textContent=nearest?`${nearest.distanceKm.toFixed(1)} km`:'Gridded data';
    $('continue-button').disabled=false;
    $('integration-note').hidden=true;
    $('anchor-note').lastElementChild.textContent=nearest
      ? `Regional data represented by ${nearest.anchor.name} approximately ${nearest.distanceKm.toFixed(1)} km away; not an on-farm measurement.`
      : 'The backend snaps this point to the nearest supported regional anchor; it is not a field measurement.';
    window.TerraShiftSelectedLocation={...selection};
    if(emit) window.dispatchEvent(new CustomEvent('terrashift:location-changed',{detail:{...selection}}));
  }
  map.on('load',()=>showStatus(''));
  map.on('error',event=>{
    console.warn('OpenFreeMap:',event.error||event);
    showStatus('The map tiles could not load. Check internet access or try refreshing.',true);
  });
  document.querySelectorAll('[data-map-style]').forEach(button=>{
    button.setAttribute('aria-pressed',String(button.dataset.mapStyle==='street'));
    button.addEventListener('click',()=>{
      const choice=button.dataset.mapStyle;
      if(!STYLES[choice])return;
      map.setStyle(STYLES[choice]);
      document.querySelectorAll('[data-map-style]').forEach(btn=>{
        const active=btn.dataset.mapStyle===choice;
        btn.classList.toggle('selected',active);
        btn.setAttribute('aria-pressed',String(active));
      });
      showStatus('');
    });
  });
  async function selectOntarioPoint(lat,lon,label='Selected farm location'){
    const id=++clickRequest;
    if(!isInEnvelope(lat,lon)){$('search-message').textContent='Choose a location in Ontario.';return;}
    $('search-message').textContent='Checking that this point is in Ontario…';
    try{
      const url=new URL('https://nominatim.openstreetmap.org/reverse');
      url.search=new URLSearchParams({lat:String(lat),lon:String(lon),format:'jsonv2',zoom:'10',addressdetails:'1'}).toString();
      const res=await fetch(url,{headers:{Accept:'application/json'}});
      if(!res.ok)throw new Error('Reverse lookup not available');
      const data=await res.json();
      if(id!==clickRequest)return;
      const province=(data.address?.state||data.address?.province||'').toLowerCase();
      if(province!=='ontario'){
        $('search-message').textContent='This point is outside Ontario. Choose a point in Ontario.';return;
      }
      const town=data.address?.town||data.address?.city||data.address?.village||data.address?.county;
      selectLocation(lat,lon,town?`${town}, Ontario`:label);
      $('search-message').textContent='Farm location selected. Click somewhere else to change it.';
    }catch(e){
      if(id===clickRequest)$('search-message').textContent='Could not verify this point. Check your connection or search for a nearby town.';
    }
  }
  map.on('click',e=>selectOntarioPoint(e.lngLat.lat,e.lngLat.lng));
  $('search-form').addEventListener('submit',async e=>{
    e.preventDefault();const q=$('search-input').value.trim();if(!q)return;
    if(searchController)searchController.abort();searchController=new AbortController();
    $('search-button').disabled=true;$('search-button').textContent='Searching…';
    $('search-message').textContent='Finding your Ontario location…';
    try{
      const params=new URLSearchParams({q:`${q}, Ontario, Canada`,format:'jsonv2',limit:'5',countrycodes:'ca',addressdetails:'1',viewbox:'-92,57,-74,41.55',bounded:'1'});
      const res=await fetch(`https://nominatim.openstreetmap.org/search?${params}`,{signal:searchController.signal,headers:{Accept:'application/json'}});
      if(!res.ok)throw new Error('Search HTTP '+res.status);
      const items=await res.json();
      const found=items.find(x=>{const p=(x.address?.state||x.address?.province||'').toLowerCase();return p==='ontario'||(!p&&x.display_name.toLowerCase().includes('ontario'));});
      if(!found){$('search-message').textContent='No Ontario match. Try a nearby town or postal code.';return;}
      const lat=Number(found.lat),lon=Number(found.lon);
      map.flyTo({center:[lon,lat],zoom:Math.max(map.getZoom(),12),essential:true});
      ++clickRequest;
      selectLocation(lat,lon,found.display_name.split(',').slice(0,3).join(',').trim());
      $('search-message').textContent='Location found. Click the field to adjust the pin.';
    }catch(e){if(e.name!=='AbortError')$('search-message').textContent='Search is unavailable. Check your connection and try again.';}
    finally{$('search-button').disabled=false;$('search-button').textContent='Search';}
  });
  $('my-location').addEventListener('click',()=>{
    if(!navigator.geolocation){$('search-message').textContent='Location is unsupported in this browser.';return;}
    $('search-message').textContent='Requesting location permission…';
    navigator.geolocation.getCurrentPosition(pos=>{
      const lat=pos.coords.latitude,lon=pos.coords.longitude;
      if(!isInEnvelope(lat,lon)){$('search-message').textContent='You are outside Ontario. Please search for your farm.';return;}
      map.flyTo({center:[lon,lat],zoom:12,essential:true});
      selectOntarioPoint(lat,lon,'Approximate current location');
    },()=>{$('search-message').textContent='Location access unavailable. Search or click the map instead.';},{enableHighAccuracy:false,timeout:12000});
  });
  async function loadAnchors(){
    const data = await window.TerraShiftAnchorsPromise;
    anchors=data.filter(a=>a&&typeof a.id==='string'&&typeof a.name==='string'&&Number.isFinite(Number(a.lat))&&Number.isFinite(Number(a.lng)))
      .map(a=>({id:a.id,name:a.name,lat:Number(a.lat),lng:Number(a.lng)}));
    anchorMarkers.forEach(m=>m.remove());anchorMarkers=[];
    for(const a of anchors){
      const dot=document.createElement('div');dot.className='terrashift-anchor-marker';
      const mk=new maplibregl.Marker({element:dot,anchor:'center'}).setLngLat([a.lng,a.lat]).setPopup(new maplibregl.Popup().setText('Climate data area: '+a.name)).addTo(map);
      anchorMarkers.push(mk);
    }
  }
  $('continue-button').addEventListener('click',()=>{
    if(!selection)return;
    const data={...selection};window.TerraShiftSelectedLocation=data;
    window.dispatchEvent(new CustomEvent('terrashift:location-selected',{detail:data}));
    try{sessionStorage.setItem('terrashift-location',JSON.stringify(data));}catch(e){}
    $('rotationRows')?.scrollIntoView({behavior:'smooth',block:'center'});
  });
  $('reset-button').addEventListener('click',()=>{
    ++clickRequest;selection=null;if(marker){marker.remove();marker=null;}
    $('location-name').textContent='No location selected yet';
    $('coordinates').textContent='—';$('nearest-anchor').textContent='Awaiting climate data';$('anchor-distance').textContent='—';
    $('continue-button').disabled=true;$('integration-note').hidden=true;
    $('anchor-note').lastElementChild.textContent='Your location helps connect farm inputs to regional climate information. Regional estimates may differ from field conditions.';
    try{sessionStorage.removeItem('terrashift-location');}catch(e){}
    window.TerraShiftSelectedLocation=null;
    window.dispatchEvent(new CustomEvent('terrashift:location-cleared'));
  });

  loadAnchors();
  if(typeof ResizeObserver!=='undefined'){
    const resizeObserver=new ResizeObserver(()=>map.resize());resizeObserver.observe($('map'));
  }
  window.addEventListener('load',()=>map.resize());
})();
