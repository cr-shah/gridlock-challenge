/* Decorative screen-space network. Never represents project geography. */
(() => {
  const canvas = document.createElement('canvas');
  canvas.className = 'radar-network-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const context = canvas.getContext('2d');
  if (!context) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const points = Array.from({length:170}, (_,i) => ({x:((i*73)%997)/997,y:((i*151)%991)/991,vx:Math.sin(i*2.3)*.000012,vy:Math.cos(i*1.7)*.000012}));
  let width=0,height=0,frame=0,last=0,shiftX=0,shiftY=0;
  function resize() {
    width=innerWidth; height=innerHeight;
    const ratio=Math.min(devicePixelRatio || 1,2);
    canvas.width=width*ratio; canvas.height=height*ratio;
    canvas.style.width=width+'px'; canvas.style.height=height+'px';
    context.setTransform(ratio,0,0,ratio,0,0);
  }
  function draw(now) {
    frame=0;
    if(document.hidden || !document.body.classList.contains('radar-view')) return;
    const step=Math.min((now-last)/16.67 || 1,2); last=now;
    context.clearRect(0,0,width,height);
    points.forEach(p=>{
      if(!reduced.matches) { p.x=(p.x+p.vx*step+1)%1; p.y=(p.y+p.vy*step+1)%1; }
    });
    const xy=points.map(p=>({x:p.x*width+shiftX,y:p.y*height+shiftY}));
    const radius=105;
    for(let i=0;i<xy.length;i++) {
      for(let j=i+1;j<xy.length;j++) {
        const distance=Math.hypot(xy[i].x-xy[j].x,xy[i].y-xy[j].y);
        if(distance<radius) {
          context.strokeStyle=`rgba(139,196,185,${(1-distance/radius)*.13})`;
          context.lineWidth=.6;context.beginPath();context.moveTo(xy[i].x,xy[i].y);context.lineTo(xy[j].x,xy[j].y);context.stroke();
        }
      }
      context.fillStyle='rgba(185,227,217,.3)';context.beginPath();context.arc(xy[i].x,xy[i].y,1.4,0,Math.PI*2);context.fill();
    }
    if(!reduced.matches) frame=requestAnimationFrame(draw);
  }
  function sync() { if(frame) cancelAnimationFrame(frame);frame=0;last=0;if(!document.hidden && document.body.classList.contains('radar-view')) frame=requestAnimationFrame(draw); }
  addEventListener('pointermove',event=>{if(!reduced.matches){shiftX=(event.clientX/innerWidth-.5)*12;shiftY=(event.clientY/innerHeight-.5)*12;}},{passive:true});
  addEventListener('resize',()=>{resize();sync();});
  document.addEventListener('visibilitychange',sync);
  reduced.addEventListener('change',()=>{shiftX=0;shiftY=0;sync();});
  new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:['class']});
  resize();sync();
})();
