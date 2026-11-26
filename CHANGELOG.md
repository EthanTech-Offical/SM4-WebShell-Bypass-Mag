# Changelog

## 1.6.3

- Removed the `op=eval` endpoint and the GUI "execute as PHP" action.
- The virtual terminal now warns when PHP code is pasted instead of sending it
  to the remote shell.

## 1.6.2

- Added WAF-looking decoy pages (`--decoy`, `--decoy-preset`, GUI selector).
- Decoy pages are bundled inside the Python package.

## 1.6.1

- Split remaining sensitive calls (`hex2bin`, `preg_replace`,
  `stream_socket_client`, OpenSSL) and obfuscated command-exec function names.
- Added `--decoy` support.

## 1.6.0

- Per-build polymorphism: random function/class/method/constant names,
  random request parameter, masked SM4 S-box.
- Removed `eval`, `base64_decode`, `$_POST`/`$_REQUEST`/`$_COOKIE`.
- Requests are parsed from `php://input`.

## 1.5.0

- Removed the tunnel feature.
- PHP-only payloads (JSP removed).

## 1.0.0

- First stable release: v2 envelope, GUI, file transfer, streaming terminal.
