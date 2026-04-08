"""Hardware constants for the Atari 800XL.

This module defines memory-mapped register addresses, timing values, and
enumerations for all major hardware components. These values come from the
Atari 800XL Technical Reference Manual and De Re Atari.

The Atari 800XL memory map (64KB address space):
    $0000-$00FF  Zero Page (256 bytes)
    $0100-$01FF  CPU Stack (256 bytes)
    $0200-$02FF  OS/Hardware Registers (shadow copies)
    $0300-$04FF  OS Vectors and Variables
    $0500-$57FF  Free RAM (available to programs)
    $5800-$7FFF  Free RAM (screen memory often placed here)
    $8000-$9FFF  Free RAM (or cartridge bank B)
    $A000-$BFFF  BASIC ROM (8KB, can be disabled via PIA PORTB)
    $C000-$CFFF  OS ROM (4KB, can be replaced with RAM)
    $D000-$D0FF  GTIA hardware registers
    $D100-$D1FF  Unused (active but undefined)
    $D200-$D2FF  POKEY hardware registers
    $D300-$D3FF  PIA hardware registers
    $D400-$D4FF  ANTIC hardware registers
    $D500-$D5FF  Cartridge control (active but rarely used on XL)
    $D600-$D7FF  Unused
    $D800-$DFFF  OS ROM (2KB floating point routines)
    $E000-$FFFF  OS ROM (8KB, includes character set and OS code)
"""

from dataclasses import dataclass
from enum import IntEnum


# =============================================================================
# Timing Constants (NTSC)
# =============================================================================

CPU_CLOCK_HZ = 1_789_773
"""CPU clock frequency in Hz (NTSC). The 6502C runs at this speed."""

CYCLES_PER_SCANLINE = 114
"""Number of CPU clock cycles per horizontal scanline.
ANTIC uses the same clock; each scanline is exactly 114 machine cycles."""

SCANLINES_PER_FRAME = 262
"""Total scanlines per frame (NTSC). Includes visible area and vertical blank."""

VISIBLE_SCANLINES = 240
"""Number of visible scanlines (approximate). The Atari displays scanlines
8-247 as the visible picture, though programs can adjust this."""

VBLANK_START_SCANLINE = 248
"""Scanline at which the vertical blank interrupt (VBI) fires."""

CYCLES_PER_FRAME = CYCLES_PER_SCANLINE * SCANLINES_PER_FRAME
"""Total CPU cycles per frame: 114 * 262 = 29,868."""

FRAMES_PER_SECOND = 60
"""Approximate frame rate for NTSC (actually 59.94 Hz)."""

# PAL timing (for reference / future use)
PAL_CPU_CLOCK_HZ = 1_773_447
PAL_SCANLINES_PER_FRAME = 312
PAL_FRAMES_PER_SECOND = 50


# =============================================================================
# Memory Map -- Region Boundaries
# =============================================================================

RAM_START = 0x0000
RAM_END = 0xFFFF  # Full 64KB, overlaid by ROM and hardware

BASIC_ROM_START = 0xA000
BASIC_ROM_END = 0xBFFF
BASIC_ROM_SIZE = 0x2000  # 8KB

OS_ROM_START = 0xC000
OS_ROM_END = 0xFFFF
OS_ROM_SIZE = 0x4000  # 16KB

# The OS ROM actually spans two regions that can be independently controlled:
OS_ROM_LOWER_START = 0xC000  # Math pack / FP routines
OS_ROM_LOWER_END = 0xCFFF
OS_ROM_UPPER_START = 0xD800
OS_ROM_UPPER_END = 0xFFFF

# Hardware register pages ($D000-$D4FF)
HARDWARE_START = 0xD000
HARDWARE_END = 0xD4FF

# Self-test ROM (visible when PIA PORTB bit 7 = 0)
SELF_TEST_START = 0x5000
SELF_TEST_END = 0x57FF

# Character set locations within the OS ROM
CHARSET_UPPERCASE = 0xE000  # Default character set
CHARSET_LOWERCASE = 0xE200  # International character set


