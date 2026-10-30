"""Unit tests for multi. Run: python3 -m unittest discover -s tests"""
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
_path = str(Path(__file__).resolve().parent.parent / "multi")
_spec = importlib.util.spec_from_loader("multi", SourceFileLoader("multi", _path))
multi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(multi)


def completed(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout=stdout)


class ResolveTest(unittest.TestCase):
    def test_bare_name_gets_com(self):
        self.assertEqual(multi.resolve("instagram"), "https://instagram.com")

    def test_domain_kept(self):
        self.assertEqual(multi.resolve("aws.amazon.com"), "https://aws.amazon.com")
        self.assertEqual(multi.resolve("cloud.oracle.com"), "https://cloud.oracle.com")

    def test_full_url_untouched(self):
        self.assertEqual(multi.resolve("http://example.com/a?b=1"), "http://example.com/a?b=1")

    def test_site_key(self):
        self.assertEqual(multi.site_key("https://aws.amazon.com"), "aws-amazon-com")
        self.assertEqual(multi.site_key("https://instagram.com/"), "instagram-com")


class LayoutTest(unittest.TestCase):
    area = (0, 28, 1500, 1052)

    def test_columns(self):
        for n in (1, 2, 3, 4):
            slots = multi.layout(n, self.area)
            self.assertEqual(len(slots), n)
            self.assertEqual([s[0] for s in slots], [i * (1500 // n) for i in range(n)])
            self.assertTrue(all(s[1:] == (28, 1500 // n, 1052) for s in slots))

    def test_columns_start_at_area_origin(self):
        slots = multi.layout(2, (1920, 28, 1500, 1052))
        self.assertEqual([s[0] for s in slots], [1920, 2670])

    def test_cascade_from_five(self):
        slots = multi.layout(5, (0, 0, 1000, 1000))
        self.assertEqual(len(slots), 5)
        self.assertEqual(slots[0], (0, 0, 600, 800))
        self.assertEqual(slots[4], (4 * multi.CASCADE_STEP, 4 * multi.CASCADE_STEP, 600, 800))


class WorkareaTest(unittest.TestCase):
    xprop = "_NET_WORKAREA(CARDINAL) = 0, 28, 3840, 1820, 0, 28, 3840, 1820\n"

    def run_workarea(self, xrandr):
        with mock.patch.object(multi.subprocess, "run", side_effect=[completed(xrandr), completed(self.xprop)]):
            return multi.workarea()

    def test_primary_monitor_minus_top_bar(self):
        xrandr = (
            "Monitors: 3\n"
            " 0: +*HDMI-1 1920/530x1080/300+1920+0  HDMI-1\n"
            " 1: +eDP-1 1368/340x768/190+1251+1080  eDP-1\n"
            " 2: +DVI-I-2 1920/530x1080/300+0+0  DVI-I-2\n"
        )
        self.assertEqual(self.run_workarea(xrandr), (1920, 28, 1920, 1052))

    def test_falls_back_to_first_monitor_without_primary(self):
        xrandr = "Monitors: 1\n 0: +DP-1 2560/600x1440/340+0+0  DP-1\n"
        self.assertEqual(self.run_workarea(xrandr), (0, 28, 2560, 1412))

    def test_lower_monitor_keeps_full_height(self):
        xrandr = " 0: +*eDP-1 1368/340x768/190+1251+1080  eDP-1\n"
        with mock.patch.object(multi.subprocess, "run", side_effect=[completed(xrandr)]):
            self.assertEqual(multi.workarea(), (1251, 1080, 1368, 768))


class LaunchTest(unittest.TestCase):
    def launch(self, profile, url="https://x.com", app=False):
        with mock.patch.object(multi.subprocess, "Popen") as popen:
            multi.launch(profile, url, (10, 20, 300, 400), app=app)
        return popen.call_args.args[0]

    def test_isolated_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "site" / "1"
            cmd = self.launch(profile)
            self.assertTrue(profile.is_dir())
        self.assertIn(f"--user-data-dir={profile}", cmd)
        self.assertIn("--window-position=10,20", cmd)
        self.assertIn("--window-size=300,400", cmd)
        self.assertIn("--ozone-platform=x11", cmd)
        self.assertEqual(cmd[-1], "https://x.com")

    def test_default_profile_has_no_user_data_dir(self):
        cmd = self.launch(None)
        self.assertFalse(any(a.startswith("--user-data-dir") for a in cmd))

    def test_app_mode(self):
        self.assertEqual(self.launch(None, "https://vault.bitwarden.com", app=True)[-1], "--app=https://vault.bitwarden.com")


class FakePath:
    """Stands in for Path(/proc/<pid>/cmdline)."""

    def __init__(self, table, path):
        self.table, self.pid = table, str(path).split("/")[2]

    def read_bytes(self):
        value = self.table[self.pid]
        if isinstance(value, Exception):
            raise value
        return value.encode()


class CloseTest(unittest.TestCase):
    data = "/home/u/.local/share/multi"
    procs = {
        # Chrome rewrites its title, so all args arrive as one space-joined entry
        "1": f"/opt/google/chrome/chrome --user-data-dir={data}/instagram-com/1 --no-first-run\0",
        "2": f"/opt/google/chrome/chrome --type=renderer --user-data-dir={data}/instagram-com/1\0",
        "3": f"/opt/google/chrome/chrome --user-data-dir={data}/example-com/1\0",
        "4": "bash\0-c\0sleep\0",
        "5": OSError("gone"),
        "6": "/opt/google/chrome/chrome\0",
        "7": f"/opt/google/chrome/chrome --user-data-dir={data}/_bitwarden --app=https://vault.bitwarden.com\0",
    }

    def killed(self, key):
        with mock.patch.object(multi, "DATA", Path(self.data)), \
                mock.patch.object(multi.os, "listdir", return_value=[*self.procs, "abc"]), \
                mock.patch.object(multi, "Path", lambda p: FakePath(self.procs, p)), \
                mock.patch.object(multi.os, "kill") as kill, \
                contextlib.redirect_stdout(io.StringIO()):
            multi.close(key)
        self.assertTrue(all(c.args[1] == multi.signal.SIGTERM for c in kill.call_args_list))
        return sorted(c.args[0] for c in kill.call_args_list)

    def test_close_all_skips_helpers_and_foreign_chrome(self):
        self.assertEqual(self.killed(None), [1, 3, 7])

    def test_close_one_site(self):
        self.assertEqual(self.killed("instagram-com"), [1])

    def test_close_unknown_site(self):
        self.assertEqual(self.killed("nope-com"), [])


class MainTest(unittest.TestCase):
    def run_main(self, *argv, **patches):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["multi", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                multi.main()
            except SystemExit as e:
                return e.code, out.getvalue(), err.getvalue()
        return None, out.getvalue(), err.getvalue()

    def test_version(self):
        for flag in ("-v", "--version"):
            code, out, _ = self.run_main(flag)
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), f"multi {multi.VERSION}")
        self.assertEqual(multi.VERSION, "0.1.0")

    def test_target_required(self):
        code, _, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("target is required", err)

    def test_count_must_be_positive(self):
        code, _, _ = self.run_main("instagram", "-x0")
        self.assertEqual(code, "multi: -x must be >= 1")

    def test_close_flags(self):
        for flag in ("-c", "-w", "--close"):
            with mock.patch.object(multi, "close") as close:
                self.run_main(flag)
            close.assert_called_once_with(None)
            with mock.patch.object(multi, "close") as close:
                self.run_main("aws.amazon.com", flag)
            close.assert_called_once_with("aws-amazon-com")

    def test_close_resolves_bare_name(self):
        with mock.patch.object(multi, "close") as close:
            self.run_main("instagram", "-c")
        close.assert_called_once_with("instagram-com")

    def flow(self, *argv):
        """Run main() with the screen and Chrome mocked out; return the launch calls."""
        with mock.patch.object(multi, "workarea", return_value=(0, 28, 1920, 1052)), \
                mock.patch.object(multi, "launch") as launch, \
                mock.patch.object(multi, "place", return_value=True) as place, \
                mock.patch.object(multi, "chrome_windows", return_value=set()):
            self.run_main(*argv)
        return launch.call_args_list, place

    def test_default_two_isolated_columns(self):
        calls, place = self.flow("instagram")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[0], multi.DATA / "instagram-com" / "1")
        self.assertEqual(calls[1].args[0], multi.DATA / "instagram-com" / "2")
        self.assertEqual(calls[0].args[2], (0, 28, 960, 1052))
        self.assertEqual(calls[1].args[2], (960, 28, 960, 1052))
        self.assertEqual(place.call_count, 2)

    def test_count_flag(self):
        calls, _ = self.flow("oracle", "-x3")
        self.assertEqual([c.args[1] for c in calls], ["https://oracle.com"] * 3)

    def test_bitwarden_uses_default_profile_and_shrinks_columns(self):
        calls, _ = self.flow("instagram", "--bitwarden")
        bw = calls[0]
        self.assertIsNone(bw.args[0])
        self.assertEqual(bw.args[1], multi.BITWARDEN_URL)
        self.assertTrue(bw.kwargs["app"])
        self.assertEqual(bw.args[2][0], 1920 - multi.BW_WIDTH)
        self.assertEqual([c.args[2][2] for c in calls[1:]], [(1920 - multi.BW_WIDTH) // 2] * 2)

    def test_default_flag_replaces_slot_one(self):
        calls, _ = self.flow("instagram", "-d", "-x3")
        self.assertIsNone(calls[0].args[0])
        self.assertEqual(calls[0].args[1], "https://instagram.com")
        self.assertEqual(calls[0].args[2][0], 0)
        self.assertEqual([c.args[0] for c in calls[1:]], [multi.DATA / "instagram-com" / "2", multi.DATA / "instagram-com" / "3"])

    def test_unplaceable_default_window_warns(self):
        with mock.patch.object(multi, "workarea", return_value=(0, 28, 1920, 1052)), \
                mock.patch.object(multi, "launch"), \
                mock.patch.object(multi, "place", return_value=False), \
                mock.patch.object(multi, "chrome_windows", return_value=set()):
            _, _, err = self.run_main("instagram", "--bitwarden")
        self.assertIn("could not position", err)


if __name__ == "__main__":
    unittest.main()
