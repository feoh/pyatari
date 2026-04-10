"""Trace the real Atari ROM boot path for debugging missing hardware behavior."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyatari.machine import Machine
from pyatari.rom_loader import find_self_test_rom, load_basic_rom, load_self_test_rom, load_xl_rom_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace PyAtari ROM boot progress")
    parser.add_argument("--steps", type=int, default=200_000, help="total CPU steps to execute")
    parser.add_argument("--stride", type=int, default=20_000, help="report state every N steps")
    parser.add_argument(
        "--post-checksum-fallback",
        action="store_true",
        help="continue from the post-checksum warm-start fallback when self-test ROM is unavailable",
    )
    parser.add_argument(
        "--rom-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "roms",
        help="directory containing atarixl.rom and optionally ataribas.rom",
    )
    args = parser.parse_args()

    machine = Machine()
    os_rom_path = args.rom_dir / "atarixl.rom"
    basic_rom_path = args.rom_dir / "ataribas.rom"
    self_test_rom_path = find_self_test_rom(args.rom_dir)
    os_rom, bundled_self_test_rom = load_xl_rom_bundle(os_rom_path)
    machine.memory.load_os_rom(os_rom.data)
    if basic_rom_path.exists():
        machine.memory.load_basic_rom(load_basic_rom(basic_rom_path).data)
    if bundled_self_test_rom is not None:
        machine.memory.load_self_test_rom(bundled_self_test_rom.data)
    if self_test_rom_path is not None:
        machine.memory.load_self_test_rom(load_self_test_rom(self_test_rom_path).data)
    machine.reset()
    if args.post_checksum_fallback:
        machine.continue_without_self_test()

    reset_state = machine.rom_boot_state()
    print(
        f"reset PC=${reset_state.pc:04X} frame={reset_state.frame} scanline={reset_state.scanline} "
        f"PORTB=${reset_state.portb:02X} COLDST=${reset_state.coldstart_status:02X} "
        f"DMACTL=${reset_state.dmactl:02X}/${reset_state.sdmctl:02X} "
        f"DLIST=${reset_state.dlist:04X}/${reset_state.sdlstl:04X} "
        f"CHBASE=${reset_state.chbase:02X}/${reset_state.chbas_shadow:02X} "
        f"SAVMSC=${reset_state.savmsc:04X} visible={reset_state.visible_output}"
    )

    for step in range(1, args.steps + 1):
        machine.step()
        if step % args.stride == 0 or step == args.steps:
            state = machine.rom_boot_state()
            print(
                f"{step:>8} PC=${state.pc:04X} A={machine.cpu.a:02X} "
                f"X={machine.cpu.x:02X} Y={machine.cpu.y:02X} "
                f"frame={state.frame} scanline={state.scanline} "
                f"PORTB=${state.portb:02X} COLDST=${state.coldstart_status:02X} "
                f"DMACTL=${state.dmactl:02X}/${state.sdmctl:02X} "
                f"DLIST=${state.dlist:04X}/${state.sdlstl:04X} "
                f"CHBASE=${state.chbase:02X}/${state.chbas_shadow:02X} "
                f"SAVMSC=${state.savmsc:04X} visible={state.visible_output}"
            )


if __name__ == "__main__":
    main()
