/* Coordinates are [latitude, longitude]. Shared with offline Node tests. */
(function (root) {
  'use strict';
  function distance(a,b) {const r=Math.PI/180,dl=(b[0]-a[0])*r,dn=(b[1]-a[1])*r;const h=Math.sin(dl/2)**2+Math.cos(a[0]*r)*Math.cos(b[0]*r)*Math.sin(dn/2)**2;return 6371000*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));}
  function onSegment(p,a,b){const cross=(p[0]-a[0])*(b[1]-a[1])-(p[1]-a[1])*(b[0]-a[0]);return Math.abs(cross)<1e-10&&p[0]>=Math.min(a[0],b[0])-1e-10&&p[0]<=Math.max(a[0],b[0])+1e-10&&p[1]>=Math.min(a[1],b[1])-1e-10&&p[1]<=Math.max(a[1],b[1])+1e-10;}
  function inside(point,area){if(!area)return true;if(!point||!point.every(Number.isFinite))return false;if(area.type==='circle')return distance(point,area.center)<=area.radius+.01;let hit=false;const p=area.points;for(let i=0,j=p.length-1;i<p.length;j=i++){if(onSegment(point,p[i],p[j]))return true;if((p[i][1]>point[1])!==(p[j][1]>point[1])&&point[0]<(p[j][0]-p[i][0])*(point[1]-p[i][1])/(p[j][1]-p[i][1])+p[i][0])hit=!hit;}return hit;}
  function validArea(a){const p=x=>Array.isArray(x)&&x.length===2&&x.every(Number.isFinite)&&x[0]>=45.2&&x[0]<=45.8&&x[1]>=8.8&&x[1]<=9.6;return !!a&&((a.type==='circle'&&p(a.center)&&Number.isFinite(a.radius)&&a.radius>=20&&a.radius<=40000)||(a.type==='polygon'&&Array.isArray(a.points)&&a.points.length>=3&&a.points.length<=200&&a.points.every(p)));}
  const api={distance,inside,validArea};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CasaGeometry=api;
})(typeof window==='undefined'?{}:window);
