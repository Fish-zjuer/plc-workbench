// Minimal TIA Portal Openness V21 console bridge.
// Uses official Siemens Openness API patterns. Requires local V21 installation.
// Python supplies a disposable copy of the template, never the original project.
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Web.Script.Serialization;

using Siemens.Engineering;
using Siemens.Engineering.Compiler;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;

internal static class Program
{
    private static readonly string OpennessFolder =
        Environment.GetEnvironmentVariable("TIA_OPENNESS_DIR") ??
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            @"Siemens\Automation\Portal V21\PublicAPI\V21\net48");

    static Program()
    {
        AppDomain.CurrentDomain.AssemblyResolve += ResolveSiemensAssembly;
    }

    private static Assembly ResolveSiemensAssembly(object sender, ResolveEventArgs args)
    {
        var name = new AssemblyName(args.Name);
        if (!name.Name.StartsWith("Siemens.Engineering.", StringComparison.Ordinal))
            return null;
        var file = Path.Combine(OpennessFolder, name.Name + ".dll");
        if (!File.Exists(file)) return null;
        var assembly = Assembly.LoadFrom(file);
        if (assembly.GetName().FullName != name.FullName)
            throw new FileNotFoundException("TIA API version mismatch", file);
        return assembly;
    }

    public static int Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        if (args.Length != 2)
        {
            Console.Error.WriteLine("Usage: TiaBridge.exe <test_project.ap21> <source.scl>");
            return 2;
        }
        try
        {
            if (args[0] == "--list-simulation-cpus") return SimulationTemplate.List(args[1]);
            if (args[0] == "--create-simulation-template") return SimulationTemplate.Create(Path.GetFullPath(args[1]));
            if (args[0] == "--simulate") return new SimulationJob().Run(Path.GetFullPath(args[1]));
            if (args[0] == "--run-simulation-card" || args[0] == "--cleanup-simulator") return RuntimeWorker.Run(args[0], args[1]);
            return new CompileJob().Run(Path.GetFullPath(args[0]), Path.GetFullPath(args[1]));
        }
        catch (Exception error)
        {
            var output = new { status = "bridge_error", message = error.ToString() };
            Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer().Serialize(output));
            return 2;
        }
    }
}

internal sealed class CompileJob
{
    public int Run(string projectFile, string sclFile)
    {
        if (!File.Exists(projectFile)) throw new FileNotFoundException("TIA project not found", projectFile);
        if (!File.Exists(sclFile) || !sclFile.EndsWith(".scl", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("SCL source not found", sclFile);

        using (var portal = TiaSession.Start())
        {
            Project project = null;
            try
            {
                Console.Error.WriteLine("Opening disposable TIA compilation project");
                project = portal.Projects.Open(new FileInfo(projectFile));
                PlcSoftware plc = FindPlcSoftware(project);
                if (plc == null)
                    throw new InvalidOperationException("No PLC software in the test project");

                // Import external SCL source and generate a program block.
                // A different source entry name is used each run; the block in
                // the dedicated test project may be overwritten on generation.
                string sourceName = "WB_" + Guid.NewGuid().ToString("N").Substring(0, 8);
                var external = plc.ExternalSourceGroup.ExternalSources.CreateFromFile(sourceName, sclFile);
                Console.Error.WriteLine("Generating candidate blocks");
                try
                {
                    external.GenerateBlocksFromSource();
                }
                catch (Siemens.Engineering.EngineeringTargetInvocationException error)
                {
                    // Siemens may reject SCL during generation, before Compile().
                    Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer().Serialize(new
                    {
                        status = "generation_failed", phase = "generate_blocks",
                        message = error.ToString(), platform = "TIA Portal V21"
                    }));
                    return 1;
                }

                Console.Error.WriteLine("Compiling candidate PLC software");
                ICompilable compiler = plc.GetService<ICompilable>();
                if (compiler == null)
                    throw new InvalidOperationException("PLC compile service unavailable");
                CompilerResult result = compiler.Compile();
                var diagnostics = new List<object>();
                CollectMessages(result.Messages, diagnostics);
                var report = new
                {
                    status = result.ErrorCount == 0 ? "compile_passed" : "compile_failed",
                    errors = result.ErrorCount,
                    warnings = result.WarningCount,
                    state = result.State.ToString(),
                    diagnostics = diagnostics,
                    platform = "TIA Portal V21",
                    scope = "Vendor compilation only; no simulation or functional test"
                };
                project.Save();
                Console.WriteLine("WB_RESULT_JSON=" + new JavaScriptSerializer().Serialize(report));
                return result.ErrorCount == 0 ? 0 : 1;
            }
            finally
            {
                if (project != null) project.Close();
            }
        }
    }

    internal static void CollectMessages(CompilerResultMessageComposition list, List<object> output)
    {
        foreach (CompilerResultMessage item in list)
        {
            output.Add(new
            {
                path = Convert.ToString(item.Path),
                state = item.State.ToString(),
                description = item.Description,
                errors = item.ErrorCount,
                warnings = item.WarningCount
            });
            CollectMessages(item.Messages, output);
        }
    }

    // The device traversal is based on Siemens' official V21 example program.
    internal static PlcSoftware FindPlcSoftware(Project project)
    {
        DeviceItem cpu;
        return FindPlcSoftware(project, out cpu);
    }

    internal static PlcSoftware FindPlcSoftware(Project project, out DeviceItem cpu)
    {
        cpu = null;
        foreach (Device device in project.Devices)
        {
            var queue = new Queue<HardwareObject>();
            queue.Enqueue(device);
            while (queue.Count > 0)
            {
                foreach (DeviceItem item in queue.Dequeue().Items)
                {
                    if (!item.IsPlugged) continue;
                    if (item.Classification.HasFlag(DeviceItemClassifications.CPU))
                    {
                        var container = item.GetService<SoftwareContainer>();
                        var plc = container == null ? null : container.Software as PlcSoftware;
                        if (plc != null) { cpu = item; return plc; }
                    }
                    queue.Enqueue(item);
                }
            }
        }
        return null;
    }
}
