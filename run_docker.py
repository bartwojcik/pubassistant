#!/usr/bin/env python
import subprocess

if __name__ == "__main__":
    try:
        subprocess.call('docker-compose up', shell=True)
    except KeyboardInterrupt:
        subprocess.call('docker-compose down', shell=True)
