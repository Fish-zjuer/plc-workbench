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
        string card = Path.Combine(evidence, "virtual_memory_card");
        if (Directory.Exists(card)) throw new IOException("Refusing to overwrite exported card");
        Directory.CreateDirectory(card);
        string cpuArticle = "";
        try
        {
            Console.Error.WriteLine("Opening disposable S7-1500 simulation project");
            CheckCancel();
            using (var portal = TiaSession.Start())
            {
                var project = portal.Projects.Open(new FileInfo((string)request["project"]));
                try
                {
                    DeviceItem cpu;
                    var plc = CompileJob.FindPlcSoftware(project, out cpu);
                    if (plc == null) throw new InvalidOperationException("No PLC software in simulation template");
                    if (cpu == null) throw new InvalidOperationException("Cannot locate simulation CPU");
                    var simulationSettings = project.GetService<PlcSimulationSettingsProvider>();
                    if (simulationSettings == null) throw new InvalidOperationException("No project simulation settings service");
                    simulationSettings.IsSimulationDuringBlockCompilationEnabled = true;
                    // The runtime API does not support S7-1200; refuse before exporting.
                    string article = Convert.ToString(cpu.GetAttribute("OrderNumber"), CultureInfo.InvariantCulture);
                    cpuArticle = article;
                    string normalizedArticle = System.Text.RegularExpressions.Regex.Replace(article, @"\s+", "");
                    if (!normalizedArticle.StartsWith("6ES751", StringComparison.OrdinalIgnoreCase))
                    {
                        Emit(new { status = "behavior_not_supported", message = "Use a dedicated S7-1500 simulation template; found " + article });
                        return 2;
                    }
                    // OB1 in the disposable template is replaced by the test-only Main.
                    // Other OBs could execute unplanned logic and are refused.
                    var obs = AllBlocks(plc.BlockGroup).OfType<OB>().ToArray();
                    if (obs.Any(b => b.Number != 1)) throw new InvalidOperationException("Simulation template must contain only the cyclic OB1");
                    foreach (var ob in obs) ob.Delete();
                    Console.Error.WriteLine("Generating candidate and native test harness");
                    var ext = plc.ExternalSourceGroup.ExternalSources.CreateFromFile("WB_Test", (string)request["source"]);
                    try { ext.GenerateBlocksFromSource(); }
                    catch (EngineeringTargetInvocationException error)
                    {
                        Emit(new { status = "harness_error", message = error.ToString(), phase = "generate_test_harness" }); return 2;
                    }
                    Console.Error.WriteLine("Compiling simulation CPU hardware configuration");
                    var hardwareCompiler = cpu.GetService<ICompilable>();
                    if (hardwareCompiler == null) throw new InvalidOperationException("CPU has no hardware compile service");
                    var hardware = hardwareCompiler.Compile();
                    var hardwareDiagnostics = new List<object>();
                    CompileJob.CollectMessages(hardware.Messages, hardwareDiagnostics);
                    File.WriteAllText(Path.Combine(evidence, "hardware_compile.json"), json.Serialize(new { errors = hardware.ErrorCount, warnings = hardware.WarningCount, state = hardware.State.ToString(), diagnostics = hardwareDiagnostics }));
                    if (hardware.ErrorCount != 0) throw new InvalidOperationException("Simulation template hardware compilation failed; inspect hardware_compile.json");
                    var compiled = plc.GetService<ICompilable>().Compile();
                    var diagnostics = new List<object>();
                    CompileJob.CollectMessages(compiled.Messages, diagnostics);
                    File.WriteAllText(Path.Combine(evidence, "harness_compile.json"), json.Serialize(new { errors = compiled.ErrorCount, warnings = compiled.WarningCount, state = compiled.State.ToString(), diagnostics }));
                    if (compiled.ErrorCount != 0) { Emit(new { status = "harness_error", message = "Siemens rejected the test harness; inspect harness_compile.json" }); return 2; }
                    CheckCancel();
                    var downloader = cpu.GetService<DownloadProvider>();
                    Console.Error.WriteLine("Exporting virtual memory card for owned simulator");
                    if (downloader == null) throw new InvalidOperationException("CPU has no virtual-memory-card download service");
                    var download = downloader.Download(new DirectoryInfo(card), ConfigureDownload);
                    var downloadDiagnostics = new List<object>();
                    CollectDownloadMessages(download.Messages, downloadDiagnostics);
                    File.WriteAllText(Path.Combine(evidence, "memory_card.json"), json.Serialize(new { state = download.State.ToString(), path = card, errors = download.ErrorCount, warnings = download.WarningCount, diagnostics = downloadDiagnostics }));
                    if (download.State.ToString() != "Success" && download.State.ToString() != "Warning") throw new InvalidOperationException("Virtual memory card export failed: " + download.State);
                    project.Save();
                }
                finally { project.Close(); }
            }
            CheckCancel();
            File.WriteAllText(Path.Combine(evidence, "prepared_card.json"), json.Serialize(new
            {
                schema = "tia-prepared-card-v1", source_sha256 = request["source_sha256"],
                source_bundle_sha256 = SimulationCardJob.FileHash((string)request["source"]),
                bridge_sha256 = SimulationCardJob.FileHash(Assembly.GetExecutingAssembly().Location),
                runtime_host_sha256 = SimulationCardJob.FileHash(RuntimeWorker.Executable),
                cpu_order_number = cpuArticle, card_sha256 = SimulationCardJob.HashTree(card)
            }));
            Console.Error.WriteLine("Starting separate PLCSIM runtime host without Openness references");
            return RuntimeWorker.Run("--run-simulation-card", requestPath);
        }
        catch (Exception error)
        {
            Emit(new { status = "simulation_error", phase = "prepare_card", message = error.ToString() });
            return 2;
        }
    }

    private static void CollectDownloadMessages(DownloadResultMessageComposition messages, List<object> output)
    {
        foreach (DownloadResultMessage message in messages)
        {
            output.Add(new { state = message.State.ToString(), description = message.Message, errors = message.ErrorCount, warnings = message.WarningCount });
            CollectDownloadMessages(message.Messages, output);
        }
    }

    private static IEnumerable<PlcBlock> AllBlocks(PlcBlockGroup group)
    {
        foreach (var block in group.Blocks) yield return block;
        foreach (var child in group.Groups) foreach (var block in AllBlocks(child)) yield return block;
    }

    private static void ConfigureDownload(DownloadConfiguration value)
    {
        Console.Error.WriteLine("Virtual-card configuration: " + value.GetType().Name);
        if (value is TargetForSoftware target) target.CurrentSelection = TargetForSoftwareSelections.PlcSimulationAdvanced;
        else if (value is OverwriteOnMemoryCard card) card.CurrentSelection = OverwriteOnMemoryCardSelections.Load;
        else if (value is ConsistentBlocksDownload blocks) blocks.CurrentSelection = ConsistentBlocksDownloadSelections.ConsistentDownload;
        else if (value is AlarmTextLibrariesDownload alarms) alarms.CurrentSelection = AlarmTextLibrariesDownloadSelections.ConsistentDownload;
        else throw new InvalidOperationException("Unmodeled virtual-card configuration: " + value.GetType().FullName);
    }

}
