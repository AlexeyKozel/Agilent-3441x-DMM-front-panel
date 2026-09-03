# Reconstructed Pseudocode of Original Front-Panel Procedures

This document presents independently rewritten pseudocode derived from the
exact original 8051 and PPC executable images. It is not a verbatim decompiler
export, source-code recovery claim, or complete disassembly. Addresses are
evidence anchors; names describe recovered behavior.

The pseudocode supports the offline emulators. It does not prove real-hardware
timing or electrical compatibility.

## Original 8051 front-panel firmware

### Reset and initialization — `CODE:0000`, `CODE:0766`

```text
reset_vector():
    jump runtime_startup_0766

runtime_startup_0766():
    clear internal_RAM
    clear XRAM[0x0000:0x0200]
    SP = 0x4F
    apply compiler_initialization_table()
    P0 = 0x7F; P1 = 0xDF; P2 = 0xF7; P3 = 0x00
    initialize_timer_counter_blocks()
    initialize_vfd_serial_engine()
    initialize_uart_0B84()
    reset_key_state_0EED()       // clears P1.6, fills debounce state with 0x82
    initialize_runtime_subsystems()
    enable_interrupts()
    jump main_loop_0A3B
```

### Cooperative main loop — `CODE:0A3B`

```text
forever:
    display_refresh_step_0A93()
    keypad_divider += 1
    if keypad_divider modulo 4 == 0:
        scan_one_keypad_row_0B42()
    if diagnostic_key_traffic_enabled:
        diagnostic_counter += 1
        if diagnostic_counter reaches 30:
            enqueue synthetic press and release for diagnostic_raw_id
            diagnostic_raw_id = (diagnostic_raw_id + 1) modulo 20
            diagnostic_counter = 0
    empty_hook_103F()
    if sound_sequence_active:
        advance_sound_sequence_0400()
```

### UART receive ISR and command selection — `CODE:05E3`, table `CODE:0882`

```text
uart_receive_isr():
    if RI is not set:
        return
    byte = SBUF
    command_marker = RB8
    clear RI

    if parser_is_idle or command_marker == 1:
        previous_state = state
        state = 0x00
        current_command = byte
        reset_payload_phase()
        if byte >= 0x40:
            reject_with_0x81()
        else:
            dispatch through 64-entry table at 0x0882
        return

    if echo_mode:
        transmit(byte, TB8=0)
        return

    pass byte to active command payload handler
```

### Common completion and status behavior

```text
complete(reply_bytes, result_state):
    for byte in reply_bytes:
        TB8 = 0
        SBUF = byte
        wait for transmit completion
    state = result_state
    parser = idle

GET_STATUS_0x05():
    old = previous_state
    transmit(old, TB8=0)
    state = 0x01
    parser = idle
```

### Display write — command `0x21`, inline in `CODE:05E3`

```text
WRITE_DISPLAY():
    count = receive_data_byte()
    start = receive_data_byte()
    DPTR = start
    iterations = 256 if count == 0 else count
    repeat iterations times:
        MOVX[DPTR] = receive_data_byte()
        DPTR += 1
    complete([0x01], 0x01)
```

The original handler does not perform the stock PPC's 150-byte span check.
The C emulator bounds the 256-write edge case inside an explicit 512-byte XRAM
window and rejects unsafe non-stock normal spans.

### Keypad scan, debounce, FIFO, and SRQ — `CODE:0B42`, `0E06`, `0D06`

```text
scan_one_keypad_row_0B42():
    drive one active-low row from P2.0, P2.1, P2.4, P2.6, P2.7
    columns = active-low P0.0..P0.3
    for each column:
        raw_id = row + 5 * column
        state_byte = XRAM[0x0096 + raw_id]
        update three-sample press/release counter
        on stable transition:
            event.bit7 = startup-held marker for first startup press
            event.bit6 = pressed
            event.bits5_0 = raw_id
            enqueue_event_0E06(event)

enqueue_event_0E06(event):
    if FIFO occupancy == 4:
        discard new event
    else:
        FIFO[write_index] = event
        advance write_index modulo 4
        if key_IRQ_gate is enabled:
            clear P1.6                  // active-low FP_SRQ*

dequeue_event_0D06():
    if FIFO is empty:
        set P1.6
        return 0xFF with state 0x81
    event = FIFO[read_index]
    advance read_index modulo 4
    if FIFO becomes empty:
        set P1.6
    return event with state 0x01
```

### VFD refresh — `CODE:0A93`, `096D`, `0902`, `0C5B`

```text
display_refresh_step_0A93():
    select the next multiplex/blanking phase
    extract two-bit cells from the 150-byte framebuffer
    assemble nibbles and swap them where required
    invert and shift serial bytes through RXDAT/EPCON
    generate latch/strobe transitions
    advance display counters
```

### Sound — `CODE:0800`, `0C2A`, sequence worker `0400`

