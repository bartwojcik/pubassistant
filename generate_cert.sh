#/bin/sh
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout cert.key.pem -out cert.pem