# =============================================================================
# CPU Vectors (stored in the last 6 bytes of the address space)
# =============================================================================

NMI_VECTOR = 0xFFFA  # Non-Maskable Interrupt vector (2 bytes)
RESET_VECTOR = 0xFFFC  # Reset vector (2 bytes)
IRQ_VECTOR = 0xFFFE  # Interrupt Request vector (2 bytes)


# =============================================================================
# GTIA -- Graphics Television Interface Adapter ($D000-$D01F)
#
# GTIA handles color generation, player/missile graphics collision
# detection, console switches, and trigger (fire button) inputs.
# Note: Many addresses serve different purposes for reads vs writes.
# =============================================================================

class GTIAWriteRegister(IntEnum):
    """GTIA write-only registers (accent on the 'write')."""
    HPOSP0 = 0xD000  # Horizontal position of player 0
    HPOSP1 = 0xD001  # Horizontal position of player 1
    HPOSP2 = 0xD002  # Horizontal position of player 2
    HPOSP3 = 0xD003  # Horizontal position of player 3
    HPOSM0 = 0xD004  # Horizontal position of missile 0
    HPOSM1 = 0xD005  # Horizontal position of missile 1
    HPOSM2 = 0xD006  # Horizontal position of missile 2
    HPOSM3 = 0xD007  # Horizontal position of missile 3
    SIZEP0 = 0xD008  # Player 0 width (1x, 2x, or 4x)
    SIZEP1 = 0xD009  # Player 1 width
    SIZEP2 = 0xD00A  # Player 2 width
    SIZEP3 = 0xD00B  # Player 3 width
    SIZEM = 0xD00C   # All four missile widths (2 bits each)
    GRAFP0 = 0xD00D  # Player 0 graphics shape (8-bit pattern)
    GRAFP1 = 0xD00E  # Player 1 graphics shape
    GRAFP2 = 0xD00F  # Player 2 graphics shape
    GRAFP3 = 0xD010  # Player 3 graphics shape
    GRAFM = 0xD011   # All four missile graphics (2 bits each)
    COLPM0 = 0xD012  # Color of player/missile 0
    COLPM1 = 0xD013  # Color of player/missile 1
    COLPM2 = 0xD014  # Color of player/missile 2
    COLPM3 = 0xD015  # Color of player/missile 3
    COLPF0 = 0xD016  # Playfield color 0
    COLPF1 = 0xD017  # Playfield color 1
    COLPF2 = 0xD018  # Playfield color 2
    COLPF3 = 0xD019  # Playfield color 3
    COLBK = 0xD01A   # Background color
    PRIOR = 0xD01B   # Priority selection, 5th player, GTIA modes
    VDELAY = 0xD01C  # Vertical delay for P/M graphics
    GRACTL = 0xD01D  # Graphics control (enable P/M DMA, latch triggers)
    HITCLR = 0xD01E  # Clear all collision registers (any write)
    CONSPK = 0xD01F  # Console speaker (accent tone, bit 3)


class GTIAReadRegister(IntEnum):
    """GTIA read-only registers (at the same addresses as write registers)."""
    M0PF = 0xD000  # Missile 0 to playfield collisions
    M1PF = 0xD001  # Missile 1 to playfield collisions
    M2PF = 0xD002  # Missile 2 to playfield collisions
    M3PF = 0xD003  # Missile 3 to playfield collisions
    P0PF = 0xD004  # Player 0 to playfield collisions
    P1PF = 0xD005  # Player 1 to playfield collisions
    P2PF = 0xD006  # Player 2 to playfield collisions
    P3PF = 0xD007  # Player 3 to playfield collisions
    M0PL = 0xD008  # Missile 0 to player collisions
    M1PL = 0xD009  # Missile 1 to player collisions
    M2PL = 0xD00A  # Missile 2 to player collisions
    M3PL = 0xD00B  # Missile 3 to player collisions
    P0PL = 0xD00C  # Player 0 to player collisions
    P1PL = 0xD00D  # Player 1 to player collisions
    P2PL = 0xD00E  # Player 2 to player collisions
    P3PL = 0xD00F  # Player 3 to player collisions
    TRIG0 = 0xD010  # Joystick 0 trigger (fire button, 0=pressed)
    TRIG1 = 0xD011  # Joystick 1 trigger
    TRIG2 = 0xD012  # Joystick 2 trigger (XL: unused)
    TRIG3 = 0xD013  # Joystick 3 trigger (XL: BASIC enabled flag)
    PAL = 0xD014    # PAL/NTSC flag (bit 0-3: 1=PAL, 15=NTSC)
    CONSOL = 0xD01F  # Console keys: START(bit 0), SELECT(bit 1), OPTION(bit 2)


