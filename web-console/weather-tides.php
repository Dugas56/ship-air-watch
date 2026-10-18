<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$start=gmdate('Y-m-d\T00:00:00\Z',time()-86400);
$end=gmdate('Y-m-d\T00:00:00\Z',time()+172800);
$url='https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/5cebf1df3d0f4a073c4bbc24/data?'.http_build_query(['time-series-code'=>'wlp-hilo','from'=>$start,'to'=>$end]);
$context=stream_context_create(['http'=>['timeout'=>7,'header'=>"User-Agent: ShipAirWatch/1.0\r\n"]]);
$json=@file_get_contents($url,false,$context);
if($json===false){http_response_code(502);echo json_encode(['error'=>'Tide provider unavailable']);exit;}
$data=json_decode($json,true);
if(!is_array($data)){http_response_code(502);echo json_encode(['error'=>'Invalid tide data']);exit;}
echo json_encode(['station'=>'Saint John','predictions'=>$data],JSON_UNESCAPED_SLASHES);