```text
start_sound(duration_selector, tone_index):
    tone_index = min(tone_index, 0x54)
    if tone_index == 0:
        disable tone output
    else:
        load exact timer pair from table at 0x0274
    if duration_selector < 3:
        active_duration = duration_selector
        repeat_count = 0
    else:
        active_duration = 2
        repeat_count = duration_selector - 3
    arm timer/PCA state and P1.4 output

advance_sound_sequence_0400():
    when the current pair completes:
        fetch the next (duration, tone) pair
        if terminator reached:
            stop sequence
        else:
            start_sound(duration, tone)
```

### Calls into internal ROM ISP — `CODE:0C0A`

```text
rom_service_path_0C0A():
    call 0xFF03 with A=0x02, R5=0x01, R7=0x03
    call 0xFF03 with A=0x02, R5=0x63, R7=0x00
```

The implementation behind `0xFF03` resides in MCU internal ROM and is not part
of the included 4162-byte application image.

## Original PPC front-panel procedures

### UART mode selection — `BpUart::setUartMode`, `0x00592FA0`

```text
set_uart_mode(mode):
    if mode == CMMD:
        ioctl(0x5001)       // transmit ninth bit 1
    else if mode == DATA:
        ioctl(0x5002)       // transmit ninth bit 0
    else if mode == DOWN:
        ioctl(0x5004)       // stock programming mode
    else:
        report invalid mode
```

### Runtime transaction — `BpComm::rawSerialTransaction`, `0x0058EFA4`

```text
raw_serial_transaction(packet, immediate_reply_length):
    set_uart_mode(DATA)
    flush_panel_channel()
    write packet as one buffer
    immediate = read exactly immediate_reply_length bytes

    set_uart_mode(CMMD)
    write byte 0x05
    status = read exactly one byte

    if (status & 0x85) != 0x01:
        return failure with immediate reply and status
    return success with immediate reply and status
```

### UART read — `BpUart::readUart`, `0x00592B20`

```text
read_uart(destination, requested_length, timeout):
    repeat until requested_length bytes are collected or an error occurs:
        wait for driver data using the configured timeout
        read available bytes into destination
    return exact byte count or failure
```

### Front-panel reset — `Frontpanel::reset`, `0x00359AD0`

```text
reset_front_panel():
    drive GPIO mask 0x04000000 HIGH
    delay approximately 2 ms
    drive the same mask LOW
    delay approximately 2 ms
    drive the same mask HIGH
    delay approximately 4 ms
```

These are recovered software delays and a logical mask. Their connector-level
waveform has not been measured.

### Display update — `Frontpanel::updateDisplay`, `0x00359CB8`

```text
update_display(old_buffer, new_buffer):
    find the first changed byte in the 150-byte framebuffer
    find the last changed byte
    if no byte changed:
        return success
    count = last - first + 1
    packet = [0x21, count, first] + new_buffer[first:last+1]
    send packet through raw_serial_transaction expecting one-byte ACK
```

### Character renderer — `lightReadoutChar`, `0x000AAA04`

```text
render_character(row, position, segment_states[17]):
    base = 5 for main row, 245 for secondary row
    for segment in 0..16:
        cell = base + 40 * floor(position / 2) + (position & 1) + 2 * segment
        write the segment's two-bit state into that cell
```

### Key polling — `keyGet 0x003573FC`, `scanKeys 0x0035777C`

```text
key_get():
    transaction = send command 0x15 expecting one byte
    if transaction failed because FIFO was empty:
        return no event
    return returned event byte

scan_keys():
    while FP_SRQ indicates pending data:
        raw_event = key_get()
        if no event:
            stop
        mapped = map_key_to_event_000AAD84(raw_event & 0x3F)
        process press/release and startup-held bits
        dispatch mapped UI event when the raw ID is mapped
```

Historical addresses `0x003577A8` and `0x003578F0` are call sites inside
`scanKeys`, not procedure entries.

### Stock firmware update — host anchors `0x0035F00C` and `0x00367074`

```text
update_original_panel(image, length):
    enter DOWN mode at 7200 bit/s
    perform reset/break and three-byte 0x55 autobaud
    read and validate device ID, boot vector, status, and UCFG
    enter programming state
    clear security and erase seven 0x400-byte sectors
    program image in blocks of up to 32 bytes using ASCII HEX records
    restore boot vector, UCFG, and status
    verify final configuration
    leave programming mode, reset panel, and restore runtime UART settings
    abort immediately on generation, echo, response, timeout, or verify error
```

Record generation at `Isp8051::genHexRecord 0x00367074` emits
`:LLAAAATT[DD...]CC` with an uppercase hexadecimal two's-complement checksum.

## Validation boundary

The pseudocode is checked against the published protocol tables, exact image
identity, opcode-derived anchors, closure traces, and offline emulator tests.
Neither emulator nor these reconstructed procedures have been validated by
operating a real instrument or original front panel.
