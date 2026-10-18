<?php
set_time_limit(0);
header('Content-Type: audio/mpeg');
header('Cache-Control: no-store');
header('X-Accel-Buffering: no');

$url = 'http://192.168.2.29:8088/air.mp3?x=' . time();
$fp = @fopen($url, 'rb');
if (!$fp) {
    http_response_code(502);
    exit;
}
while (!feof($fp)) {
    echo fread($fp, 8192);
    @ob_flush();
    flush();
}
fclose($fp);
