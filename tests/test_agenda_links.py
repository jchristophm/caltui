"""Location spans and real agenda mouse dispatch, with browser launches mocked."""
from datetime import date, datetime, timedelta
import unittest
from unittest.mock import patch

from rich.console import Console
from test_multifeed import m, g, run_ui

URL = 'https://meet.example.invalid/join/room?name=demo%20guest&token=1234567890'


class AgendaLinks(unittest.TestCase):
    def item(self, location):
        start = datetime.combine(date.today(), datetime.min.time()).replace(hour=10)
        return m['Appointment'](start, start + timedelta(hours=1), False,
                                'Meeting', location, 'link-test')

    def detail(self, location, width=180, color='bright_black'):
        return m['event_line'](self.item(location), date.today(), width, color)[1]

    def targets(self, text):
        console = Console()
        return [(text.plain[i], text.get_style_at_offset(console, i))
                for i in range(len(text))
                if text.get_style_at_offset(console, i).meta.get('meeting_url')]

    def test_plain_and_unsupported(self):
        for location in ('Science Hall', 'ftp://example.test/a', 'javascript:alert(1)',
                         'file:///tmp/example', 'https://', 'https://[broken',
                         'javascript:https://example.test/a'):
            with self.subTest(location=location):
                self.assertFalse(self.targets(self.detail(location)))
                self.assertEqual(self.detail(location).plain, ' ' * 11 + '↳ ' + location)

    def test_url_only_embedded_and_punctuation(self):
        for location in (URL, 'Join (' + URL + '). Room 2', URL + ', then http://example.invalid/a_(b).'):
            with self.subTest(location=location):
                targets = self.targets(self.detail(location))
                self.assertTrue(targets)
                self.assertEqual(targets[0][1].meta['meeting_url'], URL)
                self.assertTrue(all(style.underline for _, style in targets))
                self.assertFalse(self.detail(location).get_style_at_offset(Console(), 11).meta)
        balanced = self.targets(self.detail('http://example.invalid/a_(b).'))
        self.assertEqual(balanced[-1][1].meta['meeting_url'], 'http://example.invalid/a_(b)')

    def test_truncation_and_color(self):
        for color in ('bright_black', '#b4b4b4'):
            detail = self.detail(URL, 35, color)
            self.assertTrue(detail.plain.endswith('…'))
            targets = self.targets(detail)
            self.assertTrue(targets)
            self.assertTrue(all(style.meta['meeting_url'] == URL for _, style in targets))
            for _, style in targets:
                self.assertEqual(style.color, Console().get_style(color).color)
                self.assertTrue(style.underline)

    def test_pages_and_demo_do_not_launch(self):
        with patch.object(g['webbrowser'], 'open') as browser:
            pages = m['agenda_pages']([(date.today(), [self.item(URL)] * 5)], 5, 35)
            self.assertGreater(len(pages), 1)
            self.assertTrue(all(self.targets(page) for page in pages))
            query = m['Calendar'].from_ical(m['demo_ics']())
            locations = [str(e.get('LOCATION', '')) for e in query.walk('VEVENT')]
            self.assertTrue(any('https://meet.example.invalid/' in loc and len(loc) > 80
                                for loc in locations))
            browser.assert_not_called()

    def test_mouse_and_navigation(self):
        async def check():
            app = m['CalTUI'](demo=True, agenda=True)
            with patch.object(g['webbrowser'], 'open') as browser:
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    await pilot.press('down', 'up', 'right', 'left', 't', 'a')
                    await pilot.resize_terminal(75, 24)
                    await pilot.pause()
                    browser.assert_not_called()
                    body = app.query_one('#agenda-body')
                    # Exercise real Textual hit testing and Rich metadata after pagination.
                    page = m['agenda_pages']([(date.today(), [self.item('Join ' + URL + '. Here')])],
                                             body.content_size.height, body.content_size.width)[0]
                    body.update(page)
                    await pilot.pause()
                    y = (body.content_size.height - 3) // 2 + 2
                    await pilot.click(body, offset=(14, y))  # ordinary location text
                    browser.assert_not_called()
                    await pilot.click(body, offset=(19, y))  # visible URL
                    await pilot.pause()
                    browser.assert_called_once_with(URL)
                    self.assertTrue(app.is_running)
                    await pilot.press('q')
        run_ui(check())
