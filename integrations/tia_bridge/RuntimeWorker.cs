using System.Diagnostics;
using System.IO;
using System.Reflection;

internal static class RuntimeWorker
{
    internal static string Executable => Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location), "TiaRuntime.exe");

    internal static int Run(string mode, string input)
    {
        var start = new ProcessStartInfo(Executable, mode + " \"" + Path.GetFullPath(input) + "\"")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8, StandardErrorEncoding = System.Text.Encoding.UTF8
        };
        using (var child = Process.Start(start))
        {
            var stdout = child.StandardOutput.ReadToEndAsync();
            var stderr = child.StandardError.ReadToEndAsync();
            child.WaitForExit();
            var stem = mode == "--cleanup-simulator" ? "runtime-cleanup" : "runtime";
            var folder = Path.GetDirectoryName(Path.GetFullPath(input));
            File.WriteAllText(Path.Combine(folder, stem + "-stdout.txt"), stdout.Result);
            File.WriteAllText(Path.Combine(folder, stem + "-stderr.txt"), stderr.Result);
            System.Console.Out.Write(stdout.Result);
            System.Console.Error.Write(stderr.Result);
            return child.ExitCode;
        }
    }
}
