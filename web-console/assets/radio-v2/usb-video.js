/* USB video player. Assets and sayings are defined by usb-video-manifest.json. */
(()=>{
'use strict';
const $=id=>document.getElementById(id),key='shipwatch-usb-video-enabled';
let enabled=localStorage.getItem(key)!=='false',manifest=null,selected=localStorage.getItem('shipwatch-usb-video-clip')||'welcome',playing=false,radioWasPlaying=false;
const style=document.createElement('style');
style.textContent='.usb-video-dialog{width:min(960px,94vw);max-height:94vh;background:#071820;color:#d8f6ff;border:2px solid #73cfe7;border-radius:12px;padding:18px;font:20px Receiver,Arial,sans-serif}.usb-video-dialog::backdrop{background:#000b}.usb-video-dialog video{display:block;width:100%;max-height:65vh;background:#000;border-radius:6px}.usb-video-dialog h2{margin:0 0 12px}.usb-video-actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:14px}.usb-video-dialog button,.usb-video-dialog select{font:inherit;padding:10px 16px;color:#e1faff;background:#183b49;border:1px solid #72b7ca;border-radius:6px}.usb-video-dialog label{display:block;margin:16px 0}.usb-video-dialog input{width:22px;height:22px;vertical-align:middle}.usb-video-dialog p{line-height:1.4}';
document.head.append(style);
const panel=document.createElement('dialog');panel.className='usb-video-dialog';panel.id='usbVideoDialog';
panel.innerHTML='<h2>Ship Air Watch</h2><video id="usbWelcomeVideo" controls playsinline preload="none"></video><p id="usbVideoMessage" role="status"></p><div class="usb-video-actions"><button id="usbVideoHistory">OPEN HISTORY</button><button id="usbVideoReplay">REPLAY</button><button id="usbVideoClose">CLOSE</button></div>';
document.body.append(panel);
const settings=document.createElement('dialog');settings.className='usb-video-dialog';settings.id='usbVideoSettings';
settings.innerHTML='<h2>USB welcome video</h2><label><input id="usbVideoEnabled" type="checkbox"> Play the welcome video when I click the USB port</label><label>Welcome / saying <select id="usbVideoClip"></select></label><p>When switched off, the USB port opens ship and aircraft history directly. This choice is saved in this browser.</p><p id="usbVideoVersion"></p><div class="usb-video-actions"><button id="usbSettingsPreview">PREVIEW VIDEO</button><button id="usbSettingsHistory">OPEN HISTORY</button><button id="usbSettingsClose">DONE</button></div>';
document.body.append(settings);
const video=$('usbWelcomeVideo'),port=$('usbHistory'),drive=$('usbDrive');
function readyDrive(){ $('gullActor').hidden=true;const logo=$('gullPerch');logo.hidden=false;logo.setAttribute('role','img');logo.setAttribute('aria-label','Seagull radio operator');logo.tabIndex=-1;drive.classList.remove('insert','docking');drive.classList.add('docked');drive.setAttribute('aria-disabled','false');port.setAttribute('aria-busy','false');}
async function loadManifest(){const response=await fetch('assets/radio-v2/usb-video-manifest.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('Welcome video configuration unavailable');const data=await response.json();if(!Array.isArray(data.clips)||!data.clips.length)throw Error('No welcome videos configured');manifest=data;return data;}
function clip(){return manifest?.clips.find(c=>c.id===selected)||manifest?.clips[0];}
function videoUrl(){const c=clip(),url=new URL(c.src,location.href);if(url.origin!==location.origin)throw Error('Welcome video must be a local asset');return url.href;}
function stop(){video.pause();if(playing&&radioWasPlaying&&typeof audio!=='undefined'&&state?.mode==='voice'&&powered)audio.play().catch(()=>{});playing=false;radioWasPlaying=false;readyDrive();}
function close(){stop();panel.close();}
async function play(){if(playing)return;readyDrive();panel.showModal();$('usbVideoMessage').textContent='Loading your welcome video…';try{await loadManifest();video.src=videoUrl();radioWasPlaying=typeof audio!=='undefined'&&!audio.paused;if(radioWasPlaying)audio.pause();playing=true;await video.play();$('usbVideoMessage').textContent='When finished, click OPEN HISTORY.';}catch(error){$('usbVideoMessage').textContent=error.message+'. You can still open history.';stop();}}
window.gullPortClick=()=>enabled?play():openHistory();
const original=$('setup'),setup=original.cloneNode(true);original.replaceWith(setup);
setup.title='USB video settings';setup.setAttribute('aria-label','Setup: enable or disable USB welcome video');
setup.addEventListener('click',async()=>{settings.showModal();$('usbVideoEnabled').checked=enabled;try{await loadManifest();const select=$('usbVideoClip');select.replaceChildren();for(const c of manifest.clips){const o=document.createElement('option');o.value=c.id;o.textContent=c.label;select.append(o)}select.value=clip().id;$('usbVideoVersion').textContent='Welcome pack: '+manifest.version;}catch(error){$('usbVideoVersion').textContent=error.message}});
$('usbVideoEnabled').addEventListener('change',e=>{enabled=e.target.checked;localStorage.setItem(key,String(enabled));});
$('usbVideoClip').addEventListener('change',e=>{selected=e.target.value;localStorage.setItem('shipwatch-usb-video-clip',selected);});
$('usbSettingsClose').onclick=()=>settings.close();
$('usbSettingsPreview').onclick=()=>{settings.close();play()};
$('usbSettingsHistory').onclick=()=>{settings.close();openHistory()};
$('usbVideoHistory').onclick=()=>{close();openHistory()};
$('usbVideoClose').onclick=close;
$('usbVideoReplay').onclick=async()=>{try{if(!playing){radioWasPlaying=typeof audio!=='undefined'&&!audio.paused;if(radioWasPlaying)audio.pause();playing=true;}video.currentTime=0;await video.play();$('usbVideoMessage').textContent='When finished, click OPEN HISTORY.';}catch(error){$('usbVideoMessage').textContent=error.message;stop();}};
video.addEventListener('ended',()=>{stop();$('usbVideoMessage').textContent='Welcome! Open history to explore ships, aircraft and harbour activity.'});
video.addEventListener('error',()=>{if(panel.open){stop();$('usbVideoMessage').textContent='Video could not load. OPEN HISTORY still works.'}});
panel.addEventListener('cancel',stop);panel.addEventListener('close',stop);
drive.addEventListener('click',()=>openHistory());drive.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openHistory()}});
readyDrive();
window.usbVideo={getState:()=>({enabled,selected,playing,version:manifest?.version}),play};
})();