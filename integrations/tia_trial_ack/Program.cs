// Optional, bounded acknowledgement of the existing PLCSIM trial reminder.
// This does not activate/extend licenses or handle Openness/security prompts.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Automation;

internal static class Program
{
    private static volatile bool stop;

    [STAThread]
    private static int Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        if (args.Contains("--self-test")) return SelfTest();
        bool acknowledge = args.Contains("--ack-trial-notice");
        int seconds = Number(args, "--timeout-seconds", 900, 1, 86400);
        int maximum = Number(args, "--max-clicks", 10, 1, 1000);
        if (seconds < 0 || maximum < 0) return 2;
        if (args.Contains("--help"))
        {
            Console.WriteLine("TiaTrialAck [--ack-trial-notice] [--timeout-seconds 900] [--max-clicks 10]\nDefault: observe only. Requires an unlocked interactive Windows desktop. Ctrl+C stops.\nOnly recognized Siemens PLCSIM remaining-trial-days reminders are eligible.");
            return 0;
        }
        Console.CancelKeyPress += (sender, e) => { e.Cancel = true; stop = true; };
        Console.WriteLine(acknowledge ? "Watching for PLCSIM remaining-trial-days notices; acknowledgement enabled." : "Observe-only: matching notices will be logged; no clicks.");
        var elapsed = Stopwatch.StartNew();
        var handled = new HashSet<string>();
        int clicks = 0;
        while (!stop && elapsed.Elapsed.TotalSeconds < seconds && clicks < maximum)
        {
            try
            {
                var windows = AutomationElement.RootElement.FindAll(TreeScope.Children,
                    new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window));
                foreach (AutomationElement window in windows)
                {
                    if (stop) break;
                    try
                    {
                        string title = window.Current.Name ?? "";
                        if (title.IndexOf("PLCSIM", StringComparison.OrdinalIgnoreCase) < 0) continue;
                        int pid = window.Current.ProcessId;
                        string identity = pid + ":" + window.Current.NativeWindowHandle;
                        if (handled.Contains(identity)) continue;
                        string processPath;
                        using (var process = Process.GetProcessById(pid)) processPath = process.MainModule.FileName;
                        if (!IsInstalledSiemens(processPath)) continue;
                        var nodes = window.FindAll(TreeScope.Descendants, Condition.TrueCondition);
                        if (nodes.Count > 500) continue;
                        string text = string.Join("\n", nodes.Cast<AutomationElement>()
                            .Where(n => n.Current.ControlType == ControlType.Text)
                            .Select(n => n.Current.Name ?? ""));
                        var buttons = nodes.Cast<AutomationElement>()
                            .Where(n => n.Current.ControlType == ControlType.Button).ToArray();
                        string[] names = buttons.Select(b => b.Current.Name ?? "").ToArray();
                        if (!IsTrialReminder(title, text, names)) continue;
                        var ok = buttons.Where(b => IsOk(b.Current.Name ?? "") && b.Current.IsEnabled && !b.Current.IsOffscreen).ToArray();
                        if (ok.Length != 1) continue;
                        Console.WriteLine(DateTimeOffset.Now.ToString("o") + " matched notice; pid=" + pid + "; title=" + title);
                        if (!acknowledge) { handled.Add(identity); continue; }
                        object pattern;
                        if (!ok[0].TryGetCurrentPattern(InvokePattern.Pattern, out pattern))
                        {
                            Console.WriteLine("No InvokePattern; leaving this window untouched.");
                            handled.Add(identity); continue;
                        }
                        // Re-read the window contents on the next pass if the
                        // UI changed; never send a global Enter or coordinate click.
                        ((InvokePattern)pattern).Invoke();
                        handled.Add(identity); clicks++;
                        Console.WriteLine("ACKNOWLEDGED trial notice; total=" + clicks);
                    }
                    catch (ElementNotAvailableException) { }
                    catch (System.ComponentModel.Win32Exception) { }
                    catch (InvalidOperationException) { }
                    catch (UnauthorizedAccessException) { }
                }
            }
            catch (Exception error)
            {
                Console.Error.WriteLine("UI inspection failed: " + error.Message);
                return 2;
            }
            Thread.Sleep(250);
        }
        Console.WriteLine("Watcher stopped; acknowledged=" + clicks);
        return 0;
    }

    private static int Number(string[] args, string option, int fallback, int low, int high)
    {
        int i = Array.IndexOf(args, option), value;
        if (i < 0) return fallback;
        if (i + 1 < args.Length && int.TryParse(args[i + 1], out value) && value >= low && value <= high) return value;
        Console.Error.WriteLine(option + " must be " + low + ".." + high); return -1;
    }

    private static bool IsInstalledSiemens(string path)
    {
        string absolute = Path.GetFullPath(path);
        string[] roots = { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                           Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86) };
        bool installed = roots.Where(r => !string.IsNullOrWhiteSpace(r)).Any(r =>
            absolute.StartsWith(Path.Combine(r, "Siemens") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ||
            absolute.StartsWith(Path.Combine(r, "Common Files", "Siemens") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase));
        return installed && (FileVersionInfo.GetVersionInfo(absolute).CompanyName ?? "")
            .IndexOf("Siemens", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    private static bool IsOk(string text)
    {
        string name = text.Replace("&", "").Trim();
        return name.Equals("OK", StringComparison.OrdinalIgnoreCase) || name == "确定";
    }

    internal static bool IsTrialReminder(string title, string text, string[] buttons)
    {
        string content = (text ?? "").ToLowerInvariant();
        if ((title ?? "").IndexOf("PLCSIM", StringComparison.OrdinalIgnoreCase) < 0) return false;
        bool trial = content.Contains("trial license") || content.Contains("试用许可证") || content.Contains("试用许可");
        bool expiry = content.Contains("will expire") || content.Contains("expire in") || content.Contains("到期") || content.Contains("剩余");
        bool days = System.Text.RegularExpressions.Regex.IsMatch(content, @"\d+\s*(?:days?\b|天)");
        // The ordinary reminder itself says the trial can be activated only
        // once. That explanatory sentence must not be mistaken for an
        // activation dialog; activation buttons are refused separately.
        string[] refused = { "no valid license key", "select the trial license", "password", "permission", "openness", "授权访问", "密码" };
        return trial && expiry && days && !refused.Any(content.Contains)
            && buttons.Count(IsOk) == 1
            && !buttons.Any(b => new[] { "activate", "skip", "allow", "yes", "激活", "允许", "是" }.Contains(b.Replace("&", "").Trim().ToLowerInvariant()));
    }

    private static int SelfTest()
    {
        string english = "Your trial license will expire in 21 days. It can be activated only once.";
        var checks = new[] {
            IsTrialReminder("PLCSIM Advanced", english, new[] { "OK" }),
            IsTrialReminder("PLCSIM Advanced", "试用许可证将在 20 天后到期，只能激活一次", new[] { "确定" }),
            !IsTrialReminder("Other app", english, new[] { "OK" }),
            !IsTrialReminder("PLCSIM Advanced", "No valid License Key was found. Trial License activation", new[] { "Activate", "Skip" }),
            !IsTrialReminder("PLCSIM Advanced", "Allow Openness permission?", new[] { "OK" }),
            !IsTrialReminder("PLCSIM Advanced", english, new[] { "OK", "OK" }),
            !IsTrialReminder("PLCSIM Advanced", english, new[] { "OK", "Activate" }),
            !IsTrialReminder("PLCSIM Advanced", "Trial license information", new[] { "OK" })
        };
        Console.WriteLine("Matcher self-tests: " + checks.Count(x => x) + "/" + checks.Length + "; no Windows UI accessed.");
        return checks.All(x => x) ? 0 : 1;
    }
}