# =============================================================================
# POKEY -- Pot Keyboard Integrated Circuit ($D200-$D20F)
#
# POKEY handles sound generation (4 channels), keyboard scanning,
# serial I/O (the SIO bus), hardware timers, and random number generation.
# =============================================================================

class POKEYWriteRegister(IntEnum):
    """POKEY write-only registers."""
    AUDF1 = 0xD200  # Audio channel 1 frequency
    AUDC1 = 0xD201  # Audio channel 1 control (volume + distortion)
    AUDF2 = 0xD202  # Audio channel 2 frequency
    AUDC2 = 0xD203  # Audio channel 2 control
    AUDF3 = 0xD204  # Audio channel 3 frequency
    AUDC3 = 0xD205  # Audio channel 3 control
    AUDF4 = 0xD206  # Audio channel 4 frequency
    AUDC4 = 0xD207  # Audio channel 4 control
    AUDCTL = 0xD208  # Audio control (clock select, filter, 16-bit mode)
    STIMER = 0xD209  # Start timers (any write resets all timer counters)
    SKRES = 0xD20A   # Reset serial port status (clear SKSTAT bits)
    POTGO = 0xD20B   # Start pot (paddle) scan
    SEROUT = 0xD20D  # Serial port output data
    IRQEN = 0xD20E   # IRQ enable register
    SKCTL = 0xD20F   # Serial port control


class POKEYReadRegister(IntEnum):
    """POKEY read-only registers."""
    POT0 = 0xD200  # Paddle 0 position (0-228)
    POT1 = 0xD201  # Paddle 1 position
    POT2 = 0xD202  # Paddle 2 position
    POT3 = 0xD203  # Paddle 3 position
    POT4 = 0xD204  # Paddle 4 position
    POT5 = 0xD205  # Paddle 5 position
    POT6 = 0xD206  # Paddle 6 position
    POT7 = 0xD207  # Paddle 7 position
    ALLPOT = 0xD208  # All pots scan complete flags
    KBCODE = 0xD209  # Keyboard code (key matrix scan result)
    RANDOM = 0xD20A  # Random number generator (17-bit LFSR output)
    SERIN = 0xD20D   # Serial port input data
    IRQST = 0xD20E   # IRQ status register (active-low: 0=IRQ pending)
    SKSTAT = 0xD20F  # Serial port / keyboard status


# AUDCTL bit definitions
class AUDCTLBits(IntEnum):
    """Bit masks for the POKEY AUDCTL register ($D208 write)."""
    POLY9 = 0x80         # Use 9-bit poly instead of 17-bit (bit 7)
    CH1_179MHZ = 0x40    # Channel 1 uses 1.79 MHz clock (bit 6)
    CH3_179MHZ = 0x20    # Channel 3 uses 1.79 MHz clock (bit 5)
    CH1_CH2_16BIT = 0x10  # Channels 1+2 clocked as 16-bit pair (bit 4)
    CH3_CH4_16BIT = 0x08  # Channels 3+4 clocked as 16-bit pair (bit 3)
    CH1_HIGHPASS = 0x04   # Channel 1 high-pass filter clocked by ch 3 (bit 2)
    CH2_HIGHPASS = 0x02   # Channel 2 high-pass filter clocked by ch 4 (bit 1)
    CLOCK_15KHZ = 0x01    # Use 15 kHz base clock instead of 64 kHz (bit 0)


