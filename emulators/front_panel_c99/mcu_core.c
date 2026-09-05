#include "mcu_core.h"

#include <string.h>

/* C99-compatible compile-time contracts.  Do not replace these with
 * _Static_assert: the core deliberately remains C99, not C11. */
typedef char fp_mcu_assert_uint8_is_octet[(UINT8_MAX == 0xFFu) ? 1 : -1];
typedef char fp_mcu_assert_uint16_holds_9bit[(UINT16_MAX >= 0x1FFu) ? 1 : -1];
typedef char fp_mcu_assert_framebuffer_cells[
    (FP_MCU_FRAMEBUFFER_BYTES * 4u == FP_MCU_CELL_COUNT) ? 1 : -1];
typedef char fp_mcu_assert_xram_zero_count_span[
    (FP_MCU_STOCK_XRAM_BYTES >= 0x200u) ? 1 : -1];
typedef char fp_mcu_assert_payload_zero_count_span[
    (FP_MCU_MAX_PAYLOAD >= 258u) ? 1 : -1];

static const fp_mcu_tone_reload_t TONE_RELOAD[85] = {
    {0x00,0x00},{0xD5,0x07},{0xC9,0x07},{0xBE,0x07},{0xB3,0x07},
    {0xA9,0x07},{0x9F,0x07},{0x96,0x07},{0x8E,0x07},{0x86,0x07},
    {0x7E,0x07},{0x77,0x07},{0x70,0x07},{0xD5,0x03},{0xC9,0x03},
    {0xBE,0x03},{0xB3,0x03},{0xA9,0x03},{0x9F,0x03},{0x96,0x03},
    {0x8E,0x03},{0x86,0x03},{0x7E,0x03},{0x77,0x03},{0x70,0x03},
    {0xD5,0x01},{0xC9,0x01},{0xBE,0x01},{0xB3,0x01},{0xA9,0x01},
    {0x9F,0x01},{0x96,0x01},{0x8E,0x01},{0x86,0x01},{0x7E,0x01},
    {0x77,0x01},{0x70,0x01},{0xD5,0x00},{0xC9,0x00},{0xBE,0x00},
    {0xB3,0x00},{0xA9,0x00},{0x9F,0x00},{0x96,0x00},{0x8E,0x00},
    {0x86,0x00},{0x7E,0x00},{0x77,0x00},{0x70,0x00},{0x6A,0x00},
    {0x64,0x00},{0x5F,0x00},{0x59,0x00},{0x54,0x00},{0x4F,0x00},
    {0x4B,0x00},{0x47,0x00},{0x43,0x00},{0x3F,0x00},{0x3B,0x00},
    {0x38,0x00},{0x35,0x00},{0x32,0x00},{0x2F,0x00},{0x2C,0x00},
    {0x2A,0x00},{0x27,0x00},{0x25,0x00},{0x23,0x00},{0x21,0x00},
    {0x1F,0x00},{0x1D,0x00},{0x1C,0x00},{0x1A,0x00},{0x19,0x00},
    {0x17,0x00},{0x16,0x00},{0x15,0x00},{0x13,0x00},{0x12,0x00},
    {0x11,0x00},{0x10,0x00},{0x0F,0x00},{0x0E,0x00},{0x0E,0x00}
};

