<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$path = $_GET['path'] ?? '';
if ($path === '' || strncmp($path, '/api/', 5) !== 0) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid path']);
    exit;
}

if (strpos($path, '/api/restart') === 0) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || ($_SERVER['HTTP_X_SHIPWATCH_RECOVERY'] ?? '') !== 'confirmed') {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'Recovery confirmation required']);
        exit;
    }
    $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
    $expected = 'http://' . ($_SERVER['HTTP_HOST'] ?? '');
    if ($origin !== '' && $origin !== $expected) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'Use the listening post recovery buttons']);
        exit;
    }
}
$url = 'http://192.168.2.29:8088' . $path;
$method = $_SERVER['REQUEST_METHOD'] === 'POST' ? 'POST' : 'GET';

$ctx = stream_context_create([
    'http' => [
        'method' => $method,
        'timeout' => 22,
        'ignore_errors' => true,
        'header' => "User-Agent: ShipWatch-PC-Radio\r\nX-ShipWatch-Recovery: " . (($_SERVER['HTTP_X_SHIPWATCH_RECOVERY'] ?? '') === 'confirmed' ? 'confirmed' : '') . "\r\n"
    ]
]);

$data = @file_get_contents($url, false, $ctx);
if ($data === false) {
    http_response_code(502);
    echo json_encode(['error' => 'radio service unavailable']);
    exit;
}

echo $data;
