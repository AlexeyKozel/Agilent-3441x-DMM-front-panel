CC ?= cc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -pedantic -O2

.PHONY: all test clean

all: test_host

test_host: mcu_core.c mcu_core.h test_host.c
	$(CC) $(CFLAGS) mcu_core.c test_host.c -o test_host

test: test_host
	./test_host

clean:
	$(RM) test_host