static const fp_mcu_sound_pair_t SEQ1[13] = {
    {5,0x25},{5,0x26},{5,0x27},{5,0x28},{5,0x29},{5,0x2A},{5,0x2B},
    {5,0x2C},{5,0x2D},{5,0x2E},{5,0x2F},{5,0x30},{5,0x31}
};
static const fp_mcu_sound_pair_t SEQ2[8] = {
    {5,0x31},{5,0x33},{5,0x35},{5,0x36},{5,0x38},{5,0x3A},{5,0x3C},{5,0x3D}
};
static const fp_mcu_sound_pair_t SEQ3[24] = {
    {5,0x28},{3,0x28},{3,0x28},{9,0x28},{9,0x2F},{5,0x2D},{5,0x2C},{5,0x2A},
    {9,0x34},{9,0x2F},{5,0x2D},{5,0x2C},{5,0x2A},{9,0x34},{9,0x2F},{5,0x2D},
    {5,0x2C},{5,0x2D},{9,0x2A},{5,0x28},{5,0x28},{5,0x28},{0x11,0x28},{0,0}
};
static const fp_mcu_sound_pair_t SEQ4[31] = {
    {5,0x38},{5,0x38},{5,0x39},{5,0x3B},{5,0x3B},{5,0x39},{5,0x38},{5,0x36},
    {5,0x34},{5,0x34},{5,0x36},{9,0x38},{5,0x38},{5,0x36},{9,0x36},{5,0x38},
    {5,0x38},{5,0x39},{5,0x3B},{5,0x3B},{5,0x39},{5,0x38},{5,0x36},{5,0x34},
    {5,0x34},{5,0x36},{5,0x38},{9,0x36},{5,0x34},{9,0x34},{0,0}
};
static const fp_mcu_sound_pair_t SEQ5[37] = {
    {5,0x34},{9,0x3B},{5,0x38},{9,0x34},{5,0x33},{5,0x34},{5,0x36},{5,0x36},
    {5,0x33},{9,0x2F},{5,0x34},{9,0x3D},{5,0x3B},{5,0x39},{5,0x38},{5,0x36},
    {0x11,0x3B},{2,0x34},{2,0x36},{5,0x3B},{5,0x3B},{5,0x38},{5,0x34},{5,0x33},
    {5,0x34},{5,0x36},{5,0x36},{5,0x33},{9,0x2F},{5,0x34},{9,0x3D},{5,0x3B},
    {5,0x39},{5,0x38},{5,0x36},{0x11,0x34},{0,0}
};

static void set_srq(fp_mcu_t *mcu, bool low)
{
    if (mcu->srq_low == low) {
        return;
    }
    mcu->srq_low = low;
    if (mcu->platform.set_srq_low != NULL) {
        mcu->platform.set_srq_low(mcu->platform.user, low);
    }
}

static void update_srq_from_fifo(fp_mcu_t *mcu)
{
    set_srq(mcu, mcu->irq_enabled && (mcu->fifo_count != 0));
}

static size_t emit(fp_mcu_t *mcu, const uint8_t *bytes, size_t count)
{
    size_t i;
    if (mcu->platform.reply == NULL) {
        return count;
    }
    for (i = 0; i < count; ++i) {
        fp_mcu_reply_word_t word;
        word.byte = bytes[i];
        word.ninth_bit = false; /* stock ISR executes CLR TB8 */
        mcu->platform.reply(mcu->platform.user, word);
    }
    return count;
}

static size_t complete(fp_mcu_t *mcu, const uint8_t *reply, size_t count,
                       uint8_t state)
{
    size_t emitted = emit(mcu, reply, count);
    mcu->state = state;
    mcu->command_active = false;
    mcu->command = 0;
    mcu->payload_len = 0;
    mcu->expected_payload = 0;
    mcu->echo_mode = false;
    return emitted;
}

static size_t reject(fp_mcu_t *mcu)
{
    static const uint8_t reply[] = {0x81};
    return complete(mcu, reply, 1, 0x81);
}

static void notify_sound(fp_mcu_t *mcu, uint8_t kind, uint8_t duration,
                         uint8_t repeat, uint8_t tone)
{
    mcu->last_sound_kind = kind;
    mcu->last_duration_selector = duration;
    mcu->last_repeat_count = repeat;
    mcu->last_tone_index = tone;
    mcu->last_tone_reload = TONE_RELOAD[tone];
    if (mcu->platform.sound != NULL) {
        mcu->platform.sound(mcu->platform.user, kind, duration, repeat, tone,
                            mcu->last_tone_reload);
    }
}

