<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: private, max-age=300');

function boat_lookup_reply(array $payload, int $status = 200): void
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function boat_lookup_get(string $url): ?array
{
    $context = stream_context_create([
        'http' => [
            'timeout' => 5,
            'ignore_errors' => true,
            'header' => "User-Agent: ShipWatchBoatLookup/1.0\r\nAccept: application/json\r\n",
        ],
        'ssl' => ['verify_peer' => true, 'verify_peer_name' => true],
    ]);
    $body = @file_get_contents($url, false, $context);
    if ($body === false) {
        return null;
    }
    $json = json_decode($body, true);
    return is_array($json) ? $json : null;
}

function boat_lookup_plain($value): string
{
    return trim(html_entity_decode(strip_tags((string)$value), ENT_QUOTES | ENT_HTML5, 'UTF-8'));
}

function boat_lookup_normalize(string $value): string
{
    $value = strtolower(boat_lookup_plain($value));
    return trim((string)preg_replace('/[^a-z0-9]+/', ' ', $value));
}

$mmsi = preg_replace('/\D/', '', (string)($_GET['mmsi'] ?? ''));
$imo = preg_replace('/\D/', '', (string)($_GET['imo'] ?? ''));
$name = trim((string)($_GET['name'] ?? ''));
if (!preg_match('/^\d{9}$/', $mmsi) || strlen($name) > 80 || ($imo !== '' && !preg_match('/^\d{7}$/', $imo))) {
    boat_lookup_reply(['ok' => false, 'error' => 'Invalid vessel identity'], 400);
}
if (strlen($name) < 2) {
    boat_lookup_reply(['ok' => true, 'photo' => null]);
}

// ShipSpotting's own generated embed uses these small thumbnails for third-party
// display. Keep the listing link and photographer credit beside every image.
$shipSpottingPhotos = [
    'mmsi:373611000' => ['2160077', 'Sam Draye', 'Century Royal'],
    'imo:9614385' => ['2160077', 'Sam Draye', 'Century Royal'],
    'mmsi:316023718' => ['3640367', 'Marc Pingoud', 'Captain A.G. Soppitt'],
    'imo:9644976' => ['3640367', 'Marc Pingoud', 'Captain A.G. Soppitt'],
    'mmsi:316022239' => ['2724357', 'andrecas', 'Captain E.T. Rogers'],
    'imo:9644964' => ['2724357', 'andrecas', 'Captain E.T. Rogers'],
    'mmsi:316016449' => ['817076', 'Kyle Larabee', 'Peninsula Princess'],
    'imo:8871015' => ['817076', 'Kyle Larabee', 'Peninsula Princess'],
    'imo:8871015' => ['817076', 'Kyle Larabee', 'Peninsula Princess'],
    'mmsi:316013808' => ['3073061', 'GWR52', 'Atlantic Bear'],
    'mmsi:316012539' => ['606007', 'mud_shark8', 'Atlantic Beaver'],
    'mmsi:316006025' => ['3756157', 'Viktor', 'Atlantic Cedar'],
    'mmsi:316163000' => ['3535781', 'l.meyden', 'Atlantic Hemlock'],
    'mmsi:316013045' => ['880653', 'K. Watson', 'Spitfire III'],
    'imo:9451147' => ['3073061', 'GWR52', 'Atlantic Bear'],
    'imo:9451123' => ['606007', 'mud_shark8', 'Atlantic Beaver'],
    'imo:9324928' => ['3756157', 'Viktor', 'Atlantic Cedar'],
    'imo:9127588' => ['3535781', 'l.meyden', 'Atlantic Hemlock'],
    'imo:9451135' => ['880653', 'K. Watson', 'Spitfire III'],
];
$curatedCommonsPhotos = [
    '310867000' => [
        'imo' => '9228186',
        'name' => 'SAPPHIRE PRINCESS',
        'image' => 'https://thumb.wikimedia.org/wikipedia/commons/thumb/9/97/Sapphire_Princess_%283495253438%29.jpg/960px-Sapphire_Princess_%283495253438%29.jpg',
        'page' => 'https://commons.wikimedia.org/wiki/File:Sapphire_Princess_(3495253438).jpg',
        'artist' => 'Photo © Damian Gadal',
        'license' => 'CC BY 2.0',
        'licenseUrl' => 'https://creativecommons.org/licenses/by/2.0',
    ],
];
$curatedCommonsPhoto = $curatedCommonsPhotos[$mmsi] ?? null;
if ($curatedCommonsPhoto !== null && $imo === $curatedCommonsPhoto['imo'] && boat_lookup_normalize($name) === boat_lookup_normalize($curatedCommonsPhoto['name'])) {
    boat_lookup_reply(['ok' => true, 'photo' => $curatedCommonsPhoto]);
}
$curatedPhoto = $shipSpottingPhotos['mmsi:' . $mmsi] ?? ($imo !== '' ? ($shipSpottingPhotos['imo:' . $imo] ?? null) : null);
if ($curatedPhoto !== null) {
    [$photoId, $photographer, $verifiedName] = $curatedPhoto;
    $photo = [
        'image' => 'https://www.shipspotting.com/photos/small/' . implode('/', array_reverse(str_split(substr($photoId, -3)))) . '/' . $photoId . '.jpg?cb=0',
        'page' => 'https://www.shipspotting.com/photos/' . $photoId,
        'artist' => 'Photo © ' . $photographer,
        'license' => 'ShipSpotting thumbnail',
        'licenseUrl' => 'https://www.shipspotting.com/about/terms',
        'vessel' => $verifiedName,
    ];
    boat_lookup_reply(['ok' => true, 'photo' => $photo]);
}

