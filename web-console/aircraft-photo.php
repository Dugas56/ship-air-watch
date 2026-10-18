<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: private, max-age=3600');

function aircraft_photo_reply(array $payload, int $status = 200): void
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

$registration = strtoupper(trim((string)($_GET['registration'] ?? '')));
$registration = preg_replace('/[^A-Z0-9-]/', '', $registration) ?? '';
$hex = strtoupper(preg_replace('/[^0-9A-F]/i', '', (string)($_GET['hex'] ?? '')) ?? '');
$icaoType = strtoupper(preg_replace('/[^A-Z0-9]/i', '', (string)($_GET['icaoType'] ?? '')) ?? '');
if (!preg_match('/^[A-Z0-9]{1,3}-?[A-Z0-9]{2,6}$/', $registration) || !preg_match('/^[0-9A-F]{6}$/', $hex) || strlen($icaoType) > 8) {
    aircraft_photo_reply(['ok' => false, 'error' => 'Invalid aircraft identity'], 400);
}

$cacheDir = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'shipwatch-aircraft-photo-cache';
$cacheFile = $cacheDir . DIRECTORY_SEPARATOR . hash('sha256', 'planespotters-v1|' . $hex . '|' . $registration) . '.json';
if (is_file($cacheFile) && (int)@filemtime($cacheFile) > time() - 21600) {
    $cached = json_decode((string)@file_get_contents($cacheFile), true);
    if (is_array($cached)) {
        aircraft_photo_reply($cached);
    }
}

$query = ['reg' => $registration];
if ($icaoType !== '') {
    $query['icaoType'] = $icaoType;
}
$url = 'https://api.planespotters.net/pub/photos/hex/' . rawurlencode($hex) . '?' . http_build_query($query);
$context = stream_context_create([
    'http' => [
        'timeout' => 6,
        'ignore_errors' => true,
        'header' => "User-Agent: ShipWatch/1.0 (+https://atlanticlink.ca/contact)\r\nAccept: application/json\r\n",
    ],
    'ssl' => ['verify_peer' => true, 'verify_peer_name' => true],
]);
$body = @file_get_contents($url, false, $context);
$data = $body === false ? null : json_decode($body, true);
$photo = null;
$candidate = $data['photos'][0] ?? null;
if (is_array($candidate)) {
    $image = (string)($candidate['thumbnail']['src'] ?? '');
    $page = (string)($candidate['link'] ?? '');
    $photographer = trim(strip_tags((string)($candidate['photographer'] ?? $candidate['user'] ?? '')));
    if (strpos($image, 'https://t.plnspttrs.net/') === 0 && strpos($page, 'https://www.planespotters.net/photo/') === 0 && $photographer !== '') {
        $photo = [
            'image' => $image,
            'page' => $page,
            'artist' => '© ' . substr($photographer, 0, 160),
            'license' => 'Planespotters.net thumbnail',
            'licenseUrl' => 'https://www.planespotters.net/legal/termsofuse',
        ];
    }
}

$result = ['ok' => true, 'registration' => $registration, 'photo' => $photo];
if (!is_dir($cacheDir)) {
    @mkdir($cacheDir, 0700, true);
}
if (is_dir($cacheDir) && is_writable($cacheDir)) {
    @file_put_contents($cacheFile, json_encode($result, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE), LOCK_EX);
}
aircraft_photo_reply($result);
