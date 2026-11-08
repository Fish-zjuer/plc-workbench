using System;
using System.IO;
using System.Web.Script.Serialization;

// Deliberately no Siemens.Engineering reference or assembly resolver here.
internal static class Program
{
    public static int Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        try
        {
            if (args.Length != 2) throw new ArgumentException("Expected runtime mode and request file");
            if (args[0] == "--run-simulation-card") return new SimulationCardJob().Run(Path.GetFullPath(args[1]));
            if (args[0] == "--cleanup-simulator") return SimulationCardJob.Cleanup(Path.GetFullPath(args[1]));
            throw new ArgumentException("Unknown runtime mode");
        }
        catch (Exception error)
        {
            Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer().Serialize(new { status = "bridge_error", message = error.ToString() }));
            return 2;
        }
    }
}
