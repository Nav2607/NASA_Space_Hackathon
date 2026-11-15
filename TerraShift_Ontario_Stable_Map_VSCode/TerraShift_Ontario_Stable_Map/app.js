/* TerraShift — Map + farm location selection. No framework/build step required. */
(() => {
  'use strict';
  const cfg = window.TERRASHIFT_CONFIG || {};
  const $ = (id) => document.getElementById(id);
  const ONTARIO_BOUNDS = [[41.55, -92.0], [57.0, -74.0]]; // broad VIEW bounds, not a provincial boundary polygon
  const AAFC_BASE = 'https://agriculture.canada.ca/imagery-images/rest/services/annual_crop_inventory';
  const tileAttr = 'Tiles © Esri — Esri, Maxar, Earthstar Geographics, and the GIS User Community';
  const state = {selection: null, anchors: [], streetLayer: null, satelliteLayer: null, aafc: null, aafcLoadId: 0, cropResult: null, overlayActive: false, locationCheckId: 0};

  if (!window.L) { $('search-message').textContent = 'Map could not load. Check internet connection and refresh the page.'; return; }
  // One exported image per settled map view: avoids dozens of broken/missing tiles.
  // Crop layer remains independent. Previous imagery stays visible until the next view loads.
  const map = L.map('map', {
    zoomControl: true, scrollWheelZoom: false, preferCanvas: true,
    zoomSnap: 1, zoomAnimation: false, fadeAnimation: false,
    maxBoundsViscosity: 0.95, minZoom: 6, maxZoom: 17
  }).setView([44.1, -79.65], 8);
  map.setMaxBounds(ONTARIO_BOUNDS); // viewing envelope only; Ontario clicks verified separately
  const basemapPane = map.createPane('terrasBase');
  basemapPane.style.zIndex = 190;
  basemapPane.style.pointerEvents = 'none';
  const attributionText = 'Map imagery © Esri and its data providers';
  const BASE_SERVICES = {
    street: 'World_Topo_Map',
    satellite: 'World_Imagery'
  };
  let baseStyle = 'street', activeBase = null, requestCounter = 0, baseTimer = null;
  let emergencyTiles = null, loadingTimer = null;
  const tileBanner = $('tile-loading');
  function showTileLoading(show, message='Loading Ontario map…') {
    if (!tileBanner) return;
    tileBanner.hidden = !show;
    tileBanner.textContent = message;
  }
  function basemapRequest(style) {
    // Expand view to create a buffer while panning. No repeated requests while dragging.
    const bounds=map.getBounds().pad(0.20);
    const sw=map.options.crs.project(bounds.getSouthWest());
    const ne=map.options.crs.project(bounds.getNorthEast());
    const viewport=map.getSize();
    const w=Math.max(320,Math.min(1400,Math.round(viewport.x*1.25)));
    const h=Math.max(280,Math.min(1100,Math.round(viewport.y*1.25)));
    const query=new URLSearchParams({
      bbox:`${sw.x},${sw.y},${ne.x},${ne.y}`,
      bboxSR:'3857',imageSR:'3857',size:`${w},${h}`,
      format:style==='satellite'?'jpg':'png32',transparent:'false',f:'image',dpi:'96'
    });
    return {bounds, url:`https://server.arcgisonline.com/ArcGIS/rest/services/${BASE_SERVICES[style]}/MapServer/export?${query}`};
  }
  function showTileFallback() {
    // Only turn on a normal tile layer if the whole-image export endpoint is unreachable.
    // This is a safety net, not the default source.
    if (emergencyTiles) return;
    emergencyTiles=L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
      pane:'terrasBase', subdomains:'abcd', maxZoom:19, updateWhenIdle:true,
      updateWhenZooming:false, keepBuffer:1,
      attribution:'© OpenStreetMap contributors © CARTO'
    }).addTo(map);
    status('Satellite/map imagery is temporarily unavailable. Showing a simplified map instead.',true);
    showTileLoading(false);
  }
  function refreshBase() {
    clearTimeout(loadingTimer);
    const id=++requestCounter;
    const {bounds,url}=basemapRequest(baseStyle);
    showTileLoading(true,baseStyle==='satellite'?'Loading satellite view…':'Loading Ontario map…');
    const candidate=L.imageOverlay(url,bounds,{
      pane:'terrasBase',interactive:false,alt:'Ontario '+baseStyle+' map',
      attribution:attributionText
    });
    let complete=false;
    candidate.on('load',()=>{
      if(id!==requestCounter){map.removeLayer(candidate);return;}
      complete=true;clearTimeout(loadingTimer);
      if(activeBase)map.removeLayer(activeBase);
      activeBase=candidate;
      if(emergencyTiles){map.removeLayer(emergencyTiles);emergencyTiles=null;}
      showTileLoading(false);status('');
    });
    candidate.on('error',()=>{
      map.removeLayer(candidate);
      if(id!==requestCounter)return;
      complete=true;clearTimeout(loadingTimer);
      if(!activeBase)showTileFallback();
      else {showTileLoading(false);status('Map update unavailable; showing the previous image. Try Map view or check the connection.',true);}
    });
    candidate.addTo(map);
    loadingTimer=setTimeout(()=>{
      if(id!==requestCounter||complete)return;
      map.removeLayer(candidate);
      if(!activeBase)showTileFallback();
      else {showTileLoading(false);status('Map image is taking too long. Previous map view is still available.',true);}
    },8500);
  }
  function scheduleBase(delay=260){clearTimeout(baseTimer);baseTimer=setTimeout(refreshBase,delay);}
  function setMapStyle(style){
    if(style===baseStyle)return;
    baseStyle=style;
    document.querySelectorAll('[data-map-style]').forEach(b=>{
      const selected=b.dataset.mapStyle===style;
      b.classList.toggle('selected',selected);
      b.setAttribute('aria-pressed',String(selected));
    });
    scheduleBase(30);
  }
  map.on('moveend zoomend resize',()=>scheduleBase(320));
  document.querySelectorAll('[data-map-style]').forEach(button=>{
    button.setAttribute('aria-pressed',String(button.dataset.mapStyle===baseStyle));
    button.addEventListener('click',()=>setMapStyle(button.dataset.mapStyle));
  });
  scheduleBase(80);
  L.control.scale({imperial: false, position: 'bottomleft'}).addTo(map);
  const selectedPin = L.circleMarker([0,0], {radius: 10, color: '#fff', weight: 3, fillColor: '#C7A56B', fillOpacity: 1});
  const anchorLayer = L.layerGroup().addTo(map);
  function status(message, isError = false) {
    const el = $('map-status'); el.textContent = message; el.hidden = !message;
    el.style.color = isError ? '#a24222' : '#244D3E';
  }
  function fmtCoords(lat, lon) {return `${Math.abs(lat).toFixed(4)}° ${lat < 0 ? 'S':'N'}, ${Math.abs(lon).toFixed(4)}° ${lon < 0 ? 'W':'E'}`;}
  function haversine(lat1, lon1, lat2, lon2) {
    const radians = Math.PI/180, dLat = (lat2-lat1)*radians, dLon=(lon2-lon1)*radians;
    const a = Math.sin(dLat/2)**2 + Math.cos(lat1*radians)*Math.cos(lat2*radians)*Math.sin(dLon/2)**2;
    return 2*6371*Math.asin(Math.min(1,Math.sqrt(a)));
  }
  function nearestAnchor(lat, lon) {
    if (!state.anchors.length) return null;
    return state.anchors.map(anchor => ({anchor, distanceKm:haversine(lat,lon,anchor.lat,anchor.lng)})).sort((a,b)=>a.distanceKm-b.distanceKm)[0];
  }
  function validAnchor(a) {return a && typeof a.id === 'string' && typeof a.name === 'string' && Number.isFinite(Number(a.lat)) && Number.isFinite(Number(a.lng)) && Number(a.lat) >= 40 && Number(a.lat) <= 59 && Number(a.lng) >= -94 && Number(a.lng) <= -73;}
  async function loadAnchors() {
    let anchors = Array.isArray(cfg.anchors) ? cfg.anchors : [];
    if (cfg.apiBase) {
      try {
        const response = await fetch(`${cfg.apiBase.replace(/\/$/,'')}/api/anchors`, {headers:{Accept:'application/json'}});
        if(!response.ok) throw new Error(`HTTP ${response.status}`);
        const json=await response.json();
        anchors = Array.isArray(json) ? json : Array.isArray(json.anchors) ? json.anchors : [];
      } catch(e) { console.warn('Climate anchors unavailable:',e); }
    }
    state.anchors = anchors.filter(validAnchor).map(a => ({id:a.id,name:a.name,lat:Number(a.lat),lng:Number(a.lng)}));
    anchorLayer.clearLayers();
    state.anchors.forEach(a=>L.circleMarker([a.lat,a.lng],{radius:6,color:'#fff',weight:2,fillColor:'#244D3E',fillOpacity:.95}).bindPopup(`Climate data area: ${a.name}`).addTo(anchorLayer));
    if (state.selection) selectLocation(state.selection.lat, state.selection.lng, state.selection.name);
  }
  function selectLocation(lat, lon, name='Selected Ontario location') {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    // Broad envelope used for a user-friendly warning. Not a precise Ontario polygon check.
    if (lat < 41.55 || lat > 57 || lon < -92 || lon > -74) {
      $('search-message').textContent = 'Please select a location in Ontario.'; return;
    }
    const nearest = nearestAnchor(lat,lon);
    state.selection = {lat, lon, name, anchorId:nearest?.anchor.id ?? null, anchorName:nearest?.anchor.name ?? null, distanceKm:nearest?.distanceKm ?? null};
    selectedPin.setLatLng([lat,lon]);
    if(!map.hasLayer(selectedPin)) selectedPin.addTo(map);
    $('location-name').innerHTML = '<span class="location-indicator" aria-hidden="true">●</span><span id="location-name-text"></span>';
    $('location-name-text').textContent = name;
    $('coordinates').textContent = fmtCoords(lat,lon);
    $('nearest-anchor').textContent = nearest ? nearest.anchor.name : 'Awaiting backend data';
    $('anchor-distance').textContent = nearest ? `${nearest.distanceKm.toFixed(1)} km` : '—';
    $('continue-button').disabled = false; // location can flow to form even before anchors connect
    $('integration-note').hidden = true;
    $('anchor-note').lastElementChild.textContent = nearest
      ? `Regional data is represented by ${nearest.anchor.name}, approximately ${nearest.distanceKm.toFixed(1)} km away. This is a proxy, not an on-farm measurement.`
      : 'Your location is saved. Climate data matching will be available when your team connects its regional anchors.';
    updateCropDetail();
    window.dispatchEvent(new CustomEvent('terrashift:location-changed', {detail:{...state.selection, cropYear:Number($('crop-year').value)}}));
  }
  // Validate clicked coordinates with a real province lookup, not a rectangular bounding box.
  // Nominatim is queried only on explicit clicks, never as autocomplete.
  async function selectOntarioPoint(lat, lon, label = 'Selected farm location') {
    const requestId = ++state.locationCheckId;
    $('search-message').textContent = 'Checking that this location is in Ontario…';
    try {
      const url = new URL('https://nominatim.openstreetmap.org/reverse');
      url.search = new URLSearchParams({lat:String(lat),lon:String(lon),format:'jsonv2',zoom:'10',addressdetails:'1'}).toString();
      const res = await fetch(url.toString(), {headers:{Accept:'application/json'}});
      if (!res.ok) throw new Error('Province lookup unavailable');
      const result = await res.json();
      if (requestId !== state.locationCheckId) return;
      const province = (result.address?.state || result.address?.province || '').toLowerCase();
      if (province !== 'ontario') {
        $('search-message').textContent = 'That point is outside Ontario. Please choose a location within the province.';
        return;
      }
      const place = [result.address?.town || result.address?.city || result.address?.village || result.address?.county, 'Ontario'].filter(Boolean).join(', ');
      selectLocation(lat, lon, place || label);
      $('search-message').textContent = 'Location selected. Click another point to adjust it.';
    } catch (error) {
      if (requestId === state.locationCheckId) $('search-message').textContent = 'Could not verify the province right now. Try searching for an Ontario address instead.';
    }
  }
  map.on('click',e=>selectOntarioPoint(e.latlng.lat,e.latlng.lng));
  let searchController=null;
  $('search-form').addEventListener('submit',async (e)=>{
    e.preventDefault();
    const q=$('search-input').value.trim(); if(!q) return;
    if(searchController) searchController.abort();
    searchController=new AbortController();
    $('search-button').disabled=true; $('search-button').textContent='Searching…'; $('search-message').textContent='Finding your Ontario location…';
    try {
      // Manual search only (not autocomplete) to respect public Nominatim usage.
      const params = new URLSearchParams({q:`${q}, Ontario, Canada`,format:'jsonv2',limit:'5',countrycodes:'ca',addressdetails:'1',viewbox:'-92,57,-74,41.55',bounded:'1'});
      const response=await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {signal:searchController.signal,headers:{Accept:'application/json'}});
      if(!response.ok) throw new Error(`Search service error: ${response.status}`);
      const items=await response.json();
      const match=items.find(item=>{const region=(item.address?.state||item.address?.province||'').toLowerCase();return region==='ontario' || (region==='' && item.display_name.toLowerCase().includes('ontario'));});
      if(!match) { $('search-message').textContent='No Ontario match found. Try a nearby town, street, or postal code.';return; }
      const lat=Number(match.lat), lon=Number(match.lon);
      map.setView([lat,lon], Math.max(map.getZoom(),13));
      ++state.locationCheckId;
      selectLocation(lat,lon,match.display_name.split(',').slice(0,3).join(',').trim());
      $('search-message').textContent='Location found. Adjust the pin by clicking your field on the map.';
    } catch(error) {
      if(error.name!=='AbortError') $('search-message').textContent='Address search is currently unavailable. You can still click the map.';
    } finally { $('search-button').disabled=false;$('search-button').textContent='Search'; }
  });
  $('my-location').addEventListener('click',()=>{
    if(!navigator.geolocation){$('search-message').textContent='Location is unsupported in this browser. Search or click the map.';return;}
    $('search-message').textContent='Requesting location permission…';
    navigator.geolocation.getCurrentPosition(pos=>{
      const {latitude:lat,longitude:lon}=pos.coords;
      if(lat < 41.55 || lat >57 || lon < -92 || lon > -74){$('search-message').textContent='Your current location is outside the Ontario map area. Search for your farm instead.';return;}
      map.setView([lat,lon],13);selectOntarioPoint(lat,lon,'Current location (approximate)');
    },()=>{$('search-message').textContent='Location access was unavailable. Search or click the map instead.';},{enableHighAccuracy:false,timeout:12000});
  });
  // The optional AAFC map layers are annual crop *classifications*, not full farm boundaries.
  const years=Array.isArray(cfg.cropYears)?cfg.cropYears:[2025];
  years.forEach(y=>{const opt=document.createElement('option');opt.value=String(y);opt.textContent=String(y);$('crop-year').append(opt);});
  function imageUrl(year) {
    const bounds=map.getBounds(), southWest=map.options.crs.project(bounds.getSouthWest()), northEast=map.options.crs.project(bounds.getNorthEast());
    const width=Math.min(1800,Math.max(500,Math.round(map.getSize().x * 1.4)));
    const height=Math.min(1500,Math.max(400,Math.round(map.getSize().y * 1.4)));
    const params=new URLSearchParams({bbox:`${southWest.x},${southWest.y},${northEast.x},${northEast.y}`,bboxSR:'3857',imageSR:'3857',size:`${width},${height}`,format:'png32',transparent:'true',f:'image'});
    return `${AAFC_BASE}/${year}/ImageServer/exportImage?${params}`;
  }
  let cropTimer=null;
  function updateCropOverlay(){
    if(!state.overlayActive) return;
    const bounds=map.getBounds();const year=$('crop-year').value;
    if(!year) return;
    const id=++state.aafcLoadId;
    const replacement=L.imageOverlay(imageUrl(year),bounds,{opacity:.65,interactive:false});
    replacement.on('load',()=>{
      if(id!==state.aafcLoadId){map.removeLayer(replacement);return;}
      if(state.aafc) map.removeLayer(state.aafc);
      state.aafc=replacement;status('AAFC satellite crop classifications · '+year);
    });
    replacement.on('error',()=>{map.removeLayer(replacement);if(id===state.aafcLoadId)status('AAFC crop layer is unavailable right now. Try another year.',true);});
    replacement.addTo(map);
    // Do not block the map if imagery is slow or missing.
  }
  function scheduleCropOverlay(){clearTimeout(cropTimer);cropTimer=setTimeout(updateCropOverlay,320);}
  function updateCropDetail(){
    const year=$('crop-year').value;
    $('crop-class').textContent = state.overlayActive ? (state.cropResult || 'Map on · pixel not checked') : 'Off';
    $('crop-detail').textContent = state.overlayActive
      ? `AAFC ${year} crop classifications are visible on the map. These are satellite classifications, not verified farm boundaries or confirmed crop rotation history.`
      : 'Past crop map is optional. Turn it on to explore satellite classifications by year.';
  }
  $('crop-toggle').addEventListener('change',()=>{
    state.overlayActive=$('crop-toggle').checked;
    $('year-control').hidden=!state.overlayActive;
    if(state.overlayActive){scheduleCropOverlay();}else{state.aafcLoadId++;if(state.aafc){map.removeLayer(state.aafc);state.aafc=null;}status('');}
    updateCropDetail();
  });
  $('crop-year').addEventListener('change',()=>{state.cropResult=null;updateCropDetail();scheduleCropOverlay();});
  map.on('moveend zoomend resize',()=>{if(state.overlayActive)scheduleCropOverlay();});
  $('continue-button').addEventListener('click',()=>{
    if(!state.selection) return;
    const data={...state.selection,cropYear:Number($('crop-year').value)};
    window.TerraShiftSelectedLocation=data;
    window.dispatchEvent(new CustomEvent('terrashift:location-selected',{detail:data}));
    try{sessionStorage.setItem('terrashift-location',JSON.stringify(data));}catch(_){}
    $('integration-note').hidden=false;
    $('integration-note').textContent='Farm location saved. The next step will open your team’s farm details form once it is connected.';
  });
  $('reset-button').addEventListener('click',()=>{
    ++state.locationCheckId;state.selection=null;state.cropResult=null;
    if(map.hasLayer(selectedPin))map.removeLayer(selectedPin);
    $('location-name').textContent='No location selected yet'; $('coordinates').textContent='—';
    $('nearest-anchor').textContent='Awaiting climate data';$('anchor-distance').textContent='—';
    $('continue-button').disabled=true;$('integration-note').hidden=true;
    $('anchor-note').lastElementChild.textContent='Your location helps connect farm inputs to regional climate information. Regional data may differ from field conditions.';
    try{sessionStorage.removeItem('terrashift-location');}catch(_){}
    window.dispatchEvent(new CustomEvent('terrashift:location-cleared'));
    updateCropDetail();
  });
  $('print-button').addEventListener('click',()=>window.print());
  loadAnchors();
  // Recalculate tile grid when responsive columns change or the map becomes visible.
  if (typeof ResizeObserver !== 'undefined') {
    const resizeObserver = new ResizeObserver(() => map.invalidateSize({pan:false}));
    resizeObserver.observe($('map'));
  }
  window.addEventListener('load', () => map.invalidateSize({pan:false}));
  setTimeout(()=>map.invalidateSize({pan:false}),180);
})();
