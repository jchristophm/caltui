"""Panel geometry, pagination and palette regressions using local demo data."""
from datetime import date, datetime, time, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
import asyncio
from rich.text import Text

from rich.cells import cell_len
from test_multifeed import m, g, run_ui


class PanelProbe(m["CalTUI"]):
    def __init__(self, **kwargs):
        super().__init__(demo=True, **kwargs)
        self.reflows = self.rebuilds = 0

    def reflow_agenda(self):
        self.reflows += 1
        super().reflow_agenda()

    def rebuild_pages(self):
        self.rebuilds += 1
        super().rebuild_pages()


class Panels(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = Path(self.temporary.name) / "config.toml"
        self.patcher = patch.dict(g, {"CONFIG": self.config})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_calendar_keyboard_selection(self):
        async def check():
            app = PanelProbe()
            with patch.object(PanelProbe, "load_weather"):
                async with app.run_test(size=(120, 35)) as pilot:
                    await pilot.pause()
                    self.assertEqual(app.selected, date.today())
                    anchor, pages = app.anchor, list(app.pages)
                    app.selected = date(2024, 1, 31)
                    app.month = date(2024, 1, 1)
                    await pilot.press("right")
                    self.assertEqual(app.selected, date(2024, 2, 1))
                    self.assertEqual(app.month, date(2024, 2, 1))
                    await pilot.press("left", "shift+right")
                    self.assertEqual(app.selected, date(2024, 2, 29))
                    await pilot.press("shift+right", "shift+left")
                    self.assertEqual(app.selected, date(2024, 2, 29))
                    self.assertEqual(app.anchor, anchor)
                    self.assertEqual(app.pages, pages)
                    self.assertEqual(sum(c.has_class("selected") for c in app.query(".day")), 1)
                    await pilot.press("enter")
                    self.assertEqual(app.anchor, app.selected)
                    cell = next(c for c in app.query(".day") if c.day == date(2024, 2, 12))
                    await pilot.click(cell)
                    self.assertEqual(app.selected, date(2024, 2, 12))
                    self.assertEqual(app.anchor, app.selected)
                    await pilot.press("t")
                    self.assertEqual(app.selected, date.today())
                    self.assertEqual(app.month, date.today().replace(day=1))
                    await pilot.resize_terminal(60, 20)
                    await pilot.press("a")
                    selected = app.selected
                    await pilot.press("left", "right", "shift+right", "enter")
                    self.assertEqual(app.selected, selected)
        run_ui(check())

    def assert_footer(self, app, height):
        status, keys = app.query_one("#status"), app.query_one("#keys")
        self.assertEqual(keys.region.bottom, height)
        self.assertEqual(status.region.bottom, keys.region.y)
        for pane in (app.query_one("#calendar"), app.query_one("#agenda")):
            if pane.display:
                self.assertLessEqual(pane.region.bottom, status.region.y - (height >= 6))

    def assert_pages_fit(self, app):
        body = app.query_one("#agenda-body")
        if body.content_size.width >= 24 and body.content_size.height >= 3:
            self.assertEqual(body.content_size, app._agenda_size)
            for page in app.pages:
                self.assertLessEqual(len(page.plain.splitlines()), body.content_size.height)
                for line in page.plain.splitlines():
                    self.assertLessEqual(cell_len(line), body.content_size.width)

    def test_responsive_geometry_and_six_weeks(self):
        async def check():
            app = PanelProbe()
            async with app.run_test(size=(120, 35)) as pilot:
                nodes = list(app.query("*"))
                app.month = date(2026, 3, 1)  # Sunday start, 31 days: six weeks.
                for size, mode in [
                    ((160, 45), "wide"), ((120, 35), "wide"),
                    ((100, 24), "wide"), ((91, 21), "wide"),
                    ((90, 35), "stacked"), ((60, 35), "stacked"),
                    ((36, 32), "stacked"), ((60, 31), "compact"),
                    ((60, 24), "compact"), ((60, 20), "compact"),
                    ((28, 24), "compact"), ((20, 10), "compact"),
                    ((5, 4), "compact"), ((120, 35), "wide"),
                ]:
                    with self.subTest(size=size):
                        await pilot.resize_terminal(*size)
                        app.render_view()
                        await pilot.pause()
                        self.assertEqual(app.layout_mode, mode)
                        self.assertEqual(nodes, list(app.query("*")))
                        self.assert_footer(app, size[1])
                        cal, agenda = app.query_one("#calendar"), app.query_one("#agenda")
                        if cal.has_class("framed"):
                            self.assertEqual(cal.styles.border_top[0], "round")
                            self.assertEqual(cal.region.height, 18)
                            self.assertEqual(cal.content_size.height, 16)
                            cells = list(app.query(".day"))
                            self.assertEqual(len(cells), 42)
                            self.assertTrue(any(c.day == date(2026, 3, 31) for c in cells[-7:]))
                            for cell in cells:
                                self.assertEqual(cell.region.height, 2)
                                self.assertGreaterEqual(cell.region.y, cal.content_region.y)
                                self.assertLessEqual(cell.region.bottom, cal.content_region.bottom)
                            self.assertEqual([w.region.x for w in app.query("#weekdays Static")],
                                             [w.region.x for w in cells[:7]])
                        if mode == "wide":
                            self.assertEqual(cal.region.y, agenda.region.y)
                            self.assertEqual(agenda.region.x - cal.region.right, 1)
                            self.assertGreaterEqual(agenda.region.bottom, cal.region.bottom)
                            if app.query_one("#stage").content_size.height > 18:
                                self.assertGreater(agenda.region.bottom, cal.region.bottom)
                            self.assertEqual(agenda.region.bottom, app.query_one("#stage").content_region.bottom)
                        elif mode == "stacked":
                            self.assertEqual(agenda.region.y - cal.region.bottom, 1)
                            self.assertEqual(agenda.region.bottom, app.query_one("#stage").content_region.bottom)
                        if size == (60, 20) or size[0] < 28:
                            self.assertEqual(cal.styles.border_top[0], "")
                        self.assert_pages_fit(app)
        run_ui(check())

    def test_pagination_resizing_and_navigation(self):
        async def check():
            app = PanelProbe(agenda=True)
            async with app.run_test(size=(100, 24)) as pilot:
                today = date.today()
                rows = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//panel test//EN"]
                for i in range(80):
                    start = datetime.combine(today, time(8)) + timedelta(minutes=i)
                    end = start + timedelta(minutes=1)
                    title = "Short" if i % 2 else "A much longer appointment title, including wide 界 glyphs " * 4
                    rows += ["BEGIN:VEVENT", f"UID:panel-{i}",
                             f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}",
                             "SUMMARY:" + title, "LOCATION:Meeting room, a long descriptive location", "END:VEVENT"]
                rows.append("END:VCALENDAR")
                app.feed_query = m["parse_feed"](("\r\n".join(rows) + "\r\n").encode())
                app.render_view()
                await pilot.pause()
                for size in [(100, 24), (60, 35), (60, 24), (32, 24), (28, 24), (120, 35)]:
                    await pilot.resize_terminal(*size)
                    await pilot.pause()
                    self.assert_pages_fit(app)
                    body, agenda = app.query_one("#agenda-body"), app.query_one("#agenda")
                    self.assertEqual(body.content_region, agenda.content_region)
                    for page in app.pages:
                        for index, line in enumerate(page.plain.splitlines()):
                            if "↳" in line:
                                self.assertGreater(index, 0)
                                self.assertTrue(page.plain.splitlines()[index-1].strip())
                    self.assert_footer(app, size[1])
                await pilot.press("down")
                await pilot.pause()
                position = app.page_starts[app.page]
                await pilot.resize_terminal(20, 10)
                await pilot.pause()
                await pilot.resize_terminal(120, 35)
                await pilot.pause()
                self.assertEqual(app.page_starts[app.page], position)
                await pilot.press("c")
                day = next(c for c in app.query(".day") if c.day is not None)
                chosen = day.day
                await pilot.click(day)
                await pilot.pause()
                self.assertEqual(app.anchor, chosen)
                await pilot.press("right", "left", "t")
                self.assertEqual(app.anchor, date.today())
                self.assertTrue(any(c.has_class("today") for c in app.query(".day")))
                self.assertTrue(any(c.has_class("has-event") for c in app.query(".day")))
        run_ui(check())

    def test_live_palette_and_compact_fallback(self):
        async def check():
            app = PanelProbe()
            palettes = [
                {"10": (238, 238, 238), "11": (17, 17, 17), "4;4": (34, 68, 136),
                 "4;6": (85, 187, 204), "4;15": (255, 255, 255)},
                {"10": (34, 34, 34), "11": (238, 238, 238), "4;4": (170, 187, 221),
                 "4;6": (0, 102, 119), "4;15": (255, 255, 255)},
            ]
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause()
                before = (app.month, app.anchor, app.page_starts[app.page])
                background = app.query_one("#calendar").styles.background
                border_colors = []
                for palette in palettes:
                    for key, color in palette.items():
                        app.post_message(m["PaletteReport"](key, color))
                    await pilot.pause()
                    expected = m["blend"](palette["11"], app._text_colors["primary"], 96)
                    for selector in ("#calendar", "#agenda"):
                        panel = app.query_one(selector)
                        self.assertEqual(panel.styles.border_top[0], "round")
                        self.assertEqual(tuple(panel.styles.border_top[1].rgb), expected)
                        self.assertEqual(panel.styles.background, background)
                    border_colors.append(expected)
                    self.assertEqual((app.month, app.anchor, app.page_starts[app.page]), before)
                self.assertNotEqual(*border_colors)
                await pilot.resize_terminal(20, 10)
                await pilot.pause()
                for selector in ("#calendar", "#agenda"):
                    self.assertEqual(app.query_one(selector).styles.border_top[0], "")
                await pilot.resize_terminal(120, 35)
                await pilot.pause()
                self.assertEqual(tuple(app.query_one("#calendar").styles.border_top[1].rgb), border_colors[-1])
        run_ui(check())

    def test_optional_weather_fits_without_changing_panels(self):
        async def check():
            worker = m["CalTUI"].load_weather.__wrapped__
            with patch.object(m["CalTUI"], "load_weather") as fetch:
                app = PanelProbe()
                async with app.run_test(size=(120, 35)) as pilot:
                    await pilot.pause()
                    cal, agenda = app.query_one("#calendar"), app.query_one("#agenda")
                    regions = (cal.region, agenda.region, app.query_one("#status").region)
                    report = Text.from_ansi("\x1b[33mExample location\x1b[0m\n\n  \u2600  Clear")
                    app._weather = report
                    app.render_weather()
                    await pilot.pause()
                    weather = app.query_one("#weather")
                    self.assertTrue(weather.display)
                    self.assertEqual((cal.region, agenda.region, app.query_one("#status").region), regions)
                    self.assertEqual(weather.region.y, cal.region.bottom + 1)
                    self.assertEqual(weather.region.x, cal.region.x + (cal.region.width - weather.region.width) // 2)
                    self.assertEqual(weather.styles.border_top[0], "")
                    self.assertTrue(report.spans)
                    app._weather = Text("界" * 30 + "\nToo wide")
                    app.render_weather()
                    self.assertFalse(weather.display)  # Cells, not rune/ANSI counts.
                    app._weather = Text("line\n" * 20 + "Too tall")
                    app.render_weather()
                    self.assertFalse(weather.display)
                    app._weather = report
                    for size, visible in [((100, 24), False), ((60, 35), False),
                                          ((60, 20), False), ((120, 35), True)]:
                        await pilot.resize_terminal(*size)
                        await pilot.pause()
                        self.assertEqual(weather.display, visible)
                    self.assertEqual(fetch.call_count, 1)
                    await pilot.press("r")
                    await pilot.pause()
                    self.assertEqual(fetch.call_count, 2)
                    process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"Place\n  clear\n", b"")))
                    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as curl:
                        await worker(app)
                        curl.assert_awaited_once_with("curl", "-fsS", "--max-time", "4", "https://wttr.is/?0nq",
                                                     stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=FileNotFoundError)):
                        await worker(app)
                        await pilot.pause()
                    self.assertIsNone(app._weather)
                    self.assertFalse(weather.display)
        run_ui(check())

    def test_repeated_resize_settles(self):
        async def check():
            app = PanelProbe(agenda=True)
            async with app.run_test(size=(120, 35)) as pilot:
                for size in [(60, 35), (60, 20), (20, 10), (120, 35)] * 2:
                    before = app.reflows
                    await pilot.resize_terminal(*size)
                    await pilot.pause()
                    self.assertLess(app.reflows-before, 10, "resize caused repeated reflow cycles")
                    settled = (app.reflows, app.rebuilds, app._agenda_size, app._panel_style)
                    await pilot.pause()
                    self.assertEqual((app.reflows, app.rebuilds, app._agenda_size, app._panel_style), settled)
        run_ui(check())


if __name__ == "__main__":
    unittest.main()
