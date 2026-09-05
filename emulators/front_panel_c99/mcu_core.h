#ifndef FP_MCU_CORE_H
#define FP_MCU_CORE_H

/*
 * Target-neutral C99 core for the 34410A/34411A front-panel runtime.
 *
 * This header deliberately contains no UART/GPIO/display/HAL types.  The
 * platform only receives logical reply words and side-effect notifications.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FP_MCU_FRAMEBUFFER_BYTES 150u
#define FP_MCU_CELL_COUNT 600u
#define FP_MCU_KEY_FIFO_CAPACITY 4u
#define FP_MCU_STOCK_XRAM_BYTES 0x200u
#define FP_MCU_MAX_PAYLOAD 258u /* 0x21 count=0: count + start + 256 data */
#define FP_MCU_REVISION 0x0009u
#define FP_MCU_PANEL_ID 0x1Au

typedef struct {
    uint8_t byte;
    bool ninth_bit;
} fp_mcu_reply_word_t;

typedef struct {
    uint8_t duration_selector;
    uint8_t tone_index;
} fp_mcu_sound_pair_t;

typedef struct {
    uint8_t reload_hi;
    uint8_t reload_lo;
} fp_mcu_tone_reload_t;

typedef struct {
    void *user;
    void (*reply)(void *user, fp_mcu_reply_word_t word);
    void (*set_srq_low)(void *user, bool low);
    void (*sound)(void *user, uint8_t kind, uint8_t duration_selector,
                  uint8_t repeat_count, uint8_t tone_index,
                  fp_mcu_tone_reload_t reload);
    void (*sound_sequence)(void *user, uint8_t sequence_id,
                           const fp_mcu_sound_pair_t *pairs, size_t count);
} fp_mcu_platform_t;

typedef struct {
    fp_mcu_platform_t platform;
    uint8_t framebuffer[FP_MCU_FRAMEBUFFER_BYTES];
    uint8_t stock_xram[FP_MCU_STOCK_XRAM_BYTES];
    uint8_t key_fifo[FP_MCU_KEY_FIFO_CAPACITY];
    uint8_t fifo_read;
    uint8_t fifo_write;
    uint8_t fifo_count;
    uint8_t state;
    uint8_t status_previous;
    uint8_t command;
    uint8_t payload[FP_MCU_MAX_PAYLOAD];
    uint16_t payload_len;
    uint16_t expected_payload;
    bool command_active;
    bool echo_mode;
    bool irq_enabled;
    bool srq_low;
    bool break_detect_enabled;
    bool diagnostic_key_traffic;
    uint8_t diagnostic_counter; /* raw IRAM 0x43, loaded by command 0x36 */
    uint8_t diagnostic_key_id;
    uint32_t main_loop_count;
    uint8_t last_sound_kind;
    uint8_t last_duration_selector;
    uint8_t last_repeat_count;
    uint8_t last_tone_index;
    fp_mcu_tone_reload_t last_tone_reload;
    uint8_t last_sequence_id;
    size_t last_sequence_count;
    uint16_t last_stock_display_start;
    uint16_t last_stock_display_count;
} fp_mcu_t;

/* Lifecycle and protocol input.  Return value is the number of reply words. */
void fp_mcu_init(fp_mcu_t *mcu, const fp_mcu_platform_t *platform);
void fp_mcu_reset(fp_mcu_t *mcu);
size_t fp_mcu_receive(fp_mcu_t *mcu, uint8_t byte, bool ninth_bit);
size_t fp_mcu_receive_word(fp_mcu_t *mcu, uint16_t word);
void fp_mcu_tick(fp_mcu_t *mcu, uint32_t iterations);

/* Observable state and key ingress. */
uint8_t fp_mcu_status(const fp_mcu_t *mcu);
bool fp_mcu_srq_low(const fp_mcu_t *mcu);
bool fp_mcu_irq_enabled(const fp_mcu_t *mcu);
bool fp_mcu_echo_mode(const fp_mcu_t *mcu);
size_t fp_mcu_fifo_occupancy(const fp_mcu_t *mcu);
bool fp_mcu_enqueue_event(fp_mcu_t *mcu, uint8_t event);
bool fp_mcu_enqueue_key(fp_mcu_t *mcu, uint8_t raw_id, bool pressed,
                        bool startup_held);

/* Logical 600-cell renderer helpers. */
bool fp_mcu_set_cell(fp_mcu_t *mcu, size_t index, uint8_t value);
bool fp_mcu_get_cell(const fp_mcu_t *mcu, size_t index, uint8_t *value);
bool fp_mcu_character_cell(const char *row, uint8_t position,
                           uint8_t segment, uint16_t *cell);

/* Exact recovered RAW translation and event encoding. */
int fp_mcu_raw_to_ppc_event(uint8_t raw_id);
uint8_t fp_mcu_encode_key_event(uint8_t raw_id, bool pressed,
                                bool startup_held);

/* Read-only recovered sound table. */
const fp_mcu_tone_reload_t *fp_mcu_tone_reload(uint8_t index);
size_t fp_mcu_sequence(size_t sequence_id,
                       const fp_mcu_sound_pair_t **pairs);

#ifdef __cplusplus
}
#endif

#endif /* FP_MCU_CORE_H */
