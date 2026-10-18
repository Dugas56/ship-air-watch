"""Ship Air Watch: passive local AIS/ADS-B history collector (standard library only)."""
import argparse, gzip, json, math, os, shutil, sqlite3, time, urllib.request
from pathlib import Path

DEFAULT_HOME = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData" if os.name == "nt" else str(Path.home()))) / "ShipAirWatch"
DEFAULTS = {"ais_url":"http://192.168.2.29:8100/api/ships_array.json",
 "air_url":"http://192.168.2.29/tar1090/data/aircraft.json",
 "harbour":{"name":"Saint John observation area (provisional)","lat":45.27,"lon":-66.065,"radius_km":6.0},
 "poll_seconds":15,"fresh_seconds":120,"signal_gap_seconds":600,
 "position_days":7,"position_max_rows":200000,"marine_sample_seconds":60,"air_sample_seconds":30,"backup_copies":7}
SCHEMA = """
CREATE TABLE IF NOT EXISTS assists(id INTEGER PRIMARY KEY,tug TEXT,ship TEXT,stamp REAL,evidence TEXT,note TEXT,created REAL,UNIQUE(tug,ship,stamp));
CREATE INDEX IF NOT EXISTS assist_tug ON assists(tug,stamp);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS targets(kind TEXT,id TEXT,name TEXT,first_seen REAL,last_seen REAL,
 lat REAL,lon REAL,details TEXT,PRIMARY KEY(kind,id));
CREATE TABLE IF NOT EXISTS sightings(kind TEXT,id TEXT,stamp REAL,lat REAL,lon REAL,details TEXT,
 PRIMARY KEY(kind,id,stamp));
CREATE INDEX IF NOT EXISTS sighting_stamp ON sightings(stamp);
CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY,kind TEXT,target TEXT,label TEXT,
 start REAL,last_seen REAL,end REAL,status TEXT,arrival_known INTEGER DEFAULT 0,
 interrupted INTEGER DEFAULT 0,exit_candidate REAL,exit_last REAL,exit_count INTEGER DEFAULT 0,
 min_alt REAL,max_alt REAL,max_speed REAL);
CREATE INDEX IF NOT EXISTS visit_target ON visits(kind,target,start);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_visit ON visits(kind,target) WHERE end IS NULL;
"""
def connect(path):
    db=sqlite3.connect(path,timeout=10)
    db.row_factory=sqlite3.Row
    if db.execute("PRAGMA auto_vacuum").fetchone()[0] != 2:
        db.execute("PRAGMA auto_vacuum=INCREMENTAL"); db.execute("VACUUM")
    db.executescript(SCHEMA)
    db.execute("PRAGMA journal_mode=WAL")
    return db
def put(db,key,value):
    db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key,json.dumps(value)))
def distance(lat,lon,zone):
    p1,p2=map(math.radians,[lat,zone["lat"]])
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(zone["lon"]-lon)/2)**2
    return 6371*2*math.asin(math.sqrt(min(1,a)))
def valid(lat,lon):
    return isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and -90<=lat<=90 and -180<=lon<=180
def number(value):
    return value if isinstance(value,(int,float)) and math.isfinite(value) else None
def is_tug(name,details):
    return details.get("role")=="harbour_tug" or details.get("ship_type")==52 or " ".join(name.upper().split()) in {"ATLANTIC HEMLOCK","ATLANTIC CEDAR"}
def ship_category(code):
    if not isinstance(code,(int,float)): return None
    code=int(code)
    if 60<=code<=69: return "Passenger ship"
    if 70<=code<=79: return "Cargo ship"
    if 80<=code<=89: return "Tanker"
    if code==30: return "Fishing vessel"
    if 31<=code<=32: return "Towing vessel"
    if code==33: return "Dredging or underwater operations"
    if code==34: return "Diving operations"
    if code==35: return "Military vessel"
    if code==36: return "Sailing vessel"
    if code==37: return "Pleasure craft"
    if 40<=code<=49: return "High-speed craft"
    return {50:"Pilot vessel",51:"Search and rescue vessel",52:"Tug",53:"Port tender",
            54:"Anti-pollution vessel",55:"Law enforcement vessel",58:"Medical transport",
            59:"Non-combatant vessel"}.get(code,"Other vessel")
