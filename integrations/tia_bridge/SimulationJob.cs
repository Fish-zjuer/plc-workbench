// Native simulation via the documented PLCSIM Advanced API. No network download.
// https://docs.tia.siemens.cloud/ : Downloading PLC to a Windows folder (V21)
// https://developer.siemens.com/s7-plcsim-advanced/ : IInstance (.NET)
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;
using Siemens.Engineering;
using Siemens.Engineering.Compiler;
using Siemens.Engineering.Download;
using Siemens.Engineering.Download.Configurations;
using Siemens.Engineering.HW;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;

internal sealed class SimulationJob
{
    private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };
    private string evidence;
    private static void Emit(object value) { Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 }.Serialize(value)); }
    private void CheckCancel() { if (File.Exists(Path.Combine(evidence, "cancel.signal"))) throw new OperationCanceledException("Simulation cancelled"); }

    public int Run(string requestPath)
    {
        var request = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(requestPath));
        if ((string)request["schema"] != "tia-simulation-v1") throw new InvalidDataException("Unknown simulation protocol");
        evidence = (string)request["evidence_directory"];
        var api = new SimulationApi((string)request["simulation_api"]);
        string instanceName = "WB_" + Guid.NewGuid().ToString("N");
        string card = Path.Combine(api.DefaultStoragePath, instanceName, "SIMATIC_MC");
        // This is always a new random instance path. Never remove preexisting storage.
        if (Directory.Exists(Path.GetDirectoryName(card))) throw new IOException("Instance storage already exists");
        Directory.CreateDirectory(card);
        object instance = null;
        string cpuArticle = "";
        try
        {
            CheckCancel();
            using (var portal = new TiaPortal(TiaPortalMode.WithUserInterface))
            {
                var project = portal.Projects.Open(new FileInfo((string)request["project"]));
                try
                {
                    DeviceItem cpu;
                    var plc = CompileJob.FindPlcSoftware(project, out cpu);
                    if (plc == null) throw new InvalidOperationException("No PLC software in simulation template");
                    if (cpu == null) throw new InvalidOperationException("Cannot locate simulation CPU");
                    // The runtime API does not support S7-1200; refuse before exporting.
                    string article = Convert.ToString(cpu.GetAttribute("OrderNumber"), CultureInfo.InvariantCulture);
                    cpuArticle = article;
                    if (!article.StartsWith("6ES751", StringComparison.OrdinalIgnoreCase))
                    {
                        Emit(new { status = "behavior_not_supported", message = "Use a dedicated S7-1500 simulation template; found " + article });
                        return 2;
                    }
                    // OB1 in the disposable template is replaced by the test-only Main.
                    // Other OBs could execute unplanned logic and are refused.
                    var obs = AllBlocks(plc.BlockGroup).OfType<OB>().ToArray();
                    if (obs.Any(b => b.Number != 1)) throw new InvalidOperationException("Simulation template must contain only the cyclic OB1");
                    foreach (var ob in obs) ob.Delete();
                    var ext = plc.ExternalSourceGroup.ExternalSources.CreateFromFile("WB_Test", (string)request["source"]);
                    try { ext.GenerateBlocksFromSource(); }
                    catch (EngineeringTargetInvocationException error)
                    {
                        Emit(new { status = "harness_error", message = error.ToString(), phase = "generate_test_harness" }); return 2;
                    }
                    var compiled = plc.GetService<ICompilable>().Compile();
                    File.WriteAllText(Path.Combine(evidence, "harness_compile.json"), json.Serialize(new { errors = compiled.ErrorCount, warnings = compiled.WarningCount, state = compiled.State.ToString() }));
                    if (compiled.ErrorCount != 0) { Emit(new { status = "harness_error", message = "Siemens rejected the test harness; inspect harness_compile.json" }); return 2; }
                    CheckCancel();
                    var downloader = cpu.GetService<DownloadProvider>();
                    if (downloader == null) throw new InvalidOperationException("CPU has no virtual-memory-card download service");
                    var download = downloader.Download(new DirectoryInfo(card), ConfigureDownload);
                    File.WriteAllText(Path.Combine(evidence, "memory_card.json"), json.Serialize(new { state = download.State.ToString(), path = card }));
                    if (download.State.ToString() != "Success" && download.State.ToString() != "Warning") throw new InvalidOperationException("Virtual memory card export failed: " + download.State);
                    CopyDirectory(card, Path.Combine(evidence, "virtual_memory_card"));
                    project.Save();
                }
                finally { project.Close(); }
            }
            CheckCancel();
            instance = api.Register(instanceName);
            File.WriteAllText(Path.Combine(evidence, "simulator.json"), json.Serialize(new { owned_by = "plc-workbench", instance_name = instanceName, simulation_api = request["simulation_api"], memory_card = card }));
            api.Invoke(instance, "PowerOn", (uint)60000);
            CheckCancel();
            api.Invoke(instance, "UpdateTagList");
            api.Invoke(instance, "Run", (uint)60000);
            string db = (string)request["result_db"];
            var timer = Stopwatch.StartNew();
            double timeout = Convert.ToDouble(request["simulation_timeout_seconds"], CultureInfo.InvariantCulture);
            while (!(bool)api.Invoke(instance, "ReadBool", db + ".WB_Done"))
            {
                CheckCancel();
                if (timer.Elapsed.TotalSeconds > timeout) throw new TimeoutException("Siemens test harness did not finish");
                Thread.Sleep(20);
            }
            var names = ((IEnumerable)request["output_names"]).Cast<string>().ToArray();
            var types = ((IEnumerable)request["output_types"]).Cast<string>().ToArray();
            int count = Convert.ToInt32(request["row_count"], CultureInfo.InvariantCulture);
            var rows = new List<object>(); var times = new List<int>();
            for (int r = 0; r < count; r++)
            {
                CheckCancel(); var row = new Dictionary<string, object>();
                for (int c = 0; c < names.Length; c++) row[names[c]] = api.Read(instance, db + ".WB_Out" + c + "[" + r + "]", types[c]);
                rows.Add(row); times.Add((int)api.Invoke(instance, "ReadInt32", db + ".WB_ActualMs[" + r + "]"));
            }
            api.Shutdown(instance); instance = null;
            File.WriteAllText(Path.Combine(evidence, "simulator_closed.json"), json.Serialize(new { instance_name = instanceName, powered_off = true, unregistered = true }));
            Emit(new { status = "simulation_completed", simulation = true, instance_name = instanceName, cpu_order_number = cpuArticle,
                actual_rows = rows, actual_scan_times_ms = times, platform = "PLCSIM Advanced", scope = "Native finite tests; one FB invocation per supplied row" });
            return 0;
        }
        catch (Exception error) { Emit(new { status = "simulation_error", message = error.ToString(), instance_name = instanceName }); return 2; }
        finally
        {
            if (instance != null)
            {
                try
                {
                    api.Shutdown(instance);
                    File.WriteAllText(Path.Combine(evidence, "simulator_closed.json"), json.Serialize(new { instance_name = instanceName, powered_off = true, unregistered = true }));
                }
                catch (Exception error) { Console.Error.WriteLine("Owned simulator cleanup failed: " + error); }
            }
            // Preserve the generated card as evidence; no recursive deletion of runtime storage.
        }
    }

    private static void CopyDirectory(string source, string target)
    {
        Directory.CreateDirectory(target);
        foreach (string file in Directory.GetFiles(source)) File.Copy(file, Path.Combine(target, Path.GetFileName(file)));
        foreach (string child in Directory.GetDirectories(source)) CopyDirectory(child, Path.Combine(target, Path.GetFileName(child)));
    }

    private static IEnumerable<PlcBlock> AllBlocks(PlcBlockGroup group)
    {
        foreach (var block in group.Blocks) yield return block;
        foreach (var child in group.Groups) foreach (var block in AllBlocks(child)) yield return block;
    }

    private static void ConfigureDownload(DownloadConfiguration value)
    {
        if (value is TargetForSoftware target) target.CurrentSelection = TargetForSoftwareSelections.PlcSimulationAdvanced;
        else if (value is OverwriteOnMemoryCard card) card.CurrentSelection = OverwriteOnMemoryCardSelections.Load;
        else if (value is ConsistentBlocksDownload blocks) blocks.CurrentSelection = ConsistentBlocksDownloadSelections.ConsistentDownload;
        else if (value is AlarmTextLibrariesDownload alarms) alarms.CurrentSelection = AlarmTextLibrariesDownloadSelections.ConsistentDownload;
        else throw new InvalidOperationException("Unmodeled virtual-card configuration: " + value.GetType().FullName);
    }

    internal static int Cleanup(string manifest)
    {
        var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(manifest));
        string name = (string)data["instance_name"];
        if ((string)data["owned_by"] != "plc-workbench" || !System.Text.RegularExpressions.Regex.IsMatch(name, "^WB_[0-9a-f]{32}$")) throw new InvalidDataException("Not a workbench-owned simulator");
        var api = new SimulationApi((string)data["simulation_api"]);
        api.Shutdown(api.Attach(name)); return 0;
    }
}

