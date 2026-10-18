#!/usr/bin/env python3
import json, re, subprocess, threading, time, os, select
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen, Request

CONFIG_PATH=os.environ.get("SHIPWATCH_CONFIG","/etc/shipwatch/shipwatch.json")

def load_shipwatch_config():
    try:
        with open(CONFIG_PATH,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(f"Unable to load Shipwatch config {CONFIG_PATH}: {exc}")

CONFIG=load_shipwatch_config()
NETWORK=CONFIG.get("network",{})
RECEIVERS=CONFIG.get("receivers",{})
VOICE_CFG=RECEIVERS.get("voice",{})
AIS_CFG=RECEIVERS.get("ais",{})

HOST="0.0.0.0"
PORT=int(NETWORK.get("radio_port",8088))
WEB_PORT=int(NETWORK.get("web_port",80))
AIS_WEB_PORT=int(NETWORK.get("ais_web_port",8100))
PUBLIC_HOST=str(NETWORK.get("public_host") or "")
DEVICE=str(VOICE_CFG.get("serial") or AIS_CFG.get("serial") or "")
VOICE_SHARED_WITH_AIS=(VOICE_CFG.get("share_with")=="ais" or not VOICE_CFG.get("dedicated",False))

ALLOWED_ORIGINS=set()
if PUBLIC_HOST:
    ALLOWED_ORIGINS.add(f"http://{PUBLIC_HOST}")
    ALLOWED_ORIGINS.add(f"http://{PUBLIC_HOST}:{WEB_PORT}")

if not DEVICE:
    raise RuntimeError("No Voice SDR serial configured in shipwatch.json")
BANKS={
    "air":[
        (118.500,"CYSJ Radio / MF"),
        (123.475,"Halifax FIC"),
        (124.300,"Moncton Centre"),
        (126.700,"Halifax FIC"),
        (135.500,"Moncton Centre"),
    ],
    "marine":[
        (156.575,"Ch 71 — Port / working"),
        (156.600,"Ch 12 — VTS / Port Operations"),
        (156.700,"Ch 14 — VTS / Port Operations"),
        (156.800,"Ch 16 — Distress / Calling"),
        (161.800,"Ch 24 — Coast station"),
        (161.900,"Ch 26 — Coast station"),
    ],
}
BANKS.update({'ham': [[147.27, 'VE9SJN — Saint John'], [146.895, 'Local club repeater'], [145.13, 'Local club repeater'], [146.82, 'VE9STJ — Saint John East'], [145.33, 'VE9STM — Grove Hill'], [146.52, 'Ham FM calling']], 'frs': [[462.5625, 'FRS/GMRS Ch 1'], [462.5875, 'FRS/GMRS Ch 2'], [462.6125, 'FRS/GMRS Ch 3'], [462.6375, 'FRS/GMRS Ch 4'], [462.6625, 'FRS/GMRS Ch 5'], [462.6875, 'FRS/GMRS Ch 6'], [462.7125, 'FRS/GMRS Ch 7'], [462.55, 'FRS/GMRS Ch 15'], [462.575, 'FRS/GMRS Ch 16'], [462.6, 'FRS/GMRS Ch 17'], [462.625, 'FRS/GMRS Ch 18'], [462.65, 'FRS/GMRS Ch 19'], [462.675, 'FRS/GMRS Ch 20'], [462.7, 'FRS/GMRS Ch 21'], [462.725, 'FRS/GMRS Ch 22']]})
CHANNELS=BANKS["air"]

state_lock=threading.Lock()
stream_lock=threading.Lock()
state={
    "mode":"map",
    "bank":"air",
    "squelch":5,
    "hold":None,
    "tune_base":None,
    "tune_offset_khz":0,
    "current_freq":None,
    "current_label":"SCANNING",
    "activity":False,
    "last_audio":0.0,
    "last_heard":[],
    "generation":0,
    "scanner_pid":None,
    "scanner_error":None,
    "scan_index":0,
    "scan_count":0,
}

def run(*args):
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def is_active(service):
    return subprocess.run(["systemctl","is-active","--quiet",service]).returncode==0

def ais_active():
    return subprocess.run(["pgrep","-f","AIS-catcher"],stdout=subprocess.DEVNULL).returncode==0

def nearest_channel(hz):
    mhz=hz/1_000_000.0
    with state_lock:
        bank=state["bank"]
    f,label=min(BANKS[bank],key=lambda x:abs(x[0]-mhz))
    return f,label

VOICE_LEASE_SECONDS=int(VOICE_CFG.get("voice_lease_seconds",900 if VOICE_SHARED_WITH_AIS else 0))
def voice_safety_timer(generation):
    if VOICE_LEASE_SECONDS <= 0:
        return
    time.sleep(VOICE_LEASE_SECONDS)
    with state_lock:
        expired=(state["mode"]=="voice" and state["generation"]==generation)
    if expired:
        set_mode("map")
def set_mode(mode):
    if mode=="voice":
        if VOICE_SHARED_WITH_AIS:
            run("systemctl","stop","ais-catcher")
        with state_lock:
            state["mode"]="voice"
            state["generation"]+=1
            generation=state["generation"]
        if VOICE_LEASE_SECONDS > 0:
            threading.Thread(
                target=voice_safety_timer,
                args=(generation,),
                daemon=True
            ).start()
    elif mode=="map":
        with state_lock:
            state["mode"]="map"
            state["generation"]+=1
            pid=state.get("scanner_pid")
            state["scanner_pid"]=None
        if pid:
            run("kill","-TERM",str(pid))
        run("pkill","-f",f"rtl_fm.*{DEVICE}")
        time.sleep(1.0)
        if VOICE_SHARED_WITH_AIS:
            run("systemctl","start","ais-catcher")

def scanner_command():
    with state_lock:
        squelch=int(state["squelch"])
        hold=state["hold"]
        bank=state["bank"]
    cmd=["rtl_fm","-d",DEVICE]
    freqs=[hold] if hold else [f for f,_ in BANKS[bank]]
    for f in freqs:
        cmd += ["-f",f"{f:.4f}M"]
    modulation="am" if bank=="air" else "fm"
    cmd += ["-M",modulation,"-s","24000","-r","24000","-g","38","-l",str(squelch),"-t","10"]
    return cmd

def update_from_stderr(pipe, generation):
    rx=re.compile(r"(?:Tuned to|Frequency:?)[^0-9]*(\d{7,10})")
    for raw in iter(pipe.readline,b""):
        try:
            line=raw.decode(errors="ignore")
            m=rx.search(line)
            if not m:
                continue
            f,label=nearest_channel(int(m.group(1)))
            with state_lock:
                if generation!=state["generation"]:
                    break
                state["current_freq"]=f
                state["current_label"]=label
        except Exception:
            pass

def note_audio(generation):
    now=time.time()
    with state_lock:
        if generation!=state["generation"]:
            return
        was_quiet=now-state["last_audio"]>2.0
        state["last_audio"]=now
        state["activity"]=True
        if was_quiet and state["current_freq"]:
            item={
                "time":time.strftime("%H:%M:%S"),
                "freq":state["current_freq"],
                "label":state["current_label"],
            }
            state["last_heard"]=[item]+state["last_heard"][:7]

def status():
    with state_lock:
        s=dict(state)
        s.pop("generation",None)
        s["scanner_running"]=bool(s.pop("scanner_pid",None))
    s["readsb"]="online" if is_active("readsb") else "offline"
    s["ais"]="online" if ais_active() else "offline"
    s["activity"]=time.time()-s["last_audio"]<2.0
    return s


audio_condition=threading.Condition()
audio_chunks=[]
audio_sequence=0

def stop_child(p):
    if p is None:
        return
    if p.poll() is None:
        p.terminate()
    try:
        p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=2)