# IRQEN/IRQST bit definitions
class IRQBits(IntEnum):
    """Bit masks for POKEY IRQ enable (IRQEN) and status (IRQST) registers."""
    TIMER1 = 0x01     # Timer 1 underflow
    TIMER2 = 0x02     # Timer 2 underflow
    TIMER4 = 0x04     # Timer 4 underflow
    SERIAL_OUT_DONE = 0x08  # Serial output transmission complete
    SERIAL_OUT_NEED = 0x10  # Serial output data needed
    SERIAL_IN_DONE = 0x20   # Serial input data ready
    KEYBOARD = 0x40         # Keyboard key pressed
    BREAK_KEY = 0x80        # BREAK key pressed


# POKEY audio clock dividers
POKEY_CLOCK_64KHZ = 63_921    # ~64 kHz (CPU_CLOCK / 28)
POKEY_CLOCK_15KHZ = 15_699    # ~15.7 kHz (CPU_CLOCK / 114)
POKEY_CLOCK_179MHZ = CPU_CLOCK_HZ  # 1.79 MHz (raw CPU clock)


# =============================================================================
# PIA -- Peripheral Interface Adapter ($D300-$D303)
#
# The PIA (6520) provides two 8-bit I/O ports. On the 800XL:
#   Port A ($D300): Joystick direction inputs
#   Port B ($D302): Memory configuration / bank switching
# =============================================================================

class PIARegister(IntEnum):
    """PIA register addresses. Note: PORTA/PACTL and PORTB/PBCTL share
    addresses -- the control register's bit 2 determines whether you're
    accessing the data register or the direction register (DDR)."""
    PORTA = 0xD300   # Port A data / direction register
    PACTL = 0xD301   # Port A control register
    PORTB = 0xD302   # Port B data / direction register
    PBCTL = 0xD303   # Port B control register


# PIA Port A -- Joystick bit assignments (active low: 0 = pressed)
class JoystickBits(IntEnum):
    """Bit positions in PIA Port A for joystick directions."""
    STICK0_UP = 0x01     # Joystick 0 up (bit 0, active low)
    STICK0_DOWN = 0x02   # Joystick 0 down (bit 1)
    STICK0_LEFT = 0x04   # Joystick 0 left (bit 2)
    STICK0_RIGHT = 0x08  # Joystick 0 right (bit 3)
    STICK1_UP = 0x10     # Joystick 1 up (bit 4)
    STICK1_DOWN = 0x20   # Joystick 1 down (bit 5)
    STICK1_LEFT = 0x40   # Joystick 1 left (bit 6)
    STICK1_RIGHT = 0x80  # Joystick 1 right (bit 7)


# PIA Port B -- Memory configuration bit assignments (800XL specific)
class PORTBBits(IntEnum):
    """Bit masks for PIA Port B memory configuration on the 800XL."""
    OS_ROM_ENABLE = 0x01      # Bit 0: 1=OS ROM enabled, 0=RAM underneath
    BASIC_ROM_ENABLE = 0x02   # Bit 1: 1=BASIC enabled, 0=BASIC disabled
    LED_1 = 0x04              # Bit 2: Keyboard LED 1 (active low on 1200XL)
    LED_2 = 0x08              # Bit 3: Keyboard LED 2 (active low on 1200XL)
    # Bits 4-6: unused on 800XL
    SELF_TEST_ENABLE = 0x80   # Bit 7: 0=self-test ROM at $5000, 1=RAM


# =============================================================================
# ANTIC -- Alpha-Numeric Television Interface Controller ($D400-$D40F)
#
# ANTIC is a programmable display processor. It reads a "display list"
# (a small program) from RAM that describes what to show on each line.
# It performs DMA to fetch screen data and character set bitmaps,
# stealing CPU cycles in the process.
# =============================================================================

