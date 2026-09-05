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

static void print_bytes(const uint8_t *bytes, size_t count)
{
    size_t i;
    putchar('"');
    for (i = 0; i < count; ++i) printf("%02x", bytes[i]);
    putchar('"');
}

static void snapshot(const fp_mcu_t *mcu, const trace_probe_t *probe)
{
    size_t i;
    printf("{\"status\":%u,\"srq_low\":%u,\"irq_enabled\":%u,"
           "\"echo_mode\":%u,\"break_detect_enabled\":%u,"
           "\"diagnostic_counter\":%u,\"diagnostic_key_traffic\":%u,"
           "\"diagnostic_key_id\":%u,\"main_loop_count\":%lu,"
           "\"last_stock_display_write\":[%u,%u],\"replies\":[",
           (unsigned)mcu->state, mcu->srq_low ? 1u : 0u,
           mcu->irq_enabled ? 1u : 0u, mcu->echo_mode ? 1u : 0u,
           mcu->break_detect_enabled ? 1u : 0u,
           (unsigned)mcu->diagnostic_counter,
           mcu->diagnostic_key_traffic ? 1u : 0u,
           (unsigned)mcu->diagnostic_key_id, (unsigned long)mcu->main_loop_count,
           (unsigned)mcu->last_stock_display_start,
           (unsigned)mcu->last_stock_display_count);
    for (i = 0; i < probe->count; ++i) {
        printf("%s[%u,%u]", i == 0 ? "" : ",",
               (unsigned)probe->replies[i].byte,
               probe->replies[i].ninth_bit ? 1u : 0u);
    }
    printf("],\"key_fifo\":[");
    for (i = 0; i < mcu->fifo_count; ++i) {
        printf("%s%u", i == 0 ? "" : ",",
               (unsigned)mcu->key_fifo[(mcu->fifo_read + i) % FP_MCU_KEY_FIFO_CAPACITY]);
    }
    printf("],\"framebuffer\":");
    print_bytes(mcu->framebuffer, FP_MCU_FRAMEBUFFER_BYTES);
    printf(",\"stock_xram\":");
    print_bytes(mcu->stock_xram, FP_MCU_STOCK_XRAM_BYTES);
    puts("}");
}

int main(void)
{
    fp_mcu_t mcu;
    fp_mcu_platform_t platform = {0};
    trace_probe_t probe = {0};
    char operation;
    unsigned int argument, value;
    platform.user = &probe;
    platform.reply = collect_reply;
    fp_mcu_init(&mcu, &platform);
    /* One operation per line: W hex-word, T decimal-ticks, K hex-event,
     * C decimal-cell decimal-value, or R (reset).  Emit complete JSON state
     * after every operation, including partial display stores. */
    while (scanf(" %c", &operation) == 1) {
        probe.count = 0;
        switch (operation) {
        case 'W':
            if (scanf("%x", &argument) != 1 || argument > 0x1FFu) return 2;
            (void)fp_mcu_receive_word(&mcu, (uint16_t)argument);
            break;
        case 'T':
            if (scanf("%u", &argument) != 1) return 2;
            fp_mcu_tick(&mcu, argument);
            break;
        case 'K':
            if (scanf("%x", &argument) != 1 || argument > 0xFFu) return 2;
            (void)fp_mcu_enqueue_event(&mcu, (uint8_t)argument);
            break;
        case 'C':
            if (scanf("%u %u", &argument, &value) != 2 || value > 3u) return 2;
            if (!fp_mcu_set_cell(&mcu, argument, (uint8_t)value)) return 2;
            break;
        case 'R':
            fp_mcu_reset(&mcu);
            break;
        default:
            return 2;
        }
        snapshot(&mcu, &probe);
    }
    return 0;
}
