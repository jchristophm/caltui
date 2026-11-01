# calTUI

**A calendar that knows its place.**

Can you create events? Nope.

Can you edit events? Also nope.

Can you cancel that meeting you really don't want to attend? Unfortunately not.

But can you see what's on your calendar? Absolutely.

calTUI is a small, read-only terminal calendar and agenda. Give it an ICS
subscription, and it'll tell you what's coming up. No browser, no background
daemon, no elaborate account setup, and no fifteen different screens for
something you mostly just want to look at.

Sometimes you don't need to manage your calendar. You just need to read the damn thing.

## Features

- Responsive calendar and agenda in independent, subtle rounded panels: side-by-side, stacked, or a single view as terminal dimensions allow.
- A unified agenda from multiple ICS subscriptions, with independent caches.
- Recurring events, exceptions, cancellations, time zones, all-day and multiday appointments.
- Cached calendars displayed immediately, nonblocking TUI refreshes, and offline fallback.
- Automatic terminal color inheritance and WCAG AA text contrast adjustment (4.5:1) when the terminal reports its palette.
- Keyboard navigation and clickable calendar dates.
- JSON CLI for scripts and native Waybar JSON integration.
- No background service. It reads calendars when you run it. Revolutionary restraint.

## Screenshots

Screenshots will go here. None are included yet; run `caltui --demo` to see the
actual interface in your own terminal, with your own colors.

## Requirements

Python **3.11 or newer** is required (`tomllib` arrived in 3.11). The script's full
list of direct third-party dependencies is:

- **textual**
- **icalendar**
- **recurring-ical-events**
- **python-dateutil**
- **rich**

An interactive terminal is needed for the TUI; Waybar is optional. Linux is the
tested platform. The custom terminal color-query/input integration and PTY tests
are Linux-specific; other systems use Textual's default driver and are unverified.

Verified with Python 3.14.9, Textual 8.2.8, icalendar 7.3.0,
recurring-ical-events 3.9.0, python-dateutil 2.9.0, and Rich 15.0.0.
Python 3.11 is the source-level minimum, not a tested version here. Some Textual
internals are used, so future Textual versions may need compatibility checks.

Foot is the reference terminal. When palette queries are unsupported, calTUI uses
ANSI colors; a numerical contrast guarantee needs the terminal's reported colors.
Your terminal supplies the theme. calTUI has resisted acquiring a theme menu.

## Manual installation

From a checkout, create a private virtual environment and a small launcher:

```sh
mkdir -p "$HOME/.local/share/caltui" "$HOME/.local/bin"
python3 -m venv "$HOME/.local/share/caltui/venv"
"$HOME/.local/share/caltui/venv/bin/python" -m pip install \
  textual icalendar recurring-ical-events python-dateutil rich
install -m 755 caltui "$HOME/.local/share/caltui/caltui"
cat > "$HOME/.local/bin/caltui" <<'SH'
#!/bin/sh
exec "$HOME/.local/share/caltui/venv/bin/python" "$HOME/.local/share/caltui/caltui" "$@"
SH
chmod 755 "$HOME/.local/bin/caltui"
```

Ensure `~/.local/bin` is on your `PATH`, then run `caltui --demo`.
These commands replace any existing `~/.local/bin/caltui`; back yours up first
if needed. There is no automated installer yet.

For a quick run from the checkout, activate an environment with the dependencies
installed and use `python caltui --demo`.

## Configuration

The configuration lives at `~/.config/caltui/config.toml`. Copy the example without
overwriting an existing configuration:

```sh
mkdir -p "$HOME/.config/caltui"
cp -n config.example.toml "$HOME/.config/caltui/config.toml"
chmod 600 "$HOME/.config/caltui/config.toml"
```

Edit it directly or press `s` inside calTUI:

```toml
[[calendars]]
url = "" # Paste your private HTTPS ICS subscription URL here.

# Repeat for each additional subscription:
# [[calendars]]
# url = ""

[agenda]
days_back = 30
days_forward = 120

[refresh]
minutes = 30
```

Get a private ICS subscription URL from your provider. **Treat it like a password.**
It may contain an access token. Never publish it, commit your personal configuration,
or paste it into a bug report. URLs must start with `https://`. Empty URLs are
ignored and duplicates are loaded once. A legacy top-level `url = "…"` still works.

All three settings are optional, independently. No migration ceremony required.

| Setting | Default | Allowed integers |
| --- | --- | --- |
| `agenda.days_back` | 30 | 1–366 |
| `agenda.days_forward` | 120 | 1–366 |
| `refresh.minutes` | 30 | 1–10,080 |

The calendar and agenda expand and display events around **today's local system
date**, including the final future day. Navigating to another month does not move
this processing window. The year-sized bounds limit recurrence work. ICS feeds
still download in full; the window controls local processing, not a server filter.
CLI next-event searches can find events beyond it.

Refresh minutes is a shared cache-freshness policy for startup, `--next`, and
`--waybar`. One minute avoids excessive requests; one week bounds normal cache age.
Fresh subscriptions aren't downloaded unnecessarily; stale or missing subscriptions
refresh independently. Failed downloads preserve usable cached events.
Caches live in `~/.cache/caltui/`, with hashed per-calendar filenames and private
file permissions. Hashing is not encryption: cached appointments are private data.

This interval starts no daemon and promises no continuous polling. Startup,
settings reloads, and CLI invocations check freshness. An open TUI does not poll
subscriptions on a timer. Press `r` to request fresh data regardless of age.

After `s`, range-only edits rebuild the display without downloads. Interval edits
reevaluate cache ages, and calendar edits reload subscriptions. Invalid values
(including booleans, zero, floats, and strings) produce an error while retaining
working settings and appointments. calTUI never rewrites the configuration.
The editor priority is `VISUAL`, then `EDITOR`, then `nano`, then `vi`.