def publish_audio(ff, generation):
    global audio_sequence
    while True:
        chunk=ff.stdout.read1(1024)
        if not chunk:
            break
        with state_lock:
            if generation!=state["generation"]:
                break
        with audio_condition:
            audio_sequence+=1
            audio_chunks.append((audio_sequence,generation,chunk))
            del audio_chunks[:-128]
            audio_condition.notify_all()

def receiver_errors(pipe, generation):
    for raw in iter(pipe.readline,b""):
        line=raw.decode(errors="replace").strip()
        if any(word in line.lower() for word in ("error","failed","not found","busy","usb_claim")):
            with state_lock:
                if generation==state["generation"]:
                    state["scanner_error"]=line[:240]

def background_scanner():
    while True:
        with state_lock:
            mode=state["mode"]
            generation=state["generation"]
            bank=state["bank"]
        if mode!="voice":
            time.sleep(0.15)
            continue
        rtl=ff=None
        try:
            with state_lock:
                state["scanner_error"]=None
            ff=subprocess.Popen(
                ["ffmpeg","-hide_banner","-loglevel","error","-f","s16le","-ar","24000","-ac","1",
                 "-i","pipe:0","-af","volume=1","-c:a","libmp3lame","-b:a","64k",
                 "-flush_packets","1","-f","mp3","pipe:1"],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            threading.Thread(target=publish_audio,args=(ff,generation),daemon=True).start()
            index=0
            while True:
                with state_lock:
                    if state["generation"]!=generation or state["mode"]!="voice":
                        break
                    hold=state["hold"]
                f,label=min(BANKS[bank],key=lambda x:abs(x[0]-hold)) if hold else BANKS[bank][index]
                if hold:
                    f=hold
                cmd=scanner_command()
                first=cmd.index("-f")
                end=cmd.index("-M")
                cmd[first:end]=["-f",f"{f:.4f}M"]
                rtl=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                with state_lock:
                    state["scanner_pid"]=rtl.pid
                    state["current_freq"]=f
                    state["current_label"]=label
                    state["scan_index"]=index+1
                    state["scan_count"]=len(BANKS[bank])
                    state["last_audio"]=0.0
                threading.Thread(target=receiver_errors,args=(rtl.stderr,generation),daemon=True).start()
                tuned_at=time.monotonic()
                quiet_until=tuned_at+0.6
                activity_started=None
                while True:
                    with state_lock:
                        changed=state["generation"]!=generation or state["mode"]!="voice"
                    if changed:
                        break
                    if rtl.poll() is not None:
                        raise RuntimeError("Radio receiver exited; check scanner_error and journal")
                    ready,_,_=select.select([rtl.stdout],[],[],0.1)
                    if ready:
                        chunk=os.read(rtl.stdout.fileno(),4096)
                        if not chunk:
                            raise RuntimeError("Radio receiver closed its audio output")
                        chunk=chunk[:len(chunk)//2*2]
                        if chunk:
                            if any(chunk):
                                note_audio(generation)
                                if activity_started is None:
                                    activity_started=time.monotonic()
                            ff.stdin.write(chunk)
                            ff.stdin.flush()
                    if not hold and ((activity_started is None and time.monotonic()>=quiet_until) or (activity_started is not None and time.monotonic()-activity_started>=15)):
                        break
                stop_child(rtl)
                rtl=None
                with state_lock:
                    state["scanner_pid"]=None
                index=(index+1)%len(BANKS[bank])
        except Exception as exc:
            with state_lock:
                if state["generation"]==generation:
                    state["scanner_error"]=state.get("scanner_error") or str(exc)
            print("Scanner error: "+str(exc),flush=True)
            time.sleep(1)
        finally:
            stop_child(rtl)
            stop_child(ff)
            with state_lock:
                state["scanner_pid"]=None
                state["current_freq"]=None
                state["activity"]=False


PAGE=r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ship Watcher — Radio Listening Post</title>
<style>
:root{
  --bg:#070b0d;--case:#1a2024;--case2:#11171a;--edge:#39454b;--text:#e7edf0;
  --muted:#94a2a9;--green:#9dff78;--green2:#57c746;--amber:#ffcf5a;--red:#ff665e;
  --blue:#63d5ff;--shadow:#000a
}
*{box-sizing:border-box}
body{
  margin:0;min-height:100vh;background:
  radial-gradient(circle at 50% -20%,#26353d 0,#11191d 36%,#06090b 76%);
  color:var(--text);font-family:Segoe UI,Arial,sans-serif
}
.wrap{max-width:1180px;margin:auto;padding:24px}
.brand{display:flex;justify-content:space-between;align-items:end;gap:15px;margin-bottom:14px}
.brand h1{margin:0;font-size:24px;letter-spacing:.12em;text-transform:uppercase}
.brand .sub{font-size:12px;letter-spacing:.18em;color:#94a8b2;text-transform:uppercase;margin-bottom:5px}
.badges{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.badge{border:1px solid #46555c;background:#11191d;border-radius:999px;padding:6px 10px;font-size:11px;letter-spacing:.07em}
.on{color:#76ef85}.off{color:#ff716a}

.radio{
  background:linear-gradient(150deg,#242d32 0,#171e22 45%,#0f1518 100%);
  border:1px solid #435158;border-radius:20px;padding:22px;
  box-shadow:0 26px 60px #000b,inset 0 1px #ffffff18,inset 0 -2px #0008
}
.face{display:grid;grid-template-columns:190px 1fr 190px;gap:22px;align-items:center}
@media(max-width:820px){.face{grid-template-columns:1fr}.knobbox{order:2}.displaybox{order:1}}

.knobbox{text-align:center}
.knobtitle{font-size:12px;letter-spacing:.17em;color:#bac4c9;margin-bottom:8px}
.knobwrap{width:144px;height:144px;margin:auto;position:relative}
.scale{
  position:absolute;inset:0;border-radius:50%;
  background:conic-gradient(from 225deg,#4f626b 0deg,#4f626b 270deg,transparent 270deg);
  -webkit-mask:radial-gradient(circle,#0000 59%,#000 61% 68%,#0000 70%);
  mask:radial-gradient(circle,#0000 59%,#000 61% 68%,#0000 70%);
  opacity:.58
}
.knob{
  --angle:-135deg;
  position:absolute;inset:18px;border-radius:50%;cursor:grab;user-select:none;touch-action:none;
  background:
    radial-gradient(circle at 35% 27%,#3f484d 0 8%,#1d2428 28%,#0c1114 66%,#030506 100%);
  border:2px solid #4b565b;
  box-shadow:0 9px 18px #000b,inset 0 3px 7px #ffffff16,inset 0 -5px 10px #000b
}
.knob:active{cursor:grabbing}
.knob:after{
  content:"";position:absolute;left:50%;top:8px;width:4px;height:34px;border-radius:3px;
  background:#e6edf0;box-shadow:0 0 5px #fff8;
  transform-origin:50% 45px;transform:translateX(-50%) rotate(var(--angle))
}
.knobvalue{font:700 18px Consolas,monospace;color:#e7ecee;margin-top:7px}
.knobhint{font-size:10px;color:#778991;margin-top:2px}
.ticknum{position:absolute;font:700 10px Consolas,monospace;color:#aebbc1;line-height:1;pointer-events:none;text-shadow:0 1px 2px #000}
.tick0{left:12px;bottom:16px}.tick5{left:-2px;top:66px}.tick10{left:13px;top:16px}.tick15{left:43px;top:-2px}.tick20{left:69px;top:-7px}.tick25{right:39px;top:-2px}.tick30{right:10px;top:16px}.tick35{right:-3px;top:66px}.tick40{right:10px;bottom:16px}
.stepper{display:flex;justify-content:center;align-items:center;gap:10px;margin-top:7px}
.stepbtn{width:38px;height:30px;border-radius:6px;border:1px solid #56636a;background:linear-gradient(#313b40,#151c20);color:#eef4f6;font:800 18px/1 Consolas,monospace;cursor:pointer;box-shadow:0 3px 0 #070a0c}
.stepbtn:active{transform:translateY(2px);box-shadow:0 1px 0 #070a0c}

.displaybox{
  background:#080d08;border:6px solid #050708;border-radius:12px;padding:15px 18px 13px;
  box-shadow:inset 0 0 22px #000,0 0 0 1px #4b5550,0 8px 20px #0008
}
.lcdtop{display:flex;justify-content:space-between;gap:10px;color:#5fae57;font:700 11px Consolas,monospace;letter-spacing:.1em}
.freq{
  text-align:center;font:700 clamp(46px,7.5vw,82px)/1.03 "Courier New",Consolas,monospace;
  letter-spacing:.045em;color:var(--green);
  text-shadow:0 0 5px #8dff6eaa,0 0 18px #57ff3877;margin:9px 0 5px;
  font-variant-numeric:tabular-nums
}
.label{text-align:center;min-height:26px;color:#b6ff9f;font:700 17px Consolas,monospace;letter-spacing:.06em}
.lcdline{height:1px;background:#254424;margin:10px 0 8px}
.meterrow{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;font:700 11px Consolas,monospace;color:#74c66b}
.meter{height:13px;display:flex;gap:3px;align-items:end}
.seg{flex:1;min-width:7px;height:45%;background:#173318;border-radius:2px;box-shadow:inset 0 0 3px #000}
.seg:nth-child(n+5){height:65%}.seg:nth-child(n+8){height:85%}.seg:nth-child(n+10){height:100%}
.meter.rx .seg:nth-child(-n+8){background:#69e653;box-shadow:0 0 5px #67e45266}
.meter.rx .seg:nth-child(n+9):nth-child(-n+10){background:#ffd35c}
.meter.rx .seg:nth-child(n+11){background:#ff655e}
.modeflag{color:#8cff72}

.keys{display:flex;gap:9px;justify-content:center;flex-wrap:wrap;margin-top:22px}
.key{
  min-width:112px;padding:10px 14px;border-radius:7px;border:1px solid #4e5b61;color:#eef4f6;
  background:linear-gradient(#303a3f,#171e22);box-shadow:0 4px 0 #080c0e,0 6px 10px #0007;
  font-weight:800;letter-spacing:.04em;cursor:pointer
}
.key:active{transform:translateY(3px);box-shadow:0 1px 0 #080c0e}
.key.primary{border-color:#3e879e;color:#d9f7ff}
.key.warn{border-color:#7f7047;color:#ffe7a6}

.statusline{margin-top:16px;display:flex;justify-content:center;align-items:center;gap:9px;font-weight:800;letter-spacing:.07em}
.rxled{width:12px;height:12px;border-radius:50%;background:#273136;box-shadow:0 0 0 4px #11191d}
.statusline.active .rxled{background:#79ef64;box-shadow:0 0 13px #71ef5f}

.audioarea{margin-top:16px}
audio{width:100%;height:38px;filter:grayscale(.75) brightness(.9)}

.lower{display:grid;grid-template-columns:1.25fr .75fr;gap:16px;margin-top:16px}
@media(max-width:850px){.lower{grid-template-columns:1fr}}
.panel{background:#11181c;border:1px solid #38454b;border-radius:14px;padding:16px;box-shadow:0 12px 24px #0007}
.paneltitle{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#9baeb7;margin-bottom:11px}
.channels{display:grid;gap:7px}
.ch{display:grid;grid-template-columns:100px 1fr auto;gap:9px;align-items:center;background:#0c1215;border:1px solid #28363d;border-radius:8px;padding:8px 10px}
.ch b{font:700 15px Consolas,monospace;color:#b6ff9f}.ch span{color:#c3ccd0}.tinykey{padding:6px 9px;min-width:65px}
.history{display:grid;gap:6px}.hist{display:grid;grid-template-columns:70px 85px 1fr;gap:8px;padding:6px 0;border-bottom:1px solid #243137;font-size:13px}
.hist .f{font-family:Consolas,monospace;color:#ffd169}
.mapmini{margin-top:14px;border:1px solid #31444d;border-radius:10px;overflow:hidden;background:#071019;box-shadow:inset 0 0 18px #000}
.mapminihead{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:#0c1418;border-bottom:1px solid #2b3b42;font-size:11px;letter-spacing:.11em;color:#9fb2bb;text-transform:uppercase}
.mapmini iframe{display:block;width:100%;height:270px;border:0;background:#0a1114}
.mapmini button{padding:5px 8px;min-width:auto;font-size:10px}
.note{margin-top:10px;color:#7f919a;font-size:11px;text-align:center}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">
    <div><div class="sub">Ship Watcher</div><h1>Radio Listening Post</h1></div>
    <div class="badges"><span id="ais" class="badge">AIS</span><span id="adsb" class="badge">ADS-B</span><span id="mode" class="badge">MODE</span></div>
  </div>

  <div class="radio">
    <div class="face">
      <div class="knobbox">
        <div class="knobtitle">VOLUME</div>
        <div class="knobwrap"><div class="scale"></div><div id="volKnob" class="knob"></div></div>
        <div id="volValue" class="knobvalue">70</div>
        <div class="knobhint">drag or mouse wheel</div>
      </div>

      <div class="displaybox">
        <div class="lcdtop"><span>SHIP WATCHER RX-1</span><span><b id="bankFlag">AIR</b> • <b id="holdFlag">SCAN</b></span></div>
        <div id="freq" class="freq">---.---</div>
        <div id="label" class="label">AIRBAND SCANNER</div>
        <div class="lcdline"></div>
        <div class="meterrow">
          <span>S</span>
          <div id="meter" class="meter">
            <i class="seg"></i><i class="seg"></i><i class="seg"></i><i class="seg"></i><i class="seg"></i><i class="seg"></i>
            <i class="seg"></i><i class="seg"></i><i class="seg"></i><i class="seg"></i><i class="seg"></i><i class="seg"></i>
          </div>
          <span id="rxText">SQL</span>
        </div>
      </div>

      <div class="knobbox">
        <div class="knobtitle">SQUELCH</div>
        <div class="knobwrap">
          <div class="scale"></div>
          <span class="ticknum tick0">0</span><span class="ticknum tick5">5</span><span class="ticknum tick10">10</span><span class="ticknum tick15">15</span><span class="ticknum tick20">20</span><span class="ticknum tick25">25</span><span class="ticknum tick30">30</span><span class="ticknum tick35">35</span><span class="ticknum tick40">40</span>
          <div id="sqlKnob" class="knob"></div>
        </div>
        <div class="stepper"><button type="button" class="stepbtn" onclick="stepSquelch(-1)">−</button><div id="sqlValue" class="knobvalue">5</div><button type="button" class="stepbtn" onclick="stepSquelch(1)">+</button></div>
        <div class="knobhint">detents 0–40 • one click = one step</div>
      </div>
    </div>

    <div class="keys">
      <button class="key primary" onclick="setBank('air')">AIR BANK</button>
      <button class="key primary" onclick="setBank('marine')">MARINE BANK</button>
      <button class="key" onclick="setMode('voice')">VOICE MODE</button>
      <button class="key" onclick="setMode('map')">AIRCRAFT MAP</button>
      <button class="key" onclick="resume()">SCAN</button>
      <button class="key warn" onclick="toggleMute()">MUTE</button>
      <button class="key" onclick="startAudio()">LISTEN</button>
      <button class="key" onclick="stopAudio()">STOP</button>
    </div>

    <div id="statusline" class="statusline"><span class="rxled"></span><span id="lamptext">SQUELCHED</span></div>
    <div class="audioarea"><audio id="audio" controls preload="none"></audio></div>
    <div class="note">VOICE_FALLBACK_NOTE</div>
  </div>

  <div class="lower">
    <section class="panel">
      <div class="paneltitle">Scan Bank — HOLD parks receiver on a frequency</div>
      <div id="channels" class="channels"></div>
    </section>
    <section class="panel">
      <div class="paneltitle">Last Heard</div>
      <div id="history" class="history"><div class="note">No transmissions logged yet.</div></div>
      <div class="mapmini">
        <div class="mapminihead"><span>Marine Map Preview</span><button class="key" onclick="window.open('http://SHIPWATCH_PUBLIC_HOST/shipwatch/','_blank')">OPEN MARINE MAP</button></div>
        <iframe src="http://SHIPWATCH_PUBLIC_HOST/shipwatch/" loading="lazy" title="Marine map preview"></iframe>
      </div>
    </section>
  </div>
</div>

<script>
const banks=BANKS_JSON;
let currentBank="air";
let channels=banks[currentBank];
const $=id=>document.getElementById(id);
let volume=70, muted=false, sqlTimer=null, scanIndex=0, scanTimer=null, latestState=null;

function startScanDisplay(){clearInterval(scanTimer);}

function drawChannels(){
  $('channels').innerHTML=channels.map(c=>'<div class="ch"><b>'+c[0].toFixed(3)+'</b><span>'+c[1]+'</span><button class="key tinykey" onclick="hold('+c[0]+')">HOLD</button></div>').join('');
}
async function api(url,opt){let r=await fetch(url,opt);return r.json();}

function knobAngle(value,min,max){return -135+((value-min)/(max-min))*270}
function paintKnob(id,value,min,max){
  $(id).style.setProperty('--angle',knobAngle(value,min,max)+'deg');
}
function setVolume(v){
  volume=Math.max(0,Math.min(100,Math.round(v)));
  $('volValue').textContent=volume;
  paintKnob('volKnob',volume,0,100);
  $('audio').volume=volume/100;
}
function queueSquelch(v){
  v=Math.max(0,Math.min(40,Math.round(v)));
  const old=parseInt($('sqlValue').textContent||'5');
  if(v===old) return;
  $('sqlValue').textContent=v;
  paintKnob('sqlKnob',v,0,40);
  clearTimeout(sqlTimer);
  sqlTimer=setTimeout(()=>setSq(v),180);
}
function stepSquelch(delta){
  const v=parseInt($('sqlValue').textContent||'5');
  queueSquelch(v+delta);
}
function bindKnob(id,getValue,setValue,min,max){
  const el=$(id);
  el.addEventListener('wheel',e=>{e.preventDefault();setValue(getValue()+(e.deltaY<0?1:-1))},{passive:false});
  el.addEventListener('pointerdown',e=>{
    e.preventDefault();el.setPointerCapture(e.pointerId);
    const r=el.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;
    const move=ev=>{
      let deg=Math.atan2(ev.clientY-cy,ev.clientX-cx)*180/Math.PI+90;
      if(deg<0)deg+=360;
      let a=deg;
      if(a>225 && a<315) a=(a<270?225:315);
      let signed=a>180?a-360:a;
      signed=Math.max(-135,Math.min(135,signed));
      setValue(min+((signed+135)/270)*(max-min));
    };
    const up=ev=>{el.releasePointerCapture(ev.pointerId);el.removeEventListener('pointermove',move);el.removeEventListener('pointerup',up)};
    el.addEventListener('pointermove',move);el.addEventListener('pointerup',up);
  });
}

async function setMode(m){
  if(m==='map') stopAudio();
  await api('/api/mode?set='+m,{method:'POST'});
  if(m==='voice') setTimeout(startAudio,500);
  else setTimeout(()=>window.location.href='/map',900);
  refresh();
}
async function setBank(b){
  await api('/api/bank?set='+b,{method:'POST'});
  currentBank=b;channels=banks[b];scanIndex=0;drawChannels();
  if(latestState && latestState.mode==='voice') restartAudio();
  refresh();
}
async function hold(f){await api('/api/hold?freq='+f,{method:'POST'});restartAudio();}
async function resume(){await api('/api/hold?clear=1',{method:'POST'});restartAudio();}
async function setSq(v){
  await api('/api/squelch?value='+v,{method:'POST'});
  restartAudio();
}
function startAudio(){
  let a=$('audio');a.src='/air.mp3?x='+Date.now();a.volume=volume/100;a.muted=muted;a.play().catch(()=>{});
}
function stopAudio(){let a=$('audio');a.pause();a.removeAttribute('src');a.load();}
function restartAudio(){let a=$('audio');if(!a.paused){stopAudio();setTimeout(startAudio,350)}}
function toggleMute(){muted=!muted;$('audio').muted=muted;event.target.textContent=muted?'UNMUTE':'MUTE';}

async function refresh(){
  try{
    let s=await api('/api/status'); latestState=s;
    currentBank=s.bank||'air';channels=banks[currentBank];$('bankFlag').textContent=currentBank.toUpperCase();
    $('mode').textContent='MODE: '+s.mode.toUpperCase();$('mode').className='badge '+(s.mode==='voice'?'on':'');
    $('ais').textContent='AIS: '+s.ais.toUpperCase();$('ais').className='badge '+(s.ais==='online'?'on':'off');
    $('adsb').textContent='ADS-B: '+s.readsb.toUpperCase();$('adsb').className='badge '+(s.readsb==='online'?'on':'off');
    $('sqlValue').textContent=s.squelch;paintKnob('sqlKnob',s.squelch,0,40);
    if(s.current_freq && s.scanner_running){$('freq').textContent=s.current_freq.toFixed(3);$('label').textContent=s.current_label;$('holdFlag').textContent=s.hold?'HOLD':(s.activity?'RX':'SCAN');}
    else if(s.hold){$('freq').textContent=s.hold.toFixed(3);$('label').textContent='HOLD';$('holdFlag').textContent='HOLD';}
    $('statusline').className='statusline '+(s.activity?'active':'');$('lamptext').textContent=s.activity?'RECEIVING':'SQUELCHED';
    $('meter').className='meter '+(s.activity?'rx':'');$('rxText').textContent=s.activity?'RX':'SQL';
    if(s.last_heard.length){$('history').innerHTML=s.last_heard.map(x=>'<div class="hist"><span>'+x.time+'</span><span class="f">'+x.freq.toFixed(3)+'</span><span>'+x.label+'</span></div>').join('');}
  }catch(e){}
}

drawChannels();
setVolume(70);paintKnob('sqlKnob',5,0,40);
bindKnob('volKnob',()=>volume,setVolume,0,100);
bindKnob('sqlKnob',()=>parseInt($('sqlValue').textContent||'5'),queueSquelch,0,40);
startScanDisplay();refresh();setInterval(refresh,300);
</script>
</body></html>"""

PAGE=PAGE.replace("BANKS_JSON",json.dumps(BANKS))
PAGE=PAGE.replace("SHIPWATCH_PUBLIC_HOST",PUBLIC_HOST or "localhost")
PAGE=PAGE.replace(
    "VOICE_FALLBACK_NOTE",
    "Voice and AIS share one receiver. Voice OFF restores AIS automatically."
    if VOICE_SHARED_WITH_AIS
    else "Voice has its own dedicated receiver. AIS remains online while listening."
)

MAP_PAGE=r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ship Watcher — Aircraft Map</title>
<style>
html,body{margin:0;height:100%;background:#071019;color:#eef6f8;font-family:Segoe UI,Arial,sans-serif}
.top{height:54px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;background:#11191d;border-bottom:1px solid #33434b}
.brand{font-weight:800;letter-spacing:.08em}.btns{display:flex;gap:8px}
button{border:1px solid #4d5c64;background:linear-gradient(#303a3f,#171e22);color:#eef4f6;border-radius:7px;padding:9px 13px;font-weight:800;cursor:pointer}
button.primary{border-color:#3e879e;color:#d9f7ff}
iframe{width:100%;height:calc(100% - 55px);border:0;background:white}
</style></head>
<body>
<div class="top"><div class="brand">SHIP WATCHER • AIRCRAFT MAP</div>
<div class="btns"><button class="primary" onclick="backToRadio()">RADIO LISTENING POST</button></div></div>
<iframe src="http://192.168.2.29/tar1090/"></iframe>
<script>
async function backToRadio(){
  window.location.href='http://localhost/ship-watch/radio.html';
}
</script>
</body></html>"""


recovery_lock=threading.Lock()

def recover_receiver(target):
    services={"aircraft":"readsb","marine":"ais-catcher"}
    service=services.get(target)
    if not service:
        return {"ok":False,"error":"Invalid receiver"},400
    if not recovery_lock.acquire(blocking=False):
        return {"ok":False,"error":"Another receiver operation is in progress"},409
    try:
        with state_lock:
            if target=="marine" and state["mode"]=="voice" and VOICE_SHARED_WITH_AIS:
                return {"ok":False,"error":"Turn Voice OFF before restarting AIS"},409
        result=subprocess.run(["systemctl","restart",service],capture_output=True,text=True,timeout=15)
        if result.returncode:
            return {"ok":False,"error":result.stderr.strip()[:240] or "Service restart failed"},503
        time.sleep(1)
        online=is_active(service)
        detail=""
        if not online:
            log=subprocess.run(["journalctl","-u",service,"-n","15","--no-pager"],capture_output=True,text=True,timeout=3).stdout
            detail="Configured aircraft USB receiver not found; reconnect the aircraft dongle." if "no device matching" in log else "Receiver did not stay running; inspect its service log."
        return {"ok":online,"service":service,"error":detail,"message":"Service restarted. Waiting for new received data." if online else detail},200 if online else 503
    except subprocess.TimeoutExpired:
        return {"ok":False,"error":"Restart timed out; check receiver status before retrying"},504
    finally:
        recovery_lock.release()

def fetch_ais_json(path):
    url=f"http://127.0.0.1:{AIS_WEB_PORT}{path}"
    req=Request(url,headers={"User-Agent":"Shipwatch-Radio-Bridge"})
    with urlopen(req,timeout=4) as response:
        return json.loads(response.read().decode("utf-8","replace"))


def waterlevel_payload():
    data=fetch_ais_json("/api/binmsgs.json?receiver=0")
    rows=[]
    for row in data.get("messages",[]) if isinstance(data,dict) else []:
        msg=row.get("message",{}) if isinstance(row,dict) else {}
        if (
            msg.get("mmsi")==3160016
            and msg.get("dac")==1
            and msg.get("fid")==31
            and isinstance(msg.get("waterlevel"),(int,float))
        ):
            rows.append(row)
    rows.sort(key=lambda row: row.get("timestamp",0),reverse=True)
    return {"ok":True,"station":3160016,"reports":rows[:12]}


class Handler(BaseHTTPRequestHandler):
    def cors(self):
        origin=self.headers.get("Origin","")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin",origin)
            self.send_header("Vary","Origin")

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type, X-ShipWatch-Recovery")
        self.send_header("Access-Control-Max-Age","600")
        self.end_headers()

    def json(self,obj,code=200):
        data=json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.cors()
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p=urlparse(self.path)
        if p.path=="/":
            data=PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if p.path=="/map":
            data=MAP_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if p.path=="/api/status":
            self.json(status())
            return
        if p.path=="/api/ais-ships":
            try:
                self.json(fetch_ais_json("/api/ships_array.json"))
            except Exception as exc:
                self.json({"ok":False,"error":f"AIS feed unavailable: {exc}"},502)
            return
        if p.path=="/api/waterlevel":
            try:
                self.json(waterlevel_payload())
            except Exception as exc:
                self.json({"ok":False,"error":f"Water-level feed unavailable: {exc}"},502)
            return
        if p.path=="/air.mp3":

            with state_lock:
                if state["mode"]!="voice":
                    self.send_error(409,"Switch to VOICE mode first")
                    return
                generation=state["generation"]
            self.send_response(200)
            self.send_header("Content-Type","audio/mpeg")
            self.send_header("Cache-Control","no-store")
            self.cors()
            self.end_headers()
            with audio_condition:
                cursor=audio_sequence
            try:
                while True:
                    with state_lock:
                        if generation!=state["generation"] or state["mode"]!="voice":
                            break
                    with audio_condition:
                        chunks=[(seq,data) for seq,gen,data in audio_chunks if gen==generation and seq>cursor]
                        if not chunks:
                            audio_condition.wait(timeout=0.5)
                            continue
                    for seq,data in chunks:
                        self.wfile.write(data)
                        self.wfile.flush()
                        cursor=seq
            except (BrokenPipeError,ConnectionResetError,OSError):
                pass
            return
        self.send_error(404)

    def do_POST(self):
        p=urlparse(self.path)
        q=parse_qs(p.query)
        if p.path=="/api/restart":
            if self.headers.get("X-ShipWatch-Recovery")!="confirmed":
                return self.json({"ok":False,"error":"Recovery confirmation required"},403)
            result,code=recover_receiver(q.get("receiver",[""])[0])
            return self.json(result,code)
        if p.path=="/api/mode":
            m=q.get("set",[""])[0]
            if m not in ("voice","map"):
                return self.json({"ok":False},400)
            if not recovery_lock.acquire(blocking=False):
                return self.json({"ok":False,"error":"Receiver recovery in progress"},409)
            try:
                set_mode(m)
            finally:
                recovery_lock.release()
            return self.json({"ok":True,"mode":m})
        if p.path=="/api/bank":
            b=q.get("set",[""])[0]
            if b not in BANKS:
                return self.json({"ok":False},400)
            with state_lock:
                state["tune_base"]=None
                state["tune_offset_khz"]=0
                state["bank"]=b
                state["hold"]=None
                state["current_freq"]=None
                state["current_label"]="SCANNING"
                state["generation"]+=1
            return self.json({"ok":True,"bank":b})
        if p.path=="/api/squelch":
            try:
                v=max(0,min(40,int(q.get("value",["5"])[0])))
            except Exception:
                v=5
            with state_lock:
                state["squelch"]=v
                state["generation"]+=1
            return self.json({"ok":True,"squelch":v})
        if p.path=="/api/tune":
            try:
                delta=int(q.get("step",["0"])[0])
                if delta not in (-1,0,1):
                    return self.json({"ok":False,"error":"Invalid step"},400)
            except ValueError:
                return self.json({"ok":False,"error":"Invalid step"},400)
            with state_lock:
                if state["mode"]!="voice" or not state["hold"]:
                    return self.json({"ok":False,"error":"Select a channel HOLD in voice mode first"},409)
                base=state["tune_base"] or state["hold"]
                offset=0 if "reset" in q else state["tune_offset_khz"]+delta
                if abs(offset)>10:
                    return self.json({"ok":False,"error":"Fine tune limit is +/-10 kHz"},400)
                state["tune_base"]=base
                state["tune_offset_khz"]=offset
                state["hold"]=round(base+offset/1000,4)
                state["generation"]+=1
                result={"ok":True,"freq":state["hold"],"offset_khz":offset}
            return self.json(result)
        if p.path=="/api/hold":
            with state_lock:
                state["tune_base"]=None
                state["tune_offset_khz"]=0
                if "clear" in q:
                    state["hold"]=None
                else:
                    try:
                        state["hold"]=float(q.get("freq",[""])[0])
                    except Exception:
                        state["hold"]=None
                state["generation"]+=1
            return self.json({"ok":True,"hold":state["hold"]})
        self.send_error(404)

    def log_message(self,*args):
        pass

if __name__=="__main__":
    with state_lock:
        state["mode"]="map" if is_active("readsb") else "voice"
    threading.Thread(target=background_scanner,daemon=True).start()
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
