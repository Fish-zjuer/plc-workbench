using System;
using System.IO;
using System.Web.Script.Serialization;

internal static class BridgeProgress
{
    internal static void Record(string directory, string phase)
    {
        if (directory == null) return;
        var path = Path.Combine(directory, "bridge_progress.json");
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, new JavaScriptSerializer().Serialize(new
        {
            phase, updated_utc = DateTime.UtcNow.ToString("o"),
            process_id = System.Diagnostics.Process.GetCurrentProcess().Id
        }));
        if (File.Exists(path)) File.Replace(temporary, path, null);
        else File.Move(temporary, path);
        Console.Error.WriteLine("TIA phase: " + phase);
    }
}