With no nonempty URLs, the interactive TUI automatically shows demo events.
`--demo` explicitly selects sample data without subscription downloads. CLI queries
without `--demo` require a configured calendar.

## Keyboard and mouse

| Key | Action |
| --- | --- |
| `←` / `→` | Select previous / next day |
| `Shift+←` / `Shift+→` | Previous / next month, clamping the selected day |
| `Enter` | Open agenda for the highlighted date |
| `↑` / `↓` | Previous / next agenda page |
| `c` | Calendar view |
| `a` | Agenda view |
| `t` | Return to today |
| `s` | Open configuration in your terminal editor |
| `r` | Force subscription refresh |
| `q` | Quit |

Left/right move the highlighted calendar selection, crossing months automatically.
Shift+left/right change months while retaining the day number where possible.
Only the selected date has a solid, terminal-palette-aware highlight. Moving the
highlight leaves the agenda unchanged until Enter; clicking a date selects it
and opens its agenda immediately. T resets both the calendar and agenda to today.
Up/down continue paging the agenda. In compact mode, calendar navigation is
active only in calendar view; choose views with `c` or `a`.

The calendar stays content-sized (18 rows including its border and six calendar
weeks); the agenda fills the remaining height and paginates inside its border.
Wide layouts top-align the panels with a one-column gap, leaving unused space
below the calendar outside its border. Stacked layouts use a one-row gap. The
application footer stays outside both panels. Pagination uses the agenda's actual
content region, and long date headings are ellipsized to fit.

With the normal footer spacing, side-by-side mode needs at least 91×21 cells;
stacked mode needs at least 36×32. Other sizes use the existing single-view
controls. Framing is omitted where a small view cannot accommodate it; terminal
palette changes update the muted border colors along with the text.

Wide layouts may show the original ANSI-colored `wttr.is` weather artwork below
the calendar, centered without a border. It is fetched asynchronously once when
needed with `curl -fsS --max-time 4 'https://wttr.is/?0nq'`; `r` can refresh it too.
Weather is hidden if the complete report cannot fit, in stacked/compact layouts,
or when the request fails. Resizing never refetches it or reduces panel space.

## Command-line integration

```sh
caltui                  # Interactive calendar
caltui --agenda         # Start the TUI in agenda view (also -a)
caltui --demo           # Explicit sample events
caltui --next           # Next future timed event as JSON
caltui --waybar         # The same search, formatted for Waybar
caltui --next --within 60
caltui --demo --waybar   # Preview bar output with sample events
caltui --help
```

`--agenda` starts the TUI; it is not a text export. `--next` and `--waybar` are
mutually exclusive. `--within N` accepts positive finite minutes and works only
with those two modes; an event exactly at the boundary is included.
Next-event searches include timed starts strictly after now, exclude all-day
events, and preserve recurrence exceptions and local time conversion. An event
already in progress is not the next future start.

With a local fixture containing a Planning event on January 1, 2030, at 10 AM local
time in Office, queried at 9 AM that day, verified `--next` output is:

```json
{"date": "2030-01-01", "time": "10:00 AM", "description": "Planning", "location": "Office"}
```

The corresponding `--waybar` output is:

```json
{"text": "10:00 AM · Planning", "tooltip": "Tuesday, January 1, 2030\n10:00 AM\nPlanning\nOffice", "class": "upcoming"}
```

These are fixture examples, not a prediction that your next meeting is in 2030.
`--demo` output varies with today's date and time.

No matching event produces empty `date`, `time`, `description`, and `location`
strings for `--next`. Waybar receives empty `text`, a `No upcoming timed appointments`
tooltip, and class `empty`. Total calendar failure gives `--next` an empty result,
a stderr diagnostic, and exit status 1. Waybar receives an empty-text object with
class `error` and an explanatory tooltip (exit status 0). Partial refresh failures
use available calendars and cached data, with a stderr warning.

### Waybar

Add `custom/caltui` to your chosen module list. For example, in Waybar's JSONC:

```jsonc
"modules-right": ["custom/caltui"],
"custom/caltui": {
  "exec": "caltui --waybar",
  "return-type": "json",
  "format": "{}",
  "interval": 60,
  "tooltip": true
}
```

Ensure `caltui` is on Waybar's `PATH`, or use an absolute path to the launcher.
No separate formatter required: JSON supplies `text`, `tooltip`, and CSS `class`
(`upcoming`, `empty`, or `error`). Feed text is escaped for Pango; long titles are
shortened for the bar, and future dates get a date prefix.
Waybar's interval is in **seconds**, while calTUI's freshness setting is in
**minutes**. Running the command each minute reuses fresh subscription caches.

## Tests

From the repository root, with the runtime dependencies installed:

```sh
PYTHONPATH=tests python -m unittest test_multifeed test_settings test_config_range test_waybar test_panels
python tests/test_layout.py
python tests/test_contrast.py
# Linux PTY integration checks:
python tests/test_settings_terminal.py
python tests/test_terminal_colors.py
```

Tests use synthetic calendars, temporary caches, and mocked network/time operations.
The PTY checks emulate a terminal; no real subscription is needed. Run visual and
PTY scripts explicitly: they execute checks at import time, so broad unittest
discovery is not the recommended runner.

## Philosophy

calTUI isn't trying to replace Google Calendar, Outlook, or a full-featured terminal
calendar manager. Keep creating, editing, and declining meetings there.

It exists to answer two questions:

- What's on my calendar?
- What's coming up next?

That's enough. **calTUI reads calendars. That's it.**

## MIT License

Copyright © 2026 Chris Moore. Available under the [MIT License](LICENSE).
Use it, change it, share it. The calendar remains unimpressed.
