/* Illustrated mascot animation; radio services and audio are independent. */
(()=>{
 'use strict';
 const get=id=>document.getElementById(id),actor=get('gullActor'),perch=get('gullPerch'),drive=get('usbDrive'),port=get('usbHistory'),carried=get('gullCarriedDrive');
 let inserted=sessionStorage.getItem('shipwatch-gull-usb')==='inserted',busy=false,flight=null,timers=[];
 function clearTimers(){timers.forEach(clearTimeout);timers=[]}
 function later(fn,delay){timers.push(setTimeout(fn,delay))}
 function finish(){clearTimers();flight?.cancel();flight=null;actor.hidden=true;perch.hidden=false;drive.classList.remove('docking');drive.classList.add('docked');inserted=true;busy=false;port.setAttribute('aria-busy','false');port.setAttribute('aria-label','Open saved ship and aircraft history');sessionStorage.setItem('shipwatch-gull-usb','inserted');drive.setAttribute('aria-disabled','false')}
 function start(){
  if(busy)return; // The socket explicitly replays the optional flight.
  clearTimers();perch.classList.remove('winking');
  busy=true;port.setAttribute('aria-busy','true');drive.setAttribute('aria-disabled','true');perch.hidden=true;drive.classList.remove('docked','docking','insert');actor.hidden=false;actor.classList.remove('returning');carried.hidden=false;
  // A deliberate socket click opts into this flight, including when the OS requests reduced motion.
  // Initial page load never flies; the computer's motion preference is unchanged.
  flight=actor.animate([
   {transform:'translate(1774px,35px) scale(1)',offset:0},
   {transform:'translate(1440px,70px) scale(1)',offset:.13},
   {transform:'translate(770px,225px) scale(1)',offset:.36},
   {transform:'translate(170px,465px) scale(1)',offset:.51},
   {transform:'translate(50px,674px) scale(1)',offset:.58},
   {transform:'translate(50px,674px) scale(1)',offset:.75},
   {transform:'translate(735px,250px) scale(.85)',offset:.88},
   {transform:'translate(1480px,1px) scale(.64)',offset:1}
  ],{duration:6200,easing:'linear',fill:'forwards'});
  later(()=>{carried.hidden=true;drive.classList.add('docking')},3600);
  later(()=>{drive.classList.remove('docking');drive.classList.add('docked');inserted=true;drive.setAttribute('aria-disabled','false');port.setAttribute('aria-label','Open saved ship and aircraft history')},4400);
  later(()=>actor.classList.add('returning'),4650);
  flight.finished.then(()=>{finish();perch.classList.add('winking');later(()=>perch.classList.remove('winking'),650);toast('USB ready — CLICK ME for history')}).catch(()=>{});
 }
 function openInserted(){if(inserted&&!busy)openHistory()}
 drive.addEventListener('click',openInserted);drive.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openInserted()}});
 perch.addEventListener('click',openInserted);
 window.gullPortClick=start;
 window.gullUsb={getState:()=>({inserted,busy}),start,
  // Deterministic animation inspection/export without changing receiver state.
  previewAt(ms){clearTimers();flight?.pause();if(flight)flight.currentTime=ms;actor.hidden=ms>=6200;perch.hidden=ms<6200;carried.hidden=ms>=3600;drive.classList.toggle('docked',ms>=4400);drive.classList.toggle('docking',ms>=3600&&ms<4400);actor.classList.toggle('returning',ms>=4650);if(ms>=3600&&ms<4400){drive.style.animation='none';drive.style.visibility='visible';drive.style.opacity='1';drive.style.transform='translateY('+(4-42*Math.min(1,(ms-3600)/800))+'px)'}else{drive.style.removeProperty('animation');drive.style.removeProperty('visibility');drive.style.removeProperty('opacity');drive.style.removeProperty('transform')}},
 };
 if(inserted)finish();else{actor.hidden=true;perch.hidden=false;perch.setAttribute('aria-label','Seagull radio operator');port.setAttribute('aria-label','Send the seagull to insert the history USB drive')}
})();