static size_t handle_payload(fp_mcu_t *mcu)
{
    static const uint8_t ack[] = {0x01};
    uint8_t tone, duration;
    switch (mcu->command) {
    case 0x01: {
        static const uint8_t reply[] = {0x00, 0x09};
        return complete(mcu, reply, 2, 0x01);
    }
    case 0x03: {
        static const uint8_t reply[] = {0x1A};
        return complete(mcu, reply, 1, 0x01);
    }
    case 0x05:
        return complete(mcu, &mcu->status_previous, 1, 0x01);
    case 0x12:
        duration = mcu->payload[0];
        tone = mcu->payload[1];
        notify_sound(mcu, 1, duration < 3 ? duration : 2,
                     duration >= 3 ? (uint8_t)(duration - 3) : 0,
                     tone > 0x54 ? 0x54 : tone);
        return complete(mcu, ack, 1, 0x01);
    case 0x13:
        notify_sound(mcu, 2, 0, 0, 0);
        return complete(mcu, ack, 1, 0x01);
    case 0x14:
        notify_sound(mcu, 3, 0, 0, 0);
        return complete(mcu, ack, 1, 0x01);
    case 0x15:
        if (mcu->fifo_count != 0) {
            uint8_t event = mcu->key_fifo[mcu->fifo_read];
            mcu->fifo_read = (uint8_t)((mcu->fifo_read + 1u) % FP_MCU_KEY_FIFO_CAPACITY);
            --mcu->fifo_count;
            update_srq_from_fifo(mcu);
            return complete(mcu, &event, 1, 0x01);
        }
        set_srq(mcu, false);
        {
            static const uint8_t empty[] = {0xFF};
            return complete(mcu, empty, 1, 0x81);
        }
    case 0x21:
        /* Every data byte has already executed its stock MOVX store. */
        return complete(mcu, ack, 1, 0x01);
    case 0x31: {
        const fp_mcu_sound_pair_t *pairs = NULL;
        size_t n = fp_mcu_sequence(mcu->payload[0], &pairs);
        mcu->last_sequence_id = mcu->payload[0];
        mcu->last_sequence_count = n;
        /* IDs outside 1..5 are a defined no-op.  In particular, do not pass
         * (NULL, 0) to a platform callback that expects a real sequence. */
        if (n != 0u && mcu->platform.sound_sequence != NULL) {
            mcu->platform.sound_sequence(mcu->platform.user, mcu->payload[0], pairs, n);
        }
        return complete(mcu, ack, 1, 0x01);
    }
    case 0x32:
        mcu->break_detect_enabled = true;
        return complete(mcu, ack, 1, 0x01);
    case 0x33:
        mcu->break_detect_enabled = false;
        return complete(mcu, ack, 1, 0x01);
    case 0x36:
        mcu->diagnostic_counter = mcu->payload[0];
        mcu->diagnostic_key_traffic = mcu->diagnostic_counter != 0;
        return complete(mcu, ack, 1, 0x01);
    case 0x38:
        mcu->irq_enabled = mcu->payload[0] != 0;
        update_srq_from_fifo(mcu);
        return complete(mcu, ack, 1, 0x01);
    case 0x3A:
        mcu->fifo_read = mcu->fifo_write;
        mcu->fifo_count = 0;
        set_srq(mcu, false);
        return complete(mcu, ack, 1, 0x01);
    default:
        return reject(mcu);
    }
}

static size_t start_command(fp_mcu_t *mcu, uint8_t command)
{
    mcu->status_previous = mcu->state;
    mcu->state = 0x00;
    mcu->command = command;
    mcu->command_active = true;
    mcu->payload_len = 0;
    mcu->expected_payload = 0;
    mcu->echo_mode = false;
    switch (command) {
    case 0x01: case 0x03: case 0x05: case 0x13: case 0x14: case 0x15:
    case 0x32: case 0x33: case 0x3A:
        return handle_payload(mcu);
    case 0x12: case 0x38: case 0x36:
        mcu->expected_payload = 2; /* corrected below for one-byte commands */
        if (command != 0x12) {
            mcu->expected_payload = 1;
        }
        return 0;
    case 0x21:
        return 0;
    case 0x31:
        mcu->expected_payload = 1;
        return 0;
    case 0x34:
        mcu->echo_mode = true;
        return 0;
    default:
        return reject(mcu);
    }
}

void fp_mcu_init(fp_mcu_t *mcu, const fp_mcu_platform_t *platform)
{
    if (mcu == NULL) {
        return;
    }
    memset(mcu, 0, sizeof(*mcu));
    if (platform != NULL) {
        mcu->platform = *platform;
    }
    fp_mcu_reset(mcu);
}

