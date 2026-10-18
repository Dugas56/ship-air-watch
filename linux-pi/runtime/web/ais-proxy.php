<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');

$url = 'http://192.168.2.29:8100/api/ships_array.json';
$ctx = stream_context_create([
    'http' => [
        'timeout' => 3,
        'ignore_errors' => true,
        'header' => "User-Agent: ShipWatch-PC-Map\r\n"
    ]
]);

$data = @file_get_contents($url, false, $ctx);
if ($data === false) {
    http_response_code(502);
    echo json_encode(['ok' => false, 'error' => 'AIS feed unavailable']);
    exit;
}

echo $data;
