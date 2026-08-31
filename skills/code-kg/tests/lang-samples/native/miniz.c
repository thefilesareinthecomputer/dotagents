#include <stdio.h>
#include "miniz.h"

static int checksum(const char *data) {
    int sum = 0;
    while (*data) {
        sum += *data++;
    }
    return sum;
}

int main(int argc, char **argv) {
    struct Blob b = { "hello", 5 };
    printf("%d\n", checksum(b.data));
    return 0;
}
