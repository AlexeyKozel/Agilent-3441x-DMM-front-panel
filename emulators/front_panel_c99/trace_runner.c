#include "mcu_core.h"

#include <stdio.h>

typedef struct {
    fp_mcu_reply_word_t replies[300];
    size_t count;
} trace_probe_t;

static void collect_reply(void *user, fp_mcu_reply_word_t word)
{
    trace_probe_t *probe = (trace_probe_t *)user;
    if (probe->count < sizeof(probe->replies) / sizeof(probe->replies[0])) {
        probe->replies[probe->count++] = word;
    }
}

int main(void)
{
    fp_mcu_t mcu;
    fp_mcu_platform_t platform = {0};
    trace_probe_t probe = {0};
    unsigned int word;
    platform.user = &probe;
    platform.reply = collect_reply;
    fp_mcu_init(&mcu, &platform);
    while (scanf("%x", &word) == 1) {
        size_t i;
        probe.count = 0;
        if (word > 0x1FFu) return 2;
        (void)fp_mcu_receive_word(&mcu, (uint16_t)word);
        printf("%02X %u %u", fp_mcu_status(&mcu),
               fp_mcu_srq_low(&mcu) ? 1u : 0u, (unsigned)probe.count);
        for (i = 0; i < probe.count; ++i) {
            printf(" %02X:%u", probe.replies[i].byte,
                   probe.replies[i].ninth_bit ? 1u : 0u);
        }
        putchar('\n');
    }
    return 0;
}