def flag_country(code):
    if not isinstance(code,str) or len(code)!=2 or not code.isalpha(): return None
    return code.upper()
def record(db,kind,ident,name,stamp,lat,lon,details,now,cfg):
    if now-stamp>cfg["fresh_seconds"] or stamp>now+30 or not valid(lat,lon): return
    old=db.execute("SELECT * FROM targets WHERE kind=? AND id=?",(kind,ident)).fetchone()
    if old and stamp<=old["last_seen"]: return
    merged=json.loads(old["details"]) if old else {}
    merged.update({k:v for k,v in details.items() if v is not None and v!=""})
    name=name or (old["name"] if old else ident)
    tug=kind=="marine" and is_tug(name,merged)
    if tug: merged["role"]="harbour_tug"
    encoded=json.dumps(merged)
    db.execute("""INSERT INTO targets VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET
     name=excluded.name,last_seen=excluded.last_seen,lat=excluded.lat,lon=excluded.lon,details=excluded.details""",
     (kind,ident,name,old["first_seen"] if old else stamp,stamp,lat,lon,encoded))
    previous=db.execute("SELECT stamp FROM sightings WHERE kind=? AND id=? ORDER BY stamp DESC LIMIT 1",(kind,ident)).fetchone()
    sample=cfg.get(kind+"_sample_seconds",60 if kind=="marine" else 30)
    if not previous or stamp-previous["stamp"]>=sample:
        db.execute("INSERT OR IGNORE INTO sightings VALUES(?,?,?,?,?,?)",(kind,ident,stamp,lat,lon,encoded))
    if tug: return  # Tug work is recorded as assists, not visitor arrivals/returns.
    visit=db.execute("SELECT * FROM visits WHERE kind=? AND target=? AND end IS NULL",(kind,ident)).fetchone()
    gap= bool(old and stamp-old["last_seen"]>cfg["signal_gap_seconds"])
    if kind=="air" and visit and (gap or (details.get("callsign") and visit["label"]!=details["callsign"])):
        db.execute("UPDATE visits SET end=last_seen,status='pass ended (observation)' WHERE id=?",(visit["id"],))
        visit=None
    if kind=="marine":
        d=distance(lat,lon,cfg["harbour"])
        inside=d<=cfg["harbour"]["radius_km"]
        outside=d>cfg["harbour"]["radius_km"]+0.5
        if visit and gap:
            db.execute("UPDATE visits SET interrupted=1,exit_candidate=NULL,exit_count=0 WHERE id=?",(visit["id"],))
            visit=db.execute("SELECT * FROM visits WHERE id=?",(visit["id"],)).fetchone()
        if visit:
            if outside:
                first=visit["exit_candidate"] or stamp
                count=visit["exit_count"]+1
                if count>=2 and stamp-first>=60:
                    db.execute("UPDATE visits SET end=?,status='confirmed exit',last_seen=?,exit_count=? WHERE id=?",
                               (first,stamp,count,visit["id"]))
                else:
                    db.execute("UPDATE visits SET exit_candidate=?,exit_last=?,exit_count=?,last_seen=?,status='exit pending' WHERE id=?",
                               (first,stamp,count,stamp,visit["id"]))
            elif inside:
                db.execute("UPDATE visits SET last_seen=?,status='in area',exit_candidate=NULL,exit_count=0 WHERE id=?",(stamp,visit["id"]))
            else:
                db.execute("UPDATE visits SET last_seen=? WHERE id=?",(stamp,visit["id"]))
        elif inside:
            known= bool(old and not gap and distance(old["lat"],old["lon"],cfg["harbour"])>cfg["harbour"]["radius_km"]+0.5)
            db.execute("INSERT INTO visits(kind,target,label,start,last_seen,status,arrival_known) VALUES(?,?,?,?,?,'in area',?)",
                       (kind,ident,name,stamp,stamp,int(known)))
    else:
        alt=number(details.get("altitude_ft")); speed=number(details.get("speed_knots"))
        if not visit:
            db.execute("""INSERT INTO visits(kind,target,label,start,last_seen,status,min_alt,max_alt,max_speed)
             VALUES(?,?,?,?,?,'observed pass',?,?,?)""",(kind,ident,details.get("callsign") or name,stamp,stamp,alt,alt,speed))
        else:
            db.execute("""UPDATE visits SET last_seen=?,status='observed pass',
             min_alt=CASE WHEN ? IS NULL THEN min_alt WHEN min_alt IS NULL THEN ? ELSE min(min_alt,?) END,
             max_alt=CASE WHEN ? IS NULL THEN max_alt WHEN max_alt IS NULL THEN ? ELSE max(max_alt,?) END,
             max_speed=CASE WHEN ? IS NULL THEN max_speed WHEN max_speed IS NULL THEN ? ELSE max(max_speed,?) END WHERE id=?""",
             (stamp,alt,alt,alt,alt,alt,alt,speed,speed,speed,visit["id"]))