class ANTICRegister(IntEnum):
    """ANTIC register addresses."""
    DMACTL = 0xD400  # DMA control: enable display, P/M, width
    CHACTL = 0xD401  # Character display control (inverse, reflect)
    DLISTL = 0xD402  # Display list pointer low byte
    DLISTH = 0xD403  # Display list pointer high byte
    HSCROL = 0xD404  # Horizontal fine scroll (0-15 color clocks)
    VSCROL = 0xD405  # Vertical fine scroll (0-15 scan lines)
    # 0xD406 is unused
    PMBASE = 0xD407  # Player/missile base address (high byte, aligned)
    # 0xD408 is unused
    CHBASE = 0xD409  # Character set base address (high byte)
    WSYNC = 0xD40A   # Wait for horizontal sync (write halts CPU)
    VCOUNT = 0xD40B  # Vertical line counter (current scanline / 2)
    PENH = 0xD40C    # Light pen horizontal position (read)
    PENV = 0xD40D    # Light pen vertical position (read)
    NMIEN = 0xD40E   # NMI enable register (write)
    NMIST = 0xD40F   # NMI status register (read) / NMIRES (write: reset)


# DMACTL bit definitions
class DMACTLBits(IntEnum):
    """Bit masks for the ANTIC DMACTL register."""
    NARROW_PLAYFIELD = 0x01   # 128 color clocks (32 chars)
    NORMAL_PLAYFIELD = 0x02   # 160 color clocks (40 chars)
    WIDE_PLAYFIELD = 0x03     # 192 color clocks (48 chars)
    PLAYFIELD_MASK = 0x03     # Bits 0-1: playfield width
    MISSILE_DMA = 0x04        # Bit 2: enable missile DMA
    PLAYER_DMA = 0x08         # Bit 3: enable player DMA
    PM_1LINE = 0x10           # Bit 4: 1=single-line P/M, 0=double-line
    DL_DMA = 0x20             # Bit 5: enable display list DMA (master switch)


# NMIEN/NMIST bit definitions
class NMIBits(IntEnum):
    """Bit masks for ANTIC NMI enable (NMIEN) and status (NMIST) registers."""
    DLI = 0x80   # Display list interrupt (bit 7)
    VBI = 0x40   # Vertical blank interrupt (bit 6)
    RESET = 0x20  # System reset button (bit 5, active in NMIST only)


# CHACTL bit definitions
class CHACTLBits(IntEnum):
    """Bit masks for the ANTIC CHACTL register."""
    INVERSE = 0x02   # Bit 1: invert characters with bit 7 set (blank instead)
    REFLECT = 0x04   # Bit 2: vertically reflect all characters


# =============================================================================
# ANTIC Display List Instruction Encoding
#
# Each display list instruction is 1 byte (optionally followed by 2 address
# bytes if the LMS bit is set). The low 4 bits encode the mode:
#   $00: blank line instruction (high nibble = count - 1)
#   $01: jump (JMP) -- followed by 2-byte address
#   $41: jump and wait for vertical blank (JVB)
#   $02-$0F: display mode line
# Special bits in the instruction byte:
#   Bit 6 (LMS): Load Memory Scan -- next 2 bytes are the screen data address
#   Bit 7 (DLI): Trigger display list interrupt on last scanline of this line
#   Bit 4 (HSCROL): Enable horizontal scrolling for this line
#   Bit 5 (VSCROL): Enable vertical scrolling for this line
# =============================================================================

class DLInstruction(IntEnum):
    """Special display list instruction types."""
    BLANK_1 = 0x00   # 1 blank scanline
    BLANK_2 = 0x10   # 2 blank scanlines
    BLANK_3 = 0x20   # 3 blank scanlines
    BLANK_4 = 0x30   # 4 blank scanlines
    BLANK_5 = 0x40   # 5 blank scanlines
    BLANK_6 = 0x50   # 6 blank scanlines
    BLANK_7 = 0x60   # 7 blank scanlines
    BLANK_8 = 0x70   # 8 blank scanlines
    JMP = 0x01        # Jump to address (2-byte operand follows)
    JVB = 0x41        # Jump and wait for vertical blank


# Display list instruction bit masks
DL_MODE_MASK = 0x0F      # Low 4 bits: display mode (0-15)
DL_LMS_BIT = 0x40        # Bit 6: Load Memory Scan
DL_DLI_BIT = 0x80        # Bit 7: Display List Interrupt
DL_HSCROL_BIT = 0x10     # Bit 4: Horizontal scroll enable
DL_VSCROL_BIT = 0x20     # Bit 5: Vertical scroll enable


