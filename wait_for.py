#!/usr/bin/env python

"""This is a workaround. See:
https://github.com/docker/docker/issues/21142
https://github.com/docker/compose/issues/374"""

import socket
import sys
import time

SLEEP_TIME = 0.5

if __name__ == '__main__':
    address = sys.argv[1]
    port = int(sys.argv[2])
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    not_opened = sock.connect_ex((address, port))
    while not_opened:
        time.sleep(SLEEP_TIME)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        not_opened = sock.connect_ex((address, port))
    sock.close()
