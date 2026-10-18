<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$host = getenv('SHIPWATCH_PI_HOST') ?: '192.168.2.29';
if (!preg_match('/^[a-zA-Z0-9.:-]+$/', $host)) {
    http_response_code(500);
    echo json_encode(['error' => 'Aircraft receiver host is not configured']);
    exit;
}

$context = stream_context_create([
    'http' => [
        'method' => 'GET',
        'timeout' => 5,
        'ignore_errors' => true,
        'header' => "Accept: application/json\r\nUser-Agent: ShipWatch-Air-Lookup\r\n",
    ],
]);
$url = 'http://' . $host . '/tar1090/data/aircraft.json';
$data = @file_get_contents($url, false, $context, 0, 2 * 1024 * 1024);
if ($data === false) {
    http_response_code(502);
    echo json_encode(['error' => 'Aircraft receiver data is unavailable']);
    exit;
}

$feed = json_decode($data, true);
if (!is_array($feed) || !is_array($feed['aircraft'] ?? null)) {
    http_response_code(502);
    echo json_encode(['error' => 'Aircraft receiver returned invalid data']);
    exit;
}

echo json_encode([
    'now' => $feed['now'] ?? null,
    'messages' => $feed['messages'] ?? null,
    'aircraft' => $feed['aircraft'],
], JSON_UNESCAPED_SLASHES);