# =============================================================================
# ANTIC Display Mode Properties
#
# Each ANTIC mode defines the type of display (text or graphics), the number
# of bytes per line, the height in scanlines per mode line, and the number
# of colors available.
# =============================================================================


@dataclass(frozen=True)
class ANTICModeInfo:
    """Properties of an ANTIC display mode.

    Attributes:
        mode: The ANTIC mode number (2-15).
        name: Human-readable description.
        is_text: True for character modes, False for bitmap (map) modes.
        bytes_per_line: Number of bytes of screen data per mode line
                        (at normal playfield width, 40 chars).
        scanlines_per_row: Height of each mode line in scanlines.
        colors: Number of colors (including background).
    """
    mode: int
    name: str
    is_text: bool
    bytes_per_line: int
    scanlines_per_row: int
    colors: int


ANTIC_MODES: dict[int, ANTICModeInfo] = {
    # Text modes
    2: ANTICModeInfo(2, "40-column text", True, 40, 8, 2),
    3: ANTICModeInfo(3, "40-column text (10 scanlines)", True, 40, 10, 2),
    4: ANTICModeInfo(4, "40-column text, 5-color", True, 40, 8, 5),
    5: ANTICModeInfo(5, "40-column text, 5-color (16 scanlines)", True, 40, 16, 5),
    6: ANTICModeInfo(6, "20-column text, 5-color", True, 20, 8, 5),
    7: ANTICModeInfo(7, "20-column text, 5-color (16 scanlines)", True, 20, 16, 5),
    # Bitmap (map) modes
    8: ANTICModeInfo(8, "40-pixel bitmap (mode 3)", False, 10, 8, 4),
    9: ANTICModeInfo(9, "80-pixel bitmap (mode 4)", False, 10, 4, 2),
    10: ANTICModeInfo(10, "80-pixel bitmap, 4-color (mode 5)", False, 20, 4, 4),
    11: ANTICModeInfo(11, "160-pixel bitmap (mode 6)", False, 20, 2, 2),
    12: ANTICModeInfo(12, "160-pixel bitmap (mode 6, 1-scanline)", False, 20, 1, 2),
    13: ANTICModeInfo(13, "160-pixel bitmap, 4-color (mode 7)", False, 40, 2, 4),
    14: ANTICModeInfo(14, "160-pixel bitmap, 4-color (mode 7, 1-scanline)", False, 40, 1, 4),
    15: ANTICModeInfo(15, "320-pixel hi-res bitmap (mode 8)", False, 40, 1, 2),
}


# =============================================================================
# OS Shadow Registers and Important Zero-Page Locations
#
# The Atari OS maintains "shadow" copies of some hardware registers in RAM.
# During the vertical blank interrupt (VBI), the OS copies shadow values
# into the actual hardware registers. This lets programs update display
# parameters safely between frames.
# =============================================================================

class ShadowRegister(IntEnum):
    """OS shadow register locations in RAM."""
    SDMCTL = 0x022F   # Shadow of ANTIC DMACTL
    SDLSTL = 0x0230   # Shadow of ANTIC DLISTL (low byte)
    SDLSTH = 0x0231   # Shadow of ANTIC DLISTH (high byte)
    CHBAS = 0x02F4    # Shadow of ANTIC CHBASE
    CHART = 0x02F3    # Shadow of ANTIC CHACTL
    GPRIOR = 0x026F   # Shadow of GTIA PRIOR
    PCOLR0 = 0x02C0   # Shadow of GTIA COLPM0
    PCOLR1 = 0x02C1   # Shadow of GTIA COLPM1
    PCOLR2 = 0x02C2   # Shadow of GTIA COLPM2
    PCOLR3 = 0x02C3   # Shadow of GTIA COLPM3
    COLOR0 = 0x02C4   # Shadow of GTIA COLPF0
    COLOR1 = 0x02C5   # Shadow of GTIA COLPF1
    COLOR2 = 0x02C6   # Shadow of GTIA COLPF2
    COLOR3 = 0x02C7   # Shadow of GTIA COLPF3
    COLOR4 = 0x02C8   # Shadow of GTIA COLBK (background)
    LMARGIN = 0x0052  # Left margin for text output
    RMARGIN = 0x0053  # Right margin for text output
    ROWCRS = 0x0054   # Cursor row position
    COLCRS = 0x0055   # Cursor column position (2 bytes)


