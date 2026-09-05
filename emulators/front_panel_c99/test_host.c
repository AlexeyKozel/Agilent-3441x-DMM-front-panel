#include "mcu_core.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#ifdef NDEBUG
#error "The host regression harness requires enabled assertions"
#endif

typedef struct {
    fp_mcu_reply_word_t replies[300];
    size_t reply_count;
    bool srq_low;
} probe_t;

static void on_reply(void *user, fp_mcu_reply_word_t word)
{
    probe_t *probe = (probe_t *)user;
    assert(probe->reply_count < sizeof(probe->replies) / sizeof(probe->replies[0]));
    probe->replies[probe->reply_count++] = word;
}

static void on_srq(void *user, bool low)
{
    ((probe_t *)user)->srq_low = low;
}

static void clear_replies(probe_t *probe) { probe->reply_count = 0; }

static void send(fp_mcu_t *mcu, probe_t *probe, uint8_t byte, bool cmmd)
{
    (void)fp_mcu_receive(mcu, byte, cmmd);
    assert(probe->reply_count <= sizeof(probe->replies) / sizeof(probe->replies[0]));
}

static void expect_reply(probe_t *probe, const uint8_t *values, size_t count)
{
    size_t i;
    assert(probe->reply_count == count);
    for (i = 0; i < count; ++i) {
        assert(probe->replies[i].byte == values[i]);
        assert(!probe->replies[i].ninth_bit);
    }
}

static void test_startup_and_display(fp_mcu_t *mcu, probe_t *probe)
{
    static const uint8_t starts[] = {0, 0x95, 0x96, 0xFF};
    static const unsigned counts[] = {1, 2, 150, 255, 256};
    size_t i, s, c;
    fp_mcu_reset(mcu);
    assert(mcu->irq_enabled && mcu->srq_low && probe->srq_low);
    for (i = 0; i < FP_MCU_FRAMEBUFFER_BYTES; ++i) {
        assert(mcu->framebuffer[i] == 0xFF && mcu->stock_xram[i] == 0xFF);
    }
    for (i = 0x96; i < 0xAA; ++i) assert(mcu->stock_xram[i] == 0x82);
    for (i = 0xAA; i < FP_MCU_STOCK_XRAM_BYTES; ++i) assert(mcu->stock_xram[i] == 0);

    /* Empty dequeue raises SRQ; the default enabled gate makes the next
     * key lower it again without requiring command 0x38. */
    clear_replies(probe);
    send(mcu, probe, 0x15, false);
    assert(probe->reply_count == 1 && probe->replies[0].byte == 0xFF);
    assert(!mcu->srq_low && !probe->srq_low);
    assert(fp_mcu_enqueue_key(mcu, 0, true, true));
    assert(mcu->srq_low && probe->srq_low);

    for (s = 0; s < sizeof(starts) / sizeof(starts[0]); ++s) {
        for (c = 0; c < sizeof(counts) / sizeof(counts[0]); ++c) {
            fp_mcu_reset(mcu);
            clear_replies(probe);
            send(mcu, probe, 0x21, false);
            send(mcu, probe, (uint8_t)counts[c], false);
            send(mcu, probe, starts[s], false);
            for (i = 0; i < counts[c]; ++i) {
                unsigned address = starts[s] + (unsigned)i;
                uint8_t value = (uint8_t)(0xA5u + i * 17u);
                send(mcu, probe, value, false);
                assert(mcu->stock_xram[address] == value);
                if (address < FP_MCU_FRAMEBUFFER_BYTES) assert(mcu->framebuffer[address] == value);
                assert(mcu->last_stock_display_count == i + 1u);
                if (i + 1u < counts[c]) {
                    assert(mcu->state == 0 && probe->reply_count == 0);
                }
            }
            assert(mcu->state == 1 && probe->reply_count == 1);
            assert(probe->replies[0].byte == 1 && !probe->replies[0].ninth_bit);
        }
    }

    /* CMMD discards parser state, never the MOVX already performed. */
    for (c = 0; c < 2; ++c) {
        fp_mcu_reset(mcu);
        clear_replies(probe);
        send(mcu, probe, 0x21, false);
        send(mcu, probe, c == 0 ? 0 : 2, false);
        send(mcu, probe, 0x95, false);
        send(mcu, probe, 0xA5, false);
        assert(mcu->framebuffer[0x95] == 0xA5 && probe->reply_count == 0);
        send(mcu, probe, 0x05, true);
        assert(probe->reply_count == 1 && probe->replies[0].byte == 0);
        assert(mcu->framebuffer[0x95] == 0xA5 && mcu->stock_xram[0x95] == 0xA5);
        assert(mcu->last_stock_display_start == 0x95 && mcu->last_stock_display_count == 1);
    }
    fp_mcu_reset(mcu);
    assert(fp_mcu_set_cell(mcu, 0, 0));
    assert(mcu->framebuffer[0] == 0x3F && mcu->stock_xram[0] == 0x3F);
    assert(fp_mcu_set_cell(mcu, 599, 1));
    assert(mcu->framebuffer[149] == 0xFD && mcu->stock_xram[149] == 0xFD);
}