def ingest(db,kind,data,now,cfg):
    if kind=="marine":
        if not isinstance(data.get("dynamic"),list): raise ValueError("Invalid AIS payload")
        names={str(r[0]):r for r in data.get("static",[]) if len(r)>5}
        for r in data["dynamic"]:
            ident=str(r[0])
            # Exclude AIS base stations, buoys, AtoN, SAR aircraft and non-ship IDs.
            if len(ident)!=9 or not 2<=int(ident[0])<=7 or len(r)<14: continue
            s=names.get(ident,[])
            details={key:(s[i] if len(s)>i else None) for key,i in [("callsign",2),("destination",3),("ship_type",4),("imo",5)]}
            details["ship_category"]=ship_category(details.get("ship_type"))
            details["flag_country_code"]=flag_country(r[21] if len(r)>21 else None)
            if len(s)>9 and all(isinstance(s[i],(int,float)) for i in range(6,10)):
                details["length_m"]=s[6]+s[7]
                details["width_m"]=s[8]+s[9]
            if len(s)>10 and isinstance(s[10],(int,float)) and s[10]>0: details["draught_m"]=s[10]
            details.update(speed_knots=r[7],course=r[6],heading=r[5] if len(r)>5 else None,
                           navigation_status=r[12] if len(r)>12 else None)
            record(db,kind,ident,str(s[1]).strip() if s else ident,float(r[13]),r[1],r[2],details,now,cfg)
    else:
        if not isinstance(data.get("aircraft"),list): raise ValueError("Invalid aircraft payload")
        feed_now=float(data["now"])
        for a in data["aircraft"]:
            ident=str(a.get("hex",""))
            if not ident or not valid(a.get("lat"),a.get("lon")) or "seen_pos" not in a: continue
            stamp=feed_now-float(a["seen_pos"])
            callsign=str(a.get("flight","")).strip()
            record(db,kind,ident,callsign,stamp,a["lat"],a["lon"],
                   {"callsign":callsign,"altitude_ft":a.get("alt_baro"),"geometric_altitude_ft":a.get("alt_geom"),
                    "speed_knots":a.get("gs"),"track":a.get("track"),"squawk":a.get("squawk"),
                    "aircraft_type":a.get("t"),"aircraft_type_description":a.get("desc"),
                    "registration":a.get("r"),"operator":a.get("ownOp"),"year":a.get("year"),
                    "category":a.get("category"),"vertical_rate_fpm":a.get("baro_rate"),
                    "true_heading":a.get("true_heading"),"emergency":a.get("emergency")},now,cfg)
    db.execute("UPDATE visits SET status='signal gap / whereabouts unknown',interrupted=1 WHERE kind='marine' AND end IS NULL AND last_seen<?",
               (now-cfg["signal_gap_seconds"],))
    db.execute("UPDATE visits SET status='pass ended (observation)',end=last_seen WHERE kind='air' AND end IS NULL AND last_seen<?",
               (now-cfg["signal_gap_seconds"],))
    put(db,kind+"_feed",{"ok":True,"checked":now,"error":None})
