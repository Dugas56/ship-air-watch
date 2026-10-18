<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
function isTug($row) {
 $d=json_decode($row['details'] ?? '{}',true) ?: [];
 return ($d['role'] ?? '')==='harbour_tug' || (int)($d['ship_type'] ?? 0)===52 ||
 in_array(strtoupper(trim(preg_replace('/\s+/',' ',$row['name'] ?? ''))),['ATLANTIC HEMLOCK','ATLANTIC CEDAR'],true);
}
function shipCategory($details) {
 $code=(int)($details['ship_type'] ?? -1);
 if($code>=60 && $code<=69)return 'Passenger ship';
 if($code>=70 && $code<=79)return 'Cargo ship';
 if($code>=80 && $code<=89)return 'Tanker';
 if($code===30)return 'Fishing vessel';
 if($code===31 || $code===32)return 'Towing vessel';
 if($code===33)return 'Dredging or underwater operations';
 if($code===34)return 'Diving operations';
 if($code===35)return 'Military vessel';
 if($code===36)return 'Sailing vessel';
 if($code===37)return 'Pleasure craft';
 if($code>=40 && $code<=49)return 'High-speed craft';
 return [50=>'Pilot vessel',51=>'Search and rescue vessel',52=>'Tug',53=>'Port tender',54=>'Anti-pollution vessel',55=>'Law enforcement vessel',58=>'Medical transport',59=>'Non-combatant vessel'][$code] ?? 'Other vessel';
}
try {
 $home=getenv('SHIPWATCH_HISTORY_HOME') ?: ((getenv('ProgramData') ?: 'C:/ProgramData').'/ShipAirWatch');
 $path=$home.'/history.sqlite';
 if(!is_file($path))throw new RuntimeException('History collector has not created the database yet.');
 $db=new PDO('sqlite:'.$path,null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
 $db->exec('PRAGMA busy_timeout=3000');
 $method=$_SERVER['REQUEST_METHOD'] ?? 'GET';
 if($method==='POST'){
  $origin=$_SERVER['HTTP_ORIGIN'] ?? '';
  $expected=(!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS']!=='off'?'https':'http').'://'.($_SERVER['HTTP_HOST'] ?? '');
  if($origin!==$expected || stripos($_SERVER['CONTENT_TYPE'] ?? '','application/json')!==0){http_response_code(403);echo json_encode(['ok'=>false,'error'=>'Record assists from the history page.']);exit;}
  $in=json_decode(file_get_contents('php://input'),true) ?: [];
  $tug=(string)($in['tug'] ?? '');$ship=(string)($in['ship'] ?? '');$stamp=(float)($in['stamp'] ?? 0);
  $evidence=(string)($in['evidence'] ?? '');
  if(!preg_match('/^\d{9}$/',$tug) || !preg_match('/^\d{9}$/',$ship) || $stamp<946684800 || $stamp>time()+60 || !in_array($evidence,['observed','radio_report'],true))throw new InvalidArgumentException('Choose a tug, ship, time and confirmation source.');
  $q=$db->prepare("SELECT * FROM targets WHERE kind='marine' AND id IN (?,?)");$q->execute([$tug,$ship]);$found=[];
  foreach($q as $r)$found[$r['id']]=$r;
  if(!isset($found[$tug],$found[$ship]) || !isTug($found[$tug]) || isTug($found[$ship]) || $tug===$ship)throw new InvalidArgumentException('Select a recorded harbour tug and a different visiting ship.');
  $q=$db->prepare('INSERT INTO assists(tug,ship,stamp,evidence,note,created) VALUES(?,?,?,?,?,?) ON CONFLICT(tug,ship,stamp) DO UPDATE SET evidence=excluded.evidence,note=excluded.note');
  $q->execute([$tug,$ship,$stamp,$evidence,mb_substr(trim((string)($in['note'] ?? '')),0,200),time()]);
  echo json_encode(['ok'=>true]);exit;
 }
 $db->exec('PRAGMA query_only=ON');
 $meta=[];foreach($db->query('SELECT key,value FROM meta') as $r)$meta[$r['key']]=json_decode($r['value'],true);
 $kind=($_GET['kind'] ?? 'marine')==='air'?'air':'marine';$view=$_GET['view'] ?? 'targets';
 // Classify all saved ship profiles before applying the display limit.
 $marine=[];$tugs=[];foreach($db->query("SELECT * FROM targets WHERE kind='marine' ORDER BY last_seen DESC") as $r){if(isTug($r))$tugs[$r['id']]=$r;else $marine[$r['id']]=$r;}
 if($view==='tugs'){
  $kind='marine';$rows=[];
  $q=$db->prepare('SELECT a.*,t.name ship_name FROM assists a JOIN targets t ON t.kind=\'marine\' AND t.id=a.ship WHERE a.tug=? ORDER BY stamp DESC LIMIT 1');
  $n=$db->prepare('SELECT count(*) FROM assists WHERE tug=?');
  foreach(array_slice($tugs,0,500,true) as $id=>$r){$q->execute([$id]);$r['last_assist']=$q->fetch(PDO::FETCH_ASSOC) ?: null;$n->execute([$id]);$r['assist_count']=(int)$n->fetchColumn();$rows[]=$r;}
 }elseif($view==='tracks'){
  $kind='marine';
  $ids=array_values(array_unique(array_filter(explode(',',(string)($_GET['ids'] ?? '')),fn($id)=>preg_match('/^\\d{9}$/',$id))));
  $ids=array_slice($ids,0,30);
  $hours=max(1,min(168,(int)($_GET['hours'] ?? 24)));
  $rows=[];
  if($ids){
   $marks=implode(',',array_fill(0,count($ids),'?'));
   $q=$db->prepare("SELECT id,stamp,lat,lon FROM sightings WHERE kind='marine' AND id IN ($marks) AND stamp>=? ORDER BY id,stamp DESC");
   $q->execute([...$ids,time()-$hours*3600]);
   $tracks=[];
   foreach($q as $r){$id=$r['id'];if(!isset($tracks[$id]))$tracks[$id]=[];if(count($tracks[$id])<500)$tracks[$id][]=['stamp'=>(int)$r['stamp'],'lat'=>(float)$r['lat'],'lon'=>(float)$r['lon']];}
   foreach($tracks as $id=>$points){$rows[]=['id'=>$id,'points'=>array_reverse($points)];}
  }
  echo json_encode(['ok'=>true,'kind'=>'marine','view'=>'tracks','hours'=>$hours,'rows'=>$rows]);exit;
 }else{
  if($view==='visits'){
   $sql="SELECT v.*,t.name,t.details FROM visits v JOIN targets t ON t.kind=v.kind AND t.id=v.target WHERE v.kind=?";
   $args=[$kind];if(isset($_GET['id']) && $_GET['id']!==''){$sql.=' AND v.target=?';$args[]=(string)$_GET['id'];}
   $sql.=' ORDER BY v.start DESC';$q=$db->prepare($sql);$q->execute($args);
  }else{
   $q=$db->prepare("SELECT t.*,(SELECT count(*) FROM visits v WHERE v.kind=t.kind AND v.target=t.id) visit_count,
    (SELECT count(*) FROM visits v WHERE v.kind=t.kind AND v.target=t.id AND v.end IS NOT NULL AND v.status='confirmed exit') confirmed_exits,
    (SELECT status FROM visits v WHERE v.kind=t.kind AND v.target=t.id ORDER BY v.start DESC LIMIT 1) status
    FROM targets t WHERE t.kind=? ORDER BY last_seen DESC");$q->execute([$kind]);
  }
  $rows=[];foreach($q as $r){if($kind==='marine' && isTug($r))continue;$rows[]=$r;if(count($rows)>=500)break;}
 }
 foreach($rows as &$r){$r['details']=json_decode($r['details'],true) ?: [];if($r['kind']==='marine')$r['details']['ship_category']=$r['details']['ship_category'] ?? shipCategory($r['details']);}unset($r);
 $counts=['marine'=>count($marine),'tugs'=>count($tugs)];
 $counts['air']=(int)$db->query("SELECT count(*) FROM targets WHERE kind='air'")->fetchColumn();
 $counts['visits']=0;foreach($db->query("SELECT v.target,count(*) n FROM visits v WHERE kind='marine' GROUP BY target") as $r)if(!isset($tugs[$r['target']]))$counts['visits']+=(int)$r['n'];
 $counts['passes']=(int)$db->query("SELECT count(*) FROM visits WHERE kind='air'")->fetchColumn();
 $passengerChart=[];$passengerTotal=0;
 $q=$db->query("SELECT t.id,t.name,t.details,count(v.id) visit_count FROM targets t LEFT JOIN visits v ON v.kind=t.kind AND v.target=t.id WHERE t.kind='marine' GROUP BY t.id ORDER BY visit_count DESC,t.name");
 foreach($q as $r){if(isTug($r))continue;$d=json_decode($r['details'],true) ?: [];if(shipCategory($d)!=='Passenger ship')continue;$n=(int)$r['visit_count'];$passengerTotal+=$n;$passengerChart[]=['id'=>$r['id'],'name'=>$r['name'],'flag_country_code'=>$d['flag_country_code'] ?? null,'visit_count'=>$n];}
 $counts['passenger_ships']=count($passengerChart);$counts['passenger_visits']=$passengerTotal;
 $counts['database_bytes']=(int)filesize($path)+(is_file($path.'-wal')?(int)filesize($path.'-wal'):0);
 $counts['positions']=(int)$db->query('SELECT count(*) FROM sightings')->fetchColumn();
 $choices=[];if($view==='tugs')foreach($marine as $r)$choices[]=['id'=>$r['id'],'name'=>$r['name'],'lat'=>$r['lat'],'lon'=>$r['lon'],'last_seen'=>$r['last_seen']];
 echo json_encode(['ok'=>true,'meta'=>$meta,'counts'=>$counts,'kind'=>$kind,'view'=>$view,'rows'=>$rows,'ship_choices'=>$choices,'passenger_chart'=>$passengerChart]);
}catch(Throwable $e){http_response_code($e instanceof InvalidArgumentException?400:503);echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);}