static void test_diagnostic_counter(fp_mcu_t *mcu, probe_t *probe)
{
    static const uint8_t raw[] = {0, 1, 2, 29, 30, 31, 255};
    size_t i;
    for (i = 0; i < sizeof(raw) / sizeof(raw[0]); ++i) {
        fp_mcu_reset(mcu);
        clear_replies(probe);
        fp_mcu_tick(mcu, 29); /* Disabled time must not change the phase. */
        send(mcu, probe, 0x36, false);
        send(mcu, probe, raw[i], false);
        assert(mcu->diagnostic_counter == raw[i]);
        fp_mcu_tick(mcu, 1);
        if (raw[i] == 0) {
            assert(mcu->diagnostic_counter == 0 && !mcu->diagnostic_key_traffic);
        } else if (raw[i] < 30) {
            assert(mcu->diagnostic_counter == raw[i] + 1u && mcu->fifo_count == 0);
        } else {
            assert(mcu->diagnostic_counter == 1 && mcu->fifo_count == 2);
            assert(mcu->key_fifo[0] == 0x40 && mcu->key_fifo[1] == 0);
            assert(mcu->diagnostic_key_id == 1);
        }
    }
    fp_mcu_reset(mcu);
    clear_replies(probe);
    fp_mcu_tick(mcu, 29);
    send(mcu, probe, 0x36, false);
    send(mcu, probe, 1, false);
    fp_mcu_tick(mcu, 29);
    assert(mcu->diagnostic_counter == 30 && mcu->fifo_count == 0);
    fp_mcu_tick(mcu, 1);
    assert(mcu->diagnostic_counter == 1 && mcu->fifo_count == 2);
    send(mcu, probe, 0x36, false);
    send(mcu, probe, 0, false);
    fp_mcu_tick(mcu, 100);
    assert(mcu->diagnostic_counter == 0 && mcu->fifo_count == 2);
    send(mcu, probe, 0x36, false);
    send(mcu, probe, 1, false);
    fp_mcu_tick(mcu, 29);
    assert(mcu->diagnostic_counter == 30 && mcu->fifo_count == 2);
    fp_mcu_tick(mcu, 31);
    assert(mcu->fifo_count == 4 && mcu->diagnostic_key_id == 3);
    assert(mcu->diagnostic_counter == 1); /* Generator advances even if FIFO is full. */
}

int main(void)
{
    fp_mcu_t mcu;
    probe_t probe;
    fp_mcu_platform_t platform;
    uint8_t expected[2];
    size_t i;

    memset(&probe, 0, sizeof(probe));
    memset(&platform, 0, sizeof(platform));
    platform.user = &probe;
    platform.reply = on_reply;
    platform.set_srq_low = on_srq;
    fp_mcu_init(&mcu, &platform);
    test_startup_and_display(&mcu, &probe);
    test_diagnostic_counter(&mcu, &probe);
    fp_mcu_reset(&mcu);
    assert(fp_mcu_status(&mcu) == 0x01 && fp_mcu_srq_low(&mcu));

    clear_replies(&probe);
    send(&mcu, &probe, 0x01, false);
    expected[0] = 0x00; expected[1] = 0x09;
    expect_reply(&probe, expected, 2);
    clear_replies(&probe);
    send(&mcu, &probe, 0x05, true);
    expected[0] = 0x01;
    expect_reply(&probe, expected, 1);

    /* CMMD aborts an incomplete payload and reports the old busy state. */
    clear_replies(&probe);
    send(&mcu, &probe, 0x12, false);
    send(&mcu, &probe, 0x05, true);
    expected[0] = 0x00;
    expect_reply(&probe, expected, 1);

    /* The stock count=0 path consumes exactly 256 bytes into bounded XRAM. */
    clear_replies(&probe);
    send(&mcu, &probe, 0x21, false);
    send(&mcu, &probe, 0x00, false);
    send(&mcu, &probe, 0xFF, false);
    for (i = 0; i < 256; ++i) send(&mcu, &probe, (uint8_t)i, false);
    expected[0] = 0x01;
    expect_reply(&probe, expected, 1);
    assert(mcu.last_stock_display_start == 0xFF && mcu.last_stock_display_count == 256);
    assert(mcu.stock_xram[0xFF] == 0 && mcu.stock_xram[0x1FE] == 0xFF);

    /* Four events are retained; the fifth is dropped. */
    assert(fp_mcu_enqueue_key(&mcu, 0, true, true));
    assert(fp_mcu_enqueue_key(&mcu, 1, true, false));
    assert(fp_mcu_enqueue_key(&mcu, 2, true, false));
    assert(fp_mcu_enqueue_key(&mcu, 3, true, false));
    assert(!fp_mcu_enqueue_key(&mcu, 4, true, false));
    assert(fp_mcu_fifo_occupancy(&mcu) == 4);
    clear_replies(&probe);
    send(&mcu, &probe, 0x38, false); send(&mcu, &probe, 1, false);
    expect_reply(&probe, expected, 1);
    assert(fp_mcu_srq_low(&mcu));

    assert(fp_mcu_raw_to_ppc_event(0x00) == 0x04);
    assert(fp_mcu_raw_to_ppc_event(0x0E) < 0);
    assert(fp_mcu_raw_to_ppc_event(0x3F) == 0x3F);
    assert(fp_mcu_encode_key_event(2, true, true) == 0xC2);
    assert(fp_mcu_set_cell(&mcu, 599, 3));
    { uint8_t value = 0; assert(fp_mcu_get_cell(&mcu, 599, &value) && value == 3); }
    assert(fp_mcu_sequence(5, NULL) == 0);

    puts("mcu_core host tests: OK");
    return 0;
}
