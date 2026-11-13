# Play once at startup, or run `black-hole` to repeat until Q or Esc.
black-hole() {
  local BLACK_HOLE_ANIMATION_MODE=${1:---loop}
  if (( $# > 1 )) || [[ $BLACK_HOLE_ANIMATION_MODE != --loop && $BLACK_HOLE_ANIMATION_MODE != --once ]]; then
    print -u2 -- 'Usage: black-hole [--loop|--once]'
    return 2
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    print -u2 -- 'black-hole requires python3'
    return 127
  fi
  BLACK_HOLE_ANIMATION_MODE="$BLACK_HOLE_ANIMATION_MODE" BLACK_HOLE_ANIMATION_BG="${DOT_THEME_LIGHT_BG:-#edebdc}" python3 /dev/fd/3 3<<'PY'
import math
import os
import select
import shutil
import sys
import termios
import time
import tty

LOOP_MODE = os.environ.get("BLACK_HOLE_ANIMATION_MODE") == "--loop"
if not (sys.stdin.isatty() and sys.stdout.isatty()):
    raise SystemExit("black-hole requires an interactive terminal")

size = shutil.get_terminal_size()
if size.columns < 41 or size.lines < 14:
    if LOOP_MODE:
        print("Terminal too small (need 41 columns and 14 lines)", file=sys.stderr)
    raise SystemExit

sin, cos, exp, log, hypot, atan2 = (
    math.sin, math.cos, math.exp, math.log, math.hypot, math.atan2
)
TAU = 2 * math.pi
R0 = 0.11
R_IN, R_OUT = 1.55 * R0, 5.4 * R0
TILT, INC = math.radians(17), 0.12
CT, ST = cos(TILT), sin(TILT)
FLASH, INTRO_END, SPEED, EXIT_TIME = 7.8, 20.0, 4.0, 0.65
COLORS = ((190, 38, 12), (242, 78, 20), (255, 124, 34),
          (255, 172, 78), (255, 222, 168), (220, 228, 255),
          (130, 72, 48))
POOLS = ("1il!;:", "rtfjcvxz=+", "aeoun0{}[]<>", "08B$#&%Q")
LIGHT_THEME = os.environ.get("ZSH_THEME_MODE") == "light"
DARK_ANSI = tuple(
    tuple("\x1b[38;2;{};{};{}m".format(
        *(min(channel * level // 5, 255) for channel in rgb)
    ) for level in range(1, 7))
    for rgb in COLORS
)
if LIGHT_THEME:
    background_hex = os.environ["BLACK_HOLE_ANIMATION_BG"].lstrip("#")
    background = tuple(int(background_hex[i:i + 2], 16) for i in (0, 2, 4))

    def light_shades(rgb):
        return tuple("\x1b[38;2;{};{};{}m".format(
            *(round(bg + (channel - bg) * (level / 6) ** 0.7)
              for bg, channel in zip(background, rgb))
        ) for level in range(1, 7))

    # Keep the dark theme's heat-driven texture, with a wider warm spectrum
    # and reversed contrast for the light background.
    LIGHT_HEAT_STOPS = ((0.07, (247, 233, 207)), (0.15, (250, 210, 126)),
                        (0.30, (248, 165, 65)), (0.55, (236, 102, 42)),
                        (0.85, (188, 48, 38)), (1.25, (105, 24, 31)),
                        (2.00, (49, 15, 23)))

    def light_heat_color(value):
        for (start, faint), (end, strong) in zip(LIGHT_HEAT_STOPS,
                                                 LIGHT_HEAT_STOPS[1:]):
            if value <= end:
                blend = max(0.0, (value - start) / (end - start))
                return tuple(round(a + (b - a) * blend)
                             for a, b in zip(faint, strong))
        return LIGHT_HEAT_STOPS[-1][1]

    LIGHT_HEAT_BANDS = 48
    LIGHT_ANSI = tuple(
        light_shades(light_heat_color(0.07 + (2.0 - 0.07) * band /
                                      (LIGHT_HEAT_BANDS - 1)))
        for band in range(LIGHT_HEAT_BANDS)
    )
ANSI = DARK_ANSI
STAR_ANSI = (("\x1b[38;2;66;72;88m", "\x1b[38;2;111;119;139m",
              "\x1b[38;2;165;174;192m") if LIGHT_THEME else (ANSI[5][3],) * 3)
SPACE = " "


def smooth(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def gas(phi, rho, t, spin):
    rho = max(rho, 1e-6)
    phase = phi - (rho / R_IN) ** -1.5 * spin
    lr = log(rho / R0)
    wave = 46 * lr + 0.9 * sin(phase + 3 * lr)
    streak = (0.55 + 0.3 * sin(wave) + 0.15 * sin(2.3 * wave + 2 * phase)
              + 0.12 * sin(3 * phase - 7 * lr + 0.3 * t))
    if t > FLASH:
        pulses = 0.0
        for orbit, start, speed in ((1.8, 0.0, 0.95), (2.4, 2.1, 0.8),
                                    (3.2, 4.2, 0.65)):
            distance = (phi - start - speed * t + math.pi) % TAU - math.pi
            comet = exp(-(distance / 0.18) ** 2) if distance > 0 else exp(distance / 0.9)
            pulses += comet * exp(-((lr - log(orbit)) / 0.07) ** 2)
        streak += 0.9 * smooth((t - FLASH) / 1.0) * pulses
    return streak, phase, lr


def pixel(base_x, base_y, t, spin, cam, flash, ring_k, aura_k, disk_on, zoom,
          exit_progress, row, col):
    h = ((row * 0x9E3779B1) ^ (col * 0x85EBCA77)) & 0xFFFFFFFF
    h = ((h ^ (h >> 16)) * 0x7FEB352D) & 0xFFFFFFFF
    h = ((h ^ (h >> 15)) * 0x846CA68B) & 0xFFFFFFFF
    h ^= h >> 16
    scale = max((1 - exit_progress) ** 2, 1e-6)
    x = base_x / (zoom * scale)
    y = (base_y + 0.02 * cam) / (zoom * scale)
    if abs(x) > 1.1 or abs(y) > 0.85:
        return SPACE, None
    r = hypot(x, y)
    ang = atan2(y, x)

    around = ((ang + math.pi / 2) % TAU) / TAU
    ring = exp(-((r - 1.02 * R0) / (0.045 * R0)) ** 2)
    ring *= smooth((ring_k * 1.08 - around) / 0.08)

    aura = 0.0
    if aura_k > 0 and r < 0.4:
        a, b, wave_t = 2 * ang, 5 * r - 0.45 * t, 0.35 * t
        ripple = (0.5 * sin(a + 0.9 * sin(b + 1.3 * wave_t))
                  + 0.3 * sin(2.3 * a - b + 0.7 * wave_t)
                  + 0.2 * sin(4.1 * a + 1.7 * b - 1.1 * wave_t))
        puff = 0.5 + 0.5 * ripple
        if disk_on > 0:
            ring_rho = R_IN + max(r - R0, 0) * 2.6
            rings, _, _ = gas(ang - TILT, ring_rho, t, spin)
            puff = puff * (1 - disk_on) + rings * disk_on
        reach = 0.32 * R0 * (0.7 + 0.6 * puff)
        aura = aura_k * exp(-(max(r - R0, 0) / reach) ** 1.6)
        aura *= 0.6 + 0.4 * puff

    u = x * CT + y * ST
    v = -x * ST + y * CT
    inc = INC + 0.09 * cam
    disk = 0.0
    phase, lr = ang, log(max(r, 1e-6) / R0)
    if disk_on > 0 and abs(v) < 0.16 and abs(u) < R_OUT * 1.15:
        rho = max(hypot(u, v / inc), 1e-6)
        if R_IN - 0.04 < rho < R_OUT + 0.2:
            phi = atan2(v / inc, u)
            streak, phase, lr = gas(phi, rho, t, spin)
            edge = smooth((rho - R_IN) / (0.25 * R0))
            edge *= smooth((R_OUT - rho) / (2.2 * R0))
            disk = 1.5 * edge * streak * (R_IN / rho)
            disk *= 1 - 0.25 * u / rho
            span = R0 + disk_on * (R_OUT * 1.1 - R0)
            disk *= smooth((t - 5.0) / 0.8)
            disk *= smooth((span - abs(u)) / (0.6 * R0))
            disk *= 0.55 + 0.45 * smooth((t - FLASH + 0.3) / 0.4)

    halo = 0.0
    if disk_on > 0 and r < 0.3:
        top = 0.5 - 0.5 * sin(ang - TILT)
        side = abs(cos(ang - TILT)) ** 10
        out = max(r - 1.1 * R0, 0)
        width = 0.2 * R0 + 0.24 * R0 * top + 0.45 * R0 * side
        band = exp(-(out / width) ** 2)
        band *= exp(-(min(r - 1.1 * R0, 0) / (0.2 * R0)) ** 2)
        rho = ((1 - side) * (R_IN + max(r - R0, 0) * 2.6)
               + side * max(r, R_IN))
        flow, _, _ = gas(ang - TILT, rho, t, spin)
        halo = 1.2 * band * flow * (0.5 + 0.8 * top)
        halo *= 1 - 0.25 * cos(ang - TILT)
        halo *= smooth((t - 5.0) / 2.2)

    soft = 1 - (1 - min(aura * 0.55, 1)) * (1 - min(halo, 1)) * (1 - min(disk, 1))
    soft = max(soft, disk, halo)
    heat = max(ring * (0.9 + 0.3 * smooth((t - 5) / 2)), soft)
    if t > FLASH:
        front = R0 + (t - FLASH) * 0.55
        shock = exp(-((r - front) / 0.02) ** 2) * exp(-(t - FLASH) / 0.5) * 0.9
        heat = max(heat, shock)
    heat *= 1 + 1.4 * flash
    if r < R0 * 0.97:
        heat = disk if v > 0 and disk > 0.2 else 0.0
    heat *= 1 - exit_progress

    if heat > 0.07:
        if ring > max(aura * 0.8, disk, halo, 0.25):
            direction = math.degrees(atan2(-cos(ang), -sin(ang))) % 180
            char = "-" if direction < 22.5 or direction >= 157.5 else "/" if direction < 67.5 else "|" if direction < 112.5 else "\\"
        else:
            level = min(int(heat * 3.6), 3)
            pool = POOLS[level]
            char = pool[(h + int(phase * 2 + lr * 6)) % len(pool)]
        tag = 0 if heat < 0.1 else 1 if heat < 0.2 else 2 if heat < 0.45 else 3 if heat < 0.75 else 4
        lum = min(1.3, 0.42 + 0.85 * heat)
        lum *= 0.35 + 0.65 * smooth((heat - 0.07) / 0.15)
        level = min(6, max(1, round(lum * 5)))
        if LIGHT_THEME:
            band = min(LIGHT_HEAT_BANDS - 1, max(0, round(
                (heat - 0.07) * (LIGHT_HEAT_BANDS - 1) / (2.0 - 0.07))))
            return char, LIGHT_ANSI[band][level - 1]
        return char, ANSI[tag][level - 1]

    rnd = h / 4294967296
    if r >= R0 and rnd < 0.0025:
        star = 0 if rnd < 0.0005 else 1 if rnd < 0.0012 else 2
        return ("+" if star == 0 else "*" if star == 1 else "."), STAR_ANSI[star]
    # Dust belongs to the disk; an unbounded lane scatters punctuation across
    # the whole screen, especially visibly on a light terminal background.
    if not LIGHT_THEME and t > 4 and R0 <= r < R_OUT and abs(u) < R_OUT:
        lane = exp(-((v - 0.02) / 0.09) ** 2)
        if rnd > 1 - 0.012 * lane:
            return (":" if rnd > 1 - 0.004 * lane else ","), ANSI[6][1]
    return SPACE, None


def render(t, columns, rows, exit_progress):
    after_flash = max(t - FLASH, 0)
    spin = 0.06 * t + 0.28 * (after_flash - 0.8 * (1 - exp(-after_flash / 0.8)))
    cam = smooth(smooth((t - FLASH + 0.3) / 2.6))
    zoom = 1 + 0.28 * cam
    flash = exp(-((t - FLASH) / 0.22) ** 2)
    ring_k = smooth((t - 0.3) / 2.2)
    disk_on = smooth((t - 5.0) / 2.8)
    aura_k = smooth((t - 2.2) / 1.8) * (1 - 0.65 * disk_on)
    lines = ["\x1b[H"]
    for row in range(rows):
        lines.append(f"\x1b[{row + 1};1H")
        last_color = None
        base_y = (row + 0.5) / rows - 0.5
        for col in range(columns):
            base_x = ((col + 0.5) / columns - 0.5) * columns * 0.5 / rows
            if exit_progress >= 1:
                char, color = SPACE, None
            else:
                char, color = pixel(base_x, base_y, t, spin, cam, flash,
                                    ring_k, aura_k, disk_on, zoom,
                                    exit_progress, row, col)
            if color is not None and color != last_color:
                lines.append(color)
                last_color = color
            lines.append(char)
        lines.append("\x1b[0m\x1b[K")
    return "".join(lines)


fd = sys.stdin.fileno()
original = termios.tcgetattr(fd)
try:
    tty.setcbreak(fd)
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    sys.stdout.flush()
    started = time.monotonic()
    last_size = None
    quit_started = None
    quit_t = 0.0
    while True:
        frame_start = time.monotonic()
        if quit_started is None and select.select([fd], [], [], 0)[0]:
            keys = os.read(fd, 64)
            if not keys or b"q" in keys.lower() or b"\x1b" in keys:
                if LOOP_MODE:
                    quit_started = frame_start
                    quit_t = (frame_start - started) * SPEED
                else:
                    break
        elapsed = frame_start - started
        if LOOP_MODE:
            t = quit_t if quit_started is not None else elapsed * SPEED
            exit_progress = (smooth((frame_start - quit_started) / EXIT_TIME)
                             if quit_started is not None else 0.0)
        else:
            t = min(INTRO_END, elapsed * SPEED)
            exit_progress = smooth((elapsed - INTRO_END / SPEED) / EXIT_TIME)
        size = shutil.get_terminal_size()
        if size.columns < 41 or size.lines < 14:
            break
        if size != last_size:
            sys.stdout.write("\x1b[2J")
            last_size = size
        sys.stdout.write(render(t, size.columns - 1, size.lines - 1,
                                exit_progress))
        sys.stdout.flush()
        if exit_progress >= 1:
            break
        time.sleep(max(0, 1 / 15 - (time.monotonic() - frame_start)))
except KeyboardInterrupt:
    pass
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, original)
    sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
    sys.stdout.flush()
PY
}

if [[ -o interactive && -t 0 && -t 1 &&
      ${TERM_PROGRAM-} == WezTerm &&
      -z ${NEOVIM_APP_SINGLE_SESSION-} &&
      -z ${BLACK_HOLE_ANIMATION_SHOWN-} &&
      ${BLACK_HOLE_ANIMATION:-true} != false &&
      ${BLACK_HOLE_ANIMATION:-true} != 0 ]]; then
  _black_hole_startup() {
    add-zsh-hook -d precmd _black_hole_startup
    export BLACK_HOLE_ANIMATION_SHOWN=1
    (( $+functions[title] )) && title black-hole black-hole
    black-hole --once
  }
  autoload -Uz add-zsh-hook
  add-zsh-hook precmd _black_hole_startup
fi