$cacheDir = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'shipwatch-boat-lookup-cache';
$cacheFile = $cacheDir . DIRECTORY_SEPARATOR . hash('sha256', 'commons-v3|' . $mmsi . '|' . $imo . '|' . boat_lookup_normalize($name)) . '.json';
if (is_file($cacheFile) && (int)@filemtime($cacheFile) > time() - 86400) {
    $cached = json_decode((string)@file_get_contents($cacheFile), true);
    if (is_array($cached)) {
        boat_lookup_reply($cached);
    }
}

$search = '"' . $name . '"' . ($imo !== '' ? ' ' . $imo : '');
$searchUrl = 'https://commons.wikimedia.org/w/api.php?' . http_build_query([
    'action' => 'query', 'generator' => 'search', 'gsrnamespace' => 6, 'gsrsearch' => $search,
    'gsrlimit' => 5, 'prop' => 'imageinfo', 'iiprop' => 'url|mime|extmetadata', 'iiurlwidth' => 640,
    'format' => 'json', 'formatversion' => 2,
]);
$searchData = boat_lookup_get($searchUrl);
$photo = null;
$expectedName = boat_lookup_normalize($name);
if (isset($searchData['query']['pages']) && is_array($searchData['query']['pages'])) {
    foreach ($searchData['query']['pages'] as $candidate) {
        $title = (string)($candidate['title'] ?? '');
        if (stripos($title, 'File:') !== 0) {
            continue;
        }
        $info = $candidate['imageinfo'][0] ?? [];
        $metadata = $info['extmetadata'] ?? [];
        $description = boat_lookup_plain($metadata['ImageDescription']['value'] ?? '');
        $identityText = boat_lookup_normalize($title . ' ' . $description);
        $nameMatches = strpos($identityText, $expectedName) !== false;
        $imoMatches = $imo !== '' && strpos($identityText, $imo) !== false;
        if (!$nameMatches || ($imo !== '' && !$imoMatches)) {
            continue;
        }
        $image = (string)($info['thumburl'] ?? $info['url'] ?? '');
        $page = 'https://commons.wikimedia.org/wiki/' . rawurlencode(str_replace(' ', '_', $title));
        if ((strpos($image, 'https://upload.wikimedia.org/') !== 0 && strpos($image, 'https://thumb.wikimedia.org/') !== 0) || empty($info['mime']) || strpos((string)$info['mime'], 'image/') !== 0) {
            continue;
        }
        $license = boat_lookup_plain($metadata['LicenseShortName']['value'] ?? '');
        $licenseUrl = (string)($metadata['LicenseUrl']['value'] ?? '');
        $artist = boat_lookup_plain($metadata['Artist']['value'] ?? '');
        $photo = [
            'image' => $image,
            'page' => $page,
            'artist' => substr($artist, 0, 180),
            'license' => substr($license, 0, 80),
            'licenseUrl' => strpos($licenseUrl, 'https://') === 0 ? $licenseUrl : '',
        ];
        break;
    }
}

$result = ['ok' => true, 'photo' => $photo];
if (!is_dir($cacheDir)) {
    @mkdir($cacheDir, 0700, true);
}
if (is_dir($cacheDir) && is_writable($cacheDir)) {
    @file_put_contents($cacheFile, json_encode($result, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE), LOCK_EX);
}
boat_lookup_reply($result);
