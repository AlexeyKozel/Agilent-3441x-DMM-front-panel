#include "mcu_core.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

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
