<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function cachedText(string $key, string $url, int $ttl): array {
    $path = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'shipwatch-' . $key . '.cache';
    $retryPath = $path . '.retry';
    if (is_file($path) && time() - (int)filemtime($path) < $ttl) {
        return ['data' => (string)file_get_contents($path), 'retrieved_at' => gmdate('c', (int)filemtime($path)), 'stale' => false];
    }
    if (is_file($retryPath) && time() < (int)file_get_contents($retryPath) && is_file($path)) {
        return ['data' => (string)file_get_contents($path), 'retrieved_at' => gmdate('c', (int)filemtime($path)), 'stale' => true];
    }
    $context = stream_context_create(['http' => ['timeout' => 12, 'ignore_errors' => true, 'header' => "User-Agent: ShipWatch-ISS-preview/1.0\r\n"]]);
    $raw = @file_get_contents($url, false, $context);
    $status = $http_response_header[0] ?? '';
    if (is_string($raw) && $raw !== '' && str_contains($status, '200')) {
        @file_put_contents($path, $raw, LOCK_EX);
        @unlink($retryPath);
        return ['data' => $raw, 'retrieved_at' => gmdate('c'), 'stale' => false];
    }
    @file_put_contents($retryPath, (string)(time() + min($ttl, 3600)), LOCK_EX);
    if (is_file($path)) {
        return ['data' => (string)file_get_contents($path), 'retrieved_at' => gmdate('c', (int)filemtime($path)), 'stale' => true];
    }
    throw new RuntimeException('Upstream data is unavailable and no cached record exists.');
}
function cachedJson(string $key, string $url, int $ttl): array {
    $path = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'shipwatch-' . $key . '.json';
    if (is_file($path) && time() - (int)filemtime($path) < $ttl) {
        $data = json_decode((string)file_get_contents($path), true);
        if (is_array($data)) return ['data' => $data, 'retrieved_at' => gmdate('c', (int)filemtime($path)), 'stale' => false];
    }
    $response = cachedText($key . '-raw', $url, $ttl);
    $data = json_decode($response['data'], true);
    if (!is_array($data)) throw new RuntimeException('Orbit service returned invalid JSON.');
    if (!$response['stale']) @file_put_contents($path, json_encode($data, JSON_UNESCAPED_SLASHES), LOCK_EX);
    return ['data' => $data, 'retrieved_at' => $response['retrieved_at'], 'stale' => $response['stale']];
}

try {
    $orbit = cachedJson('iss-omm', 'https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=JSON', 7200);
    $orbitalRecord = $orbit['data'];
    if (array_is_list($orbitalRecord)) $orbitalRecord = $orbitalRecord[0] ?? null;
    if (!is_array($orbitalRecord) || (int)($orbitalRecord['NORAD_CAT_ID'] ?? 0) !== 25544) throw new RuntimeException('ISS orbital record is invalid.');
    $ariss = cachedText('ariss-status', 'https://www.ariss.org/current-status-of-iss-stations.html', 21600);
    $html = $ariss['data'];
    $body = preg_replace('~<(style|script|noscript)[^>]*>.*?</\1>~is', ' ', $html) ?? $html;
    $decoded = html_entity_decode(strip_tags($body), ENT_QUOTES | ENT_HTML5, 'UTF-8');
    $decoded = preg_replace('/[\x{00A0}\x{202F}\x{200B}\x{FEFF}]/u', ' ', $decoded) ?? $decoded;
    $plain = trim(preg_replace('/\s+/u', ' ', $decoded) ?? $decoded);
    $statusText = $plain;
    if (preg_match('/ISS Ham Radio Status(.{0,2200}?)(?:About|$)/i', $plain, $section)) $statusText = trim($section[1]);
    $frequencies = [];
    if (preg_match_all('/\b(\d{3,4}\.\d{2,3}\s*MHz)\s+down\b/i', $plain, $matches)) {
        foreach ($matches[1] as $frequency) $frequencies[] = $frequency . ' downlink';
    }
    if (preg_match_all('/APRS.{0,180}?([0-9]{3,4}\.[0-9]{2,3})/is', $plain, $matches)) {
        foreach ($matches[1] as $frequency) $frequencies[] = $frequency . ' MHz APRS';
    }
    $reportedDate = null;
    if (preg_match('/Status as of\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})/iu', $plain, $dateMatch)) $reportedDate = $dateMatch[1];
    echo json_encode([
        'orbital_record' => $orbitalRecord, 'retrieved_at' => $orbit['retrieved_at'], 'stale' => $orbit['stale'],
        'location_configured' => true, 'latitude' => 45.2733, 'longitude' => -66.0633, 'time_zone' => 'America/Halifax',
        'radio_status' => ['frequencies' => array_values(array_unique($frequencies)), 'reported_date' => $reportedDate, 'source' => 'ARISS Current Status of ISS Stations', 'url' => 'https://www.ariss.org/current-status-of-iss-stations.html', 'retrieved_at' => $ariss['retrieved_at'], 'stale' => $ariss['stale'], 'excerpt' => substr($statusText, 0, 1100)]
    ], JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
} catch (Throwable $error) {
    http_response_code(503);
    echo json_encode(['error' => 'ISS orbit/status feed unavailable', 'detail' => $error->getMessage()]);
}
