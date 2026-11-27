#!/usr/bin/env python3
"""A small chat shell that streams a reply word by word."""
import sys
import termios
import time
import tty

REPLY = "Here is a long answer that arrives one word at a time so it can be interrupted".split()


def stream_reply():
    for word in REPLY:
        sys.stdout.write(word + " ")
        sys.stdout.flush()
        time.sleep(0.3)
    sys.stdout.write("\r\n")


def main():
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    while True:
        sys.stdout.write("> ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line or line.strip() == "quit":
            break
        stream_reply()
    termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