# =============================================================================
# OS Vectors
# =============================================================================

class OSVector(IntEnum):
    """Important OS vector addresses."""
    VDSLST = 0x0200   # Display list interrupt vector (2 bytes)
    VVBLKI = 0x0222   # Immediate VBI vector (2 bytes)
    VVBLKD = 0x0224   # Deferred VBI vector (2 bytes)
    VKEYBD = 0x0208   # Keyboard IRQ vector (2 bytes)
    VBREAK = 0x0206   # BREAK key IRQ vector (2 bytes)
    VSERIN = 0x020A   # Serial input ready IRQ vector
    VSEROR = 0x020C   # Serial output ready IRQ vector
    VSEROC = 0x020E   # Serial output complete IRQ vector
    VTIMR1 = 0x0210   # Timer 1 IRQ vector
    VTIMR2 = 0x0212   # Timer 2 IRQ vector
    VTIMR4 = 0x0214   # Timer 4 IRQ vector
    DOSINI = 0x000C   # DOS init address (2 bytes)
    DOSVEC = 0x000A   # DOS run address (2 bytes)
    RUNAD = 0x02E0    # Binary load run address
    INITAD = 0x02E2   # Binary load init address


# =============================================================================
# Player/Missile (Sprite) Constants
# =============================================================================

PM_NUM_PLAYERS = 4
PM_NUM_MISSILES = 4
PM_PLAYER_WIDTH_PIXELS = 8    # Each player is 8 color clocks wide
PM_MISSILE_WIDTH_PIXELS = 2   # Each missile is 2 color clocks wide

# Player/missile size multipliers (for SIZEP0-3 and SIZEM registers)
PM_SIZE_NORMAL = 0x00  # 1x width
PM_SIZE_DOUBLE = 0x01  # 2x width
PM_SIZE_QUAD = 0x03    # 4x width


# =============================================================================
# Atari Color Model
#
# The Atari uses a byte to represent color: the high nibble (bits 4-7) is the
# hue (0-15), and the low nibble (bits 0-3) is the luminance (0-15, even
# values only -- odd values are treated as the next lower even value).
# This gives 128 unique colors (16 hues x 8 luminance levels).
# =============================================================================

NUM_HUES = 16
NUM_LUMINANCES = 16  # 0-15, but only even values are distinct


# =============================================================================
# SIO (Serial I/O) Constants
# =============================================================================

class SIODeviceID(IntEnum):
    """SIO device identifiers."""
    DISK_1 = 0x31    # $31 = Disk drive 1 (D1:)
    DISK_2 = 0x32    # Disk drive 2 (D2:)
    DISK_3 = 0x33    # Disk drive 3 (D3:)
    DISK_4 = 0x34    # Disk drive 4 (D4:)
    PRINTER = 0x40   # $40 = Printer (P:)
    CASSETTE = 0x60  # $60 = Cassette (C:)


class SIOCommand(IntEnum):
    """SIO command bytes."""
    READ_SECTOR = 0x52   # 'R' -- Read a sector
    WRITE_SECTOR = 0x57  # 'W' -- Write a sector (with verify)
    STATUS = 0x53        # 'S' -- Get device status
    PUT_SECTOR = 0x50    # 'P' -- Write a sector (no verify)
    FORMAT = 0x21        # '!' -- Format disk

# Standard sector sizes
SECTOR_SIZE_SINGLE = 128   # Single density (810 drive)
SECTOR_SIZE_DOUBLE = 256   # Double density (1050 drive enhanced)

# SIO OS routine entry point
SIO_VECTOR = 0xE459
