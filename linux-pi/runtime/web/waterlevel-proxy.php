<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$ctx=stream_context_create(['http'=>['timeout'=>5,'ignore_errors'=>true]]);
$raw=@file_get_contents('http://192.168.2.29:8100/api/binmsgs.json?receiver=0',false,$ctx);
$data=$raw===false?null:json_decode($raw,true);
if(!is_array($data)){http_response_code(502);echo json_encode(['ok'=>false,'error'=>'AIS feed unavailable']);exit;}
$rows=array_values(array_filter($data['messages']??[],function($r){
 $m=$r['message']??[];
 return ($m['mmsi']??0)==3160016 && ($m['dac']??0)==1 && ($m['fid']??0)==31 && isset($m['waterlevel']) && is_numeric($m['waterlevel']);
}));
usort($rows,function($a,$b){return ($b['timestamp']??0)<=>($a['timestamp']??0);});
echo json_encode(['ok'=>true,'station'=>3160016,'reports'=>array_slice($rows,0,12)]);