// The optional mixed-mode assembly is loaded only for simulation. Compile-only
// users do not need PLCSIM installed. All invoked methods follow IInstance .NET.
internal sealed class SimulationApi
{
    private readonly Assembly assembly;
    private readonly Type manager;
    private readonly Type instanceType;
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool SetDllDirectory(string path);
    internal SimulationApi(string path)
    {
        if (!SetDllDirectory(Path.GetDirectoryName(Path.GetFullPath(path)))) throw new IOException("Cannot set PLCSIM API dependency path");
        assembly = Assembly.LoadFrom(path);
        manager = assembly.GetType("Siemens.Simatic.Simulation.Runtime.SimulationRuntimeManager", true);
        instanceType = assembly.GetType("Siemens.Simatic.Simulation.Runtime.IInstance", true);
    }
    internal string DefaultStoragePath => (string)manager.GetProperty("DefaultStoragePath").GetValue(null);
    internal object Register(string name)
    {
        var cpu = assembly.GetType("Siemens.Simatic.Simulation.Runtime.ECPUType", true);
        return manager.GetMethod("RegisterInstance", new[] { cpu, typeof(string) }).Invoke(null, new[] { Enum.Parse(cpu, "CPU1500_Unspecified"), name });
    }
    internal object Attach(string name) => manager.GetMethod("CreateInterface", new[] { typeof(string) }).Invoke(null, new object[] { name });
    internal object Invoke(object instance, string method, params object[] args)
    {
        var info = instanceType.GetMethod(method, args.Select(x => x.GetType()).ToArray());
        if (info == null) throw new MissingMethodException("PLCSIM API: " + method);
        var result = info.Invoke(instance, args);
        if (info.ReturnType.Name == "ERuntimeErrorCode" && Convert.ToInt32(result) != 0) throw new InvalidOperationException(method + ": " + result);
        return result;
    }
    internal object Read(object instance, string tag, string type)
    {
        string method;
        switch (type.ToUpperInvariant())
        {
            case "BOOL": method = "ReadBool"; break;
            case "SINT": method = "ReadInt8"; break;
            case "USINT": case "BYTE": method = "ReadUInt8"; break;
            case "INT": method = "ReadInt16"; break;
            case "UINT": case "WORD": method = "ReadUInt16"; break;
            case "DINT": method = "ReadInt32"; break;
            case "UDINT": case "DWORD": method = "ReadUInt32"; break;
            case "LINT": method = "ReadInt64"; break;
            case "ULINT": case "LWORD": method = "ReadUInt64"; break;
            case "REAL": method = "ReadFloat"; break;
            case "TIME": case "LTIME": case "LREAL": method = "ReadDouble"; break;
            default: throw new NotSupportedException("Native simulation output type: " + type);
        }
        return Invoke(instance, method, tag);
    }
    internal void Shutdown(object instance)
    {
        try { Invoke(instance, "PowerOff", (uint)60000); }
        finally { try { Invoke(instance, "UnregisterInstance"); } finally { (instance as IDisposable)?.Dispose(); } }
    }
}