void fp_mcu_reset(fp_mcu_t *mcu)
{
    fp_mcu_platform_t platform;
    if (mcu == NULL) {
        return;
    }
    platform = mcu->platform;
    memset(mcu, 0, sizeof(*mcu));
    mcu->platform = platform;
    /* Ordinary application startup (P1.4 high): CODE:04F8 initializer
     * table runs after the RAM clear; 0EED initializes debounce XDATA. */
    memset(mcu->framebuffer, 0xFF, sizeof(mcu->framebuffer));
    memset(mcu->stock_xram, 0xFF, FP_MCU_FRAMEBUFFER_BYTES);
    memset(&mcu->stock_xram[0x96], 0x82, 20u);
    mcu->state = 0x01;
    mcu->irq_enabled = true; /* table record at CODE:05B9 sets IRAM36=1 */
    mcu->srq_low = true; /* reset startup path clears P1.6 */
    if (mcu->platform.set_srq_low != NULL) {
        mcu->platform.set_srq_low(mcu->platform.user, true);
    }
}

size_t fp_mcu_receive(fp_mcu_t *mcu, uint8_t byte, bool ninth_bit)
{
    uint8_t count;
    if (mcu == NULL) {
        return 0;
    }
    if (ninth_bit) {
        return start_command(mcu, byte);
    }
    if (mcu->echo_mode) {
        return emit(mcu, &byte, 1);
    }
    if (!mcu->command_active) {
        return start_command(mcu, byte);
    }
    if (mcu->payload_len >= FP_MCU_MAX_PAYLOAD) {
        return reject(mcu);
    }
    mcu->payload[mcu->payload_len++] = byte;
    if (mcu->command == 0x21 && mcu->payload_len == 1) {
        count = byte; /* count byte; zero means 256 data bytes */
        mcu->expected_payload = count == 0 ? 258u : (uint16_t)count + 2u;
    }
    if (mcu->command == 0x21 && mcu->payload_len == 2) {
        mcu->last_stock_display_start = byte;
        mcu->last_stock_display_count = 0;
    }
    if (mcu->command == 0x21 && mcu->payload_len > 2) {
        uint16_t address = (uint16_t)mcu->payload[1] + mcu->payload_len - 3u;
        /* CODE:067B..067E stores before decrementing the count.  Neither
         * nonzero counts nor framebuffer-crossing spans have a guard.
         * The largest reachable address is 0xFF + 255 = 0x01FE. */
        mcu->stock_xram[address] = byte;
        if (address < FP_MCU_FRAMEBUFFER_BYTES) {
            mcu->framebuffer[address] = byte;
        }
        mcu->last_stock_display_count = mcu->payload_len - 2u;
    }
    if (mcu->expected_payload != 0 && mcu->payload_len >= mcu->expected_payload) {
        return handle_payload(mcu);
    }
    return 0;
}

size_t fp_mcu_receive_word(fp_mcu_t *mcu, uint16_t word)
{
    if (word > 0x1FFu) {
        return 0;
    }
    return fp_mcu_receive(mcu, (uint8_t)word, (word & 0x100u) != 0);
}

void fp_mcu_tick(fp_mcu_t *mcu, uint32_t iterations)
{
    uint32_t i;
    if (mcu == NULL) {
        return;
    }
    for (i = 0; i < iterations; ++i) {
        mcu->main_loop_count++;
        if (mcu->diagnostic_counter != 0u) {
            uint8_t previous = mcu->diagnostic_counter;
            mcu->diagnostic_counter = (uint8_t)(previous + 1u);
            /* 0A74..0A84 compares the old byte, independent of disabled
             * iterations; even 0xFF generates a pair and then resets to 1. */
            if (previous >= 30u) {
                uint8_t key = (uint8_t)(mcu->diagnostic_key_id % 20u);
                fp_mcu_enqueue_key(mcu, key, true, false);
                fp_mcu_enqueue_key(mcu, key, false, false);
                mcu->diagnostic_key_id = (uint8_t)((mcu->diagnostic_key_id + 1u) % 20u);
                mcu->diagnostic_counter = 1;
            }
        }
        mcu->diagnostic_key_traffic = mcu->diagnostic_counter != 0u;
    }
}

uint8_t fp_mcu_status(const fp_mcu_t *mcu) { return mcu == NULL ? 0 : mcu->state; }
bool fp_mcu_srq_low(const fp_mcu_t *mcu) { return mcu != NULL && mcu->srq_low; }
bool fp_mcu_irq_enabled(const fp_mcu_t *mcu) { return mcu != NULL && mcu->irq_enabled; }
bool fp_mcu_echo_mode(const fp_mcu_t *mcu) { return mcu != NULL && mcu->echo_mode; }