def poll(db,cfg):
    for kind,key in [("marine","ais_url"),("air","air_url")]:
        now=time.time()
        try:
            req=urllib.request.Request(cfg[key],headers={"User-Agent":"ShipAirWatch-History/1"})
            with urllib.request.urlopen(req,timeout=5) as response: data=json.load(response)
            with db: ingest(db,kind,data,now,cfg)
        except Exception as exc:
            with db: put(db,kind+"_feed",{"ok":False,"checked":now,"error":str(exc)[:200]})
    with db:
        put(db,"heartbeat",time.time())

def maintain(db,home,cfg):
    now=time.time()
    old=db.execute("SELECT value FROM meta WHERE key='maintenance'").fetchone()
    if old and now-json.loads(old[0]).get("checked",0)<86400: return
    with db:
        db.execute("DELETE FROM sightings WHERE stamp<?",(now-cfg.get("position_days",7)*86400,))
        limit=max(1000,int(cfg.get("position_max_rows",200000)))
        count=db.execute("SELECT count(*) FROM sightings").fetchone()[0]
        if count>limit:
            db.execute("DELETE FROM sightings WHERE rowid IN (SELECT rowid FROM sightings ORDER BY stamp LIMIT ?)",(count-limit,))
        put(db,"maintenance",{"checked":now,"position_days":cfg.get("position_days",7),
            "position_max_rows":limit,"backup_copies":cfg.get("backup_copies",7),"summaries":"retained"})
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA incremental_vacuum(2000)")
    backups=home/"backups";backups.mkdir(exist_ok=True)
    temp=backups/"history-snapshot.sqlite"
    dest=backups/("history-"+time.strftime("%Y%m%d",time.gmtime())+".sqlite.gz")
    copy=sqlite3.connect(temp);db.backup(copy);copy.close()
    pending=dest.with_suffix(".gz.tmp")
    with open(temp,"rb") as source,gzip.open(pending,"wb",compresslevel=6) as output: shutil.copyfileobj(source,output)
    pending.replace(dest);temp.unlink()
    for stale in sorted(backups.glob("history-*.sqlite.gz"),reverse=True)[cfg.get("backup_copies",7):]:stale.unlink()
    with db: put(db,"backup",{"checked":now,"compressed_bytes":dest.stat().st_size})
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--home",type=Path,default=DEFAULT_HOME);parser.add_argument("--once",action="store_true")
    args=parser.parse_args();args.home.mkdir(parents=True,exist_ok=True)
    config=args.home/"history-config.json"
    if not config.exists(): config.write_text(json.dumps(DEFAULTS,indent=2),encoding="utf-8")
    cfg={**DEFAULTS,**json.loads(config.read_text(encoding="utf-8"))}
    config.write_text(json.dumps(cfg,indent=2),encoding="utf-8")
    # OS lock prevents duplicate collectors after task retries.
    lock=open(args.home/"collector.lock","a+b");lock.seek(0);lock.write(b"0");lock.flush();lock.seek(0)
    try:
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError: return
    db=connect(args.home/"history.sqlite")
    with db:
        put(db,"area",cfg["harbour"])
        db.execute("INSERT OR IGNORE INTO meta VALUES('started',?)",(json.dumps(time.time()),))
    while True:
        poll(db,cfg)
        try: maintain(db,args.home,cfg)
        except Exception as exc:
            with db: put(db,"maintenance_error",str(exc)[:200])
        # Hard count cap also enforced during a very busy day.
        with db:
            limit=cfg.get("position_max_rows",200000)
            excess=db.execute("SELECT count(*) FROM sightings").fetchone()[0]-limit
            if excess>0: db.execute("DELETE FROM sightings WHERE rowid IN (SELECT rowid FROM sightings ORDER BY stamp LIMIT ?)",(excess,))
        if args.once: break
        time.sleep(max(5,cfg["poll_seconds"]))
if __name__=="__main__": main()
