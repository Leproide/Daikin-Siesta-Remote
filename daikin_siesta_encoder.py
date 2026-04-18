"""
Daikin Siesta IR encoder — protocollo reverse-engineered dai codici learned.

Genera codici IR in formato Tuya base64 pronto per il Panamalar.

Bit map (Frame 1, 35 bit + Frame 2, 32 bit, LSB-first):

Frame 1:
  Byte 0:
    nibble basso = mode code (0x1=off, 0x9=cool, 0xC=heat, 0xA=dry, 0xB=fan)
    bit 4        = flag dry (0x10, solo in modalita dry)
    bit 6        = swing (0x40)
  Byte 1:        temperatura - 16
  Byte 2:
    bit 4        = turbo (0x10)
    bit 5        = LED unita interna (0x20)
    bit 7        = X-FAN (0x80)
  Byte 3, 4:     costanti 0x50, 0x02

Frame 2:
  Byte 0 bit 0 : swing echo (0x01)
  Byte 1       : costante 0x20
  Byte 2       : costante 0x00
  Byte 3       : checksum = ((mode_nibble + temp - 20) mod 16) << 4
"""

import struct, base64, json

# ── Timings ────────────────────────────────────────────────────
T_HEADER_MARK  = 9000
T_HEADER_SPACE = 4430
T_BIT_MARK     = 680
T_ZERO         = 530
T_ONE          = 1625
T_FRAME_GAP    = 20000
T_END_GAP      = 30000


# ── Mode code table (byte 0 F1) ────────────────────────────────
MODE_CODES = {
    "cool": 0x09,
    "heat": 0x0C,
    "dry":  0x1A,
    "fan":  0x0B,
}

# Nibble basso = mode id per il checksum
MODE_NIBBLE = {
    "cool": 0x9,
    "heat": 0xC,
    "dry":  0xA,
    "fan":  0xB,
    "off":  0x1,
}


def build_frames(power=True, mode="cool", temp=22,
                 turbo=False, swing=False, led=True, xfan=True):
    """Costruisce i byte dei due frame in base allo stato."""
    mode = mode.lower()
    if power and mode not in MODE_CODES:
        raise ValueError(f"Mode sconosciuto: {mode}. Valid: {list(MODE_CODES)}")

    # Frame 1 (5 byte)
    f1 = [0, 0, 0, 0x50, 0x02]

    # Byte 0: mode + swing flag
    if not power:
        f1[0] = 0x01
    else:
        f1[0] = MODE_CODES[mode]
    if swing and power:
        f1[0] |= 0x40

    # Byte 1: temperatura (nel Fan mode la temp è spesso ignorata,
    # il telecomando mandava 0x09 = 25°C ma non influisce sul condizionatore)
    f1[1] = (int(temp) - 16) & 0xFF

    # Byte 2: feature flags (solo quando ON)
    byte2 = 0x00
    if power:
        if turbo: byte2 |= 0x10
        if led:   byte2 |= 0x20
        if xfan:  byte2 |= 0x80
    f1[2] = byte2

    # Frame 2 (4 byte)
    f2 = [0, 0x20, 0, 0]

    # Byte 0 bit 0: swing echo
    if swing and power:
        f2[0] = 0x01

    # Byte 3: checksum = ((mode_nibble + temp - 20) mod 16) << 4
    if not power:
        # OFF: nibble mode = 1, temp implicita (23-20=3 → (1+3)=4? Ma osservato 0x30)
        # In realtà OFF osservato a temp 22 → (1+2)=3 → 0x30 ✓
        nibble = (MODE_NIBBLE["off"] + int(temp) - 20) & 0xF
    else:
        nibble = (MODE_NIBBLE[mode] + int(temp) - 20) & 0xF
    f2[3] = (nibble << 4) & 0xFF

    return f1, f2


def bytes_to_bits(byte_list, n_bits):
    bits = []
    for b in byte_list:
        for i in range(8):
            bits.append((b >> i) & 1)
    return bits[:n_bits]


def frames_to_pulses(f1, f2):
    pulses = []
    pulses.append(T_HEADER_MARK); pulses.append(T_HEADER_SPACE)
    for bit in bytes_to_bits(f1, 35):
        pulses.append(T_BIT_MARK)
        pulses.append(T_ONE if bit else T_ZERO)
    pulses.append(T_BIT_MARK); pulses.append(T_FRAME_GAP)
    for bit in bytes_to_bits(f2, 32):
        pulses.append(T_BIT_MARK)
        pulses.append(T_ONE if bit else T_ZERO)
    pulses.append(T_BIT_MARK); pulses.append(T_END_GAP)
    return pulses


def pulses_to_tuya_b64(pulses):
    fmt = '<%dH' % len(pulses)
    return base64.b64encode(
        struct.pack(fmt, *(int(p) for p in pulses))
    ).decode('ascii')


def generate(power=True, mode="cool", temp=22,
             turbo=False, swing=False, led=True, xfan=True):
    """
    API high-level: ritorna stringa base64 per Tuya/Panamalar.

    power: True/False
    mode:  'cool' 'heat' 'dry' 'fan'
    temp:  16-30
    turbo: velocita massima ventola (solo cool/heat)
    swing: oscillazione flap
    led:   LED display unita interna (default ON)
    xfan:  X-FAN continuous fan (default ON)
    """
    f1, f2 = build_frames(power, mode, temp, turbo, swing, led, xfan)
    pulses = frames_to_pulses(f1, f2)
    return pulses_to_tuya_b64(pulses)


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "generate-all":
        codes = {"Daikin_OFF": generate(power=False)}
        for mode in ["cool", "heat", "dry", "fan"]:
            for temp in range(18, 31):
                for turbo_flag, turbo_tag in [(False, "Auto"), (True, "Turbo")]:
                    for swing_flag, swing_tag in [(False, ""), (True, "Swing")]:
                        name = f"Daikin_ON_{temp}{turbo_tag}{mode.capitalize()}{swing_tag}"
                        codes[name] = generate(
                            mode=mode, temp=temp,
                            turbo=turbo_flag, swing=swing_flag,
                        )
        with open("ir_codes_generated.json", "w") as f:
            json.dump(codes, f, indent=2)
        print(f"Generati {len(codes)} codici in ir_codes_generated.json")
    else:
        print("Test ON 22°C cool auto:")
        print(generate(mode="cool", temp=22)[:60] + "...")
        print("\nUso:")
        print("  python daikin_siesta_encoder.py generate-all")
