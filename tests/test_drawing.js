// Exercise the pointer gesture without a browser or external map tiles.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const G = require('../casa_watch/web/geometry.js');
const source = fs.readFileSync('casa_watch/web/app.js', 'utf8');
const handlers = {};
let captured = null, committed = null;
const canvas = {
  addEventListener: (type, handler) => { handlers[type] = handler; },
  setPointerCapture: id => { captured = id; },
  releasePointerCapture: () => { captured = null; },
};
const context = {
  mode: 'freehand', pointer: null, points: [], draftLayer: null, G,
  map: {
    getContainer: () => canvas,
    mouseEventToContainerPoint: e => ({x:e.x,y:e.y,distanceTo:p=>Math.hypot(e.x-p.x,e.y-p.y)}),
    containerPointToLatLng: p => ({lat:45.46+p.y/10000,lng:9.19+p.x/10000}),
  },
  L: {polyline: () => ({addTo(){return this;},setLatLngs(){}})},
  commitArea: shape => { committed = shape; },
  cancelDraw: () => {}, localize: () => {}, $: () => ({}),
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('  const canvas=map.getContainer();let lastPixel'),source.indexOf('  drawSavedArea();',source.indexOf('// Capture a single'))),context);
const event = (x,y) => ({x,y,pointerId:1,button:0,target:{closest:()=>false},preventDefault(){},stopPropagation(){}});
handlers.pointerdown(event(0,0));
assert.equal(captured,1);
for(const p of [[40,0],[80,20],[90,60],[60,90],[20,80],[0,40]]) handlers.pointermove(event(...p));
handlers.pointerup(event(0,0));
assert.equal(captured,null);
assert.equal(context.pointer,null);
assert.equal(committed.type,'polygon');
assert.equal(G.inside([45.464,9.194],committed),true);
assert.equal(G.inside([45.48,9.22],committed),false);
committed=null;
handlers.pointerdown(event(1,1));handlers.pointerup(event(2,2));
assert.equal(committed,null,'A tap must not replace the selected area');
console.log('Freehand drag closes and filters the shape; accidental taps do not select an area.');