size_t fp_mcu_fifo_occupancy(const fp_mcu_t *mcu)
{
    if (mcu == NULL) return 0;
    return mcu->fifo_count;
}

bool fp_mcu_enqueue_event(fp_mcu_t *mcu, uint8_t event)
{
    if (mcu == NULL) return false;
    if (mcu->fifo_count >= FP_MCU_KEY_FIFO_CAPACITY) return false;
    mcu->key_fifo[mcu->fifo_write] = event;
    mcu->fifo_write = (uint8_t)((mcu->fifo_write + 1u) % FP_MCU_KEY_FIFO_CAPACITY);
    ++mcu->fifo_count;
    if (mcu->irq_enabled) update_srq_from_fifo(mcu);
    return true;
}

bool fp_mcu_enqueue_key(fp_mcu_t *mcu, uint8_t raw_id, bool pressed,
                        bool startup_held)
{
    return fp_mcu_enqueue_event(mcu, fp_mcu_encode_key_event(raw_id, pressed, startup_held));
}

bool fp_mcu_set_cell(fp_mcu_t *mcu, size_t index, uint8_t value)
{
    size_t byte_index;
    uint8_t shift;
    if (mcu == NULL || index >= FP_MCU_CELL_COUNT || value > 3) return false;
    byte_index = index >> 2;
    shift = (uint8_t)(6u - 2u * (index & 3u));
    mcu->framebuffer[byte_index] = (uint8_t)((mcu->framebuffer[byte_index] &
        (uint8_t)~(3u << shift)) | (uint8_t)(value << shift));
    mcu->stock_xram[byte_index] = mcu->framebuffer[byte_index];
    return true;
}

bool fp_mcu_get_cell(const fp_mcu_t *mcu, size_t index, uint8_t *value)
{
    size_t byte_index;
    uint8_t shift;
    if (mcu == NULL || value == NULL || index >= FP_MCU_CELL_COUNT) return false;
    byte_index = index >> 2;
    shift = (uint8_t)(6u - 2u * (index & 3u));
    *value = (uint8_t)((mcu->framebuffer[byte_index] >> shift) & 3u);
    return true;
}

bool fp_mcu_character_cell(const char *row, uint8_t position,
                           uint8_t segment, uint16_t *cell)
{
    uint8_t limit;
    uint16_t base;
    if (row == NULL || cell == NULL || segment >= 17u) return false;
    if (strcmp(row, "main") == 0) { limit = 12; base = 5; }
    else if (strcmp(row, "secondary") == 0) { limit = 18; base = 245; }
    else return false;
    if (position >= limit) return false;
    *cell = (uint16_t)(base + 40u * (position / 2u) + (position & 1u) + 2u * segment);
    return true;
}

int fp_mcu_raw_to_ppc_event(uint8_t raw_id)
{
    static const uint8_t map[21] = {
        0x04,0x06,0x1A,0x10,0x0E,0x08,0x0B,0x15,0x11,0x0D,0x05,
        0x13,0x0C,0x0F,0x00,0x09,0x19,0x0A,0x00,0x00,0x3F
    };
    if (raw_id == 0x3F) return 0x3F;
    if (raw_id > 0x14 || map[raw_id] == 0) return -1;
    return map[raw_id];
}

uint8_t fp_mcu_encode_key_event(uint8_t raw_id, bool pressed,
                                bool startup_held)
{
    return (uint8_t)((raw_id & 0x3Fu) | (pressed ? 0x40u : 0u) |
                     ((startup_held && pressed) ? 0x80u : 0u));
}

const fp_mcu_tone_reload_t *fp_mcu_tone_reload(uint8_t index)
{
    return index <= 0x54 ? &TONE_RELOAD[index] : NULL;
}

size_t fp_mcu_sequence(size_t sequence_id, const fp_mcu_sound_pair_t **pairs)
{
    static const fp_mcu_sound_pair_t *const tables[] = {NULL, SEQ1, SEQ2, SEQ3, SEQ4, SEQ5};
    static const size_t counts[] = {0, 13, 8, 24, 31, 37};
    if (pairs == NULL || sequence_id > 5) return 0;
    *pairs = tables[sequence_id];
    return counts[sequence_id];
}
