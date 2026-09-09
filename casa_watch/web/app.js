/* A small UI: preferences -> drawn area -> concise results. No framework or AI calls. */
'use strict';
const $ = id => document.getElementById(id);
let data = JSON.parse($('initial-data').textContent);
const G = window.CasaGeometry;
const online = location.protocol === 'http:' || location.protocol === 'https:';
const storageKey = 'casa-watch-search-v2';
const fields = ['budget','min-sqm','kind','bedrooms','bathrooms','max-ppm','energy','keywords','furnished','garden','exclude-auctions','price-drops'];
let area=null, step=1, visibleLimit=12, map=null, markerLayer=null, shapeLayer=null, draftLayer=null;
let mode=null, points=[], pointer=null;
const typeNames={apartment:'Apartment',penthouse:'Penthouse',house:'House / villa',rustic:'Rustic'};
const euro = n => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(n);
const known = n => Number.isFinite(n) && n>0;
const hasLocation = h => Number.isFinite(h.latitude) && Number.isFinite(h.longitude);
const pointOf = h => hasLocation(h)?[h.latitude,h.longitude]:null;

function element(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function readFilters(){return Object.fromEntries(fields.map(id=>[id,$(id).type==='checkbox'?$(id).checked:$(id).value]));}
function save(){try{localStorage.setItem(storageKey,JSON.stringify({filters:readFilters(),area,step,sort:$('sort').value}));}catch(_){} }
function restore(){try{const saved=JSON.parse(localStorage.getItem(storageKey));if(!saved)return;for(const id of fields){const value=saved.filters?.[id];if($(id).type==='checkbox')$(id).checked=value===true;else if(typeof value==='string')$(id).value=value;}
  if(!$('preferences').checkValidity()){ $('budget').value=10000000;$('min-sqm').value=0;$('max-ppm').value=0; }
  area=G.validArea(saved.area)?saved.area:null;step=[1,2,3].includes(saved.step)?saved.step:1;
  if(['score','price','ppm','newest'].includes(saved.sort))$('sort').value=saved.sort;
}catch(_){} }

function basicMatch(row,f){const h=row.home;
  if(!Number.isFinite(h.price)||h.price>Number(f.budget)||h.price<0)return false;
  if(Number(f['min-sqm'])>0&&(!known(h.sqm)||h.sqm<Number(f['min-sqm'])))return false;
  if(f.kind&&h.property_type!==f.kind)return false;
  if(Number(f.bedrooms)>0&&(!known(h.bedrooms)||h.bedrooms<Number(f.bedrooms)))return false;
  if(Number(f.bathrooms)>0&&(!known(h.bathrooms)||h.bathrooms<Number(f.bathrooms)))return false;
  if(Number(f['max-ppm'])>0&&(!known(h.sqm)||h.price/h.sqm>Number(f['max-ppm'])))return false;
  if(f.energy&&h.energy_class!==f.energy)return false;
  if(f.furnished&&h.furnished!==true)return false;
  if(f.garden&&h.garden!==true)return false;
  if(f['exclude-auctions']&&row.flags.some(flag=>flag.startsWith('Auction')))return false;
  if(f['price-drops']&&!(h.previous_price>h.price))return false;
  const words=f.keywords.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return words.every(word=>(h.title+' '+h.description).toLowerCase().includes(word));
}
function selection(){const f=readFilters(),base=data.results.filter(row=>basicMatch(row,f));
  const rows=base.filter(row=>G.inside(pointOf(row.home),area));
  rows.sort((a,b)=>{if($('sort').value==='price')return a.home.price-b.home.price;
    if($('sort').value==='ppm')return (known(a.home.sqm)?a.home.price/a.home.sqm:Infinity)-(known(b.home.sqm)?b.home.price/b.home.sqm:Infinity);
    if($('sort').value==='newest')return b.home.first_seen.localeCompare(a.home.first_seen);
    return b.score-a.score||a.home.price-b.home.price;});
  return {base,rows,missing:base.filter(row=>!hasLocation(row.home)).length};
}
function areaName(){return !area?'All Milan':area.type==='circle'?(area.radius/1000).toFixed(2)+' km radius':'Your drawn area';}

function makeCard(row){const h=row.home,card=element('article',undefined,'home-card');card.dataset.id=h.id;
  const top=element('div',undefined,'card-top');top.append(element('span',typeNames[h.property_type]||h.property_type,'home-type'));
  if(h.previous_price>h.price)top.append(element('span',Math.round(100*(1-h.price/h.previous_price))+'% price drop','signal'));
  else if(row.discount_pct>0&&row.peer_count>=5)top.append(element('span',Math.round(row.discount_pct)+'% below sample','signal'));
  card.append(top,element('div',euro(h.price),'price'));
  const title=element('h2'),link=element('a',h.address||h.title);link.href=h.url;link.target='_blank';link.rel='noopener noreferrer';title.append(link);card.append(title);
  const metrics=element('div',undefined,'metrics');
  if(known(h.sqm))metrics.append(element('span',h.sqm+' m²'));
  if(known(h.rooms))metrics.append(element('span',h.rooms+' rooms'));
  if(known(h.bedrooms))metrics.append(element('span',h.bedrooms+(h.bedrooms===1?' bedroom':' bedrooms')));
  if(known(h.bathrooms))metrics.append(element('span',h.bathrooms+(h.bathrooms===1?' bathroom':' bathrooms')));
  if(known(h.sqm))metrics.append(element('span',euro(h.price/h.sqm)+'/m²'));
  if(h.energy_class)metrics.append(element('span','Energy '+h.energy_class));
  if(metrics.childElementCount)card.append(metrics);
  if(row.summary)card.append(element('p',row.summary,'home-summary'));
  for(const flag of row.flags){if(flag.startsWith('Auction'))card.append(element('div','Auction · check starting bid','risk-label'));if(flag.startsWith('Partial'))card.append(element('div','Ownership restrictions','risk-label'));}
  const bottom=element('div',undefined,'card-bottom');const evidenceButton=element('button','Why this result?');evidenceButton.type='button';evidenceButton.setAttribute('aria-expanded','false');
  const evidence=element('div',undefined,'card-evidence');evidence.hidden=true;
  evidenceButton.addEventListener('click',()=>{evidence.hidden=!evidence.hidden;evidenceButton.setAttribute('aria-expanded',String(!evidence.hidden));});
  const reasons=element('ul');row.reasons.forEach(reason=>reasons.append(element('li',reason)));evidence.append(reasons);
  if(h.location_source)evidence.append(element('p',h.location_source));
  if(h.last_seen)evidence.append(element('p','Last seen: '+new Date(h.last_seen).toLocaleString()));
  const open=element('a','View advert ↗');open.href=h.url;open.target='_blank';open.rel='noopener noreferrer';bottom.append(evidenceButton,open);card.append(bottom,evidence);return card;
}
function renderMarkers(rows){if(!map)return;markerLayer.clearLayers();for(const row of rows){const h=row.home;if(!hasLocation(h))continue;
  const popup=element('div');popup.append(element('strong',euro(h.price),'popup-price'),element('span',h.address,'popup-address'));
  const link=element('a','View advert ↗');link.href=h.url;link.target='_blank';link.rel='noopener noreferrer';popup.append(link);
  L.circleMarker(pointOf(h),{radius:5,color:'#fff',weight:1.5,fillColor:'#185ac5',fillOpacity:.95}).bindPopup(popup).addTo(markerLayer);
}}
function render(){const {base,rows,missing}=selection();
  $('filter-count').textContent=base.length+' matching homes';
  $('area-label').textContent=areaName();$('area-count').textContent=rows.length+' matching homes';
  $('area-missing').textContent=area&&missing?missing+' homes without a matched address excluded.':'';
  $('match-count').textContent=rows.length+' homes';$('located-count').textContent=rows.filter(r=>hasLocation(r.home)).length+' on map';
  $('location-note').textContent=area&&missing?missing+' homes have no matched location.':'';
  const chips=$('active-filters');chips.replaceChildren(element('span','Up to '+euro(Number($('budget').value))),element('span',areaName()));
  if(Number($('min-sqm').value)>0)chips.append(element('span',$('min-sqm').value+'+ m²'));
  const cards=$('cards');cards.replaceChildren(...rows.slice(0,visibleLimit).map(makeCard));
  $('empty').hidden=rows.length>0;$('show-more').hidden=visibleLimit>=rows.length;
  $('show-more').textContent='Show more · '+Math.min(visibleLimit,rows.length)+' of '+rows.length;
  renderMarkers(rows);localize();
}
function setStep(next){step=next;$('preferences').hidden=step===3;$('preferences-step').hidden=step!==1;$('area-step').hidden=step!==2;$('results').hidden=step!==3;$('edit-search').hidden=step!==3;
  $('heading').textContent=step===1?'Filters':step===2?'Choose your area':'Homes';
  $('workspace').className='workspace'+(step===2?' area-mode':step===3?' results-mode':'');
  for(let i=1;i<=3;i++){if(i===step)$('step-'+i).setAttribute('aria-current','step');else $('step-'+i).removeAttribute('aria-current');}
  if(map)requestAnimationFrame(()=>map.invalidateSize());render();save();localize();
}
function drawSavedArea(){if(!map)return;if(shapeLayer)map.removeLayer(shapeLayer);shapeLayer=null;if(!area)return;
  const style={color:'#185ac5',weight:2,fillColor:'#639efb',fillOpacity:.14};
  shapeLayer=area.type==='circle'?L.circle(area.center,{...style,radius:area.radius}):L.polygon(area.points,style);shapeLayer.addTo(map);
}
function cancelDraw(){if(map&&pointer!==null){const canvas=map.getContainer();if(canvas.hasPointerCapture(pointer))const completedPointer=pointer;pointer=null;canvas.releasePointerCapture(completedPointer);}mode=null;points=[];if(draftLayer&&map)map.removeLayer(draftLayer);draftLayer=null;
  $('draw-area').setAttribute('aria-pressed','false');
  if(map){map.getContainer().classList.remove('drawing');map.dragging.enable();map.doubleClickZoom.enable();map.touchZoom.enable();map.scrollWheelZoom.enable();}
  $('map-instruction').textContent='Draw an area or search all Milan.';localize();
}
function beginDraw(){if(!map)return;if(mode){cancelDraw();return;}cancelDraw();mode='freehand';
  map.getContainer().classList.add('drawing');map.dragging.disable();map.doubleClickZoom.disable();map.touchZoom.disable();map.scrollWheelZoom.disable();
  $('draw-area').setAttribute('aria-pressed','true');$('map-instruction').textContent='Hold and drag on the map to draw your area. Release to finish.';localize();
}
function commitArea(candidate){if(!G.validArea(candidate)){$('map-instruction').textContent='Draw a larger area within Milan.';return;}
  area=candidate;cancelDraw();drawSavedArea();visibleLimit=12;render();save();localize();
}
function clearArea(){area=null;cancelDraw();drawSavedArea();visibleLimit=12;render();save();}
function initMap(){if(!online){$('map').hidden=true;document.querySelector('.map-toolbar').hidden=true;$('map-instruction').hidden=true;$('map-error').hidden=false;
  const link=element('a','Open live map →','primary');link.href='http://127.0.0.1:8765/';$('map-error').replaceChildren(link,element('p','If the app is stopped, run: python -m casa_watch --serve'));return;}
  if(!window.L){$('map-error').hidden=false;$('map-error').textContent='Map library unavailable. Filters still work.';return;}
  map=L.map('map',{preferCanvas:true}).setView([45.4642,9.19],12);markerLayer=L.layerGroup().addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,minZoom:10,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).on('tileerror',()=>{$('map-error').hidden=false;$('map-error').textContent='Map tiles could not load. Check your connection.';}).addTo(map);
  // Capture a single continuous stroke. Releasing closes it automatically.
  const canvas=map.getContainer();let lastPixel=null;
  function addPoint(event){const pixel=map.mouseEventToContainerPoint(event);
    if(lastPixel&&pixel.distanceTo(lastPixel)<4)return;
    const latlng=map.containerPointToLatLng(pixel);points.push([latlng.lat,latlng.lng]);lastPixel=pixel;
    if(!draftLayer)draftLayer=L.polyline(points,{color:'#185ac5',weight:3,interactive:false}).addTo(map);
    else draftLayer.setLatLngs(points);
  }
  canvas.addEventListener('pointerdown',event=>{if(mode!=='freehand'||pointer!==null||event.button!==0||event.target.closest('.leaflet-control'))return;
    event.preventDefault();event.stopPropagation();pointer=event.pointerId;points=[];lastPixel=null;canvas.setPointerCapture(pointer);addPoint(event);
  },true);
  canvas.addEventListener('pointermove',event=>{if(event.pointerId!==pointer)return;event.preventDefault();addPoint(event);},true);
  canvas.addEventListener('pointerup',event=>{if(event.pointerId!==pointer)return;event.preventDefault();addPoint(event);const completedPointer=pointer;pointer=null;canvas.releasePointerCapture(completedPointer);
    // Keep the saved shape small while retaining the user's outline.
    const stride=Math.max(1,Math.ceil(points.length/190));const outline=points.filter((_,i)=>i%stride===0);
    if(points.length<6||!G.validArea({type:'polygon',points:outline})){cancelDraw();$('map-instruction').textContent='Draw a larger area, then release.';localize();return;}
    commitArea({type:'polygon',points:outline});
  },true);
  canvas.addEventListener('pointercancel',()=>{pointer=null;cancelDraw();},true);
  drawSavedArea();
}
async function refreshData(){if(!online)return;try{const response=await fetch('homes.json',{cache:'no-store'});if(!response.ok)return;const next=await response.json();if(next.status.checked_at!==data.status.checked_at){data=next;render();}}catch(_){} }
async function refreshProgress(){if(!online)return;try{const response=await fetch('/api/status',{cache:'no-store'});if(!response.ok)return;const progress=await response.json();
  $('scan-state').textContent=progress.running?'Collecting · '+progress.collected+' homes':(data.status.collected_total||data.status.observed)+' collected';
  $('collect').disabled=progress.running||progress.queued;localize();
}catch(_){$('scan-state').textContent='Collector disconnected';$('collect').disabled=true;localize();} }
$('preferences').addEventListener('submit',event=>{event.preventDefault();setStep(2);});
$('preferences').addEventListener('input',()=>{visibleLimit=12;render();save();});
$('back').addEventListener('click',()=>setStep(1));$('show-results').addEventListener('click',()=>{cancelDraw();setStep(3);});$('edit-search').addEventListener('click',()=>setStep(1));
$('sort').addEventListener('change',()=>{visibleLimit=12;render();save();});$('show-more').addEventListener('click',()=>{visibleLimit+=12;render();});
$('draw-area').addEventListener('click',beginDraw);
$('clear-area').addEventListener('click',clearArea);$('reset-area-empty').addEventListener('click',clearArea);document.addEventListener('keydown',event=>{if(event.key==='Escape')cancelDraw();});
$('collect').addEventListener('click',async()=>{if(!online)return;$('collect').disabled=true;try{const response=await fetch('/api/collect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const result=await response.json();$('action-message').textContent=response.ok?'Search queued':'Search unavailable';localize();if(!response.ok)$('collect').disabled=false;}catch(_){$('action-message').textContent='Collector disconnected. Restart python -m casa_watch --serve.';}});
document.querySelectorAll('[data-language]').forEach(button=>button.addEventListener('click',()=>{setLanguage(button.dataset.language);render();}));
restore();initMap();setStep(step);$('collect').hidden=!online;refreshProgress();
if(online){setInterval(refreshData,10000);setInterval(refreshProgress,4000);}
